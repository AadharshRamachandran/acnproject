# SDN-Based Adaptive QoS Management for Heterogeneous 5G Traffic

> The original Stream A/B/C walkthrough below remains available. The modular
> research testbed added under `manager/`, `ryu_app/`, and `topo/` is the current
> implementation for the Safe Hybrid Adaptive QoS experiments.

### Legacy Stream A/B/C overview

The following three-mode walkthrough describes the legacy `scenario.py` path.
The current research runner below uses the separate tc-based adaptive pipeline.

Mininet/OVS testbed with three 5G-style traffic classes (VoIP ~ URLLC,
video ~ eMBB, bulk ~ best effort) sharing one bottleneck link, a Ryu
controller steering each class into its own OVS queue, and three QoS modes
run under an identical congestion timeline:

| Mode | What happens when bulk traffic saturates the link |
|------|---------------------------------------------------|
| `none` | No queues. Everything degrades together. |
| `static` | Fixed HTB queues (VoIP > video > bulk priority). Better, but rates are hand-tuned and never change. |
| `adaptive` | Static queues **plus** a control loop that detects congestion (utilisation / VoIP RTT) and rewrites queue rates live: bulk's max-rate is halved each tick, VoIP/video min-rates are raised, then bulk is restored gradually once the link clears. |

## Layout

| Path | Stream | Purpose |
|------|--------|---------|
| `topology/topo.py` | A | Mininet topology: 3 senders -> s1 ==bottleneck== s2 -> server |
| `traffic/generators.py` | A | iperf3-based VoIP / video / bulk generators |
| `controller/qos_controller.py` | B | Ryu app: L2 learning + per-class `set_queue` on s1 |
| `controller/qos_setup.py` | B | Creates/updates/clears OVS HTB queues via `ovs-vsctl` |
| `controller/adaptive_manager.py` | B | **Adaptive QoS control loop** — the project's contribution |
| `monitoring/metrics_collector.py` | C | Live RTT + per-queue bandwidth sampler -> `samples.csv` |
| `monitoring/congestion_detector.py` | C | Congestion state machine with hysteresis |
| `monitoring/analyze.py` | C | Per-run graphs, summary, QoS recovery time |
| `monitoring/compare.py` | C | none vs static vs adaptive comparison graphs/table |
| `scenario.py` | all | One run: topology -> QoS mode -> traffic -> congestion -> analysis |
| `run_experiments.py` | all | All modes x N repeats -> `results/comparison/` |
| `common/config.py` | all | Ports, IPs, link limits, queue rates, thresholds |

## Safe Hybrid Adaptive QoS research testbed

This implementation adds a six-host topology (three traffic sources and three
destinations), a discovered s1-to-s2 egress port, tc-based HTB queue telemetry,
selectable detectors, EWMA and Holt forecasting, AIMD/PI/tabular-Q decision
engines, fairness/safety gates, seeded scenarios, and per-run analysis artifacts. The
new control modes are separate from the legacy `scenario.py` modes documented
below; existing runs and files are preserved.

### Docker path (recommended)

The included `docker-compose.yml` builds the Python 3.8/Ryu-compatible image
from `docker/Dockerfile`; the container is privileged and shares the host
network as Mininet/OVS require. The experiment runner now starts Ryu inside the
run container automatically when nothing is listening at the configured
controller address. A matrix run reuses one controller for all trials and
shuts down only the Ryu process it started. To run Ryu separately for debugging,
use terminal 1:

```bash
docker compose build
docker compose run --rm testbed ryu-manager --ofp-tcp-listen-port 6653 ryu_app/qos_app.py
```

The runner starts Ryu automatically. Use this order for a fresh results set:

```bash
docker compose run --rm testbed python3 scripts/check_environment.py
docker compose run --rm testbed python3 run_experiments.py --modes fused_pi_forecast fused_pi_forecast_cost static reactive proactive --scenarios standard --repeats 1
docker compose run --rm testbed python3 run_experiments.py --modes none --scenarios flash_crowd --repeats 1
docker compose run --rm testbed python3 train_detector.py results/none/flash_crowd/run_7/samples.csv
docker compose run --rm testbed python3 train.py --episodes 1000 --seed 7 --output results/q_table.json
docker compose run --rm testbed python3 run_experiments.py --repeats 5
docker compose run --rm testbed python3 analyze.py --results results
```

