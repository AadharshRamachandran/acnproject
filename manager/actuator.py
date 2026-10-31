"""Direct-tc HTB actuator: bypasses OVS linux-htb and applies tc directly.

OVS 2.13's vswitchd creates OVSDB QoS records when ``ovs-vsctl set Port ...
qos=... type=linux-htb`` is called, but does *not* translate those records
into kernel tc qdiscs in the Docker test environment.  The net effect is that
``ovs-vsctl clear Port ... qos`` (called first for idempotency) strips
Mininet's original HTB qdisc, and then the replacement linux-htb structure is
never written to the kernel — leaving the bottleneck interface with no qdisc
at all.

This module bypasses OVS's QoS path entirely and applies tc HTB directly to
the bottleneck interface.  All subprocess calls go through ``_run()`` so
existing test monkeypatching continues to work.

Handle scheme (chosen to avoid collision with OVS's port-based major numbers):
    1:      root HTB qdisc
    1:fffe  root ceiling class (link capacity)
    1:1     voip  (minor 1 → queue_names[1] = 'voip'  in _tc_stats)
    1:2     video (minor 2 → queue_names[2] = 'video' in _tc_stats)
    1:3     bulk  (minor 3 → queue_names[3] = 'bulk'  in _tc_stats)
    1:4     default (minor 4 → not in queue_names, skipped)
    11:     leaf netem qdisc for voip class
    22:     leaf netem qdisc for video class
    33:     leaf netem qdisc for bulk class
    44:     leaf netem qdisc for default class
"""
import re
import subprocess
import time


CLASS_RE = re.compile(r"class htb ([0-9a-fA-F]+:[0-9a-fA-F]+).*?(?=\nclass htb |\Z)", re.S)
RATE_RE = re.compile(r"\b(rate|ceil)\s+([0-9.]+)(bit|Kbit|Mbit|Gbit)")
UNIT = {"bit": 1, "Kbit": 1000, "Mbit": 1000000, "Gbit": 1000000000}

# Root qdisc handle major — must differ from OVS's port-number-based majors.
_TC_HANDLE = "1"

# Traffic-class → (tc class minor, HTB priority)
# minor values must match the queue_names dict used in collector._tc_stats():
#   queue_names = {0:'default', 1:'voip', 2:'video', 3:'bulk'}
_CLASS_CFG = {
    "voip":    (1, 1),
    "video":   (2, 2),
    "bulk":    (3, 3),
    "default": (4, 4),
}


def _run(argv, timeout=5):
    try:
        result = subprocess.run(argv, check=True, capture_output=True,
                                text=True, timeout=timeout)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"Command failed: {' '.join(argv)}\n{detail}") from exc
    return result.stdout.strip()


def _run_best_effort(argv, timeout=5):
    """Like _run but swallows failures (used for idempotent deletes)."""
    try:
        _run(argv, timeout=timeout)
    except RuntimeError:
        pass


def tc_class_rates(interface):
    text = _run(["tc", "-s", "class", "show", "dev", interface])
    rates = {}
    for match in CLASS_RE.finditer(text):
        class_id = match.group(1).lower()
        class_rates = {kind: round(float(value) * UNIT[unit])
                       for kind, value, unit in RATE_RE.findall(match.group(0))}
        if "rate" in class_rates:
            rates[class_id] = (class_rates["rate"], class_rates.get("ceil"))
    return rates


def _bps_to_tc(bps):
    """Convert integer bps to a tc rate string."""
    bps = int(bps)
    if bps >= 1_000_000:
        return f"{bps / 1_000_000:.4g}mbit"
    if bps >= 1_000:
        return f"{bps / 1_000:.4g}kbit"
    return f"{bps}bit"


