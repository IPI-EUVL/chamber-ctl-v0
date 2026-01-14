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

_phase_shift =  np.pi * 9/8
_steps_per_rev = 200
_handle = None 
_microsteps = 16 #If the number of microsteps is changed, the DIP switches on the drivers must be set according to datasheet
_rpm_to_delay = 60/(_steps_per_rev*_microsteps)
_running = False
_straight_up_rotating_it_and_by_it_I_mean_my_linear_acuator = False
_open_gui = True
_ser_in = None
_ser_connected = False
_directional = "cw"
_is_in_or_out = "in"
_selected_speed = 300 #change to 300 maybe ?(previous speed 500)
_rpmset = 1

def setup_visualization(framing, _offset):
        # Parameters for target      

        _canvas = tk.Canvas(framing, width=500, height=250, bg="#0E1116", highlightthickness=5, highlightbackground="#2A2F3A")
        _canvas.grid(row=2, column=0, columnspan=2, padx=10, pady=10)  

        _canvas_width = float(_canvas['width'])
        _canvas_height = float(_canvas['height'])

        _target_lenght = _canvas_width * 0.17
        _target_width = _canvas_height * 0.1
        _target_ycenter = _canvas_height/2
        _target_xcenter = _canvas_width * 0.5 - _offset 

        #parameters for holder
        _holder_lenght = _canvas_width - (_target_xcenter + _target_lenght/2)
        _holder_width = _target_width * 2
        _holder_ycenter = _canvas_height/2
        _holder_xcenter = _target_xcenter + _target_lenght/2 + _holder_lenght/2

        #parameters for laser
        _laser_lenght = _canvas_height/2
        _laser_width = 5
        _laser_ycenter = _canvas_height * 3/4 + _target_width/2
        _laser_xcenter = _canvas_width/2 - _target_lenght/2 -5

        # Drawing coordinates for target
        _x1 = _target_xcenter - _target_lenght / 2
        _x2 = _target_xcenter + _target_lenght / 2        
        _y1 = _target_ycenter - _target_width / 2
        _y2 = _target_ycenter + _target_width / 2

        # Drawing coordinates for holder
        _hx1 = _holder_xcenter - _holder_lenght / 2
        _hx2 = _holder_xcenter + _holder_lenght / 2        
        _hy1 = _holder_ycenter - _holder_width / 2
        _hy2 = _holder_ycenter + _holder_width / 2

        #Drawing coordinates for laser
        _lx1 = _laser_xcenter - _laser_width / 2
        _lx2 = _laser_xcenter + _laser_width / 2        
        _ly1 = _laser_ycenter + _laser_lenght / 2
        _ly2 = _laser_ycenter - _laser_lenght / 2
        
        #impact
        _impactl = 10
        _impact_angle = np.radians(50)
        _x1impact = _lx1
        _x2impact = _x1impact - _impactl * np.cos(_impact_angle)
        _y1impact = _ly2
        _y2impact = _y1impact + _impactl * np.sin(_impact_angle)

        #line 7 
        _line7x1 = _x1
        _line7y1 = _target_ycenter 
        _line7x2 = _x2
        _line7y2 = _target_ycenter - (_target_width / 2) * (np.sin(_phase_shift))

        # Line 8
        _line8x1 = _x1
        _line8y1 = _target_ycenter - (_target_width / 2)
        _line8x2 = _x2
        _line8y2 = _target_ycenter + (_target_width / 2) * (np.cos(_phase_shift))/2

        # Line 9
        _line9x1 = _x1
        _line9y1 = _target_ycenter + (_target_width / 2) * (np.sin(np.pi/4))
        _line9x2 = _x2
        _line9y2 = _target_ycenter - (_target_width / 2) * (np.sin(_phase_shift + np.pi/4))


        # Motion stuff
        _moving = False

        # Drawing 
        _target = _canvas.create_polygon(_x1, _y2, _x1 - _target_lenght * 0.07, _target_ycenter, _x1, _y1, _x2, _y1, _x2, _y2, fill = "lightgrey", width = 3)
        _line7 = _canvas.create_line(_line7x1, _line7y1, _line7x2, _line7y2, fill="#4FC3F7", width=3)
        _line8 = _canvas.create_line(_line8x1, _line8y1, _line8x2, _line8y2, fill="#4FC3F7", width=3)
        _line9 = _canvas.create_line(_line9x1, _line9y1, _line9x2, _line9y2, fill="#4FC3F7", width=3)
        _target = _canvas.create_polygon(_x1, _y2, _x1 - _target_lenght * 0.07, _target_ycenter, _x1, _y1, _x2, _y1, _x2, _y2, fill = "", outline="#3A3F4B", width = 3)
        _holder = _canvas.create_rectangle(_hx1, _hy1, _hx2, _hy2, fill="#2A2F3A", outline="white", width=2)
        _laser = _canvas.create_rectangle(_lx1, _ly1, _lx2, 0, fill="darkred", outline="red", width=2)     

        if _lx1 >= _x1:
            _canvas.itemconfig(_laser, state = 'hidden')
            _canvas.create_rectangle(_lx1, _ly1, _lx2, _ly2, fill="darkred", outline="red", width=3)
            _line1 = _canvas.create_line(_x1impact, _y1impact, _x2impact, _y2impact, fill = "red", width = 5)
            _line2 = _canvas.create_line(_lx2, _y1impact, _lx2 + _impactl * np.cos(_impact_angle), _y2impact, fill = "red", width = 5)
        
        #GUI responsivity
        framing.columnconfigure(1, weight=1)
        framing.grid_columnconfigure(0, weight=1)
        framing.grid_columnconfigure(1, weight=1)
        _canvas.columnconfigure(1, weight = 1)
        framing.update()

        return _canvas, _target_xcenter

