import unittest
import pandas as pd

from common import config as cfg
from controller.rl_env import ACTION_COUNT, QoSBottleneckEnv, apply_action, policy_action, reward, sample_is_stale, shield_action
from monitoring.metrics_collector import QERR_RE, QSTAT_RE
from monitoring.analyze import congestion_flag_time, policy_reaction_time


class ActionMappingTests(unittest.TestCase):
    def setUp(self):
        self.rates = {"bulk_min": 1_000_000, "bulk_max": 10_000_000,
                      "voip_min": 500_000, "voip_max": 1_000_000,
                      "video_min": 4_000_000, "video_max": 6_000_000}

    def test_bulk_actions_clamp_to_baseline_bounds(self):
        self.assertEqual(apply_action(0, self.rates)["bulk_max"], 5_000_000)
        floor = apply_action(0, dict(self.rates, bulk_max=600_000))["bulk_max"]
        self.assertEqual(floor, cfg.ADAPTIVE["bulk_floor"])
        self.assertEqual(apply_action(4, self.rates)["bulk_max"], 10_000_000)

    def test_guarantees_are_clamped(self):
        self.assertEqual(apply_action(5, self.rates)["voip_min"], 750_000)
        self.assertEqual(apply_action(7, self.rates)["video_min"], 4_500_000)
        self.assertEqual(apply_action(8, dict(self.rates, video_min=4_000_000))["video_min"], 4_000_000)

    def test_invalid_action_rejected(self):
        with self.assertRaises(ValueError):
            apply_action(ACTION_COUNT, self.rates)

    def test_invalid_action_uses_safety_fallback(self):
        safe = dict(self.rates, bulk_max=5_000_000)
        selected, fallback = shield_action(ACTION_COUNT, self.rates, lambda: safe)
        self.assertTrue(fallback)
        self.assertEqual(selected["bulk_max"], 5_000_000)

    def test_stale_signal_switches_to_fallback_condition(self):
        self.assertFalse(sample_is_stale(0.2, stale_after=1.0))
        self.assertTrue(sample_is_stale(1.1, stale_after=1.0))

    def test_unseen_or_malformed_policy_row_is_rejected(self):
        self.assertIsNone(policy_action(None))
        self.assertIsNone(policy_action([0.0]))
        self.assertIsNone(policy_action([float("nan")] * ACTION_COUNT))
        self.assertIsNone(policy_action([0.0] * ACTION_COUNT))
        self.assertEqual(policy_action([0.0, 1.0] + [0.0] * 8), 1)


class TelemetryAndRewardTests(unittest.TestCase):
    def test_queue_stats_parser_accepts_ovs_formats(self):
        self.assertEqual(QSTAT_RE.findall("queue 0: bytes=123\nqueue 2: tx_bytes=456"),
                         [("0", "123"), ("2", "456")])
        self.assertEqual(QERR_RE.findall("queue 1: bytes=400 packets=4 errors=2"), [("1", "2")])

    def test_reward_penalizes_voip_delay_and_churn(self):
        good = {"voip_rtt_ms": 10, "q_mbps": {0: 2, 1: .1, 2: 5},
                "class_jitter_ms": {"voip": 1}, "class_loss": {"voip": 0}}
        bad = dict(good, voip_rtt_ms=80)
        self.assertGreater(reward(good, False), reward(bad, False))
        self.assertGreater(reward(good, False), reward(good, True))

    def test_gym_environment_contract(self):
        env = QoSBottleneckEnv(horizon=2)
        obs, info = env.reset(seed=3)
        self.assertTrue(env.observation_space.contains(obs))
        self.assertEqual(info["model"], "calibrated-surrogate")
        self.assertEqual(len(env.step(2)), 5)

    def test_detection_and_reaction_latency(self):
        samples = pd.DataFrame({"t": [4.0, 4.1, 4.2], "total_mbps": [5.0, 9.0, 9.5],
                                "voip_rtt_ms": [10.0, 10.0, 25.0]})
        decisions = pd.DataFrame({"t": [4.0, 4.2], "bulk_max_rate": [10, 5],
                                  "voip_min_rate": [0.5, 1.0], "video_min_rate": [4, 5]})
        self.assertEqual(congestion_flag_time(samples, 4.0), 4.1)
        self.assertAlmostEqual(policy_reaction_time(samples, decisions, 4.0), 0.1)


if __name__ == "__main__":
    unittest.main()
