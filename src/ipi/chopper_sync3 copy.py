import pyvisa, time, serial
import csv
from tkinter import filedialog
from datetime import date
import re
import os
import struct
import math
import gc

rm = pyvisa.ResourceManager()
scope_usb = "USB0::0xF4EC::0x100C::SDS2HBAX900425::INSTR"
scope_ip = "TCPIP0::10.11.13.220::5025::SOCKET"
scope = rm.open_resource(scope_usb)
scope.timeout = 1000
scope.write_termination = '\n'
scope.read_termination  = '\n'

tdiv_enum = [100e-12, 200e-12, 500e-12, 1e-9,
 2e-9, 5e-9, 10e-9, 20e-9, 50e-9, 100e-9, 200e-9, 500e-9, \
 1e-6, 2e-6, 5e-6, 10e-6, 20e-6, 50e-6, 100e-6, 200e-6, 500e-6, \
 1e-3, 2e-3, 5e-3, 10e-3, 20e-3, 50e-3, 100e-3, 200e-3, 500e-3, \
 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]


PORT = "COM4"

TARGET_PHASE = 325
HYSTERESIS = 15
MAX_WF_TIME = 30.0

port = serial.Serial(PORT, 115200, 8, "N", 1)
#port.open()

def main_desc(recv):
    WAVE_ARRAY_1 = recv[0x3c:0x3f + 1]
    wave_array_count = recv[0x74:0x77 + 1]
    first_point = recv[0x84:0x87 + 1]
    sp = recv[0x88:0x8b + 1]
    v_scale = recv[0x9c:0x9f + 1]
    v_offset = recv[0xa0:0xa3 + 1]
    interval = recv[0xb0:0xb3 + 1]
    code_per_div = recv[0xa4:0Xa7 + 1]
    adc_bit = recv[0xac:0Xad + 1]
    delay = recv[0xb4:0xbb + 1]
    tdiv = recv[0x144:0x145 + 1]
    probe = recv[0x148:0x14b + 1]
    data_bytes = struct.unpack('i', WAVE_ARRAY_1)[0]
    point_num = struct.unpack('i', wave_array_count)[0]
    fp = struct.unpack('i', first_point)[0]
    sp = struct.unpack('i', sp)[0]
    interval = struct.unpack('f', interval)[0]
    delay = struct.unpack('d', delay)[0]
    tdiv_index = struct.unpack('h', tdiv)[0]
    probe = struct.unpack('f', probe)[0]
    vdiv = struct.unpack('f', v_scale)[0] * probe
    offset = struct.unpack('f', v_offset)[0] * probe
    code = struct.unpack('f', code_per_div)[0]
    adc_bit = struct.unpack('h', adc_bit)[0]
    tdiv = tdiv_enum[tdiv_index]
    return vdiv, offset, interval, delay, tdiv, code, adc_bit


