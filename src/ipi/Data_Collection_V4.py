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

location = os.path.dirname(os.path.abspath(__name__))

running = False
file_path = None 

rm = pyvisa.ResourceManager()
scope = rm.open_resource("USB0::0xF4EC::0x100C::SDS2HBAX900425::INSTR")

    #-----------------------------------
    # Data Collection
    # ===========================
    # Configure Oscilloscope for Continuous Data Collection
    # ===========================
def configure_oscilloscope(channel):
        scope.write(f":CHAN{channel}:DISP ON")  # Enable selected channel

        # Disable other channels
        for i in range(1, 5):
            if i != int(channel):
                scope.write(f":CHAN{i}:DISP OFF")

        # Real-time continuous data acquisition
        scope.write(":ACQ:MODE RT")  # Real-time acquisition
        scope.write(":ACQ:SRAT 2E9")  # 2 GSa/s Sampling Rate
        scope.write(":ACQ:MDEP 10M")  # Match screen memory depth (10Mpts)  
        scope.write(":TIM:SCAL 5e-6")  # Match display (5us per division)

        # Trigger settings
        scope.write(":TRIG:MODE EDGE")  
        scope.write(":TRIG:EDGE:SLOPE POS")  
        scope.write(":TRIG:LEVEL 1.00")  
        scope.write(":TRIG:COUP DC")  # DC coupling as shown on screen  

        # Enable continuous data collection
        scope.write(":WAV:MODE RAW")  # Raw waveform mode
        scope.write(":WAV:FORMAT WORD")  # 16-bit resolution
        scope.write(":WAV:DATA:BYTEORDER LSBFirst")  
        scope.write(":WAV:POIN:MODE NORMAL")  # Continuous waveform transfer mode
        scope.write(":WAV:POIN 1000000")  # Stream up to 1M points continuously

        print("OK")

    # ===========================
    # Data Collection Variables
    # ===========================
 # Initially None, to enforce selection

    # ===========================
    # Continuous Data Collection Function (No Stopping)
    # ===========================
def collect_raw_data():
        running = True

        with open(file_path, "wb") as file:
            while running:
                try:
                    scope.write(":WAV:DATA?")
                    raw_data = scope.read_raw()

                    # Append new data to the file (continuous logging)
                    file.write(raw_data)

                    #print(f"Captured {len(raw_data)} bytes of raw data.")


                except Exception as e:
                    messagebox.showerror(f"Error",f"Error collecting raw data: {e}")

                time.sleep(0.0001)  # Short delay to maintain continuous streaming


    # ===========================
    # Start and Stop Functions
    # ===========================
def start_collection():

        if running:
            messagebox.showwarning("Warning", "Data collection is already running!")
            return
    
        ##
        configure_oscilloscope("1")
        running = True
        thread = threading.Thread(target=collect_raw_data, daemon=True)
        thread.start()
        thrread = threading.Thread(target=main, daemon=True)
        thrread.start()


        #messagebox.showinfo("Started", f"Continuous data collection started on CHAN{self.channel_var.get()}!")
def stop_collection():
        running = False

    # ===========================
    # File Path Selection
    # ===========================

