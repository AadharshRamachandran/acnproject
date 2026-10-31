"""Seeded tabular Q-learning pretraining in the fast calibrated surrogate."""
import argparse
import csv
import json
import os
import random
import sys
import math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import config as cfg
from controller.rl_env import QoSBottleneckEnv


def calibration_from_csv(paths):
    values = {"video": [], "voip_rtt": []}
    for path in paths:
        try:
            meta_path = os.path.join(os.path.dirname(path), "run_meta.json")
            t_limit = None
            if os.path.exists(meta_path):
                with open(meta_path) as meta_file:
                    meta = json.load(meta_file)
                t_limit = meta.get("t_cong_sample", meta.get("t_cong"))
            with open(path, newline="") as f:
                for row in csv.DictReader(f):
                    if t_limit is not None and float(row.get("t", 0)) >= float(t_limit):
                        continue
                    video = float(row.get("q2_mbps", 0))
                    rtt = float(row.get("voip_rtt_ms", 0))
                    if math.isfinite(video) and video > 0.5:
                        values["video"].append(video)
                    if math.isfinite(rtt) and 0 < rtt <= cfg.CONGESTION_RTT_MS:
                        values["voip_rtt"].append(rtt)
        except (OSError, ValueError):
            continue
    return {key: float(np.mean(v)) if v else default
            for key, v, default in (("video", values["video"], 4.0),
                                    ("voip_rtt", values["voip_rtt"], 10.0))}


def discrete_state(obs):
    # Compact tabular abstraction: worst queue use, VoIP quality, backlog,
    # bulk rate, last action, and change age. The Gym observation retains all 21 features.
    values = (max(obs[0:3]), obs[3], obs[6], obs[9], obs[12], obs[14], obs[19], obs[20])
    return tuple(int(min(4, max(0, x * 5))) for x in values)


def train(output, samples=(), episodes=None, seed=None, resume_policy=None):
    seed = cfg.RL["seed"] if seed is None else seed
    random.seed(seed)
    np.random.seed(seed)
    env = QoSBottleneckEnv(calibration_from_csv(samples), cfg.RL["surrogate_steps_per_episode"])
    q = {}
    if resume_policy:
        with open(resume_policy) as f:
            q = json.load(f).get("q", {})
    returns = []
    eps = 0.10 if resume_policy else 0.25
    with open(os.path.join(output, "rl_training.csv"), "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["episode", "return", "epsilon"])
        for ep in range(episodes or cfg.RL["q_learning_episodes"]):
            obs, _ = env.reset(seed=seed + ep)
            total = 0.0
            done = False
            while not done:
                state = discrete_state(obs)
                row = q.setdefault("|".join(map(str, state)), [0.0] * env.action_space.n)
                action = random.randrange(env.action_space.n) if random.random() < eps else int(np.argmax(row))
                nxt, r, done, _, _ = env.step(action)
                ns = "|".join(map(str, discrete_state(nxt)))
                future = q.setdefault(ns, [0.0] * env.action_space.n)
                row[action] += 0.15 * (r + 0.9 * max(future) * (not done) - row[action])
                obs, total = nxt, total + r
            eps = max(0.03, eps * 0.995)
            returns.append(total)
            writer.writerow([ep + 1, total, eps])
    with open(os.path.join(output, "rl_policy.json"), "w") as f:
        json.dump({"seed": seed, "calibration": env.calibration,
                   "algorithm": "tabular-q-learning-surrogate", "q": q}, f, indent=2)
    window = max(1, min(25, len(returns)))
    smooth = np.convolve(returns, np.ones(window) / window, mode="valid")
    plt.figure(figsize=(8, 4))
    plt.plot(range(1, len(returns) + 1), returns, alpha=0.25, label="episode return")
    plt.plot(range(window, len(returns) + 1), smooth, label=f"{window}-episode mean")
    plt.xlabel("Episode")
    plt.ylabel("Surrogate reward")
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output, "rl_training.png"), dpi=120)
    plt.close()
    return q


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--samples", nargs="*", default=[])
    p.add_argument("--output", default="results/rl")
    p.add_argument("--episodes", type=int, default=None)
    p.add_argument("--seed", type=int, default=cfg.RL["seed"])
    p.add_argument("--resume-policy", default=None,
                   help="continue a Q table after recalibrating the surrogate from new samples")
    a = p.parse_args()
    os.makedirs(a.output, exist_ok=True)
    train(a.output, a.samples, a.episodes, a.seed, a.resume_policy)
    print(f"Saved seeded surrogate policy to {a.output}/rl_policy.json")
