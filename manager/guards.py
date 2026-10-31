"""Fairness and safety gates shared by every decision engine."""
from collections import deque
import math


def jain_index(values):
    positive = [max(0.0, float(value)) for value in values]
    if not positive or sum(x * x for x in positive) == 0:
        return 0.0
    return sum(positive) ** 2 / (len(positive) * sum(x * x for x in positive))


class FairnessGuard:
    def __init__(self, config):
        self.config = config["guards"]["fairness"]
        self.demands = config["sla"]["class_targets_mbps"]

    def evaluate(self, candidate, sample=None):
        """Estimate Jain fairness from observed delivery and proposed bounds.

        A candidate ceiling alone overstates service when a class is already
        receiving less than its demand. Use measured rate as the projection
        baseline, bounded by the proposed HTB floor and ceiling.
        """
        measured = (sample or {}).get("q_mbps", {})
        normalized = []
        for cls in ("voip", "video", "bulk"):
            demand = max(float(self.demands[cls]), 1e-9)
            low = float(candidate[cls]["min_bps"]) / 1e6
            high = float(candidate[cls]["max_bps"]) / 1e6
            observed = max(0.0, float(measured.get(cls, 0.0)))
            projected = min(high, max(low, observed))
            normalized.append(min(1.0, projected / demand))
        score = jain_index(normalized)
        reasons = []
        floor = int(self.config["bulk_floor_bps"])
        if candidate["bulk"]["min_bps"] < floor or candidate["bulk"]["max_bps"] < floor:
            reasons.append("bulk below fairness floor")
        if score < self.config["minimum_jain"]:
            reasons.append(f"Jain {score:.3f} below {self.config['minimum_jain']:.3f}")
        return not reasons, score, reasons

    def repair_bulk_ceiling(self, candidate, capacity_bps, sample=None):
        """Raise bulk's max-rate in configured increments until fairness passes."""
        repaired = {name: dict(rates) for name, rates in candidate.items()}
        step = max(1, int(self.config.get("bulk_recovery_step_bps", 1_000_000)))
        while self.evaluate(repaired, sample)[1] < float(self.config["minimum_jain"]):
            old = int(repaired["bulk"]["max_bps"])
            repaired["bulk"]["max_bps"] = min(int(capacity_bps), old + step)
            if repaired["bulk"]["max_bps"] == old:
                break
        return repaired


class DelayBudgetHysteresis:
    """Enter protection at 80% of any budget; clear after 5 s below 60%."""

    def __init__(self, config):
        policy = config["fiveqi"]
        self.enter_ratio = float(policy["protect_enter_ratio"])
        self.exit_ratio = float(policy["protect_exit_ratio"])
        self.clear_ticks = max(1, round(float(policy["clear_hold_seconds"]) /
                                        float(config["runtime"]["tick_seconds"])))
        self.active = False
        self.calm_ticks = 0

    def update(self, delays, forecasts, budgets):
        ratios = []
        for cls, budget in budgets.items():
            limit = max(float(budget), 1e-9)
            for values in (delays, forecasts or {}):
                value = values.get(cls)
                if value is not None and math.isfinite(float(value)):
                    ratios.append(float(value) / limit)
        if not self.active:
            if any(value >= self.enter_ratio for value in ratios):
                self.active = True
                self.calm_ticks = 0
        elif ratios and all(value < self.exit_ratio for value in ratios):
            self.calm_ticks += 1
            if self.calm_ticks >= self.clear_ticks:
                self.active = False
                self.calm_ticks = 0
        else:
            self.calm_ticks = 0
        return self.active


class SafetyShield:
    def __init__(self, config, enabled=None):
        self.config = config["guards"]["safety"]
        self.enabled = config["guards"]["enabled"] if enabled is None else enabled
        self.changes = deque()
        self.cooldown = 0
        self.rejections = 0
        self.capacity_bps = config["qos"]["link_capacity_bps"]
        self.minimum_dwell_ticks = int(self.config.get("minimum_dwell_ticks", 3))
        self.last_change_tick = None

    def filter(self, candidate, current, static, tick, stale_ticks=0, forecast_mae=0.0):
        if not self.enabled:
            return candidate, False, []
        reasons = []
        while self.changes and tick - self.changes[0] >= self.config["change_window_ticks"]:
            self.changes.popleft()
        if self.cooldown > 0:
            self.cooldown -= 1
            return {k: dict(v) for k, v in current.items()}, True, ["cooldown"]
        if (candidate != current and self.last_change_tick is not None and
                tick - self.last_change_tick < self.minimum_dwell_ticks):
            return {k: dict(v) for k, v in current.items()}, True, ["minimum dwell time"]
        if stale_ticks > self.config.get("stale_after_ticks", 3):
            reasons.append("stale telemetry")
        if any(int(candidate[c]["max_bps"]) < int(candidate[c]["min_bps"]) for c in candidate):
            reasons.append("queue max-rate below min-rate")
        if sum(int(candidate[c]["min_bps"]) for c in candidate) > self.capacity_bps:
            reasons.append("minimum guarantees exceed bottleneck capacity")
        if forecast_mae > self.config["forecast_mae_limit"]:
            reasons.append("forecast MAE limit exceeded")
        if len(self.changes) >= self.config["max_changes_per_window"]:
            reasons.append("policy-change rate limit exceeded")
        if reasons:
            self.rejections += 1
            self.cooldown = self.config["cooldown_ticks"]
            return {k: dict(v) for k, v in static.items()}, True, reasons
        if candidate != current:
            self.changes.append(tick)
            self.last_change_tick = tick
        return candidate, False, []
