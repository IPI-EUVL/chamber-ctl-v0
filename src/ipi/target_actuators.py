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

#import Data_Collection_V5
#/////////////////////////////////////IMPORTS/////////////////////////////////////////////////////////////////////////////////////


# Get path to the folder where the script/exe is running
if getattr(sys, 'frozen', False):
    base_path = os.path.dirname(sys.executable)  # If running from PyInstaller bundle
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

log_path = os.path.join(os.getcwd(), "data\\Log.txt")

print(f"Writing to log file: {log_path}")

data_collection_path = os.path.join(base_path, "Data_Collection_V5.py")



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

class TargetMotionControl:
    def __init__(self):
        self.__handle = None
        self.PUL_PLUS = "FIO4"
        self.PUL_MIN = "FIO5"
        self.DIR_PLUS = "FIO6"
        self.DIR_MIN = "FIO7"

        self.PORT_NUM = 3

        self.__steps_per_rev = 200
        self.__microsteps = 16 #If the number of microsteps is changed, the DIP switches on the drivers must be set according to datasheet
        self.__sec_revs_per_step = 1/(self.__steps_per_rev*self.__microsteps)
        self.th_v = 0

        self.__shutdown = False

        self.__lin_queue = []
        self.__lin_command_block = False

        self.__z_home_pending = False
        self.z_target = float('nan')
        self.z_v = 0

        self.__rot_setup_labjack()
        self.__lin_open_port()

        self.__rot_daemon_start()
        self.__lin_daemon_start()

    def rot_set_velocity(self, vel):
        self.th_v = vel

    def lin_set_velocity(self, vel):
        self.z_v = vel

    def lin_home(self):
        self.__z_home_pending = True

    def lin_goto(self, z):
        self.z_target = z

    def stop(self):
        self.__rot_stop()
        self.__lin_stop()
        
    def __rot_setup_labjack(self):
        self.__handle = ljm.openS("ANY", "ANY", "ANY")

        ljm.eWriteName(self.__handle, "DIO_INHIBIT", 0)  #All outputs enabled
        ljm.eWriteName(self.__handle, "DIO_ANALOG_ENABLE", 0)  #Set to digital not analog
        ljm.eWriteName(self.__handle, self.PUL_PLUS, 0)
        ljm.eWriteName(self.__handle, self.PUL_MIN, 0)  #Inverse of PUL+
        ljm.eWriteName(self.__handle, self.DIR_PLUS, 0)
        ljm.eWriteName(self.__handle, self.DIR_MIN, 0)  #Inverse of DIR+

#//////////////////////////////////////////////////////////Linear motion////////////////////////////////////////////////////////////////////////////////////////
#//////////////////////////////////////////////////////////Linear motion////////////////////////////////////////////////////////////////////////////////////////
#//////////////////////////////////////////////////////////Linear motion////////////////////////////////////////////////////////////////////////////////////////
#hel
    def __lin_open_port(self):
        self.__lin_port = serial.Serial(port=f'COM{self.PORT_NUM}', baudrate=9600, bytesize=7, parity='E', stopbits=1, timeout=0.5)
            
    def __lin_daemon_start(self): 
        threading.Thread(target=self.__lin_daemon, daemon=True).start()
            
    def __lin_daemon(self):
        self.__lin_command("DM00000000")
        self.__lin_command("AM10000000")

        self.ser_in.write("SV30000\r")
        self.ser_in.write("SF30000\r")
        self.ser_in.write("SJ10000\r")
        self.ser_in.write("SA50000\r")
        self.ser_in.write("LD500000\r")
        self.ser_in.write("SD50000\r")
        
        while True:
            time.sleep(0.1)

            status = self.__lin_command(b"CO", None)
            print (status)

            if self.__z_home_pending:
                self.__lin_command(b"HD")


    def __lin_write_command(self, command):
        to_write = f"1{command}\r"
        self.__lin_port.write(to_write.encode('utf-8'))
            
    def __lin_read(self):
        ret = self.__lin_port.read_until()
        return ret
            
    def __lin_command(self, command, expected_reply = b"OK"):
        self.__lin_write_command(command)
        ret = self.__lin_read()

        print(ret)

        if ret is None:
            raise Exception("Did not get reply from linear actuator")
        
        if expected_reply is not None and ret != expected_reply:
            raise Exception(f"Unexpected reply from linear actuator: {ret}")
        
        return ret
                
    
    def __lin_stop(self):
        self.moving = False
        self.__lin_enqueue('1AB')
        time.sleep(2)
        self.__lin_enqueue('1RS')
        time.sleep(0.5)

    def __rot_daemon_start(self): 
        threading.Thread(target=self.__rot_daemon, daemon=True).start()
    
    def __rot_daemon(self):
        while not self.__shutdown:
            cw = self.th_v > 0

            ljm.eWriteName(self.__handle, self.DIR_PLUS, 1 if cw else 0)
            ljm.eWriteName(self.__handle, self.DIR_MIN, 0)
            
            step_delay = self.__sec_revs_per_step / abs(self.th_v)

            if step_delay > 0.1:
                time.sleep(0.1)
                continue

            if cw and self.th_v < 0:
                ljm.eWriteName(self.__handle, self.DIR_PLUS, 0)
                ljm.eWriteName(self.__handle, self.DIR_MIN, 0)
            elif not cw and self.th_v > 0:
                ljm.eWriteName(self.__handle, self.DIR_PLUS, 1)
                ljm.eWriteName(self.__handle, self.DIR_MIN, 0)

            cw = self.th_v > 0

            ljm.eWriteName(self.__handle, self.PUL_PLUS, 1)
            time.sleep(step_delay / 2)
            ljm.eWriteName(self.__handle, self.PUL_PLUS, 0)
            time.sleep(step_delay / 2)

    def __rot_stop(self):
        self.th_v = 0



