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
                print(exp_begin_time)
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

    for times, pulse in pulses:
        sum = np.sum(pulse)
        pulse_int_time = len(pulse) * SAMPLE_dT
        auc_volt_sec = sum * pulse_int_time
        Q_coulombs = auc_volt_sec / RESISTOR_OHMS
        E_joules = Q_coulombs / RESP_A_PER_W
        E_mJ = E_joules * 1000.0
        dose_per_pulse_mJ_cm2 = E_mJ / AREA_CM2
        if dose_per_pulse_mJ_cm2 >= 0:
            pulse_doses.append((times[0], dose_per_pulse_mJ_cm2))
        else:
            print(f"Negative dose for pulse {times[0]} in file ({dose_per_pulse_mJ_cm2:.3e} mJ/cm²)")

    pulse_doses = np.array(pulse_doses)
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

    chopper_acc = dict()

    corrections = []

    if len(chopper) == 0:
        print("No chopper data!")
        chopper.append([exp_begin_time, 0])

    chopper_index = 0
    #print(len(chopper))
    for (times, peak) in peaks:
        #print(f"{times}: using chopper @ {chopper[chopper_index][0]}")
        if chopper[chopper_index][0] < times and len(chopper) > chopper_index + 2:
            chopper_index += 1
        
        chopper_angle = chopper[chopper_index][1]

        chopper_angle = chopper_angle - chopper_angle % CHOPPER_BINNING


        if math.isnan(chopper_angle):
            continue

        if not chopper_angle in chopper_acc:
            chopper_acc[chopper_angle] = [0, 0]

        (acc, num) = chopper_acc[chopper_angle]

        chopper_acc[chopper_angle] = [acc + peak, num + 1]

    peaks = np.array(peaks)
    
    average = np.average(peaks[: ,1])
    attenuation = dict()

    for angle, (avg, samples) in chopper_acc.items():
        print(f"{angle}: {(avg / samples)} ({samples} samples)")

        attenuation[angle] = (avg / samples) / average

    print(f"Overall average: {average}")

    attenuation_s = sorted(attenuation.items(), key=lambda a: a[0])
    attenuation_graph = []

    for angle, att in attenuation_s:
        print(f"Attenuation @ {angle}: {math.log10(att)*10:.02f} dBV ({int(att*100)}%) (based on {chopper_acc[angle][1]} samples)")

        attenuation_graph.append([angle, att])

    chopper_index = 0
    #print(len(chopper))
    comp_peaks = []
    for (times, peak) in peaks:
        #print(f"{times}: using chopper @ {chopper[chopper_index][0]}")
        if chopper[chopper_index][0] < times and len(chopper) > chopper_index + 2:
            chopper_index += 1

        chopper_angle = chopper[chopper_index][1]
        chopper_angle = chopper_angle - chopper_angle % CHOPPER_BINNING

        if math.isnan(chopper_angle):
            continue

        if chopper_acc[chopper_angle][1] < 50:
            continue
        
        att = attenuation[chopper_angle]

        peak /= att
        comp_peaks.append([times, peak])

    comp_peaks = np.array(comp_peaks)
    # target comp
    target_acc = dict()

    #print(len(chopper))
    for (times, peak) in comp_peaks:
        #print(f"{times}: using chopper @ {chopper[chopper_index][0]}")
        target_angle = int((times % 60.0))

        target_angle = target_angle - target_angle % TARGET_BINNING

        if not target_angle in target_acc:
            target_acc[target_angle] = [0, 0]

        (acc, num) = target_acc[target_angle]

        target_acc[target_angle] = [acc + peak, num + 1]

    
    print(comp_peaks.shape)
    print(comp_peaks)
    print(peaks)
    comp_average = np.average(comp_peaks[: ,1])
    target_att= dict()

    for angle, (avg, samples) in target_acc.items():
        print(f"TARGET {angle}: {(avg / samples)} ({samples} samples)")

        target_att[angle] = (avg / samples) / comp_average

    tattenuation_s = sorted(target_att.items(), key=lambda a: a[0])
    tattenuation_graph = []

    for angle, att in tattenuation_s:
        print(f"Attenuation @ {angle}: {math.log10(att)*10:.02f} dBV ({int(att*100)}%) (based on {target_acc[angle][1]} samples)")

        tattenuation_graph.append([angle, att])

    print(f"Overall average: {comp_average}")

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

    powers_comp = []

    for (peaktime, peakvoltage) in comp_peaks:
        power = peakvoltage * (peakvoltage / 50.0)
        powers_comp.append([peaktime, power])

    powers_comp = np.array(powers_comp)

    tcomp_peaks = []
    for (times, peak) in comp_peaks:
        #print(f"{times}: using chopper @ {chopper[chopper_index][0]}")
        target_angle = int((times % 60.0))
        target_angle = target_angle - target_angle % TARGET_BINNING

        att = target_att[target_angle]

        peak /= att
        tcomp_peaks.append([times, peak])

    tcomp_peaks = np.array(tcomp_peaks)

    powers_comp_t = []

    for (peaktime, peakvoltage) in tcomp_peaks:
        power = peakvoltage * (peakvoltage / 50.0)
        powers_comp_t.append([peaktime, power])

    powers_comp_t = np.array(powers_comp_t)

    wtimes, averages = rolling_average(powers, 5)
    wtimes_c, averages_c = rolling_average(powers_comp, 30)
    wtimes_t, averages_t = rolling_average(powers_comp_t, 30)

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
    attenuation_graph = np.array(attenuation_graph)
    tattenuation_graph = np.array(tattenuation_graph)

    #fig.add_trace(go.Scatter(x=wtimes, y=averages, mode='lines', name='RMS', line=dict(color='red'))) 
    fig.add_trace(go.Scatter(yaxis='y', x=peaks[:, 0], y=peaks[:, 1], mode='lines', name='Peak V', line=dict(color='black'))) 
    fig.add_trace(go.Scatter(yaxis='y', x=cropped_peaks[:, 0], y=cropped_peaks[:, 1], mode='lines', name='Above average out of 1000', line=dict(color='red'))) 
    fig.add_trace(go.Scatter(yaxis='y', x=comp_peaks[:, 0], y=comp_peaks[:, 1], mode='lines', name='Chopper Compensated', line=dict(color='red'))) 
    fig.add_trace(go.Scatter(yaxis='y2', x=powers[:, 0], y=powers[:, 1], mode='lines', name='PD Dissipated Power', line=dict(color='yellow'))) 
    fig.add_trace(go.Scatter(yaxis='y2', x=powers_comp[:, 0], y=powers_comp[:, 1], mode='lines', name='PD Dissipated Power (Compensated)', line=dict(color='blue'))) 
    fig.add_trace(go.Scatter(yaxis='y2', x=wtimes, y=averages, mode='lines', name='PD Dissipated Average Power over 30 sec average (WATTS)', line=dict(color='green'))) 
    fig.add_trace(go.Scatter(yaxis='y2', x=wtimes_c, y=averages_c, mode='lines', name='PD Dissipated Average Power over 30 sec average (Comp)', line=dict(color='blue'))) 
    fig.add_trace(go.Scatter(yaxis='y2', x=wtimes_t, y=averages_t, mode='lines', name='PD Dissipated Average Power over 30 sec average (Comp)', line=dict(color='red'))) 
    fig.add_trace(go.Scatter(yaxis='y3', x=chopper[:, 0], y=chopper[:, 1], mode='lines', name='Chopper Phase (Degrees)', line=dict(color='green'))) 
    fig.add_trace(go.Scatter(yaxis='y4', x=pulse_doses[:, 0], y=pulse_doses[:, 1], mode='lines', name='Dose', line=dict(color='red'))) 
    fig.update_layout( title=f"", xaxis_title="Time (s)", template="plotly_white", legend_title_text="Waveform Type" ) 
    fig.show()

    fig2 = go.Figure()

    #fig.add_trace(go.Scatter(x=wtimes, y=averages, mode='lines', name='RMS', line=dict(color='red'))) 
    fig2.add_trace(go.Scatter(yaxis='y', x=attenuation_graph[:, 0], y=attenuation_graph[:, 1], mode='lines', name='Attenuation', line=dict(color='black'))) 
    fig2.add_trace(go.Scatter(yaxis='y', x=tattenuation_graph[:, 0], y=tattenuation_graph[:, 1], mode='lines', name='Target Attenuation', line=dict(color='red'))) 
    fig2.update_layout( title=f"", xaxis_title="Degrees", template="plotly_white", legend_title_text="Waveform Type" ) 
    fig2.show()

    


if __name__ == "__main__":
    main()
    