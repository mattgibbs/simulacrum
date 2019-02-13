from caproto import (ChannelString, ChannelEnum, ChannelDouble,
                     ChannelChar, ChannelData, ChannelInteger,
                     ChannelByte, ChannelShort, AccessRights)

class RouteChannel:
    def __init__(self, pvname, getter, setter=None, new_subscription=None, remove_subscription=None, **kwargs):
        self.pvname = pvname
        self.getter = getter
        self.setter = setter
        self.new_subscription = new_subscription
        self.remove_subscription = remove_subscription
        super().__init__(**kwargs)
    
    async def read(self, data_type):
        # First, call the getter to generate a new value.
        value = await self.getter(self.pvname)
        if value is not None:
            # Update internal state to reflect new value.
            await self.write(value)
        #Return the internal state.
        return await self._read(data_type)
        
    async def verify_value(self, value):
        value = await super().verify_value(value)
        if self.setter:
            return await self.setter(self.pvname, value)
        else:
            return value
    
    def check_access(self, host, user):
        if self.setter is None:
            return AccessRights.READ
        return super().check_access(host, user)
    
    async def subscribe(self, queue, sub_spec, sub):
        if self.new_subscription:
            await self.new_subscription(self.pvname, self)
        return await super().subscribe(queue, sub_spec, sub)
    
    async def unsubscribe(self, queue, sub_spec):
        if self.remove_subscription:
            await self.remove_subscription(self.pvname, self)
        return await super().unsubscribe(queue, sub_spec)
    
class StringRoute(RouteChannel, ChannelString):
    pass

class EnumRoute(RouteChannel, ChannelEnum):
    pass

class DoubleRoute(RouteChannel, ChannelDouble):
    pass

class CharRoute(RouteChannel, ChannelChar):
    pass

class IntegerRoute(RouteChannel, ChannelInteger):
    pass

class ByteRoute(RouteChannel, ChannelByte):
    pass

class ShortRoute(RouteChannel, ChannelShort):
    pass

class BoolRoute(RouteChannel, ChannelEnum):
    def __init__(self, *, enum_strings=None, **kwargs):
        if enum_strings is None:
            enum_strings = ['Off', 'On']
            super().__init__(enum_strings=enum_strings, **kwargs)