"""Fast synthetic tests; none of these tests starts Mininet or modifies OVS."""
import math
from pathlib import Path
import pytest

from manager.detectors import (AnomalyDetector, FusedDetector, StatisticalDetector,
                               SupervisedDetector, ThresholdDetector, train_supervised)
from manager.forecaster import HoltForecaster
from manager.guards import FairnessGuard, SafetyShield, jain_index
from manager.engines import PIController, QLearningEngine, make_engine
from manager.actuator import setup_qos
from run_research import _mos, _set_bottleneck_capacity


def config():
    from manager.config import load_config
    return load_config()


def test_threshold_detector_hysteresis():
    d = ThresholdDetector(config())
    assert d.update({"utilization": .9, "voip_rtt_ms": 10}).severity == 2
    for _ in range(config()["detectors"]["threshold"]["exit_calm_ticks"]):
        out = d.update({"utilization": .2, "voip_rtt_ms": 10})
    assert out.severity == 0


def test_stat_detector_calibrates_then_detects():
    c = config(); c["detectors"]["stat"]["calibration_seconds"] = 2
    d = StatisticalDetector(c)
    d.update({"utilization": .1}); d.update({"utilization": .1})
    out = d.update({"utilization": .9})
    assert out.severity == 2


def test_anomaly_detector_uses_calibration_window():
    c = config(); c["detectors"]["anomaly"]["calibration_seconds"] = 3
    d = AnomalyDetector(c)
    sample = {"utilization": .1, "voip_rtt_ms": 10, "video_rtt_ms": 10,
              "bulk_rtt_ms": 10, "backlog_bytes": 0, "drop_rate": 0}
    assert d.update(sample).reason == "calibrating"
    assert d.update(sample).reason == "calibrating"
    assert d.update(sample).reason == "calibrated"
    assert d.update(sample).severity in (0, 2)


def test_supervised_detector_loads_offline_model():
    samples = []
    for i in range(20):
        samples.append({"utilization": .1 if i < 10 else .95,
            "voip_rtt_ms": 10 if i < 10 else 50, "video_rtt_ms": 12,
            "bulk_rtt_ms": 10, "backlog_bytes": 0 if i < 10 else 300000,
            "drop_rate": 0, "bulk_active": i >= 10, "sla_rtt_ms": 20})
    path = Path(__file__).with_name(".supervised-test.joblib")
    try:
        train_supervised(samples, path)
        c = config(); c["detectors"]["supervised"]["model_path"] = str(path)
        result = SupervisedDetector(c).update(samples[-1])
        assert result.severity == 2
    finally:
        path.unlink(missing_ok=True)


def test_fused_detector_returns_class_severity_map():
    c = config(); c["detectors"]["anomaly"]["calibration_seconds"] = 2
    c["detectors"]["stat"]["calibration_seconds"] = 2
    d = FusedDetector(c)
    sample = {"utilization": .1, "voip_rtt_ms": 10, "video_rtt_ms": 10,
              "bulk_rtt_ms": 10, "backlog_bytes": 0, "drop_rate": 0}
    for _ in range(2):
        result = d.update(sample)
    result = d.update(sample)
    assert set(result.scores) == {"voip", "video", "bulk"}


def test_holt_forecaster_returns_finite_values_and_tracks_error():
    f = HoltForecaster(config())
    assert f.update({"utilization": .1, "voip_rtt_ms": 10}).mae == 0
    f.update({"utilization": .2, "voip_rtt_ms": 12})
    assert math.isfinite(f.mae) and f.mae >= 0


def test_holt_forecast_uses_current_observation_for_full_horizon():
    c = config()
    c["forecaster"].update({"alpha": 1.0, "beta": 1.0, "horizon_seconds": 3})
    f = HoltForecaster(c)
    f.update({"utilization": 0.0, "voip_rtt_ms": 0.0,
              "class_delay_ms": {"voip": 1.0, "video": 1.0, "bulk": 1.0}})
    result = f.update({"utilization": 0.0, "voip_rtt_ms": 0.0,
                       "class_delay_ms": {"voip": 2.0, "video": 1.0, "bulk": 1.0}})
    # With alpha=beta=1, level=2 and trend=1 at t=2, so the t=5 forecast is 5.
    assert result.class_delay_ms["voip"] == 5.0


