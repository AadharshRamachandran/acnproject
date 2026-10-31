"""Merge analysis/summary.csv from several result sets into per-scenario tables.

Usage: python3 scripts/combine_results.py OUTPUT.md LABEL=results/dir [LABEL=results/dir ...]
       (a source may also be a summary.csv path; earlier sources win per mode)
       python3 scripts/combine_results.py OUTPUT.md LABEL=results/dir --modes none,static,... \
           --scenarios standard,flash_crowd,... --all-metrics

--all-metrics writes one table per scenario with a row per metric and a
column per mode, so every recorded metric fits on the page.
"""
import csv
import sys
from pathlib import Path

COLUMNS = [
    ("VoIP viol.", "delay_sla_violation_ratio_voip", 3),
    ("Video viol.", "delay_sla_violation_ratio_video", 3),
    ("VoIP p95 delay (ms)", "delay_p95_ms_voip", 1),
    ("VoIP RTT (ms)", "voip_rtt_mean_ms", 1),
    ("Video stability", "video_stability_fraction", 3),
    ("Video loss (%)", "video_iperf_loss_pct", 1),
    ("Bulk (Mbps)", "bulk_throughput_mbps_mean", 2),
    ("Bulk starv. (s)", "bulk_starvation_s", 1),
    ("Changes", "policy_changes", 1),
    ("Flaps", "policy_flaps", 1),
    ("Reserved (Mbps)", "reserved_rate_mbps_mean", 2),
    ("Cost index", "operating_cost_index", 3),
]

