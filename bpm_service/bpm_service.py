import os
import sys
import asyncio
import numpy as np
from caproto.server import ioc_arg_parser, run, pvproperty, PVGroup
import simulacrum
import zmq
from zmq.asyncio import Context

#set up python logger
import logging  
L = simulacrum.util.LogInit(__name__, level=logging.INFO)
L.configLog()

class BPMPV(PVGroup):
    x = pvproperty(value=0.0, name=':X', read_only=True, mock_record='ai',
                   upper_disp_limit=3.0, lower_disp_limit=-3.0)
    y = pvproperty(value=0.0, name=':Y', read_only=True, mock_record='ai',
                   upper_disp_limit=3.0, lower_disp_limit=-3.0)
    tmit = pvproperty(value=0.0, name=':TMIT', read_only=True, mock_record='ai',
                   upper_disp_limit=1.0e10, lower_disp_limit=0)
    z = pvproperty(value=0.0, name=':Z', read_only=True)
    
class BPMService(simulacrum.Service):
    def __init__(self):
        super().__init__()
        bpm_pvs = {device_name: BPMPV(prefix=device_name) for device_name in simulacrum.util.device_names if device_name.startswith("BPM")}
        self.add_pvs(bpm_pvs)
        self.ctx = Context.instance()
        #cmd socket is a synchronous socket, we don't want the asyncio context.
        self.cmd_socket = zmq.Context().socket(zmq.REQ)
        self.cmd_socket.connect("tcp://127.0.0.1:{}".format(os.environ.get('MODEL_PORT', 12312)))
        self.orbit = self.initialize_orbit()
        L.Log.info("Initialization complete.")
    
    def initialize_orbit(self):
        # First, get the list of BPMs and their Z locations from the model service
        # This is maybe brittle because we use Tao's "show" command, then parse
        # the results, which the Tao authors advise against because the format of the 
        # results might change.  Oh well, I can't figure out a better way to do it.
        L.Log.info("Initializing with data from model service.")
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "show ele Instrument::BPM*,Instrument::RFB*"})
        bpms = self.cmd_socket.recv_pyobj()['result'][:-1]
        orbit = np.zeros(len(bpms), dtype=[('element_name', 'U60'), ('device_name', 'U60'), ('x', 'float32'), ('y', 'float32'), ('tmit', 'float32'), ('z', 'float32')])
        for i, row in enumerate(bpms):
            (_, name, z) = row.split()
            orbit['element_name'][i] = name
            try:
                orbit['device_name'][i] = simulacrum.util.convert_element_to_device(name)
            except KeyError:
                pass
            orbit['z'][i] = float(z)
        orbit = np.sort(orbit,order='z')
        return orbit
    
    async def publish_z(self):
        L.Log.info("Publishing Z PVs")
        for row in self.orbit:
            zpv = row['device_name']+":Z"
            if zpv in self:
                await self[zpv].write(row['z'])
    
    def request_orbit(self):
        self.cmd_socket.send_pyobj({"cmd": "send_orbit"})
        return self.cmd_socket.recv_pyobj()
        
    async def recv_orbit_array(self, flags=0, copy=False, track=False):
        """recv a numpy array"""
        model_broadcast_socket = self.ctx.socket(zmq.SUB)
        model_broadcast_socket.connect('tcp://127.0.0.1:{}'.format(os.environ.get('MODEL_BROADCAST_PORT', 66666)))
        model_broadcast_socket.setsockopt(zmq.SUBSCRIBE, b'')
        while True:
            L.Log.info("Checking for new orbit data.")
            md = await model_broadcast_socket.recv_pyobj(flags=flags)
            msg="Orbit data incoming: {}".format(md)
            #L.Log.info(msg)
            if md.get("tag", None) == "orbit":
                msg = await model_broadcast_socket.recv(flags=flags, copy=copy, track=track)
                buf = memoryview(msg)
                A = np.frombuffer(buf, dtype=md['dtype'])
                A = A.reshape(md['shape'])
                self.orbit['x'] = A[0]
                self.orbit['y'] = A[1]
                L.Log.info(self.orbit)
                await self.publish_orbit()
            else: 
                await model_broadcast_socket.recv(flags=flags, copy=copy, track=track)
                 
            
    async def publish_orbit(self):
        for row in self.orbit:
            if row['device_name']+":X" in self:
                await self[row['device_name']+":X"].write(row['x'])
                await self[row['device_name']+":Y"].write(row['y'])
                await self[row['device_name']+":TMIT"].write(row['tmit'])
    
def main():
    service = BPMService()
    loop = asyncio.get_event_loop()
    _, run_options = ioc_arg_parser(
        default_prefix='',
        desc="Simulated BPM Service")
    loop.create_task(service.publish_z())
    loop.create_task(service.recv_orbit_array())
    loop.call_soon(service.request_orbit)
    run(service, **run_options)
    
if __name__ == '__main__':
    main()
