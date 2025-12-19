import time, struct, numpy as np
from pyvisa import ResourceManager, errors as visa_errors

HORI_NUM = 10.0

# From Siglent example (partial; add more if you use other timebases)
TDIV_ENUM = [
    100e-12, 200e-12, 500e-12,
    1e-9, 2e-9, 5e-9,
    10e-9, 20e-9, 50e-9,
    100e-9, 200e-9, 500e-9,
    1e-6, 2e-6, 5e-6,
    10e-6, 20e-6, 50e-6,
    100e-6, 200e-6, 500e-6,
    1e-3, 2e-3, 5e-3,
    10e-3, 20e-3, 50e-3,
    100e-3, 200e-3, 500e-3,
    1, 2, 5, 10, 20, 50, 100, 200, 500, 1000,
]

def parse_wavedesc(desc: bytes):
    """Parse Siglent WAVEDESC block from :WAVeform:PREamble?"""

    def u16(o): return struct.unpack("<H", desc[o:o+2])[0]
    def u32(o): return struct.unpack("<I", desc[o:o+4])[0]
    def f32(o): return struct.unpack("<f", desc[o:o+4])[0]
    def f64(o): return struct.unpack("<d", desc[o:o+8])[0]

    comm_type    = u16(32)          # 0=BYTE, 1=WORD
    comm_order   = u16(34)          # 0=LSB, 1=MSB
    one_frame_pts= u32(116)         # points per frame
    read_frames  = u32(144)         # frames in THIS transfer
    sum_frames   = u32(148)         # total frames acquired
    v_gain       = f32(156)         # V/div (no probe)
    v_offset     = f32(160)         # V offset (no probe)
    code_per_div = f32(164)         # codes per div
    adc_bit      = u16(172)         # ADC resolution bits
    dt           = f32(176)         # s / sample
    delay        = f64(180)         # trigger offset in s
    tdiv_index   = u16(324)         # timebase enum
    probe        = f32(328)         # probe attenuation

    # time/div from enum (SDS2000X HD row of Table 2)
    TDIV_ENUM = [
        200e-12, 500e-12,
        1e-9, 2e-9, 5e-9,
        10e-9, 20e-9, 50e-9,
        100e-9, 200e-9, 500e-9,
        1e-6, 2e-6, 5e-6,
        10e-6, 20e-6, 50e-6,
        100e-6, 200e-6, 500e-6,
        1e-3, 2e-3, 5e-3,
        10e-3, 20e-3, 50e-3,
        100e-3, 200e-3, 500e-3,
        1, 2, 5, 10, 20, 50, 100, 200, 500, 1000,
    ]
    tdiv = TDIV_ENUM[tdiv_index] if 0 <= tdiv_index < len(TDIV_ENUM) else None

    vdiv = v_gain * probe      # actual V/div at input
    voff = v_offset * probe    # actual offset at input

    return {
        "comm_type": comm_type,
        "comm_order": comm_order,
        "one_frame_pts": one_frame_pts,
        "read_frames": read_frames,
        "sum_frames": sum_frames,
        "vdiv": vdiv,
        "voffset": voff,
        "code_per_div": code_per_div,
        "adc_bit": adc_bit,
        "dt": dt,
        "delay": delay,
        "tdiv": tdiv,
    }

