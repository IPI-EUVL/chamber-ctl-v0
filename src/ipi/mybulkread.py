import re, time, struct, numpy as np
from pyvisa import ResourceManager, errors as visa_errors

# ---- low-level readers (do NOT switch VISA terminations anywhere) ----
def read_line(inst):
    buf = bytearray()
    while True:
        b = inst.read_bytes(1)
        if b == b'\n':
            return buf.decode('ascii', errors='ignore').strip()
        buf += b

def read_hash_block(inst):
    # Find '#' (skip any "C1:WF PRE," prefix and CR/LF)
    while True:
        b = inst.read_bytes(1)
        if b == b'#':
            break
    nd = int(inst.read_bytes(1).decode())
    n  = int(inst.read_bytes(nd).decode())
    payload = inst.read_bytes(n)
    # swallow any CR/LF after the payload (non-blocking)
    try:
        inst.timeout = 100
        while True:
            break
            c = inst.read_bytes(1)
            if c not in (b'\r', b'\n'):
                break
            #inst.read_bytes(1)
    except visa_errors.VisaIOError:
        pass
    finally:
        pass
        scope.timeout = 10000
    return payload

# ---- helpers ----
_float_pat = re.compile(r'[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?')
def parse_float(s):
    m = _float_pat.search(s)
    if not m: return None
    x = float(m.group(0))
    # Siglent uses 9.9e37 (or similar) as "invalid"
    return None if abs(x) > 1e30 else x

def meas_delay_phase(inst):
    # 1 write with 2 queries (reduce RTT), then read two lines
    inst.write(":MEAS:RES? DELay,C3,C2;:MEAS:RES? PHASe,C3,C2")
    dt_s = parse_float(read_line(inst))
    ph_d = parse_float(read_line(inst))
    return dt_s, ph_d

def seq_read_new_frames(inst, start_idx, ch="C1"):
    inst.write(f":WAV:SEQuence 0,1")
    inst.write(f":WAV:SOUR {ch}")

    # PREamble (WAVEDESC) as a # block with "C1:WF PRE," prefix
    inst.write(":WAV:PRE?")
    desc = read_hash_block(inst)

    # Parse only what we need (little-endian)
    u32 = lambda o: int.from_bytes(desc[o:o+4], 'little')
    f32 = lambda o: struct.unpack('<f', desc[o:o+4])[0]
    npts = u32(116)          # points per frame
    dt   = f32(176)          # seconds/sample

    # DATA block (with "C1:WF DAT2," prefix)
    inst.write(":WAV:DATA?")
    data = read_hash_block(inst)

    nfrm = len(data) // npts
    data = data[: nfrm * npts]
    arr  = np.frombuffer(data, dtype=np.uint8).reshape(nfrm, npts)
    return arr, start_idx + nfrm, dt

def seq_read(inst, next_start, ch="C1"):
    inst.write(":STOP")
    inst.write(f":WAV:SEQuence 0,{next_start}")
    inst.write(f":WAV:SOUR {ch}")
    inst.write(":WAV:PRE?")
    desc = read_hash_block(inst)
    u32 = lambda o: int.from_bytes(desc[o:o+4], 'little')
    f32 = lambda o: struct.unpack('<f', desc[o:o+4])[0]
    npts = u32(116); dt = f32(176)
    sum_frames = u32(148)  # total frames acquired so far

    inst.write(":WAV:DATA?")
    data = read_hash_block(inst)
    nfrm = len(data)//npts
    frames = np.frombuffer(data[:nfrm*npts], dtype=np.uint8).reshape(nfrm, npts)
    inst.write(":RUN")

    # Advance next_start, detect wrap/reset
    if nfrm == 0:
        # If total fell behind our pointer, reset pointer
        if sum_frames < next_start:
            next_start = 1
    else:
        next_start += nfrm
    return frames, next_start, dt

# ---- example wiring: MEAS at ~20 Hz, LDR sequence dump every ~1.2 s ----
rm = ResourceManager()
# Prefer raw socket for LAN; USB works too. Keep read_termination=None.
scope = rm.open_resource("TCPIP0::10.11.13.220::5025::SOCKET")
scope.write_termination = '\n'
scope.read_termination  = None
scope.timeout = 10000

# Minimal one-time setup (adjust to your liking)
scope.write(":STOP")
scope.write(":WAV:INT 0")
scope.write(":WAV:WIDT BYTE; :WAV:FORM BYTE")
scope.write(":ACQ:TYPE NORM")
scope.write(":ACQ:SEQuence ON; :ACQ:SEQuence:COUNt 1000")

scope.write(":ACQ:MDEP 10k")        # Match screen memory depth (10Mpts)  
scope.write(":TIMebse:SCALe 2e-3")       # 5ms per division
scope.write(":TIMebse:DELay 8e-3")

scope.write(":CHAN1:DISP ON; :CHAN2:DISP ON; :CHAN3:DISP ON")
scope.write(":TRIG:MODE NORM; :TRIG:EDGE:SOUR C3; :TRIG:EDGE:SLOP RIS")
#scope.write(":TIMebase:SCALe 2e-3; :TIMebase:POSition 8e-3")
scope.write(":MEAS:CLE; :MEAS:ITEM DELay,C3,C2; :MEAS:ITEM PHASe,C3,C2")
scope.write(":SINGLE")

scope.write(f":WAV:SEQuence 0,{0}")
scope.write(f":WAV:SOUR C1")

next_seq = 1
t_last_dump = time.time()

try:
    while True:
        # fast MEAS read (ASCII via read_line)
        #dt_s, ph_deg = meas_delay_phase(scope)
        #if dt_s is not None and ph_deg is not None:
        #    print(f"Δt={dt_s*1e3:6.3f} ms | phase={ph_deg:6.2f}°")

        # lazy LDR dump every ~1.2 s
        if time.time() - t_last_dump > 5:
            print('sta')
            #scope.write(":STOP")  # optional; more deterministic
            frames, next_seq, dt = seq_read_new_frames(scope, next_seq, "C1")
            if frames.size:
                print(f"LDR: {frames.shape[0]} frames, {frames.shape[1]} pts, dt={dt:.3e}s")
            t_last_dump = time.time()

            scope.write(":ACQ:SEQuence ON; :ACQ:SEQuence:COUNt 1000")
            scope.write(":TRIG:MODE NORM; :TRIG:EDGE:SOUR C3; :TRIG:EDGE:SLOP RIS")
            scope.write(":RUN")
            print('fin')

except KeyboardInterrupt:
    print ("stopping")
    scope.write(":STOP")
finally:
    scope.close()
    rm.close()