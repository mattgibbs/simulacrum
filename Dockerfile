FROM ubuntu:18.04
RUN apt-get update && \
    apt-get -y install build-essential xterm man wget readline-common libreadline-dev sudo unzip \
                       cmake autoconf automake libtool m4 gfortran libtool-bin xorg xorg-dev bc \
                       libopenmpi-dev gfortran-multilib
WORKDIR /tmp
RUN wget -nv https://www.classe.cornell.edu/~cesrulib/downloads/tarballs/bmad_dist_2019_0124.tgz
WORKDIR /
RUN tar -xvf /tmp/bmad_dist_2019_0124.tgz -C /
COPY bmad_env.bash /bmad_dist_2019_0124/bmad_env.bash
SHELL ["/bin/bash", "-c"]
RUN ln -s /usr/bin/make /usr/bin/gmake
RUN cd /bmad_dist_2019_0124 && \
    pwd && \
    ls -la && \
    source ./bmad_env.bash && \
    sed -i 's/ACC_ENABLE_OPENMP.*/ACC_ENABLE_OPENMP="Y"/' /bmad_dist_2019_0124/util/dist_prefs && \
    sed -i 's/ACC_ENABLE_MPI.*/ACC_ENABLE_MPI="Y"/' /bmad_dist_2019_0124/util/dist_prefs && \
    sed -i 's/ACC_ENABLE_SHARED.*/ACC_ENABLE_SHARED="Y"/' /bmad_dist_2019_0124/util/dist_prefs && \
    sed -i 's/ACC_ENABLE_MPI.*/ACC_ENABLE_MPI="Y"/' /bmad_dist_2019_0124/util/dist_prefs && \
    sed -i 's:CMAKE_Fortran_COMPILER\} MATCHES "ifort":CMAKE_Fortran_COMPILER\} STREQUAL "ifort":' /bmad_dist_2019_0124/build_system/Master.cmake && \
    sed -i '/export PACKAGE_VERSION=/a source .\/VERSION' /bmad_dist_2019_0124/openmpi/acc_build_openmpi
WORKDIR /bmad_dist_2019_0124
RUN source ./bmad_env.bash && ./util/dist_build_production
WORKDIR /
RUN apt-get -y install python3 python3-pip libzmq3-dev
RUN ln -s /usr/bin/python3 /usr/bin/python
RUN pip3 install numpy caproto pyzmq
COPY . /simulacrum
RUN cd /simulacrum && pip3 install . 
COPY bpm_sim /bpm_sim
COPY model_service /model_service
ENV MODEL_PORT 12312
ENV ORBIT_PORT 56789
ENV EPICS_CA_SERVER_PORT 5064
ENV EPICS_CA_REPEATER_PORT 5065
EXPOSE ${MODEL_PORT}
EXPOSE ${ORBIT_PORT}
EXPOSE ${EPICS_CA_SERVER_PORT}
ENTRYPOINT cd /bmad_dist_2019_0124 && source ./bmad_env.bash && cd /model_service && (python3 model_service.py &) && cd /bpm_sim && python3 bpm_service.py