# (section, label, key, digits, better) for --all-metrics tables.
ALL_METRICS = [
    ("Delay budget (5QI share)", "VoIP budget violation ratio", "delay_sla_violation_ratio_voip", 3, "low"),
    ("Delay budget (5QI share)", "Video budget violation ratio", "delay_sla_violation_ratio_video", 3, "low"),
    ("Delay budget (5QI share)", "Bulk budget violation ratio", "delay_sla_violation_ratio_bulk", 3, "low"),
    ("Delay budget (5QI share)", "Protected (VoIP+video) violation ratio", "protected_sla_violation_ratio", 3, "low"),
    ("Delay budget (5QI share)", "VoIP delay mean (ms)", "delay_mean_ms_voip", 1, "low"),
    ("Delay budget (5QI share)", "VoIP delay p95 (ms)", "delay_p95_ms_voip", 1, "low"),
    ("Delay budget (5QI share)", "Video delay mean (ms)", "delay_mean_ms_video", 1, "low"),
    ("Delay budget (5QI share)", "Video delay p95 (ms)", "delay_p95_ms_video", 1, "low"),
    ("Delay budget (5QI share)", "Bulk delay mean (ms)", "delay_mean_ms_bulk", 1, "low"),
    ("Delay budget (5QI share)", "Bulk delay p95 (ms)", "delay_p95_ms_bulk", 1, "low"),
    ("RTT SLA", "VoIP RTT violation ratio", "rtt_sla_violation_ratio_voip", 3, "low"),
    ("RTT SLA", "Video RTT violation ratio", "rtt_sla_violation_ratio_video", 3, "low"),
    ("RTT SLA", "Bulk RTT violation ratio", "rtt_sla_violation_ratio_bulk", 3, "low"),
    ("RTT SLA", "VoIP SLA violation ratio (RTT 20 ms)", "voip_sla_violation_ratio", 3, "low"),
    ("RTT SLA", "Video SLA violation ratio", "video_sla_violation_ratio", 3, "low"),
    ("RTT SLA", "SLA violation ratio after warm-up", "sla_violation_ratio_after_warmup", 3, "low"),
    ("RTT SLA", "Ground-truth violation fraction", "gt_violation_fraction", 3, "low"),
    ("VoIP", "VoIP throughput (Mbps)", "voip_throughput_mbps_mean", 3, "high"),
    ("VoIP", "VoIP RTT mean (ms)", "voip_rtt_mean_ms", 1, "low"),
    ("VoIP", "VoIP RTT p95 (ms)", "voip_rtt_p95_ms", 1, "low"),
    ("VoIP", "VoIP RTT p99 (ms)", "voip_rtt_p99_ms", 1, "low"),
    ("VoIP", "VoIP jitter (ms)", "voip_jitter_ms_mean", 2, "low"),
    ("VoIP", "VoIP probe loss (%)", "voip_loss_pct_mean", 2, "low"),
    ("VoIP", "VoIP iperf loss (%)", "voip_iperf_loss_pct", 2, "low"),
    ("VoIP", "VoIP MOS estimate", "voip_mos_estimate", 2, "high"),
    ("Video", "Video throughput (Mbps)", "video_throughput_mbps_mean", 2, "high"),
    ("Video", "Video stability fraction", "video_stability_fraction", 3, "high"),
    ("Video", "Video throughput CV", "video_throughput_cv", 3, "low"),
    ("Video", "Video RTT mean (ms)", "video_rtt_mean_ms", 1, "low"),
    ("Video", "Video RTT p95 (ms)", "video_rtt_p95_ms", 1, "low"),
    ("Video", "Video RTT p99 (ms)", "video_rtt_p99_ms", 1, "low"),
    ("Video", "Video jitter (ms)", "video_jitter_ms_mean", 2, "low"),
    ("Video", "Video probe loss (%)", "video_loss_pct_mean", 2, "low"),
    ("Video", "Video iperf loss (%)", "video_iperf_loss_pct", 2, "low"),
    ("Bulk", "Bulk throughput (Mbps)", "bulk_throughput_mbps_mean", 2, "high"),
    ("Bulk", "Bulk goodput (Mbps)", "bulk_goodput_mbps", 2, "high"),
    ("Bulk", "Bulk starvation (s)", "bulk_starvation_s", 1, "low"),
    ("Bulk", "Bulk RTT mean (ms)", "bulk_rtt_mean_ms", 1, "low"),
    ("Bulk", "Bulk RTT p95 (ms)", "bulk_rtt_p95_ms", 1, "low"),
    ("Bulk", "Bulk RTT p99 (ms)", "bulk_rtt_p99_ms", 1, "low"),
    ("Bulk", "Bulk jitter (ms)", "bulk_jitter_ms_mean", 2, "low"),
    ("Bulk", "Bulk probe loss (%)", "bulk_loss_pct_mean", 2, "low"),
    ("Fairness", "Jain index (vs class targets)", "jain_index_mean", 3, "high"),
    ("Fairness", "Jain index (vs offered load)", "jain_offered", 3, "high"),
    ("Control", "Policy changes", "policy_changes", 1, "low"),
    ("Control", "Policy flaps", "policy_flaps", 1, "low"),
    ("Control", "Decisions logged", "decisions_logged", 1, "—"),
    ("Control", "Rejection rate", "rejection_rate", 3, "low"),
    ("Control", "Protect lead time (s)", "protect_lead_s", 1, "high"),
    ("Control", "Prediction lead (s)", "prediction_lead_s", 1, "high"),
    ("Control", "Forecast prediction lead (s)", "forecast_prediction_lead_s", 1, "high"),
    ("Control", "Forecast MAE", "forecast_mae", 3, "low"),
    ("Control", "Detection latency (s)", "detection_latency_s", 1, "low"),
    ("Control", "Time to act (s)", "time_to_act_s", 1, "low"),
    ("Control", "Time to recover (s)", "time_to_recover_s", 1, "low"),
    ("Control", "Actuation latency (s)", "actuation_latency_mean_s", 3, "low"),
    ("Control", "Detector false-positive rate", "detector_false_positive_rate", 3, "low"),
    ("Control", "Detector missed-detection rate", "detector_missed_detection_rate", 3, "low"),
    ("Control", "False-alarm QoS cost", "false_alarm_qos_cost_mean", 3, "low"),
    ("Cost", "Reserved rate (Mbps)", "reserved_rate_mbps_mean", 2, "low"),
    ("Cost", "Reservation fraction", "reservation_cost_fraction_mean", 3, "low"),
    ("Cost", "Actuation fraction", "actuation_cost_fraction", 3, "low"),
    ("Cost", "Compute fraction", "compute_cost_fraction", 3, "low"),
    ("Cost", "Controller CPU (s/tick)", "controller_cpu_s_per_tick", 4, "low"),
    ("Cost", "Operating cost index", "operating_cost_index", 3, "low"),
    ("Telemetry", "Queue stats coverage", "queue_stats_coverage", 3, "high"),
    ("Telemetry", "Queue video rate (Mbps)", "queue_video_rate_mbps_mean", 2, "—"),
    ("Telemetry", "Queue/iperf video rate ratio", "queue_video_rate_iperf_ratio", 3, "≈1"),
]


