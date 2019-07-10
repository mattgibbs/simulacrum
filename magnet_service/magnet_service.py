import os
import sys
import asyncio
import json
from collections import OrderedDict
from caproto.server import ioc_arg_parser, run, pvproperty, PVGroup
from caproto.server.records import _Limits
from caproto import ChannelType
import simulacrum
import zmq
from zmq.asyncio import Context

#set up python logger
L = simulacrum.util.SimulacrumLog(os.path.splitext(os.path.basename(__file__))[0], level='INFO')

class MagnetPV(PVGroup):
    bcon = pvproperty(value=0.0, name=':BCON')
    bdes = pvproperty(value=0.0, name=':BDES')
    bact = pvproperty(value=0.0, name=':BACT', read_only=True)
    bmin = pvproperty(value=0.0, name=':BMIN', read_only=True)
    bmax = pvproperty(value=0.0, name=':BMAX', read_only=True)
    ctrl_strings = ("Ready", "TRIM", "PERTURB", "BCON_TO_BDES", "SAVE_BDES",
                    "LOAD_BDES", "UNDO_BDES", "DAC_ZERO", "CALB", "STDZ",
                    "RESET", "TURN_ON", "TURN_OFF")                
    ctrl = pvproperty(value=0, name=':CTRL', dtype=ChannelType.ENUM,
                      enum_strings=ctrl_strings)
    func = pvproperty(value=0, name=':FUNC', dtype=ChannelType.ENUM,
                      enum_strings=ctrl_strings)
    madname = pvproperty(name=":MADNAME", read_only=True, dtype=ChannelType.STRING)
    statmsg = pvproperty(value=0, name=':STATMSG', read_only=True, dtype=ChannelType.ENUM,
        enum_strings=("Good", "BCON Warning", "Offline", "PAU Ctrl", "Turned Off", "Not Degaus'd",
                      "Not Cal'd", "Feedback Ctrl", "Tripped", "DAC Error", "ADC Error", "Not Stdz'd",
                      "Out-of-Tol", "BAD Ripple", "BAD BACT", "No Control"))
    abort = pvproperty(value=0, name=':ABORT', dtype=ChannelType.ENUM,
                      enum_strings=("Ready", "Abort"))
    select = pvproperty(value=0, name=':SELECT', dtype=ChannelType.ENUM, enum_strings=("NO", "YES"))
    selecten = pvproperty(value=0, name=':SELECTEN', dtype=ChannelType.ENUM, enum_strings=("NO", "YES"))
    bdesegu = pvproperty(name=":BDES.EGU", read_only=True, dtype=ChannelType.STRING)
    bactegu = pvproperty(name=":BACT.EGU", read_only=True, dtype=ChannelType.STRING)
    bctrlegu = pvproperty(name=":BCTRL.EGU", read_only=True, dtype=ChannelType.STRING)
    bconegu = pvproperty(name=":BCON.EGU", read_only=True, dtype=ChannelType.STRING)
    
    def __init__(self, device_name, element_name, change_callback, length, initial_value, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device_name = device_name
        self.element_name = element_name
        self.length = length
        self.saved_bdes = None
        self.bdes_for_undo = None
        self.madname._data['value'] = element_name
        self.bcon._data['value'] = float(initial_value['bact'])
        self.bdes._data['value'] = float(initial_value['bact'])
        self.bact._data['value'] = float(initial_value['bact'])
        if 'precision' in initial_value:
            prec = int(initial_value['precision'])
            self.bcon._data['precision'] = prec
            self.bdes._data['precision'] = prec
            self.bact._data['precision'] = prec
            self.bctrl._data['precision'] = prec
        if 'units' in initial_value:
            egu = initial_value['units']
            self.bcon._data['units'] = egu
            self.bdes._data['units'] = egu
            self.bact._data['units'] = egu
            self.bctrl._data['units'] = egu
            self.bconegu._data['value'] = egu
            self.bdesegu._data['value'] = egu
            self.bactegu._data['value'] = egu
            self.bctrlegu._data['value'] = egu
            self.bmin._data['units'] = egu
            self.bmax._data['units'] = egu
        if 'upper_ctrl_limit' in initial_value:
            hopr = float(initial_value['upper_ctrl_limit'])
            self.bcon._data['upper_ctrl_limit'] = hopr
            self.bdes._data['upper_ctrl_limit'] = hopr
            self.bact._data['upper_ctrl_limit'] = hopr
            self.bctrl._data['upper_ctrl_limit'] = hopr
            self.bctrl._data['upper_disp_limit'] = hopr
            self.bmax._data['value'] = hopr
        if 'lower_ctrl_limit' in initial_value:
            lopr = float(initial_value['lower_ctrl_limit'])
            self.bcon._data['lower_ctrl_limit'] = lopr
            self.bdes._data['lower_ctrl_limit'] = lopr
            self.bact._data['lower_ctrl_limit'] = lopr
            self.bctrl._data['lower_ctrl_limit'] = lopr
            self.bctrl._data['lower_disp_limit'] = lopr
            self.bmin._data['value'] = lopr
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
           L.warning("Warning, using a non-implemented magnet control function.")
        return 0
    
    @pvproperty(value=0.0, name=":BCTRL", mock_record='ao')
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

def _parse_corr_table(table):
    """ Build a dictionary of element_name -> (BACT)."""
    # We use the 'tesla_to_kGm' function here for both bends and quads,
    # even though quads actually just use kG units (not kG*m).
    # This is because BMAD specifies quad strength as a gradient (T/m),
    # so the math is the same for quads and bends.
    splits = [row.split() for row in table]
    return {simulacrum.util.convert_element_to_device(ele_name): {"length": float(l), "bact": bl_kick_to_BACT(float(bl_kick))} for (_, ele_name, _, _, l, bl_kick) in splits if ele_name in simulacrum.util.element_names}

def _parse_quad_table(table):
    splits = [row.split() for row in table]
    return {simulacrum.util.convert_element_to_device(ele_name): {"length": float(l), "bact": quad_gradient_to_BACT(float(b1_gradient), float(l))} for (_, ele_name, _, _, l, b1_gradient) in splits if ele_name in simulacrum.util.element_names}

def _parse_bend_table(table):
    splits = [row.split() for row in table]
    return {simulacrum.util.convert_element_to_device(ele_name): {"length": float(l), "bact": bend_b_field_to_BACT(float(b_field), float(l))} 
        for (_, ele_name, _, _, l, b_field) in splits if ele_name in simulacrum.util.element_names}

def bl_kick_to_BACT(bl_kick, l=None):
    """Convert the bl_kick attribute (T*m) for a corrector into SLAC BACT compatible kG*m units"""
    return -bl_kick*10.0

def BACT_to_bl_kick(bact, l=None):
    """Convert SLAC corrector BACT (kG*m) into BMAD compatible T*m units"""
    return -bact/10.0

def quad_gradient_to_BACT(b1_gradient, l):
    """Convert the b1_gradient (T/m) attribute for a quad into SLAC BACT kG units"""
    return -b1_gradient*10.0*l

def quad_BACT_to_gradient(bact, l):
    """Convert a SLAC quad BACT (kG) into BMAD b1_gradient T/m units"""
    return -bact/(10.0*l)                                                                                                  

def bend_BACT_to_b_field(bact, l):
    """Convert a SLAC bend BACT (GeV/c) into BMAD b_field T units"""
    return -bact*9.06721219/l

def bend_b_field_to_BACT(b_field, l):
    """Convert a BMAD b_field (T) into SLAC bend BACT (GeV/c)"""
    return -b_field*.11028748186*l

class MagnetService(simulacrum.Service):
    attr_for_mag_type = {"XCOR": "bl_hkick", "YCOR": "bl_vkick", "QUAD": "b1_gradient", "BEND": "b_field"}
    conversion_to_BMAD_for_mag_type = {"XCOR": BACT_to_bl_kick, "YCOR": BACT_to_bl_kick, "QUAD": quad_BACT_to_gradient, "BEND": bend_BACT_to_b_field}
    def __init__(self):
        super().__init__()
        self.ctx = Context.instance()
        #cmd socket is a synchronous socket, we don't want the asyncio context.
        self.cmd_socket = zmq.Context().socket(zmq.REQ)
        self.cmd_socket.connect("tcp://127.0.0.1:{}".format(os.environ.get('MODEL_PORT', 12312)))
        init_vals = self.get_initial_values()
        magnet_element_list = self.get_magnet_list_from_model()
        magnet_device_list = [simulacrum.util.convert_element_to_device(element) for element in magnet_element_list]
        mag_pvs = {device_name: MagnetPV(device_name, simulacrum.util.convert_device_to_element(device_name), self.on_magnet_change, length=init_vals[device_name]['length'], initial_value=init_vals[device_name], prefix=device_name) 
                    for device_name in magnet_device_list
                    if device_name in init_vals}
        self.add_pvs(mag_pvs)
        # Now that we've set up all the magnets, we need to send the model a
        # command to use non-normalized magnetic field units.
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "set ele Kicker::*,Quadrupole::* field_master = T"})
        self.cmd_socket.recv_pyobj()
        L.info("Initialization complete.")
    
    def get_magnet_list_from_model(self):
        element_list = []
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "show ele Kicker::*,Quadrupole::*,Sbend::*"})
        for row in self.cmd_socket.recv_pyobj()['result']:
            print(row)
            element_list.append(row.split(None, 3)[1])
        return element_list
    
    def get_initial_values(self):
        init_vals = self.get_magnet_BACTs_from_model()
        path_to_limits_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "magnet_limits.json")
        with open(path_to_limits_file) as f:
            limits = json.load(f)
            for device_name in init_vals:
                try:
                    init_vals[device_name]["units"] = limits[device_name]["EGU"]
                    init_vals[device_name]["precision"] = limits[device_name]["PREC"]
                    init_vals[device_name]["upper_ctrl_limit"] = limits[device_name]["HOPR"]
                    init_vals[device_name]["lower_ctrl_limit"] = limits[device_name]["LOPR"]
                except KeyError:
                    pass
        return init_vals
    
    def get_magnet_BACTs_from_model(self):
        init_vals = {}
        for (attr, dev_list, parse_func) in [("bl_hkick", "Kicker::X*", _parse_corr_table), ("bl_vkick", "Kicker::Y*", _parse_corr_table), ("b1_gradient", "Quadrupole::*", _parse_quad_table), ("b_field", "Sbend::*", _parse_bend_table)]:
            self.cmd_socket.send_pyobj({"cmd": "tao", "val": "show lat -no_label_lines -attribute {attr} {list}".format(attr=attr, list=dev_list)})
            table = self.cmd_socket.recv_pyobj()
            init_vals.update(parse_func(table['result']))
        return init_vals
        
    def on_magnet_change(self, magnet_pv, value):
        mag_type = magnet_pv.device_name.split(":")[0]
        mag_attr = self.attr_for_mag_type[mag_type]
        conv = self.conversion_to_BMAD_for_mag_type[mag_type]
        l = magnet_pv.length
        L.debug('Updating {}... '.format( magnet_pv.device_name ) )
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "set ele {element} {attr} = {val}".format(element=magnet_pv.element_name, 
                                                                                                   attr=mag_attr,
                                                                                                   val=conv(value, l))})
        
        self.cmd_socket.recv_pyobj()
        L.debug('Updated {}.'.format( magnet_pv.device_name ) )
        self.cmd_socket.send_pyobj({"cmd": "send_orbit"})
        self.cmd_socket.recv_pyobj()
        self.cmd_socket.send_pyobj({"cmd": "send_profiles_twiss"})
        self.cmd_socket.recv_pyobj()
        self.cmd_socket.send_pyobj({"cmd": "send_und_twiss"})
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
    
    
