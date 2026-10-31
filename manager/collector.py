"""Combine tc HTB counters and per-class ping probes into per-tick samples.

Queue telemetry is sourced directly from ``tc -s class show``.  OVS 2.13 does
not implement the OpenFlow OFPMP_QUEUE_STATS multipart reply for Linux-HTB
queues; any Ryu-side OFPQueueStatsRequest is silently dropped.  The tc-based
path reads the same kernel counters that OVS writes and is fully reliable.
"""
import math
import random
import re
import subprocess
import threading
import time


RTT_RE = re.compile(r"time=([0-9.]+)\s*ms")
SEQ_RE = re.compile(r"icmp_seq[= ](\d+)")
BACKLOG_RE = re.compile(r"backlog\s+(\d+)([KMG]?)b")
DROP_RE = re.compile(r"dropped\s+(\d+)")
# Matches "Sent 123456 bytes" from `tc -s class show` statistics lines.
SENT_RE = re.compile(r"Sent\s+(\d+)\s+bytes")
SCALE = {"": 1, "K": 1000, "M": 1000000, "G": 1000000000}


class PingProbe(threading.Thread):
    def __init__(self, host, destination, interval):
        super().__init__(daemon=True)
        self.host, self.destination, self.interval = host, destination, interval
        self.latest_ms = float("nan")
        self.losses = 0
        self.sent = 0
        self.received = 0
        self.stop_event = threading.Event()
        self.proc = None

    def run(self):
        self.proc = self.host.popen(["ping", "-n", "-i", str(self.interval), self.destination],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    universal_newlines=True)
        for line in self.proc.stdout:
            if self.stop_event.is_set():
                break
            seq = SEQ_RE.search(line)
            rtt = RTT_RE.search(line)
            if seq:
                seq_n = int(seq.group(1))
                self.sent = max(self.sent, seq_n)
            elif "Destination Host Unreachable" in line or "100% packet loss" in line:
                self.losses += 1
            if rtt:
                self.latest_ms = float(rtt.group(1))
                self.received += 1

    @property
    def loss_pct(self):
        return 100.0 * max(0, self.sent - self.received) / max(1, self.sent)

    def stop(self):
        self.stop_event.set()
        if self.proc:
            self.proc.terminate()


