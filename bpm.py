import random
import asyncio
from collections import defaultdict

class BPMSim:
    def __init__(self):
        self.value = 0
        self.channels = set()
        self.start_sim()
        
    def start_sim(self):
        loop = asyncio.get_event_loop()
        loop.create_task(self.update_forever())

    async def update_forever(self):
        while True:
            #print("Updating the value!")
            self.update_value()
            for channel in self.channels:
                await channel.write(self.value)
            await asyncio.sleep(0.1)
    
    def update_value(self):
        self.value = random.uniform(-1.0, 1.0)

bpms = defaultdict(BPMSim)

async def get(pvname):
    return bpms[pvname].value

async def put(pvname, value):
    raise Exception("Cannot put BPM values.")

async def subscribe(pvname, channel):
    print("BPM Sim got a new subscriber!")
    bpms[pvname].channels.add(channel)

async def unsubscribe(pvname, channel):
    print("BPM Sim is discarding a subscription.")
    bpms[pvname].channels.discard(channel)