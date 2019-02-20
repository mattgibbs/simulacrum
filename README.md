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

The project provides a Dockerfile, which can be used to build a fully isolated container containing everything you need to get going.  You can either pull a pre-build image from Docker Hub (`docker pull itsmattgibbs/simulacrum`), or clone the Simulacrum repository and build the container yourself (this takes several hours).
