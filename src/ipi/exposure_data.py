import csv

class ExposureData:
    def __init__(self, filename):
        self.__filenme = filename

def load(self):
    file = open(self.__filename)
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
        