def apply_tc_htb(interface, config):
    """Apply (or reapply) the direct tc HTB structure to *interface*.

    Creates the root HTB qdisc, the ceiling class, per-traffic-class children
    with netem leaf qdiscs (preserving the configured link delay), and u32
    filters that steer traffic by IP destination port.

    All commands go through ``_run()`` so the test suite can monkeypatch them.
    """
    qos = config["qos"]
    delay_ms = int(config["network"]["delay_ms"])
    cap_bps = int(qos["link_capacity_bps"])
    cap_str = _bps_to_tc(cap_bps)
    ports = config["network"]["ports"]

    # ── root qdisc ────────────────────────────────────────────────────────
    # 'replace' is idempotent: creates if absent, replaces if present.
    # default 4 → unclassified traffic lands in the default (bulk overflow) class.
    _run(["tc", "qdisc", "replace", "dev", interface,
          "root", "handle", f"{_TC_HANDLE}:", "htb", "default", "4"])

    # ── root ceiling class (1:fffe) ────────────────────────────────────────
    _run(["tc", "class", "replace", "dev", interface,
          "parent", f"{_TC_HANDLE}:0",
          "classid", f"{_TC_HANDLE}:fffe",
          "htb", "rate", cap_str, "ceil", cap_str])

    # ── per-traffic-class children ─────────────────────────────────────────
    class_specs = {
        "voip":    qos["queues"]["voip"],
        "video":   qos["queues"]["video"],
        "bulk":    qos["queues"]["bulk"],
        "default": qos["default"],
    }
    for cls, (minor, prio) in _CLASS_CFG.items():
        spec = class_specs[cls]
        min_str = _bps_to_tc(int(spec["min_bps"]))
        max_str = _bps_to_tc(int(spec["max_bps"]))
        _run(["tc", "class", "replace", "dev", interface,
              "parent", f"{_TC_HANDLE}:fffe",
              "classid", f"{_TC_HANDLE}:{minor}",
              "htb", "rate", min_str, "ceil", max_str, "prio", str(prio)])
        # netem leaf: preserves the per-link delay configured in the topology.
        leaf_handle = f"{minor}{minor}:"   # 11:, 22:, 33:, 44:
        _run(["tc", "qdisc", "replace", "dev", interface,
              "parent", f"{_TC_HANDLE}:{minor}",
              "handle", leaf_handle,
              "netem", "delay", f"{delay_ms}ms", "limit", "100"])

    # ── u32 destination-port filters ──────────────────────────────────────
    # Remove stale filters before adding fresh ones (best-effort).
    _run_best_effort(["tc", "filter", "del", "dev", interface,
                      "parent", f"{_TC_HANDLE}:"])
    # Extra sessions of a class (VoIP surges, video steps/bursts, extra bulk
    # streams) listen on the class base port + 1 .. + extra_class_ports, since
    # one iperf3 server serves one test at a time; they still belong to it.
    extra = int(config["network"].get("extra_class_ports", 8))
    for cls in ("voip", "video", "bulk"):
        minor, prio = _CLASS_CFG[cls]
        for port in range(int(ports[cls]), int(ports[cls]) + extra + 1):
            _run(["tc", "filter", "add", "dev", interface,
                  "parent", f"{_TC_HANDLE}:0",
                  "protocol", "ip", "prio", str(prio),
                  "u32", "match", "ip", "dport", str(port), "0xffff",
                  "flowid", f"{_TC_HANDLE}:{minor}"])


def setup_qos(interface, config):
    """Set up per-class QoS on the bottleneck interface via direct tc HTB.

    OVS linux-htb QoS is not applied to the kernel in this Docker environment
    (vswitchd creates OVSDB records but fails to write tc qdiscs).  This
    function applies tc HTB directly, bypassing OVS's QoS subsystem.

    Returns a dict ``{class_name: class_id_str}`` that records the tc class
    IDs assigned to each traffic class.  Callers that previously used OVS
    Queue UUIDs to key rate updates should switch to these class ID strings
    (or use ``OVSActuator.apply()`` which handles this transparently).
    """
    # Clear any pre-existing OVS QoS association so vswitchd does not try to
    # (re)apply its own tc structure on top of ours.  Failure is non-fatal
    # (the port may not be registered in OVS during standalone-mode tests).
    _run_best_effort(["ovs-vsctl", "--", "clear", "Port", interface, "qos"])

    # Apply tc HTB directly.
    apply_tc_htb(interface, config)

    # Return tc class IDs keyed by class name.  Format matches the historic
    # "uuid" dict so callers (including queue_uuids.json writers) require no
    # structural changes.
    return {cls: f"{_TC_HANDLE}:{minor}"
            for cls, (minor, _prio) in _CLASS_CFG.items()}


class OVSActuator:
    def __init__(self, interface, queue_uuids, config):
        self.interface = interface
        # queue_uuids now holds tc class IDs (e.g. {"voip": "1:1", ...})
        self.queue_uuids = queue_uuids
        self.config = config

    def apply(self, rates):
        """Apply per-class rate changes via ``tc class change``."""
        before = tc_class_rates(self.interface)
        started = time.monotonic()

        for cls, (minor, prio) in _CLASS_CFG.items():
            if cls == "default":
                continue
            spec = rates.get(cls)
            if not spec:
                continue
            min_str = _bps_to_tc(int(spec["min_bps"]))
            max_str = _bps_to_tc(int(spec["max_bps"]))
            _run(["tc", "class", "change", "dev", self.interface,
                  "parent", f"{_TC_HANDLE}:fffe",
                  "classid", f"{_TC_HANDLE}:{minor}",
                  "htb", "rate", min_str, "ceil", max_str,
                  "prio", str(prio)])

        timeout = float(self.config["runtime"]["tick_seconds"])
        deadline = started + timeout
        observed = False
        while time.monotonic() < deadline:
            try:
                if tc_class_rates(self.interface) != before:
                    observed = True
                    break
            except (subprocess.SubprocessError, OSError):
                pass
            time.sleep(min(0.05, timeout / 10))
        after = tc_class_rates(self.interface)
        if not observed:
            raise RuntimeError(
                f"tc accepted QoS updates on {self.interface}, but class rates did not change "
                f"within {timeout:g}s (before={before}, after={after})")
        return {"latency_seconds": time.monotonic() - started,
                "observed": observed, "before": before, "after": after}
