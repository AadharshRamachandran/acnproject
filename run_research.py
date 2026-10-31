"""Run one Mininet/Ryu experiment using the modular adaptive QoS pipeline."""
import argparse
import csv
from functools import partial
import json
import logging
import math
import os
import random
import re
import shutil
import socket
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from manager.actuator import OVSActuator, setup_qos
from manager.config import load_config
from manager.engines import make_engine
from manager.forecaster import EWMAForecaster, HoltForecaster
from manager.guards import DelayBudgetHysteresis, FairnessGuard, SafetyShield, jain_index
from manager.budgets import class_delay_budgets_ms, class_rtt_budgets_ms

LOG = logging.getLogger("safe_qos")
CLASSES = ("voip", "video", "bulk")
CONTROLLER_FREE_MODES = {"none", "fq_codel_ecn", "cake"}
# These modes carry their own trigger and guard logic and bypass the shared
# budget fallback, FairnessGuard and SafetyShield.
SELF_GUARDED_MODES = {"reactive", "proactive"}
FORECAST_MODES = ("fused_pi_forecast", "fused_pi_forecast_cost", "fused_pi_ewma",
                  "forecast_weight", "proactive")
MODE_MAP = {
    "none": (None, None, False), "static": (None, None, True),
    "reactive": ("threshold", "reactive", True),
    "proactive": (None, "proactive", True),
    "stat_pi": ("stat", "pi", True), "fused_pi": ("fused", "pi", True),
    "fused_pi_forecast": ("fused", "pi", True),
    "fused_pi_forecast_cost": ("fused", "cost_aware_pi", True),
    "fused_pi_ewma": ("fused", "pi", True),
    "fused_qlearning": ("fused", "qlearning", True),
    "fused_qlearning_unshielded": ("fused", "qlearning", True),
    "supervised_rule": ("supervised", "rule_aimd", True),
    "forecast_weight": ("threshold", "forecast_weight", True),
    "fq_codel_ecn": (None, None, False),
    "cake": (None, None, False),
}


def require_root_and_tools():
    if os.name != "posix" or not Path("/proc").exists():
        raise RuntimeError("Mininet/OVS experiment requires Linux; run inside the supplied Linux container.")
    if os.geteuid() != 0:
        raise RuntimeError("Mininet requires root privileges. Use sudo or a privileged container.")
    check = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_environment.py")])
    if check.returncode:
        raise RuntimeError("Environment dependency check failed; see messages above.")


def _controller_reachable(config):
    host = config["runtime"]["controller_ip"]
    port = int(config["runtime"]["controller_port"])
    import socket
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def start_controller(config, log_path, config_path=None):
    """Launch a managed Ryu, avoiding accidental reuse of an unrelated listener."""
    host = config["runtime"]["controller_ip"]
    port = int(config["runtime"]["controller_port"])
    reachable = _controller_reachable(config)
    if reachable and (config["runtime"].get("reuse_existing_controller", False) or
                      not config["runtime"].get("controller_auto_start", True)):
        LOG.info("Using existing Ryu controller at %s:%s", host, port)
        return None, None
    if reachable:
        # A TCP listener alone does not prove that the intended Ryu app is
        # running. Use a fresh port instead of attaching OVS to a stale process.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((host, 0))
            port = probe.getsockname()[1]
        config["runtime"]["controller_port"] = port
        LOG.warning("Configured controller port is occupied; starting managed Ryu on %s:%s", host, port)
    if not config["runtime"].get("controller_auto_start", True):
        raise RuntimeError(f"Ryu is not listening at {host}:{port} and runtime.controller_auto_start is false")
    executable = shutil.which("ryu-manager")
    if executable is None:
        raise RuntimeError("Cannot auto-start Ryu: ryu-manager executable is missing")
    log_file = log_path.open("a", encoding="utf-8")
    environment = os.environ.copy()
    environment["QOS_CONFIG"] = str(Path(config_path).resolve()) if config_path else str(ROOT / "config.yaml")
    process = subprocess.Popen(
        [executable, "--ofp-listen-host", "0.0.0.0", "--ofp-tcp-listen-port", str(port),
         "ryu_app/qos_app.py"],
        cwd=str(ROOT), env=environment, stdout=log_file, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deadline = time.monotonic() + float(config["runtime"].get("controller_start_timeout_seconds", 60))
    while time.monotonic() < deadline:
        if _controller_reachable(config):
            LOG.info("Started Ryu controller (pid %s) at %s:%s", process.pid, host, port)
            return process, log_file
        if process.poll() is not None:
            break
        time.sleep(0.2)
    details = ""
    try:
        log_file.flush()
        details = "".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines(True)[-20:])
    except OSError:
        pass
    _stop_controller(process, log_file)
    raise RuntimeError(
        f"Could not start Ryu at {host}:{port} within "
        f"{config['runtime'].get('controller_start_timeout_seconds', 60)} seconds. "
        f"See {log_path} for controller output.\n{details}"
    )


def _stop_controller(process, log_file):
    """Stop only the Ryu process started by this runner."""
    if process is not None and process.poll() is None:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    if log_file is not None:
        log_file.close()


def csv_writer(path, fields):
    stream = path.open("w", newline="", encoding="utf-8")
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    return stream, writer