def test_forecaster_does_not_claim_mae_valid_before_horizon_is_scored():
    c = config(); c["forecaster"]["horizon_seconds"] = 3
    f = HoltForecaster(c)
    sample = {"utilization": 0.2, "voip_rtt_ms": 10.0,
              "class_delay_ms": {"voip": 2.0, "video": 3.0, "bulk": 4.0}}
    for _ in range(3):
        f.update(sample)
        assert not f.ready
    f.update(sample)
    assert f.ready


def test_holt_forecaster_mae_uses_dimensionless_signal_scales():
    f = HoltForecaster(config())
    f.errors["utilization"] = [.2]
    f.errors["voip_rtt_ms"] = [4.0]
    assert f.mae == .2


def test_fiveqi_budgets_and_hysteresis_match_proposal():
    from manager.budgets import class_delay_budgets_ms
    from manager.guards import DelayBudgetHysteresis
    c = config()
    assert class_delay_budgets_ms(c) == {"voip": 10.0, "video": 15.0, "bulk": 30.0}
    guard = DelayBudgetHysteresis(c)
    assert guard.update({"voip": 8.0}, {}, class_delay_budgets_ms(c))
    for _ in range(4):
        assert guard.update({"voip": 5.0, "video": 5.0, "bulk": 5.0}, {},
                            class_delay_budgets_ms(c))
    assert not guard.update({"voip": 5.0, "video": 5.0, "bulk": 5.0}, {},
                            class_delay_budgets_ms(c))


def test_delay_estimate_does_not_double_count_propagation():
    from manager.collector import estimate_class_delay_ms
    # 4 Mbit/s video holds ~2500 B in its 5 ms netem leaf: that is just 5 ms.
    assert estimate_class_delay_ms(2500, 4.0, 5.0, 4.0) == 5.0
    # One 202 B VoIP frame is not a long wait when bounded by the 0.5 Mbit/s guarantee.
    assert estimate_class_delay_ms(202, 0.13, 5.0, 0.5) == 5.0
    assert estimate_class_delay_ms(50_000, 4.0, 5.0, 4.0) == 100.0


def test_tc_stats_extracts_per_class_sent_bytes_backlog_and_drops(monkeypatch):
    import manager.collector as collector
    fixture = """class htb 1:1 root rate 500Kbit ceil 1Mbit prio 1
 Sent 12345 bytes 100 pkt (dropped 2, overlimits 0 requeues 0)
 backlog 800b 4p requeues 0
class htb 1:2 root rate 4Mbit ceil 6Mbit prio 2
 Sent 23456 bytes 200 pkt (dropped 3, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
class htb 1:3 root rate 1Mbit ceil 10Mbit prio 3
 Sent 34567 bytes 300 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 1600b 8p requeues 0
"""

    def fake_run(*_args, **_kwargs):
        return type("Result", (), {"stdout": fixture})()

    monkeypatch.setattr(collector.subprocess, "run", fake_run)
    instance = collector.MetricsCollector(None, "s1-eth4", config())
    backlog, drops, queues = instance._tc_stats()
    assert backlog == 2400 and drops == 5
    assert queues["voip"]["tx_bytes"] == 12345
    assert queues["video"]["backlog_bytes"] == 0
    assert queues["bulk"]["drops"] == 0


def test_fairness_guard_and_jain():
    c = config(); guard = FairnessGuard(c)
    assert jain_index([1, 1, 1]) == 1
    candidate = {k: dict(v) for k, v in c["qos"]["static_rates"].items()}
    assert guard.evaluate(candidate)[0]
    candidate["bulk"]["min_bps"] = 0
    assert not guard.evaluate(candidate)[0]


def test_safety_shield_falls_back_on_stale_telemetry():
    c = config(); shield = SafetyShield(c)
    rates = {k: dict(v) for k, v in c["qos"]["static_rates"].items()}
    altered = {k: dict(v) for k, v in rates.items()}; altered["bulk"]["max_bps"] //= 2
    result, rejected, reasons = shield.filter(altered, rates, rates, 1, stale_ticks=4)
    assert rejected and result == rates and "stale telemetry" in reasons


