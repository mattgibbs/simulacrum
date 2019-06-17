#last edited by J.Shtalenkova on 04.22.2019

import os
import asyncio
import numpy as np
from collections import OrderedDict
from caproto.server import ioc_arg_parser, run, pvproperty, PVGroup
from caproto import ChannelType
import simulacrum
import zmq
from zmq.asyncio import Context

#WHAT I WANT
#data [float] gets calculated on change, 
#hist [array] gets updated on timer with data value
#---------------------------------------STOPPERS--------------------------------------------#
class BMAGPV(PVGroup):
    Xbmag = pvproperty(value= 0.0, name=':ENRCX', read_only=True)
    Ybmag = pvproperty(value=0.0, name=':ENRCY', read_only=True)
    bmag = pvproperty(value=0.0, name=':ENRC', read_only=True)
    hist = pvproperty(value=np.zeros(120).tolist(), name=':ENRCHSTBR', read_only=True)

class BMAGService(simulacrum.Service):
    #initialize service
    def __init__(self):
        super().__init__()
        #create gdet PVs
        pvs = {'GDET:FEE1:241': BMAGPV(prefix='GDET:FEE1:241')} 
        self.add_pvs(pvs)

        #network stuff  
        self.ctx = Context.instance()
        #cmd socket is a synchronous socket, we don't want the asyncio context.
        self.cmd_socket = zmq.Context().socket(zmq.REQ)
        self.cmd_socket.connect("tcp://127.0.0.1:{}".format(os.environ.get('MODEL_PORT', 12312)))

        #collect and parse design and current twiss at UNDSTART from model
        #self.cmd_socket.send_pyobj({"cmd": "tao", "val": "python lat_list 1@0>>UNDSTART|design ele.a.alpha,ele.a.beta,ele.b.alpha,ele.b.beta"})
        self.cmd_socket.send_pyobj({"cmd" : "tao", "val" : "show lat -design -no_label_lines -at alpha_a -at beta_a -at alpha_b -at beta_b UNDSTART"})
        self.design = self.get_init_data()
        #self.cmd_socket.send_pyobj({"cmd": "tao", "val": "python lat_list 1@0>>UNDSTART|model ele.a.alpha,ele.a.beta,ele.b.alpha,ele.b.beta"})
        self.cmd_socket.send_pyobj({"cmd" : "tao", "val" : "show lat -no_label_lines -at alpha_a -at beta_a -at alpha_b -at beta_b UNDSTART"})
        self.model = self.get_init_data()
        #initialize bmag values
        print('Buffer ', self['GDET:FEE1:241:ENRCHSTBR'].value, ' type: ', type(self['GDET:FEE1:241:ENRCHSTBR'].value) )
        self['GDET:FEE1:241:ENRCX'].write(self.calc_bmag()[0])
        self['GDET:FEE1:241:ENRCY'].write(self.calc_bmag()[1])
        self['GDET:FEE1:241:ENRC'].write(self.calc_bmag()[2])
        print("Initialization complete.")

    #obtain alpha and beta values at UNDSTART
    def get_init_data(self):
        #send query
        lattice=[]
        line = self.cmd_socket.recv_pyobj()['result'][0].split()
        lattice = [ float(x) for x in line[-4:] ]
        #print('init lattice: ', lattice)
        return lattice

    def get_data(self, stuff):
        #send query
        lattice=[]
        lattice = [ float(x) for x in stuff[-4:] ]
        #print('lattice from model: ', lattice)
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
            print("Checking for new twiss data.")
            md = await model_broadcast_socket.recv_pyobj(flags=flags)
            print("Some data incoming: ", md)
            if md.get("tag", None) == "und_twiss":
                print("Twiss data incoming: ", md)
                msg = await model_broadcast_socket.recv_pyobj(flags=flags) #does this look right if I am sending twiss list as a pyobj? 
                self.model = self.get_data(msg)
                self.bmags = self.calc_bmag()
                print('Bmags: ', self.bmags)
                #fill single value PVs
                await self['GDET:FEE1:241:ENRCX'].write(self.bmags[0])
                await self['GDET:FEE1:241:ENRCY'].write(self.bmags[1])
                await self['GDET:FEE1:241:ENRC'].write(self.bmags[2])
                #circle history buffer and update first value 
                #await self['GDET:FEE1:241:ENRCHSTBR'].write( np.roll(self['GDET:FEE1:241:ENRCHSTBR']) )            ROLL AND CHANGE FIRST VALUE
                print(type(self.bmags[2])) 
                print(type(self.bmags[2].tolist()))
                print(type(self['GDET:FEE1:241:ENRCHSTBR'].value))
                await self['GDET:FEE1:241:ENRCHSTBR'].write( self['GDET:FEE1:241:ENRCHSTBR'].value[:-1].append(self.bmags[2])  )     #STACK FIRST VALUE AND OLD ARRAY 
                #await self['GDET:FEE1:241:ENRCHSTBR'][0].write(self.bmags[2])
            else: 
                msg = await model_broadcast_socket.recv(flags=flags)


def main():
    service = BMAGService()
    loop = asyncio.get_event_loop()
    _, run_options = ioc_arg_parser(
        default_prefix='',
        desc="Simulated Undulator Match Service")
    loop.create_task(service.recv_twiss_list())
    loop.call_soon(service.request_twiss)
    run(service, **run_options)
    
if __name__ == '__main__':
    main()
