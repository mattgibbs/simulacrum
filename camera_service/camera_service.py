import os
import asyncio
import numpy as np
from caproto.server import ioc_arg_parser, run, pvproperty, PVGroup
import simulacrum
import zmq
import time
from zmq.asyncio import Context
import pickle

class ProfMonService(simulacrum.Service):
    def __init__(self):
        print('Initializing PVs') 
        super().__init__()
        with open('screenProps4.dat', 'rb') as file_handle:
            screens = pickle.load(file_handle, encoding='latin1');
        self.screenDict = {}
        for screenProps in screens:
            try:
                #cheeky way to check if my saved device names are all in model
                simulacrum.util.convert_device_to_element(screenProps['device_name']);
                self.screenDict[screenProps['device_name']] = screenProps
                #print(screenProps['element_name'])
            except KeyError:
                continue;

 
        def ProfMonPVClassMaker(screenProps):
            pvLen = len(screenProps['device_name']);
            image_name = screenProps['image_name'][pvLen+1:];
            image_size =  int(screenProps['values'][0] * screenProps['values'][1])
            if not image_size:
                #return None;
                image_size = 256;
            image= pvproperty(value=np.zeros(image_size).tolist(), name = image_name, read_only=True, mock_record='ai')
            pvProps = { screenProps['props'][i].split(':')[3]: pvproperty(value = float(screenProps['values'][i]), name = ':' + screenProps['props'][i].split(':')[3], read_only=True, mock_record='ai') 
                        for i in range(0, len(screenProps['props'])) if screenProps['props'][i]
                      }
            pvProps['image'] = image;
            return type(screenProps['device_name'], (PVGroup,), pvProps)
 
        real_screens = [device_name for device_name in simulacrum.util.device_names if device_name.startswith("OTR") or device_name.startswith("YAG")]
        screen_pvs = {};          
        for screen in real_screens:
            print('PV: ' + screen);
            try:
                ProfClass = ProfMonPVClassMaker(self.screenDict[screen])
            except KeyError:
                pass
            if(ProfClass):
                screen_pvs[screen] = ProfClass(prefix = screen);
        self.add_pvs(screen_pvs)
        self.ctx = Context.instance()
        #cmd socket is a synchronous socket, we don't want the asyncio context.
        self.cmd_socket = zmq.Context().socket(zmq.REQ)
        self.cmd_socket.connect("tcp://127.0.0.1:{}".format(os.environ.get('MODEL_PORT', 12312)))
        
        self.profiles = [{'device_name': i, 'element_name': simulacrum.util.convert_device_to_element(i)} for i in self.screenDict.keys()];
        print("Initialization complete.")

    def start(self):
        print("Starting Profile Monitor Service.")
        loop = asyncio.get_event_loop()
        _, run_options = ioc_arg_parser(
            default_prefix='',
            desc="Simulated Profile Monitor Service")
        task = loop.create_task(self.recv_profiles())
        try:
            loop.call_soon(self.request_profile);
            loop.run_until_complete(task)
        except KeyboardInterrupt:
            task.cancel()
      
    def get_image_size(self, screen):
        screenProps = self.screenDict[screen];
        screenX = screenProps['values'][0];
        screenY = screenProps['values'][1];
        return int(screenX * screenY);

    def request_profile(self):
        self.cmd_socket.send_pyobj({"cmd": "send_profiles_twiss"})
        return self.cmd_socket.recv_pyobj();
        
    async def recv_profiles(self, flags=0, copy=False, track=False):
        profile_socket = self.ctx.socket(zmq.SUB)
        profile_socket.connect('tcp://127.0.0.1:{}'.format(os.environ.get('PROFILE_PORT', 56790)))
        profile_socket.setsockopt(zmq.SUBSCRIBE, b'')
        while True:
            print("Checking for new profile data.")
            md = await profile_socket.recv_pyobj(flags=flags)
            print("Profile data incoming: ", md)
            msg = await profile_socket.recv(flags=flags, copy=copy, track=track)
            buf = memoryview(msg)
            A = np.frombuffer(buf, dtype=md['dtype'])
            result = A.reshape(md['shape'])[3:-3]
            iterator = iter(result)
            i = 0
            while True:
                try:
            #for i, row in enumerate(result):
                    row = next(iterator)
                    ( _, name, _, _, _, beta_a, beta_b) = row.split();
                    if(name != self.profiles[i]['element_name']):
                        continue
                    image_size = self.get_image_size(self.profiles[i]['device_name']);
                    image = np.ones(image_size)* float(beta_a);
                    self.profiles[i]['image'] = image.tolist(); 
                    i = i+1
                except StopIteration:
                    break
            await self.publish_profiles()

    async def publish_profiles(self):
        for row in self.profiles:
            pvName = self.screenDict[row['device_name']]['image_name'][1:];
            if pvName in self:
                await self[pvName].write(row['image'])
    
def main():
    service = ProfMonService()
    service.start()
    loop = asyncio.get_event_loop()
    _, run_options = ioc_arg_parser(
        default_prefix='',
        desc="Simulated Profile Monitor Service")

    
if __name__ == '__main__':
    main()
