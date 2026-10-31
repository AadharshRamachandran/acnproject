"""Train the offline RandomForest detector from labelled sample CSV files."""
import argparse
import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from manager.config import load_config
from manager.detectors import train_supervised


CONTROLLER_FREE_MODES = {"none", "fq_codel_ecn"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="+", help="samples.csv files with bulk_active, voip_rtt_ms and sla_rtt_ms")
    parser.add_argument("--output")
    args = parser.parse_args()
    samples = []
    source_modes = set()
    for filename in args.csv:
        summary_path = Path(filename).resolve().parent / "summary.json"
        if not summary_path.exists():
            raise ValueError(f"{filename}: missing run summary; train only from a completed, validated run")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        run_config_path = Path(filename).resolve().parent / "config.json"
        run_mode = None
        if run_config_path.exists():
            run_mode = json.loads(run_config_path.read_text(encoding="utf-8")).get("run", {}).get("mode")
        source_modes.add(run_mode)
        valid_run = (summary.get("telemetry_valid") is True and
                     summary.get("throughput_valid") is True and
                     summary.get("bulk_throughput_within_capacity") is True and
                     float(summary.get("rejection_rate", 1.0)) < 0.30)
        if run_mode not in CONTROLLER_FREE_MODES:
            valid_run = (valid_run and
                         summary.get("queue_video_rate_matches_iperf") is True)
        if not valid_run:
            raise ValueError(f"{filename}: run summary failed queue/iperf validation; refusing to train")
        with open(filename, newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            rows = list(reader)
            if not rows:
                raise ValueError(f"{filename}: no samples found")
            if "queue_stats_received" not in (reader.fieldnames or []):
                raise ValueError(f"{filename}: missing queue_stats_received; use samples from the current research runner")
            if run_mode not in CONTROLLER_FREE_MODES:
                coverage = sum(str(row.get("queue_stats_received", "")).lower() == "true"
                               for row in rows) / len(rows)
                if coverage < 0.8:
                    raise ValueError(f"{filename}: queue-stat coverage is {coverage:.1%}; "
                                     "collect valid controller-backed samples before training")
                for cls in ("voip", "video", "bulk"):
                    column = f"queue_{cls}_tx_bytes"
                    if column not in (reader.fieldnames or []):
                        raise ValueError(f"{filename}: missing {column}; collect samples with validated queue counters")
                    if max((_float(row.get(column)) for row in rows), default=0.0) <= 0:
                        raise ValueError(f"{filename}: {cls} queue has no transmitted bytes; refusing to train on incomplete telemetry")
            if max((_float(row.get("video_mbps")) for row in rows), default=0.0) <= 0:
                raise ValueError(f"{filename}: video queue has no measured throughput; refusing to train on incomplete telemetry")
            for row in rows:
                samples.append({k: _float(v) for k, v in row.items()})
                samples[-1]["bulk_active"] = str(row.get("bulk_active", "0")).lower() in ("1", "true", "yes")
    positive = sum(
        bool(_float(sample.get("gt_congestion"))) if "gt_congestion" in sample else
        bool(sample["bulk_active"]) and
        math.isfinite(_float(sample.get("voip_rtt_ms"))) and
        _float(sample.get("voip_rtt_ms")) > _float(sample.get("sla_rtt_ms", 20.0))
        for sample in samples)
    negative = len(samples) - positive
    if not positive or not negative:
        raise ValueError(
            f"Training data has {positive} congested and {negative} clear samples; "
            "both congestion-ground-truth labels are required. Collect validated baseline "
            "samples with clear and saturated periods, e.g. none/voip_surge or none/bulk_ramp."
        )
    config = load_config()
    output = args.output or config["detectors"]["supervised"]["model_path"]
    train_supervised(samples, output, config["runtime"]["seed"])
    print(f"Saved labelled-run detector to {output} ({len(samples)} samples: "
          f"{positive} congested, {negative} clear; modes={','.join(sorted(str(m) for m in source_modes))})")


def _float(value):
    try: return float(value)
    except (TypeError, ValueError): return 0.0


if __name__ == "__main__":
    main()
