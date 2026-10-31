"""Small Gymnasium environment and shared, safety-clamped QoS action mapping."""
import numpy as np
try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError:  # Keep action/reward tests usable outside the pinned Docker image.
    class _Env:
        def reset(self, *, seed=None, options=None):
            return None

    class _Discrete:
        def __init__(self, n): self.n = n

    class _Box:
        def __init__(self, low, high, shape, dtype):
            self.low, self.high, self.shape, self.dtype = low, high, shape, dtype
        def contains(self, value):
            return value.shape == self.shape and bool(np.all(value >= self.low) and np.all(value <= self.high))

    class _Spaces:
        Discrete = _Discrete
        Box = _Box

    class _Gym:
        Env = _Env
    gym, spaces = _Gym(), _Spaces()

from common import config as cfg

BULK_ACTIONS = (0.5, 0.75, 1.0, -0.5, -1.0)  # factors for shrink/hold; positive deltas in Mbps for increase
ACTION_COUNT = 10


def apply_action(action, rates):
    """Return bounded rate dict; invalid actions raise ValueError for caller fallback."""
    if not isinstance(action, (int, np.integer)) or not 0 <= int(action) < ACTION_COUNT:
        raise ValueError("invalid RL action")
    result = dict(rates)
    if action < 5:
        value = BULK_ACTIONS[action]
        if action in (0, 1):
            result["bulk_max"] = max(cfg.ADAPTIVE["bulk_floor"],
                                      int(result["bulk_max"] * value))
        elif action == 2:
            result["bulk_max"] = result["bulk_max"]
        else:
            result["bulk_max"] = min(cfg.STATIC_QOS["queues"][0]["max_rate"],
                                      result["bulk_max"] + int(abs(value) * 1_000_000))
    elif action in (5, 6):
        step = 250_000 if action == 5 else -250_000
        result["voip_min"] = min(cfg.ADAPTIVE["voip_protect_min"], max(
            cfg.STATIC_QOS["queues"][1]["min_rate"], result["voip_min"] + step))
    elif action in (7, 8, 9):
        step = 500_000 if action == 7 else (-500_000 if action == 8 else 0)
        result["video_min"] = min(cfg.ADAPTIVE["video_protect_min"], max(
            cfg.STATIC_QOS["queues"][2]["min_rate"], result["video_min"] + step))
    return result


def shield_action(action, rates, fallback):
    """Apply a valid policy action, otherwise invoke the caller's safe fallback."""
    try:
        return apply_action(action, rates), False
    except (ValueError, TypeError):
        return fallback(), True


def sample_is_stale(age_s, stale_after=None):
    """Shared stale-signal predicate used by the RL rule fallback shield."""
    limit = cfg.TELEMETRY_STALE_S if stale_after is None else stale_after
    return age_s > limit


def policy_action(values):
    """Return the best action from a valid ten-action row, or None if unseen/bad."""
    if not isinstance(values, list) or len(values) != ACTION_COUNT:
        return None
    try:
        if not all(np.isfinite(float(value)) for value in values):
            return None
        if not any(abs(float(value)) > 1e-12 for value in values):
            return None
        return int(max(range(ACTION_COUNT), key=lambda i: float(values[i])))
    except (TypeError, ValueError):
        return None


def state_vector(sample, rates, seconds_since_change, last_action=2):
    """Normalized queue/class QoS features, all rate bounds, action and change age."""
    cap = float(cfg.BOTTLENECK_BW_MBPS)
    queue_use = [sample.get("q_mbps", {}).get(q, 0.0) / cap for q in (1, 2, 0)]
    delay = sample.get("class_delay_ms", {})
    jitter = sample.get("class_jitter_ms", {})
    loss = sample.get("class_loss", {})
    delay = [delay.get(c, sample.get(f"{c}_rtt_ms", 0.0)) for c in ("voip", "video", "bulk")]
    delay = [sample.get(f"{c}_rtt_ms", 0.0) if v is None or np.isnan(v) else v
             for c, v in zip(("voip", "video", "bulk"), delay)]
    d = [0.0 if np.isnan(v) else v / 100.0 for v in delay]
    j = [0.0 if np.isnan(jitter.get(c, np.nan)) else jitter.get(c, 0.0) / 50.0
         for c in ("voip", "video", "bulk")]
    l = [min(1.0, loss.get(c, 0.0) / 100.0) for c in ("voip", "video", "bulk")]
    backlog = min(1.0, sample.get("backlog_bytes", 0) / 100000.0)
    rate = [rates["bulk_min"] / 10e6, rates["bulk_max"] / 10e6,
            rates["voip_min"] / 1e6, rates["voip_max"] / 1e6,
            rates["video_min"] / 6e6, rates["video_max"] / 10e6]
    return np.clip(np.asarray(queue_use + d + j + l + [backlog] + rate +
                              [last_action / max(1, ACTION_COUNT - 1),
                               min(1.0, seconds_since_change / 10.0)], dtype=np.float32), 0, 1)


