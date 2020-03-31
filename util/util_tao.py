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



    
