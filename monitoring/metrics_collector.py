"""Stream C: live metrics sampler.

Runs inside the scenario (needs Mininet host objects) and every
SAMPLE_INTERVAL_S appends one row to results/<run>/samples.csv:

    t, voip_rtt_ms, video_rtt_ms, bulk_rtt_ms, q0_tx_bytes, q1_tx_bytes, q2_tx_bytes

Each sender runs one long-lived `ping` whose output is read by its own
thread; the sampler records the most recent RTT seen. Per-queue byte
counters come from `ovs-ofctl queue-stats` on the bottleneck port and are
differenced by analyze.py to get per-class bandwidth.

Node.cmd() is deliberately not used here: it shares one shell pipe per node
with the main thread (which starts the iperf3 generators) and asserts when
two threads talk to the same node.
"""
import csv
import os
import re
import socket
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common import config as cfg

RTT_RE = re.compile(r"time=([\d.]+)\s*ms")
# OF1.3 prints "queue 0: bytes=...", OF1.0 "queue 0: tx_bytes=..."
QSTAT_RE = re.compile(r"queue\s+(\d+):\s*(?:tx_)?bytes=(\d+)")
QERR_RE = re.compile(r"queue\s+(\d+):[^\n]*?(?:tx_)?errors=(\d+)")


class _PingReader(threading.Thread):
    """Continuous ping from one host; exposes the latest RTT."""

    def __init__(self, host, target, interval):
        super().__init__(daemon=True)
        self.latest = float("nan")
        self.proc = host.popen(
            ["ping", "-n", "-i", str(interval), target],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            universal_newlines=True,
        )

    def run(self):
        for line in self.proc.stdout:
            m = RTT_RE.search(line)
            if m:
                self.latest = float(m.group(1))

    def stop(self):
        self.proc.terminate()


def queue_bytes(switch, port):
    """{queue_id: tx_bytes} for one port, read from the root namespace."""
    return queue_counters(switch, port)[0]


def queue_counters(switch, port):
    """Per-queue bytes and OVS-reported tx errors from one switch query."""
    out = subprocess.run(
        ["ovs-ofctl", "-O", "OpenFlow13", "queue-stats", switch, port],
        capture_output=True, universal_newlines=True,
    ).stdout
    byte_counts = {int(qid): int(b) for qid, b in QSTAT_RE.findall(out)}
    errors = {int(qid): int(e) for qid, e in QERR_RE.findall(out)}
    return byte_counts, errors


class MetricsCollector:
    def __init__(self, net, run_dir, port, switch="s1", interval=None, report_callback=None):
        self.net = net
        self.port = port
        self.switch = switch
        self.path = os.path.join(run_dir, "samples.csv")
        self.interval = cfg.SAMPLE_INTERVAL_S if interval is None else interval
        self.report_callback = report_callback
        self.latest = None  # most recent sample dict, read by the adaptive manager
        self._pings = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._t0 = None

    def start(self):
        self._t0 = time.monotonic()
        for name in cfg.SENDER_IPS:
            reader = _PingReader(self.net.get(name), cfg.SERVER_IP, self.interval)
            reader.start()
            self._pings[name] = reader
        self._thread.start()

    def elapsed_now(self):
        return time.monotonic() - (self._t0 or time.monotonic())

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=5)
        for reader in self._pings.values():
            reader.stop()

    def _loop(self):
        t0 = self._t0 or time.monotonic()
        prev_q, prev_t = None, None
        with open(self.path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t", "voip_rtt_ms", "video_rtt_ms", "bulk_rtt_ms",
                        "q0_tx_bytes", "q1_tx_bytes", "q2_tx_bytes",
                        "q0_mbps", "q1_mbps", "q2_mbps", "total_mbps",
                        "voip_delay_ms", "video_delay_ms", "bulk_delay_ms",
                        "voip_jitter_ms", "video_jitter_ms", "bulk_jitter_ms",
                        "voip_probe_loss", "video_probe_loss", "bulk_probe_loss",
                        "backlog_bytes", "drops", "q0_errors", "q1_errors", "q2_errors",
                        "signal_source"])
            while not self._stop.is_set():
                t = round(time.monotonic() - t0, 3)
                rtts = [self._pings[n].latest for n in ("voip", "video", "bulk")]
                q, qe = queue_counters(self.switch, self.port)
                qb = [q.get(i, 0) for i in (0, 1, 2)]

                mbps = [0.0, 0.0, 0.0]
                if prev_q is not None and t > prev_t:
                    mbps = [(b - pb) * 8 / (t - prev_t) / 1e6 for b, pb in zip(qb, prev_q)]
                prev_q, prev_t = qb, t

                probes = read_probe_state(os.path.join(os.path.dirname(self.path), "probes.csv"))
                delays = [probes[c]["delay"] for c in ("voip", "video", "bulk")]
                jitters = [probes[c]["jitter"] for c in ("voip", "video", "bulk")]
                losses = [probes[c]["loss"] for c in ("voip", "video", "bulk")]
                backlog, drops = queue_backlog(self.port)
                source = "telemetry" if self.interval < cfg.SAMPLE_INTERVAL_S else "polling"
                row = [t, *rtts, *qb, *mbps, sum(mbps), *delays, *jitters,
                       *losses, backlog, drops, qe.get(0, 0), qe.get(1, 0), qe.get(2, 0), source]
                w.writerow(row)
                f.flush()
                self.latest = {
                    "t": t,
                    "voip_rtt_ms": rtts[0],
                    "video_rtt_ms": rtts[1],
                    "bulk_rtt_ms": rtts[2],
                    "q_tx_bytes": {0: qb[0], 1: qb[1], 2: qb[2]},
                    "q_errors": {0: qe.get(0, 0), 1: qe.get(1, 0), 2: qe.get(2, 0)},
                    "q_mbps": {0: mbps[0], 1: mbps[1], 2: mbps[2]},
                    "total_mbps": sum(mbps),
                    "class_delay_ms": dict(zip(("voip", "video", "bulk"), delays)),
                    "class_jitter_ms": dict(zip(("voip", "video", "bulk"), jitters)),
                    "class_loss": dict(zip(("voip", "video", "bulk"), losses)),
                    "backlog_bytes": backlog, "drops": drops,
                }
                if self.report_callback:
                    self.report_callback(self.latest)
                self._stop.wait(self.interval)


