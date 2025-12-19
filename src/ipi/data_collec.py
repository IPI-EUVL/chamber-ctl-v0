import pyvisa, time, serial
import csv

rm = pyvisa.ResourceManager()
scope_usb = "USB0::0xF4EC::0x100C::SDS2HBAX900425::INSTR"
scope_ip = "TCPIP0::10.11.13.220::5025::SOCKET"
scope = rm.open_resource(scope_usb)
scope.timeout = 1000
scope.write_termination = '\n'
scope.read_termination  = '\n'

PORT = "COM1"

TARGET_PHASE = 325
HYSTERESIS = 15

port = serial.Serial(PORT, 115200, 8, "N", 1)
#port.open()


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

#setup_meas()
#set_chopper(False)
#time.sleep(0.1)
#send_chopper_cmd(f"ref=0")
#time.sleep(0.1)
#set_chopper(True)

def serial_receive():
    while True:
        read = port.read_all()
        print(read)
        time.sleep(0.1)
last_tgt = 0

#def compensate(ph):
    #global last_tgt

    #tgt = last_tgt
    #if ph > (TARGET_PHASE + HYSTERESIS):
    #    tgt = 2501
    #elif ph < (TARGET_PHASE - HYSTERESIS):
    #    tgt = 2498
    #else:
    #    tgt = 2500

    #if tgt != last_tgt:
    #    last_tgt = tgt
    #    send_chopper_cmd(f"freq={tgt}")
    #    time.sleep(1)

def read_loop():
    out_file = open(f"./out_{time.time_ns()}.csv", "w", newline="")
    labels = ['t', 'vpp', 'filt', 'avg', 'amp', 'rms']
    log = csv.writer(out_file)
    log.writerow(labels)
    
    while True:
        # Try the “RESULT?” form first What does this mean
        vpp, filt, avg_vpp, amplitude, rms  = float('nan'), float('nan'), float('nan'), float('nan'), float('nan')
        try:
            #ph = float(scope.query(":MEASure:ADVanced:P1:VALue?"))
            #dt = float(scope.query(":MEASure:ADVanced:P2:VALue?"))
            vpp = float(scope.query(":MEASure:ADVanced:P3:VALue?"))
            filt = float(scope.query(":MEASure:ADVanced:P4:VALue?"))
            avg_vpp = float(scope.query(":MEASure:ADVanced:P5:VALue?"))
            amplitude = float(scope.query(":MEASure:ADVanced:P6:VALue?"))
            rms = float(scope.query(":MEASure:ADVanced:P7:VALue?"))

            #if ph > 360:
                #ph -= 360

            #if ph < 0:
                #ph += 360

        except ValueError:
            pass

        #if dt != float('nan'): print(f"Δt = {dt*1e3:.3f} ms", end='  ')
        #if ph != float('nan'): print(f"phase = {ph:6.2f}°", end=' ')
        if vpp != float('nan'): print(f"Vpp = {vpp:6.5f}°", end=' ')
        if filt != float('nan'): print(f"Filtered = {filt:6.5f}°", end=' ')
        if avg_vpp != float('nan'): print(f"Average = {avg_vpp:6.5f}°", end='\n')
        if amplitude != float('nan'): print(f"Amplitude = {amplitude:6.5f}°", end='\n')
        if rms != float('nan'): print(f"Root Mean Sq = {rms:6.5f}°", end='\n')

        to_log = [time.time(), vpp, filt, avg_vpp, amplitude, rms]
        print(to_log)
        log.writerow(to_log)

        #if ph is not None:
            #compensate(ph)
        print(f"thing:{scope.query(":MEASure:ADVanced:P1:VALue?")}")
        time.sleep(0.05)

def main():
    try:
        read_loop()
        
    finally:
        #set_chopper(False)
        time.sleep(0.1)
        port.close()

main()