def test_pi_output_is_clamped_to_configured_floor_ceiling():
    c = config(); pi = PIController(c)
    rates = {k: dict(v) for k, v in c["qos"]["static_rates"].items()}
    result, _ = pi.decide({"voip_rtt_ms": 100, "q_mbps": {"video": 1}}, 2, rates)
    assert c["qos"]["queues"]["voip"]["floor_bps"] <= result["voip"]["min_bps"] <= c["qos"]["queues"]["voip"]["max_bps"]


def test_pi_reduces_bulk_ceiling_and_opens_protected_ceilings_on_queue_delay():
    c = config(); pi = PIController(c)
    rates = {k: dict(v) for k, v in c["qos"]["static_rates"].items()}
    pi.decide({"voip_rtt_ms": 10, "q_mbps": {"video": 4.0}}, 0, rates)
    result, _ = pi.decide({"voip_rtt_ms": 30, "q_mbps": {"video": 2.0}}, 2, rates)
    assert result["bulk"]["max_bps"] < rates["bulk"]["max_bps"]
    assert result["voip"]["max_bps"] > rates["voip"]["max_bps"]
    assert result["video"]["max_bps"] > rates["video"]["max_bps"]


def test_pi_can_act_on_a_qualified_forecast():
    from manager.forecaster import Forecast
    c = config(); pi = PIController(c)
    rates = {k: dict(v) for k, v in c["qos"]["static_rates"].items()}
    pi.decide({"voip_rtt_ms": 10, "q_mbps": {"video": 4.0}}, 0, rates)
    result, _ = pi.decide({"voip_rtt_ms": 10, "q_mbps": {"video": 4.0}}, 0,
                          rates, forecast=Forecast(.5, 30.0, .1))
    assert result["bulk"]["max_bps"] < rates["bulk"]["max_bps"]


def test_pi_stays_protective_until_delay_hysteresis_clears():
    c = config(); pi = PIController(c)
    rates = {k: dict(v) for k, v in c["qos"]["static_rates"].items()}
    sample = {"class_delay_ms": {"voip": 5.0, "video": 5.0, "bulk": 5.0},
              "q_mbps": {"video": 4.0}, "delay_protect_active": True}
    assert pi._need(sample) >= 1.0 - c["fiveqi"]["protect_enter_ratio"]
    result, _ = pi.decide(sample, 0, rates)
    assert result["bulk"]["max_bps"] < rates["bulk"]["max_bps"]


def test_qlearning_update_populates_q_table():
    c = config(); e = QLearningEngine(c, training=True, seed=1)
    rates = {k: dict(v) for k, v in c["qos"]["static_rates"].items()}
    sample = {"utilization": .95, "voip_rtt_ms": 30, "bulk_mbps": .1, "jain_index": .7}
    e.decide(sample, 2, rates)
    e.decide(sample, 2, rates)
    assert e.q
    assert any(any(v != 0 for v in row) for row in e.q.values())


def test_engine_factory_accepts_shared_runtime_options():
    c = config()
    assert isinstance(make_engine("pi", c, training=False, seed=7, q_table=None), PIController)
    assert isinstance(make_engine("qlearning", c, training=False, seed=7, q_table=None), QLearningEngine)


def test_reactive_halves_bulk_to_floor_then_restores_normal():
    from manager.engines import ReactiveController
    c = config(); e = ReactiveController(c)
    static = {k: dict(v) for k, v in c["qos"]["static_rates"].items()}
    rates = static
    for _ in range(10):
        rates, _ = e.decide({}, 2, rates)
    assert rates["bulk"]["max_bps"] == c["engines"]["reactive"]["bulk_floor_bps"]
    assert rates["bulk"]["min_bps"] <= rates["bulk"]["max_bps"]
    assert rates["video"] == c["engines"]["proactive"]["protect_rates"]["video"]
    rates, _ = e.decide({}, 0, rates)
    assert rates == static


def _proactive_sample(voip=5.0, video=5.0):
    return {"class_delay_ms": {"voip": voip, "video": video, "bulk": 40.0},
            "q_mbps": {"voip": 0.1, "video": 4.0, "bulk": 5.0}, "bulk_active": True}


