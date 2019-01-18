import numpy as np
PVACCESS_AVAILABLE = False
try:
	import pvaccess
	PVACCESS_AVAILABLE = True
except ImportError:
	pass
from itertools import cycle
from collections import OrderedDict

def get_rmat(from_device, to_device=[], use_design=False, from_pos='MIDDLE', to_pos='MIDDLE', full_model=None, ignore_bad_names=False):
	if isinstance(from_device, bytes):
		from_device = [from_device]
	if isinstance(to_device, bytes):
		to_device = [to_device]
	if len(from_device) > 1 and len(to_device) > 1 and len(from_device) != len(to_device):
		raise Exception("Length of from_device must match length of to_device if both have length > 1.")
	if len(to_device) == 0:
		to_device = list(from_device)
		from_device = [b'CATH:IN20:111']
	if full_model is None:
		full_model = get_full_machine_model(use_design)
	device_list = list(zip(from_device, cycle(to_device)) if len(from_device) > len(to_device) else zip(cycle(from_device), to_device))
	rmats = np.zeros((len(device_list),6,6))
	i = 0
	for dev_pair in device_list:
		a, b = dev_pair
		a_index = np.where(full_model['epics_channel_access_name'] == a)
		if len(a_index[0]) > 1:
			a_index = a_index & (full_model['position_index'] == from_pos)
		b_index = np.where(full_model['epics_channel_access_name'] == b)
		if len(b_index[0]) > 1:
			b_index = b_index & (full_model['position_index'] == to_pos)
		try:
			a_mat = np.mat(full_model[a_index][0]['r_mat'])
		except IndexError:
			msg = "Device with name {name} not found in the machine model.".format(name=a)
			if ignore_bad_names:
				print(msg)
				a_mat = np.zeros((6,6))
				a_mat.fill(np.nan)
				a_mat = np.asmatrix(a_mat)
			else:
				raise IndexError(msg)
		try:
			b_mat = np.mat(full_model[b_index][0]['r_mat'])
		except IndexError:
			msg = "Device with name {name} not found in the machine model.".format(name=b)
			if ignore_bad_names:
				print(msg)
				b_mat = np.zeros((6,6))
				b_mat.fill(np.nan)
				b_mat = np.asmatrix(b_mat)
			else:
				raise IndexError(msg)
		rmats[i] = b_mat * np.linalg.inv(a_mat)
		i += 1
	if i == 1:
		return rmats[0]
	return rmats

def get_zpos(device_list, pos='MIDDLE', full_model=None, ignore_bad_names=False):
	if isinstance(device_list, bytes):
		device_list = [device_list]
	if full_model is None:
		full_model = get_full_machine_model()
	z_pos = np.zeros((len(device_list)))
	i = 0
	for dev in device_list:
		dev_index = np.where(full_model['epics_channel_access_name'] == bytes(dev, encoding='ascii'))
		if len(dev_index[0]) > 1:
			dev_index = dev_index & (full_model['position_index'] == pos)
		if len(dev_index[0]) > 0:
			z_pos[i] = full_model[dev_index][0]['z_position']
		else:
			msg = "BPM with name {name} not found in the machine model, could not get Z position.".format(name=dev)
			if ignore_bad_names:
				print(msg)
				z_pos[i] = None
			else:
				raise IndexError(msg)
		i += 1
	if i == 1:
		return z_pos[0]
	return z_pos

def get_full_machine_model(use_design=False):
	if not PVACCESS_AVAILABLE:
		raise NoPVAccessException
	request = pvaccess.PvObject(OrderedDict([('scheme', pvaccess.STRING), ('path', pvaccess.STRING)]), 'epics:nt/NTURI:1.0')
	model_type = "EXTANT"
	if use_design:
		model_type = "DESIGN"
	path = "MODEL:RMATS:{}:FULLMACHINE".format(model_type)
	rpc = pvaccess.RpcClient(path)
	request.set(OrderedDict([('scheme', 'pva'), ('path', path)]))
	response = rpc.invoke(request).getStructure()
	m = np.zeros(len(response['ELEMENT_NAME']), dtype=[('ordinal', 'i16'),('element_name', 'a60'), ('epics_channel_access_name', 'a60'), ('position_index', 'a6'), ('z_position', 'float32'), ('r_mat', 'float32', (6,6))])
	m['ordinal'] = response['ORDINAL']
	m['element_name'] = response['ELEMENT_NAME']
	m['epics_channel_access_name'] = response['EPICS_CHANNEL_ACCESS_NAME']
	m['position_index'] = response['POSITION_INDEX']
	m['z_position'] = response['Z_POSITION']
	m['r_mat'] = np.reshape(np.array([response['R11'], response['R12'], response['R13'], response['R14'], response['R15'], response['R16'], response['R21'], response['R22'], response['R23'], response['R24'], response['R25'], response['R26'], response['R31'], response['R32'], response['R33'], response['R34'], response['R35'], response['R36'], response['R41'], response['R42'], response['R43'], response['R44'], response['R45'], response['R46'], response['R51'], response['R52'], response['R53'], response['R54'], response['R55'], response['R56'], response['R61'], response['R62'], response['R63'], response['R64'], response['R65'], response['R66']]).T, (-1,6,6))
	return m


class NoPVAccessException(Exception):
	pass

if __name__ == '__main__':
	rmats = get_r_matrix('BPMS:LI23:201',['BPMS:LI23:301','BPMS:LI23:401'])
	print(rmats)
	rmat = get_r_matrix('BPMS:LI24:801')
	print(rmat)
