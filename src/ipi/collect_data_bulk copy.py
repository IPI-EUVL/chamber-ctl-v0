import time, struct, os, signal, re, sys, threading, numpy as np
from datetime import date
from pyvisa import ResourceManager, errors as visa_errors

HORI_NUM = 10.0

PULSE_RATE = 100
SAVE_RATE = 100
NUM_SKIP = PULSE_RATE / SAVE_RATE

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

def parse_seq_preamble(desc: bytes):
    """Parse only what we need for sequence waveform decode."""
    def u16(o): return struct.unpack("<H", desc[o:o+2])[0]
    def u32(o): return struct.unpack("<I", desc[o:o+4])[0]
    def f32(o): return struct.unpack("<f", desc[o:o+4])[0]
    def f64(o): return struct.unpack("<d", desc[o:o+8])[0]

    width       = u16(0x20)      # 0=BYTE, 1=WORD
    order       = u16(0x22)      # 0=LSB, 1=MSB
    read_pts    = u32(0x74)      # points per frame (this transfer)
    read_frame  = u32(0x90)      # frames in this transfer
    sum_frame   = u32(0x94)      # total acquired frames

    v_scale     = f32(0x9C)      # V/div pre-probe
    v_offset    = f32(0xA0)      # V offset pre-probe
    code_raw    = f32(0xA4)      # codes/div for 16-bit container
    adc_bits_c  = u16(0xAC)      # container bits (16 on HD)

    interval    = f32(0xB0)      # base dt (s/sample)
    delay       = f64(0xB4)      # horiz position
    tdiv_index  = u16(0x144)
    probe       = f32(0x148)

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


wav_int = 1
def decode_sequence_waveforms(desc: bytes, datablock: bytes, wav_int: int = 1):
    """
    Given one WAVEDESC (desc) and one DATA? payload (data)
    from SDS2000X HD in sequence mode, return:
        t: (n_pts,) time axis [s]
        V: (n_frames, n_pts) voltages [V]
        meta: dict of preamble fields
    """
    m = parse_seq_preamble(desc)

    width      = m["width"]
    order      = m["order"]
    read_pts   = m["read_pts"]
    read_frame = m["read_frame"]
    vdiv       = m["vdiv"]
    voff       = m["voff"]
    code_raw   = m["code_raw"]
    interval   = m["interval"]
    delay      = m["delay"]
    tdiv       = m["tdiv"]

    # Export decimation
    N = int(wav_int) if wav_int and wav_int > 0 else 1
    eff_dt = interval * N

    # ---- bytes/sample ----
    if width == 0:
        bps = 1
    else:
        bps = 2

    # ---- sanity: expected byte length ----
    expected_samples = read_pts * read_frame
    expected_bytes = expected_samples * bps
    if len(datablock) != expected_bytes:
        # If this trips: preamble / read_pts / read_frame mismatch.
        # That will absolutely cause cloned frames.
        raise ValueError(
            f"Length mismatch: got {len(datablock)} bytes, "
            f"expected {expected_bytes} for {read_frame}x{read_pts}"
        )

    # ---- raw → unsigned codes ----
    if width == 0:
        # BYTE export: top 8 bits of 16-bit container (HD quirk)
        adc_bits = 8
        raw = np.frombuffer(datablock, dtype=np.uint8)
        code_per_div = code_raw / (1 << (16 - adc_bits))   # 7680/256 = 30
        center = (1 << (adc_bits - 1)) - 1                 # 127
        full   = 1 << adc_bits                             # 256
    else:
        # WORD export: 16-bit container, 12-bit effective for SDS2000X HD
        adc_bits = 12
        if order == 1:
            raw16 = np.frombuffer(datablock, dtype=">u2")
        else:
            raw16 = np.frombuffer(datablock, dtype="<u2")
        raw = raw16 >> (16 - adc_bits)                     # 16 → 12 bits
        code_per_div = code_raw / (1 << (16 - adc_bits))   # 7680/16 = 480
        center = (1 << (adc_bits - 1)) - 1                 # 2047
        full   = 1 << adc_bits                             # 4096

    # ---- reshape strictly by (read_frame, read_pts) ----
    codes_u = raw.reshape(read_frame, read_pts)

    # ---- unsigned → signed ----
    codes = codes_u.astype(np.int32)
    mask = codes > center
    codes[mask] -= full

    # ---- to volts ----
    # V = code * (vdiv / code_per_div) - voff
    V = codes.astype(np.float64) * (vdiv / code_per_div) - voff

    # ---- time axis ----
    idx = np.arange(read_pts, dtype=np.float64)
    if tdiv is not None:
        # Siglent's own formula
        t0 = -delay - (tdiv * HORI_NUM / 2.0)
    else:
        t0 = -delay
    t = t0 + idx * eff_dt

    meta = dict(m)
    meta.update({
        "adc_bits": adc_bits,
        "code_per_div_eff": code_per_div,
        "dt_eff": eff_dt,
    })
    return t, V, meta

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
#scope.write(":STOP")
scope.write(":WAV:INT 0")
#scope.write(":WAVeform:WIDTh BYTE")
#scope.write(":WAV:WIDT BYTE; :WAV:FORM BYTE")
#scope.write(":WAVeform:INTerval 0")
#scope.write(":ACQ:TYPE NORM")
#scope.write(":ACQ:MMAN FSRate")          # fixed sample rate
#scope.write(":ACQ:SRAT 2.0E9")           # 10 kS/s
##scope.write(":TIMEBASE:SCAL 0.002; :TIMEBASE:POS 0")  # 2 ms/div
#scope.write(":CHAN1:DISP ON; :WAV:SOUR C1")
scope.write(":HISTory ON")              # avoid History interfering with seq
#scope.write(":RUN")
#scope.write(":MEAS:CLE; :MEAS:ITEM DELay,C3,C2; :MEAS:ITEM PHASe,C3,C2")
# (If you run a fast MEAS loop normally, pause it during the burst capture below.)

