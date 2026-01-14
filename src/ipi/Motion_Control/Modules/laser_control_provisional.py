<<<<<<< HEAD
import time
import tkinter as tk
import pyvisa

class LASER:
    def __init__ (self):
        self.waveform = pyvisa.ResourceManager().open_resource('USB0::0x0957::0x1507::MY48009073::INSTR')
        self.phi = 260

    def setup(self):
        self.command("TRIGger:SOURce EXTernal") #for chopper trigger
        self.command("UNIT:ANGLe DEGree")
        self.command("PHASe 0")
        self.phase(self.phi)

    def command(self, command_str):
        self.waveform.write(command_str)

    def ON(self):
        self.command("OUTPut ON")    

    def OFF(self):
        self.command("OUTPut OFF")  

    def phase(self, phi):
        self.command(f"BURSt:PHASe {phi}")

    def powerup(self):
        self.ON()
        target = 273 #deg
        curr = self.phi #deg
        dif = abs(curr-target)
        poweruptime = 15 #seconds it takes the laser to achieve full power
        delta = dif/(poweruptime*10)
        for i in range(poweruptime*10):
            curr += delta
            self.phase(curr)
            print(curr)
            time.sleep(0.1)

#laser.OFF()

#root = tk.Tk()
#ONbutt = tk.Button(root, text = "ON", command = LASER_ON)
#OFFbutt = tk.Button(root, text = "OFF", command = LASER_OFF)
#phi = tk.DoubleVar()
#slider = tk.Scale(root, from_ = 100, to = 300, bigincrement = 1, variable = phi, command = lambda e: phase(phi.get()), orient = tk.HORIZONTAL)

#ONbutt.grid(column = 0, row = 0)
#OFFbutt.grid(column = 1, row = 0, padx = 50)
#slider.grid(column = 0, row = 1, columnspan = 3)

#root.grid_rowconfigure(0, weight = 1)
#root.grid_columnconfigure(0, weight = 1)

#root.geometry("300x300")
#root.resizable(False, False)

#root.mainloop()

=======
import serial
import time
import threading 
import pyvisa

waveform = pyvisa.ResourceManager().open_resource('USB0::0x0957::0x1507::MY48009073::INSTR')

def command(command_str):
    waveform.write(command_str)
>>>>>>> 13c4082e4d72a76be7d0f0abd03d5120e38fe2b8

#LASER ON: command("OUTPut ON")
#LASER OFF: command("OUTPut OFF")