def read_probe_state(path):
    """Read latest per-class emulated in-band probe measurements."""
    result = {c: {"delay": float("nan"), "jitter": float("nan"), "loss": 0.0}
              for c in ("voip", "video", "bulk")}
    try:
        with open(path, newline="") as f:
            rows = list(csv.reader(f))[-300:]
        latest = {}
        for row in rows:
            if len(row) >= 6 and row[1] in result:
                latest[row[1]] = row
        for c, row in latest.items():
            seq = max(1, int(row[2]) + 1)
            result[c] = {"delay": float(row[3]), "jitter": float(row[4]),
                         "loss": 100.0 * float(row[5]) / seq}
    except (OSError, ValueError):
        pass
    return result


def queue_backlog(port):
    """Best-effort backlog/drop telemetry from tc -s on the OVS egress."""
    try:
        out = subprocess.run(["tc", "-s", "qdisc", "show", "dev", port],
                             capture_output=True, text=True, timeout=0.08).stdout
        backlog = sum(int(x) for x in re.findall(r"backlog\s+(\d+)b", out))
        drops = sum(int(x) for x in re.findall(r"dropped\s+(\d+)", out))
        return backlog, drops
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return 0, 0


class TelemetryCollector:
    """MetricsCollector-compatible UDP report receiver for emulated telemetry.

    A 100 ms local agent samples OVS queue counters and pushes JSON reports to
    this collector. Reports are periodic and additionally tagged on threshold
    crossings. The UDP hop models a telemetry export channel; no switch INT is
    present in this OVS testbed.
    """
    def __init__(self, net, run_dir, port, switch="s1"):
        import json
        import socket
        self.latest = None
        self._stop = threading.Event()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind((cfg.TELEMETRY_REPORT_HOST, cfg.TELEMETRY_REPORT_PORT))
        self._sock.settimeout(0.2)
        self._json = json
        self._agent = MetricsCollector(net, run_dir, port, switch,
                                      interval=cfg.TELEMETRY_INTERVAL_S,
                                      report_callback=self._push)
        self._thread = threading.Thread(target=self._receive, daemon=True)
        self.path = self._agent.path
        self.interval = cfg.TELEMETRY_INTERVAL_S
        self._agent_t0 = None
        self.overhead_path = os.path.join(os.path.dirname(self.path), "telemetry_overhead.csv")

    def _push(self, sample):
        import socket
        report = dict(sample)
        report["monotonic_s"] = time.monotonic()
        report["event"] = bool(
            sample["total_mbps"] / cfg.BOTTLENECK_BW_MBPS > cfg.CONGESTION_UTIL_THRESHOLD
            or (not __import__("math").isnan(sample["voip_rtt_ms"])
                and sample["voip_rtt_ms"] > cfg.CONGESTION_RTT_MS))
        report["signal_source"] = "telemetry"
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as tx:
            tx.sendto(self._json.dumps(report).encode(),
                      (cfg.TELEMETRY_REPORT_HOST, cfg.TELEMETRY_REPORT_PORT))

    def _receive(self):
        started = time.monotonic()
        cpu_started = time.process_time()
        bytes_total = 0
        count = 0
        with open(self.overhead_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["t", "reports", "bytes", "bytes_per_s", "process_cpu_pct"])
            while not self._stop.is_set():
                try:
                    data, _ = self._sock.recvfrom(8192)
                    report = self._json.loads(data.decode())
                    for key in ("q_mbps", "q_tx_bytes", "q_errors"):
                        if key in report:
                            report[key] = {int(k): v for k, v in report[key].items()}
                    report["signal_source"] = "telemetry"
                    self.latest = report
                    bytes_total += len(data)
                    count += 1
                    now = time.monotonic()
                    if now - started >= 1.0:
                        elapsed = now - started
                        writer.writerow([round(now, 3), count, bytes_total,
                                         round(bytes_total / elapsed, 2),
                                         round(100.0 * (time.process_time() - cpu_started) / elapsed, 2)])
                        f.flush()
                        started, cpu_started, bytes_total, count = now, time.process_time(), 0, 0
                except socket.timeout:
                    continue
                except (ValueError, OSError):
                    if not self._stop.is_set():
                        continue

    def start(self):
        self._agent_t0 = time.monotonic()
        self._agent._t0 = self._agent_t0
        self._thread.start()
        self._agent.start()

    def elapsed_now(self):
        return time.monotonic() - (self._agent_t0 or time.monotonic())

    def stop(self):
        self._agent.stop()
        self._stop.set()
        self._sock.close()
        self._thread.join(timeout=1)


def create_collector(net, run_dir, port, signal_source=None, switch="s1"):
    """Construct the shared collector interface from `polling` or `telemetry`."""
    source = cfg.SIGNAL_SOURCE if signal_source is None else signal_source
    if source == "polling":
        return MetricsCollector(net, run_dir, port, switch)
    if source == "telemetry":
        return TelemetryCollector(net, run_dir, port, switch)
    raise ValueError("signal_source must be 'polling' or 'telemetry'")
