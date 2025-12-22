import sys
import os
import time
import math
import datetime
import matplotlib.pyplot as plt
import numpy as np
import csv
import plotly.graph_objects as go
import re

NAN = float('nan')

CHOPPER_BINNING = 2
TARGET_BINNING = 5

RESISTOR_OHMS = 50
RESP_A_PER_W = 0.22
AREA_CM2 = (19.7/4) / 100.0

def get_data(filename):
    file = open(filename)
    reader = csv.reader(file)
    value_labels = next(reader)
    values = []

    for line in reader:
        data = []
        for d in line:
            data.append(float(d))
        values.append(data)

    labels_dict = dict()
    for i in range(len(value_labels)):
        labels_dict[value_labels[i]] = i

    return labels_dict, np.array(values)

def time_based_average(values, window_size):
    begin_time = values[0, 0]
    avg = 0.0
    samples = 0

    window_times = []
    window_averages = []
    for (time, vpp) in values:
        #print(time - begin_time)
        #print(avg / (time - begin_time))
        
        if vpp != float('nan'):
            avg += vpp
            samples+=1

        if (time - begin_time) > window_size:
            window_times.append(begin_time)
            window_averages.append(avg / samples)

            begin_time = time
            avg = 0
            samples = 0

    return (window_times, window_averages)

def rolling_average(values, window_size):
    s_begin_time = values[0, 0]
    avg = 0.0
    samples = 0

    window_times = []
    window_averages = []

    cur_vals = []
    for (time, vpp) in values:
        #print(time - begin_time)
        #print(avg / (time - begin_time))        
        if vpp != float('nan'):
            cur_vals.append((time, vpp))

        avg_v = 0
        begin_time = max(time - window_size, s_begin_time)
        last_time = begin_time

        for (pt, pv) in cur_vals:
            if (time - window_size) > pt:
                cur_vals.remove((pt, pv))
                continue
            
            dt = pt - last_time
            last_time = pt
            avg_v += pv * dt
        
        t_len = last_time - begin_time
        if t_len == 0:
            continue

        window_averages.append(avg_v / t_len)
        window_times.append(time)

    return (window_times, window_averages)

SAVE_PATH = os.path.join(os.environ["EUVL_PATH"], "datasets")