#//////////////////////////////////////////////////////////GUI////////////////////////////////////////////////////////////////////////////////////////
class TargetMotionControlGUI:
    def __init__(self, root):
        self.root = root
        root.title("Target Motion Control")
        root.configure(bg="black")

        #LabJack setup
        self.handle = None
        self.PUL_PLUS = "FIO4"
        self.PUL_MIN = "FIO5"
        self.DIR_PLUS = "FIO6"
        self.DIR_MIN = "FIO7"

        #Parameters
        self.steps_per_rev = 200
        self.microsteps = 16 #If the number of microsteps is changed, the DIP switches on the drivers must be set according to datasheet
        self.rpm_to_delay = 60/(self.steps_per_rev*self.microsteps)
        self.running = False
        self.straight_up_rotating_it_and_by_it_I_mean_my_linear_acuator = False
        self.open_gui = True
        self.ser_in = None
        self.ser_connected = False
        self.directional = "cw"
        self.is_in_or_out = "in"
        self.selected_speed = 300 #change to 300 maybe ?(previous speed 500)
        self.rpmset = 1

        try:
            self.handle = ljm.openS("ANY", "ANY", "ANY")
            self.pins()
        except ljm.LJMError as err:
            print(f"LabJack Error: {err}")
            self.handle = None
            self.show_error_message("Failed to connect to LabJack")
        

        #Ports
        self.ports = serial.tools.list_ports.comports()
        self.available_ports = []
        self.highest_number = 0
        for port in self.ports:
            self.available_ports.append(port.device)
        for port in self.ports:
            number = int(port.device.replace("COM",""))
            if number > self.highest_number:
                self.highest_number = number


        #GUI setup
        self.lin_widgets()

        self.animation_widgets()

        self.run_serial_setup()

        self.button = "Start"
    
    def pins(self):
        if not self.handle:
            return
            
        ljm.eWriteName(self.handle, "DIO_INHIBIT", 0)  #All outputs enabled
        ljm.eWriteName(self.handle, "DIO_ANALOG_ENABLE", 0)  #Set to digital not analog
        ljm.eWriteName(self.handle, self.PUL_PLUS, 0)
        ljm.eWriteName(self.handle, self.PUL_MIN, 1)  #Inverse of PUL+
        ljm.eWriteName(self.handle, self.DIR_PLUS, 0)
        ljm.eWriteName(self.handle, self.DIR_MIN, 1)  #Inverse of DIR+
    
    def lin_widgets(self):
        framing = ttk.LabelFrame(self.root, text="Actuators Control")
        framing.grid(rowspan=2, column=0, padx=10, pady=10, sticky="nsew")

        #Status HUB    
        Status = ttk.LabelFrame(framing, text="System Status")
        Status.grid(row=2, column=0, columnspan=2, padx=10, pady=10, sticky="ew")

        #Linear actuator status
        self.status_lbl = ttk.Label(Status, text="Disconnected", font=("Helvetica", 9, "bold", "italic"))
        self.status_lbl.pack()

        #Labjack Status
        self.status_lbl2 = ttk.Label(Status, text="Ready" if self.handle else "Disconnected", font=("Helvetica", 9, "bold", "italic"))
        self.status_lbl2.pack()

        #tin target length
        self.length = tk.IntVar()
        self.targetl = ttk.Label(framing, text = "Please enter target length", font=("Helvetica", 9, "bold"))
        self.targetl2 = ttk.Label(framing, text = "mm", font=("Helvetica", 9, "bold"))
        self.targetentry = tk.Entry(framing, textvariable=self.length)
        self.targetl.grid(row=3, column=0, columnspan=2, padx=10, pady=10, sticky="ew")
        self.targetentry.grid(row=4, column=0, columnspan=1, padx=10, pady=10, sticky="ew")
        self.targetl2.grid(row=4, column=1, columnspan=1, padx=10, pady=10, sticky="w")



        with open (log_path, "r") as readlog:
            times = readlog.readlines()
        total_minutes1 = float(times[1].strip()) / 60
        total_minutes2 = float(times[2].strip()) / 60
        minutes1 = int(total_minutes1)
        minutes2 = int(total_minutes2)
        seconds1 = (total_minutes1 - minutes1)/60 
        seconds2 = (total_minutes2 - minutes2)/60 
        dt = total_minutes1*60
        t = total_minutes2*60
        tot_min = (12.83333333333*60 - dt)/60
        cur_time = (t/60)
        sec1 = f"{int(float(tot_min-int(tot_min)-seconds1)*60):02}"
        sec2 = f"{int(float(cur_time-int(cur_time)+seconds2)*60):02}"
        tot_exp = f"Total Exposure Time Remaining = {(int(tot_min))}:{sec1}"
        sec_exp = f"Current Exposure Time = {(int(cur_time))}:{sec2}"


        #Exposure label    
        self.exposure_lbl = ttk.Label(Status, text=f"{tot_exp}", font=("Helvetica", 9, "bold", "italic"))
        self.exposure_lbl.pack()

        #Current Exposure label   
        self.currentexposure_lbl = ttk.Label(Status, text=f"{sec_exp}", font=("Helvetica", 9, "bold", "italic"))
        self.currentexposure_lbl.pack()

        #GUI responsivity
        self.root.columnconfigure(0, weight=1)
        framing.columnconfigure(1, weight=1)

    def animation_widgets(self):
        # Window
        framing = ttk.LabelFrame(self.root, text="Target Visualization")
        framing.grid(row=0, column=1, columnspan=2, padx=10, pady=10, rowspan = 2)            

        self.canvas = tk.Canvas(framing, width=1300, height=500, bg="black")
        self.canvas.grid(row=2, column=0, columnspan=2, padx=10, pady=10)  

        canvas_width = int(self.canvas['width'])
        canvas_height = int(self.canvas['height'])

        #general parameters
        self.animated = False
        self.last_time = time.time()
        self.speed_conversion = (self.targetentry.get()*7836.745406824146968503937007874)/(canvas_width*0.15)
        self.phase_shift =  np.pi * 9/8
        self.clockw = True

        with open (log_path, "r") as readlog:
            pos = readlog.readlines()
            self.offset = abs(float(pos[0].strip()))/self.speed_conversion

        #buttons
        self.toggle_button1 = tk.Button(framing, text="Start Movement", bg="green", fg="white", font=("Segoe UI", 12, "bold"), width=12, command=self.go_in)
        self.toggle_button1.grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="ew")    

        self.toggle_button2 = tk.Button(framing, text="New Sample (Reset Exposure Time)", bg = "blue", fg="white", font=("Segoe UI", 12, "bold"), width=12, command=self.new_exposure)
        self.toggle_button2.grid(row=5, column=0, columnspan=2, padx=10, pady=10, sticky="ew")

        self.toggle_button3 = tk.Button(framing, text="Return to Home Position & Reset Timer", bg= "red", fg="white", font=("Segoe UI", 12, "bold"), width=12, command=self.reset_all)
        self.toggle_button3.grid(row=6, column=0, columnspan=2, padx=10, pady=(10,0), sticky="ew")

        separator = tk.Label(framing, text=". . . . .", font=("Segoe UI", 20, "bold"))
        separator.grid(row=7, column=0, columnspan=2, pady=(0, 13))

        self.toggle_button4 = tk.Button(framing, text="Set New Home Position", bg="red", fg="white", font=("Segoe UI", 12, "bold"), width=12, command=self.rezero_pos)
        self.toggle_button4.grid(row=8, column=0, columnspan=2, padx=10, pady=(0,15), sticky="ew")

        # Parameters for target
        self.target_lenght = canvas_width * 0.17
        self.target_width = canvas_height * 0.1
        self.target_ycenter = canvas_height/2
        self.target_xcenter = canvas_width * 0.5 - self.offset 

        #parameters for holder
        self.holder_lenght = canvas_width - (self.target_xcenter + self.target_lenght/2)
        self.holder_width = self.target_width * 2
        self.holder_ycenter = canvas_height/2
        self.holder_xcenter = self.target_xcenter + self.target_lenght/2 + self.holder_lenght/2

        #parameters for laser
        self.laser_lenght = canvas_height/2
        self.laser_width = 5
        self.laser_ycenter = canvas_height * 3/4 + self.target_width/2
        self.laser_xcenter = canvas_width/2 - self.target_lenght/2 -5

        # Drawing coordinates for target
        self.x1 = self.target_xcenter - self.target_lenght / 2
        self.x2 = self.target_xcenter + self.target_lenght / 2        
        self.y1 = self.target_ycenter - self.target_width / 2
        self.y2 = self.target_ycenter + self.target_width / 2

        # Drawing coordinates for holder
        self.hx1 = self.holder_xcenter - self.holder_lenght / 2
        self.hx2 = self.holder_xcenter + self.holder_lenght / 2        
        self.hy1 = self.holder_ycenter - self.holder_width / 2
        self.hy2 = self.holder_ycenter + self.holder_width / 2

        #Drawing coordinates for laser
        self.lx1 = self.laser_xcenter - self.laser_width / 2
        self.lx2 = self.laser_xcenter + self.laser_width / 2        
        self.ly1 = self.laser_ycenter + self.laser_lenght / 2
        self.ly2 = self.laser_ycenter - self.laser_lenght / 2
        
        #impact
        self.impactl = 10
        self.impact_angle = np.radians(50)
        self.x1impact = self.lx1
        self.x2impact = self.x1impact - self.impactl * np.cos(self.impact_angle)
        self.y1impact = self.ly2
        self.y2impact = self.y1impact + self.impactl * np.sin(self.impact_angle)

        #line 7 
        self.line7x1 = self.x1
        self.line7y1 = self.target_ycenter 
        self.line7x2 = self.x2
        self.line7y2 = self.target_ycenter - (self.target_width / 2) * (np.sin(self.phase_shift))

        # Line 8
        self.line8x1 = self.x1
        self.line8y1 = self.target_ycenter - (self.target_width / 2)
        self.line8x2 = self.x2
        self.line8y2 = self.target_ycenter + (self.target_width / 2) * (np.cos(self.phase_shift))/2

        # Line 9
        self.line9x1 = self.x1
        self.line9y1 = self.target_ycenter + (self.target_width / 2) * (np.sin(np.pi/4))
        self.line9x2 = self.x2
        self.line9y2 = self.target_ycenter - (self.target_width / 2) * (np.sin(self.phase_shift + np.pi/4))


        # Motion stuff
        self.moving = False

        # Drawing 
        self.target = self.canvas.create_polygon(self.x1, self.y2, self.x1 - self.target_lenght * 0.07, self.target_ycenter, self.x1, self.y1, self.x2, self.y1, self.x2, self.y2, fill = "lightgrey", width = 3)
        self.line7 = self.canvas.create_line(self.line7x1, self.line7y1, self.line7x2, self.line7y2, fill="darkgrey", width=3)
        self.line8 = self.canvas.create_line(self.line8x1, self.line8y1, self.line8x2, self.line8y2, fill="darkgrey", width=3)
        self.line9 = self.canvas.create_line(self.line9x1, self.line9y1, self.line9x2, self.line9y2, fill="darkgrey", width=3)
        self.target = self.canvas.create_polygon(self.x1, self.y2, self.x1 - self.target_lenght * 0.07, self.target_ycenter, self.x1, self.y1, self.x2, self.y1, self.x2, self.y2, fill = "", outline="violet", width = 3)
        self.holder = self.canvas.create_rectangle(self.hx1, self.hy1, self.hx2, self.hy2, fill="grey", outline="white", width=2)
        self.laser = self.canvas.create_rectangle(self.lx1, self.ly1, self.lx2, 0, fill="darkred", outline="red", width=2)     

        if self.lx1 >= self.x1:
            self.canvas.itemconfig(self.laser, state = 'hidden')
            self.canvas.create_rectangle(self.lx1, self.ly1, self.lx2, self.ly2, fill="darkred", outline="red", width=3)
            self.line1 = self.canvas.create_line(self.x1impact, self.y1impact, self.x2impact, self.y2impact, fill = "red", width = 5)
            self.line2 = self.canvas.create_line(self.lx2, self.y1impact, self.lx2 + self.impactl * np.cos(self.impact_angle), self.y2impact, fill = "red", width = 5)
        
        #GUI responsivity
        self.root.columnconfigure(0, weight=1)
        framing.columnconfigure(1, weight=1)
        framing.grid_columnconfigure(0, weight=1)
        framing.grid_columnconfigure(1, weight=1)
        self.canvas.columnconfigure(1, weight = 1)

