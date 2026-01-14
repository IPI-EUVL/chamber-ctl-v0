import os
import serial
import serial.tools.list_ports
import time
import tkinter as tk
from tkinter import ttk
import threading
from labjack import ljm
import threading
import numpy as np
import tkinter.messagebox as messagebox
import sys
import subprocess
import signal       

#Setup
ports = serial.tools.list_ports.comports()
available_ports = []
portnumber = 3
"""
    for port in self.ports:
    self.available_ports.append(port.device)
    for port in self.ports:
    number = int(port.device.replace("COM",""))
    if number > self.highest_number:
    self.highest_number = number"""
def serial_port_setup():
            ser_in = serial.Serial(port=f'COM{portnumber}', baudrate=9600, bytesize=7, parity='E', stopbits=1, timeout=1)
            ser_in.write(b"SV30000\r")
            ser_in.write(b"SF30000\r")
            ser_in.write(b"SJ10000\r")
            ser_in.write(b"SA50000\r")
            #status_updater(f"Successfully connected to {ser_in.portstr}")
            time.sleep(3)
            #status_updater("Ready")
            return ser_in

#Communication
def run_communicate(): 
    threading.Thread(target=communicate, daemon=True).start()

def communicate(command, ser_in = None):
            try:
                cmd = command + '\r'
                cd = cmd.encode()
                ser_in.write(cd)
                print(cd)
            except AttributeError:
                messagebox.showerror("Connection Error", "Linear actuator is not connected.")
                return False    


#Movement
def MOVE(speed, ser_in, datanodata):
    if datanodata == "data":
        threading.Thread(target=communicate, args=(f'1CV{float(speed)}', ser_in), daemon=True).start()
        data_collec = subprocess.Popen(["python", "C:\\Apps\\chamber-ctl\\src\\ipi\\collect_data_bulk.py"], stdin=subprocess.PIPE, text=True)
        return data_collec
    elif datanodata == "nodata":
        threading.Thread(target=communicate, args=(f'1CV{float(speed)}', ser_in), daemon=True).start()


def go_out(speed, ser_in):  
    threading.Thread(target=MOVE, args=(speed,ser_in, "nodata"), daemon=True).start()

#Stopping
def stop(data_collec, ser_in):
        try:
            #self.choppersync.send_signal(signal.SIGBREAK)
            #os.kill(self.choppersync.ch, signal.CTRL_C_EVENT)
            data_collec.stdin.write("q\r\n\n")
            time.sleep(0.1)
            data_collec.communicate('q\r\n', timeout=10)
            print("Child has exited gracefully.")
            time.sleep(0.1)
            os.kill(data_collec.pid, signal.SIGINT)
        except Exception as e:
            print(e)
            pass

        threading.Thread(target=stop_linmotion, args=(ser_in,), daemon=True).start()

def stop_linmotion(ser_in):
    threading.Thread(target=communicate, args=(f'1AB', ser_in), daemon=True).start()
    time.sleep(2)
    threading.Thread(target=communicate, args=(f'1RS', ser_in), daemon=True).start()
    time.sleep(0.5)





#move to absolute position
#serin = serial_port_setup()

#MOVE(-5000, serin, "nodata")

#stop_linmotion(serin)

#communicate('1CP0', serin)


#communicate('1MR4000', serin)
#cleardatum
#communicate('1CD', serin) #1

#communicate('1DM01110000', serin) #3

#sethome
#communicate("1SH200", serin) #2

#searchdatum
#communicate('1HD', serin) #4

#move to datum
#communicate('1MD', serin)

#communicate('1MH', serin)

#communicate('1SF10000', serin)

#creep speed
#communicate('1SC5000', serin)

#1MA4000

#1CP50000

