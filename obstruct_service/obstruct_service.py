#last edited by J.Shtalenkova on 2.19.2019

import os
import asyncio
import numpy as np
from collections import OrderedDict
from caproto.server import ioc_arg_parser, run, pvproperty, PVGroup
from caproto import ChannelType
import simulacrum
import zmq
from zmq.asyncio import Context

class StopperPV(PVGroup):
    sts_states = [0, 1, 2, 3] #0-MOVING, 1-OUT, 2-IN, 3-INCONSISTENT 
    sts = pvproperty(value=0, name=':TGT_STS', read_only=True)
    ctrl_strings = ["IN", "OUT"]
    ctrl = pvproperty(value=0, name=':CTRL', dtype=ChannelType.ENUM,
                        enum_strings=ctrl_strings)

    def __init__(self, device_name, element_name, change_callback, initial_value, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device_name = device_name
        self.element_name = element_name
        self.sts._data['value'] = initial_value
        if initial_value == 2:
            self.ctrl._data['value'] = 'IN'
        elif initial_value == 1:
            self.ctrl._data['value'] = 'OUT'
        #self.pneu._data['value'] = <pneu initial_value>
        self.change_callback = change_callback
    
#    pneu_string = ':' + self.element_name + '_PNEU'
#
#    @pvproperty(value=0, name=pneu_string)
#    async def pneu(self, instance):
#        
#        ioc = instance.group
#        if ioc.sts.value==2:
#            instance._data['value']=<pneuIN value>
#        elif ioc.sts.value==1:
#            instance._data['value']=<pneuOUT value>
#        instance._data['value']=ioc.sts.value
#        return None
#
#    @pneu.putter
#    async def pneu(self, instance, value):
#        ioc = instance.group
#        await ioc.ctrl.write()
    
    @ctrl.putter
    async def ctrl(self, instance, value):
        print('IM MR MESEEKS LOOK AT MEEEEEE!!!!!!!!!' + value)
        ioc = instance.group
        if value == "IN":
            await ioc.sts.write(2)
            self.change_callback(self, ioc.sts.value)
        elif value == "OUT":
            await ioc.sts.write(1)
            self.change_callback(self, ioc.sts.value)
        else:
            print("Warning, using a non-implemented stopper control function.")
        return self.ctrl_strings.index(value)



#---------------------------------------COLLIMATORS--------------------------------------------#
#class CollimatorPV(ObstructPV):
#collimator control is a bit more complicated 
    #basic implementation is to just get/set gap and center 
    
    #more complicated implementation will need individual jaw control (for stuff like horn-cutting)
    #set left jaw and right jaw individually -need des and readback plus update center and width readbacks

#    setgap = pvproperty(value=0.0, name=':SETGAP')
#    getgap = pvproperty(value=0.0, name=':GETGAP', read_only=True)
#    setcenter = pvproperty(value=0.0, name=':SETCENTER')
#    getcenter = pvproperty(value=0.0, name=':GETCENTER', read_only=True)
#    
#
#    def __init__(self, device_name, element_name, change_callback, initial_gap, initial_center, *args, **kwargs):
#        super().__init__(*args, **kwargs)
#        self.device_name = device_name
#        self.element_name = element_name
#        self.setgap._data['value'] = initial_gap
#        self.setcenter._data['value'] = initial_center
#        self.change_callback = change_callback
#
#
#    @setgap.putter
#    async def setgap(self, instance, value):
#        ioc = instance.group
#        await ioc.setgap.write(value)



#----------------------------------------PROFILE MONITORS--------------------------------------------#
#class ProfileMonitorPV(PVGroup):



#parse the bmad 'show lat' return 
def parse_limits(table):
    limits = [row.split() for row in table]
    return {ele: ( float(x1), float(x2), float(y1), float(y2) ) for (_, ele, _, _, _, x1, x2, y1, y2) in limits} 


class ObstructorService(simulacrum.Service):

  
    #name converter inverter 
    def names_inverter(d):
        {v:k for k, v in d}
        return d 

    def recv_pytao():
        for line in self.cmd_socket.recv_pyobj()['result']:
            print(line)
    #initialize service
    def __init__(self):
        super().__init__()
        #name converters 
        self.stopper_names = {'TD11':'DUMP:LI21:305', 'TDUND':'DUMP:LTU1:970'} 
        self.screen_names =  {'YAG02':'YAGS:IN20:241'}
        self.collimator_names = {'CE11': 'COLL:LI21:235'}
        self.limit_names = ['x1_limit', 'x2_limit', 'y1_limit', 'y2_limit']
        
        #network stuff <consult M. Gibbs> 
        self.ctx = Context.instance()
        #cmd socket is a synchronous socket, we don't want the asyncio context.
        self.cmd_socket = zmq.Context().socket(zmq.REQ)
        self.cmd_socket.connect("tcp://127.0.0.1:{}".format(os.environ.get('MODEL_PORT', 12312)))
        #build dictionary of start values
        self.init_sts = self.get_obstruct_statuses_from_model()
        #create stopper PVs
        stopper_pvs = {device_name: StopperPV(device_name, simulacrum.util.convert_device_to_element(device_name), 
                        self.on_stopper_change, initial_value=self.init_sts[device_name], prefix=device_name)
                    for device_name in self.stopper_names.values()}
        self.add_pvs(stopper_pvs)
   
# !!!   #create collimator PVs    

# !!!   #create screen PVs    
    
        print("Initialization complete.")
    
    #obtain status target status values from model 
    def get_obstruct_statuses_from_model(self):
        
        #---------------------------------STOPPERS--------------------------
        self.init_sts={}
        #build and send tao command
        command = 'show lat -no_label_lines'
        for x in self.limit_names:
            command+=(' -attrib {att}'.format(att=x))
        for dev in self.stopper_names.keys(): 
            command+= (' ' + dev)
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": command})
        #collect and parse result into dictionary 
        table = self.cmd_socket.recv_pyobj()['result']
        #dictionary of {ele_name:[x1_limit, x2_limit, y1_limit, y2_limit]}
        init_vals = parse_limits(table)
        
        for stopper in init_vals.keys():
            #all limits the same = defined stopper state
            if len(set(init_vals[stopper]))==1:
                #stopper is OUT
                if (init_vals[stopper][0] == 0.0):
                    self.init_sts[self.stopper_names[stopper]]=1
                #stopper is IN
                else:
                    self.init_sts[self.stopper_names[stopper]]=2
            #otherwise, INCONSISTENT
            else:
                self.init_sts[self.stopper_names[stopper]]=3
        print(self.init_sts)
        #dictionary of {dev_name: TGT_STS value}
        return self.init_sts

    def on_stopper_change(self, stopper_pv, value):
        #define obstructor object type
        ob_type = stopper_pv.device_name.split(":")[0]
        #convert device to element
        #stopper_ele = names_inverter(self.stopper_names)[sopper_pv]
        #stopper_ele = simulcrum.util.convert_device_to_element(device_name)
        #stop global computation
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "set global lattice_calc_on=F"})
        print(self.cmd_socket.recv_pyobj())
        
        limits = self.init_sts[stopper_pv.device_name]
        if value==2:
            lim = '1e-30'
        elif value==1:
            lim = '0.0'
        #build and send tao command
        for i in range(len(self.limit_names)):
            command = 'set ele {element} {attr}={val}'.format(element=simulacrum.util.convert_device_to_element(stopper_pv.device_name), attr=self.limit_names[i], val=lim)
            self.cmd_socket.send_pyobj({"cmd": "tao", "val": command})
            print(self.cmd_socket.recv_pyobj())

        #restart global computation
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "set global lattice_calc_on=T"})
        #update orbit?
        print(self.cmd_socket.recv_pyobj())
        self.cmd_socket.send_pyobj({"cmd": "send_orbit"})
        print(self.cmd_socket.recv_pyobj())


        
    #def on_collimator_change(self):

    #def on_profmon_change(self):
    




def main():
    service = ObstructorService()
    loop = asyncio.get_event_loop()
    _, run_options = ioc_arg_parser(
        default_prefix='',
        desc="Simulated Obstructor Service")
    run(service, **run_options)
    
if __name__ == '__main__':
    main()