class MetricsCollector:
    def __init__(self, net, interface, config, seed=7, scenario=None):
        self.net, self.interface, self.config = net, interface, config
        self.tick = float(config["runtime"]["tick_seconds"])
        self.random = random.Random(seed)
        self.scenario = scenario or {}
        self.probes = {}
        self.t0 = None
        self._last_tc_text = ""
        self._last_drop_total = 0
        self._last_queue_drops = {}
        # tc-based queue rate tracking: maps class name → (tx_bytes, monotonic_s)
        self._last_tc_tx = {}

    def start(self):
        for cls, ip in self.config["network"]["server_ips"].items():
            self.probes[cls] = PingProbe(self.net.get(f"h_{cls}_src"), ip, self.tick)
            self.probes[cls].start()
        self.t0 = time.monotonic()

    def sample(self, sim_t=None):
        now = time.monotonic()
        backlog, drops, per_queue = self._tc_stats()

        # --- queue rates from tc tx_bytes deltas ----------------------------
        classes = ("voip", "video", "bulk")
        queue_mbps = {}
        queue_tx_bytes = {}
        for cls in classes:
            entry = per_queue.get(cls)
            if entry is None or entry.get("tx_bytes") is None:
                # HTB class not yet visible (queues not yet applied)
                continue
            tx_bytes = entry.get("tx_bytes", 0)
            prev = self._last_tc_tx.get(cls)
            if prev is not None:
                prev_bytes, prev_time = prev
                elapsed = max(now - prev_time, 1e-6)
                delta = tx_bytes - prev_bytes
                # Counter reset after bridge teardown between runs → treat as baseline.
                if delta < 0:
                    delta = tx_bytes
                queue_mbps[cls] = delta * 8 / elapsed / 1e6
            else:
                queue_mbps[cls] = 0.0
            queue_tx_bytes[cls] = tx_bytes
            self._last_tc_tx[cls] = (tx_bytes, now)

        # A sample is valid when all three traffic classes are represented.
        # The first tick always yields 0.0 Mbps (no previous reading), which
        # is consistent with the old Ryu-OFP behaviour.
        tc_valid = set(classes).issubset(queue_mbps)

        # --- per-class drop rates -------------------------------------------
        drop_rate = max(0, drops - self._last_drop_total) / max(self.tick, 1e-9)
        self._last_drop_total = drops
        per_class_drop_rate = {}
        for cls, values in per_queue.items():
            count = values["drops"]
            per_class_drop_rate[cls] = (
                max(0, count - self._last_queue_drops.get(cls, count)) / max(self.tick, 1e-9)
            )
            self._last_queue_drops[cls] = count

        # --- ping probes ----------------------------------------------------
        if (self.scenario.get("name") == "noisy_telemetry" and
                self.random.random() < self.scenario["config"]["probe_loss_probability"]):
            rtts = {cls: float("nan") for cls in self.probes}
        else:
            rtts = {cls: probe.latest_ms for cls, probe in self.probes.items()}

        # --- noisy_telemetry counter jitter --------------------------------
        if self.scenario.get("name") == "noisy_telemetry" and tc_valid:
            fraction = self.scenario["config"]["counter_jitter_fraction"]
            queue_mbps = {
                k: max(0.0, v * (1 + self.random.uniform(-fraction, fraction)))
                for k, v in queue_mbps.items()
            }

        capacity = float(self.config["network"]["bandwidth_mbps"])
        used = sum(float(queue_mbps.get(cls, 0.0)) for cls in classes)
        class_delay_ms = {
            cls: estimate_class_delay_ms(
                per_queue.get(cls, {}).get("backlog_bytes", 0),
                queue_mbps.get(cls, 0.0),
                float(self.config["network"].get("delay_ms", 5.0)),
                float(self.config["qos"]["queues"][cls]["min_bps"]) / 1e6,
                float(self.config["network"].get("max_estimated_delay_ms", 5000.0)),
            )
            for cls in classes
        }

        return {
            "t": sim_t if sim_t is not None else now - self.t0,
            "monotonic_s": now,
            "queue_mbps": queue_mbps if tc_valid else {},
            # queue_stats_received mirrors the old Ryu-OFP flag; now driven by tc.
            "queue_stats_received": tc_valid,
            "queue_errors": {},
            "queue_tx_bytes": {cls: queue_tx_bytes.get(cls, 0) for cls in classes},
            "q_mbps": queue_mbps if tc_valid else {},
            "utilization": min(1.5, used / capacity),
            "voip_rtt_ms": rtts["voip"],
            "video_rtt_ms": rtts["video"],
            "bulk_rtt_ms": rtts["bulk"],
            "probe_loss_pct": {cls: probe.loss_pct for cls, probe in self.probes.items()},
            "backlog_bytes": backlog,
            "drop_rate": drop_rate,
            "queue_backlog_bytes": {
                c: per_queue.get(c, {}).get("backlog_bytes", 0) for c in classes
            },
            "class_delay_ms": class_delay_ms,
            "queue_drops": {c: per_class_drop_rate.get(c, 0.0) for c in classes},
            # stale is always False with tc-based telemetry: we read fresh data
            # each tick synchronously, so there is no "stale" concept.
            "stale": False,
            "stale_ticks": 0,
            "tc_class_text": self._last_tc_text,
        }

    def _tc_stats(self):
        """Read per-queue backlog, drop, and tx_bytes from tc HTB class stats."""
        try:
            result = subprocess.run(
                ["tc", "-s", "class", "show", "dev", self.interface],
                check=True, capture_output=True, text=True, timeout=self.tick / 2,
            )
            self._last_tc_text = result.stdout
            per_queue = {}
            queue_names = {
                int(qid): name
                for name, qid in self.config["network"]["queue_ids"].items()
            }
            blocks = re.split(r"(?=class htb )", result.stdout)
            for block in blocks:
                match = re.search(r"class htb [0-9a-fA-F]+:([0-9a-fA-F]+)", block)
                if not match:
                    continue
                qid = int(match.group(1), 16)
                name = queue_names.get(qid)
                if not name or name == "default":
                    continue
                backlog_values = [int(n) * SCALE[u] for n, u in BACKLOG_RE.findall(block)]
                drop_values = [int(n) for n in DROP_RE.findall(block)]
                # "Sent N bytes" is the cumulative tx counter for this HTB class.
                sent_match = SENT_RE.search(block)
                # Missing counters must not be mistaken for a valid zero-byte
                # counter; otherwise a partial tc dump can pass coverage checks.
                tx_bytes = int(sent_match.group(1)) if sent_match else None
                per_queue[name] = {
                    "backlog_bytes": sum(backlog_values),
                    "drops": sum(drop_values),
                    "tx_bytes": tx_bytes,
                }
            backlog = sum(v["backlog_bytes"] for v in per_queue.values())
            drops = sum(v["drops"] for v in per_queue.values())
            return backlog, drops, per_queue
        except (OSError, subprocess.SubprocessError):
            self._last_tc_text = ""
            return 0, 0, {}

    def stop(self):
        for probe in self.probes.values():
            probe.stop()
        for probe in self.probes.values():
            probe.join(timeout=1)

    @property
    def elapsed(self):
        return time.monotonic() - self.t0 if self.t0 else 0.0


def estimate_class_delay_ms(backlog_bytes, rate_mbps, base_delay_ms,
                            minimum_rate_mbps=0.1, maximum_delay_ms=5000.0):
    """Estimate one-way delay from an HTB class backlog and its send rate.

    Rates are Mbps, backlog is bytes, and the result is milliseconds. The class
    backlog includes packets held in the netem leaf for the propagation delay
    (about rate x delay bytes), so backlog/rate already covers that delay;
    the estimate is therefore max(propagation, backlog/rate). The class's
    guaranteed rate bounds the denominator so a single queued packet of a
    low-rate class is not read as a long wait. The result is capped.
    """
    backlog = max(0.0, float(backlog_bytes))
    rate = max(float(rate_mbps), float(minimum_rate_mbps), 1e-6)
    delay = max(max(0.0, float(base_delay_ms)), backlog * 8.0 / (rate * 1000.0))
    return min(max(0.0, float(maximum_delay_ms)), delay)
