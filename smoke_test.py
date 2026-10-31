"""Run one short Mininet episode for each mode (requires the Docker testbed)."""
import argparse

from common import config as cfg
from scenario import MODES, run


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--policy", default="results/rl/rl_policy.json")
    p.add_argument("--duration", type=int, default=8,
                   help="total episode seconds; bulk starts at half time")
    p.add_argument("--modes", nargs="+", choices=MODES,
                   default=["none", "static", "rule-polling", "rule-telemetry", "rl-polling", "rl-telemetry"])
    a = p.parse_args()
    for i, mode in enumerate(a.modes):
        run(mode, max(1, a.duration // 2), a.duration, tag="smoke",
            policy_path=a.policy, seed=cfg.RL["seed"] + i, include_probes=True)


if __name__ == "__main__":
    main()
