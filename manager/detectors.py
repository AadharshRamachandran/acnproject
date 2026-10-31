"""Selectable threshold, statistical, anomaly, supervised, and fused detectors."""
from collections import deque
from dataclasses import dataclass
from pathlib import Path
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestClassifier


@dataclass
class Detection:
    severity: int
    congested: bool
    scores: dict
    reason: str


def feature_vector(sample):
    values = np.asarray([sample.get("utilization", 0.0), sample.get("voip_rtt_ms", 0.0),
                         sample.get("video_rtt_ms", 0.0), sample.get("bulk_rtt_ms", 0.0),
                         sample.get("backlog_bytes", 0.0) / 100000.0,
                         sample.get("drop_rate", 0.0)], dtype=float)
    return np.nan_to_num(values, nan=0.0, posinf=1e6, neginf=0.0)


class ThresholdDetector:
    def __init__(self, config):
        self.cfg = config["detectors"]["threshold"]
        self.calm = 0
        self.active = False

    def update(self, sample, **_):
        bad = (sample.get("utilization", 0) > self.cfg["utilization"]
               or sample.get("voip_rtt_ms", 0) > self.cfg["voip_rtt_ms"])
        if bad:
            self.active, self.calm = True, 0
        elif self.active:
            self.calm += 1
            if self.calm >= self.cfg["exit_calm_ticks"]:
                self.active = False
        sev = 2 if self.active else 0
        return Detection(sev, self.active, {c: sev for c in ("voip", "video", "bulk")},
                         "threshold-crossing" if bad else ("hysteresis" if self.active else "clear"))


class StatisticalDetector:
    def __init__(self, config):
        self.cfg = config["detectors"]["stat"]
        self.alpha = self.cfg["ewma_alpha"]
        self.base = None
        self.scale = None
        self.samples = []
        self.ewma = None
        self.cusum = 0.0
        self.active = False
        self.calm = 0
        self.tick = 0

    def update(self, sample, **_):
        x = float(sample.get("utilization", 0.0))
        self.tick += 1
        if self.tick <= max(1, round(self.cfg["calibration_seconds"])):
            self.samples.append(x)
            if self.tick == max(1, round(self.cfg["calibration_seconds"])):
                self.base = float(np.mean(self.samples))
                self.scale = max(float(np.std(self.samples)), float(self.cfg["std_floor"]))
                self.ewma = self.base
            return Detection(0, False, {c: 0 for c in ("voip", "video", "bulk")}, "calibrating")
        if self.base is None:
            self.base = x
            self.ewma = x
        self.ewma = self.alpha * x + (1 - self.alpha) * self.ewma
        deviation = max(0.0, (self.ewma - self.base) / max(self.scale or 0.0, self.cfg["std_floor"]))
        self.cusum = max(0.0, self.cusum + deviation - self.cfg["cusum_k"])
        entry = self.cusum >= self.cfg["cusum_h"] or deviation >= self.cfg["deviation_threshold"]
        if entry:
            self.active, self.calm = True, 0
        elif self.active:
            self.calm += 1
            if self.calm >= self.cfg["exit_calm_ticks"]:
                self.active, self.cusum = False, 0.0
        sev = 2 if self.active else (1 if deviation > 0 else 0)
        return Detection(sev, self.active, {c: sev for c in ("voip", "video", "bulk")},
                         f"ewma={self.ewma:.4f};cusum={self.cusum:.3f}")


class AnomalyDetector:
    def __init__(self, config):
        self.cfg = config["detectors"]["anomaly"]
        self.window = deque(maxlen=self.cfg["window"])
        self.calibration_ticks = max(1, round(self.cfg["calibration_seconds"] /
                                             config["runtime"]["tick_seconds"]))
        self.calibration = []
        self.model = IsolationForest(contamination=self.cfg["contamination"],
                                     random_state=self.cfg["random_state"])
        self.fitted = False

    def update(self, sample, **_):
        x = feature_vector(sample)
        self.window.append(x)
        if not self.fitted and len(self.calibration) < self.calibration_ticks:
            self.calibration.append(x)
        if not self.fitted and len(self.calibration) >= self.calibration_ticks:
            self.model.fit(np.asarray(self.calibration))
            self.fitted = True
            return Detection(0, False, {c: 0 for c in ("voip", "video", "bulk")}, "calibrated")
        if not self.fitted:
            return Detection(0, False, {c: 0 for c in ("voip", "video", "bulk")}, "calibrating")
        anomaly = int(self.model.predict(x.reshape(1, -1))[0] == -1)
        sev = 2 if anomaly else 0
        return Detection(sev, bool(anomaly), {c: sev for c in ("voip", "video", "bulk")},
                         "isolation-forest" if anomaly else "normal")


class SupervisedDetector:
    def __init__(self, config):
        self.path = Path(config["detectors"]["supervised"]["model_path"])
        self.model = joblib.load(self.path) if self.path.exists() else None

    def update(self, sample, **_):
        pred = int(self.model.predict(feature_vector(sample).reshape(1, -1))[0]) if self.model else 0
        sev = 2 if pred else 0
        return Detection(sev, bool(pred), {c: sev for c in ("voip", "video", "bulk")},
                         "random-forest" if self.model else "model-not-trained")


class FusedDetector:
    def __init__(self, config):
        self.stat = StatisticalDetector(config)
        self.anomaly = AnomalyDetector(config)
        self.cfg = config["detectors"]["fused"]

    def update(self, sample, **kwargs):
        stat = self.stat.update(sample, **kwargs)
        anomaly = self.anomaly.update(sample, **kwargs)
        score = float(stat.severity == 2) + float(anomaly.severity == 2)
        threshold = self.cfg["congested_score"]
        sev = 2 if score >= threshold else (1 if score >= self.cfg["warning_score"] else 0)
        return Detection(sev, sev == 2, {c: sev for c in ("voip", "video", "bulk")},
                         f"fused(stat={stat.reason};anomaly={anomaly.reason})")


def make_detector(name, config):
    types = {"threshold": ThresholdDetector, "stat": StatisticalDetector,
             "anomaly": AnomalyDetector, "supervised": SupervisedDetector,
             "fused": FusedDetector}
    if name not in types:
        raise ValueError(f"unknown detector {name!r}; choose {', '.join(types)}")
    return types[name](config)


def train_supervised(samples, output, random_state=7):
    """Fit an RF detector using congestion ground truth when available."""
    rows = [feature_vector(s) for s in samples]
    labels = [int(s["gt_congestion"]) if "gt_congestion" in s else
              int(s.get("bulk_active", False) and s.get("voip_rtt_ms", 0) > s.get("sla_rtt_ms", 20))
              for s in samples]
    if len(set(labels)) < 2:
        raise ValueError("training requires both congested and clear labelled samples")
    model = RandomForestClassifier(n_estimators=100, random_state=random_state,
                                   class_weight="balanced")
    model.fit(np.asarray(rows), np.asarray(labels))
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output)
    return model
