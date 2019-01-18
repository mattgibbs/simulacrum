from .orbit import BaseOrbit, Orbit, BaseBPM, StaticBPM
import numpy as np
from . import model
class SimOrbit(BaseOrbit):
    def __init__(self):
        super(SimOrbit, self).__init__(name="Simulated Orbit")
        names = Orbit.lcls_bpm_list()
        print(names)
        self.bpm_count = len(names)
        model_data = np.load("bpm_sim/sim_model.npy", encoding='ASCII')
        self.bpm_data = np.zeros(len(names), dtype=[('name', 'a60'), ('x', 'float32'), ('y', 'float32'), ('tmit', 'float32'), ('x_err', 'float32'), ('y_err', 'float32'), ('tmit_err', 'float32'), ('z', 'float32'), ('x_severity', 'i8'), ('y_severity', 'i8'), ('tmit_severity', 'i8'), ('r_mat', 'float32', (6,6))])
        self.bpm_data['name'] = names
        self.bpm_data['z'] = model.get_zpos(names, full_model=model_data, ignore_bad_names=True)
        good_indices = np.where(np.logical_not(np.isnan(self.bpm_data['z'])))
        self.bpm_data = self.bpm_data[good_indices]
        self.bpm_count = len(self.bpm_data)
        self.bpm_data['tmit'] = 1.5e9
        self.bpm_data['r_mat'] = model.get_rmat(b'BPMS:IN20:221', self.bpm_data['name'], full_model=model_data)
        self.bpm_data['x_err'] = np.random.normal(0.0, 0.15,self.bpm_count)
        self.bpm_data['y_err'] = np.random.normal(0.0, 0.15,self.bpm_count)
        self.bpm_data['tmit_err'] = np.random.normal(0.0, 7705482,self.bpm_count)
        #Don't add extra error in the undulator
        und_indices = np.where(np.core.defchararray.startswith(self.bpm_data['name'], b'BPMS:UND1'))
        self.bpm_data['x_err'][und_indices] = 0.0
        self.bpm_data['y_err'][und_indices] = 0.0
        for i in range(0, self.bpm_count):
            #if self.bpm_data['z'][i] is None:
            #   continue
            bpm = ProxyBPM(i, self.bpm_data)
            if bpm.name in Orbit.lcls_energy_bpms():
                bpm.is_energy_bpm = True
            self.append(bpm)

    def _find_z_min_and_max(self):
        self._zmin = np.min(self.bpm_data['z'])
        self._zmax = np.max(self.bpm_data['z'])

    def names(self):
        return self.bpm_data['name']

    def vals(self, axis):
        return self.bpm_data[axis]
    
    def update(self):
        initial_conditions = np.array([np.random.normal(0.0, 0.008), np.random.normal(0.0, 0.004), np.random.normal(0.0, 0.012), np.random.normal(0.0, 0.008), np.random.normal(0.0, 10.0)])
        Q = np.append(self.bpm_data['r_mat'][:, 0, [0,1,2,3,5]], self.bpm_data['r_mat'][:, 2, [0,1,2,3,5]],0)
        trajectory = np.mat(Q)*np.mat(initial_conditions).T
        self.bpm_data['x'] = np.array(trajectory[0:self.bpm_count].T) + self.bpm_data['x_err']
        self.bpm_data['y'] = np.array(trajectory[self.bpm_count:].T) + self.bpm_data['y_err']
        self.bpm_data['tmit'] = np.random.normal(1.5e9, 20705382.0) + np.random.normal(0.0, 10000.0, self.bpm_count) + self.bpm_data['tmit_err']

    def to_static(self, name=None):
        o = BaseOrbit(name=name)
        for i in range(0, self.bpm_count):
            bpm = StaticBPM(self.bpm_data[i]['name'], z_pos=self.bpm_data[i]['z'], x_val=self.bpm_data[i]['x'], y_val=self.bpm_data[i]['y'], tmit_val=self.bpm_data[i]['tmit'], x_severity=self.bpm_data[i]['x_severity'], y_severity=self.bpm_data[i]['y_severity'], tmit_severity=self.bpm_data[i]['tmit_severity'])
            o.append(bpm)
        return o
        
    def __getitem__(self, key):
        pieces = key.split(":")
        name = bytes(":".join(pieces[0:3]), encoding='ascii')
        val = pieces[-1].lower()
        return self.bpm_data[self.bpm_data['name']==name][0][val]

class ProxyBPM(object):
    def __init__(self, index, data):
        self.index = index
        self.data = data
        self.is_energy_bpm = False

    def __getitem__(self, key):
                if key.lower() == "x":
                        return self.x
                if key.lower() == "y":
                        return self.y
                if key.lower() == "tmit":
                        return self.tmit
                if key.lower() == "z":
                        return self.z
    @property
    def x(self):
        return self.data[self.index]['x']
    
    @property
    def y(self):
        return self.data[self.index]['y']

    @property
    def tmit(self):
        return self.data[self.index]['tmit']

    @property
    def z(self):
        return self.data[self.index]['z']

    @property
    def name(self):
        return self.data[self.index]['name']

    def severity(self, axis):
        return 0

    @property
    def x_severity(self):
        return 0

    @property
    def y_severity(self):
        return 0

    @property
    def tmit_severity(self):
        return 0
