import sys
import logging
from os import path
ele2dev = {}
dev2ele = {}
element_names = []
device_names = []
path_to_lines = path.join(path.dirname(path.realpath(__file__)), "LCLS_lines.dat")

logform = 'FROM %(module)s %(process)d AT %(asctime)s: \n  %(message)s'

with open(path_to_lines, 'r') as f:
    for line in f:
        d = line.split()
        element_names.append(d[1])
        device_names.append(d[0])
        ele2dev[d[1]] = d[0]
        dev2ele[d[0]] = d[1]

def convert_element_to_device(element_name):
    return ele2dev[element_name]

def convert_device_to_element(device_name):
    return dev2ele[device_name]


#Create  Log object using python's getLogger rather than trying to inherit the logger class
class LogInit():
    def __init__(self, name, level=logging.DEBUG, stream=sys.stdout, msg=logform):
        self.name=name
        self.level=level
        self.stream=stream
        self.msg=msg

        self.Log=logging.getLogger(name)

    #Logger is reconfigurable by user    
    #Log always set to DEBUG level, level to stdout is specified by user as level paramter in LogInit initialization
    def configLog(self):
        self.Log.setLevel(logging.DEBUG)
        Handler=logging.StreamHandler(self.stream)
        Handler.setLevel(self.level)
        Format=logging.Formatter(self.msg)
        Handler.setFormatter(Format)
        self.Log.addHandler(Handler)


        


