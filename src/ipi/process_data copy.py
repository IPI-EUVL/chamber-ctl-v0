import sys
import time
import datetime
import matplotlib.pyplot as plt
import numpy as np

NAN = float('nan')

def get_data(filename):
    file = open(filename)

    value_labels = dict()
    values = []

    for line in file:
        tokens = line.split(',')
        data = []

        for kvp in tokens:
            k, v = kvp.split(':')
            data.append(float(v))
        
        values.append(data)

    return np.array(values)

def time_based_average(values, window_size):
    begin_time = values[0, 0]
    avg = 0.0
    samples = 0

    window_times = []
    window_averages = []
    for (time, skew, phase, vpp) in values[1:]:
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

def main():
    values = get_data(sys.argv[1])

    #times, averages = time_based_average(values[2000:-1000], 5)
    #print(times)
    #print(averages)
    print(values)
    plt.plot(values[:, 0], values[:, 7])
    plt.show()



if __name__ == "__main__":
    main()