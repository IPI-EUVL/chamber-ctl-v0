import time, struct, numpy as np
from pyvisa import ResourceManager, errors as visa_errors

def read_line(inst):
    buf = bytearray()
    while True:
        b = inst.read_bytes(1)
        if b == b'\n': return buf.decode('ascii', 'ignore').strip()
        buf += b

def read_hash_block(inst):
    # Skip any "C1:WF ..." prefix until '#'
    while True:
        try:
            b = inst.read_bytes(1)
            if b == b'#': break
        except visa_errors.VisaIOError:
            pass
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
        inst.timeout = 1000
    return payload

rm = ResourceManager()
scope = rm.open_resource("TCPIP0::10.11.13.220::5025::SOCKET")  # or USB0::...::INSTR
scope.write_termination = '\n'
scope.read_termination  = None
scope.timeout = 10000

# --- one-time config ---
scope.write(":STOP")
scope.write(":WAV:INT 0")
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
    scope.write(":SINGle")
    # Wait until stopped (acq done). Poll a light ASCII that changes on stop:
    while True:
        scope.write(":TRIG:STAT?")
        st = read_line(scope)  # e.g., "STOP"
        print(st)
        if "STOP" in st.upper(): break
        time.sleep(0.02)

    # Freeze a consistent snapshot is already ensured (we're stopped)
    scope.write(":WAV:SEQuence 0,1")   # request all frames starting at 1
    scope.write(":WAV:PRE?")
    desc = read_hash_block(scope)
    u32 = lambda o: int.from_bytes(desc[o:o+4], 'little')
    f32 = lambda o: struct.unpack('<f', desc[o:o+4])[0]
    npts = u32(116)                    # points per frame
    dt   = f32(176)                    # seconds/sample

    scope.write(":WAV:DATA?")
    data = read_hash_block(scope)
    nfrm = len(data)//npts
    arr  = np.frombuffer(data[:nfrm*npts], dtype=np.uint8).reshape(nfrm, npts)

    print(len(arr))
    print(arr.shape)
    return arr, dt

# Example loop: burst every ~1.5 s
while True:
    frames, dt = capture_burst_and_read(N=250)  # ~250*20 ms ≈ 5 s of data if triggers come fast
    print(frames[0])
    print(frames[1])
    print(frames[2])
    print(frames[3])
    print(frames[10])
    print(frames[100])
    print(f"burst: {frames.shape[0]} frames, {frames.shape[1]} pts, dt={dt:.3e}s")
    # ... process frames here ...
    # If you want your MEAS loop, resume :RUN and do it between bursts.
    #scope.write(":RUN")
    #scope.write(":STOP")