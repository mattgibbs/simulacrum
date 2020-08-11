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

class CudKlys(PVGroup):
    """
    Represents the PVs used by the Klystron CUD.
    Every PV in here is just a static value, driven by
    the Klystron CUD MATLAB process. 
    """
    onbeam1 = pvproperty(value=0.0, name=':ONBEAM1')
    status = pvproperty(value=0.0, name=':STATUS')
    statusdesc = pvproperty(value='None', name=':STATUS.DESC', dtype=ChannelType.STRING)
    def __init__(self, device_name, element_name, initial_value, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device_name = device_name
        self.element_name = element_name
        self.onbeam1._data['value'] = initial_value
        self.status._data['value'] = initial_value

class SubboosterPV(PVGroup):
    """
    Represents the PVs for a subbooster.  Currently these
    don't actually do anything, but some displays use them.
    """
    pdes = pvproperty(value=0.0, name=':PDES')  
    phas = pvproperty(value=0.0, name=':PHAS', read_only=True)
    poly = pvproperty(value=np.zeros(6), name=':POLY', dtype=ChannelType.DOUBLE)
    def __init__(self, device_name, element_name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device_name = device_name
        self.element_name = element_name

class KlystronPV(PVGroup):
    pdes = pvproperty(value=0.0, name=':PDES', precision=1)  
    phas = pvproperty(value=0.0, name=':PHAS', read_only=True, precision=1)
    enld = pvproperty(value=0.0, name=':ENLD')
    ades = pvproperty(value=100.0, name=':ADES', precision=1)
    ampl = pvproperty(value=100.0, name=':AMPL', precision=1)
    bvjt = pvproperty(value=0.0, name=':BVJT')
    alem = pvproperty(value=0.0, name=':ALEM')
    plem = pvproperty(value=0.0, name=':PLEM')
    eglem = pvproperty(value=0.0, name=':EGLEM')
    chlem = pvproperty(value=0.0, name=':CHLEM')
    mkbvftpjasigma = pvproperty(value=0.0, name=':MKBVFTPJASIGMA')
    poly = pvproperty(value=np.zeros(6), name=':POLY', dtype=ChannelType.DOUBLE)
    # The seemingly random numbers in clear_* are the values these status
    # PVs have when a klystron is working normally, with no faults.
    clear_swrd = 0
    clear_hdsc = 32
    clear_dsta = [1610612737, 528640]
    clear_stat = 1
    swrd = pvproperty(value=clear_swrd, name=':SWRD')
    hdsc = pvproperty(value=clear_hdsc, name=':HDSC')
    dsta = pvproperty(value=clear_dsta, name=':DSTA')
    stat = pvproperty(value=clear_stat, name=':STAT')
    bc1_tctl =  pvproperty(value=0, name=':BEAMCODE1_TCTL', dtype=ChannelType.ENUM,
                            enum_strings=("Deactivate", "Reactivate", "Activate"))
    bc1_tstat = pvproperty(value=0, name=':BEAMCODE1_TSTAT', dtype=ChannelType.ENUM,
                            enum_strings=("Deactivated", "Activated"), read_only=True)
    #BEAMCODE1_STAT represents the same data as BEAMCODE1_TSTAT, but does it as a float, not an enum.  2=off 1=on.
    bc1_stat =  pvproperty(value=2, name=':BEAMCODE1_STAT', read_only=True)
    trim = pvproperty(value=0, name=':TRIMPHAS', dtype=ChannelType.ENUM,
                      enum_strings=("Done", "TRIM"))
    mod_reset = pvproperty(value=0, name=':MOD:RESET', dtype=ChannelType.ENUM,
                      enum_strings=("Done", "RESET"))
    mod_hv_ctrl = pvproperty(value=1, name=':MOD:HVON_SET', dtype=ChannelType.ENUM,
                      enum_strings=("OFF", "ON"))
    def __init__(self, device_name, element_name, change_callback, initial_values, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device_name = device_name 
        self.element_name = element_name
        self.orig_enld = initial_values[0]
        self.tripped = False
        self.hv_ctrl_on = True
        self.has_accel_triggers = True
        self.enld._data['value'] = initial_values[0]
        self.pdes._data['value'] = initial_values[1]
        self.phas._data['value'] = initial_values[1]  
        self.bc1_tctl._data['value'] = 1
        self.bc1_tstat._data['value'] = 1
        self.bc1_stat._data['value'] = 1
        self.change_callback = change_callback 

    async def interlock_trip(self):
        if self.tripped:
            return
        self.tripped = True
        dsta1, dsta2 = self.dsta.value
        dsta2 = dsta2 & ~(1 << 3) #Turn off "Mod interlocks complete"
        dsta2 = dsta2 & ~(1 << 7) #Turn off "Mod HV on"
        self.dsta._data['value'] = [dsta1, dsta2]
        await self.dsta.publish(0)
        await self.mod_hv_ctrl.write('OFF') # Only for SimUI
        await self.on_off_changed()
    
    @mod_reset.putter
    async def mod_reset(self, instance, value):
        ioc = instance.group
        if value == "RESET":
            dsta2 = self.clear_dsta[1]
            dsta2 = dsta2 & ~(1 << 7) #Keep "Mod HV on" bit zeroed
            dsta2 = dsta2 | (1 << 4) #Turn on the "Mod HV Ready" bit
            self.dsta._data['value'] = [self.clear_dsta[0], dsta2]
            self.swrd._data['value'] = self.clear_swrd
            self.hdsc._data['value'] = self.clear_hdsc
            # Note, mod reset doesn't change the STAT PV.
            await asyncio.gather(
                self.dsta.publish(0),
                self.swrd.publish(0),
                self.hdsc.publish(0))
            self.tripped = False
        return 0

    @mod_hv_ctrl.putter
    async def mod_hv_ctrl(self, instance, value):
        if value == "ON":
            await self.mod_on()
        else:
            await self.mod_off()
        
        return value

    async def mod_on(self):
        if self.tripped or self.hv_ctrl_on:
            return
        dsta1, dsta2 = self.dsta.value
        dsta2 = dsta2 | (1 << 7) #Turn on the "Mod HV On" bit
        dsta2 = dsta2 & ~(1 << 4) #Turn off the "Mod HV Ready" bit
        self.dsta._data['value'] = [dsta1, dsta2]
        await self.dsta.publish(0)
        self.hv_ctrl_on = True
        await self.on_off_changed()
    
    async def mod_off(self, hv_ready=True):
        #if self.tripped or (not self.hv_ctrl_on):
        if not self.hv_ctrl_on:
            return
        dsta1, dsta2 = self.dsta.value
        dsta2 = dsta2 & ~(1 << 7) #Zero the "Mod HV On" bit
        if hv_ready:
            dsta2 = dsta2 | (1 << 4) #Turn on the "Mod HV Ready" bit
        self.dsta._data['value'] = [dsta1, dsta2]
        await self.dsta.publish(0)
        self.hv_ctrl_on = False
        await self.on_off_changed()

    @swrd.putter
    async def swrd(self, instance, value):
        ioc = instance.group
        """
        SWRD bit decoder:
        bit | meaning          | klystron faulted if bit set?
        -----------------------------------------------------
        0   | Bad Cable Status | Faulted
        1   | MKSU Protect     | Faulted
        2   | No Triggers      | Faulted
        3   | Modulator Fault  | Faulted
        4   | Lost Acc Trigger | Faulted
        5   | Low RF Power     | Faulted
        6   | Amplitude Mean   | Not Faulted
        7   | Amplitude Jitter | Not Faulted
        8   | Lost Phase       | Faulted
        9   | Phase Mean       | Not Faulted
        10  | Phase Jitter     | Not Faulted
        11  | No Sample Rate   | Not Faulted
        12  | No Accel Rate    | Faulted 
        """
        fault_mask = 0b1000100111111
        if (int(value) & fault_mask) > 0:
            await self.interlock_trip()
        return value
            
    @hdsc.putter
    async def hdsc(self, instance, value):
        ioc = instance.group
        """
        HDSC bit decoder:
        bit | meaning               | klystron faulted if bit set?
        ---------------------------------------------
        0   | Phase Trim Disabled   | Not Faulted
        1   | Maintenance Mode      | Faulted
        2   | To Be Replaced        | Faulted
        3   | Awaiting Run Up       | Faulted
        4   | Additional Phase Ctrl | Not Faulted
        5   | No Touch Up           | Not Faulted
        6   | Check Phase           | Not Faulted
        7   | 14:1 Winding Ratio    | Not Faulted
        8   | Designated Spare      | Not Faulted
        9   | Solid State Ph Shiftr | Not Faulted
        10  | Controlled by EPICS   | Not Faulted
        11  | Powers Transverse RF  | Not Faulted
        12  | Power Savings Mode    | Faulted 
        """
        fault_mask = 0b1000000001110
        if (int(value) & fault_mask) > 0:
            await self.interlock_trip()
        return value

    @stat.putter
    async def stat(self, instance, value):
        ioc = instance.group
        """
        STAT bit decoder:
        bit | meaning               | klystron HV off if bit set?
        ---------------------------------------------
        0   | Status OK             | Not Faulted
        1   | Status Maintenance    | Faulted
        2   | Status Unit Offline   | Faulted
        3   | Status Out of Tol     | Not Faulted
        4   | Status Bad CAMAC      | Not Faulted
        5   | Status SWRD Error     | Not Faulted
        6   | Dead Man Timeout      | Faulted
        7   | Fox Phase Home Error  | Not Faulted
        8   | Phase Mean Out of Tol | Not Faulted
        9   | Status IPL Required   | Not Faulted
        10  | Status Update Request | Not Faulted
        """
        off_mask = 0b00001000110
        if (int(value) & off_mask) > 0:
            await self.mod_off(hv_ready=False)
        else:
            if self.mod_hv_ctrl.value == "ON":
                await self.mod_on()
            else:
                await self.mod_off(hv_ready=True)
        return value

    @dsta.putter
    async def dsta(self, instance, value):
        ioc = instance.group
        """
        DSTA1 bit decoder:
        bit | meaning                        | klystron faulted if bit set?
        ---------------------------------------------
        0   | SLED Cavity Tuned              | Not Faulted
        1   | SLED Cavity Detuned            | Not Faulted
        2   | SLED Motor Not at Limit        | Faulted
        3   | SLED Upper Needle Fault        | Faulted
        4   | SLED Lower Needle Fault        | Faulted
        5   | Electromagnet Current Tols     | Faulted
        6   | Klystron Temperature           | Faulted
        7   | Klystron Reflected Energy      | Faulted
        8   | Klystron Over-Voltage          | Faulted
        9   | Klystron Over-Current          | Faulted
        10  | ADC Read Error                 | Not Faulted
        11  | ADC Out of Tolerance           | Not Faulted
        12  | Desired Phase Change           | Not Faulted
        13  | Water Summary Fault            | Faulted
        14  | Accelerator Water Flowswitch 1 | Faulted
        15  | Accelerator Water Flowswitch 2 | Faulted
        16  | Waveguide Water Flowswitch 1   | Faulted
        17  | Waveguide Water Flowswitch 2   | Faulted
        18  | Klystron Water Flowswitch      | Faulted
        19  | 24V Battery Fault              | Faulted
        20  | Waveguide Vacuum Fault         | Faulted
        21  | Klystron Vacuum Fault          | Faulted
        22  | Electromagnet Current Fault    | Faulted
        23  | Electromagnet Breaker Fault    | Faulted
        24  | MKSU Trigger Enable Fault      | Faulted
        25  | MOD Available                  | Not Faulted
        26  | No Text Defined                | Not Faulted
        
        DSTA2 bit decoder:
        bit | meaning                        | klystron faulted if bit set?
        ---------------------------------------------
        0   | Modulator Control Power Fault  | Faulted
        1   | Modulator VVS Voltage Fault    | Faulted
        2   | Modulator Klys Heater Delay    | Faulted
        3   | Modulator Interlocks Complete  | Not Faulted
        4   | Modulator HV Ready             | Not Faulted
        5   | Modulator Fault Lockout        | Faulted
        6   | Modulator External Fault       | Faulted
        7   | Modulator HV On                | Not Faulted
        8   | Modulator Trigger Overcurrent  | Faulted
        9   | Mod. End-of-line Clipper Fault | Faulted
        10  | Mod. Electromag Over Current   | Faulted
        """
        dsta1_fault_mask = 0b001111111111110001111111100
        dsta2_fault_mask = 0b11101100111
        if ((int(value[0]) & dsta1_fault_mask) > 0) or ((int(value[1]) & dsta2_fault_mask) > 0):
            await self.interlock_trip()
        return value

    @trim.putter
    async def trim(self, instance, value):
        ioc = instance.group
        if value == "TRIM":
            await asyncio.sleep(0.2)
            await ioc.phas.write(ioc.pdes.value)
            self.change_callback(self, ioc.phas.value, "PHAS")
        else:
            L.warning("Warning, only valid function is TRIM.")
        return 0

    @enld.putter
    async def enld(self, instance, value):
        self.change_callback(self, value, "ENLD")
        return value

    @bc1_tctl.putter
    async def bc1_tctl(self, instance, value):
        self.has_accel_triggers = value in ("Activate", "Reactivate")
        await self.on_off_changed()
        await self.bc1_tstat.write(1 if self.has_accel_triggers else 0)
        await self.bc1_stat.write(1 if self.has_accel_triggers else 2)
        return value
    
    async def on_off_changed(self):
        is_on = self.has_accel_triggers and self.hv_ctrl_on and not self.tripped
        if is_on:
            await self.ampl.write(100.0)
        else:
            await self.ampl.write(0.0)
        self.change_callback(self, is_on, "IS_ON")

def _parse_klys_table(table):
    splits = [row.split() for row in table]
    return {'KLYS:LI{0}:{1}1'.format(ele_name[3:5],ele_name[6:8]): ( float(bmadEnld), float(bmadPhas), float(bmadEnld) > 1 ) for (_, ele_name, _, _, _, bmadEnld, bmadPhas) in splits}

def convert_device_to_element(device_name):
    return 'O_K{0}_{1}'.format(device_name[7:9],device_name[10])
    
def convert_sbst_to_element(device_name):
    return 'O_S{0}_{1}'.format(device_name[7:9],device_name[10])

def _parse_cudklys_table(table):
    """
    Right now we basically just want a list of device names, eventually 
    this might actually do something useful.
    """
    splits = [row.split() for row in table]
    return {'CUDKLYS:LI{0}:{1}'.format(ele_name[3:5], ele_name[6:8]): 0 for (_, ele_name, _, _, _, _, _) in splits}  


class KlystronService(simulacrum.Service):
    attr_for_klys_type = {"ENLD": "ENLD_MeV", "PHAS":"PHAS_Deg"} 
    def __init__(self):
        super().__init__()
        self.ctx = Context.instance()
        #cmd socket is a synchronous socket, we don't want the asyncio context.
        self.cmd_socket = zmq.Context().socket(zmq.REQ)
        self.cmd_socket.connect("tcp://127.0.0.1:{}".format(os.environ.get('MODEL_PORT', 12312)))
        init_vals, init_cud_vals = self.get_klystron_ACTs_from_model()
        init_sbst_vals = self.get_sbst_ACTs_from_model()
        klys_pvs = {device_name: KlystronPV(device_name, convert_device_to_element(device_name), self.on_klystron_change, initial_values=init_vals[device_name], prefix=device_name) for device_name in init_vals.keys()}
        cud_pvs = {device_name: CudKlys(device_name,convert_device_to_element(device_name), initial_value=init_cud_vals[device_name], prefix=device_name) for device_name in init_cud_vals.keys()}
        sbst_pvs =  {device_name: SubboosterPV(device_name,convert_sbst_to_element(device_name), prefix=device_name) for device_name in init_sbst_vals.keys()}
        L.info(init_vals)
        self.add_pvs(klys_pvs)
        self.add_pvs(cud_pvs)
        self.add_pvs(sbst_pvs)
        L.info("Initialization complete.")

    def get_klystron_ACTs_from_model(self):
        init_vals = {}
        init_CudVals = {}
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": "show lat -no_label_lines -attribute ENLD_MeV -attribute Phase_Deg O_K*"})
        table = self.cmd_socket.recv_pyobj()['result']
        # We inject our own static data for the injector and TCAV stations, which aren't modelled.
        injector_stat = ['0 O_K20_5 Lcavity 5.6 --- 100 0', '0 O_K20_6 Lcavity 0.5 --- 6 0' , '0 O_K20_7 Lcavity 1.518 --- 58.5 0' ,  '0 O_K20_8 Lcavity 5.362 --- 114.0 0',  '0 O_K24_8 Lcavity 160 --- 114.0 0']
        table.extend(injector_stat)
        init_vals = _parse_klys_table(table)
        init_CudVals = _parse_cudklys_table(table)
        return init_vals, init_CudVals

    def get_sbst_ACTs_from_model(self):
        init_vals = {} ## TODO: Integrate SBST phase with model Overlord
        for ii in range(21,31):
            init_vals[f'SBST:LI{ii}:1'] = (0,0)
        return init_vals

    def on_klystron_change(self, klystron_pv, value, parameter):
        element = klystron_pv.element_name
        if parameter == "PHAS":
            klys_attr = "Phase_Deg"
        elif parameter == "ENLD": 
            klys_attr = "ENLD_MeV"
        elif parameter == "IS_ON":
            klys_attr = "is_on"
            value =  'T' if value else 'F'
            element = element[2:]+'*'  #O_K30_8 overlay to K30_8*

        cmd = f'set ele {element} {klys_attr} = {value}'
        L.info(cmd)
        self.cmd_socket.send_pyobj({"cmd": "tao", "val": cmd})
        msg = self.cmd_socket.recv_pyobj()['result']
        L.info(msg)
   
def main():
    service = KlystronService()
    loop = asyncio.get_event_loop()
    _, run_options = ioc_arg_parser(
        default_prefix='',
        desc="Simulated Klystron Service")
    run(service, **run_options)
    
if __name__ == '__main__':
    main()
    



        
