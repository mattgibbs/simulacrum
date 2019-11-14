import os
import sys
import asyncio
import json
import functools
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
        self.bctrl._data['value'] = float(initial_value['bact'])
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
        instance._data['value'] = value
        await ioc.bdes.write(value)
        await ioc.ctrl.write("PERTURB")
        return value
    
    @bact.putter
    async def bact(self, instance, value):
        ioc = instance.group
        bctrl_val = self.bctrl._data['value']
        if bctrl_val != value:
            print("bctrl = {}, value = {}".format(bctrl_val, value))
            self.bctrl._data['value'] = value
            await self.bctrl.publish(0)
        return value
    
    @bdes.putter
    async def bdes(self, instance, value):
        ioc = instance.group
        self.bdes_for_undo = ioc.bdes.value
        return value
    
    @bact.putter
    async def bact(self, instance, value):
        ioc = instance.group
        self.bctrl._data['value'] = value
        await self.bctrl.publish(0)
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
        # Lets do some custom additions to handle bend magnets.
        self.add_pvs(self.make_bx02_pv()) #BX02 is the power supply for the DL1 bend string
        self.add_pvs(self.make_byd1_pv()) #BYD1 is the power supply for the BYD bend string
        self.add_pvs(self.make_bx12_pv()) #BX12 is the power supply for the BC1 bend string
        self.add_pvs(self.make_bx22_pv()) #BX22 is the power supply for the BC2 bend string
        
        # Now that we've set up all the magnets, we need to send the model a
        # command to use non-normalized magnetic field units.
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "set ele Kicker::*,Quadrupole::*,Sbend::* field_master = T"})
        self.cmd_socket.recv_pyobj()
        L.info("Initialization complete.")
    
    def make_bx02_pv(self):
        bx02_name = "BEND:IN20:751"
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "show lat -no_label_lines -attribute b_field -attribute g BX02*"})
        _, _, _, _, l, b_init_tesla, g = self.cmd_socket.recv_pyobj()['result'][0].split()
        # b_init_gevc = -1 * speed of light * b_init_tesla / (g * 10**9)
        g = float(g)
        b_init_tesla = float(b_init_tesla)
        b_init_gevc = -1.0 * 2.99792458e8 * b_init_tesla / (g * 10**9)
        print("BX02 init strength in GeV/c = ", b_init_gevc)
        print("BX02 init strength in Tesla = ", b_init_tesla)
        init_vals = {"length": float(l), "bact": b_init_gevc, "units": "GeV/c"} 
        dl1_partial = functools.partial(self.on_dl1_change, b_init_tesla, g)
        return {bx02_name: MagnetPV(bx02_name, simulacrum.util.convert_device_to_element(bx02_name), dl1_partial, length=float(l), initial_value=init_vals, prefix=bx02_name)}
    
    def make_byd1_pv(self):
        byd1_name = "BEND:DMPH:400"
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "show lat -no_label_lines -attribute b_field -attribute g BX31*"})
        _, _, _, _, l, b_init_bx31_tesla, g_bx31 = self.cmd_socket.recv_pyobj()['result'][0].split()
        g_bx31 = float(g_bx31)
        b_init_bx31_tesla = float(b_init_bx31_tesla)
        # b_init_gevc = -1 * speed of light * b_init_tesla / (g * 10**9)
        b_init_bx31_gevc = -1.0 * 2.99792458e8 * b_init_bx31_tesla / (g_bx31 * 10**9)
        init_vals = {"length": float(l), "bact": b_init_bx31_gevc, "units": "GeV/c"}
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "show lat -no_label_lines -attribute b_field -attribute g BX35*"})
        _, _, _, _, _, b_init_bx35_tesla, g_bx35 = self.cmd_socket.recv_pyobj()['result'][0].split()
        g_bx35 = float(g_bx35)
        b_init_bx35_tesla = float(b_init_bx35_tesla)
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "show lat -no_label_lines -attribute b_field -attribute g BYD*"})
        _, _, _, _, _, b_init_byd1_tesla, g_byd1 = self.cmd_socket.recv_pyobj()['result'][0].split()
        g_byd1 = float(g_byd1)
        b_init_byd1_tesla = float(b_init_byd1_tesla)
        #def on_dl2_change(self, b_init_bx31, b_init_bx35, b_init_byd1, g_bx31, g_bx35, g_byd1, magnet_pv, value)
        byd1_partial = functools.partial(self.on_dl2_change, b_init_bx31_tesla, b_init_bx35_tesla, b_init_byd1_tesla, g_bx31, g_bx35, g_byd1)
        return {byd1_name: MagnetPV(byd1_name, simulacrum.util.convert_device_to_element(byd1_name), byd1_partial, length=float(l), initial_value=init_vals, prefix=byd1_name)}
    
    def make_bx12_pv(self):
        bx12_name = "BEND:LI21:231"
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "show lat -no_label_lines -attribute b_field -attribute g BX12*"})
        _, _, _, _, l_bx12, b_init_bx12_tesla, g_bx12 = self.cmd_socket.recv_pyobj()['result'][0].split()
        l_bx12 = float(l_bx12)
        g_bx12 = float(g_bx12)
        b_init_bx12_tesla = float(b_init_bx12_tesla)
        # b_init_kgm = 10.0 * b_init_tesla * l
        b_init_bx12_kgm = -10.0 * b_init_bx12_tesla * l_bx12
        init_vals = {"length": l_bx12, "bact": b_init_bx12_kgm, "units": "kG-m"}
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "show lat -no_label_lines -attribute b_field -attribute g BX11*"})
        _, _, _, _, l_bx11, b_init_bx11_tesla, g_bx11 = self.cmd_socket.recv_pyobj()['result'][0].split()
        l_bx11 = float(l_bx11)
        g_bx11 = float(g_bx11)
        b_init_bx11_tesla = float(b_init_bx11_tesla)
        # b_init_kgm = 10.0 * b_init_tesla * l
        b_init_bx11_kgm = -10.0 * b_init_bx11_tesla * l_bx11
        #def on_bc2_change(self, b_init_bx11, b_init_bx12, g_bx11, g_bx12, value)
        bx12_partial = functools.partial(self.on_bc1_change, b_init_bx11_tesla, b_init_bx12_tesla, l_bx11, l_bx12)
        return {bx12_name: MagnetPV(bx12_name, simulacrum.util.convert_device_to_element(bx12_name), bx12_partial, length=float(l_bx12), initial_value=init_vals, prefix=bx12_name)}
    
    def make_bx22_pv(self):
        bx22_name = "BEND:LI24:790"
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "show lat -no_label_lines -attribute b_field -attribute g BX22*"})
        _, _, _, _, l_bx22, b_init_bx22_tesla, g_bx22 = self.cmd_socket.recv_pyobj()['result'][0].split()
        l_bx22 = float(l_bx22)
        g_bx22 = float(g_bx22)
        b_init_bx22_tesla = float(b_init_bx22_tesla)
        # b_init_kgm = 10.0 * b_init_tesla * l
        b_init_bx22_kgm = -10.0 * b_init_bx22_tesla * l_bx22
        init_vals = {"length": l_bx22, "bact": b_init_bx22_kgm, "units": "kG-m"}
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "show lat -no_label_lines -attribute b_field -attribute g BX21*"})
        _, _, _, _, l_bx21, b_init_bx21_tesla, g_bx21 = self.cmd_socket.recv_pyobj()['result'][0].split()
        l_bx21 = float(l_bx21)
        g_bx21 = float(g_bx21)
        b_init_bx21_tesla = float(b_init_bx21_tesla)
        # b_init_kgm = 10.0 * b_init_tesla * l
        b_init_bx21_kgm = -10.0 * b_init_bx21_tesla * l_bx21
        #def on_bc2_change(self, b_init_bx11, b_init_bx12, g_bx11, g_bx12, value)
        bx22_partial = functools.partial(self.on_bc2_change, b_init_bx21_tesla, b_init_bx22_tesla, l_bx21, l_bx22)
        return {bx22_name: MagnetPV(bx22_name, simulacrum.util.convert_device_to_element(bx22_name), bx22_partial, length=float(l_bx22), initial_value=init_vals, prefix=bx22_name)}
    
    def get_magnet_list_from_model(self):
        element_list = []
        # Until bend overlays are working better, I am not simulating them.
        # self.cmd_socket.send_pyobj({"cmd": "tao", "val": "show ele -no_slaves Kicker::*,Quadrupole::*,Sbend::*"})
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "show ele -no_slaves Kicker::*,Quadrupole::*"})
        for row in self.cmd_socket.recv_pyobj()['result'][:-1]:
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
        
    def on_bc1_change(self, b_init_bx11, b_init_bx12, l_bx11, l_bx12, magnet_pv, value):
        self.chicane_bend_change(b_init_bx11, l_bx11, "BX11*,BX14*", value)
        self.chicane_bend_change(b_init_bx12, l_bx12, "BX12*,BX13*", -1.0 * value)
    
    def on_bc2_change(self, b_init_bx21, b_init_bx22, l_bx21, l_bx22, magnet_pv, value):
        self.chicane_bend_change(b_init_bx21, l_bx21, "BX21*,BX24*", value)
        self.chicane_bend_change(b_init_bx22, l_bx22, "BX22*,BX23*", -1.0 * value)
    
    def on_dl1_change(self, b_init, g, magnet_pv, value):
        self.dl_bend_change(b_init, g, "BX02*,BX01*", value)
    
    def on_dl2_change(self, b_init_bx31, b_init_bx35, b_init_byd1, g_bx31, g_bx35, g_byd1, magnet_pv, value):
        self.dl_bend_change(b_init_bx31, g_bx31, "BX31*,BX32*", value)
        self.dl_bend_change(b_init_bx35, g_bx35, "BX35*,BX36*", value)
        self.dl_bend_change(b_init_byd1, g_byd1, "BYD*", value)
        
    def chicane_bend_change(self, b_init, l, element_name, value):
        L.debug(f"Changing {element_name} value to {value} kG*m")
        L.debug(f"l = {l}")
        L.debug(f"b_init = {b_init}")
        b_field = value / (10.0 * l)
        L.debug("New b_field in tesla:", b_field)
        b_err = b_field - b_init
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": f"set ele {element_name} b_field_err = {b_err}"})
        self.cmd_socket.recv_pyobj()
        L.debug("%s bend strength changed to %s (T)", element_name, b_field)
        
    def dl_bend_change(self, b_init, g, element_name, value):
        L.debug(f"Changing {element_name} value to {value} GeV/c")
        L.debug(f"g = {g}")
        L.debug(f"b_init = {b_init}")
        # value is in GeV/c units for DL1.
        # convert to Tesla:
        b_field = -1.0 * value * 10**9 * g / 2.99792458e8
        L.debug("New b_field in tesla:", b_field)
        # Put the change into the b_err field.
        # (You have to do this for bends, otherwise Tao changes the bend angle, which is not what you want)
        b_err = b_field - b_init
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": f"set ele {element_name} b_field_err = {b_err}"})
        self.cmd_socket.recv_pyobj()
        L.debug("%s bend strength changed to %s (T)", element_name, b_field)

    def on_magnet_change(self, magnet_pv, value):
        """ This method gets called any time a PV updates for XCORs, YCORs, or QUADs. """
        mag_type = magnet_pv.device_name.split(":")[0]
        mag_attr = self.attr_for_mag_type[mag_type]
        conv = self.conversion_to_BMAD_for_mag_type[mag_type]
        l = magnet_pv.length
        L.debug('Updating {}... '.format( magnet_pv.device_name ) )
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "set ele {element} {attr} = {val}".format(element=magnet_pv.element_name, 
                                                                                                   attr=mag_attr,
                                                                                                   val=conv(value, l))})
        self.cmd_socket.recv_pyobj()
        L.debug('Updated {}.'.format(magnet_pv.device_name))
       
def main():
    service = MagnetService()
    loop = asyncio.get_event_loop()
    _, run_options = ioc_arg_parser(
        default_prefix='',
        desc="Simulated Magnet Service")
    run(service, **run_options)
    
if __name__ == '__main__':
    main()
    
    
