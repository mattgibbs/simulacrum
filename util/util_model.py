import random
import h5py
from time import sleep
#For epics
from scipy.io import savemat
from scipy.io import loadmat
from numpy import array, save
import epics
#For simulacrum 
import zmq
from zmq.asyncio import Context
import os
cmd_socket = zmq.Context().socket(zmq.REQ)
cmd_socket.connect("tcp://127.0.0.1:{}".format(os.environ.get('MODEL_PORT', 12312)))
model_broadcast_socket = zmq.Context().socket(zmq.SUB)
model_broadcast_socket.connect('tcp://127.0.0.1:{}'.format(os.environ.get('MODEL_BROADCAST_PORT', 66666)))
model_broadcast_socket.setsockopt(zmq.SUBSCRIBE, b'')


def taoCmd(cmd, terse = False):
   cmd_socket.send_pyobj({"cmd": "tao", "val": cmd})
   v = cmd_socket.recv_pyobj()
   for l in v['result']:
       if not terse:
           print(l)
   return v
def taoEcho(echo):
    cmd_socket.send_pyobj({"cmd": "echo", "val": echo})
    v = cmd_socket.recv_pyobj()
    return v

def modelCmd(cmd, val = None):
    cmd_socket.send_pyobj({"cmd": cmd, "val": val})
    v = cmd_socket.recv_pyobj()
    while True:
        b = model_broadcast_socket.recv_pyobj()
        if(b['tag'] == 'part_positions'):
            print("particles!")
            b = model_broadcast_socket.recv_pyobj()
            break;
        else:
            b = model_broadcast_socket.recv()
    return b



    
