#from utilities.edef import EventDefinition
#import pyca
#from psp.Pv import Pv
import time
import numpy as np
import pickle
from operator import attrgetter
#import utilities.matlog
#from utilities.batch_get import batch_get
import math
import subprocess
import re
import os
import json
from datetime import datetime
MODEL_AVAILABLE = False
try:
    import utilities.model as model
    import utilities.fit
    MODEL_AVAILABLE = True
except ModuleNotFoundError:
    MODEL_AVAILABLE = False

"""A collection of classes to represent a linac orbit"""
class BaseBPM(object):
    """Abstract base class for a Beam Position Monitor.
    Each BPM has an X, Y, and TMIT value, and a Z Position."""
    def __init__(self, name, z_pos=None):
        self.name = name
        self.z = z_pos
        self.is_energy_bpm = False

    @property           
    def x(self):
        raise NotImplementedError
    
    @property
    def y(self):
        raise NotImplementedError
    
    @property    
    def tmit(self):
        raise NotImplementedError
    
    def __getitem__(self, key):
        if key.lower() == "x":
            return self.x
        if key.lower() == "y":
            return self.y
        if key.lower() == "tmit":
            return self.tmit
        if key.lower() == "z":
            return self.z

    def __str__(self):
        return self.name

class StaticBPM(BaseBPM):
    """StaticBPM is a BPM, frozen in time.  An Orbit with Static BPMs is how you make a reference orbit."""
    def __init__(self, name, z_pos=None, x_val=None, y_val=None, tmit_val=None, x_rms=0.0, y_rms=0.0, tmit_rms=0.0, x_severity=None, y_severity=None, tmit_severity=None, x_status=None, y_status=None, tmit_status=None, is_energy_bpm=False):
        super(StaticBPM, self).__init__(name, z_pos=z_pos)
        self._x = x_val
        self._y = y_val
        self._tmit = tmit_val
        self._x_rms = x_rms
        self._y_rms = y_rms
        self._tmit_rms = tmit_rms
        self._x_sevr = x_severity
        self._y_sevr = y_severity
        self._tmit_sevr = tmit_severity
        self._x_status = x_status
        self._y_status = y_status
        self._tmit_status = tmit_status
        self.is_energy_bpm = is_energy_bpm
    
    @BaseBPM.x.getter
    def x(self):
        return self._x

    @BaseBPM.y.getter
    def y(self):
        return self._y
        
    @BaseBPM.tmit.getter    
    def tmit(self):
        return self._tmit

    @property
    def x_rms(self):
        return self._x_rms
        
    @property
    def y_rms(self):
        return self._y_rms
        
    @property
    def tmit_rms(self):
        return self._tmit_rms

    def severity(self, axis):
        if axis == "x":
            return self._x_sevr
        if axis == "y":
            return self._y_sevr
        if axis == "tmit":
            return self._tmit_sevr
        raise Exception("Axis parameter not valid")
    
    @property
    def x_severity(self):
        return self.severity('x')

    @property
    def y_severity(self):
        return self.severity('y')

    @property
    def tmit_severity(self):
        return self.severity('tmit')

    def status(self, axis):
        if axis == "x":
            return self._x_status
        if axis == "y":
            return self._y_status
        if axis == "tmit":
            return self._tmit_status
        raise Exception("Axis parameter not valid")
    
    @property
    def x_status(self):
        return self.status('x')

    @property
    def y_status(self):
        return self.status('y')

    @property
    def tmit_status(self):
        return self.status('tmit')

    def to_static(self):
        return self

