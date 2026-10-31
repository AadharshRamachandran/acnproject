"""Online EWMA and Holt forecasts for utilization and per-class delay."""
from collections import deque
from dataclasses import dataclass, field
import math

from manager.budgets import CLASSES, class_delay_budgets_ms


@dataclass
class Forecast:
    utilization: float
    voip_rtt_ms: float
    mae: float
    class_delay_ms: dict = field(default_factory=dict)


class _OnlineForecaster:
    def __init__(self, config):
        self.horizon = max(1, round(float(config["forecaster"]["horizon_seconds"]) /
                                   float(config["runtime"]["tick_seconds"])))
        self.alpha = float(config["forecaster"]["alpha"])
        self.beta = float(config["forecaster"]["beta"])
        self.scales = {
            "utilization": 1.0,
            "voip_rtt_ms": max(float(config["sla"]["voip_rtt_ms"]), 1e-9),
        }
        self.scales.update({f"delay_{cls}_ms": max(value, 1e-9)
                            for cls, value in class_delay_budgets_ms(config).items()})
        self.level, self.trend = {}, {}
        self.errors = {key: [] for key in self.scales}
        self.pending = {key: deque() for key in self.scales}
        self.tick = 0

    def _step(self, key, value):
        if not math.isfinite(value):
            if key not in self.level:
                return 0.0
            return max(0.0, self.level[key] + self.horizon * self.trend.get(key, 0.0))

        if key not in self.level:
            self.level[key], self.trend[key] = value, 0.0
        else:
            old_level = self.level[key]
            old_trend = self.trend.get(key, 0.0)
            new_level = self.alpha * value + (1 - self.alpha) * (
                old_level + old_trend)
            self.trend[key] = self._update_trend(
                new_level, old_level, old_trend)
            self.level[key] = new_level

        while self.pending[key] and self.pending[key][0][0] <= self.tick:
            _, old_prediction = self.pending[key].popleft()
            self.errors[key].append(abs(value - old_prediction))
        self.errors[key] = self.errors[key][-100:]
        # Incorporate this tick's observation first, then forecast from the
        # updated state. The emitted value is therefore genuinely `horizon`
        # ticks ahead of the current sample, not one tick stale.
        prediction = self._predict(self.level[key], self.trend.get(key, 0.0))
        self.pending[key].append((self.tick + self.horizon, prediction))
        return max(0.0, prediction)

    def _predict(self, level, trend):
        raise NotImplementedError

    def _update_trend(self, new_level, old_level, old_trend):
        return 0.0

    def update(self, sample):
        self.tick += 1
        utilization = self._step("utilization", float(sample.get("utilization", 0.0)))
        rtt = self._step("voip_rtt_ms", float(sample.get("voip_rtt_ms", 0.0)))
        delays = sample.get("class_delay_ms", {}) or {}
        forecast_delays = {}
        for cls in CLASSES:
            value = delays.get(cls)
            # Preserve the original API for callers that only supply ping RTT.
            if value is None and cls == "voip":
                value = float(sample.get("voip_rtt_ms", 0.0)) / 2.0
            elif value is None:
                value = float("nan")
            forecast_delays[cls] = self._step(f"delay_{cls}_ms", float(value))
        return Forecast(utilization, rtt, self.mae, forecast_delays)

    @property
    def mae(self):
        """Maximum rolling MAE after normalizing each signal by its budget/scale."""
        normalized = [sum(values) / len(values) / self.scales[key]
                      for key, values in self.errors.items() if values]
        return max(normalized) if normalized else 0.0

    @property
    def ready(self):
        """Only trust forecasts after a full horizon has been scored."""
        required = ["utilization"] + [f"delay_{cls}_ms" for cls in CLASSES]
        return all(self.errors[key] for key in required)


class HoltForecaster(_OnlineForecaster):
    """Holt double exponential smoothing with a configurable multi-tick horizon."""

    def _predict(self, level, trend):
        return level + self.horizon * trend

    def _update_trend(self, new_level, old_level, old_trend):
        return self.beta * (new_level - old_level) + (1 - self.beta) * old_trend


class EWMAForecaster(_OnlineForecaster):
    """EWMA baseline: project the smoothed level forward with zero trend."""

    def _predict(self, level, trend):
        return level
