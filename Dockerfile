# This root-level alias uses the same Ryu-compatible image setup as compose.
FROM ubuntu:20.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    openvswitch-switch openvswitch-common openvswitch-testcontroller \
    python3 python3-pip python3-dev python3-setuptools build-essential git \
    iperf3 iproute2 iputils-ping net-tools psmisc socat tcpdump ethtool kmod sudo \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch 2.3.0 https://github.com/mininet/mininet.git /opt/mininet \
    && cd /opt/mininet && make mnexec && install -m 755 mnexec /usr/local/bin/mnexec \
    && python3 setup.py install && rm -rf /opt/mininet
COPY docker/requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt
WORKDIR /app
COPY . .
RUN chmod +x docker/entrypoint.sh
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["bash"]