def capture_burst_and_read(N=200):
    # Arm segmented capture: exactly N segments, then stop
    scope.write(":ACQ:SEQuence ON")
    scope.write(f":ACQ:SEQuence:COUNt {N}")
    scope.write(":TRIGger:MODE SINGle")
    scope.write(":TRIGger:RUN")
    # Wait until stopped (acq done). Poll a light ASCII that changes on stop:

    while True:
        scope.write(":TRIG:STAT?")
        st = read_line(scope)  # e.g., "STOP"
        if "STOP" in st.upper(): break
        time.sleep(0.02)
    print("Done! Calculating...\t\t\t.", end='\r')

    st = time.time()

    # Freeze a consistent snapshot is already ensured (we're stopped)
    scope.write(f":WAVeform:SEQuence 0,{N-1}")         # or 0,<next_start> in your loop
    scope.write(":WAVeform:SOURce C1")
    scope.write(":WAVeform:PREamble?")
    desc = read_hash_block(scope)                 # returns WAVEDESC payload

    scope.write(":WAVeform:DATA?")
    data = read_hash_block(scope)                 # returns concatenated frame data

    # 3) Decode to time + voltages
    t, V, meta = decode_sequence_waveforms(desc, data)

    et = time.time()
    print(f"Captured {len(V)} frames in {et- st} seconds. This results in a capture % of: {(N / PULSE_RATE) / ((N / PULSE_RATE) + et - st)}. Recording...", end='\r')
    return t, V, meta

# Example loop: burst every ~1.5 s
today = date.today().strftime("%Y-%m-%d")

SAVE_PATH = os.path.join(os.environ["EUVL_PATH"], "datasets")

os.makedirs(SAVE_PATH, exist_ok=True)

pattern = re.compile(rf"{today}_S(\d+)_*")

existing_files = os.listdir(SAVE_PATH)
sequence_numbers = [
        int(match.group(1))
        for filename in existing_files
        if (match := pattern.match(filename))
            ]

next_seq = max(sequence_numbers, default=0) + 1

foldername = os.path.join(SAVE_PATH, f"{today}_S{next_seq}")
filename = os.path.join(foldername, f"vals.csv")
os.makedirs(foldername, exist_ok=True)

stop_flag = False

def handle_signal(sig, frame):
    global stop_flag
    print("RECEIVED INTERRUPT!!")
    stop_flag = True

def stop_thread():
    global stop_flag
    
    try:
        while True:
            i = input()
            print("Received ", i)
            if i == 'q':
                break
    finally:
        stop_flag = True

#scope.write(":CHAN1:DISP ON")
#scope.write(":WAV:INT 1")
#scope.write(":WAV:WIDT WORD")
#scope.write(":WAV:SOUR C1")
#scope.write(":WAV:STAR 0")
#scope.write(":WAV:POIN 0")
scope.write(":HISTory ON")
#scope.write(":WAV:MODE RAW")

