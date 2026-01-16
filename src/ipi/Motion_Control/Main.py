#/////////////////////////////////////IMPORTS/////////////////////////////////////////////////////////////////////////////////////
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
from Modules import Animation as anim
from Modules import Linear_Motion as lin
from Modules import Rotational_Motion2
from Modules import laser_control_provisional as laserctrl

#import Data_Collection_V5
#/////////////////////////////////////IMPORTS/////////////////////////////////////////////////////////////////////////////////////


# Get path to the folder where the script/exe is running
#if getattr(sys, 'frozen', False):
#    base_path = os.path.dirname(sys.executable)  # If running from PyInstaller bundle
#else:
#    base_path = os.path.dirname(os.path.abspath(__file__))

log_path = os.path.join("./", "Log.txt")

print(f"Writing to log file: {log_path}")

#data_collection_path = os.path.join(, "Data_Collection_V5.py")



#/////////////////////////////////////NOTES///////////////////////////////////////////////////////////////////////////////////////////

#====== Linear Actuator Configuration ===== 
#Linear Actuator's error was due to a Tracking Error (4th pin). Abort condition was disabled in order for the machine to ignore it. 
#<A tracking error occurs when the difference between the command position and the actual position exceeds a limit for more than a defined time.>
#communicate('1AM00010100') disables the conflicting abort condition (already implemented in the machine)
#==========================================

# ===== Stepper Motor Configuration =====
# PUL+       → LabJack FIO4
# PUL−       → LabJack GND
# DIR+       → LabJack FIO6
# DIR−       → LabJack FIO7
# DIP switch configuration:
#   SW1 OFF, SW2 OFF, SW3 ON, others configured for 3200 steps/rev (1/16 microstepping)
# Speed (RPM) controlled by the delay between pulses on FIO4
# Direction set by writing HIGH/LOW to DIR+ and DIR− respectively
# Verified with StepperOnline 23HS45-4204S (4.2A, 3N·m) and DM556T driver
# =======================================

