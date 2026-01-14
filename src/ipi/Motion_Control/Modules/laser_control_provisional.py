import serial
import time
import threading 
import pyvisa

waveform = pyvisa.ResourceManager().open_resource('USB0::0x0957::0x1507::MY48009073::INSTR')

def command(command_str):
    waveform.write(command_str)

#LASER ON: command("OUTPut ON")
#LASER OFF: command("OUTPut OFF")