# segmented single run
#scope.write(":ACQ:SEQuence ON")
#scope.write(":ACQ:SEQuence:COUNt 10")
scope.write(":TRIG:MODE SINGle")
scope.write(":TRIG:RUN")

# wait for STOP
while True:
    scope.write(":TRIG:STAT?")
    st = read_line(scope).upper()
    if "STOP" in st:
        break

# now read those 10 segments
scope.write(":WAV:SEQuence 0,0")
scope.write(":WAV:PRE?")
desc = read_hash_block(scope)
scope.write(":WAV:DATA?")
dat = read_hash_block(scope)

t, V, meta = decode_sequence_waveforms(desc, dat, wav_int=1)

print(V[0])
print("frames", meta["read_frame"], "pts", meta["read_pts"])
for i in range(meta["read_frame"] - 1):
    print(i, "==", i+1, np.allclose(V[i], V[i+1]))

scope.write(":WAV:SEQuence 1,0")
scope.write(":WAV:PRE?")
desc = read_hash_block(scope)
scope.write(":WAV:DATA?")
dat = read_hash_block(scope)

t, V, meta = decode_sequence_waveforms(desc, dat, wav_int=1)

print(V[0])
print("frames", meta["read_frame"], "pts", meta["read_pts"])
for i in range(meta["read_frame"] - 1):
    print(i, "==", i+1, np.allclose(V[i], V[i+1]))

scope.write(":WAV:SEQuence 2,0")
scope.write(":WAV:PRE?")
desc = read_hash_block(scope)
scope.write(":WAV:DATA?")
dat = read_hash_block(scope)

t, V, meta = decode_sequence_waveforms(desc, dat, wav_int=1)

print(V[0])
print("frames", meta["read_frame"], "pts", meta["read_pts"])
for i in range(meta["read_frame"] - 1):
    print(i, "==", i+1, np.allclose(V[i], V[i+1]))

exit()

def read_loop():
    global stop_flag

    print("Wait for trigger...", end='\t\t\t\r')
    while not stop_flag:
        start = time.time()
        cur_time = 0
        data = np.empty((0, 2))

        num_pulses = 0
        try:
            while time.time() - start < 30.0 and not stop_flag:
                try:
                    t, V, meta = capture_burst_and_read(100)

                    print("read_frame =", meta["read_frame"])
                    print("read_pts   =", meta["read_pts"])
                    print("V shape    =", V.shape)
                    print("t[0], t[-1]", t[0], t[-1])

                    # Check if frames are genuinely identical in the raw decode:
                    same = []
                    for i in range(min(5, meta["read_frame"] - 1)):
                        same.append(np.array_equal(V[i], V[i+1]))
                    print("first few frame equality flags:", same)

                except Exception as e:
                    print(e)
                    scope.clear()
                    continue

                print(V[0])
                print(V[1])
                print(V[10])

                #print(len(V))

                if len(V) == 0:
                    continue
                #print(pulse[-1, 0])
                
                #print(t, V, meta)

                for nv in range(0, len(V), int(NUM_SKIP)):
                    mytime = np.copy(t)
                    end_time = mytime[-1]
                    mytime += cur_time
                    cur_time += end_time

                    #print( V[nv])
                    #print(len(V[nv]))
                    #print(" THE T", t)
                    #print("MYTIME: ", mytime)
                    values = np.column_stack((mytime, V[nv]))
                    #print("DARATA:", data)

                    data = np.vstack((data, values))

                    num_pulses += 1

            print()
        except:
            raise
        finally:
            if len(data) == 0:
                print("Collected NO samples!!")
                pass

            
            res_filename = f"{foldername}\\snapshot_{int(time.time())}.csv"
            print(f"Saving #{len(data)} samples, with {num_pulses} pulses.")
            np.savetxt(res_filename, data, delimiter=',', header="t,v", comments="")
            print(f"Saved to {res_filename}")

            exit()
       

def main():
    try:
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGABRT, handle_signal)
        signal.signal(signal.SIGBREAK, handle_signal)

        threading.Thread(target=stop_thread, daemon=True).start()

        read_loop()

    finally:
        scope.write(":ACQ:SEQuence OFF")
        scope.close()

main()