def load_and_plot_threshold_label_multi(file_paths,
                                            threshold=1,  
                                            min_width_sec=7e-9,  
                                            baseline_value=0.8,
                                            resistor_ohms=50,          
                                            area_mm2=19.7/4,             
                                            responsivity_A_per_W=0.22, 
                                            rep_rate_hz=100,           
                                            exposure_time_s_per_file=10):
        """
        Process multiple .bin files independently, compute AUC and dose for each pulse per file,
        and provide individual summaries, including pulse collection rate.
        
        Args:
            file_paths (list): List of paths to .bin files
            threshold (float): Voltage threshold for pulse detection
            min_width_sec (float): Minimum pulse width in seconds
            baseline_value (float): Baseline voltage value
            resistor_ohms (float): Resistor value in ohms
            area_mm2 (float): Area in mm^2
            responsivity_A_per_W (float): Photodiode responsivity in A/W
            rep_rate_hz (float): Repetition rate in Hz
            exposure_time_s_per_file (float): Exposure time per file in seconds
        """
        try:
            fs = 2e9  # Sampling rate: 2 GSa/s
            area_cm2 = area_mm2 / 100.0
            total_pulses_per_file = rep_rate_hz * exposure_time_s_per_file  # e.g., 9000

            # Process each file independently
            #for file_idx, file_path in enumerate(file_paths):
            #    print(f"Processing file {file_idx + 1}/{len(file_paths)}: {file_path}")
            #    current_file_pos = len(file_paths) - 1
            #    file = file_paths[current_file_pos]

                    # 1. Load and scale data
            with open(file_paths, "rb") as f:
                raw_data = f.read()
                #print(file_paths)


            excess = len(raw_data) % 2
            if excess:
                raw_data = raw_data[:-excess]
                #print(f"Trimmed {excess} excess bytes from {self.file_path}")

            raw_values = np.frombuffer(raw_data, dtype=np.uint16)
            voltage_data = ((raw_values - 32768) / 32768) * 0.8  # -8 to 8 V range
        
            if voltage_data.size == 0:
                raise ValueError("Voltage data is empty. Cannot compute minimum or plot.")

            # 2. Create time axis for this file
            total_samples = len(voltage_data)
            total_time = total_samples/fs
            time_axis = np.linspace(0, total_time, total_samples)

             # 3. Threshold and label pulses
            above_threshold = (voltage_data > threshold)
            labeled_array, num_labels = label(above_threshold)

                # 4. Filter by minimum width
            min_width_samples = int(min_width_sec * fs)
            keep_mask = np.zeros_like(voltage_data, dtype=bool)
            pulse_aucs = []

            for label_idx in range(1, num_labels + 1):
                region_mask = (labeled_array == label_idx)
                region_size = np.sum(region_mask)
                if region_size >= min_width_samples:
                    keep_mask[region_mask] = True
                    pulse_voltage = voltage_data[region_mask]
                    pulse_time = time_axis[region_mask]
                    auc_volt_sec = np.trapezoid(pulse_voltage, x=pulse_time)
                    pulse_aucs.append((label_idx, auc_volt_sec))

            # 5. Build filtered waveform (no plotting, just for calculation)
            voltage_filtered = np.where(keep_mask, voltage_data, baseline_value)
            # 6. Calculate dose for each pulse
            pulse_doses = []
            for pulse_idx, auc_volt_sec in pulse_aucs:
                Q_coulombs = auc_volt_sec / resistor_ohms
                E_joules = Q_coulombs / responsivity_A_per_W
                E_mJ = E_joules * 1000.0
                dose_per_pulse_mJ_cm2 = E_mJ / area_cm2
                if dose_per_pulse_mJ_cm2 >= 0:
                    pulse_doses.append((pulse_idx, dose_per_pulse_mJ_cm2))
                else:
                    messagebox.showwarning(f"Warning", "Negative dose for pulse {pulse_idx} in file {file_idx} ({dose_per_pulse_mJ_cm2:.3e} mJ/cm²)")

                # 7. Calculate metrics for this file
            num_pulses = len(pulse_doses)
            collection_rate = (num_pulses / total_pulses_per_file) * 100 if total_pulses_per_file > 0 else 0
            avg_single_shot_dose = np.mean([dose for _, dose in pulse_doses]) if pulse_doses else 0
            total_dose = avg_single_shot_dose * total_pulses_per_file  # Extrapolated to 9000 pulses
            dose_rate = total_dose / exposure_time_s_per_file if exposure_time_s_per_file > 0 else 0

            #8. plot the plot v1 (matplotlib)
                #fig, ax = plt.subplots()
                #ax.clear()
                #ax.set_title("Voltage vs. Time Graph")
                #ax.plot(time_axis, voltage_data, label="Original")
                #ax.plot(time_axis, voltage_filtered, label="Filtered")
                #ax.set_xlabel("time (s)")
                #ax.set_ylim(min(voltage_data.min(), voltage_filtered.min()) - 0.1,
                #            max(voltage_data.max(), voltage_filtered.max()) + 0.1)
                #ax.set_xlim(0, exposure_time_s_per_file)

                #ax.set_ylabel("Voltage (V)")
                #ax.legend()

                #canvas = FigureCanvasTkAgg(fig, master=root)
                #canvas.draw()
                #canvas.get_tk_widget().pack(pady = 10)
            today = date.today()
            #9. update the UI
 #########################################################################           
            # Assuming these variables are already defined:
            # self.location, exposure_time_s_per_file, num_pulses, collection_rate, avg_single_shot_dose, rep_rate_hz, total_pulses_per_file, total_dose, dose_rate

            today = date.today().strftime("%Y-%m-%d")

            folder_path2 = os.path.join(location, "Exposure_Results", today)

            os.makedirs(folder_path2, exist_ok=True)

            # Pattern to match files like "2025-08-07_S1_10s.txt"
            pattern = re.compile(rf"{today}_S(\d+)_\d+s\.txt")

            # Get existing sequence numbers
            existing_files = os.listdir(folder_path2)
            sequence_numbers = [
                int(match.group(1))
                for filename in existing_files
                if (match := pattern.match(filename))
            ]

            # Determine next sequence number
            next_seq = max(sequence_numbers, default=0) + 1

            # Create filename
            filename = f"{today}_S{next_seq}_{int(exposure_time_s_per_file)}s.txt" 
##########################################################################################
            with open (f"{folder_path2}\{filename}", "w") as output:
                output.write(f"Total number of pulses: {num_pulses}\n"
                                    f"Collection Rate: {collection_rate:.1f}%\n"
                                    f"Average Single-Shot Dose: {avg_single_shot_dose:.3e} mJ/cm²\n"
                                    f"Total exposure time: {exposure_time_s_per_file} s\n"
                                    f"Total pulses at {rep_rate_hz} Hz: {total_pulses_per_file}\n"
                                    f"Total Dose: {total_dose:.3e} mJ/cm²\n"
                                    f"Dose Rate: {dose_rate:.3e} mJ/cm²/s")

                #8. plot thee plot v2 (plotly)
            if not running:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=time_axis, y=voltage_data, mode='lines', name='Original Waveform', line=dict(color='blue'))) 
                fig.add_trace(go.Scatter(x=time_axis, y=voltage_filtered, mode='lines', name='Filtered Waveform', line=dict(color='red'))) 
                fig.update_layout( title=f"Oscilloscope Waveform: {os.path.basename(file_path)}", xaxis_title="Time (s)", yaxis_title="Voltage (V)", yaxis_range=[min(voltage_data.min(), -0.5), max(voltage_data.max(), 0.5) + 0.5], template="plotly_white", legend_title_text="Waveform Type" ) 
                fig.show()

        except Exception as e:
            messagebox.showerror(f"Error",f"Error processing files: {e}")

   
def main():
        
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

            # Run the processing function
            load_and_plot_threshold_label_multi(
                file_paths=file_path,
                threshold=1,
                min_width_sec=7e-9,
                baseline_value=0.8,
                resistor_ohms=50,
                area_mm2=19.7/4,
                responsivity_A_per_W=0.22,
                rep_rate_hz=100,
                exposure_time_s_per_file= total_t
            )
