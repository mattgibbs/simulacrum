import numpy as np
import sys
import os
import asyncio
from collections import OrderedDict
from caproto.server import ioc_arg_parser, run, pvproperty, PVGroup
from caproto import ChannelType
import simulacrum
import zmq
from zmq.asyncio import Context

#set up python logger
L = simulacrum.util.SimulacrumLog(os.path.splitext(os.path.basename(__file__))[0], level='INFO')

class UndulatorPV(PVGroup):
    useg_proc = pvproperty(value=0, name=':ConvertK2Gap.PROC' ) #Go command
    #gapact = pvproperty(value=0.0, name=':GapAct')
    #gapdes = pvproperty(value=0.0, name=':GapDes')
    kact = pvproperty(value=0.0, name=':KAct', read_only=True)
    kdes = pvproperty(value=0.0, name=':KDes')
    taper_des = pvproperty(value=0.0, name=':TaperDes')
    taper_act = pvproperty(value=0.0, name=':TaperAct', read_only=True)
    symm_act = pvproperty(value=0.0, name=':SymmetryAct', read_only=True)
    serial_n = pvproperty(value=0.0, name=':SerialNum')

    def __init__(self, device_name, element_name, change_callback, initial_values, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device_name = device_name  
        self.element_name = element_name
        self.kact._data['value'] = float(initial_values['kact'])
        self.kdes._data['value'] = float(initial_values['kact'])
        self.taper_des._data['value'] = 0
        self.symm_act._data['value'] = 0
        self.change_callback = change_callback 

    @useg_proc.putter
    async def useg_proc(self, instance, value):
        ioc = instance.group
        await asyncio.sleep(0.2)
        await ioc.kact.write(ioc.kdes.value)
        await self.change_callback(self, ioc.kact.value)  

def convert_umahx_element_to_device(ele_name):
    unit_number = ele_name.replace('UMAHX','')
    return f'USEG:UNDH:{unit_number}50'

def convert_umahx_device_to_element(device_name):
    unit_number = device_name.split(':')[2][0:2]
    return f'UMAHX{unit_number}'

def _parse_undulator_table(table):
    splits = [row.split() for row in table] 
    return {convert_umahx_element_to_device(ele_name): {"kact": und_B_max_to_Kact(float(b_max))} for (_, ele_name, _, _, l, b_max) in splits if 'UMAHX' in ele_name}

def und_B_max_to_Kact(b_max):
    # k=2, b_max = 8.2382661E-01 T
    # k = 2 pi electron_mass / (light_velocity * 0.026) / b_max
    # k = 0.9337 B(T) labda_u (cm)
    return  0.9337 * b_max * 2.6

def Kact_to_und_B_max(k):
    return k/2.6/0.9337

class UndulatorService(simulacrum.Service):
    conversion_to_BMAD_for_und_type = {"USEG": Kact_to_und_B_max}
    def __init__(self):
        super().__init__()
        self.ctx = Context.instance()
        #cmd socket is a synchronous socket, we don't want the asyncio context.
        self.cmd_socket = zmq.Context().socket(zmq.REQ)
        self.cmd_socket.connect("tcp://127.0.0.1:{}".format(os.environ.get('MODEL_PORT', 12312)))
        init_vals = self.get_initial_values()
        undulator_element_list = self.get_undulator_list_from_model() 
        undulator_device_list = [convert_umahx_element_to_device(element) for element in undulator_element_list]
        print(undulator_device_list)
        for device_name in undulator_device_list:
            if device_name in init_vals:
                initial_value=init_vals[device_name]
                print(f'{device_name} {convert_umahx_device_to_element(device_name)} {initial_value}')

        und_pvs = {device_name: UndulatorPV(device_name, convert_umahx_device_to_element(device_name), self.on_undulator_change, initial_values=init_vals[device_name], prefix=device_name) 
                    for device_name in undulator_device_list
                    if device_name in init_vals}

        
        print(und_pvs)
        self.add_pvs(und_pvs)
        L.info("Initialization complete.")

    def get_undulator_list_from_model(self):
        element_list = []
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "show ele -no_slaves UMAHX*"})
        for row in self.cmd_socket.recv_pyobj()['result'][:-1]:
            element_list.append(row.split(None, 3)[1])
        return element_list


    def get_initial_values(self):
        init_vals = self.get_undulator_Kacts_from_model()
        #path_to_limits_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "undulator_limits.json")
        #with open(path_to_limits_file) as f:
        #    limits = json.load(f)
        #    for device_name in init_vals:
        #        try:
        #            init_vals[device_name]["units"] = limits[device_name]["EGU"]
        #            init_vals[device_name]["precision"] = limits[device_name]["PREC"]
        #            init_vals[device_name]["upper_ctrl_limit"] = limits[device_name]["HOPR"]
        #            init_vals[device_name]["lower_ctrl_limit"] = limits[device_name]["LOPR"]
        #        except KeyError:
        #            pass
        return init_vals

    def get_undulator_Kacts_from_model(self):
        init_vals = {}
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "show lat -no_label_lines -no_slaves -attribute {attr} {list}".format(attr="B_MAX", list="UMAHX*")})
        table = self.cmd_socket.recv_pyobj()
        init_vals.update(_parse_undulator_table(table['result']))
        return init_vals

    async def on_undulator_change(self, undulator_pv, value):
        und_type = undulator_pv.device_name.split(":")[0]
        und_attr = 'B_MAX' 
        conv = self.conversion_to_BMAD_for_und_type[und_type]
        #l = magnet_pv.length
        L.debug('Updating {}... '.format( undulator_pv.device_name ) )
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "set ele {element} {attr} = {val}".format(element=undulator_pv.element_name, 
                                                                                                   attr=und_attr,
                                                                                                   val=conv(value))})
        self.cmd_socket.recv_pyobj()
        L.info('Updated {}.'.format(undulator_pv.device_name))

def main():
    service = UndulatorService()
    loop = asyncio.get_event_loop()
    _, run_options = ioc_arg_parser(
        default_prefix='',
        desc="Simulated Undulator Service")
    run(service, **run_options)
    
if __name__ == '__main__':
    main()
    
    
