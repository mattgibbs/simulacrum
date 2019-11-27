import sys
import logging
from os import path
import csv
ele2dev = {}
dev2ele = {}
element_names = []
device_names = []
path_to_lines = path.join(path.dirname(path.realpath(__file__)), "lcls_elements.csv")

with open(path_to_lines, 'r') as f:
    reader = csv.reader(f, delimiter=',', quotechar='"')
    for row in reader:
        element_names.append(row[0])
        device_names.append(row[1])
        ele2dev[row[0]] = row[1]
        dev2ele[row[1]] = row[0]

def convert_element_to_device(element_name):
    return ele2dev[element_name]

def convert_device_to_element(device_name):
    return dev2ele[device_name]


lvls={'CRITICAL' : logging.CRITICAL,
        'ERROR' : logging.ERROR, 
        'WARNING' : logging.WARNING, 
        'INFO' : logging.INFO, 
        'DEBUG' : logging.DEBUG,
        'NOTSET' : logging.NOTSET}

class SimulacrumLog():
    def __init__(self, name, level=logging.DEBUG, stream=sys.stdout):
        self.name=name
        self.level=lvls[level.upper()]
        self.stream=stream
        self.msg = 'FROM {} %(process)d AT %(asctime)s: \n  %(message)s'.format(self.name)

        self.Log=logging.getLogger(name)
        self.configLog()

 
    #Log always set to DEBUG level, level to stdout is specified by user as level paramter in SimulacrumLog initialization
    def configLog(self):
        self.Log.setLevel(logging.DEBUG)
        Handler=logging.StreamHandler(self.stream)
        Handler.setLevel(self.level)
        Format=logging.Formatter(self.msg)
        Handler.setFormatter(Format)
        self.Log.addHandler(Handler)
    
    #logging function override to enable logging by Logger object
    def critical(self, *args, **kwargs):
        self.Log.critical(*args, **kwargs)

    def error(self, *args, **kwargs):
        self.Log.error(*args, **kwargs)

    def warning(self, *args, **kwargs):
        self.Log.warning(*args, **kwargs)
    
    def info(self, *args, **kwargs):
        self.Log.info(*args, **kwargs)
    
    def debug(self, *args, **kwargs):
        self.Log.debug(*args, **kwargs)
