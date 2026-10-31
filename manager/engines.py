"""Rate-decision engines with a shared decide interface."""
from collections import defaultdict
import random
import math

from manager.budgets import class_delay_budgets_ms


class RuleAIMD:
    def __init__(self, config):
        self.cfg = config["engines"]["rule_aimd"]
        self.qos = config["qos"]

    def decide(self, sample, severity, rates, **_):
        new = {name: dict(value) for name, value in rates.items()}
        if severity >= 2:
            bulk = self.qos["queues"]["bulk"]
            new["bulk"]["max_bps"] = max(bulk["floor_bps"], rates["bulk"]["min_bps"], int(rates["bulk"]["max_bps"] * self.cfg["bulk_shrink"]))
            new["voip"]["min_bps"] = self.cfg["voip_min_bps"]
            new["video"]["min_bps"] = self.cfg["video_min_bps"]
            reason = "congested: multiplicative bulk decrease and protected guarantees"
        elif severity == 0 and rates["bulk"]["max_bps"] < self.qos["queues"]["bulk"]["max_bps"]:
            new["bulk"]["max_bps"] = min(self.qos["queues"]["bulk"]["max_bps"], rates["bulk"]["max_bps"] + self.cfg["bulk_restore_bps"])
            new["voip"]["min_bps"] = self.qos["static_rates"]["voip"]["min_bps"]
            new["video"]["min_bps"] = self.qos["static_rates"]["video"]["min_bps"]
            reason = "clear: additive bulk restore"
        else:
            reason = "hold"
        return new, reason


class PIController:
    def __init__(self, config):
        self.cfg = config["engines"]["pi"]
        self.qos = config["qos"]
        self.sla = config["sla"]
        self.delay_budgets = class_delay_budgets_ms(config)
        self.enter_ratio = float(config["fiveqi"]["protect_enter_ratio"])
        self.base_rtt = None
        self.integral = 0.0
        self.last_change = -10**9
        self.tick = 0

    def _need(self, sample, forecast=None):
        current_delays = sample.get("class_delay_ms", {}) or {}
        predicted_delays = getattr(forecast, "class_delay_ms", {}) if forecast else {}
        if current_delays:
            delay_needs = [max(0.0, float(current_delays.get(cls, 0.0)) -
                               self.enter_ratio * budget) / budget
                           for cls, budget in self.delay_budgets.items()]
            forecast_needs = [max(0.0, float(predicted_delays[cls]) -
                                  self.enter_ratio * budget) / budget
                              for cls, budget in self.delay_budgets.items()
                              if cls in predicted_delays]
            video = float(sample.get("q_mbps", {}).get("video", 0.0))
            video_target = float(self.sla["video_min_mbps"])
            video_need = max(0.0, (video_target - video) / video_target) if video > 0.1 else 0.0
            need = max(delay_needs + forecast_needs + [video_need])
            # Keep the PI output in its protective range while the shared
            # hysteresis is active. Otherwise it would begin restoring the
            # bulk ceiling as soon as signals fell below the 80% entry point,
            # bypassing the configured 60% / 5-second recovery condition.
            if sample.get("delay_protect_active"):
                need = max(need, 1.0 - self.enter_ratio)
            return need

        # Backward-compatible path for older callers with only VoIP ping RTT.
        rtt = float(sample.get("voip_rtt_ms", float("nan")))
        if math.isfinite(rtt):
            self.base_rtt = rtt if self.base_rtt is None else min(self.base_rtt, rtt)
        target = float(self.cfg["voip_queue_target_ms"])
        voip_need = (max(0.0, rtt - self.base_rtt - target) / target
                     if self.base_rtt is not None and math.isfinite(rtt) else 0.0)
        video = float(sample.get("q_mbps", {}).get("video", 0.0))
        video_target = float(self.sla["class_targets_mbps"]["video"])
        video_need = max(0.0, (video_target - video) / video_target) if video > 0.1 else 0.0
        forecast_need = 0.0
        if forecast is not None and self.base_rtt is not None:
            future_rtt = float(forecast.voip_rtt_ms)
            if math.isfinite(future_rtt):
                forecast_need = max(0.0, future_rtt - self.base_rtt - target) / target
        return max(voip_need, video_need, forecast_need)

    def decide(self, sample, severity, rates, forecast=None, **_):
        self.tick += 1
        need = self._need(sample, forecast=forecast)
        self.integral = min(float(self.cfg["integral_max"]),
                            float(self.cfg["leak"]) * self.integral + need)
        u = min(1.0, float(self.cfg["kp"]) * need + float(self.cfg["ki"]) * self.integral)
        if self.tick - self.last_change < int(self.cfg["dwell_ticks"]):
            return rates, "PI dwell"

        new = {name: dict(value) for name, value in rates.items()}
        queues = self.qos["queues"]
        bulk = queues["bulk"]
        bulk_hi = int(bulk["max_bps"])
        bulk_lo = max(int(bulk["floor_bps"]), int(rates["bulk"]["min_bps"]))
        new["bulk"]["max_bps"] = max(int(new["bulk"]["min_bps"]),
                                       int(bulk_hi - u * (bulk_hi - bulk_lo)))
        for cls in ("voip", "video"):
            base = int(self.qos["static_rates"][cls]["max_bps"])
            ceiling = int(self.qos["link_capacity_bps"])
            new[cls]["max_bps"] = max(int(new[cls]["min_bps"]), min(ceiling, int(base + u * (ceiling - base))))
        changed = new != rates
        if changed:
            self.last_change = self.tick
        return new, f"PI u={u:.2f}" if changed else "PI hold"