Before running the full matrix, inspect the smoke run's `summary.json`: it must
have `telemetry_valid: true`, nonzero per-class `queue_counter_totals_bytes`,
and a `queue_video_rate_iperf_ratio` between 0.5 and 1.5. The analyzer excludes
incomplete queue telemetry and runs whose iperf throughput is missing. If a
matrix is interrupted, rerun its command with `--resume`.

Each run is written to `results/<mode>/<scenario>/run_<seed>/` with a full
config snapshot, samples, decisions, summary JSON, and time-series plot. The
aggregate CSV, Markdown table, and mode comparison plots go to
`results/analysis/`. `mn -c` is run before and after each trial. Add `--resume`
after an interrupted matrix to skip trials that already have `summary.json`.

### Native Linux path

Use a supported Linux host with root/sudo access. Install system packages
(`mininet`, `openvswitch-switch`, `iperf3`, `iproute2`, `iputils-ping`) and
Python packages from `requirements.txt`, start OVS, then use two terminals:

```bash
sudo service openvswitch-switch start
python3 -m pip install -r requirements.txt
```

```bash
sudo python3 scripts/check_environment.py
sudo python3 run_research.py --mode fused_pi_forecast --scenario standard --seed 7
sudo python3 run_experiments.py --modes reactive proactive stat_pi fused_pi_forecast fused_qlearning --scenarios standard repeated_bursts --repeats 5
python3 analyze.py --results results
```

For the supervised detector, train from labeled `samples.csv` files collected
from runs that include the required `bulk_active`, `sla_rtt_ms`, and feature
columns, then select `supervised_rule`:

```bash
python3 run_experiments.py --modes none --scenarios flash_crowd --repeats 1
python3 train_detector.py results/none/flash_crowd/run_7/samples.csv
```

Train and evaluate the tabular Q table (evaluation always sets epsilon to zero):

```bash
python3 train.py --episodes 1000 --seed 7 --output results/q_table.json
sudo python3 run_experiments.py --modes fused_qlearning --scenarios standard --repeats 5 --q-table results/q_table.json
```

`scripts/setup_qos.py <s1-ethN>` can also be used to configure an OVS port
manually; it prints the resulting queue UUID map. The experiment runner
discovers the s1 egress itself and stores that map in each run directory.

### Modes, assumptions, and limits

`config.yaml` is the source for timing, SLA, queue floors, detector thresholds,
forecast horizon, PI/Q-learning parameters, guard thresholds, and scenario
timings. Its `fiveqi` section maps VoIP/video/bulk to profiles 1/2/9 and
computes per-class one-way delay budgets as configured link-share × PDB.
The controller estimates queue delay as propagation delay plus backlog/service
time. Holt is the forecast-assisted policy; `fused_pi_ewma` provides the EWMA
baseline. Both forecast each class three seconds ahead and can enter protection
at 80% of budget. Adaptive engines also fall back to reactive protection when
measured class delay exceeds budget. Protection exits only after all measured
and forecast class delays stay below 60% of budget for five seconds. The
fairness guard uses Jain's index threshold of 0.75 and a 1 Mbps bulk floor; the
safety shield enforces a three-second minimum dwell.

Modes include no-control, static HTB, threshold/AIMD, statistical/PI, fused/PI,
fused/PI with Holt forecast action, fused/PI with EWMA forecast, cost-aware
fused Holt/PI, fused/Q-learning
with and without the shield, supervised/RF, forecast-weight feedback,
FQ-CoDel+ECN, and optional CAKE. CAKE depends on host `sch_cake` kernel support
and is excluded from the default matrix; run it explicitly with `--modes cake`.
FQ-CoDel and CAKE use valid Linux qdisc parentage. Their performance depends on
the host kernel and Mininet/OVS emulation.