#//////////////////////////////////////////////////////////Linear motion////////////////////////////////////////////////////////////////////////////////////////
#//////////////////////////////////////////////////////////Linear motion////////////////////////////////////////////////////////////////////////////////////////
#//////////////////////////////////////////////////////////Linear motion////////////////////////////////////////////////////////////////////////////////////////
#hel
    def run_serial_setup(self):
        threading.Thread(target=self.serial_port_setup, daemon=True).start()

    def serial_port_setup(self):
        try:
            self.ser_in = serial.Serial(port=f'COM{self.highest_number}', baudrate=9600, bytesize=7, parity='E', stopbits=1, timeout=1)
            self.ser_connected = True
            self.status_updater(f"Successfully connected to {self.ser_in.portstr}")
            time.sleep(3)
            self.status_updater("Ready")
        except serial.SerialException as e:
            self.ser_in = None # Ensure ser_in is None if connection fails
            self.ser_connected = False
            message = f"Failed to connect to serial port: {e}\n\n" \
                      f"Please check if the device is connected, the port is correct, and not in use by another application."
            self.status_updater(message)
            time.sleep(10)
            self.status_updater("Disconnected")

    def status_updater(self, text):
        if self.open_gui:
            try:
                self.status_lbl.config(text=text)
                self.root.update()
            except tk.TclError:
                self.open_gui = False

    def Exposure_timer(self, text):
        if self.open_gui:
            try:
                self.exposure_lbl.config(text=text)
                self.root.update()
            except tk.TclError:
                self.open_gui = False

    def Exposure_timer_the_second(self, text):
        if self.open_gui:
            try:
                self.currentexposure_lbl.config(text=text)
                self.root.update()
            except tk.TclError:
                self.open_gui = False

    def Buttoner(self, text, bg, fg):
        if self.open_gui:    
                try:
                    self.toggle_button1.config(text=text, bg=bg, fg=fg)
                    self.root.update()
                except tk.TclError:
                    self.open_gui = False

    def friendly_button(self):
        threading.Thread(target=self.Button_changer, daemon=True).start()
