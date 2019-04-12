#!/usr/bin/env python3
import os
import sys
import pickle
import pytao
import numpy as np
import asyncio
import zmq
from zmq.asyncio import Context

class ModelService:
    def __init__(self):
        tao_lib = os.environ.get('TAO_LIB', '')
        self.tao = pytao.Tao(so_lib=tao_lib)
        path_to_lattice = os.path.join(os.path.dirname(os.path.realpath(__file__)), "lcls.lat")
        path_to_init = os.path.join(os.path.dirname(os.path.realpath(__file__)), "tao.init")
        self.tao.init("-noplot -lat {lat_path} -init {init_path}".format(lat_path=path_to_lattice, init_path=path_to_init))
        self.ctx = Context.instance()
        self.orbit_socket = zmq.Context().socket(zmq.PUB)
        self.orbit_socket.bind("tcp://*:{}".format(os.environ.get('ORBIT_PORT', 56789)))
        self.profile_socket = zmq.Context().socket(zmq.PUB)
        self.profile_socket.bind("tcp://*:{}".format(os.environ.get('PROFILE_PORT', 12345)))

    def start(self):
        print("Starting Model Service.")
        loop = asyncio.get_event_loop()
        task = loop.create_task(self.recv())
        try:
            loop.run_until_complete(task)
        except KeyboardInterrupt:
            task.cancel()
    
    def set_corrector_strength(self, name, new_strength, axis=None):
        if not axis:
            if name.startswith("XC"):
                axis = "h"
            elif name.startswith("YC"):
                axis = "v"
            else:
                raise Exception("Could not determine if corrector is horizontal or vertical.")
        axis = axis.lower()
        if axis == "x":
            axis = "h"
        elif axis == "y":
            axis = "v"
        if axis not in ["h", "v"]:
            raise Exception("Invalid Axis")
        result = self.tao.cmd("set ele {element} {axis}kick = {strength}".format(element=name, axis=axis, strength=new_strength))
        result = "".join(result)
        if "ERROR" in result:
            raise Exception(result)
        else:
            self.send_orbit()
            self.send_profiles_twiss() 
            self.send_prof_orbit()
    
    def get_orbit(self):
        #Get X Orbit
        x_orb_text = self.tao.cmd("show data orbit.x")[3:-2]
        x_orb = _orbit_array_from_text(x_orb_text)
        #Get Y Orbit
        y_orb_text = self.tao.cmd("show data orbit.y")[3:-2]
        y_orb = _orbit_array_from_text(y_orb_text)
        return np.stack((x_orb, y_orb))

    def get_prof_orbit(self):
        #Get X Orbit
        x_orb_text = self.tao.cmd("show data orbit.profx")[3:-2]
        x_orb = _orbit_array_from_text(x_orb_text)
        #Get Y Orbit
        y_orb_text = self.tao.cmd("show data orbit.profy")[3:-2]
        y_orb = _orbit_array_from_text(y_orb_text)
        return np.stack((x_orb, y_orb))
    
    def old_get_orbit(self):
        #Get X Orbit
        x_orb_text = self.tao.cmd("python lat_list 1@0>>BPM*|model orbit.vec.1")
        x_orb = _orbit_array_from_text(x_orb_text)
        #Get Y Orbit
        y_orb_text = self.tao.cmd("python lat_list 1@0>>BPM*|model orbit.vec.3")
        y_orb = _orbit_array_from_text(y_orb_text)
        return np.stack((x_orb, y_orb))
    
    def send_orbit(self):
        orb = self.get_orbit()
        metadata = {"dtype": str(orb.dtype), "shape": orb.shape}
        self.orbit_socket.send_pyobj(metadata, zmq.SNDMORE)
        self.orbit_socket.send(orb)

    def send_prof_orbit(self):
        orb = self.get_prof_orbit()
        metadata = {"dtype": str(orb.dtype), "shape": orb.shape}
        self.profile_socket.send_pyobj(metadata, zmq.SNDMORE)
        self.profile_socket.send(orb)

    def send_profiles_twiss(self):
        print('Sending Profile');
        twiss_text = np.asarray(self.tao.cmd("show lat -at beta_a -at beta_b Instrument::OTR*,Instrument::YAG*"))
        metadata = {"dtype": str(twiss_text.dtype), "shape": twiss_text.shape}
        self.profile_socket.send_pyobj(metadata, zmq.SNDMORE)
        self.profile_socket.send(np.stack(twiss_text));        
           
    async def recv(self):
        s = self.ctx.socket(zmq.REP)
        s.bind("tcp://*:{}".format(os.environ.get('MODEL_PORT', "12312")))
        while True:
            p = await s.recv_pyobj()
            print("Got a message: ", p)
            if p['cmd'] == 'corr':
                try:
                    self.set_corrector_strength(name=p['name'], new_strength=p['val'], axis=p.get('axis'))
                    await s.send_pyobj({'status': 'ok'})
                except Exception as e:
                    await s.send_pyobj({'status': 'fail', 'err': e})
            elif p['cmd'] == 'tao':
                try:
                    retval = self.tao.cmd(p['val'])
                    await s.send_pyobj({'status': 'ok', 'result': retval})
                except Exception as e:
                    await s.send_pyobj({'status': 'fail', 'err': e})
            elif p['cmd'] == 'send_orbit':
                try:
                    self.send_orbit()
                    await s.send_pyobj({'status': 'ok'})
                except Exception as e:
                    await s.send_pyobj({'status': 'fail', 'err': e})
            elif p['cmd'] == 'echo':
                    await s.send_pyobj({'status': 'ok', 'result': p['val']})
            elif p['cmd'] == 'send_profiles_twiss':
                self.send_profiles_twiss()
                self.send_prof_orbit()
                await s.send_pyobj({'status': 'ok'})
    
def _orbit_array_from_text(text):
    return np.array([float(l.split()[5]) for l in text])*1000.0

if __name__=="__main__":
    serv = ModelService()
    serv.start()