# clear any old measurements and add the two we need
# (Siglent firmwares vary; try A, then B if A raises an error)
def setup_meas():
    # one-time setup
    #scope.write(":CHAN1:DISP ON; :CHAN2:DISP ON; :CHAN3:DISP ON")
    #scope.write(":TRIG:MODE NORM; :TRIG:EDGE:SOUR C3; :TRIG:EDGE:SLOP RIS")

    scope.write(f":CHAN{1}:VIS ON")  # Enable selected channel
    scope.write(f":CHAN{2}:VIS ON")  # Enable selected channel
    scope.write(f":CHAN{3}:VIS ON")  # Enable selected channel

    scope.write(":ACQ:MODE RT")         # Real-time acquisition
    scope.write(":ACQ:SRAT 200E6")      # 200 MSa/s Sampling Rate
    scope.write(":ACQ:MDEP 10M")        # Match screen memory depth (10Mpts)  
    scope.write(":TIMebase:SCALe 5e-3")       # 5ms per division
    scope.write(":TIMebase:DELay 8e-3")       # 5ms per division

    # Trigger settings
    scope.write(":TRIG:MODE NORM")  
    scope.write(":TRIG:TYPE EDGE")  
    scope.write(":TRIGger:EDGE:SLOPe RIS")  
    scope.write(":TRIGger:EDGE:LEVel 3.00")  
    scope.write(":TRIGger:COUPling DC")  # DC coupling as shown on screen  
    scope.write(":TRIGger:EDGE:SOUR C3")  # DC coupling as shown on screen  
    scope.write(f":ACQ:MDEP 10k")

    scope.write(":MEASure ON")
    scope.write(":MEASure:MODE ADVanced")
    scope.write(":MEASure:ADVanced:STYle M2")
    scope.write(":MEASure:ADVanced:LINenumber 12")
    scope.write(":MEASure:ADVanced:P1 ON")
    scope.write(":MEASure:ADVanced:P2 ON")
    scope.write(":MEASure:ADVanced:P3 ON")

    scope.write(":MEASure:ADVanced:P1:TYPE PHA")
    scope.write(":MEASure:ADVanced:P2:TYPE SKEW")

    
    scope.write(":MEASure:ADVanced:P1:SOURce1 C3")  # laser vs chopper
    scope.write(":MEASure:ADVanced:P1:SOURce2 C2")

    scope.write(":MEASure:ADVanced:P2:SOURce1 C3")  # laser vs chopper
    scope.write(":MEASure:ADVanced:P2:SOURce2 C2")

    scope.write(":RUN")


def send_chopper_cmd(cmd):
    print(f"{cmd}\r".encode("utf-8"))
    port.write(f"{cmd}\r".encode("utf-8"))

def set_chopper(state):
    send_chopper_cmd(f"enable={1 if state else 0}")

setup_meas()
set_chopper(False)
time.sleep(0.1)
send_chopper_cmd(f"ref=0")
time.sleep(0.1)
set_chopper(False)

def serial_receive():
    while True:
        read = port.read_all()
        print(read)
        time.sleep(0.1)

last_tgt = 0
last_upd = time.time()

def compensate(ph):
    global last_tgt, last_upd

    if time.time() - last_upd < 1.0:
        return

    tgt = last_tgt
    if ph > (TARGET_PHASE + HYSTERESIS):
        tgt = 2501
    elif ph < (TARGET_PHASE - HYSTERESIS):
        tgt = 2498
    else:
        tgt = 2500

    if tgt != last_tgt:
        last_tgt = tgt
        send_chopper_cmd(f"freq={tgt}")
        print("Update chopper")
        last_upd = time.time()

take_wf = False
last_wf = time.time()

def read_wf():
    global last_upd, take_wf, last_wf

    scope.write(":WAV:MODE RAW")  # Raw waveform mode
    scope.write(":WAV:FORMAT WORD")  # 16-bit resolution
    scope.write(":WAV:DATA:BYTEORDER LSBFirst")  
    scope.write(":WAV:POIN:MODE NORMAL")  # Continuous waveform transfer mode
    scope.write(":WAV:POIN 1000000")
    scope.write(":WAV:SOURce 1")
    scope.write(":WAVeform:INTerval 10")

    print(scope.write("WAV:PREamble?"))
    time.sleep(0.5)
    a = bytes(scope.read_raw())
    b = bytes(scope.read_raw())

    preamble = a + b

    vdiv, ofst, interval, trdl, tdiv, vcode_per, adc_bit = main_desc(preamble)
    print(vdiv, ofst, interval, trdl, tdiv,vcode_per,adc_bit)

    scope.write(":WAV:DATA?")
    time.sleep(0.1)
    raw_data = bytes(scope.read_raw())
    print(raw_data)
    print(f"Got DATA: {len(raw_data)}")

    print(raw_data[0])
    print(raw_data[10])
    print(raw_data[20])
    print(raw_data[100])
    print(raw_data[500])
    print(raw_data[1000])


    block_start = raw_data.find(b'#') + 1

    nd = int(raw_data[block_start:block_start + 1].decode())
    n = int(raw_data[block_start + 1:block_start + nd + 1].decode())

    print(f"NUM BYTES: {nd}")
    print(f"NUM BYTES: {n}")

    data = raw_data[block_start + nd + 1:block_start + nd + 1 + n]

    print(f"GOT DATA WITH {len(data)} POINTS: {data}")

    last_wf = time.time()

