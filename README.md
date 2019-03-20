# Simulacrum: The LCLS Accelerator Simulator

> simulacrum (Noun):
>	1. An image or representation of someone or something.
>	*'a small-scale simulacrum of a skyscraper'*
>
>	1.1 An unsatisfactory imitation or substitute.
>	*'a bland simulacrum of American soul music'*
>
> --Oxford English Dictionary

Simulacrum is a system to simulate the LCLS accelerator and its control system.  It is comprised of a set of "services", individual processes that each simulate a different subsystem.  These processes can communicate with each other via ZeroMQ, can communicate with the user (and their software) via EPICS Channel Access.  The goal of this project is to run unmodified accelerator software (and develop new software), but with data coming from the simulator, rather than the real machine.

The project provides a Dockerfile, which can be used to build a fully isolated container containing everything you need to get going.  You can either pull a pre-build image from Docker Hub (`docker pull itsmattgibbs/simulacrum`), or clone the Simulacrum repository and build the container yourself (the command to build is a one-liner, `docker build -t simulacrum .`, but it will take about two hours to build).

## Running Simulacrum in the container

There are a few different ways you can use the Simulacrum Docker container.

### You can run all services inside the container:
This command starts up every simulation service, and exposes only the EPICS traffic to your local network:
`docker run -p 5064:5064 -p 5064:5064/udp -it simulacrum:latest /start_all_services.bash`

For debug purposes, you might want to also expose the ZeroMQ port that the model service uses for internal communication:
`docker run -p 5064:5064 -p 5064:5064/udp -p 12312:12312 -it simulacrum:latest /start_all_services.bash`

### You can open up a bash terminal inside the container:
If you want to poke around inside the container, this is the best way to do it.
`docker run -it simulacrum:latest /bin/bash`

### For development of new services, it can be useful to run just the model service inside the container, and run your in-development service on your local machine:
This runs the model service, and only exposes the ports for ZeroMQ traffic (no EPICS).  If you want to run a service you are developing on your laptop, this is the best way to do it.
`docker run -p 12312:12312 -p 56789:56789 -it simulacrum:latest /model_service/model_service.py`