def test_proactive_enters_on_forecast_and_exits_after_calm_hold():
    from manager.engines import ProactiveController
    from manager.forecaster import Forecast
    c = config(); e = ProactiveController(c)
    static = {k: dict(v) for k, v in c["qos"]["static_rates"].items()}
    calm = Forecast(0, 0, 0, {"voip": 5.0, "video": 5.0, "bulk": 40.0})
    rates, _ = e.decide(_proactive_sample(), 0, static, forecast=calm)
    assert rates == static
    # Forecast above 0.8 x 10 ms VoIP budget while the measured delay is fine.
    warn = Forecast(0, 0, 0, {"voip": 9.0, "video": 5.0, "bulk": 40.0})
    rates, reason = e.decide(_proactive_sample(), 0, static, forecast=warn)
    assert "forecast" in reason
    assert rates["bulk"]["max_bps"] == c["engines"]["proactive"]["protect_rates"]["bulk"]["max_bps"]
    states = [e.decide(_proactive_sample(), 0, rates, forecast=calm)[0] == static for _ in range(5)]
    assert states == [False, False, False, False, True]


def test_proactive_fallback_and_dwell():
    from manager.engines import ProactiveController
    c = config(); e = ProactiveController(c)
    static = {k: dict(v) for k, v in c["qos"]["static_rates"].items()}
    rates, reason = e.decide(_proactive_sample(voip=12.0), 0, static)
    assert "fallback" in reason and rates != static
    e.clear_ticks = 1
    # Calm right away, but the 3 s dwell holds PROTECT for two more ticks.
    held = [e.decide(_proactive_sample(), 0, rates)[0] == static for _ in range(3)]
    assert held == [False, False, True]


def test_proactive_guardrail_raises_bulk_ceiling_until_jain_passes():
    from manager.engines import ProactiveController
    c = config(); e = ProactiveController(c)
    e.demand_mbps = {"voip": 0.1, "video": 4.0, "bulk": 5.0}
    candidate = {k: dict(v) for k, v in c["engines"]["proactive"]["protect_rates"].items()}
    candidate["bulk"]["max_bps"] = 100_000
    guarded, adjusted = e.guardrail(candidate, bulk_active=True)
    assert adjusted and guarded["bulk"]["max_bps"] >= 1_000_000
    assert e.satisfaction_jain(guarded, True) >= 0.75
    assert e.satisfaction_jain({**candidate, "bulk": {"min_bps": 0, "max_bps": 100_000}}, True) < 0.75


def test_report_config_extends_base_and_defines_s1_to_s4():
    from manager.config import load_config
    from manager.budgets import class_delay_budgets_ms
    c = load_config(Path(__file__).resolve().parents[1] / "configs" / "report.yaml")
    assert set(["S1", "S2", "S3", "S4"]) <= set(c["scenarios"])
    assert "standard" in c["scenarios"]  # inherited from config.yaml
    assert c["engines"]["proactive"]["protect_rates"]["voip"]["min_bps"] == 1_500_000
    assert c["engines"]["proactive"]["forecast"]["alpha"] == 0.9  # inherited
    s20 = load_config(Path(__file__).resolve().parents[1] / "configs" / "report_s20.yaml")
    assert class_delay_budgets_ms(s20)["voip"] == 20.0


def test_scenario_streams_get_distinct_ports_and_offered_load():
    from manager.config import load_config
    from run_research import _offered_mbps, _rate_mbps, _scenario_streams
    c = load_config(Path(__file__).resolve().parents[1] / "configs" / "report.yaml")
    s4 = _scenario_streams(c, c["scenarios"]["S4"])
    assert [s["port"] for s in s4] == [5061, 5062, 5063]
    assert [s["file"] for s in s4] == ["voip_surge_30.json", "voip_surge_60.json", "voip_surge_90.json"]
    # 0.32 base for 120 s plus streams for 90, 60 and 30 s: 0.32 * (120+90+60+30)/120.
    assert abs(_offered_mbps(c, c["scenarios"]["S4"])["voip"] - 0.8) < 1e-9
    s2 = _scenario_streams(c, c["scenarios"]["S2"])
    assert s2[0]["file"] == "bulk_2.json" and s2[0]["flows"] == 8
    assert _rate_mbps("640K") == 0.64 and _rate_mbps("4M") == 4.0


def test_simplified_emodel_is_bounded():
    assert 1 <= _mos(10) <= 4.5
    assert 1 <= _mos(500) <= 4.5


