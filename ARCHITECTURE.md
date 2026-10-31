# Architecture and novelty boundaries

## Existing dataplane

The testbed keeps its existing Mininet topology and Ryu OpenFlow 1.3 learning
switch. OVS HTB queues on `s1`'s bottleneck egress serve VoIP (queue 1), video
(queue 2), and bulk (queue 0). `none`, `static`, and `adaptive` retain their
prior setup and rule policy. New behavior is opt-in through the added modes.

## Metrics source interface

Both collectors expose `start()`, `stop()`, `latest`, and `interval`. The
`create_collector(..., signal_source=...)` factory accepts `polling` or
`telemetry`, and `common/config.py` provides the default source. The polling
collector preserves 1-second samples. The telemetry collector uses a
100 ms sampling agent for `ovs-ofctl queue-stats` and `tc -s qdisc`, then pushes
JSON reports over UDP to a local collector. Reports are periodic and carry an
event flag when utilization or VoIP RTT crosses the configured threshold.
`samples.csv` retains the legacy columns and appends probe delay, jitter, loss,
aggregate qdisc backlog/drops, per-queue OVS transmission errors, and source
fields. `telemetry_overhead.csv` records report
bytes per second and approximate process CPU percentage.

`monitoring/probe_agent.py` sends 10 Hz UDP probes on traffic-class-specific
ports through the same queue classifier. Probe payloads contain a monotonic
timestamp and sequence number. The receiver estimates one-way delay, jitter,
and sequence gaps and writes them to `probes.csv`. This assumes sender and
receiver share the host monotonic clock, as they do in this local Mininet
emulation; it is not a valid clock-synchronized one-way measurement across
separate machines.

This is **INT-inspired emulated telemetry**. OVS/Linux HTB is not a P4 switch,
and the probes are generated at hosts. There is no switch-resident INT header
insertion or P4 metadata pipeline. A P4/BMv2 dataplane is a possible stretch
option for true INT.

## RL controller

`controller/rl_env.py` implements a Gymnasium environment and shared action,
state, and reward functions. State inputs normalize per-queue use, per-class
delay/jitter/loss, backlog, current min/max rates, last action, and time since
change. Ten discrete actions adjust bulk max rate or VoIP/video guarantees;
all rates are clamped to baseline bounds. `controller/train_rl.py` fits a
seeded tabular Q-learning policy in a compact surrogate. It can calibrate its
starting delay and video values from existing `samples.csv` files, writes the
policy, `rl_training.csv`, and an `rl_training.png` reward curve, and uses no
neural-network framework. Later real Mininet samples can recalibrate the
surrogate and resume the saved Q table with `--resume-policy`. Mininet runs
remain necessary for validation; the surrogate curve is not a network result.

The runtime shield rejects invalid actions and uses the rule manager when the
latest sample is stale. Polling RL is evaluated at the polling cadence;
telemetry RL uses a 200 ms decision interval. Reward weights are in
`common/config.py` and reflect video throughput, VoIP delay/jitter/loss,
delay-threshold violations, bulk starvation, policy churn, and normalized
reserved-bandwidth cost. The separate `fused_pi_forecast_cost` policy uses
demand-level minimum guarantees while calm and temporarily raises VoIP/video
guarantees when forecasts or measured delay signal risk.

Experiment summaries report an operating-cost index built from normalized
guaranteed bandwidth, policy actuation frequency, and controller CPU time.
This index is an operational proxy, not a monetary charge. Evaluate it with
video stability, VoIP RTT, SLA violations, and bulk starvation so an
uncontrolled baseline does not appear attractive solely because it reserves
no per-class HTB bandwidth.

## Experiment design

The default ablation is `none`, `static`, `rule-polling`, `rule-telemetry`,
`rl-polling`, and `rl-telemetry`. The runner defaults to ten repeats with a
fixed seed sequence, the same probes in every compared mode with per-seed
phase offsets, and identical congestion timing. Standalone legacy runs keep
probes disabled unless their mode uses telemetry or RL. Actual results are
written only after execution; comparison output reports mean and a 95%
confidence interval and creates CSV, plots, and `summary.md`. No performance
claim is inferred from surrogate training curves.