#//////////////////////////////////////////////////////////GUI////////////////////////////////////////////////////////////////////////////////////////
class TargetMotionControlGUI(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.root = master
        #LabJack setup
        #Parameters
        self.steps_per_rev = 200
        self.handle = None 
        self.microsteps = 16 #If the number of microsteps is changed, the DIP switches on the drivers must be set according to datasheet
        self.rpm_to_delay = 60/(self.steps_per_rev*self.microsteps)
        self.running = False
        self.straight_up_rotating_it_and_by_it_I_mean_my_linear_acuator = False
        self.open_gui = True
        self.ser_in = None
        self.ser_connected = False
        self.directional = "cw"
        self.is_in_or_out = "in"
        self.selected_speed = 130 #change to 300 maybe ?(previous speed 500)
        self.rpmset = 1
        self.speed = self.selected_speed
        self.targt_len = 63.5#mm

        #GUI setup
        try:
            self.lin_widgets()

            self.animation_widgets()

            self.ser_in = lin.serial_port_setup()

            self.status_updater(self.status_lbl,"Connected")

            self.laser = laserctrl.LASER()

            self.laser.setup()

            self.rot = Rotational_Motion2.Rotate()
        except serial.SerialException as e:
            message = f"Failed to connect to serial port: {e}\n\n" \
                      f"Please check if the device is connected, the port is correct, and not in use by another application."
            messagebox.showerror("Linear Actuator Connection Error", f"{message}")
            time.sleep(10)
        except Exception as e:
            messagebox.showerror("Initialization Error", f"An unexpected error occured during initialization:\n{e}")

        try:
            self.rot.labjack_config()
            self.status_updater(self.status_lbl2, "Connected")
        except ljm.LJMError as err:
            print(f"LabJack Error: {err}")
            self.handle = None
            messagebox.showerror("Failed to connect to LabJack")

        #self.run_serial_setup()

        self.button = "Start"
    
    def lin_widgets(self):
        framing = tk.LabelFrame(self.root,bg = "#6D83B3")
        framing.grid(rowspan=2, column=0, padx=10, pady=10, sticky="nsew")

        #Status HUB    
        Status = tk.LabelFrame(framing, text="System Status", bg = "#111827", fg = "white", font=("Helvetica", 12, "bold"))
        Status.grid(row=2, column=0, columnspan=2, padx=10, pady=10, sticky="ew")

        #Linear actuator status
        self.status_lbl = tk.Label(Status, text="Disconnected", bg = "#111827", fg = "white", font=("Helvetica", 9, "bold", "italic"))
        self.status_lbl.pack()

        #Labjack Status
        self.status_lbl2 = tk.Label(Status, text="Ready" if self.handle else "Disconnected", bg = "#111827", fg = "white", font=("Helvetica", 9, "bold", "italic"))
        self.status_lbl2.pack()

        #Data Collection?
        
        #data collection 
        self.data = tk.StringVar(value="Enabled")

        self.status_lbl3 = tk.Label(Status, text="Laser OFF", bg = "#111827", fg = "white", font=("Helvetica", 9, "bold", "italic"))
        self.status_lbl3.pack()

        tot_exp = f"Total Exposure Time Remaining = --:--"
        sec_exp = f"Current Exposure Time = --:--"

        #Exposure label    
        self.exposure_lbl = tk.Label(Status, text=f"{tot_exp}", bg = "#111827", fg = "white", font=("Helvetica", 9, "bold", "italic"))
        self.exposure_lbl.pack()

        #Current Exposure label   
        self.currentexposure_lbl = tk.Label(Status, text=f"{sec_exp}", bg = "#111827", fg = "white", font=("Helvetica", 9, "bold", "italic"))
        self.currentexposure_lbl.pack()

        with open (log_path, "r") as readlog:
            times = readlog.readlines()
        total_minutes1 = float(times[1].strip()) / 60
        total_minutes2 = float(times[2].strip()) / 60
        tot_min = (7836.745406824146968503937007874/self.selected_speed * float(self.targt_len))/60 - total_minutes1
        cur_time = 0 + total_minutes2
        sec1 = f"{int(float(tot_min-int(tot_min))*60):02}"
        sec2 = f"{int(float(cur_time-int(cur_time))*60):02}"
        self.status_updater(self.exposure_lbl, f"Total Exposure Time Remaining = {(int(tot_min))}:{sec1}")
        self.status_updater(self.currentexposure_lbl, f"Current Exposure Time = {(int(cur_time))}:{sec2}")

        #Sample exposure time
        self.timer1 = tk.IntVar(value=30)
        self.timer1l = tk.Label(framing,text = "Please enter exposure time in seconds", fg = "black", bg = "#6D83B3", font=("Helvetica", 9, "bold"))
        self.timer1l2 = tk.Label(framing, text = "s", fg = "black",bg = "#6D83B3", font=("Helvetica", 9, "bold"))
        self.timer1entry = tk.Entry(framing, textvariable=self.timer1, fg = "white", bg = "#273554", justify = "right")
        self.timer1l.grid(row=5, column=0, columnspan=2, padx=10, pady=10, sticky="ew")
        self.timer1entry.grid(row=6, column=0, columnspan=1, padx=10, pady=10, sticky="ew")
        self.timer1l2.grid(row=6, column=1, columnspan=1, padx=10, pady=10, sticky="w")

        #tk.Radiobutton(framing, text="Data Collection Enabled", variable=self.data, fg = "black",bg = "#6D83B3", value="Enabled").grid(row=7, column=0, columnspan=1, padx=10, pady=10, sticky="w")
        #tk.Radiobutton(framing, text="Data Collection Disabled", variable=self.data, fg = "black",bg = "#6D83B3", value="Disabled").grid(row=8, column=0, columnspan=1, padx=10, pady=10, sticky="w")

        #tk.Button(framing, text = "Select Save File").grid(row = 9, column = 0 , columnspan = 1, padx = 10, pady = 10, stick = "ew")

        #GUI responsivity
        self.root.columnconfigure(0, weight=1)
        self.root.update()
        framing.columnconfigure(1, weight=1)


    def animation_widgets(self):
        # Window
        self.framing = tk.LabelFrame(self.root, bg = "#111827", text="Target Visualization", fg = "white", font=("Helvetica", 12, "bold"))
        self.framing.grid(row=0, column=1, columnspan=2, padx=10, pady=10, rowspan = 2)            

        #self.canvas = tk.Canvas(framing, width=1300, height=500, bg="black")
        #self.canvas.grid(row=2, column=0, columnspan=2, padx=10, pady=10)  

        #self.canvas_width = int(self.canvas['width'])
        #self.canvas_height = int(self.canvas['height'])

        #general parameters
        self.animated = False
        self.last_time = time.time()
        self.speed_conversion = (30*7836.745406824146968503937007874)/(1300*0.15)
        self.phase_shift =  np.pi * 9/8
        self.clockw = True

        with open (log_path, "r") as readlog:
            pos = readlog.readlines()
            self.offset = abs(float(pos[0].strip()))/self.speed_conversion

        #buttons
        self.toggle_button1 = tk.Button(self.framing, text="Start Movement", bg="#1E40AF", fg="#EAF2FF", font=("Segoe UI", 12, "bold"), width=12, command = self.go_in)
        self.toggle_button1.grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="ew")    

        self.toggle_button3 = tk.Button(self.framing, text="Return to Home Position & Reset Timer", bg= "#CA8A04", fg="#FFFBEB", font=("Segoe UI", 12, "bold"), width=12, command = self.resetall) #change to the appr function
        self.toggle_button3.grid(row=6, column=0, columnspan=2, padx=10, pady=(10,13), sticky="ew")

        self.rest_cur_exp = tk.Button(self.framing, text="Reset Current Exposure", bg="#CA8A04", fg="#FFFBEB", font=("Segoe UI", 12, "bold"), command=self.reset)
        self.rest_cur_exp.grid(row=7, column=0, columnspan=2, padx = 10, pady=(0, 13), sticky="ew")

        self.toggle_button4 = tk.Button(self.framing, text="Set New Home Position", bg="#B91C1C", fg="#FFF5F5", font=("Segoe UI", 12, "bold"), width=12, command=self.rezero_pos)
        self.toggle_button4.grid(row=8, column=0, columnspan=2, padx=10, pady=(0,15), sticky="ew")

        self.canvas, self.target_xcenter = anim.setup_visualization(self.framing, self.offset)
        self.speed_conversion = (float(self.targt_len)*7836.745406824146968503937007874)/(float(self.canvas['width'])*0.15)
        self.rate = -self.speed/self.speed_conversion
        self.animation = anim.visualization(self.canvas, self.animated, self.rpmset, self.rate, self.root, self.phase_shift, self.target_xcenter)

