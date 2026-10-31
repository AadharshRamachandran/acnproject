# Proposal implementation map

This map distinguishes requirements described in the proposal from the
literature-review and background slides. The latter motivate the work but are
not executable project features.

| Proposal item | Project implementation | Status and scope |
|---|---|---|
| Three traffic classes mapped to 5QI 1, 2 and 9 | `config.yaml`, `manager/budgets.py`, Mininet topology and Ryu classifier | Implemented as emulated VoIP, video and bulk flows. It does not signal to a 5G core. |
| Delay budget `Bᵢ = s × PDBᵢ`, with 10%, 15% and 20% share choices | `config.yaml`, `manager/budgets.py` | Implemented; per-class overrides are supported. |
| Holt main predictor and EWMA comparison, 2–3 seconds ahead | `manager/forecaster.py`; modes `fused_pi_forecast` and `fused_pi_ewma` | Implemented online with horizon-scored MAE gating. |
| Trigger at 80% predicted budget, current-delay fallback, release below 60% for 5 seconds | `manager/guards.py`, `run_research.py` | Implemented with configured ratios and hold time. |
| Fairness index at least 0.75, 1 Mbps bulk floor, 3-second dwell | `manager/guards.py`, `config.yaml` | Implemented. Fairness uses a measured-rate projection bounded by the proposed min/max rates. |
| Reactive baseline with 85% utilization / 20 ms VoIP RTT | `manager/detectors.py` (`ThresholdDetector`), `manager/engines.py` (`ReactiveController`), mode `reactive` | Implemented. Applies PROTECT minimums and halves the bulk ceiling (floor 100 kbit/s) each congested tick; returns to NORMAL after 3 calm seconds. Bypasses the shared guards. |
| Proactive NORMAL/PROTECT controller | `manager/engines.py` (`ProactiveController`), mode `proactive` | Implemented. Holt delay forecast (α 0.9, β 0.1, 2 s ahead) against 5QI budgets, measured-delay fallback, 0.8/0.6 hysteresis with 5 s clear hold, 3 s dwell, and a guardrail (1 Mbps bulk floor, Jain ≥ 0.75 on predicted satisfaction). Demand is the EWMA of measured queue send rates, not OpenFlow ingress counters. |
| No QoS, static HTB, reactive, FQ-CoDel and CAKE comparisons | `run_research.py`, `run_experiments.py` | Implemented as modes. CAKE needs host `sch_cake`; run it only where that qdisc is available. |
| Identical seeded traffic and scenarios | `run_experiments.py`, `scenario.py`, `config.yaml` | Implemented for matrix runs. Use matching seeds and scenarios for paired comparisons. |
| Throughput, jitter, loss, RTT, SLA violations, prediction lead, Jain fairness and bulk starvation | `run_research.py`, `analyze.py` | Implemented in per-run and aggregate summaries. Queue-derived one-way delay is an estimate, not a packet timestamp measurement. |
| Proposed predictive policy with low resource cost | `manager/engines.py`, mode `fused_pi_forecast_cost`, `config.yaml` | Added. It lowers calm-state guarantees to demand floors, raises VoIP/video guarantees during forecast or measured risk, targets video delivery above 95% of its configured rate during bulk load, and retains the bulk floor. |
| Cost reporting | `run_research.py`, `analyze.py` | Added normalized reservation, actuation and controller-compute cost components plus a weighted operating-cost index. These are operational proxies, not currency. |
| OVSDB queue-rate actuator shown in the diagram | `manager/actuator.py` | The experiment uses Linux `tc` HTB because OVS 2.13 in the supplied environment does not reliably apply OVSDB Linux-HTB rows. OpenFlow classification remains in Ryu/OVS. |

The cost-aware objective is evaluated together with its quality constraints:
VoIP RTT, video stability, 5QI delay violations and the bulk floor. A low cost
index by itself does not mean a mode is effective; in particular, no-QoS can
have zero HTB reservation while delivering poor QoS.

Run a direct comparison and analyze its results with:

```bash
docker compose run --rm testbed python3 run_experiments.py --modes none static reactive proactive fq_codel_ecn fused_pi_forecast fused_pi_forecast_cost --scenarios standard repeated_bursts flash_crowd capacity_step noisy_telemetry misclassified false_alarms --repeats 5 --output results/cost_aware_comparison
docker compose run --rm testbed python3 analyze.py --results results/cost_aware_comparison
```

Add `cake` to `--modes` only on a Linux host that provides the `sch_cake`
qdisc.

For an existing result directory, pass that same directory to `analyze.py`.
Do not compare aggregate rows with different valid-run counts as if they were a
balanced experiment.