class BaseOrbit(object):
    @classmethod
    def from_dict(cls, d):
        orbit = cls()
        for (i, name) in enumerate(d['names']):
            bpm = StaticBPM(str(name).strip(), z_pos=d['z'][i], x_val=d['x'][i], y_val=d['y'][i], tmit_val=d['tmit'][i], x_rms=d['x_rms'][i], y_rms=d['y_rms'][i], tmit_rms=d['tmit_rms'][i], x_severity=d['x_severity'][i], y_severity=d['y_severity'][i], tmit_severity=d['tmit_severity'][i])
            orbit.append(bpm)
        return orbit

    @classmethod
    def from_MATLAB_file(cls, filepath):
        """Files saved in the matlab format are awful to deal with:  Plain-old lists turn into crazy nested nonsense."""
        d = matlog.load(filepath)
        orbit = cls()
        for (i, name) in enumerate(d['data']['names'][0][0]):
            bpm = StaticBPM(str(name).strip(), z_pos=d['data']['z'][0][0][0][i], x_val=d['data']['x'][0][0][0][i], y_val=d['data']['y'][0][0][0][i], tmit_val=d['data']['tmit'][0][0][0][i], x_rms=d['data']['x_rms'][0][0][0][i], y_rms=d['data']['y_rms'][0][0][0][i], tmit_rms=d['data']['tmit_rms'][0][0][0][i], x_severity=d['data']['x_severity'][0][0][0][i], y_severity=d['data']['y_severity'][0][0][0][i], tmit_severity=d['data']['tmit_severity'][0][0][0][i])
            orbit.append(bpm)
        orbit.name = os.path.basename(filepath)
        return orbit

    @classmethod
    def from_json_file(cls, filepath):
        with open(filepath) as json_file:
            d = json.load(json_file)
            orbit = cls.from_dict(d)
            orbit.name = os.path.basename(filepath)
            return orbit

    def __init__(self, name=None):
        self._bpms = []
        self._bpm_name_dict = {}
        self._zmin = None
        self._zmax = None
        self._rmat_cache = None
        self._rmats_for_fit = None
        self._zs_for_fit = None
        self._saved_fit_start = None
        self._saved_fit_end = None
        self._saved_fit_point = None
        self.name = name
        self.fit_data = None
    
    def __str__(self):
        return str(self.name)

    @property
    def bpms(self):
        return self._bpms

    @bpms.setter
    def bpms(self, new_bpms):
        self._clear_all_caches()
        self._bpms = new_bpms
        self._bpm_name_dict = {}
        for bpm in new_bpms:
            self._bpm_name_dict[bpm.name] = bpm

    def append(self, new_bpm):
        if new_bpm.name in self._bpm_name_dict:
            raise ValueError('Orbit already contains a BPM named "{}".  BPM names in an orbit must be unique.'.format(new_bpm.name))
        self._bpm_name_dict[new_bpm.name] = new_bpm
        self._bpms.append(new_bpm)

    def bpm_with_name(self, name):
        return self._bpm_name_dict[name]

    def _clear_z_cache(self):
        self._zmin = None
        self._zmax = None
    
    def _clear_all_caches(self):
        self._rmat_cache = None
        self._clear_z_cache()
    
    def _find_z_min_and_max(self):
        for bpm in self.bpms:
            if bpm.z < self._zmin or (self._zmin is None):
                self._zmin = bpm.z
            if bpm.z > self._zmax or (self._zmax is None):
                self._zmax = bpm.z
    
    def zmin(self):
        if self._zmin is None:
            self._find_z_min_and_max()
        return self._zmin
    
    def zmax(self):
        if self._zmax is None:
            self._find_z_min_and_max()
        return self._zmax
    
    def xmin(self):
        xmin = None
        for bpm in self.bpms:
            if bpm.x < xmin or (xmin is None):
                xmin = bpm.x
        return xmin
    
    def xmax(self):
        xmax = None
        for bpm in self.bpms:
            if bpm.x > xmax or (xmax is None):
                xmax = bpm.x
        return xmax
    
    def ymin(self):
        ymin = None
        for bpm in self.bpms:
            if bpm.y < ymin or (ymin is None):
                ymin = bpm.y
        return ymin
    
    def ymax(self):
        ymax = None
        for bpm in self.bpms:
            if bpm.y > ymax or (ymax is None):
                ymax = bpm.y
        return ymax
    
    def tmitmin(self):
        tmitmin = None
        for bpm in self.bpms:
            if bpm.tmit < tmitmin or (tmitmin is None):
                tmitmin = bpm.tmit
        return tmitmin
    
    def tmitmax(self):
        tmitmax = None
        for bpm in self.bpms:
            if bpm.tmit > tmitmax or (tmitmax is None):
                tmitmax = bpm.tmit
        return tmitmax

    def names(self):
        return [bpm.name for bpm in self.bpms]

    def vals(self, axis):
        return [getattr(bpm,axis) for bpm in self.bpms]

    def x_vals(self):
        return self.vals('x')

    def y_vals(self):
        return self.vals('y')

    def tmit_vals(self):
        return self.vals('tmit')

    def x_rms_vals(self):
        return self.vals('x_rms')

    def y_rms_vals(self):
        return self.vals('y_rms')
    
    def tmit_rms_vals(self):
        return self.vals('tmit_rms')

    def z_vals(self):
        return self.vals('z')

    def x_severity_vals(self):
        return self.vals('x_severity')
    
    def y_severity_vals(self):
        return self.vals('y_severity')
    
    def tmit_severity_vals(self):
        return self.vals('tmit_severity')
        
    def x_status_vals(self):
        return self.vals('x_status')
    
    def y_status_vals(self):
        return self.vals('y_status')
    
    def tmit_status_vals(self):
        return self.vals('tmit_status')

    def sort_bpms_by_z(self):
        self.bpms.sort(key=attrgetter('z'))

    def export_to_json(self, filename):
        raise NotImplementedError
    
    def __getitem__(self, item):
        return self.bpms[item]
    
    def __len__(self):
        return len(self._bpms)

    def __iter__(self):
        return iter(self._bpms)

    def to_static(self):
        return self

    def to_dict(self):
        d = {'x': self.vals('x'), 'y': self.vals('y'), 'tmit': self.vals('tmit'), 'z': self.vals('z'), 'x_rms': self.vals('x_rms'), 'y_rms': self.vals('y_rms'), 'tmit_rms': self.vals('tmit_rms'), 'x_severity': self.vals('x_severity'), 'y_severity': self.vals('y_severity'), 'tmit_severity': self.vals('tmit_severity')}
        d['names'] = self.names()
        return d

    def save_to_file(self, filepath='default'):
        self.save_to_MATLAB_file(filepath)
        self.save_to_json(filepath)
    
    def save_to_MATLAB_file(self, filepath='default'):
        if filepath == 'default':
            filename = "orbit"
        else:
            (filepath, filename) = os.path.split(filepath)          
        matlog.save(filename, self.to_dict(), filepath, oned_as="row")

    def save_to_json_file(self, filepath='default'):
        if filepath=='default':
            filename = "orbit-{}.json".format(datetime.now().strftime("%Y-%m-%d-%H%M%S"))
            filepath = os.path.join("/home/physics/mgibbs/orbit_data/", filename)
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f)
        
    def sector_locations(self):
        # This assumes BPM names follow the pattern BPMS:SECTOR:UNITNUMBER
        ticks = []
        current_sector = None
        for (i, bpm) in enumerate(self.bpms):
            bpm_sector = bpm.name.split(':',2)[1]
            if current_sector != bpm_sector:
                current_sector = bpm_sector
                if i==0:
                    z = bpm.z
                else:
                    z = (bpm.z + self.bpms[i-1].z)/2.0
                ticks.append((z, current_sector))
        return ticks

    def rmats(self, from_device=None):
        """Get R-Matrices for each BPM from the model.
        The matrices for this orbit are then cached, for performance reasons.
        If the orbit's bpms property changes, this cache is cleared.

        Returns
        -------
        numpy.ndarray
            A Nx6x6 numpy array with R matrices for each BPM.  N is equal to len(self.bpms)."""
        if self._rmat_cache is None:
            self._rmat_cache = model.get_rmat(self.names())
        return self._rmat_cache

    def fit(self, start, end, fit_point, fit_xpos=True, fit_xang=True, fit_ypos=True, fit_yang=True, fit_energy_difference=True, fit_xkick=True, fit_ykick=True, opt_dict=None):
        """Fit a trajectory to the orbit's BPM readings, given the R-matrices at each BPM.
        Parameters:
        ----------
        start : BaseBPM or int
            The first BPM to include in the fit.
        end : BaseBPM or int
            The last BPM to include in the fit.
        fit_point : BaseBPM or int
            The BPM to use for the initial fit point.
        fit_xpos : Optional[bool]
            Whether or not to fit the x position.
        fit_xang : Optional[bool]
            Whether or not to fit the x angle.
        fit_ypos : Optional[bool]
            Whether or not to fit the y position.
        fit_yang : Optional[bool]
            Whether or not to fit the y angle.
        fit_energy_difference : Optional[bool]
            Whether or not to fit dE/E.
        fit_xkick : Optional[bool]
            Whether or not to fit the x kick.
        fit_ykick : Optional[bool]
            Whether or not to fit the y kick.
        opt_dict : Optional[dict]
            A dictionary which provides keys matching any of the above options. 

        Returns
        -------
        dict
            A dictionary with the following keys:
            'xpos': a numpy.ndarray of fitted x trajectories in mm.
            'ypos': a numpy.ndarray of fitted y trajectories in mm.
            'xpos0': the fitted x position at z0 in mm.
            'xang0': the fitted x angle at z0 in mrad.
            'ypos0': the fitted y position at z0 in mm.
            'yang0': the fitted y angle at z0 in mrad.
            'dE/E': the fitted dE/E in parts per 1000.  Only returned if R16 or R36 > 10mm in the fit region.
            'xkick': the fitted x kick in mrad.
            'ykick': the fitted y kick in mrad.
            'dp': A dictionary with all of the above keys, but this time with values representing the fitted error.
        
        Raises
        ------
        Exception
            If the machine model is not available (usually this is because EPICSv4 could not be imported)
        ValueError
            If the number of R matrices in Rs does not equal the number of BPMs in the orbit.
        """
        #This method is really crappy - its an almost line-for-line port of the MATLAB BPM GUI's fitting routine,
        # which ends up really awkward in numpy.  There are probably performance gains to be had here - unnecessary
        # copies, unnecessary conversions between numpy arrays and numpy matrices, etc.
        if MODEL_AVAILABLE == False:
            raise Exception("Model is not available, cannot perform fitting.")
        if isinstance(start, BaseBPM):
            start_index = self.bpms.index(start)
        else:
            start_index = int(start)
        if isinstance(end, BaseBPM):
            end_index = self.bpms.index(end)
        else:
            end_index = int(end)
        if isinstance(fit_point, BaseBPM):
            z0 = fit_point.z
            fit_point_index = self.bpms.index(fit_point)
        else:
            fit_point_index = int(fit_point)
            z0 = self.bpms[fit_point_index].z

        if start_index == self._saved_fit_start and end_index == self._saved_fit_end and fit_point_index == self._saved_fit_point:
            Rs = self._rmats_for_fit
        else:
            Rs = model.get_rmat(self.bpms[fit_point_index].name, self.names())
            self._rmats_for_fit = Rs
            self._saved_fit_start = start_index
            self._saved_fit_end = end_index
            self._saved_fit_point = fit_point_index
        Rs = Rs[start_index:end_index+1]
        zs = np.array(self.z_vals())[start_index:end_index+1]
        xs = np.array(self.x_vals())[start_index:end_index+1]
        ys = np.array(self.y_vals())[start_index:end_index+1]
        dxs = np.array(self.x_rms_vals())[start_index:end_index+1]
        #dxs = np.ones(len(zs))/1.0e-3
        dys = np.array(self.y_rms_vals())[start_index:end_index+1]
        #dys = np.ones(len(zs))/1.0e-3
        tmit_sevrs = np.array(self.tmit_severity_vals())[start_index:end_index+1]
        
        #Filter out BPMS with bad TMIT severity (usually a good indicator of no beam)
        tmit_good = np.where(tmit_sevrs == 0)
        tmit_sevrs = tmit_sevrs[tmit_good]
        num_bpms = len(tmit_sevrs)
        if num_bpms == 0:
            self.fit_data = None
            raise NoValidBPMDataException("No BPMS with sufficient TMIT for fit.")
        zs = zs[tmit_good]
        xs = xs[tmit_good]
        ys = ys[tmit_good]
        dxs = dxs[tmit_good]
        dys = dys[tmit_good]
        Rs = Rs[tmit_good]
        if Rs.shape != (num_bpms,6,6):
            raise ValueError("Number of R matrices in Rs does not equal the number of BPMs in the orbit.")
        xsf = np.zeros((1, num_bpms))
        ysf = np.zeros((1, num_bpms))

        #Grab just the R1s and R3s, except for R15 and R35.
        R1s = Rs[:, 0, [0, 1, 2, 3, 5]]
        R3s = Rs[:, 2, [0, 1, 2, 3, 5]]

        if not (np.any(np.abs(R1s[:, 4]) > 0.010) or np.any(np.abs(R3s[:,4]) > 0.010)):
            #Not enough dispersion to fit energy, disabling energy fit.
            fit_energy_difference = False
        
        I = np.where(np.array([fit_xpos, fit_xang, fit_ypos, fit_yang, fit_energy_difference, fit_xkick, fit_ykick]))[0]
        R1s_kick = R1s.copy()
        R3s_kick = R3s.copy()
        R1s_kick[zs <= z0, :] = 0.0
        R3s_kick[zs <= z0, :] = 0.0
        R1s_kick = np.mat(R1s_kick)
        R3s_kick = np.mat(R3s_kick)
        R1s = np.append(R1s, R1s_kick[:,1], 1)
        R1s = np.append(R1s, R1s_kick[:,3], 1)
        R3s = np.append(R3s, R3s_kick[:,1], 1)
        R3s = np.append(R3s, R3s_kick[:,3], 1)
        Q = np.append(R1s[:, I], R3s[:, I], 0)
        S = np.mat(np.append(xs, ys, 0)).transpose()
        dS = np.mat(np.append(dxs, dys, 0)).transpose()
        #print(S.shape)
        if np.all(dS == 0.0):
            #Fit without any weighting
            Ssf, dSsf, p1, dp1, chisq, V = fit.fit(Q, S)
        else:
            #Fit with weighting
            Ssf, dSsf, p1, dp1, chisq, V = fit.fit(Q, S, dS)
        nr, nc = np.shape(V)
        p = np.array(p1[:,0])
        #print("p = {}".format(p))
        dp = np.array(dp1[:])
        #print("Ssf = {}".format(Ssf))
        Xsf = np.array(Ssf[0:num_bpms])
        #print("X vals = {}".format(Xsf))
        Ysf = np.array(Ssf[num_bpms:])
        #print("Y vals = {}".format(Ysf))
        Vs = np.reshape(V, (1,nr*nc))
        result = {}
        result['xpos'] = Xsf.flatten()
        result['ypos'] = Ysf.flatten()
        result['zs'] = zs
        result['xpos0'] = p[I==0][0][0] if (I==0).any() else None
        result['xang0'] = p[I==1][0][0] if (I==1).any() else None
        result['ypos0'] = p[I==2][0][0] if (I==2).any() else None
        result['yang0'] = p[I==3][0][0] if (I==3).any() else None
        result['dE/E'] = p[I==4][0][0] if (I==4).any() else None
        result['xkick'] = p[I==5][0][0] if (I==5).any() else None
        result['ykick'] = p[I==6][0][0] if (I==6).any() else None
        self.fit_data = result
        return self.fit_data
        
    @property
    def enable_fitting(self):
        return self._enable_fitting
    
    @enable_fitting.setter
    def enable_fitting(self, enabled=True):
        self._enable_fitting = enabled

    #def set_fit_options(self, 

