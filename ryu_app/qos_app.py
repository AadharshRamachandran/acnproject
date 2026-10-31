"""Learning switch and queue classification for the QoS research testbed.

OVS 2.13 does not implement OpenFlow OFPMP_QUEUE_STATS multipart replies for
Linux-HTB queues; any OFPQueueStatsRequest is silently dropped by the switch.
Queue telemetry is therefore collected by the experiment runner directly from
``tc -s class show`` (see manager/collector.py).  This app is responsible only
for:

  1. Installing the table-miss flow and learning per-datapath MAC→port mappings.
  2. Classifying packets by destination port and setting the OVS queue action.
"""
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER, set_ev_cls
from ryu.lib.packet import ethernet, ether_types, ipv4, packet, tcp, udp
from ryu.ofproto import ofproto_v1_3

from manager.config import load_config


CONFIG = load_config(os.environ.get("QOS_CONFIG", str(Path(__file__).resolve().parents[1] / "config.yaml")))


class SafeQoSController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mac_to_port = defaultdict(dict)
        self.datapaths = {}

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features(self, ev):
        dp = ev.msg.datapath
        self.datapaths[dp.id] = dp
        p, o = dp.ofproto_parser, dp.ofproto
        # Install table-miss: send unknown packets to the controller.
        self.add_flow(dp, 0, p.OFPMatch(), [p.OFPActionOutput(o.OFPP_CONTROLLER, o.OFPCML_NO_BUFFER)])

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def state_change(self, ev):
        if ev.state == MAIN_DISPATCHER:
            self.datapaths[ev.datapath.id] = ev.datapath
        elif ev.state == DEAD_DISPATCHER:
            self.datapaths.pop(ev.datapath.id, None)

    def add_flow(self, dp, priority, match, actions, idle=0):
        p, o = dp.ofproto_parser, dp.ofproto
        inst = [p.OFPInstructionActions(o.OFPIT_APPLY_ACTIONS, actions)]
        dp.send_msg(p.OFPFlowMod(datapath=dp, priority=priority, match=match,
                                 instructions=inst, idle_timeout=idle))

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in(self, ev):
        msg, dp = ev.msg, ev.msg.datapath
        p, o = dp.ofproto_parser, dp.ofproto
        in_port = msg.match["in_port"]
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return
        self.mac_to_port[dp.id][eth.src] = in_port
        out_port = self.mac_to_port[dp.id].get(eth.dst, o.OFPP_FLOOD)
        actions, match = [], None
        if out_port != o.OFPP_FLOOD:
            match, queue = self._classify(p, pkt, eth, in_port)
            if dp.id == CONFIG["runtime"]["switch_dpid"] and queue is not None:
                actions.append(p.OFPActionSetQueue(queue))
        actions.append(p.OFPActionOutput(out_port))
        if match:
            self.add_flow(dp, 10, match, actions, idle=30)
        data = msg.data if msg.buffer_id == o.OFP_NO_BUFFER else None
        dp.send_msg(p.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id, in_port=in_port,
                                  actions=actions, data=data))

    def _classify(self, parser, pkt, eth, in_port):
        ip = pkt.get_protocol(ipv4.ipv4)
        l4 = pkt.get_protocol(udp.udp) or pkt.get_protocol(tcp.tcp)
        if ip is None or l4 is None:
            return parser.OFPMatch(in_port=in_port, eth_dst=eth.dst, eth_src=eth.src), None
        ports = CONFIG["network"]["ports"]
        queues = CONFIG["network"]["queue_ids"]
        port_to_class = {int(ports[name]): name for name in ports}
        traffic_class = port_to_class.get(l4.dst_port)
        if traffic_class is None:
            return parser.OFPMatch(in_port=in_port, eth_dst=eth.dst, eth_src=eth.src), None
        fields = {"in_port": in_port, "eth_type": ether_types.ETH_TYPE_IP,
                  "ipv4_src": ip.src, "ipv4_dst": ip.dst, "ip_proto": ip.proto}
        fields["udp_dst" if isinstance(l4, udp.udp) else "tcp_dst"] = l4.dst_port
        return parser.OFPMatch(**fields), queues[traffic_class]

    @set_ev_cls(ofp_event.EventOFPErrorMsg, MAIN_DISPATCHER)
    def openflow_error(self, ev):
        self.logger.error("OpenFlow error from dpid %s xid %s: type=%s code=%s",
                          ev.msg.datapath.id, ev.msg.xid,
                          ev.msg.type, ev.msg.code)