class visualization:
        
        def __init__(self, _canvas, _animated, _rpmset, _newrate, _root, _phase_shift, _target_xcenter):
            self.canvas = _canvas
            self.animated = _animated
            self.rpmset = _rpmset
            self.newrate = _newrate
            self.root = _root
            self.phase_shift = _phase_shift
            self.target_xcenter = _target_xcenter
            self._last_time = time.time()

        def go(self):
            
            if not self.animated:
                self.impactl = 0
                self.new_rot_rate = 0
                update_coords(self.canvas, self.target_xcenter, self.impactl, self.new_rot_rate, self.phase_shift)
                return
            
            self.impactl = np.absolute(10 + 5 * np.sin(np.radians(3000*time.time())))
            self.new_rot_rate = float(self.rpmset) * ((2*np.pi)/60)

            self.current_time = time.time()
            self.dt = self.current_time - self._last_time
            self._last_time = self.current_time


            self.current_rate = self.newrate
                #fix
            self.target_xcenter = self.target_xcenter + self.current_rate*self.dt
                
            update_coords(self.canvas, self.target_xcenter, self.impactl, self.new_rot_rate, self.phase_shift)
            self.root.update_idletasks()
            self.root.update()
            self.root.after(2, self.go)

def update_coords(_canvas, _target_xcenter, _impactl, _new_rot_rate, _phase_shift):

        _canvas.delete("all")
        _canvas_width = float(_canvas['width'])
        _canvas_height = float(_canvas['height'])
        # Parameters for target
        _target_lenght = _canvas_width * 0.17
        _target_width = _canvas_height * 0.1
        _target_ycenter = _canvas_height/2

        #parameters for holder
        _holder_lenght = _canvas_width - (_target_xcenter + _target_lenght/2)
        _holder_width = _target_width * 2
        _holder_ycenter = _canvas_height/2
        _holder_xcenter = _target_xcenter + _target_lenght/2 + _holder_lenght/2

        #parameters for laser
        _laser_lenght = _canvas_height/2
        _laser_width = 5
        _laser_ycenter = _canvas_height * 3/4 + _target_width/2
        _laser_xcenter = _canvas_width/2 - _target_lenght/2 - 5

        # Drawing coordinates for targetu
        _x1 = _target_xcenter - _target_lenght / 2
        _x2 = _target_xcenter + _target_lenght / 2        
        _y1 = _target_ycenter - _target_width / 2
        _y2 = _target_ycenter + _target_width / 2

        # Drawing coordinates for holder
        _hx1 = _holder_xcenter - _holder_lenght / 2
        _hx2 = _holder_xcenter + _holder_lenght / 2        
        _hy1 = _holder_ycenter - _holder_width / 2
        _hy2 = _holder_ycenter + _holder_width / 2

        #Drawing coordinates for laser
        _lx1 = _laser_xcenter - _laser_width / 2
        _lx2 = _laser_xcenter + _laser_width / 2        
        _ly1 = _laser_ycenter + _laser_lenght / 2
        _ly2 = _laser_ycenter - _laser_lenght / 2
        
        #impact
        _impact_angle = np.radians(50)
        _x1impact = _lx1
        _x2impact = _x1impact - _impactl * np.cos(_impact_angle)
        _y1impact = _ly2
        _y2impact = _y1impact + _impactl * np.sin(_impact_angle)



        #line 7 
        _line7x1 = _x1
        _line7y1 = _target_ycenter + (_target_width / 2) * (np.sin((_new_rot_rate * time.time())))
        _line7x2 = _x2
        _line7y2 = _target_ycenter - (_target_width / 2) * (np.sin((_new_rot_rate * time.time())+_phase_shift))
        # Line 8
        _line8x1 = _x1
        _line8y1 = _target_ycenter + (_target_width / 2) * (np.cos((_new_rot_rate * time.time())))
        _line8x2 = _x2
        _line8y2 = _target_ycenter - (_target_width / 2) * (np.cos((_new_rot_rate * time.time())+_phase_shift))

        # Line 9
        _line9x1 = _x1
        _line9y1 = _target_ycenter + (_target_width / 2) * (np.sin((_new_rot_rate * time.time()) + np.pi/4))
        _line9x2 = _x2
        _line9y2 = _target_ycenter - (_target_width / 2) * (np.sin((_new_rot_rate * time.time()) + _phase_shift + np.pi/4))

        # rectangle cover
        _rx1 = _target_xcenter - _target_lenght / 2
        _rx2 = _target_xcenter + _target_lenght / 2 
        _ry1 = _target_ycenter + (_target_width / 2)* (np.sin((_new_rot_rate * time.time())))
        _ry2 = _target_ycenter + _target_width / 2
        
        # Drawing 
        _target = _canvas.create_polygon(_x1, _y2, _x1 - _target_lenght * 0.07, _target_ycenter, _x1, _y1, _x2, _y1, _x2, _y2, fill = "lightgrey", width = 3)

        _line7 = _canvas.create_line(_line7x1, _line7y1, _line7x2, _line7y2, fill="#4FC3F7", width=3)
        _line8 = _canvas.create_line(_line8x1, _line8y1, _line8x2, _line8y2, fill="#4FC3F7", width=3)
        _line9 = _canvas.create_line(_line9x1, _line9y1, _line9x2, _line9y2, fill="#4FC3F7", width=3)
        _cover = _canvas.create_rectangle(_rx1, _ry1, _rx2, _ry2, fill="lightgrey", outline = "lightgrey", width=2)

        _target = _canvas.create_polygon(_x1, _y2, _x1 - _target_lenght * 0.07, _target_ycenter, _x1, _y1, _x2, _y1, _x2, _y2, fill = "", outline="#3A3F4B", width = 3)
        _holder = _canvas.create_rectangle(_hx1, _hy1, _hx2, _hy2, fill="#2A2F3A", outline="white", width=2)
        _laser = _canvas.create_rectangle(_lx1, _ly1, _lx2, 0, fill="darkred", outline="red", width=2)     


        if _lx2 >= _x1:
            _canvas.itemconfig(_laser, state = 'hidden')
            _canvas.create_rectangle(_lx1, _ly1, _lx2, _ly2, fill="darkred", outline="red", width=3)
            _line1 = _canvas.create_line(_x1impact, _y1impact, _x2impact, _y2impact, fill = "red", width = 5)
            _line2 = _canvas.create_line(_lx2, _y1impact, _lx2 + _impactl * np.cos(_impact_angle), _y2impact, fill = "red", width = 5)
        
        _canvas.update()
