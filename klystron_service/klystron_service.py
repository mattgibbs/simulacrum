import os
import asyncio
from collections import OrderedDict
from caproto.server import ioc_arg_parser, run, pvproperty, PVGroup
from caproto import ChannelType
import simulacrum
import zmq
from zmq.asyncio import Context

class KlystronPV(PVGroup):
    pdes = pvproperty(value=0.0, name=':PDES')  
    phas = pvproperty(value=0.0, name=':PHAS')
    enld = pvproperty(value=0.0, name=':ENLD')
    swrd = pvproperty(value=0, name=':SWRD')
    hdsc = pvproperty(value=0, name=':HDSC')
    dsta = pvproperty(value=0, name=':DSTA')
    stat = pvproperty(value=0, name=':STAT')  #TODO figure out STAT, DSTA for all green as defaults
    bc1s =  pvproperty(value=0, name=':BEAMCODE1_STAT')
    trim = pvproperty(value=0, name=':TRIMPHAS', dtype=ChannelType.ENUM,
                      enum_strings=("Done", "TRIM"))
    def __init__(self, device_name, element_name, change_callback, initial_values, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device_name = device_name
        self.element_name = element_name
        self.enld._data['value'] = initial_values[0]
        self.pdes._data['value'] = initial_values[1]
        self.phas._data['value'] = initial_values[1]  
        self.bc1s._data['value'] = 1
        self.change_callback = change_callback 

    @trim.putter
    async def trim(self, instance, value):
        ioc = instance.group
        if value == "TRIM":
            await asyncio.sleep(0.2)
            await ioc.phas.write(ioc.pdes.value)
            self.change_callback(self, ioc.phas.value, "PHAS")
        else:
            print("Warning, only valid function is TRIM.")
        return 0

    @enld.putter
    async def enld(self, instance, value):
        self.change_callback(self, value, "ENLD")
        return value

    @bc1s.putter
    async def bc1s(self, instance, value):
        self.change_callback(self, value, "BEAMCODE1_STAT")
        return value

 

def _parse_klys_table(table):
    splits = [row.split() for row in table]
    return {'KLYS:LI{0}:{1}1'.format(ele_name[3:5],ele_name[6:8]): ( float(bmadEnld), float(bmadPhas), float(bmadEnld) > 1 ) for (_, ele_name, _, _, _, bmadEnld, bmadPhas) in splits}

def convert_device_to_element(device_name):
    return 'O_K{0}_{1}'.format(device_name[7:9],device_name[10])

class KlystronService(simulacrum.Service):
    attr_for_klys_type = {"ENLD": "ENLD_MeV", "PHAS":"PHAS_Deg"} 
    def __init__(self):
        super().__init__()
        self.ctx = Context.instance()
        #cmd socket is a synchronous socket, we don't want the asyncio context.
        self.cmd_socket = zmq.Context().socket(zmq.REQ)
        self.cmd_socket.connect("tcp://127.0.0.1:{}".format(os.environ.get('MODEL_PORT', 12312)))
        init_vals = self.get_klystron_ACTs_from_model()
        klys_pvs = {device_name: KlystronPV(device_name, convert_device_to_element(device_name), self.on_klystron_change, initial_values=init_vals[device_name], prefix=device_name) 
                    for device_name in init_vals.keys()} 
        print(init_vals)
        self.add_pvs(klys_pvs)
                                                            
        print("Initialization complete.")

    def get_klystron_ACTs_from_model(self):
        init_vals = {}
        for (attr, dev_list, parse_func) in [("ENLD_MeV", "O_K*", _parse_klys_table)]:
            self.cmd_socket.send_pyobj({"cmd": "tao", "val": "show lat -no_label_lines -attribute ENLD_MeV -attribute Phase_Deg O_K*"})
            table = self.cmd_socket.recv_pyobj()
            init_vals.update(parse_func(table['result']))
        return init_vals
 
    def on_klystron_change(self, klystron_pv, value, parameter):
        element = klystron_pv.element_name
        if parameter == "PHAS":
            klys_attr = "Phase_Deg"
        elif parameter == "ENLD": 
            klys_attr = "ENLD_MeV"
        elif parameter == "BEAMCODE1_STAT":
            klys_attr = "is_on"
            value =  'T' if value else 'F'
            element = element[2:]+'*'  #O_K30_8 overlay to K30_8*
        cmd = f'set ele {element} {klys_attr} = {value}'
        print(cmd)
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": cmd})
        print(self.cmd_socket.recv_pyobj())
        self.cmd_socket.send_pyobj({"cmd": "send_orbit"})
        self.cmd_socket.recv_pyobj()
   
def main():
    service = KlystronService()
    loop = asyncio.get_event_loop()
    _, run_options = ioc_arg_parser(
        default_prefix='',
        desc="Simulated Klystron Service")
    run(service, **run_options)
    
if __name__ == '__main__':
    main()
    



        
