#last edited by J.Shtalenkova on 2.19.2019

import os
import sys
import asyncio
import numpy as np
from collections import OrderedDict
from caproto.server import ioc_arg_parser, run, pvproperty, PVGroup
from caproto import ChannelType
import simulacrum
import zmq
from zmq.asyncio import Context

#set up python logger
import logging  
L = simulacrum.util.LogInit(__name__, level=logging.DEBUG)
L.configLog()


#---------------------------------------STOPPERS--------------------------------------------#
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
   
        self.change_callback = change_callback
    
    @ctrl.putter
    async def ctrl(self, instance, value):
        ioc = instance.group
        if value == "IN":
            await ioc.sts.write(2)
            self.change_callback(self, 2)
        elif value == "OUT":
            await ioc.sts.write(1)
            self.change_callback(self, 1)
        else:
            L.Log.warning("Warning, using a non-implemented stopper control function.")
        return self.ctrl_strings.index(value)



##---------------------------------------COLLIMATORS--------------------------------------------#
# 'left' and 'right' jaw nomenclature used for all stoppers; vertical stoppers 'left'==bottom, 'right'==top; 'left' jaw takes on negative values, 'right' jaw - positive
class CollimatorPV(PVGroup):

    setgap = pvproperty(value=0.0, name=':SETGAP')
    getgap = pvproperty(value=0.0, name=':GETGAP', read_only=True)
    setcenter = pvproperty(value=0.0, name=':SETCENTER')
    getcenter = pvproperty(value=0.0, name=':GETCENTER', read_only=True)
    
    setleft = pvproperty(value=0.0, name=':SETLEFT')
    getleft = pvproperty(value=0.0, name=':GETLEFT', read_only=True)
    
    setright = pvproperty(value=0.0, name=':SETRIGHT')
    getright = pvproperty(value=0.0, name=':GETRIGHT', read_only=True)

    @staticmethod
    def calc_coll(left, right):
        #positive right value plus negative left value gives gap
        gap = right +abs(left)
        center = right - (gap/2)
        return [gap, center]


    def __init__(self, device_name, element_name, change_callback, left_initial_value, right_initial_value, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device_name = device_name
        self.element_name = element_name
        #initialize jaws
        self.setleft._data['value'] = left_initial_value
        self.getleft._data['value'] = left_initial_value
        self.setright._data['value'] = right_initial_value
        self.getright._data['value'] = right_initial_value
        
        #print('left initial value: ', left_initial_value, ', type: ', type(left_initial_value) )
        #print('right initial value: ', right_initial_value, ', type: ', type(right_initial_value) )
        
        [g, c] = self.calc_coll(left_initial_value, right_initial_value)

        #print('center value: ', c)
        #print('gap value: ', g)
        
        #initialize gap and center
        self.setcenter._data['value'] = c
        self.getcenter._data['value'] = c
        self.setgap._data['value'] = g
        self.getgap._data['value'] = g
        
        self.change_callback = change_callback
   
    
    @setleft.putter
    async def setleft(self, instance, value):
        ioc = instance.group
        #write value to getjaw
        await ioc.getleft.write(value)
        #calculate gap and center
        val = [value, ioc.getright.value]
        [gap, center] = self.calc_coll(val[0], val[1])
        #set new gap
        self.setgap._data['value'] = gap
        self.getgap._data['value'] = gap
        #set new center
        self.setcenter._data['value'] = center
        self.getcenter._data['value'] = center

        #callback to update bmad
        self.change_callback(self, val)
        return value 
    
    @setright.putter
    async def setright(self, instance, value):
        ioc = instance.group
        await ioc.getright.write(value)
        val = [ioc.getleft.value, value]
        [gap, center] = self.calc_coll(val[0], val[1])
        self.setgap._data['value'] = gap
        self.getgap._data['value'] = gap
        self.setcenter._data['value'] = center
        self.getcenter._data['value'] = center
        self.change_callback(self, val)
        return value 


    @setcenter.putter
    async def setcenter(self, instance, value):
        ioc = instance.group
        c_diff = ioc.getcenter.value - value
        #write value to getgap
        await ioc.getcenter.write(value)
        #set new left jaw 
        self.setleft._data['value']  = ioc.getleft.value - c_diff 
        self.getleft._data['value']  = self.setleft._data['value'] 
        #set new right jaw
        self.setright._data['value']  = ioc.getright.value - c_diff 
        self.getright._data['value']  = self.setright._data['value']
        #update model
        val = [ioc.getleft.value, ioc.getright.value]
        self.change_callback(self, val)
        return value 


    @setgap.putter
    async def setgap(self, instance, value):
        ioc = instance.group
        g_diff = ioc.getgap.value - value
        await ioc.getgap.write(value)
        self.setleft._data['value'] = ioc.getleft.value + (g_diff/2)
        self.getleft._data['value'] = self.setleft._data['value']
        self.setright._data['value'] = ioc.getright.value - (g_diff/2)
        self.getright._data['value'] = self.setright._data['value']
        val = [ioc.getleft.value, ioc.getright.value]
        self.change_callback(self, val)
        return value 


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
            L.Log.info(line)
    #initialize service
    def __init__(self):
        super().__init__()
        #name converters 
        self.stopper_names = {'TD11':'DUMP:LI21:305', 'TDUND':'DUMP:LTU1:970'} 
        self.screen_names =  {'YAG02':'YAGS:IN20:241'}
        self.x_collimator_names = {'CE11': 'COLL:LI21:235'}
        self.y_collimator_names = {}
        self.limit_names = ['x1_limit', 'x2_limit', 'y1_limit', 'y2_limit']
        self.lim = [0.0, 0.0, 0.0, 0.0]

        #network stuff <consult M. Gibbs> 
        self.ctx = Context.instance()
        #cmd socket is a synchronous socket, we don't want the asyncio context.
        self.cmd_socket = zmq.Context().socket(zmq.REQ)
        self.cmd_socket.connect("tcp://127.0.0.1:{}".format(os.environ.get('MODEL_PORT', 12312)))
        #build dictionary of start values
        self.init_sts = self.get_obstruct_statuses_from_model()
        pvs={}
        #create stopper PVs
        stopper_pvs = {device_name: StopperPV(device_name, simulacrum.util.convert_device_to_element(device_name), 
                        self.on_obstructor_change, initial_value=self.init_sts[device_name], prefix=device_name)
                    for device_name in self.stopper_names.values()}
        #self.add_pvs(stopper_pvs)
        
        #create horizontal collimator PVs
        x_collimator_pvs = {device_name: CollimatorPV(device_name, simulacrum.util.convert_device_to_element(device_name), 
                        self.on_obstructor_change, left_initial_value=self.init_sts[device_name][0], right_initial_value=self.init_sts[device_name][1], prefix=device_name)
                    for device_name in self.x_collimator_names.values()}
        #self.add_pvs(x_collimator_pvs)
        
        #create vertical collimator PVs
        y_collimator_pvs = {device_name: CollimatorPV(device_name, simulacrum.util.convert_device_to_element(device_name), 
                        self.on_obstructor_change, left_initial_value=self.init_sts[device_name][0], right_initial_value=self.init_sts[device_name][1], prefix=device_name)
                    for device_name in self.y_collimator_names.values()}
        pvs.update(stopper_pvs)
        pvs.update(x_collimator_pvs)
        pvs.update(y_collimator_pvs)
        self.add_pvs(pvs)
   
# !!!   #create screen PVs    
    
        L.Log.info("Initialization complete.")
    
    #obtain status target status values from model 
    def get_obstruct_statuses_from_model(self):

        self.init_sts={}
        #build and send tao command
        command = 'show lat -no_label_lines'
        for x in self.limit_names:
            command+=(' -attrib {att}'.format(att=x))
        for dev in list(self.stopper_names)+list(self.x_collimator_names):
            command+= (' ' + dev)
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": command})
        #collect and parse result into dictionary 
        table = self.cmd_socket.recv_pyobj()['result']
        #dictionary of {ele_name:[x1_limit, x2_limit, y1_limit, y2_limit]}
        init_vals = parse_limits(table)
       

        for obstructor in init_vals.keys():
            #---------------------------------STOPPERS--------------------------
            #from x and y limits in model, determine if stopper is IN or OUT
            if obstructor in self.stopper_names.keys():
                #all limits the same = defined stopper state
                if len(set(init_vals[obstructor]))==1:
                    #stopper is OUT
                    if (init_vals[obstructor][0] == 0.0):
                        self.init_sts[self.stopper_names[obstructor]]=1
                    #stopper is IN
                    else:
                        self.init_sts[self.stopper_names[obstructor]]=2
                #otherwise, INCONSISTENT
                else:
                    self.init_sts[self.stopper_names[obstructor]]=3
            
            #---------------------------------COLLIMATORS--------------------------
            #from x and y limits in model, determine left and right jaw settings
            elif obstructor in self.x_collimator_names.keys(): 
                self.init_sts[self.x_collimator_names[obstructor]]=init_vals[obstructor][0:2] 
            #from x and y limits in model, determine bottom and top jaw settings
            elif obstructor in self.y_collimator_names.keys(): 
                self.init_sts[self.y_collimator_names[obstructor]]=init_vals[obstructor][2:4] 
        
        #print(self.init_sts)
        #dictionary of { stopper_name: TGT_STS value, collimator_name: [GETLEFT value, GETRIGHT value] }
        return self.init_sts

    
    def on_collimator_change(self, pv, value):
        #---------------------------------COLLIMATORS--------------------------
        # change x limits for horiztonal collimators or y limits for vertical collimators
        #for horizontal collimators
        if pv.element_name in self.x_collimator_names.keys():
            self.lim = [str(value[0]), str(value[1]), '0.0', '0.0']
        #for vertical collimators
        if pv.element_name in self.y_collimator_names.keys():
            self.lim = ['0.0', '0.0', str(value[0]), str(value[1])]
        return self.lim
        

    def on_stopper_change(self, pv, value):

        #---------------------------------STOPPERS--------------------------
        # change all four limits in model to put stopper IN(2) or OUT(1)
        if value==2:
            self.lim = ['1e-30' for num in range(len(self.limit_names))]
        elif value==1:
            self.lim = ['0.0' for num in range(len(self.limit_names))]
    
    #def on_profmon_change(self):
    
    def on_obstructor_change(self, pv, value):
        #define obstructor object type
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "set global lattice_calc_on=F"})
        msg = self.cmd_socket.recv_pyobj()['result']
        L.Log.info(msg)
        L.Log.info('Obstructor changing...')
        msg = 'PV: {}'.format(pv)
        L.Log.info(msg)
        msg='PV device, PV element: {} {}'.format( pv.device_name, pv.element_name)
        L.Log.debug(msg)
        if pv.element_name in self.stopper_names.keys():
            #print('I am a stopper...')
            self.on_stopper_change(pv, value)
            #print('My limits are ', self.lim )
        elif pv.element_name in self.x_collimator_names.keys() or pv.element_name in self.y_collimator_names.keys() and type(value)==list:
            #print('I am a collimator...')
            self.on_collimator_change(pv, value)
            #print('My limits are ', self.lim )
        else:
            L.Log.warning('Warning, using a non-implemented control function....')

    #build and send tao command
        for i in range(len(self.limit_names)):
            command = 'set ele {element} {attr}={val}'.format(element=pv.element_name, attr=self.limit_names[i], val=self.lim[i])
            self.cmd_socket.send_pyobj({"cmd": "tao", "val": command})
            msg=self.cmd_socket.recv_pyobj()['result']
            L.Log.info(msg)
        #restart global computation
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "set global lattice_calc_on=T"})
        #update orbit?
        msg = self.cmd_socket.recv_pyobj()['result']
        L.Log.info(msg)
        self.cmd_socket.send_pyobj({"cmd": "send_orbit"})
        msg = self.cmd_socket.recv_pyobj()['result']
        L.Log.info(msg)
    


def main():
    service = ObstructorService()
    loop = asyncio.get_event_loop()
    _, run_options = ioc_arg_parser(
        default_prefix='',
        desc="Simulated Obstructor Service")
    run(service, **run_options)
    
if __name__ == '__main__':
    main()