def main():
    #substitute -l with latest data, if unspecified use latest eposure and latest sapshot
    exposures = []
    if len(sys.argv) >= 2: # if specified
        for arg in sys.argv[1:]:
            exposures.append(arg)
    else:
        exposures.append(sorted(os.listdir(SAVE_PATH), key=lambda x: os.path.getctime(os.path.join(SAVE_PATH, x)))[-1])
    
    pulses = []
    chopper = []
    start_time = 0

    for exposure in exposures:
        print(f"Processing: {exposure}")
        foldername = os.path.join(SAVE_PATH, f"{exposure}")

        existing_files = os.listdir(foldername)

        pattern = re.compile(r"snapshot_(\d+).csv")

        nums = [
                int(match.group(1))
                for filename in existing_files
                if (match := pattern.match(filename))
                    ]
        exp_begin_time = 0

        for i in range(len(nums)):
            pulses_fn = os.path.join(foldername, f"snapshot_{sorted(nums)[i]}.csv")
            nums_fn = os.path.join(foldername, f"pulses_{sorted(nums)[i]}.dat")
            chopper_fn = os.path.join(foldername, f"chopper_{sorted(nums)[i]}.csv")

            print(f"Processing: {pulses_fn} ({i + 1} / {len(nums)})")
            labels, values = get_data(pulses_fn)


            increment = 0

            nums_file = open(nums_fn)

            for line in nums_file:
                end_index = 0
                if line.find(','):
                    end_index = int(line.strip().split(',')[0])

                    if exp_begin_time == 0:
                        exp_begin_time = float(line.strip().split(',')[1])
                else:
                    end_index = int(line.strip())

                if increment == 0 and end_index != 0:
                    increment = end_index
                    break

            nums_file.close()
            nums_file = open(nums_fn)

            for line in nums_file:
                start_index = 0
                if line.find(','):
                    start_index = int(line.strip().split(',')[0])
                else:
                    start_index = int(line.strip())

                end_index = start_index + increment

                if line.find(','):
                    pulses.append(([(float(line.strip().split(',')[1]) - exp_begin_time)], values[start_index:end_index, labels['v']]))
                else:
                    pulsetimes = np.array(values[start_index:end_index, labels['t']])
                    pulsetimes += start_time

                    pulses.append((pulsetimes, values[start_index:end_index, labels['v']]))

            try:
                chopper_file = open(chopper_fn)
                for line in chopper_file:
                    if line.startswith("t"):
                        continue
                    #print(line.strip().split(','))
                    (t, phase, sync) = line.strip().split(',')
                    chopper.append([float(t) / 1000000000.0, float(phase)])

                start_time += values[-1, labels['t']]
                chopper_file.close()
            except FileNotFoundError:
                pass

    pulse_doses = []
    print(pulses[1][0])
    pulse_time = pulses[1][0][0] - pulses[0][0][0]
    print(pulse_time)

    SAMPLE_dT = 10 / 1e9
    pulse_int_time = len(pulses[0][1]) * SAMPLE_dT
    print("Pulse num:", len(pulses) / 100)
    print("Area:", AREA_CM2)

    for times, pulse in pulses:
        sum = np.trapezoid(pulse) / len(pulse)
        auc_volt_sec = sum * pulse_int_time
        print(f"nWeber: {auc_volt_sec * 1e9}")
        Q_coulombs = auc_volt_sec / RESISTOR_OHMS
        E_joules = Q_coulombs / RESP_A_PER_W
        E_mJ = E_joules * 1000.0
        dose_per_pulse_mJ_cm2 = E_mJ / AREA_CM2
        #print(f"uJ/cm2: {dose_per_pulse_mJ_cm2 * 1e3}")
        if dose_per_pulse_mJ_cm2 >= 0:
            pulse_doses.append((times[0], dose_per_pulse_mJ_cm2))
        else:
            print(f"Negative dose for pulse {times[0]} : ({dose_per_pulse_mJ_cm2:.3e} mJ/cm²)")

    pulse_doses = np.array(pulse_doses)
    #print(pulse_doses)
    #print(len(pulse_doses))
    total = np.sum(pulse_doses[:, 1])
    print(f"Total dose = {total} mJ")

        # 7. Calculate metrics for this file
    num_pulses = len(pulse_doses)

    peaks = []
    values = []
    ptimes = [] 

    for times, pulse in pulses:
        peak = np.max(pulse)
        peaks.append([times[0], peak])

    peaks = np.array(peaks)

    #print(peaks)
    powers = []

    cropped_peaks = np.empty((0, 2))
    for i in range(0, len(peaks), 1000):
        threshold_v= np.average(peaks[i: i + 1000, 1])
        mask = peaks[i: i + 1000, 1] >= threshold_v
        cropped = peaks[i:i + 1000][mask]

        cropped_peaks = np.vstack((cropped_peaks, cropped))


    print(len(cropped_peaks))
    print(len(peaks))
    #print(chopper)

    for (peaktime, peakvoltage) in peaks:
        power = peakvoltage * (peakvoltage / 50.0)
        powers.append([peaktime, power])

    powers = np.array(powers)

    wtimes, averages = rolling_average(powers, 5)

    fig = go.Figure(layout={
        'yaxis': {
            'title': 'Volts',
            'color': 'black'},
        'yaxis2': {
            'title': 'Watts',
            'overlaying': 'y',
            'side': 'right',
            'color': 'red'
        },
        'yaxis3': {
            'title': 'Degrees',
            'overlaying': 'y',
            'side': 'right',
            'color': 'purple'
        },
        'yaxis4': {
            'title': 'millijoules',
            'overlaying': 'y',
            'side': 'right',
            'color': 'orange'
        }
    })

    chopper = np.array(chopper)
    #fig.add_trace(go.Scatter(x=wtimes, y=averages, mode='lines', name='RMS', line=dict(color='red'))) 
    fig.add_trace(go.Scatter(yaxis='y', x=peaks[:, 0], y=peaks[:, 1], mode='lines', name='Peak V', line=dict(color='black'))) 
    fig.add_trace(go.Scatter(yaxis='y', x=cropped_peaks[:, 0], y=cropped_peaks[:, 1], mode='lines', name='Above average out of 1000', line=dict(color='red'))) 
    fig.add_trace(go.Scatter(yaxis='y2', x=powers[:, 0], y=powers[:, 1], mode='lines', name='PD Dissipated Power', line=dict(color='yellow'))) 
    fig.add_trace(go.Scatter(yaxis='y2', x=wtimes, y=averages, mode='lines', name='PD Dissipated Average Power over 30 sec average (WATTS)', line=dict(color='green'))) 
    fig.add_trace(go.Scatter(yaxis='y4', x=pulse_doses[:, 0], y=pulse_doses[:, 1], mode='lines', name='Dose', line=dict(color='red'))) 
    fig.update_layout( title=f"", xaxis_title="Time (s)", template="plotly_white", legend_title_text="Waveform Type" ) 
    fig.show()
    print(f"Exposure time {times[0]} : ({dose_per_pulse_mJ_cm2:.3e} mJ/cm²)")
    print(f"Total dose = {total} mJ")


if __name__ == "__main__":
    main()
    