class CostAwarePIController:
    """Forecasted PI control with QoS floors and minimum reservation cost.

    The controller uses demand-level guarantees while the link is calm. When
    measured or forecast delay enters the configured protection region, it
    temporarily raises guarantees for VoIP and video. If capacity steps make
    the preferred guarantees infeasible, it preserves the bulk floor and VoIP
    first, then assigns the remaining capacity to video.
    """

    def __init__(self, config):
        self.pi = PIController(config)
        self.config = config
        self.budgets = class_delay_budgets_ms(config)
        self.cost = config["cost"]

    def decide(self, sample, severity, rates, forecast=None, **kwargs):
        candidate, reason = self.pi.decide(
            sample, severity, rates, forecast=forecast, **kwargs)
        candidate = {name: dict(value) for name, value in candidate.items()}
        predicted = getattr(forecast, "class_delay_ms", {}) if forecast else {}
        enter_ratio = float(self.config["fiveqi"]["protect_enter_ratio"])
        current_delay = sample.get("class_delay_ms", {}) or {}
        video_target = float(self.config["sla"]["class_targets_mbps"]["video"])
        stable_video_target = video_target * float(
            self.cost.get("video_stability_target_fraction", 0.95))
        video_rate = float(sample.get("q_mbps", {}).get("video", 0.0))
        video_risk = max(0.0, stable_video_target - video_rate) / max(
            stable_video_target, 1e-9)
        video_risk_active = (bool(sample.get("bulk_active")) and
                             bool(sample.get("queue_stats_received", True)) and
                             video_risk > 0.0)
        protect = (bool(sample.get("delay_protect_active")) or severity >= 2 or
                   video_risk_active or
                   any(float(current_delay.get(cls, 0.0)) >= budget
                       for cls, budget in self.budgets.items()) or
                   any(float(predicted.get(cls, 0.0)) >= enter_ratio * budget
                       for cls, budget in self.budgets.items()))

        preferred = self.cost["protected_min_bps" if protect else "reservation_floor_bps"]
        capacity = int(self.config["qos"]["link_capacity_bps"])
        bulk_floor = int(self.config["guards"]["fairness"]["bulk_floor_bps"])
        requested = {cls: int(preferred[cls]) for cls in ("voip", "video", "bulk")}
        requested["bulk"] = max(requested["bulk"], bulk_floor)

        # Keep the hard bulk floor, then prioritize VoIP and video guarantees.
        allocated = {"bulk": min(requested["bulk"], capacity)}
        remaining = max(0, capacity - allocated["bulk"])
        for cls in ("voip", "video"):
            allocated[cls] = min(requested[cls], remaining)
            remaining -= allocated[cls]

        for cls in ("voip", "video", "bulk"):
            candidate[cls]["min_bps"] = allocated[cls]
            candidate[cls]["max_bps"] = max(candidate[cls]["max_bps"], allocated[cls])
        if video_risk_active:
            shrink = float(self.cost.get("video_bulk_shrink", 0.50)) * min(1.0, video_risk)
            candidate["bulk"]["max_bps"] = max(
                allocated["bulk"],
                int(candidate["bulk"]["max_bps"] * (1.0 - shrink)))
        reservation = sum(allocated.values()) / max(capacity, 1)
        return candidate, (f"cost-aware PI u; protect={int(protect)} "
                           f"video_risk={video_risk:.3f} reservation={reservation:.3f}")