def upd_wf():
    global last_upd, take_wf, last_wf

    if time.time() - last_upd < 1:
        if not take_wf:
            read_wf()
            take_wf = True
    else:
        take_wf = False

    if  time.time() - last_wf > MAX_WF_TIME:
        read_wf()

def read_meaus(path):
    try:
        return float(scope.query(path))
    except ValueError:
        return float('nan')

def select_file():
    global file_paths1
    file_paths1 = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
        title="Save  Oscilloscope Data As"
    )
    return file_paths1

#select_file()

today = date.today().strftime("%Y-%m-%d")

folder_path2 = "C:\\Apps\\chamber-ctl\\src\\ipi\\data\\Oscilloscope_Data"

os.makedirs(folder_path2, exist_ok=True)

pattern = re.compile(rf"{today}_S(\d+)_\.csv")

existing_files = os.listdir(folder_path2)
sequence_numbers = [
        int(match.group(1))
        for filename in existing_files
        if (match := pattern.match(filename))
            ]


next_seq = max(sequence_numbers, default=0) + 1

filename = f"C:\\Apps\\chamber-ctl\\src\\ipi\\data\\Oscilloscope_Data\\{today}_S{next_seq}_.csv" 

def read_loop():
    out_file = open(filename, "w", newline="")
    #out_file = open(f"{file_paths1}","w",newline="")
    labels = ['t (s)', 'skew', 'phase', 'vpp', 'filt', 'avg', 'amp', 'rms']
    log = csv.writer(out_file)
    log.writerow(labels)

    start = time.time()
    while True:
        now = time.time()
        dtt = now-start

        # Try the “RESULT?” form first What does this mean
        dt, ph, vpp, filt, avg_vpp, amplitude, rms  = float('nan'), float('nan'), float('nan'), float('nan'), float('nan'), float('nan'), float('nan')
        ph = read_meaus(":MEASure:ADVanced:P1:VALue?")
        dt = read_meaus(":MEASure:ADVanced:P2:VALue?")
        vpp = read_meaus(":MEASure:ADVanced:P3:VALue?")
        filt = read_meaus(":MEASure:ADVanced:P4:VALue?")
        avg_vpp = read_meaus(":MEASure:ADVanced:P5:VALue?")
        amplitude = read_meaus(":MEASure:ADVanced:P6:VALue?")
        rms = read_meaus(":MEASure:ADVanced:P7:VALue?")

        if ph > 360:
                ph -= 360

        if ph < 0:
            ph += 360

        upd_wf()

        if dt != float('nan'): print(f"Δt = {dt:.3f} ms", end='  ')
        if ph != float('nan'): print(f"phase = {ph:6.2f}°", end=' ')
        if vpp != float('nan'): print(f"Vpp = {vpp:6.5f}°", end=' ')
        if filt != float('nan'): print(f"Filtered = {filt:6.5f}°", end=' ')
        if avg_vpp != float('nan'): print(f"Average = {avg_vpp:6.5f}°", end='\n')
        if amplitude != float('nan'): print(f"Amplitude = {amplitude:6.5f}°", end='\n')
        if rms != float('nan'): print(f"Root Mean Sq = {rms:6.5f}°", end='\n')

        to_log = [dtt, dt*1e3, ph, vpp, filt, avg_vpp, amplitude, rms]
        print(to_log)
        log.writerow(to_log)

        if ph is not None:
            compensate(ph)

        read = port.read_all()
        print(read)
        #time.sleep(0.05)

def main():
    try:
        read_loop()
        
    finally:
        set_chopper(False)
        time.sleep(0.1)
        scope.close()
        port.close()


main()