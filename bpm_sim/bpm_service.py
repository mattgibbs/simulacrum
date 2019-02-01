from caproto.server import ioc_arg_parser, run
from simulacrum import Service
import bpm

class BPMService(Service):
    def __init__(self):
        super().__init__()
        self.bpms = bpm.BPMSim()
        self.add_route("BPMS:.+:[0-9]+:(X|Y|TMIT|Z)", 
                        data_type=float,
                        get=self.bpms.get,
                        new_subscription=self.bpms.subscribe,
                        remove_subscription=self.bpms.unsubscribe)

def main():
    _, run_options = ioc_arg_parser(
        default_prefix='',
        desc="Simulated BPM Service")
    service = BPMService()  
    run(service, **run_options)

if __name__ == '__main__':
    main()