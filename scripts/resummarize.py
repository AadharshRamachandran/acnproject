"""Rebuild summary.json of finished runs from their saved files, without re-running.

Use after a fix to iperf3 parsing or summary metrics. Timing fields that only
the live run knows (detection/actuation/recovery times, forecast alert times,
forecast MAE, false-alarm costs) are carried over from the old summary.

Usage: python3 scripts/resummarize.py RUN_DIR [RUN_DIR ...]
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_research as rr

CARRIED = ("forecast_prediction_lead_by_class_s", "forecast_prediction_lead_s")


def resummarize(out):
    out = Path(out).resolve()
    snapshot = json.loads((out / "config.json").read_text(encoding="utf-8"))
    config, mode = snapshot["config"], snapshot["run"]["mode"]
    scenario_cfg = config["scenarios"][out.parent.name]
    old = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    streams = rr._scenario_streams(config, scenario_cfg)
    bulk_sessions = [(out / "bulk_1.json", int(scenario_cfg.get("bulk_start", 0)))]
    bulk_sessions += [(out / s["file"], s["start"]) for s in streams if s["cls"] == "bulk"]
    voip_sessions = [(out / s["file"], s["start"], s["stop"] - s["start"])
                     for s in streams if s["cls"] == "voip"]
    video_sessions = [(out / s["file"], s["start"], s["stop"] - s["start"])
                      for s in streams if s["cls"] == "video"]
    rr._apply_iperf_sample_metrics(out / "samples.csv", out, mode, bulk_sessions,
                                   voip_sessions=voip_sessions, video_sessions=video_sessions)
    rr._write_summary(out, samples_path=out / "samples.csv", decisions_path=out / "decisions.csv",
                      starvation=old.get("bulk_starvation_s", 0.0),
                      false_alarm_costs=old.get("false_alarm_events", []),
                      detection_time=old.get("detection_latency_s"),
                      actuation_time=old.get("time_to_act_s"),
                      recovery_time=old.get("time_to_recover_s"),
                      forecast=SimpleNamespace(mae=old.get("forecast_mae", 0.0)),
                      config=config, prediction_lead=old.get("prediction_lead_s"),
                      forecast_alert_at=None, mode=mode)
    new = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    new.update({key: old[key] for key in CARRIED if key in old})
    (out / "summary.json").write_text(json.dumps(new, indent=2), encoding="utf-8")
    return new


if __name__ == "__main__":
    for run_dir in sys.argv[1:]:
        summary = resummarize(run_dir)
        print(run_dir, "telemetry_valid", summary["telemetry_valid"],
              "throughput_valid", summary["throughput_valid"])