def test_qos_setup_applies_tc_directly(monkeypatch):
    import manager.actuator as actuator
    calls = []

    def fake_run(argv, timeout=5):
        calls.append(list(argv))
        return ""

    def fake_run_best_effort(argv, timeout=5):
        calls.append(list(argv))

    monkeypatch.setattr(actuator, "_run", fake_run)
    monkeypatch.setattr(actuator, "_run_best_effort", fake_run_best_effort)
    uuids = setup_qos("s1-eth4", config())
    
    # Check that tc qdisc replace root was called
    root_qdisc_cmd = [c for c in calls if "qdisc" in c and "root" in c]
    assert len(root_qdisc_cmd) > 0
    assert "1:" in root_qdisc_cmd[0]
    
    # Check returned keys are the class IDs
    assert set(uuids) == {"default", "voip", "video", "bulk"}
    assert uuids["voip"] == "1:1"
    assert uuids["video"] == "1:2"
    assert uuids["bulk"] == "1:3"


def test_actuator_surfaces_failed_tc_rate_update(monkeypatch):
    import manager.actuator as actuator
    monkeypatch.setattr(actuator, "tc_class_rates", lambda _interface: [1, 2, 3])
    monkeypatch.setattr(actuator, "_run", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError("tc class change failed")))
    rates = {k: dict(v) for k, v in config()["qos"]["static_rates"].items()}
    rates["bulk"]["max_bps"] -= 1_000_000
    with pytest.raises(RuntimeError, match="tc class change failed"):
        actuator.OVSActuator("s1-eth4", {}, config()).apply(rates)


def test_tc_rate_snapshot_includes_ceilings(monkeypatch):
    import manager.actuator as actuator
    output = ("class htb 1:fffe root rate 10Mbit ceil 10Mbit\n"
              "class htb 1:1 parent 1:fffe rate 500Kbit ceil 1Mbit\n")
    monkeypatch.setattr(actuator, "_run", lambda *_args, **_kwargs: output)
    assert actuator.tc_class_rates("s1-eth4") == {
        "1:fffe": (10_000_000, 10_000_000),
        "1:1": (500_000, 1_000_000),
    }


def test_capacity_step_none_mode_does_not_lookup_missing_ovs_qos(monkeypatch):
    import run_research
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((list(argv), kwargs))
        if argv[1:3] == ["class", "change"]:
            return type("Result", (), {"returncode": 1})()
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(run_research.subprocess, "run", fake_run)
    _set_bottleneck_capacity("none", "s1-eth4", 5, {})
    assert calls[0][0][1:3] == ["class", "change"]
    assert calls[1][0][1:3] == ["qdisc", "replace"]


def test_fq_codel_qdisc_uses_valid_classful_parentage(monkeypatch):
    import run_research
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(run_research.subprocess, "run", fake_run)
    run_research._apply_qdisc("s1-eth4", 10, 5, 100)
    assert any(cmd[cmd.index("root") + 1:cmd.index("root") + 2] == ["handle"] and "htb" in cmd for cmd in calls)
    assert any("class" in cmd and "1:1" in cmd and "htb" in cmd for cmd in calls)
    fq = next(cmd for cmd in calls if "fq_codel" in cmd)
    assert fq[fq.index("parent") + 1] == "1:1"
    assert not any("netem" in cmd for cmd in calls)


def test_cake_qdisc_is_a_root_shaper_not_nested_under_netem(monkeypatch):
    import run_research
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(run_research.subprocess, "run", fake_run)
    run_research._apply_qdisc("s1-eth4", 10, 5, 100, kind="cake")
    assert len(calls) == 1
    assert calls[0][calls[0].index("root") + 1] == "handle"
    assert "cake" in calls[0] and "bandwidth" in calls[0]
    assert "netem" not in calls[0]


def test_delay_step_updates_peer_netem_for_aqm_baseline(monkeypatch):
    import run_research
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        if argv[:4] == ["tc", "qdisc", "show", "dev"]:
            output = ("qdisc htb 5: root\nqdisc netem 10: parent 5:1 limit 1000"
                      if argv[-1] == "s2-eth4" else "qdisc htb 1: root")
            return type("Result", (), {"returncode": 0, "stdout":
                output, "stderr": ""})()
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(run_research.subprocess, "run", fake_run)
    run_research._set_path_delay("s1-eth4", 20)
    assert calls[-1][calls[-1].index("dev") + 1] == "s2-eth4"
    assert calls[-1][calls[-1].index("parent") + 1] == "5:1"
    assert "20ms" in calls[-1]