class QLearningEngine:
    """Small tabular Q learner; deployment evaluation uses epsilon zero."""
    ACTIONS = ("bulk_down", "bulk_up", "voip_up", "video_up", "noop")

    def __init__(self, config, q_table=None, training=False, seed=None):
        self.cfg = config["engines"]["qlearning"]
        self.weights = config["engines"]["reward"]
        self.qos = config["qos"]
        self.sla = config["sla"]
        self.bulk_floor_mbps = config["guards"]["fairness"]["bulk_floor_bps"] / 1e6
        self.q = defaultdict(lambda: [0.0] * len(self.ACTIONS), q_table or {})
        self.training = training
        self.epsilon = self.cfg["epsilon"] if training else self.cfg["eval_epsilon"]
        self.rng = random.Random(config["runtime"]["seed"] if seed is None else seed)
        self.previous = None

    def state(self, sample, severity):
        utilization, rtt = float(sample.get("utilization", 0.0)), float(sample.get("voip_rtt_ms", 0.0))
        utilization = utilization if math.isfinite(utilization) else 0.0
        rtt = rtt if math.isfinite(rtt) else 0.0
        return (max(0, min(4, int(utilization * 5))),
                max(0, min(4, int(rtt / self.sla["voip_rtt_ms"] * 2.5))),
                int(severity))

    def decide(self, sample, severity, rates, **_):
        state = self.state(sample, severity)
        values = self.q[state]
        action = (self.rng.randrange(len(self.ACTIONS))
                  if self.training and self.rng.random() < self.epsilon
                  else max(range(len(values)), key=values.__getitem__))
        candidate = {name: dict(value) for name, value in rates.items()}
        if action == 0:
            candidate["bulk"]["max_bps"] = max(rates["bulk"]["min_bps"], self.qos["queues"]["bulk"]["floor_bps"], rates["bulk"]["max_bps"] - self.cfg["bulk_step_bps"])
        elif action == 1:
            candidate["bulk"]["max_bps"] = min(self.qos["queues"]["bulk"]["max_bps"], rates["bulk"]["max_bps"] + self.cfg["bulk_step_bps"])
        elif action == 2:
            candidate["voip"]["min_bps"] = min(self.qos["queues"]["voip"]["max_bps"], rates["voip"]["min_bps"] + self.cfg["voip_step_bps"])
        elif action == 3:
            candidate["video"]["min_bps"] = min(self.qos["queues"]["video"]["max_bps"], rates["video"]["min_bps"] + self.cfg["video_step_bps"])
        if self.training and self.previous:
            old_state, old_action, old_changed = self.previous
            reward = self.reward(sample, old_changed)
            target = reward + self.cfg["gamma"] * max(self.q[state])
            row = self.q[old_state]
            row[old_action] += self.cfg["alpha"] * (target - row[old_action])
        self.previous = (state, action, candidate != rates)
        return candidate, self.ACTIONS[action]

    def reward(self, sample, changed):
        w = self.weights
        voip_rtt = float(sample.get("voip_rtt_ms", 0.0))
        if not math.isfinite(voip_rtt):
            voip_rtt = float(self.sla["voip_rtt_ms"])
        video_rate = float(sample.get("q_mbps", {}).get("video", 0.0))
        video_target = float(self.sla["class_targets_mbps"]["video"])
        return (-w["sla_violation"] * int(voip_rtt > self.sla["voip_rtt_ms"])
                -w.get("voip_delay", 0.0) * min(1.0, max(0.0, voip_rtt) /
                                                max(float(self.sla["voip_rtt_ms"]), 1e-9))
                -w.get("video_throughput", 0.0) *
                    (1.0 - min(1.0, max(0.0, video_rate) / max(video_target, 1e-9)))
                -w.get("video_instability", 0.0) *
                    int(video_rate < float(w.get("video_stability_ratio", 0.95)) *
                        video_target)
                -w["policy_change"] * int(changed)
                +w["fairness"] * sample.get("jain_index", 1.0)
                -w["bulk_starvation"] * int(sample.get("bulk_mbps", 1.0) < self.bulk_floor_mbps)
                -w.get("reservation_cost", 0.0) * float(
                    sample.get("reservation_cost_fraction", 0.0)))

    def finish_episode(self):
        self.epsilon = max(self.cfg["epsilon_min"], self.epsilon * self.cfg["epsilon_decay"])
        self.previous = None

    @staticmethod
    def read_q_table(path):
        """Load the JSON artifact written by train.py into tuple state keys."""
        import json
        from pathlib import Path
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return {tuple(int(part) for part in key.split("|")): value
                for key, value in data.get("q_table", {}).items()}