#####
    def Button_changer(self):
        if self.button == "Start":
            self.Buttoner("Start", "#43a047", "white")
        elif self.button == "going":
            self.Buttoner("Stop", "red", "white")
            #self.data_collec = subprocess.Popen(["C:\\Program Files\\Python313\\python.exe C:\\Apps\\Testing\\Data_Collection_V5.py"])
            Data_Collection_V5.configure_oscilloscope("1")
            Data_Collection_V5.running = True
            Data_Collection_V5.collect_raw_data()
            print("yay")
        elif self.button == "stopped":
            #subprocess.run(["taskkill", "/IM", "Data_Collection_V5.exe", "/F"], shell=True)
            Data_Collection_V5.running = False
            self.Buttoner("Continue", "darkgrey", "white")
            print("killed")

#####
    def run_communicate(self): 
        threading.Thread(target=self.communicate, daemon=True).start()

    def communicate(self, command):
            try:
                cmd = command + '\r'
                cd = cmd.encode()
                self.ser_in.write(cd)
            except AttributeError:
                messagebox.showerror("Connection Error", "Linear actuator is not connected.")
                return False
                
    
    def run_threaded_in(self): 
        threading.Thread(target=self.go_in, daemon=True).start()

    def run_threaded_out(self): 
        threading.Thread(target=self.go_out, daemon=True).start()

    
    def stop_linmotion(self):
        self.moving = False
        self.communicate('1AB')
        time.sleep(2)
        self.communicate('1RS')
        time.sleep(0.5)

