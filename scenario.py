"""Integration: run one congestion scenario end-to-end.

Timeline (seconds):
    0        start voip + video (steady state)
    T_CONG   start bulk flows  -> bottleneck saturates
    T_END    everything stops, analysis runs

Usage (inside the container, with ryu-manager already running):
    sudo python3 scenario.py --mode none      # no QoS: raw congestion
    sudo python3 scenario.py --mode static    # static OVS queues
    sudo python3 scenario.py --mode adaptive  # static queues + adaptive manager
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mininet.log import setLogLevel

from common import config as cfg
from controller import qos_setup
from controller.adaptive_manager import AdaptiveQoSManager
from monitoring.analyze import analyze
from monitoring.metrics_collector import create_collector
from topology.topo import bottleneck_port, build_net
from traffic import generators as gen

MODES = ["none", "static", "adaptive", "rule-polling", "rule-telemetry",
         "rl-polling", "rl-telemetry"]


def run(mode, t_cong, t_end, tag="", policy_path="results/rl/rl_policy.json", seed=None,
        signal_source=None, include_probes=False):
    rl_mode = mode in ("rl-polling", "rl-telemetry")
    if rl_mode and not os.path.exists(policy_path):
        raise FileNotFoundError(f"RL policy missing: {policy_path}; train it with controller/train_rl.py first")
    name = f"{datetime.now():%Y%m%d-%H%M%S-%f}-{mode}{('-' + tag) if tag else ''}"
    run_dir = os.path.join(cfg.RESULTS_DIR, name)
    os.makedirs(run_dir, exist_ok=True)

    net = build_net()
    net.start()
    port = bottleneck_port(net)
    print(f"[scenario] mode={mode} bottleneck_port={port} run_dir={run_dir}")

    qos_mode = mode in ("static", "adaptive", "rule-polling", "rule-telemetry", "rl-polling", "rl-telemetry")
    chosen_source = signal_source or ("telemetry" if mode in ("rule-telemetry", "rl-telemetry")
                                      else cfg.SIGNAL_SOURCE)
    if chosen_source not in ("polling", "telemetry"):
        raise ValueError("signal_source must be 'polling' or 'telemetry'")
    telemetry_mode = chosen_source == "telemetry"
    if qos_mode:
        qos_setup.apply_static_qos(port)
    else:
        qos_setup.clear_qos(port)

    # Let the controller learn MACs before measurements begin.
    net.pingAll()

    server = net.get("server")
    gen.start_servers(server, run_dir)
    time.sleep(1)

    collector = create_collector(net, run_dir, port, chosen_source)
    collector.start()

    manager = None
    probe_processes = []
    probes_enabled = telemetry_mode or rl_mode or include_probes
    if probes_enabled:
        probe_file = os.path.join(run_dir, "probes.csv")
        receiver = server.popen(["python3", "/app/monitoring/probe_agent.py", "receive",
                                 "--output", probe_file, "--duration", str(t_end + 5)])
        probe_processes.append(receiver)
        time.sleep(0.2)
        for i, (cls, host_name) in enumerate((("voip", "voip"), ("video", "video"), ("bulk", "bulk"))):
            proc = net.get(host_name).popen(["python3", "/app/monitoring/probe_agent.py", "send",
                "--host", cfg.SERVER_IP, "--port", str(cfg.PROBE_PORTS[cls]),
                "--rate", str(cfg.PROBE_RATE_HZ), "--duration", str(t_end + 2),
                "--seed", str((seed or 0) + i)])
            probe_processes.append(proc)
    if mode in ("adaptive", "rule-polling", "rule-telemetry"):
        manager = AdaptiveQoSManager(port, collector, run_dir)
        manager.start()
    elif rl_mode:
        from controller.rl_manager import RLQoSManager
        manager = RLQoSManager(port, collector, run_dir, policy_path)
        manager.start()

    gen.start_voip(net.get("voip"), run_dir, t_end)
    gen.start_video(net.get("video"), run_dir, t_end)
    print(f"[scenario] steady state for {t_cong}s")
    time.sleep(t_cong)

    print(f"[scenario] injecting bulk traffic for {t_end - t_cong}s")
    bulk_start_sample_t = collector.elapsed_now() if hasattr(collector, "elapsed_now") else None
    gen.start_bulk(net.get("bulk"), run_dir, t_end - t_cong)
    time.sleep(t_end - t_cong + 2)

    if manager:
        manager.stop()
    collector.stop()
    for proc in probe_processes:
        proc.terminate()
    gen.stop_all(net)
    qos_setup.clear_qos(port)
    net.stop()

    with open(os.path.join(run_dir, "run_meta.json"), "w") as f:
        json.dump({"mode": mode, "t_cong": t_cong, "t_end": t_end,
                   "signal_source": "telemetry" if telemetry_mode else "polling",
                   "controller": "rl" if rl_mode else ("rule" if mode in ("adaptive", "rule-polling", "rule-telemetry") else "none"),
                   "seed": seed, "probes_enabled": probes_enabled,
                   "t_cong_sample": bulk_start_sample_t}, f)

    print("[scenario] analysing")
    analyze(run_dir)
    print(f"[scenario] done -> {run_dir}/metrics.png")
    return run_dir


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=MODES, default="static")
    p.add_argument("--t-cong", type=int, default=15, help="seconds before bulk starts")
    p.add_argument("--t-end", type=int, default=45, help="total run length")
    p.add_argument("--tag", default="", help="suffix for the run directory")
    p.add_argument("--policy", default="results/rl/rl_policy.json")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--signal-source", choices=("polling", "telemetry"), default=None)
    args = p.parse_args()
    setLogLevel("info")
    run(args.mode, args.t_cong, args.t_end, args.tag, args.policy, args.seed, args.signal_source)
