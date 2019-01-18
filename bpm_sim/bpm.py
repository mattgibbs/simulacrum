import random
import asyncio
from collections import defaultdict
from .sim_orbit import SimOrbit
class BPMSim:
    def __init__(self):
        self.orbit = SimOrbit()
        self.value = 0
        self.channels = defaultdict(set)
        self.start_sim()
        
    def start_sim(self):
        loop = asyncio.get_event_loop()
        loop.create_task(self.update_forever())

    async def update_forever(self):
        while True:
            #print("Updating the value!")
            self.update_value()
            for pvname, d in self.channels.items():
                for channel in d:
                    await channel.write(self.orbit[pvname])
            await asyncio.sleep(0.1)
    
    def update_value(self):
        self.orbit.update()

bpms = BPMSim()

async def get(pvname):
    return bpms.orbit[pvname]

async def put(pvname, value):
    raise Exception("Cannot put BPM values.")

async def subscribe(pvname, channel):
    print("BPM Sim got a new subscriber!")
    bpms.channels[pvname].add(channel)

async def unsubscribe(pvname, channel):
    print("BPM Sim is discarding a subscription.")
    bpms.channels[pvname].discard(channel)