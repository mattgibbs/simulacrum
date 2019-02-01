import os
import random
import asyncio
import numpy as np
from collections import defaultdict
import zmq
from zmq.asyncio import Context
from simulacrum.util import convert_element_to_device

class BPMSim:
    def __init__(self):
        self.orbit = None
        self.value = 0
        self.channels = defaultdict(set)
        self.ctx = Context.instance()
        #cmd socket is a synchronous socket, we don't want the asyncio context.
        self.cmd_socket = zmq.Context().socket(zmq.REQ)
        self.cmd_socket.connect("tcp://127.0.0.1:{}".format(os.environ.get('MODEL_PORT', 12312)))
        self.initialize_orbit()
    
    def initialize_orbit(self):
        # First, get the list of BPMs and their Z locations from the model service
        # This is maybe brittle because we use Tao's "show" command, then parse
        # the results, which the Tao authors advise against because the format of the 
        # results might change.  Oh well, I can't figure out a better way to do it.
        print("Initializing with data from model service.")
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "show ele Instrument::BPM*,Instrument::RFB*"})
        bpms = self.cmd_socket.recv_pyobj()['result'][:-1]
        self.orbit = np.zeros(len(bpms), dtype=[('element_name', 'a60'), ('device_name', 'a60'), ('x', 'float32'), ('y', 'float32'), ('tmit', 'float32'), ('z', 'float32'), ('x_severity', 'i8'), ('y_severity', 'i8'), ('tmit_severity', 'i8')])
        for i, row in enumerate(bpms):
            (_, name, z) = row.split()
            self.orbit['element_name'][i] = name
            try:
                self.orbit['device_name'][i] = convert_element_to_device(name)
            except KeyError:
                pass
            self.orbit['z'][i] = z
        
        print("Initialization complete.")
        #Initialization is done, lets start the show...        
        asyncio.get_event_loop().create_task(self.recv_orbit_array())
        #Ask the model to send us the first orbit.
        self.cmd_socket.send_pyobj({"cmd":"send_orbit"})
    
    def __getitem__(self, key):
        pieces = key.split(":")
        name = bytes(":".join(pieces[0:3]), encoding='ascii')
        val = pieces[-1].lower()
        return self.orbit[self.orbit['device_name']==name][0][val]
    
    async def recv_orbit_array(self, flags=0, copy=True, track=False):
        """recv a numpy array"""
        orbit_socket = self.ctx.socket(zmq.SUB)
        orbit_socket.connect('tcp://127.0.0.1:{}'.format(os.environ.get('ORBIT_PORT', 56789)))
        orbit_socket.setsockopt(zmq.SUBSCRIBE, b'')
        while True:
            print("Checking for new orbit data.")
            md = await orbit_socket.recv_pyobj(flags=flags)
            print("Orbit data incoming: ", md)
            msg = await orbit_socket.recv(flags=flags, copy=copy, track=track)
            buf = memoryview(msg)
            A = np.frombuffer(buf, dtype=md['dtype'])
            A = A.reshape(md['shape'])
            self.orbit['x'] = A[0]
            self.orbit['y'] = A[1]
            print(self.orbit)
            await self.publish_orbit()

    async def publish_orbit(self):
        for pvname, d in self.channels.items():
            for channel in d:
                await channel.write(self[pvname])

    async def get(self, pvname):
        return self[pvname]

    async def put(self, pvname, value):
        raise Exception("Cannot put BPM values.")

    async def subscribe(self, pvname, channel):
        self.channels[pvname].add(channel)

    async def unsubscribe(self, pvname, channel):
        self.channels[pvname].discard(channel)