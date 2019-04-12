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
    default_image_dim = 1024
    util_pvs = ['EVR:IN20:PM01:CTRL.DG0E', 'EVR:IN20:PM02:CTRL.DG1E', 'EVR:IN20:PM02:CTRL.DG0E',
                'EVR:IN20:PM03:CTRL.DG0E', 'EVR:IN20:PM03:CTRL.DG1E', 'EVR:IN20:PM04:CTRL.DG1E',
                'EVR:IN20:PM04:CTRL.DG0E', 'EVR:IN20:PM05:CTRL.DG1E', 'EVR:IN20:PM05:CTRL.DG0E',
                'EVR:IN20:PM06:CTRL.DG1E', 'EVR:IN20:PM06:CTRL.DG0E', 'EVR:LI21:PM01:CTRL.DG1E', 
                'EVR:LI21:PM01:CTRL.DG0E', 'EVR:LI24:PM01:CTRL.DG1E', 'EVR:LI24:PM01:CTRL.DG0E', 
                'EVR:LTU1:PM01:CTRL.DG0E', 'EVR:UND1:PM03:CTRL.DG1E', 'EVR:UND1:PM03:CTRL.DG0E',
                'EVR:UND1:PM01:CTRL.DG0E', 'EVR:IN20:PM01:CTRL.DG1E', 'YAGS:IN20:841:FRAME_RATE', 
                'YAGS:IN20:351:FRAME_RATE', 'OTRS:IN20:541:FRAME_RATE', 'OTRS:IN20:621:FRAME_RATE',
                'YAGS:IN20:921:FRAME_RATE', 'OTRS:LI21:291:FRAME_RATE', 'OTRS:LI25:342:FRAME_RATE', 
                'CTHD:IN20:206:FRAME_RATE', 'SIOC:SYS0:ML02:AO000'] #last one not strictly necessary but speeds up matlab init

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

            if not screenProps['values'][6]*screenProps['values'][7]:
                screenProps['values'][[0, 1, 6, 7]] = self.default_image_dim
                #screenProps['values'][2] = self.default_image_dim
                #screenProps['values'][6] = self.default_image_dim
                #screenProps['values'][7] = self.default_image_dim

            image_size = int(screenProps['values'][6] * screenProps['values'][7])
            image= pvproperty(value=np.zeros(image_size).tolist(), name = image_name, read_only=True, mock_record='ai')
            
            #dummy pv for EVR acquisition 
            acquire = pvproperty(value = "Acquire", name = ':Acquisition', read_only=False, mock_record='ai');
            frame_rate = pvproperty(value = 0, name = ':FRAME_RATE', read_only=True, mock_record='ai');
            buf_idx =  pvproperty(value = 0, name = ':IMG_BUF_IDX', read_only=False, mock_record='ai');
            img_save = pvproperty(value = 0, name = ':SAVE_IMG', read_only=False, mock_record='ai');
            try:
                pvProps = { screenProps['props'][i].split(':')[3]: pvproperty(value = float(screenProps['values'][i]), name = ':' + screenProps['props'][i].split(':')[3], read_only=False, mock_record='ai') 
                            for i in range(0, len(screenProps['props'])) if screenProps['props'][i]
                        }
            except IndexError:
                print(screen + ' has an invalid device name')
                return None
            pvProps.update({'acquire': acquire, 'frame_rate': frame_rate, 'buf_idx': buf_idx, 'img_save': img_save, 'image': image})
            return type(screenProps['device_name'], (PVGroup,), pvProps)

        def UtilPVClassMaker(PVName):
            pv = pvproperty(value = 0, name = PVName, read_only=False, mock_record='ai');
            return type(PVName, (PVGroup,), {'pv': pv})

        screen_pvs = {}         
        util_pvs = {} 

        for screen in self.profiles:
            print('PV: ' + screen + ' ' + self.dev2ele[screen])
            ProfClass = ProfMonPVClassMaker(self.profiles[screen]['props'])
            if(ProfClass):
                screen_pvs[screen] = ProfClass(prefix = screen)

        for pv in self.util_pvs:
            prefix = ':'.join(pv.split(':')[0:3])
            suffix = pv.split(':')[3]
            UtilPVClass = UtilPVClassMaker(':' + suffix)
            screen_pvs[pv] = UtilPVClass(prefix = prefix)

        self.add_pvs(screen_pvs)
        self.add_pvs(util_pvs)
        self.ctx = Context.instance()
        #cmd socket is a synchronous socket, we don't want the asyncio context.
        self.cmd_socket = zmq.Context().socket(zmq.REQ)
        self.cmd_socket.connect("tcp://127.0.0.1:{}".format(os.environ.get('MODEL_PORT', 12312)))
        
        print("Initialization complete.")

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

            print("Checking for new profile orbits.")
            md = await profile_socket.recv_pyobj(flags=flags)
            print("Profile orbit incoming: ", md)
            msg = await profile_socket.recv(flags=flags, copy=copy, track=track)
            buf = memoryview(msg)
            A = np.frombuffer(buf, dtype=md['dtype'])
            orbit = A.reshape(md['shape'])

            for i, row in enumerate(result):
                ( _, name, _, _, _, beta_a, beta_b) = row.split()
                devName = self.ele2dev[name]
                if devName not in self.profiles:
                    continue

                #CGI
                image = self.gen_beam_image(float(beta_a), float(beta_b), orbit[0][i], orbit[1][i],  self.profiles[devName]['props']['values'])
                self.profiles[devName]['image'] = image.tolist()
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
    def gen_beam_image(self, beta_a, beta_b, x, y, props):

        # image parameters
        imageX = props[0]
        imageY = props[1]
        bit_depth = props[2]
        cal = (props[3]*1e-6 if props[3] else 1e-10)   # resolution ie  calibration in m/pixel  
        roiX = props[6]
        roiY = props[7]
        if(roiX*roiY == 0): 
            roiX = imageX
            roiY = imageY
        centerX = props[10]
        centerY = props[11]
        #print("Cal: %f, dimX: %d, dimY: %d, centerX: %d, centerX: %d" % (cal, dimX, dimY, centerX, centerY))
        # beam parameters
        emittance = 0.4e-6 
        beam_size_x = np.sqrt(beta_a*emittance)
        beam_size_y = np.sqrt(beta_b*emittance)
        #beam parameters in pixels
        sig_x = beam_size_x/cal
        sig_y = beam_size_y/cal
        xPos = 1e-3*x/cal
        yPos = 1e-3*y/cal
        #normalization of uncorrelated 2D gaussian.
        A = 1./np.pi/sig_x/sig_y
        #Estimate camera intensity, see profmon_simulCreate.m. basically # of e- * quantum efficiency / attenuation factor
        q = 1e-9
        e0 = 1.6e-19
        qe = 2e-3
        atten = 1
        intensity = (q/e0)*qe/atten
        #generate image. TODO: get particle orbit and offset in x and y
        x = np.arange(1, roiX+1) - centerX - xPos
        y = np.arange(1, roiY+1) - centerY - yPos
        x2 = -((x/sig_x)**2)/2
        y2 = -((y/sig_y)**2)/2
        xx2, yy2 = np.meshgrid(x2, y2)
        img = intensity*A*np.exp(xx2 + yy2)
        img = img.astype(np.uint8) if bit_depth <= 8 else img.astype(np.uint16) 
        img_flat = np.minimum(img.ravel(), 2**bit_depth - 1) 
        return img_flat
        
        
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
