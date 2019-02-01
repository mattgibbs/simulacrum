#!/bin/bash
export DIST_BASE_DIR=/bmad_dist_2019_0124
source ${DIST_BASE_DIR}/util/dist_source_me
ulimit -S -c 0
ulimit -S -d 25165824