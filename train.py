"""Seeded tabular Q-learning training on the lightweight synthetic environment."""
import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from manager.config import load_config
from manager.engines import QLearningEngine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--output", default="results/q_table.json")
    args = parser.parse_args()
    config = load_config()
    episodes = args.episodes or config["engines"]["qlearning"]["episodes"]
    seed = args.seed if args.seed is not None else config["runtime"]["seed"]
    rng = random.Random(seed)
    engine = QLearningEngine(config, training=True, seed=seed)
    started = time.perf_counter()
    for _ in range(episodes):
        rates = {k: dict(v) for k, v in config["qos"]["static_rates"].items()}
        bulk_active = False
        for tick in range(60):
            if tick % 15 == 0:
                bulk_active = rng.random() < .7
            demand = rng.uniform(7.0, 10.0) if bulk_active else rng.uniform(.1, .5)
            bulk = min(demand, rates["bulk"]["max_bps"] / 1e6)
            used = .1 + 4.0 + bulk
            utilization = used / config["network"]["bandwidth_mbps"]
            rtt = 10.0 + max(0.0, utilization - .85) * 45.0 + rng.uniform(-1.0, 1.0)
            shares = [.1 / .1, min(1.0, 4.0 / 4.0), min(1.0, bulk / max(demand, .1))]
            jain = sum(shares) ** 2 / (len(shares) * sum(x*x for x in shares))
            sample = {"utilization": utilization, "voip_rtt_ms": rtt,
                      "bulk_mbps": bulk, "jain_index": jain}
            severity = 2 if sample["utilization"] > .85 or sample["voip_rtt_ms"] > config["sla"]["voip_rtt_ms"] else 0
            rates, _ = engine.decide(sample, severity, rates)
        engine.finish_episode()
    elapsed = time.perf_counter() - started
    serialized = {"|".join(map(str, state)): values for state, values in engine.q.items()}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"seed": seed, "episodes": episodes, "training_wall_seconds": elapsed,
                                  "q_table": serialized}, indent=2), encoding="utf-8")
    print(f"Trained {episodes} episodes in {elapsed:.3f}s; saved {output}")


if __name__ == "__main__":
    main()