#//////////////////////////////////////////////////////////Rotational motion////////////////////////////////////////////////////////////////////////////////////////
#//////////////////////////////////////////////////////////Rotational motion////////////////////////////////////////////////////////////////////////////////////////
#//////////////////////////////////////////////////////////Rotational motion////////////////////////////////////////////////////////////////////////////////////////
    
    def pulse(self):
        if not self.handle:
            return
            
        ljm.eWriteName(self.handle, self.PUL_PLUS, 1)
        time.sleep(0.000001)
        ljm.eWriteName(self.handle, self.PUL_PLUS, 0)
        time.sleep(0.000001)  # Pulse duration, adjust as needed

    def direction_set(self, direction):
        if not self.handle:
            return
            
        if direction:
            ljm.eWriteName(self.handle, self.DIR_PLUS, 1)
            ljm.eWriteName(self.handle, self.DIR_MIN, 0)
        else:  
            ljm.eWriteName(self.handle, self.DIR_PLUS, 0)
            ljm.eWriteName(self.handle, self.DIR_MIN, 1)

    def run_threaded_rotation(self): 
        threading.Thread(target=self.start_rotation, daemon=True).start()

    def rotate_cw(self):
        self.directional = "cw"
        self.run_threaded_rotation()

    def rotate_ccw(self):
        self.directional = "ccw"
        self.run_threaded_rotation()
    
    def start_rotation(self):
        self.stop_rotation()
        self.straight_up_rotating_it_and_by_it_I_mean_my_linear_acuator = True
        self.animated = True
        self.visualization()
        if not self.handle or self.running:
            return
            
        try:
            rpm = float(self.rpmset)
            direction = self.directional == "ccw"
            
            if rpm <= 0:
                self.gui_updater("RPM must be positive")
                return
                
            self.running = True
            self.straight_up_rotating_it_and_by_it_I_mean_my_linear_acuator = True
            self.gui_updater(f"Rotating {'CCW' if direction else 'CW'} at {rpm} RPM...")
            
            step_delay = self.rpm_to_delay / rpm
            self.direction_set(direction)
            
            while self.running:
                self.pulse()
                time.sleep(step_delay)
                if not self.open_gui:
                    break
                    
            self.gui_updater("Ready")
            
        except ValueError:
            self.gui_updater("Invalid RPM value")
        except ljm.LJMError as err:
            self.gui_updater(f"LabJack Error: {err}")
            self.running = False

    def stop_rotation(self):
        self.running = False
        self.straight_up_rotating_it_and_by_it_I_mean_my_linear_acuator = False
        self.gui_updater("Idle")

    def gui_updater(self, text):
        if self.open_gui:
            try:
                self.status_lbl2.config(text=text)
                self.root.update()
            except tk.TclError:
                self.open_gui = False

    def window_popup(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        self.cleanup()
        self.root.destroy()

    def cleanup(self):
        self.open_gui = False
        self.stop_rotation()
        try:
            self.ser_in = serial.Serial(port=f'{str(self.selected_port.get())}', baudrate=9600, bytesize=7, parity='E', stopbits=1, timeout=1)
            self.ser_connected = True
            time.sleep(0.1)

            if self.ser_connected == True:
                self.stop()
                self.ser_in.close()
                self.root.destroy()

        except serial.SerialException as e:
            self.ser_in = None # Ensure ser_in is None if connection fails
            self.ser_connected = False
            self.root.destroy()

        if self.handle:
            ljm.close(self.handle)

    def show_error_message(self, message):
        error_window = tk.Toplevel(self.root)
        error_window.title("Error")
        ttk.Label(error_window, text=message).pack(padx=20, pady=20)
        ttk.Button(error_window, text="OK", command=error_window.destroy).pack(pady=10)

#//////////////////////////////////////////////////////////ANIMATION////////////////////////////////////////////////////////////////////////////////////////
#//////////////////////////////////////////////////////////ANIMATION////////////////////////////////////////////////////////////////////////////////////////
#//////////////////////////////////////////////////////////ANIMATION////////////////////////////////////////////////////////////////////////////////////////
   
    def go_in(self):
        self.is_in_or_out = "in"
        if self.button == "Start":
            self.button = "going"
            self.friendly_button()
            self.dt = 0
            self.t = 0
            self.last_time = time.time()  # Reset time before animation
            threading.Thread(target=self.MOVE, daemon=True).start()
            self.rotate_cw()

        elif self.button == "going":
            self.button = "stopped"
            self.friendly_button()
            self.stop()

        elif self.button == "stopped":
            self.button = "going"
            self.friendly_button()
            self.last_time = time.time()  # Reset time here to avoid jump
            threading.Thread(target=self.MOVE, daemon=True).start()
            self.rotate_cw()


        
    def MOVE(self, speed_str = 2000):
        if self.is_in_or_out == "in":
            self.move = True
            self.recording()
            try:
                speed_str = self.selected_speed
                self.rate = int(speed_str) / self.speed_conversion
                self.newrate = -self.rate
                self.animated = True
                self.moving = True
                self.visualization()
                threading.Thread(target=self.update_coords, daemon=True).start()
                self.communicate(f'1CV-{float(speed_str)}')
                self.status_updater(f"Moving in at {speed_str} steps/s")

            except ValueError:
                messagebox.showerror("Input Error", "Please select a valid speed.")
                return False
        else:
            try:
                self.rate = int(speed_str) / self.speed_conversion
                self.newrate = self.rate
                self.animated = True
                self.moving = True
                self.visualization()
                threading.Thread(target=self.update_coords, daemon=True).start()
                self.communicate(f'1CV{float(speed_str)}')
                self.status_updater(f"Moving out at {speed_str} steps/s")
            except ValueError:
                messagebox.showerror("Input Error", "Please select a valid speed.")
                return False

    def go_out(self, speed):
        self.is_in_or_out = "GETOUT"
        self.last_time = time.time()  #  Reset last_time to current time
        threading.Thread(target=self.MOVE, args=(speed,), daemon=True).start()
        self.rotate_ccw()


    def stop(self):
        self.status_updater(f"Stopping...")
        self.move = False
        self.moving = False
        self.button = "stopped"
        self.stop_rotation()
        self.stop_linmotion()
        if self.handle:
            ljm.eWriteName(self.handle, self.PUL_PLUS, 0)
            ljm.eWriteName(self.handle, self.PUL_MIN, 1)
            ljm.eWriteName(self.handle, self.DIR_PLUS, 0)
            ljm.eWriteName(self.handle, self.DIR_MIN, 1)
        self.animated = False
        self.visualization()
        time.sleep(0.1)
        self.status_updater(f"Idle")
        #STOP EVERYTHING

    def visualization(self):
        try:
            if not self.animated:
                return
            
            current_time = time.time()
            dt = current_time - self.last_time
            self.last_time = current_time
            self.direction1 = self.directional == "cw"
            self.clockw = self.direction1
            self.new_rot_rate = float(self.rpmset) * ((2*np.pi)/60)

            if self.new_rot_rate < 0:
                messagebox.showerror("Input Error", "Please Enter a Valid RPM")
                return False

            if self.moving == True:
                self.current_rate = self.newrate
                #fix
                self.target_xcenter = self.target_xcenter + self.current_rate*dt
            else:
                pass

            self.impactl = np.absolute(10 + 5 * np.sin(np.radians(3000*time.time())))
            
            self.update_coords()

            self.root.after(2, self.visualization)
        except ValueError:
            messagebox.showerror("Input Error", "Please Enter a Valid RPM")
            return False


    def update_coords(self):
        self.canvas.delete("all")
        canvas_width = 1300
        canvas_height = 500
        # Parameters for target
        self.target_lenght = canvas_width * 0.17
        self.target_width = canvas_height * 0.1
        self.target_ycenter = canvas_height/2

        #parameters for holder
        self.holder_lenght = canvas_width - (self.target_xcenter + self.target_lenght/2)
        self.holder_width = self.target_width * 2
        self.holder_ycenter = canvas_height/2
        self.holder_xcenter = self.target_xcenter + self.target_lenght/2 + self.holder_lenght/2

        #parameters for laser
        self.laser_lenght = canvas_height/2
        self.laser_width = 5
        self.laser_ycenter = canvas_height * 3/4 + self.target_width/2
        self.laser_xcenter = canvas_width/2 - self.target_lenght/2 - 5

        # Drawing coordinates for targetu
        self.x1 = self.target_xcenter - self.target_lenght / 2
        self.x2 = self.target_xcenter + self.target_lenght / 2        
        self.y1 = self.target_ycenter - self.target_width / 2
        self.y2 = self.target_ycenter + self.target_width / 2

        # Drawing coordinates for holder
        self.hx1 = self.holder_xcenter - self.holder_lenght / 2
        self.hx2 = self.holder_xcenter + self.holder_lenght / 2        
        self.hy1 = self.holder_ycenter - self.holder_width / 2
        self.hy2 = self.holder_ycenter + self.holder_width / 2

        #Drawing coordinates for laser
        self.lx1 = self.laser_xcenter - self.laser_width / 2
        self.lx2 = self.laser_xcenter + self.laser_width / 2        
        self.ly1 = self.laser_ycenter + self.laser_lenght / 2
        self.ly2 = self.laser_ycenter - self.laser_lenght / 2
        
        #impact
        self.impact_angle = np.radians(50)
        self.x1impact = self.lx1
        self.x2impact = self.x1impact - self.impactl * np.cos(self.impact_angle)
        self.y1impact = self.ly2
        self.y2impact = self.y1impact + self.impactl * np.sin(self.impact_angle)

        if self.straight_up_rotating_it_and_by_it_I_mean_my_linear_acuator == True:

            #line 7 
            self.line7x1 = self.x1
            self.line7y1 = self.target_ycenter + (self.target_width / 2) * (np.sin((self.new_rot_rate * time.time())))
            self.line7x2 = self.x2
            self.line7y2 = self.target_ycenter - (self.target_width / 2) * (np.sin((self.new_rot_rate * time.time())+self.phase_shift))
            # Line 8
            self.line8x1 = self.x1
            self.line8y1 = self.target_ycenter + (self.target_width / 2) * (np.cos((self.new_rot_rate * time.time())))
            self.line8x2 = self.x2
            self.line8y2 = self.target_ycenter - (self.target_width / 2) * (np.cos((self.new_rot_rate * time.time())+self.phase_shift))

            # Line 9
            self.line9x1 = self.x1
            self.line9y1 = self.target_ycenter + (self.target_width / 2) * (np.sin((self.new_rot_rate * time.time()) + np.pi/4))
            self.line9x2 = self.x2
            self.line9y2 = self.target_ycenter - (self.target_width / 2) * (np.sin((self.new_rot_rate * time.time()) + self.phase_shift + np.pi/4))

            # rectangle cover
            self.rx1 = self.target_xcenter - self.target_lenght / 2
            self.rx2 = self.target_xcenter + self.target_lenght / 2 
            if self.clockw == True:
                self.ry1 = self.target_ycenter + (self.target_width / 2)* (np.sin((self.new_rot_rate * time.time())))
                self.ry2 = self.target_ycenter + self.target_width / 2
            else: 
                self.ry1 = self.target_ycenter - self.target_width / 2
                self.ry2 = self.target_ycenter + (self.target_width / 2)* (np.sin((self.new_rot_rate * time.time())))
        
        else:
             #line 7 
            self.line7x1 = self.x1
            self.line7y1 = self.target_ycenter 
            self.line7x2 = self.x2
            self.line7y2 = self.target_ycenter - (self.target_width / 2) * (np.sin(self.phase_shift))

            # Line 8
            self.line8x1 = self.x1
            self.line8y1 = self.target_ycenter - (self.target_width / 2)
            self.line8x2 = self.x2
            self.line8y2 = self.target_ycenter + (self.target_width / 2) * (np.cos(self.phase_shift))/2

            # Line 9
            self.line9x1 = self.x1
            self.line9y1 = self.target_ycenter + (self.target_width / 2) * (np.sin(np.pi/4))
            self.line9x2 = self.x2
            self.line9y2 = self.target_ycenter - (self.target_width / 2) * (np.sin(self.phase_shift + np.pi/4))

            # rectangle cover
            self.rx1 = 0
            self.rx2 = 0
            self.ry1 = 0
            self.ry2 = 0
        
        # Drawing 
        self.target = self.canvas.create_polygon(self.x1, self.y2, self.x1 - self.target_lenght * 0.07, self.target_ycenter, self.x1, self.y1, self.x2, self.y1, self.x2, self.y2, fill = "lightgrey", width = 3)

        self.line7 = self.canvas.create_line(self.line7x1, self.line7y1, self.line7x2, self.line7y2, fill="darkgrey", width=3)
        self.line8 = self.canvas.create_line(self.line8x1, self.line8y1, self.line8x2, self.line8y2, fill="darkgrey", width=3)
        self.line9 = self.canvas.create_line(self.line9x1, self.line9y1, self.line9x2, self.line9y2, fill="darkgrey", width=3)
        self.cover = self.canvas.create_rectangle(self.rx1, self.ry1, self.rx2, self.ry2, fill="lightgrey", outline = "lightgrey", width=2)

        self.target = self.canvas.create_polygon(self.x1, self.y2, self.x1 - self.target_lenght * 0.07, self.target_ycenter, self.x1, self.y1, self.x2, self.y1, self.x2, self.y2, fill = "", outline="violet", width = 3)
        self.holder = self.canvas.create_rectangle(self.hx1, self.hy1, self.hx2, self.hy2, fill="grey", outline="white", width=2)
        self.laser = self.canvas.create_rectangle(self.lx1, self.ly1, self.lx2, 0, fill="darkred", outline="red", width=2)     


        if self.lx2 >= self.x1:
            self.canvas.itemconfig(self.laser, state = 'hidden')
            self.canvas.create_rectangle(self.lx1, self.ly1, self.lx2, self.ly2, fill="darkred", outline="red", width=3)
            self.line1 = self.canvas.create_line(self.x1impact, self.y1impact, self.x2impact, self.y2impact, fill = "red", width = 5)
            self.line2 = self.canvas.create_line(self.lx2, self.y1impact, self.lx2 + self.impactl * np.cos(self.impact_angle), self.y2impact, fill = "red", width = 5)

    def rezero_pos(self):
        canvas_width = 1300
        canvas_height = 500
        with open (log_path, "r") as readlog:
            este = readlog.readlines()
        with open (log_path, "w") as log:
            log.write(f"0\n{este[1].strip()}\n{este[2].strip()}")
        # Parameters for target
        self.target_lenght = canvas_width * 0.15
        self.target_width = canvas_height * 0.1
        self.target_ycenter = canvas_height/2
        self.target_xcenter = canvas_width * 0.5
        self.update_coords()
        
    def reset_all(self):
        self.stop()
        with open (log_path, "r") as readlog:
            este = readlog.readlines()
        print(f"{este[0]}")
        if abs(int(float(este[0].strip())))>0:
            self.home()
        else:
            pass
        self.button = "Start"
        self.friendly_button()
        self.Exposure_timer(f"Total Exposure Time Remaining = 12:50")
        self.Exposure_timer_the_second(f"Current Exposure Time = 0:00")
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
            self.status_updater("Moving to Home position")
            self.Exposure_timer_the_second(f"Current Exposure Time = 0:00")
        if moved > 0:
            self.is_in_or_out = "in"
            self.MOVE(-2000)
            time.sleep(abs(moved)/2000)
            self.stop()
        else:
            self.is_in_or_out = "GET OUT"
            self.MOVE(2000)
            time.sleep(abs(moved)/2000)
            self.stop()
        self.rezero_pos()
          
    def new_exposure(self):
        self.stop()
        with open (log_path, "r") as log:
            lines = log.readlines()
            time_t = float(lines[1].strip())
        with open (log_path, "w") as log:
            log.write(f"{lines[0].strip()}\n{time_t}\n0")
        self.Exposure_timer_the_second(f"Current Exposure Time = 0:00")
        self.button = "Start"
        self.friendly_button()
        self.dt = 0
        self.t = 0

    def recording(self):
        threading.Thread(target=self.record, daemon=True).start()

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
        while self.move == True:
            now = time.time()
            elapsed = now - last_time
            last_time = now
            self.dt += elapsed
            self.t += elapsed
            if self.dt >= float(12.8 * 60):
                self.button = "going"
                self.friendly_button()
                self.stop()
                messagebox.showerror("Tin Target Spent", "Please replace the tin target")
            tot_min = (12.833333333333333*60 - self.dt)/60
            cur_time = (self.t/60)
            sec1 = f"{int(float(tot_min-int(tot_min)-seconds1)*60):02}"
            sec2 = f"{int(float(cur_time-int(cur_time)+seconds2)*60):02}"
            self.Exposure_timer(f"Total Exposure Time Remaining = {(int(tot_min))}:{sec1}")
            self.Exposure_timer_the_second(f"Current Exposure Time = {(int(cur_time))}:{sec2}")
            time.sleep(0.01)
        else:
            tot_time = self.dt
            current_exp = self.t
            if self.is_in_or_out == "in":
                    tot_displ = -self.dt*self.selected_speed
            else:
                    tot_displ = self.dt*self.selected_speed
            with open (log_path, "w") as log:
                    log.write(f"{tot_displ}\n{tot_time}\n{current_exp}")
#/////////////////////////////////////////////////////////////////GUI///////////////////////////////////////////////////////////////////////////

import tkinter as tk

def main():
    root = tk.Tk()
    app = TargetMotionControl()

    time.sleep(10)

if __name__ == "__main__":
    main()

#/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////   
