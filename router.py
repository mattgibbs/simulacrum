#!/usr/bin/env python3
import asyncio
from caproto.server import ioc_arg_parser, run

from collections import defaultdict
from caproto import (ChannelString, ChannelEnum, ChannelDouble,
                     ChannelChar, ChannelData, ChannelInteger,
                     ChannelType)
from route_channel import (StringRoute, EnumRoute, DoubleRoute,
                           CharRoute, IntegerRoute, BoolRoute,
                           ByteRoute, ShortRoute, BoolRoute)
import re
from arch import get_mean_and_std
import bpm_sim.bpm as bpm

route_type_map = {
    str: CharRoute,
    bytes: ByteRoute,
    int: IntegerRoute,
    float: DoubleRoute,
    bool: BoolRoute,

    ChannelType.STRING: StringRoute,
    ChannelType.INT: ShortRoute,
    ChannelType.LONG: IntegerRoute,
    ChannelType.DOUBLE: DoubleRoute,
    ChannelType.ENUM: EnumRoute,
    ChannelType.CHAR: CharRoute,
}

default_values = {
    str: '',
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

class Router(defaultdict):
    def __init__(self, factory=None):
        super().__init__(factory)
        self.routes = []
        
    def add_route(self, pattern, data_type, get, put=None, new_subscription=None, remove_subscription=None):
        self.routes.append((re.compile(pattern), data_type, get, put, new_subscription, remove_subscription))
    
    def __contains__(self, key):
        return True

    def __missing__(self, pvname):
        chan = None
        for (pattern, data_type, get_route, put_route, new_subscription_route, remove_subscription_route) in self.routes:
            print("Testing {} against {}".format(pvname, pattern.pattern))
            if pattern.match(pvname) != None:
                chan = self.make_route_channel(pvname, data_type, get_route, put_route, new_subscription_route, remove_subscription_route)
        if chan is None:
            # No routes matched, so revert to making static data.
            chan = self.default_factory(pvname)
        ret = self[pvname] = chan
        return ret
    
    def make_route_channel(self, pvname, data_type, getter, setter=None, new_subscription=None, remove_subscription=None):
        if data_type in route_type_map:
            route_class = route_type_map[data_type]
            return route_class(pvname, getter, setter, new_subscription, remove_subscription, value=default_values[data_type])
        else:
            raise ValueError("Router doesn't know what EPICS type to use for Python type {}".format(data_type))
            

def fabricate_channel(pvname):
    print("Making a static channel for key: {}".format(pvname))
    return ChannelDouble(value=0)

def main():
    _, run_options = ioc_arg_parser(
        default_prefix='',
        desc="PV black hole")
    
    router = Router(fabricate_channel)
    router.add_route("BPMS:.+:[0-9]+:(X|Y|TMIT)", data_type=float, get=bpm.get, new_subscription=bpm.subscribe, remove_subscription=bpm.unsubscribe)        
    run(router, **run_options)



if __name__ == '__main__':
    main()