def _copy_rates(rates):
    return {name: dict(value) for name, value in rates.items()}


class ReactiveController:
    """Rule-based reactive baseline: protect while the threshold detector fires.

    While utilisation is above 85 % or the VoIP RTT above 20 ms (severity 2 from
    ThresholdDetector), apply the VoIP/video PROTECT rates shared with the
    proactive policy and halve the bulk ceiling each tick down to a 100 kbit/s
    floor. Once the detector has seen three calm ticks it reports severity 0
    and the NORMAL (static) rates return at once.
    """

    def __init__(self, config):
        self.cfg = config["engines"]["reactive"]
        self.protect = config["engines"]["proactive"]["protect_rates"]
        self.static = config["qos"]["static_rates"]

    def decide(self, sample, severity, rates, **_):
        if severity < 2:
            return _copy_rates(self.static), "clear: NORMAL rates"
        new = _copy_rates(rates)
        for cls in ("voip", "video"):
            new[cls] = dict(self.protect[cls])
        bulk_max = max(int(self.cfg["bulk_floor_bps"]), int(rates["bulk"]["max_bps"]) // 2)
        new["bulk"]["max_bps"] = bulk_max
        new["bulk"]["min_bps"] = min(int(self.static["bulk"]["min_bps"]), bulk_max)
        return new, "congested: PROTECT minimums, bulk ceiling halved"


class ProactiveController:
    """5QI-budget NORMAL/PROTECT policy driven by a Holt delay forecast.

    NORMAL -> PROTECT when a VoIP/video forecast exceeds enter_ratio x budget
    (reason "forecast") or the measured delay already exceeds the budget
    (reason "fallback"). PROTECT -> NORMAL after every protected forecast stays
    below exit_ratio x budget for clear_hold_seconds. Changes are at least
    dwell_seconds apart. Every PROTECT proposal passes the fairness guardrail
    (bulk floor, then Jain >= minimum_jain on predicted satisfaction).
    """

    PROTECTED = ("voip", "video")

    def __init__(self, config):
        self.cfg = config["engines"]["proactive"]
        self.static = config["qos"]["static_rates"]
        self.capacity_bps = float(config["qos"]["link_capacity_bps"])
        self.budgets = class_delay_budgets_ms(config)
        tick = float(config["runtime"]["tick_seconds"])
        self.enter = float(config["fiveqi"]["protect_enter_ratio"])
        self.exit = float(config["fiveqi"]["protect_exit_ratio"])
        self.clear_ticks = max(1, round(float(config["fiveqi"]["clear_hold_seconds"]) / tick))
        self.dwell_ticks = max(1, round(float(self.cfg["dwell_seconds"]) / tick))
        self.protect = False
        self.calm = 0
        self.tick = 0
        self.last_change = -10**9
        self.demand_mbps = {}
        self.guard_adjustments = 0

    def _update_demand(self, sample):
        weight = float(self.cfg["demand_ewma_weight"])
        for cls in ("voip", "video", "bulk"):
            value = float(sample.get("q_mbps", {}).get(cls, 0.0) or 0.0)
            old = self.demand_mbps.get(cls)
            self.demand_mbps[cls] = value if old is None else weight * value + (1 - weight) * old

    def satisfaction_jain(self, candidate, bulk_active):
        """Jain index of predicted per-class satisfaction under ``candidate``."""
        from manager.guards import jain_index
        capacity = self.capacity_bps / 1e6
        satisfaction, used = [], 0.0
        for cls in self.PROTECTED:
            need = self.demand_mbps.get(cls, 0.0)
            got = min(need, candidate[cls]["max_bps"] / 1e6)
            used += got
            satisfaction.append(min(1.0, got / need) if need > 1e-3 else 1.0)
        if bulk_active:
            got = min(candidate["bulk"]["max_bps"] / 1e6, max(0.0, capacity - used))
            satisfaction.append(min(1.0, got / (capacity / 3.0)))
        else:
            satisfaction.append(1.0)
        return jain_index(satisfaction)

    def guardrail(self, candidate, bulk_active):
        guarded = _copy_rates(candidate)
        floor = int(self.cfg["bulk_floor_bps"])
        guarded["bulk"]["max_bps"] = max(floor, int(guarded["bulk"]["max_bps"]))
        step = int(self.cfg["bulk_recovery_step_bps"])
        while (self.satisfaction_jain(guarded, bulk_active) < float(self.cfg["minimum_jain"]) and
               guarded["bulk"]["max_bps"] < self.capacity_bps):
            guarded["bulk"]["max_bps"] = int(min(self.capacity_bps, guarded["bulk"]["max_bps"] + step))
        return guarded, guarded != candidate

    def decide(self, sample, severity, rates, forecast=None, **_):
        self.tick += 1
        self._update_demand(sample)
        delays = sample.get("class_delay_ms", {}) or {}
        predicted = getattr(forecast, "class_delay_ms", {}) if forecast else {}
        if not self.protect:
            trigger = None
            if any(float(predicted.get(c, 0.0)) > self.enter * self.budgets[c] for c in self.PROTECTED):
                trigger = "forecast"
            elif any(float(delays.get(c, 0.0)) > self.budgets[c] for c in self.PROTECTED):
                trigger = "fallback"
            want = trigger is not None
        else:
            calm = all(float(predicted.get(c, delays.get(c, 0.0))) < self.exit * self.budgets[c]
                       for c in self.PROTECTED)
            self.calm = self.calm + 1 if calm else 0
            want = self.calm < self.clear_ticks
            trigger = "clear" if not want else None
        if want != self.protect and self.tick - self.last_change >= self.dwell_ticks:
            self.protect, self.calm, self.last_change = want, 0, self.tick
        if not self.protect:
            return _copy_rates(self.static), f"NORMAL ({trigger})" if trigger else "NORMAL hold"
        bulk_active = bool(sample.get("bulk_active")) or self.demand_mbps.get("bulk", 0.0) > 0.1
        candidate, adjusted = self.guardrail(_copy_rates(self.cfg["protect_rates"]), bulk_active)
        if adjusted and candidate != rates:
            self.guard_adjustments += 1
        reason = f"PROTECT ({trigger})" if trigger else "PROTECT hold"
        return candidate, reason + ("; guardrail raised bulk ceiling" if adjusted else "")


class ForecastWeightController:
    """Predictive-feedback stand-in; not a reproduction of any named paper."""
    def __init__(self, config):
        self.config = config

    def decide(self, sample, severity, rates, forecast=None, **_):
        new = {name: dict(value) for name, value in rates.items()}
        budgets = class_delay_budgets_ms(self.config)
        predicted = getattr(forecast, "class_delay_ms", {}) if forecast else {}
        current = sample.get("class_delay_ms", {}) or {}
        forecast_warning = any(
            cls in predicted and predicted[cls] >=
            self.config["fiveqi"]["protect_enter_ratio"] * budget
            for cls, budget in budgets.items())
        actual_violation = any(current.get(cls, 0.0) >= budget
                               for cls, budget in budgets.items())
        protect_active = bool(sample.get("delay_protect_active", False))
        fallback_severe = severity >= 2 and (forecast is None or not predicted)
        legacy_warning = (forecast is not None and not predicted and
                          forecast.voip_rtt_ms > self.config["sla"]["voip_rtt_ms"] and
                          severity < 2)
        if forecast_warning or legacy_warning or actual_violation or protect_active or fallback_severe:
            floor = max(self.config["qos"]["queues"]["bulk"]["floor_bps"],
                        self.config["guards"]["fairness"]["bulk_floor_bps"])
            new["bulk"]["max_bps"] = max(rates["bulk"]["min_bps"], floor,
                                                int(rates["bulk"]["max_bps"] * self.config["engines"]["forecast_weight"]["bulk_shrink"]))
            reason = "forecast or delay-budget warning: bulk decrease"
        elif rates["bulk"]["max_bps"] < self.config["qos"]["static_rates"]["bulk"]["max_bps"]:
            new["bulk"]["max_bps"] = min(self.config["qos"]["static_rates"]["bulk"]["max_bps"],
                                                rates["bulk"]["max_bps"] + self.config["engines"]["rule_aimd"]["bulk_restore_bps"])
            reason = "delay budget clear: additive bulk restore"
        else:
            reason = "hold"
        return new, reason


def make_engine(name, config, **kwargs):
    classes = {"rule_aimd": RuleAIMD, "pi": PIController,
               "cost_aware_pi": CostAwarePIController, "qlearning": QLearningEngine,
               "reactive": ReactiveController, "proactive": ProactiveController}
    if name == "forecast_weight":
        return ForecastWeightController(config)
    if name not in classes:
        raise ValueError(f"unknown engine {name!r}; choose {', '.join((*classes, 'forecast_weight'))}")
    # Runtime options (training flag, seed, loaded table) are specific to the
    # tabular learner; fixed-policy engines intentionally have config-only APIs.
    if name == "qlearning":
        return QLearningEngine(config, **kwargs)
    return classes[name](config)
