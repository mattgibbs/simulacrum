import os
from caproto import (ChannelString, ChannelEnum, ChannelDouble,
                     ChannelChar, ChannelData, ChannelInteger,
                     ChannelByte, ChannelShort, AccessRights,
                     ChannelType)
from caproto.server import ioc_arg_parser, run
import simulacrum

#set up python logger
 #import logging as Log 
 #FORMAT=simulacrum.util.logform
 #Log.basicConfig(level=Log.DEBUG, format=FORMAT)

class ChannelBool(ChannelEnum):
    def __init__(self, *, enum_strings=None, **kwargs):
        if enum_strings is None:
            enum_strings = ['Off', 'On']
            super().__init__(enum_strings=enum_strings, **kwargs)
           
class_for_type = {
    'str': str,
    'bytes': bytes,
    'int': int,
    'float': float,
    'bool': bool,
    
    str: str,
    bytes: bytes,
    int: int,
    float: float,
    bool: bool
}           
           
channel_type_map = {
    'str': ChannelString,
    'bytes': ChannelByte,
    'int': ChannelInteger,
    'float': ChannelDouble,
    'bool': ChannelBool,
    
    str: ChannelString,
    bytes: ChannelByte,
    int: ChannelInteger,
    float: ChannelDouble,
    bool: ChannelBool,

    ChannelType.STRING: ChannelString,
    ChannelType.INT: ChannelInteger,
    ChannelType.LONG: ChannelInteger,
    ChannelType.DOUBLE: ChannelDouble,
    ChannelType.ENUM: ChannelEnum,
    ChannelType.CHAR: ChannelChar
}

default_values = {
    'str': '',
    'bytes': b'',
    'int': 0,
    'float': 0.0,
    'bool': False,
    
    str: '',
    bytes: b'',
    int: 0,
    float: 0.0,
    bool: False,

    ChannelType.STRING: '',
    ChannelType.INT: 0,
    ChannelType.LONG: 0,
    ChannelType.DOUBLE: 0.0,
    ChannelType.ENUM: 0,
    ChannelType.CHAR: '',
}

def make_channel(pvname, data_type, initial_value=None):
    if initial_value is None:
        initial_value = default_values[data_type]
    if data_type in channel_type_map:
        channel_class = channel_type_map[data_type]
        return channel_class(value=initial_value)
    else:
        raise ValueError("Generic PV service doesn't know what EPICS type to use for Python type {}".format(data_type))

class GenericPVService(simulacrum.Service):
    def __init__(self):
        super().__init__()
        path_to_pv_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "pvs.txt")
        with open(path_to_pv_file) as f:
            for line in f:
                if line.startswith("#"):
                    continue
                pv_args = line.split(None, 2)
                if len(pv_args) == 0:
                    continue
                pv = pv_args[0]
                type_for_pv = pv_args[1]
                initial_value = None
                if len(pv_args) > 2:
                    initial_value = pv_args[2]
                chan = make_channel(pv, type_for_pv, initial_value=class_for_type[type_for_pv](initial_value))
                self[pv] = chan
        
def main():
    service = GenericPVService()
    _, run_options = ioc_arg_parser(
        default_prefix='',
        desc="Generic PV Service")
    run(service, **run_options)
    
if __name__ == '__main__':
    main()
