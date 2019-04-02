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
    default_image_size = 1024*1024

    def __init__(self):
        print('Initializing PVs') 
        super().__init__()

        #load Profmon properties from file
        path_to_screen_props = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'screenProps.dat')
        with open(path_to_screen_props, 'rb') as file_handle:
            screens = pickle.load(file_handle)

        #build dicts to translate element name/device name
        self.ele2dev = {}
        self.dev2ele = {}
        self.profiles = {}
        for screenProps in screens:
                self.ele2dev[screenProps['element_name']] = screenProps['device_name']
                self.dev2ele[screenProps['device_name']] = screenProps['element_name']
                self.profiles[screenProps['device_name']] = {'props': screenProps}
 
        def ProfMonPVClassMaker(screenProps):
            pvLen = len(screenProps['device_name'])
            image_name = screenProps['image_name'][pvLen:]
            image_size =  int(screenProps['values'][0] * screenProps['values'][1])
            if not image_size:
                image_size = self.default_image_size

            image= pvproperty(value=np.zeros(image_size).tolist(), name = image_name, read_only=True, mock_record='ai')

            try:
                pvProps = { screenProps['props'][i].split(':')[3]: pvproperty(value = float(screenProps['values'][i]), name = ':' + screenProps['props'][i].split(':')[3], read_only=True, mock_record='ai') 
                            for i in range(0, len(screenProps['props'])) if screenProps['props'][i]
                        }
            except IndexError:
                print(screen + ' has an invalid device name')
                return None

            pvProps['image'] = image
            return type(screenProps['device_name'], (PVGroup,), pvProps)

        screen_pvs = {}          
        for screen in self.profiles:
            print('PV: ' + screen + ' ' + self.dev2ele[screen])
            ProfClass = ProfMonPVClassMaker(self.profiles[screen]['props'])
            if(ProfClass):
                screen_pvs[screen] = ProfClass(prefix = screen)

        self.add_pvs(screen_pvs)
        self.ctx = Context.instance()
        #cmd socket is a synchronous socket, we don't want the asyncio context.
        self.cmd_socket = zmq.Context().socket(zmq.REQ)
        self.cmd_socket.connect("tcp://127.0.0.1:{}".format(os.environ.get('MODEL_PORT', 12312)))
        
        print("Initialization complete.")

    def get_image_size(self, screenProps):
        screenX = screenProps[0]
        screenY = screenProps[1]
        return int(screenX * screenY)

    def request_profiles(self):
        self.cmd_socket.send_pyobj({"cmd": "send_profiles_twiss"})
        return self.cmd_socket.recv_pyobj()
        
    async def recv_profiles(self, flags=0, copy=False, track=False):
        profile_socket = self.ctx.socket(zmq.SUB)
        profile_socket.connect('tcp://127.0.0.1:{}'.format(os.environ.get('PROFILE_PORT', 12345)))
        profile_socket.setsockopt(zmq.SUBSCRIBE, b'')
        while True:
            print("Checking for new profile data.")
            md = await profile_socket.recv_pyobj(flags=flags)
            print("Profile data incoming: ", md)
            msg = await profile_socket.recv(flags=flags, copy=copy, track=track)
            buf = memoryview(msg)
            A = np.frombuffer(buf, dtype=md['dtype'])
            result = A.reshape(md['shape'])[3:-3]

            for row in result:
                ( _, name, _, _, _, beta_a, beta_b) = row.split()
                devName = self.ele2dev[name]
                if devName not in self.profiles:
                    continue

                #CGI
                print('Calculating image for ' + devName)
                image = self.gen_beam_image(float(beta_a), float(beta_b), self.profiles[devName]['props']['values'])
                self.profiles[devName]['image'] = image.tolist()
                print( len(self.profiles[devName]['image']))
            await self.publish_profiles()

    async def publish_profiles(self):
        for key, profile in self.profiles.items():
            pvName = profile['props']['image_name']
            if pvName in self:
                try:
                    await self[pvName].write(profile['image'])
                except:
                    continue

    # Generate 2D gaussian from orbit & betas.
    def gen_beam_image(self, beta_a, beta_b, props):

        # image parameters
        image_size = self.get_image_size(props)
        cal = (props[3]*1e-6 if props[3] else 1e-10)   # CCD calibration in m/pixel  
        dimX = props[6]
        dimY = props[7]
        centerX = props[10]
        centerY = props[11]
        #print("Cal: %f, dimX: %d, dimY: %d, centerX: %d, centerX: %d" % (cal, dimX, dimY, centerX, centerY))
        # beam parameters
        emittance = 0.4e-6 
        beam_size_x = np.sqrt(beta_a*emittance)
        beam_size_y = np.sqrt(beta_b*emittance)
        print(beam_size_x*1e6) 
        #beam parameters in pixels
        sig_x = beam_size_x/cal
        sig_y = beam_size_y/cal

        #normalization of uncorrelated 2D gaussian. TODO: replace random 1000 with a physically sensible number. 
        A = 1000./np.pi/sig_x/sig_y

        #generate image. TODO: get particle orbit and offset in x and y
        x = np.arange(1, dimX+1) - centerX
        y = np.arange(1, dimY+1) - centerY
        x2 = -((x/sig_x)**2)/2
        y2 = -((y/sig_y)**2)/2
        xx2, yy2 = np.meshgrid(x2, y2)
        img = A*np.exp(xx2 + yy2)
        return img.ravel()
        
        
def main():
    service = ProfMonService()
    loop = asyncio.get_event_loop()
    _, run_options = ioc_arg_parser(
        default_prefix='',
        desc="Simulated Profile Monitor Service")
    loop.create_task(service.recv_profiles())
    loop.call_soon(service.request_profiles)
    run(service, **run_options)
    
if __name__ == '__main__':
    main()