def fmt(row, key, digits):
    value = row.get(key)
    if value in (None, ""):
        return "—"
    mean = float(value)
    try:
        half = (float(row[key + "_ci95_high"]) - float(row[key + "_ci95_low"])) / 2
    except (KeyError, ValueError):
        half = 0.0
    return f"{mean:.{digits}f} ± {half:.{digits}f}" if half > 0.5 * 10 ** -digits else f"{mean:.{digits}f}"


def _option(args, name):
    if name not in args:
        return None
    index = args.index(name)
    value = args[index + 1].split(",")
    del args[index:index + 2]
    return value


def _wide(by_scenario, sources, scenarios):
    header = "| Source | Mode | Runs | " + " | ".join(name for name, _, _ in COLUMNS) + " |"
    rule = "|---|---|---:|" + "---:|" * len(COLUMNS)
    order = {label: index for index, (label, _) in enumerate(sources)}
    lines = []
    for scenario in scenarios:
        lines += [f"## {scenario}", "", header, rule]
        for label, row in sorted(by_scenario[scenario], key=lambda item: (order[item[0]], item[1]["mode"])):
            cells = [fmt(row, key, digits) for _, key, digits in COLUMNS]
            lines.append(f"| {label} | {row['mode']} | {row['runs']} | " + " | ".join(cells) + " |")
        lines.append("")
    return lines


def _tall(by_scenario, scenarios, modes):
    lines = []
    for scenario in scenarios:
        rows = {}
        for _, row in by_scenario[scenario]:
            rows.setdefault(row["mode"], row)  # earlier sources win
        present = [mode for mode in modes if mode in rows]
        lines += [f"## {scenario}", "",
                  "| Metric | Better | " + " | ".join(present) + " |",
                  "|---|:---:|" + "---:|" * len(present),
                  "| **Runs** | | " + " | ".join(rows[m]["runs"] for m in present) + " |"]
        section = None
        for name, label, key, digits, better in ALL_METRICS:
            if all(rows[m].get(key) in (None, "") for m in present):
                continue
            if name != section:
                section = name
                lines.append(f"| **{name}** | |" + " |" * len(present))
            lines.append(f"| {label} | {better} | " +
                         " | ".join(fmt(rows[m], key, digits) for m in present) + " |")
        lines.append("")
    return lines


def main():
    args = sys.argv[1:]
    all_metrics = "--all-metrics" in args
    if all_metrics:
        args.remove("--all-metrics")
    modes = _option(args, "--modes")
    scenarios = _option(args, "--scenarios")
    output = Path(args[0])
    sources = [arg.split("=", 1) for arg in args[1:]]
    by_scenario = {}
    for label, directory in sources:
        path = Path(directory)
        path = path if path.suffix == ".csv" else path / "analysis" / "summary.csv"
        with path.open(encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                if modes is None or row["mode"] in modes:
                    by_scenario.setdefault(row["scenario"], []).append((label, row))
    scenarios = [s for s in (scenarios or sorted(by_scenario)) if s in by_scenario]
    lines = ["# All results by scenario", "",
             "Mean ± 95% CI half-width across seeds (no ± when the interval is zero or there is one run). "
             "— means the metric was not recorded in that result set.", ""]
    if all_metrics:
        lines += _tall(by_scenario, scenarios, modes or sorted({r["mode"] for v in by_scenario.values() for _, r in v}))
    else:
        lines += _wide(by_scenario, sources, scenarios)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
