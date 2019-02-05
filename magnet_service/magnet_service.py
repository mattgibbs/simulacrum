import os
import asyncio
from collections import OrderedDict
from caproto.server import ioc_arg_parser, run, pvproperty, PVGroup
from caproto import ChannelType
import simulacrum
import zmq
from zmq.asyncio import Context

class MagnetPV(PVGroup):
    bcon = pvproperty(value=0.0, name=':BCON')
    bdes = pvproperty(value=0.0, name=':BDES')
    bact = pvproperty(value=0.0, name=':BACT', read_only=True)
    ctrl_strings = ("Ready", "TRIM", "PERTURB", "BCON_TO_BDES", "SAVE_BDES",
                    "LOAD_BDES", "UNDO_BDES", "DAC_ZERO", "CALB", "STDZ",
                    "RESET", "TURN_ON", "TURN_OFF")                
    ctrl = pvproperty(value=0, name=':CTRL', dtype=ChannelType.ENUM,
                      enum_strings=ctrl_strings)
    def __init__(self, device_name, element_name, change_callback, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device_name = device_name
        self.element_name = element_name
        self.saved_bdes = None
        self.bdes_for_undo = None
        self.change_callback = change_callback
        
    @ctrl.putter
    async def ctrl(self, instance, value):
        ioc = instance.group
        if value == "PERTURB":
            await ioc.bact.write(ioc.bdes.value)
            self.change_callback(self, ioc.bact.value)
        elif value == "TRIM":
            await asyncio.sleep(0.2)
            await ioc.bact.write(ioc.bdes.value)
            self.change_callback(self, ioc.bact.value)
        elif value == "BCON_TO_BDES":
            await ioc.bdes.write(ioc.bcon.value)
        elif value == "SAVE_BDES":
            self.saved_bdes = ioc.bdes.value
        elif value == "LOAD_BDES":
            if self.saved_bdes:
                await ioc.bdes.write(self.saved_bdes)
        elif value == "UNDO_BDES":
            if self.bdes_for_undo:
                await ioc.bdes.write(self.bdes_for_undo)
        else:
            print("Warning, using a non-implemented magnet control function.")
        return 0
    
    @pvproperty(value=0.0, name=":BCTRL")
    async def bctrl(self, instance):
        # We have to do some hacky stuff with caproto private data
        # because otherwise, the putter method gets called any time
        # we read.
        ioc = instance.group
        instance._data['value'] = ioc.bact.value
        return None
    
    @bctrl.putter
    async def bctrl(self, instance, value):
        ioc = instance.group
        await ioc.bdes.write(value)
        await ioc.ctrl.write("PERTURB")
        return value
    
    @bdes.putter
    async def bdes(self, instance, value):
        ioc = instance.group
        self.bdes_for_undo = ioc.bdes.value
        return value

class MagnetService(simulacrum.Service):
    attr_for_mag_type = {"XCOR": "hkick", "YCOR": "vkick", "QUAD": "k1", "BEND": "angle"}
    
    def __init__(self):
        super().__init__()
        mag_pvs = {device_name: MagnetPV(device_name, simulacrum.util.convert_device_to_element(device_name), self.on_magnet_change, prefix=device_name) 
                    for device_name in simulacrum.util.device_names 
                    if device_name.startswith("XCOR") or device_name.startswith("YCOR") or device_name.startswith("QUAD") or device_name.startswith("BEND")}
        self.add_pvs(mag_pvs)
        self.ctx = Context.instance()
        #cmd socket is a synchronous socket, we don't want the asyncio context.
        self.cmd_socket = zmq.Context().socket(zmq.REQ)
        self.cmd_socket.connect("tcp://127.0.0.1:{}".format(os.environ.get('MODEL_PORT', 12312)))
        print("Initialization complete.")
    
    def on_magnet_change(self, magnet_pv, value):
        mag_attr = self.attr_for_mag_type[magnet_pv.device_name.split(":")[0]]
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "set ele {element} {attr} = {val}".format(element=magnet_pv.element_name, 
                                                                                                   attr=mag_attr,
                                                                                                   val=value)})
        print(self.cmd_socket.recv_pyobj())
        self.cmd_socket.send_pyobj({"cmd": "send_orbit"})
        self.cmd_socket.recv_pyobj()
                                                                                                  

def main():
    service = MagnetService()
    loop = asyncio.get_event_loop()
    _, run_options = ioc_arg_parser(
        default_prefix='',
        desc="Simulated Magnet Service")
    run(service, **run_options)
    
if __name__ == '__main__':
    main()
    
    