#!/bin/bash
docker run -p 5064:5064 -p 5065:5065 -p 5064:5064/udp -p 5065:5065/udp -it --name simul simulacrum:latest