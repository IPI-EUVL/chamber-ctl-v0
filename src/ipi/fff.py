import numpy as np
import pyvisa
import time
GRID = 10.0

def read_hash_block(inst):
    # Read standard IEEE488.2 definite-length block: #<d><len...><data>
    # Ignores any ASCII prefix like "C1:WF DAT2,"
    raw = inst.read_raw()
    # Find '#'
    i = raw.find(b'#')
    if i < 0:
        raise IOError(f"No block header: {raw[:40]!r}")
    if i + 2 > len(raw):
        raise IOError("Truncated block header")
    ndig = raw[i+1] - 48  # '0'
    if ndig < 1 or ndig > 9:
        raise IOError(f"Bad block ndig={ndig}")
    if i + 2 + ndig > len(raw):
        raise IOError("Truncated length digits")
    length = int(raw[i+2:i+2+ndig])
    start = i + 2 + ndig
    end = start + length
    if end > len(raw):
        raise IOError("Truncated block data")
    return raw[start:end]  # payload only

def parse_seq_preamble(desc: bytes):
    import struct

    def u16(o): return struct.unpack("<H", desc[o:o+2])[0]
    def u32(o): return struct.unpack("<I", desc[o:o+4])[0]
    def f32(o): return struct.unpack("<f", desc[o:o+4])[0]
    def f64(o): return struct.unpack("<d", desc[o:o+8])[0]

    width       = u16(0x20)      # 0=BYTE,1=WORD
    order       = u16(0x22)      # 0=LSB,1=MSB
    read_pts    = u32(0x74)      # pts of *single frame*
    read_frame  = u32(0x90)      # frames returned by this command
    sum_frame   = u32(0x94)      # total frames acquired

    v_scale     = f32(0x9C)
    v_offset    = f32(0xA0)
    code_raw    = f32(0xA4)
    adc_bits_c  = u16(0xAC)
    interval    = f32(0xB0)
    delay       = f64(0xB4)
    tdiv_index  = u16(0x144)
    probe       = f32(0x148)

    TDIV_ENUM = [
        100e-12, 200e-12, 500e-12,
        1e-9, 2e-9, 5e-9, 10e-9, 20e-9, 50e-9,
        100e-9, 200e-9, 500e-9,
        1e-6, 2e-6, 5e-6, 10e-6, 20e-6, 50e-6,
        100e-6, 200e-6, 500e-6,
        1e-3, 2e-3, 5e-3, 10e-3, 20e-3, 50e-3,
        100e-3, 200e-3, 500e-3,
        1, 2, 5, 10, 20, 50, 100, 200, 500, 1000,
    ]
    tdiv = TDIV_ENUM[tdiv_index] if 0 <= tdiv_index < len(TDIV_ENUM) else None

    vdiv = v_scale * probe
    voff = v_offset * probe

    return {
        "width": width,
        "order": order,
        "read_pts": read_pts,
        "read_frame": read_frame,
        "sum_frame": sum_frame,
        "vdiv": vdiv,
        "voff": voff,
        "code_raw": code_raw,
        "adc_bits_c": adc_bits_c,
        "interval": interval,
        "delay": delay,
        "tdiv": tdiv,
    }

def decode_one(desc: bytes, datablock: bytes):
    import numpy as np

    m = parse_seq_preamble(desc)
    width      = m["width"]
    order      = m["order"]
    pts        = m["read_pts"]
    vdiv       = m["vdiv"]
    voff       = m["voff"]
    code_raw   = m["code_raw"]
    interval   = m["interval"]
    delay      = m["delay"]
    tdiv       = m["tdiv"]

    # one frame only
    bps = 1 if width == 0 else 2
    expected = pts * bps
    if len(datablock) != expected:
        raise ValueError(f"len(datablock)={len(datablock)} expected={expected}")

    # BYTE vs WORD handling (SDS2000X HD: 12-bit ADC in 16-bit container)
    if width == 0:
        adc_bits = 8
        raw = np.frombuffer(datablock, dtype=np.uint8)
        code_per_div = code_raw / (1 << (16 - adc_bits))
        center = (1 << (adc_bits - 1)) - 1
        full = 1 << adc_bits
    else:
        adc_bits = 12
        dt = ">u2" if order == 1 else "<u2"
        raw16 = np.frombuffer(datablock, dtype=dt)
        raw = raw16 >> (16 - adc_bits)
        code_per_div = code_raw / (1 << (16 - adc_bits))
        center = (1 << (adc_bits - 1)) - 1
        full = 1 << adc_bits

    codes = raw.astype(np.int32)
    mask = codes > center
    codes[mask] -= full

    V = codes.astype(np.float64) * (vdiv / code_per_div) - voff

    idx = np.arange(pts, dtype=np.float64)
    if tdiv is not None:
        t0 = -delay - (tdiv * GRID / 2.0)
    else:
        t0 = -delay
    t = t0 + idx * interval

    return t, V, m

def get_frame(scope, frame_num):
    # Assumes: acquisition in sequence mode is complete,
    #          history enabled if required by your FW.
    scope.write(f":WAV:SEQuence {frame_num},0")  # single frame
    scope.write(":WAV:PRE?")
    desc = read_hash_block(scope)
    scope.write(":WAV:DATA?")
    datablock = read_hash_block(scope)
    return decode_one(desc, datablock)

rm = pyvisa.ResourceManager()
scope = rm.open_resource("TCPIP0::10.11.13.220::5025::SOCKET")  # or USB0::...::INSTR
scope.write_termination = '\n'
scope.read_termination  = None
scope.timeout = 10000
scope.write(":STOP")
scope.write(":CHAN1:DISP ON")
scope.write(":WAV:SOUR C1")
scope.write(":WAV:WIDT WORD")
scope.write(":WAV:INT 1")
scope.write(":WAV:STARt 0")
scope.write(":WAV:POINt 0")
scope.write(":ACQ:TYPE NORMal")
scope.write(":HISTory OFF")            # we'll turn it on after capture

# Enable segmented acquisition
scope.write(":ACQ:SEQuence ON")
scope.write(":ACQ:SEQuence:COUNt 10")  # 10 segments for test

# Arm single segmented run
scope.write(":TRIG:MODE SINGle")
scope.write(":TRIG:RUN")

# Wait until done
while True:
    scope.write(":TRIG:STATus?")
    st = scope.read().strip().upper()
    if "STOP" in st:
        break

# Now expose segments as history
scope.write(":HISTory ON")

# How many frames did we actually get?
scope.write(":HISTory:FRAMe?")
last_frame = int(scope.read().strip())
print("last_frame", last_frame)