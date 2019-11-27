
import os
import sys
import asyncio
import numpy as np
from collections import OrderedDict
from caproto.server import ioc_arg_parser, run, pvproperty, PVGroup
from caproto import ChannelType, ChannelDouble
import simulacrum
import zmq
from zmq.asyncio import Context

#set up python logger
L = simulacrum.util.SimulacrumLog(os.path.splitext(os.path.basename(__file__))[0], level='INFO')

class BMAGPV(PVGroup):
    Xbmag = pvproperty(value= 0.0, name=':ENRCX', read_only=True)
    Ybmag = pvproperty(value=0.0, name=':ENRCY', read_only=True)
    bmag = pvproperty(value=0.0, name=':ENRC', read_only=True)
    #hist = pvproperty(value=np.zeros(120).tolist(), name=':ENRCHSTBR', read_only=True)

class BMAGService(simulacrum.Service):
    #initialize service
    def __init__(self):
        super().__init__()
        #create gdet PVs
        self.buffer_pv = ChannelDouble(value=np.zeros(2800, dtype=np.float64))
        self['GDET:FEE1:241:ENRCHSTBR'] = self.buffer_pv
        pvs = {'GDET:FEE1:241': BMAGPV(prefix='GDET:FEE1:241')} 
        self.add_pvs(pvs)

        #network stuff  
        self.ctx = Context.instance()
        #cmd socket is a synchronous socket, we don't want the asyncio context.
        self.cmd_socket = zmq.Context().socket(zmq.REQ)
        self.cmd_socket.connect("tcp://127.0.0.1:{}".format(os.environ.get('MODEL_PORT', 12312)))

        #collect and parse design and current twiss at UNDSTART from model.
        #Sadly, the different beamlines give this marker point different names.  We just try all of em.            
        und_marker_points = ("UNDSTART", "BEGUNDH", "BEGUNDS")
        for marker_point in und_marker_points:
            self.cmd_socket.send_pyobj({"cmd" : "tao", "val" : "show lat -design -no_label_lines -at alpha_a -at beta_a -at alpha_b -at beta_b {}".format(marker_point)})
            response = self.cmd_socket.recv_pyobj()
            if "ERROR" not in response['result'][0]:
                self.design = self.get_init_data(response)
                self.cmd_socket.send_pyobj({"cmd" : "tao", "val" : "show lat -no_label_lines -at alpha_a -at beta_a -at alpha_b -at beta_b {}".format(marker_point)})
                response = self.cmd_socket.recv_pyobj()
                self.model = self.get_init_data(response)
                break
            
        #initialize bmag values
        msg = 'Buffer {}'.format(self['GDET:FEE1:241:ENRCHSTBR'].value)
        L.debug(msg)
        self.bmags = self.calc_bmag()
        self['GDET:FEE1:241:ENRCX']._data['value'] = self.bmags[0]
        self['GDET:FEE1:241:ENRCY']._data['value'] = self.bmags[1]
        self['GDET:FEE1:241:ENRC']._data['value'] = self.bmags[2]
        L.info("Initialization complete.")

    #obtain alpha and beta values at UNDSTART
    def get_init_data(self, response):
        #send query
        lattice=[]
        line = response['result'][0].split()
        lattice = [ float(x) for x in line[-4:] ]
        return lattice

    def get_data(self, stuff):
        #send query
        lattice=[]
        lattice = [ float(x) for x in stuff[-4:] ]
        return lattice
    #build Bmag
    def calc_bmag(self):
        [x_alpha, x_beta, y_alpha, y_beta] = self.model
        x_bmag = (1/2)*((self.design[1]/x_beta)+(x_beta/self.design[1])+(x_alpha*np.sqrt(self.design[1]/x_beta)-self.design[0]*np.sqrt(x_beta/self.design[1]))**2)
        y_bmag = (1/2)*((self.design[3]/y_beta)+(y_beta/self.design[3])+(y_alpha*np.sqrt(self.design[3]/y_beta)-self.design[2]*np.sqrt(y_beta/self.design[3]))**2)
        return [x_bmag, y_bmag, np.sqrt(x_bmag*y_bmag)]
    
    #listen for twiss objects from model
    def request_twiss(self):
        self.cmd_socket.send_pyobj({"cmd" : "send_und_twiss"})
        return self.cmd_socket.recv_pyobj()
   
    #accept twiss list from model
    async def recv_twiss_list(self, flags=0, copy=False, track=False):
        model_broadcast_socket = self.ctx.socket(zmq.SUB)
        model_broadcast_socket.connect('tcp://127.0.0.1:{}'.format(os.environ.get('MODEL_BROADCAST_PORT', 66666)))
        model_broadcast_socket.setsockopt(zmq.SUBSCRIBE, b'')
        while True:
            L.info("Checking for new twiss data.")
            md = await model_broadcast_socket.recv_pyobj(flags=flags)
            msg="Some data incoming: {}".format( md)
            L.info(msg)
            if md.get("tag", None) == "und_twiss":
                msg="Twiss data incoming: {}".format( md)
                L.info(msg)
                msg = await model_broadcast_socket.recv_pyobj(flags=flags) #does this look right if I am sending twiss list as a pyobj? 
                self.model = self.get_data(msg)
                self.bmags = self.calc_bmag()
                msg='Bmags: {}'.format( self.bmags)
                L.debug(msg)
                #fill single value PVs
                await self['GDET:FEE1:241:ENRCX'].write(self.bmags[0])
                await self['GDET:FEE1:241:ENRCY'].write(self.bmags[1])
                await self['GDET:FEE1:241:ENRC'].write(self.bmags[2])
                #circle history buffer and update first value
                
                msg = 'Buffer: {}'.format( self['GDET:FEE1:241:ENRCHSTBR'].value )
                L.debug(msg)
            else: 
                msg = await model_broadcast_socket.recv(flags=flags)

    #update buffer PV from Gaussian distribution around BMAG
    async def rotate_buffer(self): 
        while True:
           await asyncio.sleep(0.01)
           new_buff = np.roll(self.buffer_pv.value, -1)
           #calculate gdet and noise
           gdet = np.exp(1-self.bmags[2])
           sigma = np.sqrt(0.064**2+gdet*0.138**2)
           new_buff[-1] = np.random.normal(gdet, 0.01)
           await self.buffer_pv.write(new_buff)
    
    async def print_buffer(self):
        while True:
            await asyncio.sleep(20.0)
            msg='Buffer: {}'.format( self['GDET:FEE1:241:ENRCHSTBR'].value[2780:])
            L.info(msg)

def main():
    service = BMAGService()
    loop = asyncio.get_event_loop()
    _, run_options = ioc_arg_parser(
        default_prefix='',
        desc="Simulated Undulator Match Service")
    loop.create_task(service.recv_twiss_list())
    loop.create_task(service.rotate_buffer())
    loop.create_task(service.print_buffer())
    loop.call_soon(service.request_twiss)
    run(service, **run_options)
    
if __name__ == '__main__':
    main()