def run(mode, scenario, seed, config_path=None, output_root=None, q_table_path=None,
        disable_guards=False, environment_checked=False, controller_ready=False,
        controller_port=None, manage_cleanup=True):
    """Run one seeded Mininet trial and persist samples, decisions and config."""
    if not environment_checked:
        require_root_and_tools()
    from manager.detectors import make_detector
    config = load_config(config_path) if config_path else load_config()
    if controller_port is not None:
        config["runtime"]["controller_port"] = int(controller_port)
    if mode not in MODE_MAP or scenario not in config["scenarios"]:
        raise ValueError(f"Unsupported mode/scenario: {mode}/{scenario}")
    random.seed(seed)
    scenario_cfg = config["scenarios"][scenario]
    duration = int(scenario_cfg["duration"])
    out = (Path(output_root or config["runtime"]["results_dir"]) / mode / scenario / f"run_{seed}").resolve()
    out.mkdir(parents=True, exist_ok=True)
    snapshot = {"config": config, "run": {
        "mode": mode, "scenario": scenario, "seed": seed,
        "guards_enabled": bool(config["guards"]["enabled"] and not disable_guards),
        "q_table": q_table_path}}
    (out / "config.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from mininet.link import TCLink
    from mininet.log import setLogLevel
    from mininet.net import Mininet
    from mininet.node import OVSSwitch, RemoteController
    from topo.research_topo import ResearchTopo, bottleneck_interface
    setLogLevel("warning")
    if manage_cleanup and config["runtime"].get("mn_cleanup", True):
        subprocess.run(["mn", "-c"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    controller_required = mode not in CONTROLLER_FREE_MODES
    switch = partial(OVSSwitch, protocols="OpenFlow13",
                     failMode="secure" if controller_required else "standalone")
    net = Mininet(topo=ResearchTopo(config), switch=switch, link=TCLink,
                  controller=None, autoSetMacs=True, build=False)
    if controller_required:
        net.addController("c0", controller=RemoteController,
                          ip=config["runtime"]["controller_ip"], port=config["runtime"]["controller_port"])
    sample_stream, samples = csv_writer(out / "samples.csv", ["t", "utilization", "voip_rtt_ms", "video_rtt_ms", "bulk_rtt_ms", "delay_voip_ms", "delay_video_ms", "delay_bulk_ms", "bulk_mbps", "voip_mbps", "video_mbps", "iperf_voip_mbps", "iperf_video_mbps", "iperf_bulk_mbps", "voip_loss_pct", "video_loss_pct", "bulk_loss_pct", "backlog_bytes", "drop_rate", "queue_backlog_bytes", "queue_drops", "queue_voip_tx_bytes", "queue_video_tx_bytes", "queue_bulk_tx_bytes", "severity", "ground_truth", "gt_congestion", "gt_violation", "delay_budget_violation", "bulk_active", "sla_rtt_ms", "stale", "queue_stats_received", "jain_index", "delay_protect_active", "forecast_utilization", "forecast_voip_rtt_ms", "forecast_delay_voip_ms", "forecast_delay_video_ms", "forecast_delay_bulk_ms", "reserved_rate_mbps", "reservation_cost_fraction", "controller_cpu_s"])
    decision_stream, decisions = csv_writer(out / "decisions.csv", ["t", "mode", "detector", "engine", "severity", "old_rates", "new_rates", "reason", "rejected", "actuation_latency_s"])
    net_started = False
    controller_process = None
    controller_log = None
    try:
        if controller_required and not controller_ready:
            controller_process, controller_log = start_controller(config, out / "controller.log", config_path)
        net.start(); net_started = True
        if controller_required:
            _configure_switch_controllers(net.switches, config["runtime"]["controller_ip"],
                                           config["runtime"]["controller_port"])
            _wait_for_switch_controllers(net.switches,
                float(config["runtime"].get("controller_start_timeout_seconds", 60)))
        s1 = net.get("s1")
        interface = bottleneck_interface(net)
        port_no = s1.ports[s1.intf(interface)]
        config["runtime"]["bottleneck_port_no"] = int(port_no)
        snapshot["config"] = config
        (out / "config.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        if mode in CONTROLLER_FREE_MODES:
            subprocess.run(["ovs-vsctl", "clear", "Port", interface, "qos"], check=True)
            queue_uuids = {}
        else:
            queue_uuids = setup_qos(interface, config)
        actuator = OVSActuator(interface, queue_uuids, config)
        static_rates = {name: dict(config["qos"]["static_rates"][name]) for name in CLASSES}
        current = {k: dict(v) for k, v in static_rates.items()}
        (out / "queue_uuids.json").write_text(json.dumps(queue_uuids, indent=2), encoding="utf-8")
        from manager.collector import MetricsCollector
        collector = MetricsCollector(net, interface, config, seed, {"name": scenario, "config": scenario_cfg})
        collector.start()
        detector_name, engine_name, use_static = MODE_MAP[mode]
        detector = make_detector(detector_name, config) if detector_name else None
        q_table = None
        if engine_name == "qlearning" and q_table_path:
            from manager.engines import QLearningEngine
            q_table = QLearningEngine.read_q_table(q_table_path)
        elif engine_name == "qlearning":
            LOG.warning("No trained Q table supplied; provide --q-table or use run_experiments.py to train/load one")
        engine = make_engine(engine_name, config, training=False, seed=seed, q_table=q_table) if engine_name else None
        guards_on = bool(config["guards"]["enabled"] and not disable_guards and
                         mode not in SELF_GUARDED_MODES)
        shield = SafetyShield(config, enabled=(guards_on and mode != "fused_qlearning_unshielded"))
        guard = FairnessGuard(config)
        delay_hysteresis = DelayBudgetHysteresis(config)
        if mode == "proactive":
            forecast_config = dict(config)
            forecast_config["forecaster"] = {**config["forecaster"],
                                             **config["engines"]["proactive"]["forecast"]}
            forecast = HoltForecaster(forecast_config)
        elif mode == "fused_pi_ewma":
            forecast = EWMAForecaster(config)
        else:
            forecast = HoltForecaster(config)
        qdisc_applied = False
        if mode in ("fq_codel_ecn", "cake"):
            qdisc_latency = _apply_qdisc(interface, config["network"]["bandwidth_mbps"],
                                         config["network"]["delay_ms"], config["network"]["queue_size"],
                                         kind="cake" if mode == "cake" else "fq_codel")
            decisions.writerow({"t": 0.0, "mode": mode, "detector": "none", "engine": "qdisc",
                "severity": 0, "old_rates": "{}", "new_rates": "{}",
                "reason": f"install {mode} stand-in qdisc", "rejected": False,
                "actuation_latency_s": qdisc_latency})
            qdisc_applied = True
        servers = {c: net.get(f"h_{c}_dst") for c in CLASSES}
        for cls, host in servers.items():
            port = config["network"]["ports"][cls]
            host.cmd(f"iperf3 -s -p {port} -i 1 > {out / ('server_' + cls + '.log')} 2>&1 &")
        # iperf3 permits only one active test per server process. VoIP surge
        # scenarios overlap the background VoIP flow, so give each surge its
        # own listening port on the same destination host.
        voip_surge_port = int(config["network"]["ports"].get(
            "voip_surge", int(config["network"]["ports"]["voip"]) + 1))
        if scenario_cfg.get("voip_calls"):
            servers["voip"].cmd(
                f"iperf3 -s -p {voip_surge_port} -i 1 > {out / 'server_voip_surge.log'} 2>&1 &")
        # The same applies when a video rate step replaces the first video session.
        video_step_port = int(config["network"]["ports"].get(
            "video_step", int(config["network"]["ports"]["video"]) + 1))
        if scenario_cfg.get("video_rate_steps"):
            servers["video"].cmd(
                f"iperf3 -s -p {video_step_port} -i 1 > {out / 'server_video_step.log'} 2>&1 &")
        sources = {c: net.get(f"h_{c}_src") for c in CLASSES}
        ip = config["network"]["server_ips"]
        ports = config["network"]["ports"]
        streams = _scenario_streams(config, scenario_cfg)
        for stream in streams:
            servers[stream["cls"]].cmd(
                f"iperf3 -s -p {stream['port']} -i 1 > {out / ('server_' + stream['name'] + '.log')} 2>&1 &")
        video_steps = scenario_cfg.get("video_rate_steps", [])
        first_video_step = min((int(item[0]) for item in video_steps), default=duration)
        voip_rate = (f"{float(scenario_cfg['voip_rate_mbps'])}M" if "voip_rate_mbps" in scenario_cfg
                     else config["traffic"]["voip_rate"])
        video_rate = (f"{float(scenario_cfg['video_rate_mbps'])}M" if "video_rate_mbps" in scenario_cfg
                      else config["traffic"]["video_rate"])
        sources["voip"].cmd(f"iperf3 -c {ip['voip']} -p {ports['voip']} -u -b {voip_rate} -l {config['traffic']['voip_packet_bytes']} -t {duration+5} -i 1 --get-server-output -J > {out / 'voip.json'} 2>&1 &")
        sources["video"].cmd(f"iperf3 -c {ip['video']} -p {ports['video']} -u -b {video_rate} -l {config['traffic']['video_packet_bytes']} -t {first_video_step} -i 1 --get-server-output -J > {out / 'video.json'} 2>&1 &")
        active_bulk = []
        bulk_sessions = []
        voip_sessions = []
        video_sessions = []
        current_bulk_ramp = None
        started = time.monotonic()
        congestion_start = None
        detected_at = None
        acted_at = None
        reactive_trigger_at = None
        recovery_start = None
        starvation_seconds = 0
        false_alarm_costs = {}
        forecast_alert_at = {}
        alarm_duration = int(scenario_cfg.get("alarm_duration", 0))
        alarm_slots = max(0, duration - alarm_duration + 1)
        alarm_count = min(int(scenario_cfg.get("alarm_count", 0)), alarm_slots)
        alarm_starts = sorted(random.Random(seed).sample(range(alarm_slots), alarm_count)) if alarm_count else []
        for tick in range(duration):
            tick_cpu_start = time.process_time()
            controller_cpu = 0.0
            now_s = time.monotonic() - started
            should_bulk = _bulk_active(scenario, scenario_cfg, tick)
            if scenario_cfg.get("bulk_ramp"):
                desired = next((float(rate) for at, rate in reversed(scenario_cfg["bulk_ramp"])
                                if tick >= int(at)), None)
                if desired is not None and (current_bulk_ramp is None or desired > current_bulk_ramp):
                    increment = desired - (current_bulk_ramp or 0.0)
                    bulk_path = out / f"bulk_{len(bulk_sessions) + 1}.json"
                    active_bulk = _start_bulk(sources["bulk"], ip["bulk"], ports["bulk"], 1,
                                              duration + 5, bulk_path, rate_mbps=increment)
                    bulk_sessions.append((bulk_path, tick))
                    current_bulk_ramp = desired
            elif should_bulk and not active_bulk:
                bulk_path = out / f"bulk_{len(bulk_sessions) + 1}.json"
                active_bulk = _start_bulk(sources["bulk"], ip["bulk"], ports["bulk"],
                                          int(scenario_cfg.get("bulk_flows", config["traffic"]["bulk_flows"])),
                                          duration + 5, bulk_path)
                bulk_sessions.append((bulk_path, tick))
            elif not should_bulk and active_bulk:
                sources["bulk"].cmd("pkill -x iperf3 >/dev/null 2>&1 || true")
                active_bulk = []
            for call_start, call_duration in scenario_cfg.get("voip_calls", []):
                if tick == int(call_start):
                    surge_path = out / f"voip_surge_{tick}.json"
                    sources["voip"].cmd(f"iperf3 -c {ip['voip']} -p {voip_surge_port} -u -b {scenario_cfg['voip_surge_rate_mbps']}M -l {config['traffic']['voip_packet_bytes']} -t {int(call_duration)} -i 1 --get-server-output -J > {surge_path} 2>&1 &")
                    voip_sessions.append((surge_path, tick, int(call_duration)))
            for step_tick, step_rate in video_steps:
                if tick == int(step_tick):
                    step_path = out / f"video_step_{tick}.json"
                    sources["video"].cmd(f"iperf3 -c {ip['video']} -p {video_step_port} -u -b {float(step_rate)}M -l {config['traffic']['video_packet_bytes']} -t {duration-tick+5} -i 1 --get-server-output -J > {step_path} 2>&1 &")
                    video_sessions.append((step_path, tick, duration - tick))
            for stream in streams:
                if tick != stream["start"]:
                    continue
                length = stream["stop"] - stream["start"]
                path = out / stream["file"]
                if stream["cls"] == "bulk":
                    _start_bulk(sources["bulk"], ip["bulk"], stream["port"], stream["flows"],
                                length, path)
                    bulk_sessions.append((path, tick))
                else:
                    sources[stream["cls"]].cmd(
                        f"iperf3 -c {ip[stream['cls']]} -p {stream['port']} -u -b {stream['rate_mbps']}M "
                        f"-l {config['traffic'][stream['cls'] + '_packet_bytes']} -t {length} -i 1 "
                        f"--get-server-output -J > {path} 2>&1 &")
                    (voip_sessions if stream["cls"] == "voip" else video_sessions).append(
                        (path, tick, length))
            for step_tick, delay_ms in scenario_cfg.get("delay_steps", []):
                if tick == int(step_tick):
                    _set_path_delay(interface, int(delay_ms))
                    config["network"]["delay_ms"] = int(delay_ms)
            if scenario == "capacity_step":
                for at, rate in scenario_cfg.get("capacity_steps", []):
                    if tick == at:
                        old_capacity = config["qos"]["link_capacity_bps"]
                        config["qos"]["link_capacity_bps"] = int(rate * 1e6)
                        config["network"]["bandwidth_mbps"] = float(rate)
                        shield.capacity_bps = int(rate * 1e6)
                        _set_bottleneck_capacity(mode, interface, int(rate), queue_uuids)
                        decisions.writerow({"t": now_s, "mode": mode, "detector": detector_name,
                            "engine": engine_name, "severity": 0, "old_rates": json.dumps({"capacity_bps": old_capacity}),
                            "new_rates": json.dumps({"capacity_bps": int(rate * 1e6)}),
                            "reason": "scenario bottleneck capacity step", "rejected": False,
                            "actuation_latency_s": 0.0})
            if scenario == "misclassified" and scenario_cfg["misclass_start"] <= tick < scenario_cfg["misclass_start"] + scenario_cfg["misclass_duration"]:
                sources["bulk"].cmd(f"iperf3 -c {ip['video']} -p {ports['video']} -u -b 3M -t 1 >/dev/null 2>&1 &")
            sample = collector.sample(sim_t=now_s)
            # Preserve raw tc class counters at both ends of each trial. This
            # makes rate mismatches against iperf auditable without relying on
            # OpenFlow queue-stat support from the switch.
            if tick in (0, duration - 1):
                with (out / "tc_class_stats.txt").open("a", encoding="utf-8") as stream:
                    stream.write(f"tick={tick} monotonic_s={sample['monotonic_s']:.6f}\n")
                    stream.write(sample.get("tc_class_text", ""))
                    stream.write("\n")
            sample["bulk_active"] = should_bulk
            if mode in CONTROLLER_FREE_MODES:
                # No per-class HTB backlog exists; queueing happens upstream, so
                # one-way delay is the class probe RTT minus the return-path delay.
                return_delay = float(config["network"]["delay_ms"])
                for cls in CLASSES:
                    rtt = float(sample.get(f"{cls}_rtt_ms", float("nan")))
                    if math.isfinite(rtt):
                        sample["class_delay_ms"][cls] = max(return_delay, rtt - return_delay)
            sample["sla_rtt_ms"] = config["sla"]["voip_rtt_ms"]
            sample["delay_budget_ms"] = class_delay_budgets_ms(config)
            sample["bulk_mbps"] = sample["q_mbps"].get("bulk", 0.0)
            for cls in CLASSES:
                sample[f"{cls}_mbps"] = sample["q_mbps"].get(cls, 0.0)
                sample[f"{cls}_loss_pct"] = sample["probe_loss_pct"].get(cls, 0.0)
                sample[f"queue_{cls}_tx_bytes"] = sample.get("queue_tx_bytes", {}).get(cls, 0)
            sample["jain_index"] = jain_index([sample["q_mbps"].get(c, 0.0) / max(config["sla"]["class_targets_mbps"][c], .001) for c in CLASSES])
            sample["reserved_rate_mbps"] = _reserved_rate_mbps(mode, current)
            sample["reservation_cost_fraction"] = sample["reserved_rate_mbps"] / max(
                float(config["qos"]["link_capacity_bps"]) / 1e6, 1e-9)
            gt_violation = bool(math.isfinite(float(sample.get("voip_rtt_ms", float("nan")))) and
                                float(sample["voip_rtt_ms"]) > config["sla"]["voip_rtt_ms"])
            delay_budget_violation = any(
                float(sample["class_delay_ms"].get(cls, 0.0)) > budget
                for cls, budget in sample["delay_budget_ms"].items())
            if delay_budget_violation and reactive_trigger_at is None:
                reactive_trigger_at = now_s
            gt_congestion = bool(should_bulk and sample.get("utilization", 0.0) >=
                                 float(config["detectors"]["ground_truth"]["congestion_utilization"]))
            if gt_congestion and congestion_start is None:
                congestion_start = now_s
            if scenario == "false_alarms" and not should_bulk and _false_alarm(scenario_cfg, tick, alarm_starts):
                detection = type("Injected", (), {"severity": 2, "congested": True, "reason": "injected-false-alarm"})()
            else:
                detection = detector.update(sample, ground_truth=gt_congestion) if detector else type("Clear", (), {"severity": 0, "congested": False, "reason": "disabled"})()
            prediction = forecast.update(sample)
            forecast_limit = min(float(config["forecaster"]["forecast_mae_limit"]),
                                 float(config["guards"]["safety"]["forecast_mae_limit"]))
            forecast_ok = forecast.ready and prediction.mae <= forecast_limit
            if mode == "proactive":
                # The proactive policy has its own measured-delay fallback and
                # does not gate the forecast on its rolling error.
                forecast_ok = forecast.ready
            fc = prediction if forecast_ok else None
            predicted_delays = fc.class_delay_ms if fc else {}
            delay_protect_active = delay_hysteresis.update(
                sample["class_delay_ms"], predicted_delays, sample["delay_budget_ms"])
            sample["delay_protect_active"] = delay_protect_active
            if mode in FORECAST_MODES:
                for cls, budget in sample["delay_budget_ms"].items():
                    if (predicted_delays.get(cls, 0.0) >=
                            config["fiveqi"]["protect_enter_ratio"] * budget):
                        forecast_alert_at.setdefault(cls, now_s)
            severity = detection.severity
            # Reactive fallback: any adaptive engine must take protective
            # action once a measured class delay exceeds its 5QI budget.
            if engine is not None and delay_budget_violation and mode not in SELF_GUARDED_MODES:
                severity = max(2, severity)
            if mode in ("fused_pi_forecast", "fused_pi_forecast_cost", "fused_pi_ewma") and delay_protect_active and severity < 2:
                severity = max(1, severity)
            rejected = False
            proposed = None
            if mode == "none":
                candidate, reason = current, "no control"
            elif use_static and not engine:
                candidate, reason = static_rates, "static HTB"
            elif engine:
                cpu_start = time.process_time()
                engine_forecast = fc if mode in FORECAST_MODES else None
                candidate, reason = engine.decide(sample, severity, current, forecast=engine_forecast)
                if guards_on:
                    candidate = guard.repair_bulk_ceiling(
                        candidate, config["qos"]["link_capacity_bps"], sample=sample)
                proposed = {name: dict(value) for name, value in candidate.items()}
                controller_cpu = time.process_time() - cpu_start
                rejected = False
                if guards_on:
                    ok, fairness, rejection = guard.evaluate(candidate, sample=sample)
                    rejected = not ok
                    if rejected:
                        candidate, reason = current, "; ".join(rejection)
                candidate, shielded, shield_reasons = shield.filter(candidate, current, static_rates, tick,
                    stale_ticks=sample["stale_ticks"] if sample["stale"] else 0,
                    forecast_mae=prediction.mae if fc else 0.0)
                if shielded:
                    rejected = True; reason = "; ".join(shield_reasons)
            else:
                candidate, reason, rejected = current, "qdisc stand-in; endpoint agnostic", False
                if mode in ("fq_codel_ecn", "cake") and not qdisc_applied:
                    _apply_qdisc(interface, config["network"]["bandwidth_mbps"],
                                 config["network"]["delay_ms"], config["network"]["queue_size"],
                                 kind="cake" if mode == "cake" else "fq_codel")
                    qdisc_applied = True
            if candidate != current and mode not in CONTROLLER_FREE_MODES:
                latency = actuator.apply(candidate)["latency_seconds"]
                if acted_at is None:
                    acted_at = now_s
                decisions.writerow({"t": now_s, "mode": mode, "detector": detector_name,
                    "engine": engine_name, "severity": severity, "old_rates": json.dumps(current),
                    "new_rates": json.dumps(candidate), "reason": reason, "rejected": rejected,
                    "actuation_latency_s": latency})
                current = candidate
            else:
                latency = 0.0
                if rejected:
                    decisions.writerow({"t": now_s, "mode": mode, "detector": detector_name,
                        "engine": engine_name, "severity": severity, "old_rates": json.dumps(current),
                        "new_rates": json.dumps(proposed or candidate), "reason": reason,
                        "rejected": True, "actuation_latency_s": 0.0})
            # Charge the allocation actually left installed during this tick.
            sample["reserved_rate_mbps"] = _reserved_rate_mbps(mode, current)
            sample["reservation_cost_fraction"] = sample["reserved_rate_mbps"] / max(
                float(config["qos"]["link_capacity_bps"]) / 1e6, 1e-9)
            if gt_congestion and detected_at is None and detection.congested:
                detected_at = now_s
            if not gt_congestion and congestion_start is not None and recovery_start is None:
                recovery_start = now_s
            if should_bulk and sample["q_mbps"].get("bulk", 0) < config["guards"]["fairness"]["bulk_floor_bps"] / 1e6:
                starvation_seconds += config["runtime"]["tick_seconds"]
            if scenario == "false_alarms" and detection.congested and not gt_congestion:
                rtt_cost = max(0.0, sample["voip_rtt_ms"] - config["sla"]["voip_rtt_ms"]) / max(config["sla"]["voip_rtt_ms"], 1e-9)
                bulk_target = config["sla"]["class_targets_mbps"]["bulk"]
                bulk_cost = max(0.0, bulk_target - sample["bulk_mbps"]) / max(bulk_target, 1e-9)
                event_start = next((start for start in alarm_starts if start <= tick < start + alarm_duration), tick)
                event = false_alarm_costs.setdefault(event_start, {"t": float(event_start), "costs": [], "rtt": [], "bulk": []})
                event["costs"].append(rtt_cost + bulk_cost)
                event["rtt"].append(_finite_or_none(sample["voip_rtt_ms"]))
                event["bulk"].append(sample["bulk_mbps"])
            controller_cpu = time.process_time() - tick_cpu_start
            samples.writerow({**sample,
                **{f"delay_{cls}_ms": sample["class_delay_ms"].get(cls, 0.0) for cls in CLASSES},
                **{f"forecast_delay_{cls}_ms": prediction.class_delay_ms.get(cls, 0.0) for cls in CLASSES},
                "severity": severity, "ground_truth": int(gt_congestion),
                "gt_congestion": int(gt_congestion), "gt_violation": int(gt_violation),
                "delay_budget_violation": int(delay_budget_violation),
                "forecast_utilization": prediction.utilization, "forecast_voip_rtt_ms": prediction.voip_rtt_ms,
                "controller_cpu_s": controller_cpu})
            time.sleep(max(0, config["runtime"]["tick_seconds"] - (time.monotonic() - started - tick)))
        collector.stop()
        _stop_hosts(net)
        sample_stream.flush(); decision_stream.flush()
        sample_stream.close()
        _apply_iperf_sample_metrics(out / "samples.csv", out, mode, bulk_sessions,
                                    voip_sessions=voip_sessions, video_sessions=video_sessions)
        false_alarm_rows = [{"t": event["t"], "qos_cost": sum(event["costs"]) / len(event["costs"]),
                             "voip_rtt_ms": _mean_optional(event["rtt"]),
                             "bulk_mbps": _mean_optional(event["bulk"])}
                            for event in false_alarm_costs.values() if event["costs"]]
        _write_summary(out, samples_path=out / "samples.csv", decisions_path=out / "decisions.csv",
                       starvation=starvation_seconds, false_alarm_costs=false_alarm_rows,
                       detection_time=(detected_at - congestion_start if detected_at is not None and congestion_start is not None else None),
                       actuation_time=(acted_at - congestion_start if acted_at is not None and congestion_start is not None else None),
                       recovery_time=(recovery_start - congestion_start if recovery_start is not None and congestion_start is not None else None), forecast=forecast, config=config,
                       prediction_lead=(reactive_trigger_at - acted_at
                                        if reactive_trigger_at is not None and acted_at is not None
                                        else None), forecast_alert_at=forecast_alert_at,
                       mode=mode)
    finally:
        try:
            sample_stream.close(); decision_stream.close()
            if net_started:
                _stop_hosts(net); net.stop()
        finally:
            _stop_controller(controller_process, controller_log)
            if manage_cleanup and config["runtime"].get("mn_cleanup", True):
                subprocess.run(["mn", "-c"], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out


def _scenario_streams(config, scenario_cfg):
    """Expand ``scenarios.<name>.streams`` into sessions with their own ports.

    The n-th extra stream of a class listens on that class's base port + n.
    Session files reuse the names the summary already aggregates
    (voip_surge_*, video_step_*, bulk_*).
    """
    ports = config["network"]["ports"]
    counts = {cls: 0 for cls in CLASSES}
    prefixes = {"voip": "voip_surge", "video": "video_step", "bulk": "bulk"}
    expanded = []
    for item in scenario_cfg.get("streams", []):
        cls = item["cls"]
        counts[cls] += 1
        start = int(item["start"])
        stop = int(item.get("stop", scenario_cfg["duration"]))
        # bulk_1.json is the base bulk session; extra bulk sessions follow it.
        suffix = counts[cls] + 1 if cls == "bulk" else start
        expanded.append({"cls": cls, "start": start, "stop": stop,
                         "port": int(ports[cls]) + counts[cls],
                         "rate_mbps": float(item.get("rate_mbps", 0.0)),
                         "flows": int(item.get("flows", 1)),
                         "name": f"{cls}_extra_{counts[cls]}",
                         "file": f"{prefixes[cls]}_{suffix}.json"})
    return expanded


def _offered_mbps(config, scenario_cfg):
    """Time-averaged scripted VoIP/video payload rate (Mbit/s) over the run."""
    duration = float(scenario_cfg["duration"])
    base = {
        "voip": float(scenario_cfg.get("voip_rate_mbps", _rate_mbps(config["traffic"]["voip_rate"]))),
        "video": float(scenario_cfg.get("video_rate_mbps", _rate_mbps(config["traffic"]["video_rate"]))),
    }
    offered = dict(base)
    for stream in _scenario_streams(config, scenario_cfg):
        if stream["cls"] in offered:
            offered[stream["cls"]] += stream["rate_mbps"] * (stream["stop"] - stream["start"]) / duration
    return offered


def _rate_mbps(text):
    """Parse an iperf3 rate such as '640K' or '4M' into Mbit/s."""
    text = str(text).strip()
    scale = {"K": 1e-3, "M": 1.0, "G": 1e3}.get(text[-1:].upper())
    return float(text[:-1]) * scale if scale else float(text) / 1e6


def _bulk_active(name, cfg, tick):
    if name == "repeated_bursts": return any(a <= tick < b for a, b in cfg["bursts"])
    if name == "bulk_ramp": return any(tick >= int(at) for at, _ in cfg.get("bulk_ramp", []))
    if name == "capacity_step": return tick >= cfg["bulk_start"]
    return tick >= cfg.get("bulk_start", 15) and tick < cfg.get("duration", 45)


def _false_alarm(cfg, tick, starts):
    duration = int(cfg.get("alarm_duration", 1))
    return any(start <= tick < start + duration for start in starts)


def _start_bulk(host, ip, port, flows, duration, output_path, rate_mbps=None):
    rate_args = f"-u -b {float(rate_mbps)}M" if rate_mbps is not None else ""
    host.cmd(f"iperf3 -c {ip} -p {port} -P {flows} {rate_args} -t {duration} -i 1 --get-server-output -J > {output_path} 2>&1 &")
    return ["iperf3"]


def _stop_hosts(net):
    for host in net.hosts:
        host.cmd("pkill -x iperf3 >/dev/null 2>&1 || true")


def _configure_switch_controllers(switches, host, port):
    """Apply the exact OpenFlow version and out-of-band controller target to each bridge."""
    target = f"tcp:{host}:{int(port)}"
    for switch in switches:
        subprocess.run(["ovs-vsctl", "set", "Bridge", switch.name,
                        "protocols=OpenFlow13"], check=True)
        subprocess.run(["ovs-vsctl", "set-controller", switch.name, target], check=True)
        controller_ids = subprocess.check_output(
            ["ovs-vsctl", "get", "Bridge", switch.name, "controller"], text=True).strip()
        controller_ids = controller_ids.strip("[]").replace('"', "")
        for controller_id in (value.strip() for value in controller_ids.split(",")):
            if controller_id:
                subprocess.run(["ovs-vsctl", "set", "Controller", controller_id,
                                "connection_mode=out-of-band"], check=True)


def _wait_for_switch_controllers(switches, timeout):
    """Fail before collecting metrics if any controller-backed switch is disconnected."""
    deadline = time.monotonic() + timeout
    disconnected = [switch.name for switch in switches]
    while time.monotonic() < deadline:
        disconnected = []
        for switch in switches:
            try:
                controller_ids = subprocess.check_output(
                    ["ovs-vsctl", "get", "Bridge", switch.name, "controller"],
                    text=True, stderr=subprocess.DEVNULL, timeout=2).strip()
                controller_ids = controller_ids.strip("[]").replace('"', "")
                ids = [value.strip() for value in controller_ids.split(",") if value.strip()]
                connected = any(subprocess.check_output(
                    ["ovs-vsctl", "get", "Controller", controller_id, "is_connected"],
                    text=True, stderr=subprocess.DEVNULL, timeout=2).strip() == "true"
                    for controller_id in ids)
            except (OSError, subprocess.SubprocessError):
                connected = False
            if not connected:
                disconnected.append(switch.name)
        if not disconnected:
            return
        time.sleep(0.25)
    raise RuntimeError(
        "OpenFlow controller did not connect to switch(es): " + ", ".join(disconnected) +
        ". Verify the Ryu listener and OpenFlow 1.3 compatibility; no experiment data was collected.")


def _reserved_rate_mbps(mode, rates):
    """Sum configured class guarantees; classless baselines reserve none."""
    if mode in CONTROLLER_FREE_MODES:
        return 0.0
    return sum(float(rates.get(cls, {}).get("min_bps", 0.0))
               for cls in CLASSES) / 1e6


def _get_qos_uuid(interface):
    return subprocess.check_output(["ovs-vsctl", "get", "Port", interface, "qos"], text=True).strip().strip('"')


def _set_bottleneck_capacity(mode, interface, rate_mbps, queue_uuids):
    """Change OVS HTB capacity when present; directly shape baseline qdiscs otherwise."""
    if queue_uuids:
        # direct tc HTB setup from actuator.py: root ceiling is 1:fffe
        rate = f"{rate_mbps}mbit"
        subprocess.run(["tc", "class", "change", "dev", interface,
                        "parent", "1:0", "classid", "1:fffe",
                        "htb", "rate", rate, "ceil", rate], check=True)
        return

    rate = f"{rate_mbps}mbit"
    if mode == "cake":
        subprocess.run(["tc", "qdisc", "change", "dev", interface,
                        "root", "handle", "1:", "cake", "bandwidth", rate], check=True)
        return
    if mode == "fq_codel_ecn":
        # HTB supplies the capacity ceiling; FQ-CoDel remains its class leaf.
        subprocess.run(["tc", "class", "change", "dev", interface,
                        "parent", "1:", "classid", "1:1", "htb",
                        "rate", rate, "ceil", rate], check=True)
        return

    # The no-control baseline has no QoS row. Preserve Mininet's HTB setup if
    # it is still present; fall back to an explicit token bucket if not.
    result = subprocess.run(["tc", "class", "change", "dev", interface, "classid", "5:1",
                             "htb", "rate", rate, "ceil", rate],
                            capture_output=True, text=True)
    if result.returncode:
        subprocess.run(["tc", "qdisc", "replace", "dev", interface, "root",
                        "handle", "10:", "tbf", "rate", rate, "burst", "32kb",
                        "latency", "50ms"], check=True)


def _apply_qdisc(interface, bandwidth_mbps, delay_ms, queue_size=100, kind="fq_codel"):
    """Install the requested AQM with valid Linux qdisc parentage.

    Netem is classless, so another qdisc cannot be attached below it. Keep
    FQ-CoDel directly below an HTB class; Mininet's peer-side TCLink supplies
    the configured propagation delay. CAKE supplies its own bandwidth shaper.
    """
    cap = f"{float(bandwidth_mbps):g}mbit"
    if kind not in ("fq_codel", "cake"):
        raise ValueError(f"unsupported qdisc kind {kind!r}")
    if kind == "cake":
        commands = [["tc", "qdisc", "replace", "dev", interface, "root",
                     "handle", "1:", "cake", "bandwidth", cap,
                     "rtt", f"{max(1, int(delay_ms) * 2)}ms"]]
    else:
        commands = [
            ["tc", "qdisc", "replace", "dev", interface, "root", "handle", "1:", "htb", "default", "1"],
            ["tc", "class", "replace", "dev", interface, "parent", "1:", "classid", "1:1", "htb", "rate", cap, "ceil", cap],
            ["tc", "qdisc", "replace", "dev", interface, "parent", "1:1", "handle", "20:", "fq_codel", "ecn", "limit", str(int(queue_size))],
        ]
    started = time.monotonic()
    for cmd in commands:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode:
            detail = (result.stderr or result.stdout or "no details from tc").strip()
            if kind == "cake" and ("unknown" in detail.lower() or "not found" in detail.lower()):
                raise RuntimeError(
                    "The host kernel does not provide the CAKE qdisc. Load/install "
                    "the matching sch_cake module, or omit mode 'cake'.\n" + detail)
            raise RuntimeError(f"Could not install shaped {kind} qdisc: {' '.join(cmd)}\n{detail}")
    return time.monotonic() - started


def _set_path_delay(interface, delay_ms):
    """Change existing netem leaf delays without replacing link shaping."""
    result = subprocess.run(["tc", "qdisc", "show", "dev", interface],
                            check=True, capture_output=True, text=True)
    # tc prints class parents as e.g. "5:1" or "5:". Keep the complete
    # handle; dropping the minor component makes `tc qdisc change` target a
    # parent that does not exist.
    netem = re.findall(
        r"qdisc netem ([0-9a-fA-F]+:) parent ([0-9a-fA-F]+:[0-9a-fA-F]*)",
        result.stdout)
    if not netem:
        # The AQM baseline owns s1's root qdisc. TCLink's peer endpoint keeps
        # the independent netem root, so update that direction for delay-step
        # scenarios instead of trying to nest netem under a classless AQM.
        peer_interface = re.sub(r"^s1-", "s2-", interface)
        peer = subprocess.run(["tc", "qdisc", "show", "dev", peer_interface],
                              capture_output=True, text=True)
        peer_netem = re.findall(
            r"qdisc netem ([0-9a-fA-F]+:) parent ([0-9a-fA-F]+:[0-9a-fA-F]*)",
            peer.stdout)
        if peer_netem:
            for handle, parent in peer_netem:
                subprocess.run(["tc", "qdisc", "change", "dev", peer_interface,
                                "parent", parent, "handle", handle, "netem",
                                "delay", f"{int(delay_ms)}ms"], check=True)
            return
        root = re.search(r"qdisc netem ([0-9a-fA-F]+): root", peer.stdout)
        if root:
            subprocess.run(["tc", "qdisc", "change", "dev", peer_interface,
                            "root", "handle", root.group(1), "netem",
                            "delay", f"{int(delay_ms)}ms"], check=True)
            return
        raise RuntimeError(f"No netem qdisc found on {interface} or {peer_interface}; cannot apply delay step")
    for handle, parent in netem:
        subprocess.run(["tc", "qdisc", "change", "dev", interface, "parent", parent,
                        "handle", handle, "netem", "delay", f"{int(delay_ms)}ms"], check=True)


def _write_summary(out, samples_path, decisions_path, starvation, false_alarm_costs,
                   detection_time, actuation_time, recovery_time, forecast, config,
                   prediction_lead, mode, forecast_alert_at=None):
    rows = list(csv.DictReader(samples_path.open(encoding="utf-8")))
    numeric = lambda key: [float(r[key]) for r in rows if r.get(key) not in ("", "nan", "NaN")]
    warmup = float(config["experiment"].get("warmup_seconds", 10))
    measured_rows = [r for r in rows if float(r.get("t") or 0.0) >= warmup]
    decision_rows = list(csv.DictReader(decisions_path.open(encoding="utf-8")))
    bulk_floor_mbps = float(config["guards"]["fairness"]["bulk_floor_bps"]) / 1e6
    starvation_ticks = sum(
        str(row.get("bulk_active", "")).lower() in ("true", "1") and
        float(row.get("bulk_mbps") or 0.0) < bulk_floor_mbps
        for row in rows)
    starvation = starvation_ticks * float(config["runtime"]["tick_seconds"])
    acted = [r for r in decision_rows
             if str(r.get("rejected", "")).lower() != "true"
             and r.get("old_rates") != r.get("new_rates")
             and r.get("reason") != "scenario bottleneck capacity step"]
    rejected_count = sum(str(r.get("rejected", "")).lower() == "true" for r in decision_rows)
    delay_budgets = class_delay_budgets_ms(config)
    rtt_budgets = class_rtt_budgets_ms(config)
    summary = {"samples": len(rows), "bulk_starvation_s": starvation,
               "detection_latency_s": detection_time, "time_to_act_s": actuation_time,
               "time_to_recover_s": recovery_time, "false_alarm_events": false_alarm_costs,
               "false_alarm_qos_cost_mean": (sum(event["qos_cost"] for event in false_alarm_costs) / len(false_alarm_costs) if false_alarm_costs else 0.0),
               "forecast_prediction_lead_s": None,
               "prediction_lead_s": prediction_lead, "forecast_mae": forecast.mae,
               "5qi_link_share": float(config["fiveqi"]["link_share"]),
               "5qi_pdb_ms": config["fiveqi"]["pdb_ms"],
               "class_delay_budget_one_way_ms": delay_budgets,
               "class_delay_budget_rtt_ms": rtt_budgets,
               "sla_warmup_seconds": warmup,
               "policy_changes": len(acted), "decisions_logged": len(decision_rows),
               "rejection_rate": rejected_count / max(1, len(decision_rows))}
    # Compare alerts and measured violations for the same traffic class. A
    # single global first-alert timestamp could otherwise pair, for example,
    # a bulk forecast with a later VoIP violation and overstate forecast lead.
    lead_by_class = {}
    if isinstance(forecast_alert_at, dict):
        for cls in CLASSES:
            violations = [float(row.get("t") or 0.0) for row in rows
                          if float(row.get(f"delay_{cls}_ms") or 0.0) > delay_budgets[cls]]
            if cls in forecast_alert_at and violations:
                lead_by_class[cls] = min(violations) - float(forecast_alert_at[cls])
    # A flap is a rate change that restores the previous rates within 5 s.
    flap_window = 5.0
    summary["policy_flaps"] = sum(
        1 for previous, change in zip(acted, acted[1:])
        if change.get("new_rates") == previous.get("old_rates") and
        float(change["t"]) - float(previous["t"]) <= flap_window)
    # Lead time: first VoIP/video budget breach minus the first protect action.
    breaches = [float(row.get("t") or 0.0) for row in rows
                if any(float(row.get(f"delay_{cls}_ms") or 0.0) > delay_budgets[cls]
                       for cls in ("voip", "video"))]
    first_act = float(acted[0]["t"]) if acted else None
    summary["protect_lead_s"] = (min(breaches) - first_act
                                 if breaches and first_act is not None else None)
    protected_violations = [
        any(float(r.get(f"delay_{cls}_ms") or 0.0) > delay_budgets[cls] for cls in ("voip", "video"))
        for r in measured_rows]
    summary["protected_sla_violation_ratio"] = (
        sum(protected_violations) / len(protected_violations) if protected_violations else None)
    summary["forecast_prediction_lead_by_class_s"] = lead_by_class
    valid_leads = [value for value in lead_by_class.values() if value >= 0.0]
    summary["forecast_prediction_lead_s"] = (
        sum(valid_leads) / len(valid_leads) if valid_leads else None)
    # Every mode that installs OVS queues depends on the Ryu queue counters,
    # including detector-only and forecast-weighted policies.
    queue_modes = set(MODE_MAP) - CONTROLLER_FREE_MODES
    queue_reports = sum(str(row.get("queue_stats_received", "")).lower() == "true"
                        for row in rows)
    summary["queue_stats_samples"] = queue_reports
    summary["queue_stats_coverage"] = queue_reports / max(1, len(rows))
    queue_counter_totals = {
        cls: max((float(row.get(f"queue_{cls}_tx_bytes") or 0) for row in rows), default=0.0)
        for cls in CLASSES
    }
    summary["queue_counter_totals_bytes"] = queue_counter_totals
    summary["queue_counters_valid"] = all(value > 0 for value in queue_counter_totals.values())
    video_queue_rates = numeric("video_mbps")
    summary["queue_video_rate_mbps_mean"] = (
        sum(video_queue_rates) / len(video_queue_rates) if video_queue_rates else 0.0)
    scenario_cfg = config["scenarios"].get(out.parent.name, {})
    # Session paths are recorded by the runner; infer them from stable file names.
    voip_paths = [out / "voip.json"] + sorted(out.glob("voip_surge_*.json"))
    video_paths = [out / "video.json"] + sorted(out.glob("video_step_*.json"))
    stream_classes = {stream["cls"] for stream in _scenario_streams(config, scenario_cfg)}
    if scenario_cfg.get("voip_calls") or "voip" in stream_classes:
        voip_metric = _iperf_sessions_summary(voip_paths, float(scenario_cfg["duration"]))
    else:
        voip_metric = _iperf_summary(out / "voip.json")
    if scenario_cfg.get("video_rate_steps") or "video" in stream_classes:
        video_metric = _iperf_sessions_summary(video_paths, float(scenario_cfg["duration"]))
    else:
        video_metric = _iperf_summary(out / "video.json")
    iperf_metrics = {"voip": voip_metric, "video": video_metric}
    iperf_metrics["bulk"] = _iperf_bulk_summary(out)
    summary["iperf_metrics"] = iperf_metrics
    scenario_config = config["scenarios"].get(out.parent.name, {})
    capacity_mbps = max([float(config["network"]["bandwidth_mbps"])] +
                        [float(rate) for _, rate in scenario_config.get("capacity_steps", [])])
    bulk_metric = iperf_metrics["bulk"]
    bulk_within_capacity = (bulk_metric is not None and bulk_metric["valid"] and
                            bulk_metric["throughput_mbps"] <= 1.05 * capacity_mbps)
    summary["link_capacity_mbps"] = capacity_mbps
    # Report-style throughput: total bytes received / scenario duration, so
    # concurrent bulk sessions add up instead of being time-averaged.
    duration_s = max(float(scenario_cfg.get("duration", 1)), 1e-9)
    bulk_bytes = sum(int((_iperf_summary(path) or {}).get("bytes", 0))
                     for path in sorted(out.glob("bulk_*.json")))
    summary["bulk_goodput_mbps"] = bulk_bytes * 8 / duration_s / 1e6
    # Jain index of delivered / scripted offered load (offline ground truth only).
    offered = _offered_mbps(config, scenario_cfg)
    satisfaction = []
    for cls in ("voip", "video"):
        got = (iperf_metrics.get(cls) or {}).get("throughput_mbps")
        if got is not None and offered[cls] > 0:
            satisfaction.append(min(1.0, float(got) / offered[cls]))
    satisfaction.append(min(1.0, summary["bulk_goodput_mbps"] / (capacity_mbps / 3.0)))
    summary["jain_offered"] = jain_index(satisfaction) if len(satisfaction) == 3 else None
    summary["bulk_throughput_within_capacity"] = bulk_within_capacity
    summary["throughput_valid"] = all(
        metric is not None and metric["valid"] for metric in iperf_metrics.values()) and bulk_within_capacity
    video_iperf = iperf_metrics["video"]
    video_ratio = (summary["queue_video_rate_mbps_mean"] / video_iperf["throughput_mbps"]
                   if video_iperf and video_iperf["throughput_mbps"] > 0 else 0.0)
    summary["queue_video_rate_iperf_ratio"] = video_ratio
    summary["queue_video_rate_matches_iperf"] = (
        0.5 <= video_ratio <= 1.5 if video_iperf and video_iperf["throughput_mbps"] > 0
        else False)
    rtt_coverage = sum(row.get("voip_rtt_ms") not in (None, "", "nan", "NaN")
                       for row in rows) / max(1, len(rows))
    summary["telemetry_valid"] = (
        summary["queue_stats_coverage"] >= 0.8 and summary["queue_counters_valid"] and
        summary["queue_video_rate_matches_iperf"]
        if mode in queue_modes else rtt_coverage >= 0.8
    ) and summary["throughput_valid"]
    for cls in CLASSES:
        class_delays = [float(r[f"delay_{cls}_ms"]) for r in measured_rows
                        if r.get(f"delay_{cls}_ms") not in (None, "", "nan", "NaN")]
        budget = delay_budgets[cls]
        summary[f"delay_mean_ms_{cls}"] = (
            sum(class_delays) / len(class_delays) if class_delays else None)
        ordered_delays = sorted(class_delays)
        summary[f"delay_p95_ms_{cls}"] = (
            ordered_delays[int(.95 * (len(ordered_delays) - 1))] if ordered_delays else None)
        summary[f"delay_sla_violation_ratio_{cls}"] = (
            sum(value > budget for value in class_delays) / len(class_delays)
            if class_delays else None)
        measured_rtts = [float(r[f"{cls}_rtt_ms"]) for r in measured_rows
                         if r.get(f"{cls}_rtt_ms") not in (None, "", "nan", "NaN")]
        rtt_budget = rtt_budgets[cls]
        summary[f"rtt_sla_violation_ratio_{cls}"] = (
            sum(value > rtt_budget for value in measured_rtts) / len(measured_rtts)
            if measured_rtts else None)
        vals = numeric(f"{cls}_rtt_ms")
        ordered = sorted(vals)
        summary[f"{cls}_rtt_mean_ms"] = sum(vals) / len(vals) if vals else None
        summary[f"{cls}_rtt_p95_ms"] = ordered[int(.95 * (len(ordered)-1))] if ordered else None
        summary[f"{cls}_rtt_p99_ms"] = ordered[int(.99 * (len(ordered)-1))] if ordered else None
        losses = numeric(f"{cls}_loss_pct")
        summary[f"{cls}_loss_pct_mean"] = sum(losses) / len(losses) if losses else None
        throughputs = numeric(f"{cls}_mbps")
        iperf_metric = iperf_metrics[cls]
        if iperf_metric is not None:
            # Prefer iperf's receiver-side result where available. Retain this
            # run-level application rate separately from the per-tick OVS queue
            # rates used by the controller and time-series plots.
            summary[f"{cls}_throughput_mbps_mean"] = iperf_metric["throughput_mbps"]
            summary[f"{cls}_throughput_source"] = iperf_metric["source"]
            summary[f"{cls}_iperf_loss_pct"] = iperf_metric["loss_pct"]
        else:
            summary[f"{cls}_throughput_mbps_mean"] = sum(throughputs) / len(throughputs) if throughputs else None
            summary[f"{cls}_throughput_source"] = "ovs-queue-counters" if throughputs else None
        jitters = [abs(b-a) for a, b in zip(vals, vals[1:])]
        summary[f"{cls}_jitter_ms_mean"] = sum(jitters) / len(jitters) if jitters else None
    voip_vals = numeric("voip_rtt_ms")
    summary["voip_sla_violation_ratio"] = (sum(v > config["sla"]["voip_rtt_ms"] for v in voip_vals) / len(voip_vals)) if voip_vals else None
    video_vals = numeric("video_mbps")
    summary["video_sla_violation_ratio"] = (sum(v < config["sla"]["video_min_mbps"] for v in video_vals) / len(video_vals)) if video_vals else None
    clear_count = sum(not int(float(row.get("gt_congestion") or 0)) for row in rows)
    congested_count = len(rows) - clear_count
    summary["detector_false_positive_rate"] = sum(float(r["severity"]) >= 2 and not int(float(r.get("gt_congestion") or 0)) for r in rows) / max(1, clear_count)
    summary["detector_missed_detection_rate"] = sum(int(float(r.get("gt_congestion") or 0)) and float(r["severity"]) < 2 for r in rows) / max(1, congested_count)
    summary["gt_violation_fraction"] = sum(int(float(r.get("gt_violation") or 0)) for r in rows) / max(1, len(rows))
    delay_violations = [int(float(r.get("delay_budget_violation") or 0))
                        for r in measured_rows]
    summary["sla_violation_ratio_after_warmup"] = (
        sum(delay_violations) / len(delay_violations) if delay_violations else None)
    jains = numeric("jain_index")
    summary["jain_index_mean"] = sum(jains) / len(jains) if jains else None
    cpus = numeric("controller_cpu_s")
    summary["controller_cpu_s_per_tick"] = sum(cpus) / len(cpus) if cpus else None
    reserved = numeric("reserved_rate_mbps")
    summary["reserved_rate_mbps_mean"] = sum(reserved) / len(reserved) if reserved else 0.0
    reservation_fraction = numeric("reservation_cost_fraction")
    summary["reservation_cost_fraction_mean"] = (
        sum(reservation_fraction) / len(reservation_fraction)
        if reservation_fraction else 0.0)
    budget_per_10 = max(float(config["cost"].get("actuation_budget_per_10ticks", 1)), 1e-9)
    summary["actuation_cost_fraction"] = min(
        1.0, len(acted) / max(len(rows) / 10.0 * budget_per_10, 1.0))
    summary["compute_cost_fraction"] = min(
        1.0, (summary["controller_cpu_s_per_tick"] or 0.0) /
        max(float(config["runtime"]["tick_seconds"]), 1e-9))
    cost_weights = config["cost"]["weights"]
    summary["operating_cost_index"] = (
        float(cost_weights["reservation"]) * summary["reservation_cost_fraction_mean"] +
        float(cost_weights["actuation"]) * summary["actuation_cost_fraction"] +
        float(cost_weights["compute"]) * summary["compute_cost_fraction"])
    latencies = [float(r["actuation_latency_s"]) for r in decision_rows if r.get("actuation_latency_s")]
    summary["actuation_latency_mean_s"] = sum(latencies) / len(latencies) if latencies else None
    if numeric("voip_rtt_ms"):
        summary["voip_mos_estimate"] = _mos(sum(numeric("voip_rtt_ms")) / len(numeric("voip_rtt_ms")))
    video = numeric("video_mbps")
    target = config["sla"]["class_targets_mbps"]["video"]
    summary["video_stability_fraction"] = sum(v >= .9 * target for v in video) / max(1, len(video))
    summary["video_throughput_cv"] = _cv(video)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def _apply_iperf_sample_metrics(samples_path, out, mode, bulk_sessions,
                               voip_sessions=(), video_sessions=()):
    """Keep iperf's measured per-second rates for baselines without OVS queues."""
    with samples_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    run_config = json.loads((out / "config.json").read_text(encoding="utf-8"))["config"]
    scenario_name = out.parent.name
    capacity_steps = run_config["scenarios"].get(scenario_name, {}).get("capacity_steps", [])

    series = {
        "voip": [(_iperf_intervals(out / "voip.json"), 0.0)] +
                [(_iperf_intervals(path), float(offset)) for path, offset, _ in voip_sessions],
        "video": [(_iperf_intervals(out / "video.json"), 0.0)] +
                 [(_iperf_intervals(path), float(offset)) for path, offset, _ in video_sessions],
    }
    bulk_series = [(_iperf_intervals(path), float(offset))
                   for path, offset in bulk_sessions]
    for row in rows:
        t = float(row["t"])
        for cls in ("voip", "video"):
            rate = sum(_rate_at(intervals, t - offset) for intervals, offset in series[cls])
            row[f"iperf_{cls}_mbps"] = rate
            if mode in CONTROLLER_FREE_MODES:
                row[f"{cls}_mbps"] = rate
        bulk_rate = 0.0
        for intervals, offset in bulk_series:
            bulk_rate += _rate_at(intervals, t - offset)
        row["iperf_bulk_mbps"] = bulk_rate
        if mode in CONTROLLER_FREE_MODES:
            row["bulk_mbps"] = bulk_rate
            capacity = float(run_config["network"]["bandwidth_mbps"])
            for step_time, step_capacity in capacity_steps:
                if t >= float(step_time):
                    capacity = float(step_capacity)
            capacity = max(capacity, 1e-9)
            used = float(row["voip_mbps"]) + float(row["video_mbps"]) + bulk_rate
            row["utilization"] = min(1.5, used / capacity)
            targets = run_config["sla"]["class_targets_mbps"]
            normalized = [float(row[f"{cls}_mbps"]) / max(float(targets[cls]), .001)
                          for cls in CLASSES]
            row["jain_index"] = jain_index(normalized)
        violation = math.isfinite(float(row.get("voip_rtt_ms", "nan"))) and float(row["voip_rtt_ms"]) > float(run_config["sla"]["voip_rtt_ms"])
        saturated = float(row.get("utilization", 0.0)) >= float(run_config["detectors"]["ground_truth"]["congestion_utilization"])
        congestion = str(row.get("bulk_active", "0")).lower() in ("1", "true") and saturated
        row["ground_truth"] = int(congestion)
        row["gt_congestion"] = int(congestion)
        row["gt_violation"] = int(violation)

    with samples_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _iperf_sessions_summary(paths, wall_seconds):
    """Aggregate concurrent/stepped sessions by bytes delivered over wall time."""
    metrics = [_iperf_summary(Path(path)) for path in paths]
    if not metrics or any(metric is None or not metric["valid"] for metric in metrics):
        return None
    seconds = max(float(wall_seconds), 1e-9)
    total_bytes = sum(int(metric.get("bytes", 0)) for metric in metrics)
    losses = [metric["loss_pct"] for metric in metrics if metric.get("loss_pct") is not None]
    return {"valid": True, "throughput_mbps": total_bytes * 8 / seconds / 1e6,
            "seconds": seconds, "bytes": total_bytes,
            "loss_pct": sum(losses) / len(losses) if losses else None,
            "source": "+".join(sorted({metric["source"] for metric in metrics}))}


def _read_iperf_json(path):
    """Parse iperf3 -J output, skipping warnings it prints before the JSON."""
    text = Path(path).read_text(encoding="utf-8")
    return json.loads(text[text.index("{"):] if "{" in text else text)


def _iperf_intervals(path):
    try:
        result = _read_iperf_json(path)
    except (OSError, ValueError, TypeError):
        return []
    candidates = []
    server_output = result.get("server_output_json")
    if isinstance(server_output, str):
        try:
            server_output = json.loads(server_output)
        except ValueError:
            server_output = None
    if isinstance(server_output, dict):
        candidates.append(server_output)
    candidates.append(result)
    for candidate in candidates:
        intervals = candidate.get("intervals") or []
        rates = []
        for interval in intervals:
            records = [interval.get(key) for key in ("sum_received", "sum", "sum_sent")]
            records = [record for record in records if isinstance(record, dict)]
            if not records:
                streams = interval.get("streams") or []
                records = [streams[0]] if streams else []
            rate_record = None
            for candidate_record in records:
                try:
                    candidate_rate = float(candidate_record["bits_per_second"])
                except (KeyError, TypeError, ValueError):
                    continue
                if candidate_rate > 0:
                    rate_record = candidate_record
                    break
            if rate_record is None and records:
                rate_record = records[0]
            if rate_record is None:
                continue
            try:
                start = float(rate_record.get("start", interval.get("start")))
                end = float(rate_record.get("end", interval.get("end")))
                rate = float(rate_record["bits_per_second"]) / 1e6
            except (KeyError, TypeError, ValueError):
                continue
            if end > start and math.isfinite(rate) and rate >= 0:
                rates.append((start, end, rate))
        if rates:
            return rates
    return []


def _rate_at(intervals, t):
    for start, end, rate in intervals:
        if start <= t < end:
            return rate
    return 0.0


def _iperf_bulk_summary(out):
    sessions = sorted(out.glob("bulk_*.json"))
    if not sessions and (out / "bulk.json").exists():
        sessions = [out / "bulk.json"]
    metrics = [_iperf_summary(path) for path in sessions]
    metrics = [metric for metric in metrics if metric is not None and metric["valid"]]
    if not metrics:
        return None
    seconds = sum(metric["seconds"] for metric in metrics)
    bps = sum(metric["throughput_mbps"] * metric["seconds"] for metric in metrics) / max(seconds, 1e-9)
    byte_count = sum(metric["bytes"] for metric in metrics)
    losses = [metric["loss_pct"] for metric in metrics if metric["loss_pct"] is not None]
    return {"valid": True, "throughput_mbps": bps, "seconds": seconds,
            "bytes": byte_count, "loss_pct": sum(losses) / len(losses) if losses else None,
            "source": "+".join(sorted(set(metric["source"] for metric in metrics)))}


def _iperf_summary(path):
    """Read receiver-side iperf3 goodput, falling back to client JSON if needed."""
    try:
        result = _read_iperf_json(path)
    except (OSError, ValueError, TypeError):
        return None

    candidates = []
    server_output = result.get("server_output_json")
    if isinstance(server_output, str):
        try:
            server_output = json.loads(server_output)
        except ValueError:
            server_output = None
    if isinstance(server_output, dict):
        candidates.append(server_output)
    candidates.append(result)

    records = []
    for candidate_index, candidate in enumerate(candidates):
        end = candidate.get("end") or {}
        for record_name in ("sum_received", "sum", "sum_sent"):
            record = end.get(record_name)
            if not isinstance(record, dict):
                continue
            try:
                bps = float(record["bits_per_second"])
                seconds = float(record.get("seconds", 0.0))
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(bps) and math.isfinite(seconds) and seconds > 0 and bps >= 0:
                loss = record.get("lost_percent")
                try:
                    loss = float(loss) if loss is not None else None
                except (TypeError, ValueError):
                    loss = None
                source = "iperf3-server-json" if candidate_index == 0 else "iperf3-client"
                if record_name == "sum_sent":
                    source += "-sender"
                records.append({"valid": True, "throughput_mbps": bps / 1e6,
                                "seconds": seconds, "bytes": int(record.get("bytes", 0)),
                                "loss_pct": loss, "source": source,
                                "record": record_name})
    # Some iperf3 builds include an empty sum_received record in client JSON
    # while still reporting sent bytes. Prefer positive receiver/client rates
    # before accepting an all-zero record.
    for metric in records:
        if metric["throughput_mbps"] > 0:
            return metric
    if records:
        return records[0]
    return None


def _cv(values):
    if not values: return None
    mean = sum(values) / len(values)
    return (sum((v-mean)**2 for v in values) / len(values)) ** .5 / mean if mean else None


def _finite_or_none(value):
    return float(value) if math.isfinite(float(value)) else None


def _mean_optional(values):
    valid = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return sum(valid) / len(valid) if valid else None


def _mos(rtt):
    # Simplified E-model estimate; it is not a subjective listening test.
    id_ = min(100.0, max(0.0, .024 * rtt + .11 * max(0.0, rtt - 177.3)))
    ie_eff = 0.0
    r = max(0.0, min(100.0, 93.2 - id_ - ie_eff))
    return 1 + .035*r + 7e-6*r*(r-60)*(100-r) if 0 < r < 100 else (4.5 if r >= 100 else 1.0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=MODE_MAP, default="fused_pi_forecast")
    parser.add_argument("--scenario", default="standard")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--config")
    parser.add_argument("--output")
    parser.add_argument("--q-table", help="trained JSON Q table used by qlearning evaluation modes")
    parser.add_argument("--disable-guards", action="store_true", help="ablation: bypass FairnessGuard and SafetyShield")
    args = parser.parse_args()
    print(run(args.mode, args.scenario, args.seed, args.config, args.output, args.q_table, args.disable_guards))


if __name__ == "__main__":
    main()
