"""Aggregate run summaries and render per-run time-series and mode comparisons."""
import argparse
import csv
import json
import math
from pathlib import Path
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def mean_ci(values):
    values = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not values: return None, None, None
    mean = statistics.mean(values)
    if len(values) < 2: return mean, mean, mean
    half = 1.96 * statistics.stdev(values) / math.sqrt(len(values))
    return mean, mean-half, mean+half


def analyze(root, allow_rejected=(), output_name="analysis"):
    """allow_rejected lists modes exempt from the rejection-rate check, for
    reporting learners whose actions the guards mostly block."""
    root = Path(root)
    summaries = []
    rejected = 0
    for path in root.glob("*/*/run_*/summary.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        mode = path.parts[-4]
        run_config = {}
        try:
            run_config = json.loads((path.parent / "config.json").read_text(encoding="utf-8"))["config"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        scenario_cfg = run_config.get("scenarios", {}).get(path.parent.parent.name, {})
        capacity = max([float(run_config.get("network", {}).get("bandwidth_mbps", 0.0))] +
                       [float(rate) for _, rate in scenario_cfg.get("capacity_steps", [])])
        no_queue_modes = {"none", "fq_codel_ecn", "cake"}
        # Older summaries lack the checks needed to establish valid delivered
        # throughput and must not silently enter a new aggregate.
        valid = (data.get("telemetry_valid") is True and
                 data.get("throughput_valid") is True)
        try:
            bulk_mbps = float(data.get("iperf_metrics", {}).get("bulk", {}).get("throughput_mbps"))
            valid = (valid and capacity > 0 and bulk_mbps <= 1.05 * capacity and
                     data.get("bulk_throughput_within_capacity") is True and
                     (mode in allow_rejected or float(data.get("rejection_rate", 1.0)) < 0.30))
        except (TypeError, ValueError, AttributeError):
            valid = False
        if mode not in no_queue_modes:
            try:
                valid = (valid and
                         float(data.get("queue_stats_coverage", 0.0)) >= 0.8 and
                         data.get("queue_counters_valid") is True and
                         data.get("queue_video_rate_matches_iperf") is True)
            except (TypeError, ValueError):
                valid = False
        if valid:
            summaries.append((path, data))
        else:
            rejected += 1
    if not summaries:
        raise SystemExit(f"No telemetry-valid run summaries found under {root}. "
                         "Run or resume experiments with valid telemetry first.")
    if rejected:
        print(f"Ignoring {rejected} run summary/summaries with invalid or incomplete telemetry.")
    records = []
    grouped = {}
    for path, data in summaries:
        mode, scenario = path.parts[-4:-2]
        seed = path.parent.name[4:] if path.parent.name.startswith("run_") else path.parent.name
        row = {"mode": mode, "scenario": scenario, "seed": seed, **data}
        records.append(row); grouped.setdefault((mode, scenario), []).append(data)
        _plot_timeseries(path.parent)
    metrics = sorted({k for item in records for k, v in item.items() if isinstance(v, (int, float)) and k != "seed"})
    output = root / output_name; output.mkdir(parents=True, exist_ok=True)
    rows = []
    for (mode, scenario), runs in sorted(grouped.items()):
        row = {"mode": mode, "scenario": scenario, "runs": len(runs)}
        for metric in metrics:
            mean, low, high = mean_ci([run.get(metric) for run in runs])
            if mean is not None:
                row[metric] = mean; row[metric + "_ci95_low"] = low; row[metric + "_ci95_high"] = high
        rows.append(row)
    fields = sorted({k for r in rows for k in r})
    with (output / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fields); w.writeheader(); w.writerows(rows)
    with (output / "summary.md").open("w", encoding="utf-8") as f:
        f.write("# Experiment summary\n\nMeans and normal-approximation 95% confidence intervals across seeds.\n\n")
        f.write("| Mode | Scenario | Runs | VoIP RTT mean (ms) | Video stability | SLA violations after warm-up | Reserved rate (Mbps) | Operating cost index | Prediction lead (s) | Policy changes |\n|---|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for r in rows:
            changes = f"{r['policy_changes']:.2f}" if isinstance(r.get("policy_changes"), (int, float)) else "—"
            f.write(f"| {r['mode']} | {r['scenario']} | {r['runs']} | {_fmt_ci(r, 'voip_rtt_mean_ms')} | {_fmt_ci(r, 'video_stability_fraction')} | {_fmt_ci(r, 'sla_violation_ratio_after_warmup')} | {_fmt_ci(r, 'reserved_rate_mbps_mean')} | {_fmt_ci(r, 'operating_cost_index')} | {_fmt_ci(r, 'forecast_prediction_lead_s')} | {changes} |\n")
        f.write("\n## Per-class budget metrics\n\nViolation ratios are the fraction of post-warm-up seconds whose one-way delay exceeds the class 5QI budget. Bulk is iperf3 goodput.\n\n")
        f.write("| Mode | Scenario | Runs | VoIP viol. | Video viol. | VoIP p95 delay (ms) | Video p95 delay (ms) | Video loss (%) | Bulk (Mbps) | Bulk goodput (Mbps) | Changes | Flaps | Jain (offered) | Protect lead (s) |\n|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for r in rows:
            f.write(f"| {r['mode']} | {r['scenario']} | {r['runs']} | {_fmt_pm(r, 'delay_sla_violation_ratio_voip')} | {_fmt_pm(r, 'delay_sla_violation_ratio_video')} | {_fmt_pm(r, 'delay_p95_ms_voip', 1)} | {_fmt_pm(r, 'delay_p95_ms_video', 1)} | {_fmt_pm(r, 'video_iperf_loss_pct', 1)} | {_fmt_pm(r, 'bulk_throughput_mbps_mean', 2)} | {_fmt_pm(r, 'bulk_goodput_mbps', 2)} | {_fmt_pm(r, 'policy_changes', 1)} | {_fmt_pm(r, 'policy_flaps', 1)} | {_fmt_pm(r, 'jain_offered')} | {_fmt_pm(r, 'protect_lead_s', 1)} |\n")
    _barplot(rows, output)
    return output


def _fmt_pm(row, key, digits=3):
    if key not in row: return "—"
    half = (row.get(key + "_ci95_high", row[key]) - row.get(key + "_ci95_low", row[key])) / 2
    return f"{row[key]:.{digits}f} ± {half:.{digits}f}"


def _fmt_ci(row, key):
    if key not in row: return "—"
    return f"{row[key]:.3f} [{row.get(key+'_ci95_low', row[key]):.3f}, {row.get(key+'_ci95_high', row[key]):.3f}]"


def _plot_timeseries(run_dir):
    path = run_dir / "samples.csv"
    if not path.exists(): return
    with path.open(newline="", encoding="utf-8") as f: rows = list(csv.DictReader(f))
    if not rows: return
    x = [float(r["t"]) for r in rows]
    fig, axes = plt.subplots(4, 1, figsize=(10, 11), sharex=True)
    axes[0].plot(x, [float(r["utilization"]) for r in rows]); axes[0].set_ylabel("Utilization")
    for cls in ("voip", "video", "bulk"):
        axes[1].plot(x, [_safe(r.get(cls+"_rtt_ms")) for r in rows], label=cls)
        axes[2].plot(x, [_safe(r.get(cls+"_mbps")) for r in rows], label=cls)
    axes[1].set_ylabel("RTT ms"); axes[2].set_ylabel("Throughput Mbps"); axes[2].set_xlabel("Time (s)")
    axes[2].set_xlabel("")
    axes[3].step(x, [int(float(r.get("severity", 0))) for r in rows], where="post", label="severity")
    axes[3].set_ylim(-.1, 2.2); axes[3].set_yticks([0, 1, 2]); axes[3].set_ylabel("Severity")
    decision_file = run_dir / "decisions.csv"
    if decision_file.exists():
        with decision_file.open(newline="", encoding="utf-8") as stream:
            changes = list(csv.DictReader(stream))
        for row in changes:
            axes[3].axvline(float(row["t"]), color="purple", alpha=.45, linewidth=.8)
        if changes:
            axes[3].plot([], [], color="purple", label="policy change")
    axes[3].legend(loc="upper right")
    for ax in axes:
        for i, row in enumerate(rows):
            if int(float(row.get("severity", 0))) >= 2: ax.axvspan(x[i], x[i] + 1, color="red", alpha=.08)
        ax.grid(alpha=.2)
    axes[1].legend(ncol=3); axes[2].legend(ncol=3)
    fig.tight_layout(); fig.savefig(run_dir / "timeseries.png", dpi=140); plt.close(fig)


def _barplot(rows, output):
    metrics = ["voip_rtt_mean_ms", "video_stability_fraction", "operating_cost_index",
               "reservation_cost_fraction_mean", "actuation_cost_fraction", "compute_cost_fraction", "bulk_starvation_s",
               "sla_violation_ratio_after_warmup", "protected_sla_violation_ratio",
               "delay_sla_violation_ratio_voip", "delay_sla_violation_ratio_video",
               "bulk_throughput_mbps_mean", "policy_changes", "policy_flaps",
               "forecast_prediction_lead_s", "forecast_mae",
               "detector_false_positive_rate", "detection_latency_s"]
    for metric in metrics:
        valid = [r for r in rows if metric in r]
        if not valid: continue
        labels = [f"{r['mode']}\n{r['scenario']}" for r in valid]
        fig, ax = plt.subplots(figsize=(max(8, len(valid)*.5), 4))
        means = [r[metric] for r in valid]
        errors = [(r.get(metric, 0)-r.get(metric+"_ci95_low", r.get(metric,0)), r.get(metric+"_ci95_high",r.get(metric,0))-r.get(metric,0)) for r in valid]
        ax.bar(range(len(valid)), means, yerr=[[e[0] for e in errors],[e[1] for e in errors]], capsize=3)
        ax.set_xticks(range(len(valid)), labels, rotation=70, ha="right"); ax.set_ylabel(metric); ax.grid(axis="y", alpha=.2)
        fig.tight_layout(); fig.savefig(output / f"{metric}.png", dpi=140); plt.close(fig)


def _safe(value):
    try:
        result = float(value); return result if math.isfinite(result) else float("nan")
    except (TypeError, ValueError): return float("nan")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--results", default="results")
    parser.add_argument("--allow-rejected", nargs="*", default=[],
                        help="modes exempt from the rejection-rate < 0.30 check")
    parser.add_argument("--output-name", default="analysis",
                        help="analysis folder name under --results")
    args = parser.parse_args()
    print(analyze(args.results, allow_rejected=set(args.allow_rejected), output_name=args.output_name))
