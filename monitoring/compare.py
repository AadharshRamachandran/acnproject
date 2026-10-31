"""Stream C: compare none / static / adaptive runs side by side.

    python3 monitoring/compare.py results/<run-none> results/<run-static> results/<run-adaptive> [...]

Multiple runs of the same mode are averaged. Produces in results/comparison/:
    comparison.csv      per-mode, per-class metrics (congested window)
    comparison.png      bar charts: VoIP RTT, VoIP loss, video throughput, recovery time
    timeseries.png      VoIP RTT and video throughput over time, one line per mode
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common import config as cfg
from monitoring.analyze import build_summary, load_run, policy_reaction_time, recovery_time

MODE_ORDER = ["none", "static", "adaptive", "rule-polling", "rule-telemetry", "rl-polling", "rl-telemetry"]


def collect(run_dirs):
    summaries, series = [], {}
    for rd in run_dirs:
        meta, per_class, samples, decisions = load_run(rd)
        mode = meta.get("mode", os.path.basename(rd).split("-")[-1])
        s = build_summary(meta, per_class, samples)
        if not decisions.empty and {"bulk_max_rate", "voip_min_rate", "video_min_rate"}.issubset(decisions.columns):
            changes = decisions[["bulk_max_rate", "voip_min_rate", "video_min_rate"]].diff().fillna(0).ne(0).any(axis=1)
            s["policy_changes"] = int(changes.sum())
            s["reaction_time_s"] = policy_reaction_time(
                samples, decisions, meta.get("t_cong_sample", meta.get("t_cong", 0)))
        s["recovery_time_s"] = recovery_time(
            samples, meta.get("t_cong_sample", meta.get("t_cong", 0)))
        s["run"] = os.path.basename(rd)
        summaries.append(s)
        series.setdefault(mode, []).append((samples, per_class))
    return pd.concat(summaries, ignore_index=True), series


def compare(run_dirs, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    df, series = collect(run_dirs)

    metric_cols = [c for c in df.columns if c not in ("mode", "class", "run")]
    grouped = df.groupby(["mode", "class"])[metric_cols]
    agg = grouped.mean().reset_index()
    for col in metric_cols:
        ci = grouped[col].agg(lambda x: 1.96 * x.std(ddof=1) / (len(x) ** 0.5) if len(x) > 1 else 0.0)
        agg[col + "_ci95"] = [ci.loc[(row["mode"], row["class"])] for _, row in agg.iterrows()]
    agg["mode"] = pd.Categorical(agg["mode"], MODE_ORDER)
    agg = agg.sort_values(["class", "mode"])
    agg.to_csv(os.path.join(out_dir, "comparison.csv"), index=False)
    with open(os.path.join(out_dir, "summary.md"), "w") as f:
        f.write("# Experiment summary\n\nMean and 95% confidence interval (normal approximation); missing values mean no valid observation.\n\n")
        f.write("| Mode | Class | Throughput (Mbps) | RTT (ms) | Loss (%) | Detection (s) | Reaction (s) | Policy changes | Telemetry (bytes/s) | Process CPU (%) |\n|---|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for _, row in agg.iterrows():
            def ci_text(column, digits=2):
                value, ci = row.get(column), row.get(column + "_ci95", 0)
                return "n/a" if pd.isna(value) else f"{value:.{digits}f} ± {ci:.{digits}f}"
            f.write(f"| {row['mode']} | {row['class']} | {ci_text('avg_mbps_congested')} | {ci_text('avg_rtt_ms_congested')} | {ci_text('loss_pct_congested')} | {ci_text('detection_latency_s')} | {ci_text('reaction_time_s')} | {ci_text('policy_changes', 0)} | {ci_text('telemetry_bytes_per_s')} | {ci_text('telemetry_process_cpu_pct')} |\n")
    print(agg.to_string(index=False))

    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    panels = [
        ("voip", "avg_rtt_ms_congested", "VoIP RTT under congestion (ms)"),
        ("voip", "loss_pct_congested", "VoIP loss under congestion (%)"),
        ("video", "avg_mbps_congested", "Video throughput under congestion (Mbit/s)"),
        ("voip", "recovery_time_s", "QoS recovery time (s)"),
    ]
    for ax, (cls, col, title) in zip(axes.flat, panels):
        sub = agg[agg["class"] == cls].set_index("mode").reindex(MODE_ORDER)
        ax.bar(sub.index.astype(str), sub[col].fillna(0))
        ax.set_title(title)
        for i, v in enumerate(sub[col]):
            if pd.notna(v):
                ax.text(i, v, f"{v:.1f}", ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "comparison.png"), dpi=120)
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(9, 7), sharex=True)
    for mode in MODE_ORDER:
        if mode not in series:
            continue
        samples, per_class = series[mode][0]
        axes[0].plot(samples["t"], samples["voip_rtt_ms"], label=mode)
        if not per_class["video"].empty:
            axes[1].plot(per_class["video"]["t"], per_class["video"]["mbps"], label=mode)
    axes[0].axhline(cfg.CONGESTION_RTT_MS, ls=":", c="grey")
    axes[0].set_ylabel("VoIP RTT (ms)")
    axes[1].set_ylabel("Video throughput (Mbit/s)")
    axes[1].set_xlabel("Time (s)")
    for ax in axes:
        ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "timeseries.png"), dpi=120)
    plt.close(fig)
    print(f"-> {out_dir}/comparison.png, timeseries.png")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: compare.py results/<run> [results/<run> ...]")
        sys.exit(1)
    compare(sys.argv[1:], os.path.join(cfg.RESULTS_DIR, "comparison"))