#//////////////////////////////////////////////////////////Linear motion////////////////////////////////////////////////////////////////////////////////////////
#//////////////////////////////////////////////////////////Linear motion////////////////////////////////////////////////////////////////////////////////////////
#//////////////////////////////////////////////////////////Linear motion////////////////////////////////////////////////////////////////////////////////////////

    def go_in(self):
        if self.button == "Start":
            self.animation.animated = True
            self.status_updater(self.status_lbl3, "Laser Powering Up...")
            self.laser.powerup()
            self.status_updater(self.status_lbl3, "Laser at Full Power")
            self.animation.go()
            self.rot.run_threaded_rotation()
            self.data = lin.MOVE(-self.selected_speed, self.ser_in, "data")
            self.button = "going"
            self.friendly_button()
            self.recording()
        elif self.button == "going":
            self.laser.OFF()
            self.status_updater(self.status_lbl3, "Laser OFF")
            self.animation.animated = False
            self.animation.go()
            self.rot.stop_rotation()
            lin.stop(self.data, self.ser_in)
            self.button = "Start"
            self.friendly_button()
 

    def Buttoner(self, text, bg, fg):
        if self.open_gui:    
                try:
                    self.toggle_button1.config(text=text, bg=bg, fg=fg)
                    self.root.update()
                except tk.TclError:
                    self.open_gui = False

    def Button_changer(self):
        if self.button == "Start":
            self.Buttoner("Start Movement", "#1E40AF", "white")
        elif self.button == "going":
            self.Buttoner("Stop", "#B91C1C", "white")

    def friendly_button(self):
        threading.Thread(target=self.Button_changer, daemon=True).start()

