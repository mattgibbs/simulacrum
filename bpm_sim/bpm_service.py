from caproto.server import ioc_arg_parser, run
from simulacrum import Service
import bpm

class BPMService(Service):
    def __init__(self):
        super().__init__()
        self.add_route("BPMS:.+:[0-9]+:(X|Y|TMIT|Z)", 
                        data_type=float,
                        get=bpm.get,
                        new_subscription=bpm.subscribe,
                        remove_subscription=bpm.unsubscribe)

def main():
    _, run_options = ioc_arg_parser(
        default_prefix='',
        desc="PV black hole")
    service = BPMService()  
    run(service, **run_options)

if __name__ == '__main__':
    main()