The `fused_pi_forecast_cost` novelty keeps VoIP, video, and bulk at demand-level
minimum guarantees while delay is safe (0.1, 4, and 1 Mbps by default). When a
measured or forecast delay reaches the protection region, it temporarily raises
the VoIP and video guarantees to 0.5 and 5 Mbps. It keeps the 1 Mbps bulk floor,
and trims preferred guarantees to fit a reduced capacity. During active bulk
traffic, video falling below 95% of its configured rate triggers protection
and a proportional reduction in the bulk ceiling. This targets high video
stability and low VoIP RTT while reducing reserved rate when the link is calm.
The Q-learning reward also penalizes reservation cost alongside VoIP delay,
video instability, SLA violations, starvation, and policy changes.

The analyzer reports mean reserved rate and a dimensionless operating-cost
index. The index combines normalized guaranteed bandwidth (70%), policy
actuation rate (20%), and controller CPU time (10%). It is a reproducible
operational cost proxy, not a monetary bill; compare it alongside VoIP RTT,
video stability, SLA violations, and bulk starvation. Classless `none`,
FQ-CoDel, and CAKE modes have no HTB guarantees to count as reserved bandwidth.

Queue delay is an estimate derived from HTB backlog and service rate, not a
packet-level one-way delay measurement. The configured 5QI IDs label the three
emulated traffic classes; the testbed does not implement 5G core signaling or
real 5QI admission control. The proposal's OVSDB actuator diagram is not
literal: this environment applies rate changes through Linux `tc` HTB because
OVS 2.13 does not reliably realize these kernel classes through OVSDB QoS rows.
The proposal's no-QoS, static HTB, reactive, FQ-CoDel, CAKE, and predictive
fairness-guarded setups are available in the same experiment matrix; CAKE still
requires a host kernel with `sch_cake` support.

The supervised RF and forecast-weight paths are simplified
stand-ins; none claims to reproduce a specific published paper or endpoint
signaling protocol. The MOS output uses the requested simplified ITU-T G.107
equation and is an estimate, not a subjective listening test.

Assumptions and limitations: traffic classification uses destination transport
ports; hosts and controller run on one Linux machine; Mininet timing and
virtualized queue counters have emulation jitter; the anomaly model fits its
initial calibration window; ground-truth congestion is bulk-active plus VoIP
RTT above the configured target; and a one-second RTT delta is only a jitter
estimate. Ryu must be running at the configured remote endpoint before a run.
The research testbed cannot run natively on Windows; use Linux or the supplied
privileged container. The qdisc stand-ins are endpoint agnostic, while their
performance still depends on host kernel and OVS behavior.

The unit tests do not start Mininet, Ryu, or OVS:

```bash
python3 -m pytest -q tests/test_research_manager.py
```

The legacy Stream A/B/C examples follow. To keep using the original
`scenario.py` comparison modes, run `python3 run_experiments.py --legacy
--repeats 3`.

```bash
docker compose build
docker compose run --rm testbed
```

Inside the container, two terminals (or `tmux`):

```bash
# terminal 1 — controller
ryu-manager controller/qos_controller.py

# terminal 2 — single run
python3 scenario.py --mode none      # baseline: raw congestion
python3 scenario.py --mode static    # static QoS queues
python3 scenario.py --mode adaptive  # static queues + adaptive manager
python3 monitoring/analyze.py results/<run-dir>   # re-plot later

# terminal 2 — full comparison (the end-sem result)
python3 run_experiments.py --legacy --repeats 3
python3 monitoring/compare.py results/<run-a> results/<run-b> ...   # re-compare later
```

Each run writes `results/<timestamp>-<mode>/` containing per-class iperf3
JSON, `samples.csv`, `decisions.csv` (adaptive only), `summary.csv` and
`metrics.png`. `run_experiments.py` additionally writes
`results/comparison/{comparison.csv,comparison.png,timeseries.png}`.

## Metrics reported

Per class, over the congested window (after bulk starts):
throughput, jitter, loss, average/max RTT, and **QoS recovery time** —
seconds after bulk injection until VoIP RTT is back under
`CONGESTION_RTT_MS` for `CLEAR_HOLD_TICKS` consecutive samples. For adaptive
runs the number of policy changes is also reported and each change is drawn
as a green line on the per-run graph. Aggregate reports also include reservation,
actuation, and controller-compute cost components.

## Tuning the adaptive policy

All knobs live in `common/config.py`:

* `CONGESTION_UTIL_THRESHOLD`, `CONGESTION_RTT_MS` — when to react
* `CLEAR_HOLD_TICKS` — hysteresis before declaring the link clear
* `ADAPTIVE.bulk_shrink_factor` / `bulk_restore_step` / `bulk_floor` — how hard and how fast bulk is throttled and restored
* `ADAPTIVE.voip_protect_min` / `video_protect_min` — guarantees raised during congestion

The policy logic can be exercised without Mininet by feeding synthetic
samples to `AdaptiveQoSManager._decide()` (see the unit check in git history).

## Verifying each stream in isolation

```bash
# A: topology + traffic
python3 topology/topo.py              # drops into Mininet CLI
mininet> voip iperf3 -c 10.0.0.10 -p 5001 -u -b 64K -l 160 -t 5

# B: queues actually exist on the bottleneck port
python3 controller/qos_setup.py apply s1-eth4
ovs-vsctl list queue
ovs-ofctl -O OpenFlow13 dump-flows s1     # look for set_queue:N

# C: sampler output is sane
head results/<run>/samples.csv
```

## Telemetry and RL ablation

The original `none`, `static`, and `adaptive` invocations remain available.
The added modes expose the two novelty axes independently:

| Mode | Controller | Signal |
|---|---|---|
| `rule-polling` | existing rule controller | 1 s polling |
| `rule-telemetry` | existing rule controller | 100 ms pushed telemetry |
| `rl-polling` | tabular Q policy | 1 s polling |
| `rl-telemetry` | tabular Q policy | 100 ms pushed telemetry |

Telemetry reports are exported over local UDP from an emulated sampling agent.
Small timestamped UDP probes use the class queues and report delay, jitter,
and sequence gaps. This is **INT-inspired emulated telemetry**, not true INT:
the project uses OVS/Linux HTB and host probes, not P4 switches. See
[ARCHITECTURE.md](ARCHITECTURE.md) for the measurement assumptions and limits.

Train a reproducible CPU-only surrogate policy before running either RL mode:

```bash
python3 controller/train_rl.py --samples results/<run>/samples.csv --output results/rl
```

Training writes `results/rl/rl_policy.json` and `rl_training.csv`. The trainer
uses seeded tabular Q-learning and can accept multiple previous sample files.
The surrogate makes training fast; it does not replace validation in Mininet.
The default action/reward configuration is in `common/config.py`.
After collecting new Mininet samples, recalibrate and continue an existing Q
table with `--resume-policy`:

```bash
python3 controller/train_rl.py --samples results/<new-run>/samples.csv --resume-policy results/rl/rl_policy.json --output results/rl
```

Run all six ablation modes with ten repeats (same timeline and a reproducible
seed sequence), or reduce the run count for a smoke check:

```bash
python3 run_experiments.py --repeats 10
python3 run_experiments.py --repeats 1 --t-cong 4 --t-end 10
python3 smoke_test.py --policy results/rl/rl_policy.json
```

The experiment runner writes per-run probe/telemetry overhead data and extends
the comparison output with 95% confidence intervals, detection latency,
reaction time, and policy-change counts. `monitoring/compare.py` creates
`comparison.csv`, `comparison.png`, `timeseries.png`, and `summary.md`.
The collector can also be selected independently with `scenario.py --signal-source polling|telemetry`; the ablation mode names choose their
corresponding source by default.
Measurements are not included in the repository as claimed outcomes; run the
experiments to produce them on the Docker/Mininet testbed. Focused local checks
run with `python3 -m unittest discover -s tests -v`.

## Notes

* The container needs `--privileged` and host networking (set in
  `docker-compose.yml`) because Mininet creates network namespaces and OVS
  talks to the kernel datapath.
* **Do not bump the base image past Ubuntu 20.04.** Ryu is unmaintained
  (last release 2019) and does not run on Python 3.10+: `eventlet==0.30.2`
  fails on 3.10's immutable `TimeoutError`, `dnspython==1.16.0` uses
  `collections.MutableMapping` (removed in 3.10), and upgrading either one
  breaks `ryu/app/wsgi.py`, which imports `eventlet.wsgi.ALREADY_HANDLED`.
  Python 3.8 on 20.04 is the combination Ryu actually works with.
* RL and adaptive queue updates reuse `qos_setup.update_queue()`; both read the
  collector's shared `latest` sample interface.
