# Data Collection (USB)
import pyvisa
import numpy as np
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk  # Modern UI styling  
from scipy.ndimage import label
import os
import argparse
import plotly.graph_objects as go
import time as time
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from tkhtmlview import HTMLLabel
import plotly.graph_objects as go
import plotly.io as pio
from datetime import date
import re
import pyvisa
import time
import signal
import sys

# Register signal handlers
# signal.signal(signal.SIGINT, handle_exit)   # Ctrl+C
# signal.signal(signal.SIGTERM, handle_exit)  # External kill

TIMEBASE = 2*10^-3
TRIG = 8*10^-3
SAMPLE_RATE = 50000000
POINTS=1000000



rm = pyvisa.ResourceManager()
scope = rm.open_resource("USB0::0xF4EC::0x100C::SDS2HBAX900425::INSTR")

def configure_oscilloscope():
        scope.write(f":CHAN{1}:VIS ON")  # Enable selected channel
        scope.write(f":CHAN{2}:VIS ON")  # Enable selected channel
        scope.write(f":CHAN{3}:VIS ON")  # Enable selected channel
        scope.write(f":CHAN{4}:VIS ON")  # Enable selected channel

        # Disable other channels

        # Real-time continuous data acquisition
        scope.write(":ACQ:MODE RT")         # Real-time acquisition
        scope.write(":ACQ:SRAT 50E6")      # 200 MSa/s Sampling Rate
        scope.write(":ACQ:MDEP 1M")        # Match screen memory depth (10Mpts)  
        scope.write(":TIM:SCAL 2e-3")       # 5ms per division
        scope.write(":TIM:DEL 8e-3")       # 5ms per division

        # Trigger settings
        scope.write(":TRIG:MODE NORM")  
        scope.write(":TRIG:TYPE EDGE")  
        scope.write(":TRIG:EDGE:SLOP RIS")  
        scope.write(":TRIG:EDGE:LEV 3.00")  
        scope.write(":TRIG:COUP DC")  # DC coupling as shown on screen  
        scope.write(":TRIG:EDGE:SOUR C3")  # DC coupling as shown on screen  

        # Enable continuous data collection
        scope.write(":WAV:MODE RAW")  # Raw waveform mode
        scope.write(":WAV:FORMAT BYTE")  # 16-bit resolution
        scope.write(":WAV:DATA:BYTEORDER LSBFirst")  
        scope.write(":WAV:POIN:MODE NORMAL")  # Continuous waveform transfer mode
        scope.write(":WAV:POIN 1000000")  # Stream up to 1M points continuously
        print("OK")

def index_to_secs(index):
     return index / SAMPLE_RATE

def collect_raw_data():
    scope.write(":WAVeform:FORMat BYTE")
    scope.write(":WAVeform:WIDTh BYTE")
    scope.write(":WAVeform:STARt 1")
    scope.write(":WAVeform:POINt 0")
    scope.write(":WAVeform:SOURce C3")

    xinc  = float(scope.query(":WAVeform:XINCrement?"))
    xorig = float(scope.query(":WAVeform:XORigin?"))
    xref  = float(scope.query(":WAVeform:XREFerence?"))
    yinc  = float(scope.query(":WAVeform:YINCrement?"))
    yorig = float(scope.query(":WAVeform:YORigin?"))
    yref  = float(scope.query(":WAVeform:YREFerence?"))
    #raw_data = scope.read_raw()

    raw_values = np.asarray(
        scope.query_binary_values(":WAVeform:DATA?", datatype='B',
                                  container=list, expect_termination=True,
                                  chunk_size=1024*1024),
        dtype=np.uint8
    )
    voltage_data = ((raw_values - 128) / 128)
    print(voltage_data[199000:200000])
    print(raw_values[199000:200000])

    index = np.argmax(voltage_data > 3.0)

    print (np.min(voltage_data))
    print (np.max(voltage_data))

    print (index)

    #raw_values = np.frombuffer(raw_data, dtype=np.uint16)
    # Append new data to the file (continuous logging)

    #print(f"Captured {len(raw_data)} bytes of raw data.")




def main():
        running = True
        #print("its doing the thing")
        last_time = time.time()
        t=0
        while running:
            #print("still doing the thing")
            current_time = time.time()
            dt = current_time - last_time
            last_time = current_time
            t += dt

        else:
            total_t = t
            """Main function to parse arguments and run the processing."""
#REMEMBER TO CHANGE THE FILEPATHS
configure_oscilloscope()
collect_raw_data()
