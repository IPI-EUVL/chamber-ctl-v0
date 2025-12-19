import sys
import time
import datetime
import matplotlib.pyplot as plt
import numpy as np
import csv
import plotly.graph_objects as go

NAN = float('nan')

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

def main():
    labels, values = get_data(sys.argv[1])
    print (labels, values, values[:0, [labels['t (s)'], labels['vpp']]])

    times, vppavg = rolling_average(values[:, [labels['t (s)'], labels['vpp']]], 240)
    times, averages = rolling_average(values[:, [labels['t (s)'], labels['rms']]], 240)
    #print(times)
    #print(averages)

    #print(labels)python process_data.py C:\Apps\chamber-ctl\out_1759792686129503000.csv
    #print(values)
    #plt.plot(times, averages)
    #plt.show()

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=values[:, labels['t (s)']], y=values[:, labels['vpp']], mode='lines', name='RMS', line=dict(color='gray'))) 
    fig.add_trace(go.Scatter(x=values[:, labels['t (s)']], y=values[:, labels['rms']], mode='lines', name='Vpp', line=dict(color='gray'))) 
    fig.add_trace(go.Scatter(x=values[:, labels['t (s)']], y=values[:, labels['phase']], mode='lines', name='Chopper phase', line=dict(color='blue'))) 
    fig.add_trace(go.Scatter(x=values[:, labels['t (s)']], y=vppavg, mode='lines', name='Rolling average of Vpp', line=dict(color='red'))) 
    fig.add_trace(go.Scatter(x=values[:, labels['t (s)']], y=averages, mode='lines', name='Rolling average of RMS', line=dict(color='red'))) 
    fig.update_layout( title=f"", xaxis_title="Time (s)", yaxis_title="RMS Voltage (V)", template="plotly_white", legend_title_text="Waveform Type" ) 
    fig.show()



if __name__ == "__main__":
    main()
    