###Position Tracking?
    def record(self):
        with open (log_path, "r") as readlog:
            times = readlog.readlines()
        total_minutes1 = float(times[1].strip()) / 60
        total_minutes2 = float(times[2].strip()) / 60
        minutes1 = int(total_minutes1)
        minutes2 = int(total_minutes2)
        seconds1 = (total_minutes1 - minutes1)/60 
        seconds2 = (total_minutes2 - minutes2)/60 
        self.dt = total_minutes1*60
        self.t = total_minutes2*60
        last_time = time.time()
        while self.animation.animated == True:
            now = time.time()
            elapsed = now - last_time
            last_time = now
            self.dt += elapsed
            self.t += elapsed
            if self.dt >= float(7836.745406824146968503937007874/self.selected_speed * self.targt_len):
                self.reset()
                self.go_in()
                messagebox.showerror("Tin Target Spent", "Please replace the tin target")

            if self.t >= float(self.timer1.get()):
                self.go_in()
                self.reset()
                messagebox.showinfo("Exposure Completed", "Exposure completed")

            tot_min = (7836.745406824146968503937007874/self.selected_speed* float(self.targt_len) - self.dt)/60
            cur_time = (self.t/60)
            sec1 = f"{int(float(tot_min-int(tot_min)-seconds1)*60):02}"
            sec2 = f"{int(float(cur_time-int(cur_time)+seconds2)*60):02}"
            self.status_updater(self.exposure_lbl, f"Total Exposure Time Remaining = {(int(tot_min))}:{sec1}")
            self.status_updater(self.currentexposure_lbl, f"Current Exposure Time = {(int(cur_time))}:{sec2}")
            time.sleep(0.01)
        else:
            tot_time = self.dt
            current_exp = self.t
            tot_displ = -self.dt*self.selected_speed
            tot_displ = self.dt*self.selected_speed
            with open (log_path, "w") as log:
                    log.write(f"{tot_displ}\n{tot_time}\n{current_exp}")

    def recording(self):
        threading.Thread(target=self.record, daemon=True).start()

#####New home position
    def rezero_pos(self):
        lin.stop_linmotion(self.ser_in)
        with open (log_path, "r") as readlog:
            este = readlog.readlines()
        with open (log_path, "w") as log:
            log.write(f"0\n{este[1].strip()}\n{este[2].strip()}")
        
        target_xcenter = float(self.canvas["width"])/2
        # Parameters for target
        self.animation.target_xcenter = target_xcenter
        self.animation.animated = False
        self.animation.go()

    def new_home(self):
        threading.Thread(target = self.rezero_pos, daemon=True).start()

###reset current exposure
    def res_cur_exp(self):
        lin.stop_linmotion(self.ser_in)
        self.button = "Start"
        self.friendly_button()
        with open (log_path, "r") as readlog:
            lines = readlog.readlines()
        with open (log_path, "w") as log:
            log.write(f"{lines[0].strip()}\n{lines[1].strip()}\n0")
        self.status_updater(self.currentexposure_lbl, f"Current Exposure Time = 0:00")
        self.root.update()

    def reset(self):
        threading.Thread(target=self.res_cur_exp, daemon=True).start()

        self.t = 0

