OBSTRUCTOR SERVICE

This service simulates devices that destructively interfere with the electron beam including stoppers, collimators and screens. This service communicates with the model by sending/receiving PyTao objects via ZeroMQ and can communicate with the user (and their software) via EPICS Channel Access.

Currently supported PVs:

TD11
  DUMP:LI21:305:TGT_STS      read-only PV describes stopper status (1=OUT, 2=IN, 3=INCONSISTENT)
  DUMP:LI21:305:CTRL         control PV to which user can caput IN or OUT status
  
TDUND
  DUMP:LTU1:970:TGT_STS      read-only PV describes stopper status (1=OUT, 2=IN, 3=INCONSISTENT)
  DUMP:LTU1:970:CTRL         control PV to which user can caput IN or OUT status

CE11 (horn-cutting)
When simulating collimators, my goal is to stay consistent with the existing controls system. The collimator service supports independent readback and control of the left jaw, right jaw, gap, and center and propogates appropriately the changes dictated by the user. 

  COLL:LI21:GETGAP          read-only PV describing collimator gap size in mm
  COLL:LI21:SETGAP          control PV for collimator gap size in mm
  
  COLL:LI21:GETCENTER       read-only PV describing collimator center in mm
  COLL:LI21:SETCENTER       control PV describing collimator gap size in mm
  
  COLL:LI21:GETLEFT         read-only PV describing collimator gap size in mm
  COLL:LI21:SETLEFT         read-only PV describing collimator gap size in mm
  
  COLL:LI21:GETRIGHT        read-only PV describing collimator gap size in mm
  COLL:LI21:SETRIGHT        read-only PV describing collimator gap size in mm
  


The goal of this project is to 'run unmodified accelerator software (and develop new software), but with data coming from the simulator, rather than the real machine...' so insight from you, the user, as to what features and use cases you would be interested in will help drive the development. For feedback and suggestions regarding this service, please contact: yshtalen@slac.stanford.edu
