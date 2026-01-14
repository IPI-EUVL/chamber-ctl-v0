
<<<<<<< HEAD
from labjack import ljm
=======
import labjack as ljm
>>>>>>> 13c4082e4d72a76be7d0f0abd03d5120e38fe2b8
import time 
import threading 
import serial 

<<<<<<< HEAD
class Rotate:
=======
class Rotational_Motion:
>>>>>>> 13c4082e4d72a76be7d0f0abd03d5120e38fe2b8
    def __init__(self):
        self.handle = None
        self.PUL_PLUS = "FIO4"
        self.PUL_MIN = "FIO5"
        self.DIR_PLUS = "FIO6"
        self.DIR_MIN = "FIO7"
        self.steps_per_rev = 200
        self.microsteps = 16 #If the number of microsteps is changed, the DIP switches on the drivers must be set according to datasheet
        self.rpm_to_delay = 60/(self.steps_per_rev*self.microsteps)
        self.running = False
        self.straight_up_rotating_it_and_by_it_I_mean_my_linear_acuator = False
        self.open_gui = True
        self.ser_in = None
        self.ser_connected = False
        self.directional = "cw"
        self.rpmset = 1
    
    def pins(self):
        if not self.handle:
            return
            
        ljm.eWriteName(self.handle, "DIO_INHIBIT", 0)  #All outputs enabled
        ljm.eWriteName(self.handle, "DIO_ANALOG_ENABLE", 0)  #Set to digital not analog
        ljm.eWriteName(self.handle, self.PUL_PLUS, 0)
        ljm.eWriteName(self.handle, self.PUL_MIN, 1)  #Inverse of PUL+
        ljm.eWriteName(self.handle, self.DIR_PLUS, 0)
        ljm.eWriteName(self.handle, self.DIR_MIN, 1)  #Inverse of DIR+

    def labjack_config(self):
<<<<<<< HEAD
            self.handle = ljm.openS("ANY", "ANY", "ANY")
            self.pins()
=======
        try:
            self.handle = ljm.openS("ANY", "ANY", "ANY")
            self.pins()
        except ljm.LJMError as err:
            print(f"LabJack Error: {err}")
            self.handle = None
            self.show_error_message("Failed to connect to LabJack")
>>>>>>> 13c4082e4d72a76be7d0f0abd03d5120e38fe2b8

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
<<<<<<< HEAD
        self.straight_up_rotating_it_and_by_it_I_mean_my_linear_acuator = True #UIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUUIUIUIUIUIUIUIUIUIUIUI
=======
        self.straight_up_rotating_it_and_by_it_I_mean_my_linear_acuator = True
        self.animated = True
        self.visualization() #UIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUUIUIUIUIUIUIUIUIUIUIUI
>>>>>>> 13c4082e4d72a76be7d0f0abd03d5120e38fe2b8
        if not self.handle or self.running:
            return
            
        try:
            rpm = float(self.rpmset)
            direction = self.directional == "ccw"
                
            self.running = True
            self.straight_up_rotating_it_and_by_it_I_mean_my_linear_acuator = True
<<<<<<< HEAD

=======
            self.gui_updater(f"Rotating {'CCW' if direction else 'CW'} at {rpm} RPM...") #UIUIUIUIUIUIUIUIUIUIIUIUIUIUIUIUUUIUIUIUI
            
>>>>>>> 13c4082e4d72a76be7d0f0abd03d5120e38fe2b8
            step_delay = self.rpm_to_delay / rpm
            self.direction_set(direction)
            
            while self.running:
                self.pulse()
                time.sleep(step_delay)
                if not self.open_gui:
                    break

        except ljm.LJMError as err: #UIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIU
<<<<<<< HEAD
            self.running = False
            print(err)
=======
            self.gui_updater(f"LabJack Error: {err}")
            self.running = False
>>>>>>> 13c4082e4d72a76be7d0f0abd03d5120e38fe2b8

    def stop_rotation(self):
        self.running = False
        self.straight_up_rotating_it_and_by_it_I_mean_my_linear_acuator = False
        #self.gui_updater("Idle") #UIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIU

    #def gui_updater(self, text): #UIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUI
        #if self.open_gui:
            #try:
                #self.status_lbl2.config(text=text)
                #self.root.update()
            #except tk.TclError: #UIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUIUI
                #self.open_gui = False

<<<<<<< HEAD
    def on_close(self):
        self.cleanup()
=======
    def window_popup(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        self.cleanup()
        self.root.destroy()
>>>>>>> 13c4082e4d72a76be7d0f0abd03d5120e38fe2b8

    def cleanup(self, port=None):
        port = port
        self.open_gui = False
        self.stop_rotation()
        try:
            self.ser_in = serial.Serial(port=f'{str(port)}', baudrate=9600, bytesize=7, parity='E', stopbits=1, timeout=1)
            self.ser_connected = True
            time.sleep(0.1)

            if self.ser_connected == True:
<<<<<<< HEAD
                self.ser_in.close()
=======
                self.stop()
                self.ser_in.close()
                self.root.destroy()
>>>>>>> 13c4082e4d72a76be7d0f0abd03d5120e38fe2b8

        except serial.SerialException as e:
            self.ser_in = None # Ensure ser_in is None if connection fails
            self.ser_connected = False
<<<<<<< HEAD
=======
            self.root.destroy()
>>>>>>> 13c4082e4d72a76be7d0f0abd03d5120e38fe2b8

        if self.handle:
            ljm.close(self.handle)

    #def show_error_message(self, message):
        #error_window = tk.Toplevel(self.root)
        #error_window.title("Error")
        #ttk.Label(error_window, text=message).pack(padx=20, pady=20)
        #ttk.Button(error_window, text="OK", command=error_window.destroy).pack(pady=10)