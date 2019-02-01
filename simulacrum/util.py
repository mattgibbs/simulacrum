import sys
from os import path
ele2dev = {}
dev2ele = {}
path_to_lines = path.join(path.dirname(path.realpath(__file__)), "LCLS_lines.dat")

with open(path_to_lines, 'r') as f:
    for line in f:
        d = line.split()
        ele2dev[d[1]] = d[0]
        dev2ele[d[0]] = d[1]

def convert_element_to_device(element_name):
    return ele2dev[element_name]

def convert_device_to_element(device_name):
    return dev2ele[device_name]