#Generic code to get an array of PVs from aidalist.
def get_pv_list(pattern):
    return subprocess.check_output(['eget','-ts','ds','-a','name={}'.format(pattern)]).splitlines()[:-1]

class Orbit(BaseOrbit):
    @classmethod
    def lcls_bpm_list(cls, use_cache=True):
        if use_cache:
            cache_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)),'bpm_names.pkl')
            #First, try loading our PV list from a cache file.
            try:
                with open(cache_filename, 'rb') as cache:
                    name_list = pickle.load(cache)
                    if len(name_list) > 0:
                        #print("Num BPMs: " + str(len(name_list)))
                        return name_list
            except IOError:
                pass
        sectors = ['IN20', 'LI21', 'LI22', 'LI23', 'LI24', 'LI25', 'LI26', 'LI27', 'LI28', 'LI29', 'LI30', 'CLTH', 'BSYH', 'LTU%', 'UND%', 'DMP%']
        return cls.get_bpm_names(sectors, cache_filename)

    @classmethod
    def get_bpm_names(cls, sectors, cache_filename=None):
        name_list = [pv[:-2] for pv in cls.get_z_pvs(sectors)]
        if cache_filename is not None:
            with open(cache_filename, 'wb') as cache:
                pickle.dump(name_list, cache)
        return name_list
    
    @classmethod
    def get_z_pvs(cls, sectors):
        pv_list = []
        for sector in sectors:
            pv_list.extend(get_pv_list('BPMS:{sector}:%:Z'.format(sector=sector)))
            #Filter out the stupid spectrometer line BPMS, and BSY BPM 52.
            pv_list = [pv for pv in pv_list if not re.match('BPMS:(IN20:(821|925|945|981)|BSY0:52|UND1:3395):Z',pv)]
        return pv_list

    @classmethod
    def lcls_bpms(cls, edef=None, auto_connect=True):
        return cls(cls.lcls_bpm_list(), edef=edef, auto_connect=auto_connect)
    @classmethod
    def lcls_energy_bpms(cls):
        return ['BPMS:IN20:731','BPMS:LI21:233','BPMS:LI24:801','BPMS:LTU1:250','BPMS:LTU1:450','BPMS:DMP1:502','BPMS:DMP1:693']

class NoValidBPMDataException(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)
