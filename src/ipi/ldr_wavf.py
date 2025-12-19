import time, struct
import numpy as np
import pyvisa
from pyvisa import errors as visa_errors, Resource

# -------- helpers --------

def _drain_input(s, max_ms=2000):
    """Non-blocking drain of any leftover bytes in the input buffer."""
    old_to, old_rt = s.timeout, s.read_termination
    s.timeout, s.read_termination = 5, None
    t0 = time.time()
    try:
        while (time.time()-t0)*1000 < max_ms:
            try:
                junk = s.read_raw()
                print ("cleared byte")
                if not junk:
                    break
            except visa_errors.VisaIOError as e:
                # timeout => buffer is empty
                if e.error_code == visa_errors.VI_ERROR_TMO:
                    break
                raise
    finally:
        s.timeout, s.read_termination = old_to, old_rt

def read_hash_block(inst: Resource):
    """Read a single IEEE-488.2 block even if the device prepends ASCII like 'C1:WF ...'.
    Skips anything before '#', then reads exactly the payload length, and eats trailing CR/LF."""
    old_rt, old_to = inst.read_termination, inst.timeout
    inst.read_termination = None
    try:
        # Find the '#' header (skip 'C1:WF ', 'DAT2,', '\r\n', spaces, etc.)
        while True:
            b = inst.read_bytes(1)
            if b == b'#':
                break
        nd = int(inst.read_bytes(1).decode())
        n  = int(inst.read_bytes(nd).decode())
        payload = inst.read_bytes(n)

        # Non-blocking swallow of one/two trailing terminators
        inst.timeout = 1
        try:
            while True:
                c = inst.read_bytes(1)
                if c not in (b'\r', b'\n'):
                    # unread not possible; we'll just ignore if extra data arrived
                    break
        except visa_errors.VisaIOError:
            pass
        return payload
    finally:
        _drain_input(inst)
        inst.read_termination, inst.timeout = old_rt, old_to

def read_new_frames(inst: Resource, start_frame_idx: int, ch="C1"):
    """
    Sequence bulk read:
      - tells scope which frames to send (0 = as many as available),
      - reads PREamble (WAVEDESC) block,
      - reads DATA block and reshapes [n_frames, n_points].
    Assumes :WAV:WIDT BYTE.
    Returns (frames_uint8[N,P], next_start_idx, dt_seconds).
    """
    # ask for frames
    inst.write(f":WAVeform:SEQuence 0,{start_frame_idx}")
    inst.write(f":WAVeform:SOURce {ch}")

    # PREamble -> WAVEDESC binary block with ASCII prefix
    inst.write(":WAVeform:PREamble?")
    desc = read_hash_block(inst)

    # Parse just what we need from WAVEDESC (little-endian)
    def u32(o): return int.from_bytes(desc[o:o+4], 'little')
    def f32(o): return struct.unpack('<f', desc[o:o+4])[0]
    npts = u32(116)              # points per frame
    dt   = f32(176)              # seconds/sample

    # DATA block (may be prefixed by 'C1:WF DAT2,')
    inst.write(":WAVeform:DATA?")
    data = read_hash_block(inst)

    # Some firmwares stick CR/LF after the payload; trim by npts
    nfrm = len(data) // npts
    data = data[: nfrm * npts]
    arr  = np.frombuffer(data, dtype=np.uint8).reshape(nfrm, npts)

    next_start = start_frame_idx + nfrm
    return arr, next_start, dt

def configure_for_sequence(inst, source='C1', s_rate=10_000, tdiv=2e-3, seg_count=4000):
    inst.write(":STOP")
    # 2 ms/div, fixed 10 kS/s sampling
    inst.write(f":TIMebase:SCALe {tdiv}")                # 2 ms/div
    inst.write(":ACQuire:MMANagement FSRate")            # Fixed sampling-rate mode
    inst.write(f":ACQuire:SRATe {float(s_rate):.3E}")    # 10 kS/s
    inst.write(":ACQuire:TYPE NORMal")
    # sequence mode (segmented)
    inst.write(":ACQuire:SEQuence ON")
    inst.write(f":ACQuire:SEQuence:COUNt {seg_count}")
    # History ON lets us read past frames while we stop/run
    inst.write(":HISTory ON")
    # Waveform transfer settings (BYTE → 8-bit for smallest payload)
    inst.write(f":WAVeform:SOURce {source}")
    inst.write(":WAVeform:WIDTh BYTE")
    inst.write(":WAVeform:STARt 0")
    inst.write(":WAVeform:POINt 0")                      # whole frame
    inst.write(":WAVeform:INTerval 1")                      # whole frame
    inst.chunk_size = 20 * 1024 * 1024                   # avoid chunking on bigger reads
    inst.timeout = 5000
    inst.write(":RUN")

# -------- main example --------
rm = pyvisa.ResourceManager()
# Replace with your USB or LAN VISA resource string
scope = rm.open_resource("TCPIP0::10.11.13.220::INSTR")
scope.write_termination = '\n'
scope.read_termination  = '\n'

print(scope.query("*IDN?").strip())

configure_for_sequence(scope, source='C1', s_rate=10_000, tdiv=2e-3, seg_count=8000)

next_start = 1
READ_PERIOD_S = 1.2   # read roughly every 1–2 s

try:
    while True:
        time.sleep(READ_PERIOD_S)
        # Freeze briefly to get a consistent snapshot (optional; remove if you prefer continuous run)
        scope.write(":STOP")
        frames, next_start, dt = read_new_frames(scope, next_start)
        scope.write(":RUN")

        if frames.size:
            # Do your processing here; 'frames' is shape = (n_frames, ~200 samples)
            # Example: compute mean or edge times etc.
            print(f"got {frames.shape[0]} frames, {frames.shape[1]} pts/frame, dt={dt:.6e}s")
        else:
            print("no new frames yet")

except KeyboardInterrupt:
    pass
finally:
    scope.write(":STOP")
    scope.close()
    rm.close()