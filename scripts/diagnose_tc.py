#!/usr/bin/env python3
"""Diagnostic: check what tc and OVS actually have during a live Mininet run."""
import subprocess
import sys
import os
import time

sys.path.insert(0, "/app")
from manager.config import load_config
from manager.actuator import setup_qos
from topo.research_topo import ResearchTopo, bottleneck_interface

from mininet.link import TCLink
from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.node import OVSSwitch

setLogLevel("warning")
subprocess.run(["mn", "-c"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

config = load_config("/app/config.yaml")
from functools import partial
switch = partial(OVSSwitch, protocols="OpenFlow13", failMode="standalone")
net = Mininet(topo=ResearchTopo(config), switch=switch, link=TCLink,
              controller=None, autoSetMacs=True, build=False)
net.start()

s1 = net.get("s1")
interface = bottleneck_interface(net)
port_no = s1.ports[s1.intf(interface)]
config["runtime"]["bottleneck_port_no"] = int(port_no)
print(f"Bottleneck interface: {interface}, port_no: {port_no}")

queue_uuids = setup_qos(interface, config)
print(f"Queue UUIDs: {queue_uuids}")

time.sleep(1)  # let OVS apply

print("\n=== tc -s qdisc show dev", interface, "===")
subprocess.run(["tc", "-s", "qdisc", "show", "dev", interface])

print("\n=== tc -s class show dev", interface, "===")
subprocess.run(["tc", "-s", "class", "show", "dev", interface])

# Also check the bridge interface 's1'
print("\n=== tc -s class show dev s1 ===")
subprocess.run(["tc", "-s", "class", "show", "dev", "s1"])

# Also check ovs-ofctl queue-stats
print("\n=== ovs-ofctl queue-stats s1 ===")
subprocess.run(["ovs-ofctl", "queue-stats", "s1"])

# List all network interfaces that have qdiscs
print("\n=== tc qdisc show (all) ===")
subprocess.run(["tc", "qdisc", "show"])

# List OVS QoS record
print("\n=== ovs-vsctl list QoS ===")
subprocess.run(["ovs-vsctl", "list", "QoS"])

net.stop()
subprocess.run(["mn", "-c"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
