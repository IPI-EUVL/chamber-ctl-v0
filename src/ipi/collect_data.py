import signal
import pyvisa, time, serial
import csv
from tkinter import filedialog
from datetime import date
import re
import os
import struct
import math
import gc
import numpy as np

rm = pyvisa.ResourceManager()
scope_usb = "USB0::0xF4EC::0x100C::SDS2HBAX900425::INSTR"
scope_ip = "TCPIP0::10.11.13.220::5025::SOCKET"
scope = rm.open_resource(scope_usb)
scope.timeout = 10000
scope.write_termination = '\n'
scope.read_termination  = '\n'

tdiv_enum = [100e-12, 200e-12, 500e-12, 1e-9,
 2e-9, 5e-9, 10e-9, 20e-9, 50e-9, 100e-9, 200e-9, 500e-9, \
 1e-6, 2e-6, 5e-6, 10e-6, 20e-6, 50e-6, 100e-6, 200e-6, 500e-6, \
 1e-3, 2e-3, 5e-3, 10e-3, 20e-3, 50e-3, 100e-3, 200e-3, 500e-3, \
 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]

HORI_NUM = 10

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
    #scope.write(":ACQ:MDEP 10M")        # Match screen memory depth (10Mpts)  
    #scope.write(":TIMebase:SCALe 1e-6")       # 5ms per division
    #scope.write(":TIMebase:DELay 0")       # 5ms per division

    # Trigger settings
    #scope.write(":TRIG:MODE NORM")  
    #scope.write(":TRIG:TYPE EDGE")  
    #scope.write(":TRIGger:EDGE:SLOPe RIS")  
    #scope.write(":TRIGger:EDGE:LEVel 0.00")  
    #scope.write(":TRIGger:COUPling DC")  # DC coupling as shown on screen  
    #scope.write(":TRIGger:EDGE:SOUR C1")  # DC coupling as shown on screen  
    scope.write(f":ACQ:MDEP 10k")

    #scope.write(":MEASure ON")
    #scope.write(":MEASure:MODE ADVanced")
    #scope.write(":MEASure:ADVanced:STYle M2")
    #scope.write(":MEASure:ADVanced:LINenumber 12")
    #scope.write(":MEASure:ADVanced:P1 ON")
    #scope.write(":MEASure:ADVanced:P2 ON")
    #scope.write(":MEASure:ADVanced:P3 ON")

    #scope.write(":MEASure:ADVanced:P1:TYPE PHA")
    #scope.write(":MEASure:ADVanced:P2:TYPE SKEW")

    
    #scope.write(":MEASure:ADVanced:P1:SOURce1 C3")  # laser vs chopper
    #scope.write(":MEASure:ADVanced:P1:SOURce2 C2")

    #scope.write(":MEASure:ADVanced:P2:SOURce1 C3")  # laser vs chopper
    #scope.write(":MEASure:ADVanced:P2:SOURce2 C2")

    scope.write(":RUN")

def read_wf():
    global last_upd, take_wf, last_wf

    scope.chunk_size = 20 * 1024 * 1024
    #scope.write(":ACQ:MDEP 100M")        # Match screen memory depth (10Mpts)  

    scope.write(":WAVeform:STARt 0")
    scope.write("WAV:SOUR C1")
    scope.write(":WAVeform:INTerval 10")
    scope.write("WAV:PREamble?")

    a = scope.read_raw()
    while len(a) < 358:
        a += scope.read_raw()

    print("PRE len:", len(a))
    recv_all = a 
    recv = recv_all[recv_all.find(b'#') + 11:]
    vdiv, ofst, interval, trdl, tdiv, vcode_per, adc_bit = main_desc(recv)
    print(vdiv, ofst, interval, trdl, tdiv,vcode_per,adc_bit)
    points = scope.query(":ACQuire:POINts?").strip()
    points = float(scope.query(":ACQuire:POINts?").strip())
    one_piece_num = float(scope.query(":WAVeform:MAXPoint?").strip())
    if points > one_piece_num:
        scope.write(":WAVeform:POINt {}".format(one_piece_num))
    if adc_bit > 8:
        scope.write(":WAVeform:WIDTh WORD")
    read_times = math.ceil(points / one_piece_num)
    recv_all = []
    for i in range(0, read_times):
        start = i * one_piece_num
        scope.write(":WAVeform:STARt {}".format(start))
        scope.write("WAV:DATA?")
        recv_rtn = scope.read_raw().rstrip()
        print("RECV len:", len(recv_rtn))
        block_start = recv_rtn.find(b'#')
        data_digit = int(recv_rtn[block_start + 1:block_start + 2])
        data_start = block_start + 2 + data_digit
        recv = list(recv_rtn[data_start:])
        recv_all += recv
    convert_data = []
    if adc_bit > 8:
        for i in range(0, int(len(recv_all) / 2)):
            data = recv_all[2 * i + 1] * 256 + recv_all[2 * i]
            convert_data.append(data)
    else:
        convert_data = recv_all
    volt_value = []
    for data in convert_data:
        if data > pow(2, adc_bit - 1) - 1:
            data = data - pow(2, adc_bit)
        else:
            pass
        volt_value.append(data)

    del recv, recv_all, convert_data
    gc.collect()
    time_value = []
    for idx in range(0, len(volt_value)):
        volt_value[idx] = volt_value[idx] / vcode_per * float(vdiv) - float(ofst)
        time_data = - (float(tdiv) * HORI_NUM / 2) + idx * interval + float(trdl)
        time_value.append(time_data)

    for i in range(0, len(volt_value), 1000):
        print(f"{time_value[i]}: {volt_value[i]}")


    volts = np.array(volt_value)
    times = np.array(time_value)
    values = np.column_stack((times, volts))

    last_wf = time.time()
    #setup_meas()

    return values

today = date.today().strftime("%Y-%m-%d")

SAVE_PATH = os.path.join(os.environ["EUVL_PATH"], "datasets")

os.makedirs(SAVE_PATH, exist_ok=True)

pattern = re.compile(rf"{today}_S(\d+)_*")

existing_files = os.listdir(SAVE_PATH)
print(existing_files)
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

def read_loop():
    global stop_flag

    while not stop_flag:
        start = time.time()
        cur_time = 0
        data = np.empty((0, 2))

        num_pulses = 0
        try:
            while time.time() - start < 30.0 and not stop_flag:
                try:
                    pulse = read_wf()
                except Exception as e:
                    print(e)
                    scope.clear()
                    continue

                print(len(pulse))

                if len(pulse) == 0:
                    continue
                #print(pulse[-1, 0])
                
                c_t = cur_time

                print(pulse[0, 0])
                pulse[:, 0] -= pulse[0, 0]
                cur_time += pulse[-1, 0]
                print(pulse[0, 0])
                pulse[:, 0] += c_t
                print(pulse[0, 0])

                num_pulses += 1

                data = np.vstack((data, pulse))
        except:
            raise
        finally:
            if len(data) == 0:
                print("Collected NO samples!!")
                pass

            print(f"Saving #{len(data)} samples, with {num_pulses} pulses.")
            np.savetxt(f"{foldername}\\snapshot_{int(time.time())}.csv", data, delimiter=',', header="t,v", comments="")
       

def main():
    try:
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGABRT, handle_signal)
        signal.signal(signal.SIGBREAK, handle_signal)

        setup_meas()
        read_loop()

    finally:
        scope.close()

main()