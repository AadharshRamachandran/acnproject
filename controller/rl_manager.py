"""Runtime Q-table policy with stale-data and invalid-action rule fallback."""
import csv
import json
import os
import threading
import time

from common import config as cfg
from controller import qos_setup
from controller.adaptive_manager import AdaptiveQoSManager
from controller.rl_env import policy_action, sample_is_stale, shield_action, state_vector


class RLQoSManager:
    def __init__(self, port, collector, run_dir, policy_path):
        self.port, self.collector = port, collector
        self.path = os.path.join(run_dir, "decisions.csv")
        self.policy = json.load(open(policy_path))
        self.q = self.policy["q"]
        q = cfg.STATIC_QOS["queues"]
        self.rates = {"bulk_min": q[0]["min_rate"], "bulk_max": q[0]["max_rate"],
                      "voip_min": q[1]["min_rate"], "voip_max": q[1]["max_rate"],
                      "video_min": q[2]["min_rate"], "video_max": q[2]["max_rate"]}
        self.fallback = AdaptiveQoSManager(port, collector, run_dir)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._last_sample_t = None
        self._last_change = time.monotonic()
        self._last_received = time.monotonic()
        self._was_stale = False
        self._last_action = 2

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=5)

    def _loop(self):
        with open(self.path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t", "controller", "action", "bulk_max_rate", "voip_min_rate",
                        "video_min_rate", "reason"])
            while not self._stop.is_set():
                sample = self.collector.latest
                fresh = sample and sample.get("t") != self._last_sample_t
                if fresh:
                    self._last_sample_t = sample["t"]
                    self._last_received = time.monotonic()
                stale = sample and sample_is_stale(time.monotonic() - self._last_received)
                if sample and (fresh or (stale and not self._was_stale)):
                    self._was_stale = bool(stale)
                    if stale:
                        congested, reason = self.fallback.detector.update(sample)
                        action = self.fallback._decide(congested)
                        self.rates.update({"bulk_max": self.fallback.bulk_max,
                                           "voip_min": self.fallback.voip_min,
                                           "video_min": self.fallback.video_min})
                        controller = "rule-fallback"
                    else:
                        self._was_stale = False
                        state = self._discrete(state_vector(sample, self.rates,
                                          time.monotonic() - self._last_change, self._last_action))
                        values = self.q.get("|".join(map(str, state)))
                        proposed = policy_action(values)
                        if proposed is None:
                            proposed = -1  # shield unseen states into the rule fallback
                        def fallback_action():
                            congested, reason = self.fallback.detector.update(sample)
                            self.fallback._decide(congested)
                            self.rates.update({"bulk_max": self.fallback.bulk_max,
                                               "voip_min": self.fallback.voip_min,
                                               "video_min": self.fallback.video_min})
                            return dict(self.rates)
                        updated, used_fallback = shield_action(proposed, self.rates, fallback_action)
                        controller = "rule-fallback-invalid-action" if used_fallback else "rl"
                        reason = "invalid policy action" if used_fallback else "policy"
                        action = str(proposed) if not used_fallback else "rule-fallback"
                        if not used_fallback:
                            if updated != self.rates:
                                self._apply(updated)
                                self._last_change = time.monotonic()
                            self.rates = updated
                            self._last_action = proposed
                    w.writerow([sample["t"], controller, action, self.rates["bulk_max"],
                                self.rates["voip_min"], self.rates["video_min"], reason])
                    f.flush()
                self._stop.wait(cfg.RL["decision_interval_s"])

    @staticmethod
    def _discrete(obs):
        values = (max(obs[0:3]), obs[3], obs[6], obs[9], obs[12], obs[14], obs[19], obs[20])
        return tuple(int(min(4, max(0, x * 5))) for x in
                     values)

    def _apply(self, rates):
        qos_setup.update_queue(self.port, 0, min_rate=rates["bulk_min"], max_rate=rates["bulk_max"])
        qos_setup.update_queue(self.port, 1, min_rate=rates["voip_min"], max_rate=rates["voip_max"])
        qos_setup.update_queue(self.port, 2, min_rate=rates["video_min"], max_rate=rates["video_max"])
