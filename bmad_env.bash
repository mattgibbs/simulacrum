#!/bin/bash
export DIST_BASE_DIR=/bmad
source ${DIST_BASE_DIR}/util/dist_source_me
ulimit -S -c 0
ulimit -S -d 25165824