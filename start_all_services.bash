#!/bin/bash
(/model_service/model_service.py &) && cd /bpm_service && (python3 bpm_service.py &) && cd /magnet_service && python3 magnet_service.py 