###reset all
    def wipe(self):
        with open (log_path, "w") as log:
            log.write(f"0\n0\n0")
        tot_min = (7836.745406824146968503937007874/300 * float(self.targt_len))/60
        sec1 = f"{int(float(tot_min-int(tot_min))*60):02}"
        self.status_updater(self.exposure_lbl, f"Total Exposure Time Remaining = {(int(tot_min))}:{sec1}")
        self.status_updater(self.currentexposure_lbl, f"Current Exposure Time = 0:00")
        self.root.update()

    def resetall(self):
        speed = 4000
        with open (log_path, "r") as readlog:
            este = readlog.readlines()
        anim.setup_visualization(self.framing, 0)
        self.rot.stop_rotation()
        lin.MOVE(speed, self.ser_in, "nodata")
        time.sleep(abs(float(este[0].strip()))/speed)
        lin.stop_linmotion(self.ser_in)
        threading.Thread(target=self.wipe, daemon=True).start()

    def run_serial_setup(self):
        threading.Thread(target=self.serial_port_setup, daemon=True).start()

    def status_updater(self, label, text):
        if self.open_gui:
            try:
                label.config(text=text)
                self.root.update()
            except tk.TclError:
                self.open_gui = False

#####
#rezero position
#####



#//////////////////////////////////////////////////////////Rotational motion////////////////////////////////////////////////////////////////////////////////////////
#//////////////////////////////////////////////////////////Rotational motion////////////////////////////////////////////////////////////////////////////////////////
#//////////////////////////////////////////////////////////Rotational motion////////////////////////////////////////////////////////////////////////////////////////


#//////////////////////////////////////////////////////////ANIMATION////////////////////////////////////////////////////////////////////////////////////////
#//////////////////////////////////////////////////////////ANIMATION////////////////////////////////////////////////////////////////////////////////////////
#//////////////////////////////////////////////////////////ANIMATION////////////////////////////////////////////////////////////////////////////////////////   

    def reset_all(self):
        #self.stop()
        with open (log_path, "r") as readlog:
            este = readlog.readlines()
        print(f"{este[0]}")
        if abs(int(float(este[0].strip())))>0:
            self.home()
        else:
            pass
        self.button = "Start"
        self.friendly_button()
        self.status_updater(self.exposure_lbl, f"Total Exposure Time Remaining = --:--")
        self.status_updater(self.currentexposure_lbl, f"Current Exposure Time = --:--")
        with open (log_path, "r") as readlog:
            este = readlog.readlines()
        with open (log_path, "w") as log:
            log.write(f"{este[0].strip()}\n0\n0")

    def home(self):
        threading.Thread(target=self.home2, daemon=True).start()

    def home2(self):
        self.update_coords()
        print("coords updated")
        with open (log_path, "r") as log:
            lines = log.readlines()
            moved = float(lines[0].strip())
            time_t = float(lines[1].strip())
        with open (log_path, "w") as log:
            log.write(f"0\n0\n0")
            self.status_updater(self.status_lbl, "Moving to Home position")
            self.status_updater(self.currentexposure_lbl, f"Current Exposure Time = 0:00")

        self.rezero_pos()
          
    def new_exposure(self):
        self.stop()

        log = open (log_path, "r")
        lines = log.readlines()
        time_t = float(lines[1].strip())
        log.close()

        log = open (log_path, "w")
        log.write(f"{lines[0].strip()}\n{time_t}\n0")
        log.close()

        self.status_updater(self.currentexposure_lbl, f"Current Exposure Time = 0:00")
        self.button = "Start"
        self.friendly_button()
        self.t = 0

    
#/////////////////////////////////////////////////////////////////GUI///////////////////////////////////////////////////////////////////////////

root = tk.Tk()
root.title("Target Motion Control Remake")
root.resizable(True, True)
root.configure(bg="black")
ui = TargetMotionControlGUI(root)
root.grid_propagate(True)
root.mainloop()

#/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////   
          