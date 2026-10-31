"""Run configured mode x scenario x seed comparisons (Mininet requires Linux/root)."""
import argparse
import itertools
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from manager.config import load_config
from run_research import (CONTROLLER_FREE_MODES, MODE_MAP, _stop_controller, require_root_and_tools,
                          run, start_controller)


def main():
    if "--legacy" in sys.argv:
        legacy_main()
        return
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config")
    config_path = pre.parse_known_args()[0].config
    cfg = load_config(config_path) if config_path else load_config()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="YAML config (may extend config.yaml with base:)")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--seed", type=int, default=cfg["runtime"]["seed"])
    parser.add_argument("--modes", nargs="+", choices=MODE_MAP, default=cfg["experiment"]["default_modes"])
    parser.add_argument("--scenarios", nargs="+", choices=cfg["scenarios"], default=cfg["experiment"]["default_scenarios"])
    parser.add_argument("--output", default=cfg["runtime"]["results_dir"])
    parser.add_argument("--q-table", help="trained JSON Q table for Q-learning evaluation")
    parser.add_argument("--disable-guards", action="store_true", help="ablation: bypass fairness and safety filters")
    parser.add_argument("--resume", action="store_true", help="skip runs whose summary confirms valid telemetry")
    parser.add_argument("--pause", type=float, default=2.0, help="settling time between Mininet runs")
    args = parser.parse_args()
    if args.repeats < 1: parser.error("--repeats must be >= 1")
    if "supervised_rule" in args.modes:
        model_path = Path(cfg["detectors"]["supervised"]["model_path"])
        if not model_path.exists():
            parser.error(
                f"supervised_rule requires a trained model at {model_path}; "
                "first collect reactive samples and run train_detector.py")
    q_modes = {"fused_qlearning", "fused_qlearning_unshielded"}
    q_table_path = args.q_table
    work = list(itertools.product(args.modes, args.scenarios, range(args.repeats)))
    output_root = Path(args.output).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    def completed_validly(mode, scenario, repeat):
        summary_path = (output_root / mode / scenario /
                        f"run_{args.seed + repeat}" / "summary.json")
        try:
            with summary_path.open(encoding="utf-8") as stream:
                summary = json.load(stream)
            if summary.get("telemetry_valid") is not True:
                return False
            if summary.get("throughput_valid") is not True:
                return False
            if summary.get("bulk_throughput_within_capacity") is not True:
                return False
            if float(summary.get("rejection_rate", 1.0)) >= 0.30:
                return False
            if mode not in CONTROLLER_FREE_MODES:
                return (float(summary.get("queue_stats_coverage", 0.0)) >= 0.8 and
                        summary.get("queue_counters_valid") is True and
                        summary.get("queue_video_rate_matches_iperf") is True)
            return True
        except (OSError, ValueError):
            return False

    pending = [(mode, scenario, repeat) for mode, scenario, repeat in work
               if not args.resume or not completed_validly(mode, scenario, repeat)]
    if not pending:
        print("All requested runs already have summary.json; nothing to resume.")
        return
    require_root_and_tools()
    if q_modes.intersection(args.modes) and not q_table_path:
        q_table_path = str(Path(args.output) / "q_table.json")
        q_path = Path(q_table_path)
        if not q_path.exists():
            print(f"Training seeded Q table ({cfg['engines']['qlearning']['episodes']} episodes)...", flush=True)
            subprocess.run([sys.executable, str(ROOT / "train.py"), "--output", q_table_path], check=True)
    total = len(work)
    # Mininet cleanup kills processes named ryu-manager. Clean stale network
    # state before starting the one shared controller for the experiment matrix.
    if cfg["runtime"].get("mn_cleanup", True):
        subprocess.run(["mn", "-c"], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    needs_controller = any(mode not in CONTROLLER_FREE_MODES for mode in args.modes)
    controller_process, controller_log = (start_controller(cfg, output_root / "controller.log", config_path)
        if needs_controller else (None, None))
    try:
        for index, (mode, scenario, repeat) in enumerate(work, 1):
            seed = args.seed + repeat
            output = output_root / mode / scenario / f"run_{seed}"
            if args.resume and completed_validly(mode, scenario, repeat):
                print(f"[{index}/{total}] skipping valid {mode}/{scenario}/run_{seed}", flush=True)
                continue
            print(f"[{index}/{total}] mode={mode} scenario={scenario} seed={seed}", flush=True)
            path = run(mode, scenario, seed, config_path=config_path,
                       output_root=args.output, q_table_path=q_table_path,
                       disable_guards=args.disable_guards, environment_checked=True,
                       controller_ready=needs_controller,
                       controller_port=cfg["runtime"]["controller_port"] if needs_controller else None,
                       manage_cleanup=False)
            print(f"  saved {path}", flush=True)
            if index < total and args.pause:
                time.sleep(args.pause)
    finally:
        _stop_controller(controller_process, controller_log)
        if (cfg["runtime"].get("mn_cleanup", True) and
                (not needs_controller or controller_process is not None)):
            subprocess.run(["mn", "-c"], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("All requested runs finished. Generate aggregates with: python3 analyze.py --results " + args.output)


def legacy_main():
    """Retain the pre-existing scenario.py comparison runner on request."""
    from mininet.log import setLogLevel
    from common import config as legacy_config
    from monitoring.compare import compare
    from scenario import MODES, run as legacy_run
    parser = argparse.ArgumentParser(description="Run the original project comparison modes")
    parser.add_argument("--legacy", action="store_true")
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--t-cong", type=int, default=15)
    parser.add_argument("--t-end", type=int, default=45)
    parser.add_argument("--modes", nargs="+", choices=MODES,
                        default=["none", "static", "rule-polling", "rule-telemetry", "rl-polling", "rl-telemetry"])
    parser.add_argument("--policy", default="results/rl/rl_policy.json")
    args = parser.parse_args()
    setLogLevel("warning")
    run_dirs = []
    for repeat in range(args.repeats):
        for mode in args.modes:
            print(f"legacy run {repeat + 1}/{args.repeats} mode={mode}", flush=True)
            run_dirs.append(legacy_run(mode, args.t_cong, args.t_end, tag=f"r{repeat + 1}",
                policy_path=args.policy, seed=legacy_config.RL["seed"] + repeat, include_probes=True))
            time.sleep(2)
    compare(run_dirs, str(Path(legacy_config.RESULTS_DIR) / "comparison"))


if __name__ == "__main__":
    main()