def reward(sample, action_changed):
    """Weighted reward: video service and VoIP quality, with starvation/churn costs."""
    w = cfg.RL["reward"]
    v = min(1.0, sample.get("q_mbps", {}).get(2, 0.0) / 6.0)
    rtt = sample.get("voip_rtt_ms", 0.0)
    if np.isnan(rtt):
        rtt = 0.0
    jitter = sample.get("class_jitter_ms", {}).get("voip", 0.0)
    if np.isnan(jitter):
        jitter = 0.0
    loss = sample.get("class_loss", {}).get("voip", 0.0)
    bulk = sample.get("q_mbps", {}).get(0, 0.0)
    video_target = cfg.STATIC_QOS["queues"][2]["min_rate"] / 1e6
    video_rate = sample.get("q_mbps", {}).get(2, 0.0)
    return (w["video_throughput"] * v - w["voip_delay"] * min(1.0, rtt / 100.0)
            - w.get("video_stability", 0.0) * int(
                video_rate < w.get("video_stability_ratio", 0.95) * video_target)
            - w["voip_jitter"] * min(1.0, jitter / 50.0)
            - w["voip_loss"] * min(1.0, loss / 100.0)
            - w["delay_violation"] * max(0.0, rtt - cfg.CONGESTION_RTT_MS) / 100.0
            - w["bulk_starvation"] * max(0.0, 1.0 - bulk / 1.0)
            - w["policy_change"] * int(action_changed)
            - w.get("reservation_cost", 0.0) * float(
                sample.get("reservation_cost_fraction", 0.0)))


class QoSBottleneckEnv(gym.Env):
    """Fast surrogate for pretraining; calibrated from observed samples.csv rates."""
    metadata = {"render_modes": []}

    def __init__(self, calibration=None, horizon=120):
        super().__init__()
        self.action_space = spaces.Discrete(ACTION_COUNT)
        self.observation_space = spaces.Box(0.0, 1.0, shape=(21,), dtype=np.float32)
        self.calibration = calibration or {"video": 4.0, "voip_rtt": 10.0, "bulk": 5.0}
        self.horizon = horizon
        self.rng = np.random.default_rng(cfg.RL["seed"])
        self.reset(seed=cfg.RL["seed"])

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        self.i = 0
        self.rates = {"bulk_min": 1_000_000, "bulk_max": 10_000_000,
                      "voip_min": 500_000, "voip_max": 1_000_000,
                      "video_min": 4_000_000, "video_max": 6_000_000}
        self.last_action = 2
        self.since = 1.0
        self.load = float(self.rng.uniform(0.75, 1.0))
        return self._observation(), {"model": "calibrated-surrogate"}

    def _sample(self):
        bm = min(10.0, self.rates["bulk_max"] / 1e6) * self.load
        vm = min(self.rates["video_max"] / 1e6,
                 max(self.calibration.get("video", 4.0), self.rates["video_min"] / 1e6))
        total = min(10.0, bm + vm + 0.1)
        rtt = max(5.0, self.calibration.get("voip_rtt", 10.0) + max(0.0, total - 8.5) * 5)
        noise = float(self.rng.normal(0, 0.15))
        reserved = sum(self.rates[key] for key in
                       ("bulk_min", "voip_min", "video_min"))
        return {"total_mbps": total, "voip_rtt_ms": rtt,
                "q_mbps": {0: max(0.0, bm + noise), 1: 0.1, 2: min(vm, max(0, 9.9-bm))},
                "class_jitter_ms": {"voip": max(0.0, (rtt-10)/5)},
                "class_loss": {"voip": max(0.0, total-9.5) * 5},
                "backlog_bytes": max(0, (total-8.0)*10000),
                "reservation_cost_fraction": reserved /
                    float(cfg.BOTTLENECK_BW_MBPS * 1_000_000)}

    def _observation(self):
        return state_vector(self._sample(), self.rates, self.since, self.last_action)

    def step(self, action):
        before = self.rates
        self.rates = apply_action(action, self.rates)
        changed = self.rates != before
        self.since = 0.0 if changed else self.since + 0.2
        self.last_action = int(action)
        self.i += 1
        sample = self._sample()
        obs = state_vector(sample, self.rates, self.since, self.last_action)
        return obs, float(reward(sample, changed)), self.i >= self.horizon, False, {"sample": sample}