def decode_sequence_waveforms(desc: bytes, data: bytes):
    """
    Given one WAVEDESC (desc) and one DATA? payload (data)
    from SDS2000X HD in sequence mode, return:
        t: (n_pts,) time axis [s]
        V: (n_frames, n_pts) voltages [V]
        meta: dict of preamble fields
    """
    m = parse_wavedesc(desc)

    comm_type    = m["comm_type"]
    comm_order   = m["comm_order"]
    npts         = m["one_frame_pts"]
    nfrm_report  = m["read_frames"]
    vdiv         = m["vdiv"]
    voff         = m["voffset"]
    code_per_div = m["code_per_div"] / 256 # SIGLENT WHY
    adc_bit      = 8#m["adc_bit"] SIGLENT WHY
    dt           = m["dt"]
    delay        = m["delay"]
    tdiv         = m["tdiv"]

    # ---- raw to unsigned codes ----
    if comm_type == 0:
        # BYTE mode (8-bit container)
        raw = np.frombuffer(data, dtype=np.uint8)
    else:
        # WORD mode (16-bit container)
        if comm_order == 1:   # MSB first
            raw16 = np.frombuffer(data, dtype=">u2")
        else:                 # LSB first
            raw16 = np.frombuffer(data, dtype="<u2")
        # Left-aligned ADC bits: shift down into lower bits
        shift = 16 - adc_bit
        raw = (raw16 >> shift).astype(np.uint16)

        print(raw)

    # ---- reshape into frames ----
    total_pts = raw.size
    nfrm = total_pts // npts
    raw = raw[: nfrm * npts].reshape(nfrm, npts)

    # ---- unsigned -> signed code_value ----
    # Use model-agnostic 2's complement based on adc_bit
    full   = 1 << adc_bit
    center = (full // 2) - 1      # e.g. 2047 for 12-bit
    codes = raw.astype(np.int32)
    neg = codes > center
    codes[neg] -= full

    # ---- code -> volts (Siglent formula) ----
    # V = code_value * (vdiv / code_per_div) - voffset
    scale = vdiv / code_per_div
    V = codes.astype(np.float64) * scale - voff

    # ---- time base ----
    # time = -delay - (tdiv * GRID / 2) + index * dt
    idx = np.arange(npts, dtype=np.float64)
    if tdiv is not None:
        t0 = -delay - (tdiv * HORI_NUM / 2.0)
    else:
        t0 = -delay
    t = t0 + idx * dt

    return t, V, m

def read_line(inst):
    buf = bytearray()
    while True:
        b = inst.read_bytes(1)
        if b == b'\n': return buf.decode('ascii', 'ignore').strip()
        buf += b

def read_hash_block(inst):
    # Skip any "C1:WF ..." prefix until '#'
    while True:
        b = inst.read_bytes(1)
        if b == b'#': break
    nd = int(inst.read_bytes(1).decode())
    n  = int(inst.read_bytes(nd).decode())
    payload = inst.read_bytes(n)
    # eat trailing CR/LF (non-blocking)
    try:
        inst.timeout = 1
        while True:
            c = inst.read_bytes(1)
            if c not in (b'\r', b'\n'): break
    except visa_errors.VisaIOError:
        pass
    finally:
        inst.timeout = 10000
    return payload

rm = ResourceManager()
scope = rm.open_resource("TCPIP0::10.11.13.220::5025::SOCKET")  # or USB0::...::INSTR
scope.write_termination = '\n'
scope.read_termination  = None
scope.timeout = 10000

# --- one-time config ---
scope.write(":STOP")
scope.write(":WAV:INT 0")
scope.write(":WAVeform:WIDTh BYTE")
scope.write(":WAV:WIDT BYTE; :WAV:FORM BYTE")
scope.write(":ACQ:TYPE NORM")
scope.write(":ACQ:MMAN FSRate")          # fixed sample rate
scope.write(":ACQ:SRAT 2.0E9")           # 10 kS/s
#scope.write(":TIMEBASE:SCAL 0.002; :TIMEBASE:POS 0")  # 2 ms/div
scope.write(":CHAN1:DISP ON; :WAV:SOUR C1")
scope.write(":HISTory OFF")              # avoid History interfering with seq
scope.write(":RUN")
#scope.write(":MEAS:CLE; :MEAS:ITEM DELay,C3,C2; :MEAS:ITEM PHASe,C3,C2")
# (If you run a fast MEAS loop normally, pause it during the burst capture below.)

def capture_burst_and_read(N=200):
    # Arm segmented capture: exactly N segments, then stop
    scope.write(":ACQ:SEQuence ON")
    scope.write(f":ACQ:SEQuence:COUNt {N}")
    scope.write(":TRIGger:MODE SINGle")
    scope.write(":TRIGger:RUN")
    # Wait until stopped (acq done). Poll a light ASCII that changes on stop:

    print("Wait for trigger...", end='\t\t\t\r')
    while True:
        scope.write(":TRIG:STAT?")
        st = read_line(scope)  # e.g., "STOP"
        if "STOP" in st.upper(): break
        time.sleep(0.02)
    print("Done! Calculating...", end='\t\t\t\r')

    st = time.time()

    # Freeze a consistent snapshot is already ensured (we're stopped)
    scope.write(":WAVeform:SEQuence 0,1")         # or 0,<next_start> in your loop
    scope.write(":WAVeform:SOURce C1")
    scope.write(":WAVeform:PREamble?")
    desc = read_hash_block(scope)                 # returns WAVEDESC payload

    scope.write(":WAVeform:DATA?")
    data = read_hash_block(scope)                 # returns concatenated frame data

    # 3) Decode to time + voltages
    t, V, meta = decode_sequence_waveforms(desc, data)

    et = time.time()
    print(f"Took {et- st} seconds. This results in a capture % of: {10.0 / (10 + et - st)}")
    return t, V, meta

# Example loop: burst every ~1.5 s
while True:
    t, V, meta = capture_burst_and_read(N=250)  # ~250*20 ms ≈ 5 s of data if triggers come fast
    print(f"burst: {len(V)} frames, {len(t)} pts, {meta}")
    print(V[0])
    print(V[0].min())
    print(V[0].max())
    print(V[0].mean())
    # ... process frames here ...
    # If you want your MEAS loop, resume :RUN and do it between bursts.
    #scope.write(":RUN")
    #scope.write(":STOP")