"""Six-host research topology with one instrumented inter-switch bottleneck."""
from mininet.topo import Topo


class ResearchTopo(Topo):
    def build(self, config):
        s1 = self.addSwitch("s1", protocols="OpenFlow13")
        s2 = self.addSwitch("s2", protocols="OpenFlow13")
        for cls, ip in config["network"]["source_ips"].items():
            host = self.addHost(f"h_{cls}_src", ip=f"{ip}/24")
            # Linux IFNAMSIZ allows at most 15 visible characters. Mininet's
            # default h_video_src-eth0 exceeds it, so retain node aliases while
            # explicitly assigning short interface names.
            short = {"voip": "vs0", "video": "xs0", "bulk": "bs0"}[cls]
            self.addLink(host, s1, intfName1=short)
        for cls, ip in config["network"]["server_ips"].items():
            host = self.addHost(f"h_{cls}_dst", ip=f"{ip}/24")
            short = {"voip": "vd0", "video": "xd0", "bulk": "bd0"}[cls]
            self.addLink(s2, host, intfName2=short)
        link = self.addLink(s1, s2, bw=config["network"]["bandwidth_mbps"],
                            delay=f"{config['network']['delay_ms']}ms",
                            max_queue_size=config["network"]["queue_size"])
        self.bottleneck_link = link


def bottleneck_interface(net):
    """Discover the s1 egress interface connected to s2 from the live topology."""
    s2 = net.get("s2")
    for intf in net.get("s1").intfList():
        if intf.link and (intf.link.intf1.node is s2 or intf.link.intf2.node is s2):
            return intf.name
    raise RuntimeError("Could not discover the s1-s2 bottleneck interface")
