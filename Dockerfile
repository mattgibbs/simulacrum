FROM ubuntu:18.04 as sim_builder
RUN apt-get update && \
    apt-get -y install build-essential xterm man wget readline-common libreadline-dev sudo unzip \
                       cmake autoconf automake libtool m4 gfortran libtool-bin xorg xorg-dev bc \
                       libopenmpi-dev gfortran-multilib
WORKDIR /tmp
RUN wget -nv https://www.classe.cornell.edu/~cesrulib/downloads/tarballs/bmad_dist_2019_0129.tgz
WORKDIR /
RUN tar -xvf /tmp/bmad_dist_2019_0129.tgz -C /
COPY bmad_env.bash /bmad_dist_2019_0129/bmad_env.bash
SHELL ["/bin/bash", "-c"]
RUN ln -s /usr/bin/make /usr/bin/gmake
RUN cd /bmad_dist_2019_0129 && \
    pwd && \
    ls -la && \
    source ./bmad_env.bash && \
    sed -i 's/ACC_ENABLE_OPENMP.*/ACC_ENABLE_OPENMP="Y"/' /bmad_dist_2019_0129/util/dist_prefs && \
    sed -i 's/ACC_ENABLE_MPI.*/ACC_ENABLE_MPI="Y"/' /bmad_dist_2019_0129/util/dist_prefs && \
    sed -i 's/ACC_ENABLE_SHARED.*/ACC_ENABLE_SHARED="Y"/' /bmad_dist_2019_0129/util/dist_prefs && \
    sed -i 's/ACC_ENABLE_MPI.*/ACC_ENABLE_MPI="Y"/' /bmad_dist_2019_0129/util/dist_prefs && \
    sed -i 's:CMAKE_Fortran_COMPILER\} MATCHES "ifort":CMAKE_Fortran_COMPILER\} STREQUAL "ifort":' /bmad_dist_2019_0129/build_system/Master.cmake && \
    sed -i '/export PACKAGE_VERSION=/a source .\/VERSION' /bmad_dist_2019_0129/openmpi/acc_build_openmpi
WORKDIR /bmad_dist_2019_0129
RUN source ./bmad_env.bash && ./util/dist_build_production


FROM ubuntu:18.04
COPY --from=sim_builder /bmad_dist_2019_0129/bmad /bmad_dist_2019_0129/bmad
COPY --from=sim_builder /bmad_dist_2019_0129/build_system /bmad_dist_2019_0129/build_system
COPY --from=sim_builder /bmad_dist_2019_0129/util /bmad_dist_2019_0129/util
COPY --from=sim_builder /bmad_dist_2019_0129/tao /bmad_dist_2019_0129/tao
COPY --from=sim_builder /bmad_dist_2019_0129/production /bmad_dist_2019_0129/production
COPY bmad_env.bash /bmad_dist_2019_0129/bmad_env.bash
RUN apt-get update && apt-get -y install readline-common python3 python3-pip libzmq5 libx11-6 gfortran
RUN ln -s /usr/bin/python3 /usr/bin/python
RUN pip3 install numpy caproto pyzmq
SHELL ["/bin/bash", "-c"]
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
ENTRYPOINT cd /bmad_dist_2019_0129 && source ./bmad_env.bash && cd /model_service && (python3 model_service.py &) && cd /bpm_sim && python3 bpm_service.py