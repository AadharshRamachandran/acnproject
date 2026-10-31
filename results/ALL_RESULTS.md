# All results by scenario

Mean ± 95% CI half-width across seeds (no ± when the interval is zero or there is one run). — means the metric was not recorded in that result set.

Modes: none = report's noqos; static, reactive and proactive match the report; fused_pi_forecast is our own fused-detector PI controller with Holt forecast; fused_qlearning is our tabular Q-learning (RL) agent. The last two are not in the report. Scenarios: standard ≈ S1 steady, flash_crowd ≈ S2 bulk flood, video_step ≈ S3 video bursts, voip_surge ≈ S4 VoIP ramp.

fused_qlearning caveat: the guards blocked 58–64% of its actions in every run, above the project's 30% validity limit, so its column comes from `analyze.py --allow-rejected fused_qlearning` (results/report_modes/analysis_qlearning) rather than the main analysis. Its Q-table was trained offline on train.py's synthetic environment, not on these scenarios.

## standard

| Metric | Better | none | static | reactive | proactive | fused_pi_forecast | fused_qlearning |
|---|:---:|---:|---:|---:|---:|---:|---:|
| **Runs** | | 5 | 5 | 5 | 5 | 5 | 5 |
| **Delay budget (5QI share)** | | | | | | | |
| VoIP budget violation ratio | low | 0.800 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Video budget violation ratio | low | 0.800 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Bulk budget violation ratio | low | 0.800 | 0.829 | 0.829 | 0.829 | 0.829 | 0.829 |
| Protected (VoIP+video) violation ratio | low | 0.800 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| VoIP delay mean (ms) | low | 92.3 ± 1.5 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 |
| VoIP delay p95 (ms) | low | 130.0 ± 1.6 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 |
| Video delay mean (ms) | low | 92.6 ± 1.4 | 5.2 ± 0.1 | 5.3 ± 0.1 | 5.3 ± 0.1 | 5.2 ± 0.1 | 5.4 ± 0.1 |
| Video delay p95 (ms) | low | 131.6 ± 1.0 | 6.7 ± 0.8 | 6.3 ± 1.1 | 7.2 | 5.9 ± 1.1 | 7.2 |
| Bulk delay mean (ms) | low | 92.6 ± 1.3 | 227.7 ± 10.7 | 674.5 ± 61.3 | 224.4 ± 7.3 | 1237.1 ± 9.2 | 210.4 ± 17.4 |
| Bulk delay p95 (ms) | low | 130.4 ± 1.3 | 360.6 ± 7.3 | 1945.7 ± 167.5 | 368.6 ± 11.0 | 2356.5 ± 5.9 | 354.3 ± 4.7 |
| **RTT SLA** | | | | | | | |
| VoIP RTT violation ratio | low | 0.800 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Video RTT violation ratio | low | 0.800 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Bulk RTT violation ratio | low | 0.800 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| VoIP SLA violation ratio (RTT 20 ms) | low | 0.641 ± 0.004 | 0.004 ± 0.009 | 0.013 ± 0.011 | 0.009 ± 0.011 | 0.004 ± 0.009 | 0.000 |
| Video SLA violation ratio | low | 0.000 | 0.044 | 0.044 | 0.044 | 0.044 | 0.044 |
| SLA violation ratio after warm-up | low | 0.800 | 0.829 | 0.829 | 0.829 | 0.829 | 0.829 |
| Ground-truth violation fraction | low | 0.636 ± 0.011 | 0.004 ± 0.009 | 0.013 ± 0.011 | 0.009 ± 0.011 | 0.004 ± 0.009 | 0.000 |
| **VoIP** | | | | | | | |
| VoIP throughput (Mbps) | high | 0.100 | 0.100 | 0.100 | 0.100 | 0.100 | 0.100 |
| VoIP RTT mean (ms) | low | 78.7 ± 1.2 | 10.4 ± 0.3 | 10.6 ± 0.4 | 10.5 ± 0.3 | 10.4 ± 0.3 | 10.4 ± 0.1 |
| VoIP RTT p95 (ms) | low | 134.4 ± 1.5 | 10.4 ± 0.1 | 10.3 ± 0.1 | 10.4 ± 0.1 | 10.3 | 10.9 ± 0.4 |
| VoIP RTT p99 (ms) | low | 135.6 ± 1.7 | 10.9 ± 1.1 | 10.8 ± 0.9 | 10.6 ± 0.2 | 11.0 ± 1.0 | 12.3 ± 1.5 |
| VoIP jitter (ms) | low | 11.02 ± 0.69 | 0.28 ± 0.29 | 0.50 ± 0.38 | 0.35 ± 0.28 | 0.28 ± 0.38 | 0.34 ± 0.12 |
| VoIP probe loss (%) | low | 0.71 ± 0.66 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| VoIP iperf loss (%) | low | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| VoIP MOS estimate | high | 4.37 | 4.40 | 4.40 | 4.40 | 4.40 | 4.40 |
| **Video** | | | | | | | |
| Video throughput (Mbps) | high | 4.00 | 4.00 | 4.00 | 4.00 | 4.00 | 4.00 |
| Video stability fraction | high | 1.000 | 0.956 | 0.956 | 0.956 | 0.956 | 0.956 |
| Video throughput CV | low | 0.001 | 0.153 ± 0.001 | 0.153 | 0.153 | 0.153 | 0.153 |
| Video RTT mean (ms) | low | 79.0 ± 0.8 | 10.4 ± 0.3 | 10.4 ± 0.3 | 10.2 | 10.5 ± 0.4 | 10.5 ± 0.4 |
| Video RTT p95 (ms) | low | 135.6 ± 1.3 | 10.3 | 10.4 ± 0.1 | 10.3 ± 0.1 | 10.3 | 10.7 ± 0.3 |
| Video RTT p99 (ms) | low | 137.0 ± 0.9 | 10.4 ± 0.1 | 10.5 ± 0.2 | 10.4 ± 0.1 | 10.4 ± 0.1 | 11.3 ± 0.8 |
| Video jitter (ms) | low | 11.41 ± 0.62 | 0.24 ± 0.32 | 0.31 ± 0.34 | 0.07 ± 0.01 | 0.38 ± 0.41 | 0.41 ± 0.41 |
| Video probe loss (%) | low | 0.11 ± 0.22 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| Video iperf loss (%) | low | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| **Bulk** | | | | | | | |
| Bulk throughput (Mbps) | high | 5.65 ± 0.01 | 5.84 ± 0.05 | 3.44 ± 0.09 | 5.77 ± 0.01 | 1.71 ± 0.03 | 5.77 ± 0.02 |
| Bulk goodput (Mbps) | high | — | — | — | — | 1.14 ± 0.02 | 3.83 ± 0.01 |
| Bulk starvation (s) | low | 0.0 | 1.0 | 6.0 | 1.0 | 14.4 ± 0.5 | 1.0 |
| Bulk RTT mean (ms) | low | 79.0 ± 1.3 | 10.5 ± 0.5 | 10.4 ± 0.3 | 10.2 | 10.5 ± 0.3 | 10.4 ± 0.1 |
| Bulk RTT p95 (ms) | low | 134.4 ± 1.6 | 10.5 ± 0.2 | 10.4 ± 0.1 | 10.3 | 10.3 | 10.9 ± 0.5 |
| Bulk RTT p99 (ms) | low | 136.0 ± 1.4 | 10.6 ± 0.2 | 10.7 ± 0.2 | 10.5 ± 0.3 | 10.6 ± 0.3 | 11.5 ± 1.0 |
| Bulk jitter (ms) | low | 11.31 ± 0.29 | 0.34 ± 0.52 | 0.27 ± 0.36 | 0.08 ± 0.02 | 0.35 ± 0.35 | 0.26 ± 0.17 |
| Bulk probe loss (%) | low | 0.33 ± 0.65 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| **Fairness** | | | | | | | |
| Jain index (vs class targets) | high | 0.611 ± 0.001 | 0.611 | 0.738 | 0.611 | 0.850 | 0.612 |
| Jain index (vs offered load) | high | — | — | — | — | 0.863 ± 0.003 | 1.000 |
| **Control** | | | | | | | |
| Policy changes | low | 0.0 | 0.0 | 31.4 ± 1.9 | 0.0 | 6.0 | 8.0 |
| Policy flaps | low | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Decisions logged | — | 0.0 | 0.0 | 31.4 ± 1.9 | 0.0 | 6.0 | 22.0 |
| Rejection rate | low | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.636 |
| Prediction lead (s) | high | — | — | 9.4 ± 7.5 | — | 15.0 | 16.0 |
| Forecast prediction lead (s) | high | — | — | — | 0.0 | 0.0 | — |
| Forecast MAE | low | 2.011 ± 0.134 | 2.212 ± 0.163 | 14.755 ± 1.007 | 1.391 ± 0.115 | 14.258 ± 0.403 | 2.087 ± 0.367 |
| Detection latency (s) | low | — | — | 0.0 | — | — | — |
| Time to act (s) | low | — | — | -9.4 ± 7.5 | — | -15.0 | -16.0 |
| Time to recover (s) | low | — | — | 2.0 | — | 1.0 | — |
| Actuation latency (s) | low | — | — | 0.074 ± 0.002 | — | 0.079 ± 0.005 | 0.029 ± 0.002 |
| Detector false-positive rate | low | 0.000 | 0.000 | 0.418 ± 0.044 | 0.000 | 0.636 | 0.000 |
| Detector missed-detection rate | low | 1.000 | 1.000 | 0.000 | 1.000 | 0.000 | 0.000 |
| False-alarm QoS cost | low | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| **Cost** | | | | | | | |
| Reserved rate (Mbps) | low | 0.00 | 5.50 | 6.31 ± 0.05 | 5.50 | 5.50 | 5.78 |
| Reservation fraction | low | 0.000 | 0.550 | 0.631 ± 0.005 | 0.550 | 0.550 | 0.578 |
| Actuation fraction | low | 0.000 | 0.000 | 1.000 | 0.000 | 1.000 | 1.000 |
| Compute fraction | low | 0.012 ± 0.002 | 0.010 ± 0.001 | 0.040 ± 0.003 | 0.011 ± 0.001 | 0.025 ± 0.002 | 0.028 ± 0.003 |
| Controller CPU (s/tick) | low | 0.0121 ± 0.0024 | 0.0103 ± 0.0012 | 0.0400 ± 0.0027 | 0.0110 ± 0.0014 | 0.0250 ± 0.0016 | 0.0280 ± 0.0026 |
| Operating cost index | low | 0.001 | 0.386 | 0.646 ± 0.004 | 0.386 | 0.587 | 0.608 |
| **Telemetry** | | | | | | | |
| Queue stats coverage | high | 0.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| Queue video rate (Mbps) | — | 4.00 | 4.03 | 4.03 | 4.03 | 4.03 | 4.03 |
| Queue/iperf video rate ratio | ≈1 | 1.000 | 1.008 ± 0.001 | 1.008 | 1.009 | 1.008 | 1.008 |

## flash_crowd

| Metric | Better | none | static | reactive | proactive | fused_pi_forecast | fused_qlearning |
|---|:---:|---:|---:|---:|---:|---:|---:|
| **Runs** | | 5 | 5 | 5 | 5 | 5 | 5 |
| **Delay budget (5QI share)** | | | | | | | |
| VoIP budget violation ratio | low | 0.806 ± 0.011 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Video budget violation ratio | low | 0.800 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Bulk budget violation ratio | low | 0.800 | 0.829 | 0.829 | 0.829 | 0.829 | 0.829 |
| Protected (VoIP+video) violation ratio | low | 0.806 ± 0.011 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| VoIP delay mean (ms) | low | 99.0 ± 1.7 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 |
| VoIP delay p95 (ms) | low | 132.2 ± 1.7 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 |
| Video delay mean (ms) | low | 98.5 ± 2.0 | 5.3 ± 0.1 | 5.3 | 5.3 | 5.2 ± 0.1 | 5.4 ± 0.2 |
| Video delay p95 (ms) | low | 131.4 ± 0.8 | 7.2 | 7.2 ± 0.1 | 7.2 | 6.3 ± 1.1 | 7.2 |
| Bulk delay mean (ms) | low | 98.3 ± 2.1 | 273.5 ± 4.6 | 744.8 ± 36.1 | 275.1 ± 4.9 | 1443.8 ± 23.9 | 261.8 ± 14.6 |
| Bulk delay p95 (ms) | low | 130.8 ± 1.3 | 376.7 ± 4.8 | 2046.9 ± 83.3 | 381.4 ± 3.0 | 2245.0 ± 44.0 | 375.6 ± 4.8 |
| **RTT SLA** | | | | | | | |
| VoIP RTT violation ratio | low | 0.800 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Video RTT violation ratio | low | 0.800 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Bulk RTT violation ratio | low | 0.800 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| VoIP SLA violation ratio (RTT 20 ms) | low | 0.644 | 0.004 ± 0.009 | 0.013 ± 0.011 | 0.009 ± 0.011 | 0.004 ± 0.009 | 0.009 ± 0.011 |
| Video SLA violation ratio | low | 0.000 | 0.040 ± 0.009 | 0.044 | 0.044 | 0.044 | 0.044 |
| SLA violation ratio after warm-up | low | 0.806 ± 0.011 | 0.829 | 0.829 | 0.829 | 0.829 | 0.829 |
| Ground-truth violation fraction | low | 0.644 | 0.004 ± 0.009 | 0.013 ± 0.011 | 0.009 ± 0.011 | 0.004 ± 0.009 | 0.009 ± 0.011 |
| **VoIP** | | | | | | | |
| VoIP throughput (Mbps) | high | 0.100 | 0.100 | 0.100 | 0.100 | 0.100 | 0.100 |
| VoIP RTT mean (ms) | low | 83.5 ± 1.4 | 10.4 ± 0.3 | 10.8 ± 0.4 | 10.5 ± 0.3 | 10.4 ± 0.3 | 10.6 ± 0.3 |
| VoIP RTT p95 (ms) | low | 137.0 ± 1.4 | 10.4 | 10.3 ± 0.1 | 10.4 ± 0.1 | 10.3 | 10.7 ± 0.2 |
| VoIP RTT p99 (ms) | low | 138.0 ± 1.8 | 10.4 ± 0.1 | 12.1 ± 3.1 | 10.7 ± 0.5 | 10.4 ± 0.1 | 11.4 ± 0.5 |
| VoIP jitter (ms) | low | 10.01 ± 1.60 | 0.19 ± 0.27 | 0.65 ± 0.48 | 0.35 ± 0.33 | 0.28 ± 0.27 | 0.56 ± 0.34 |
| VoIP probe loss (%) | low | 1.41 ± 2.31 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| VoIP iperf loss (%) | low | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| VoIP MOS estimate | high | 4.37 | 4.40 | 4.40 | 4.40 | 4.40 | 4.40 |
| **Video** | | | | | | | |
| Video throughput (Mbps) | high | 4.00 | 4.00 | 4.00 | 4.00 | 4.00 | 4.00 |
| Video stability fraction | high | 1.000 | 0.960 ± 0.009 | 0.956 | 0.956 | 0.956 | 0.956 |
| Video throughput CV | low | 0.001 | 0.153 ± 0.001 | 0.153 | 0.153 | 0.153 | 0.153 |
| Video RTT mean (ms) | low | 84.0 ± 1.4 | 10.2 | 10.3 ± 0.1 | 10.5 ± 0.3 | 10.4 ± 0.3 | 10.6 ± 0.3 |
| Video RTT p95 (ms) | low | 135.8 ± 1.1 | 10.4 | 10.3 | 10.3 | 10.4 ± 0.1 | 10.7 ± 0.4 |
| Video RTT p99 (ms) | low | 137.2 ± 1.1 | 10.5 ± 0.1 | 10.4 ± 0.1 | 10.4 ± 0.1 | 11.3 ± 1.2 | 11.8 ± 0.9 |
| Video jitter (ms) | low | 9.73 ± 1.45 | 0.09 ± 0.02 | 0.17 ± 0.16 | 0.34 ± 0.33 | 0.32 ± 0.35 | 0.56 ± 0.31 |
| Video probe loss (%) | low | 1.08 ± 0.60 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| Video iperf loss (%) | low | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| **Bulk** | | | | | | | |
| Bulk throughput (Mbps) | high | 5.76 ± 0.02 | 5.90 ± 0.04 | 3.47 ± 0.05 | 5.92 ± 0.02 | 1.57 ± 0.02 | 5.93 ± 0.02 |
| Bulk goodput (Mbps) | high | — | — | — | 3.91 | 1.04 ± 0.02 | 3.93 ± 0.02 |
| Bulk starvation (s) | low | 0.0 | 1.0 | 6.0 | 1.0 | 14.4 ± 0.5 | 1.0 |
| Bulk RTT mean (ms) | low | 84.3 ± 1.7 | 10.2 | 10.3 ± 0.1 | 10.2 | 10.3 | 10.3 ± 0.1 |
| Bulk RTT p95 (ms) | low | 135.4 ± 1.3 | 10.4 | 10.3 | 10.4 | 10.4 ± 0.1 | 10.7 ± 0.3 |
| Bulk RTT p99 (ms) | low | 136.4 ± 1.6 | 10.5 ± 0.2 | 10.5 ± 0.1 | 10.4 ± 0.1 | 10.7 ± 0.4 | 11.2 ± 0.5 |
| Bulk jitter (ms) | low | 9.33 ± 1.28 | 0.08 ± 0.04 | 0.16 ± 0.16 | 0.12 ± 0.08 | 0.14 ± 0.08 | 0.24 ± 0.14 |
| Bulk probe loss (%) | low | 0.95 ± 1.32 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| **Fairness** | | | | | | | |
| Jain index (vs class targets) | high | 0.609 ± 0.002 | 0.611 ± 0.001 | 0.737 | 0.611 | 0.850 | 0.611 |
| Jain index (vs offered load) | high | — | — | — | 1.000 | 0.850 ± 0.002 | 1.000 |
| **Control** | | | | | | | |
| Policy changes | low | 0.0 | 0.0 | 31.4 ± 1.9 | 0.0 | 6.0 | 8.0 |
| Policy flaps | low | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Decisions logged | — | 0.0 | 0.0 | 31.4 ± 1.9 | 0.0 | 6.0 | 22.0 |
| Rejection rate | low | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.636 |
| Prediction lead (s) | high | — | — | 9.4 ± 7.5 | — | 15.0 | 16.0 |
| Forecast prediction lead (s) | high | — | — | — | 0.0 | — | — |
| Forecast MAE | low | 2.369 ± 0.083 | 2.130 ± 0.056 | 17.165 ± 0.691 | 1.459 ± 0.036 | 15.197 ± 0.799 | 2.280 ± 0.201 |
| Detection latency (s) | low | — | — | 0.0 | — | — | — |
| Time to act (s) | low | — | — | -9.6 ± 7.3 | — | -15.0 | -16.0 |
| Time to recover (s) | low | — | 27.0 | 1.8 ± 0.4 | — | 1.0 | — |
| Actuation latency (s) | low | — | — | 0.079 ± 0.007 | — | 0.080 ± 0.007 | 0.028 ± 0.002 |
| Detector false-positive rate | low | 0.000 | 0.000 | 0.422 ± 0.040 | 0.000 | 0.638 ± 0.003 | 0.000 |
| Detector missed-detection rate | low | 1.000 | 1.000 | 0.000 | 1.000 | 0.000 | 0.000 |
| False-alarm QoS cost | low | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| **Cost** | | | | | | | |
| Reserved rate (Mbps) | low | 0.00 | 5.50 | 6.31 ± 0.05 | 5.50 | 5.50 | 5.78 |
| Reservation fraction | low | 0.000 | 0.550 | 0.631 ± 0.005 | 0.550 | 0.550 | 0.578 |
| Actuation fraction | low | 0.000 | 0.000 | 1.000 | 0.000 | 1.000 | 1.000 |
| Compute fraction | low | 0.010 ± 0.001 | 0.018 ± 0.018 | 0.041 ± 0.003 | 0.011 ± 0.001 | 0.031 ± 0.008 | 0.028 ± 0.001 |
| Controller CPU (s/tick) | low | 0.0097 ± 0.0013 | 0.0181 ± 0.0177 | 0.0411 ± 0.0029 | 0.0105 ± 0.0012 | 0.0307 ± 0.0076 | 0.0280 ± 0.0011 |
| Operating cost index | low | 0.001 | 0.387 ± 0.002 | 0.646 ± 0.003 | 0.386 | 0.588 ± 0.001 | 0.608 |
| **Telemetry** | | | | | | | |
| Queue stats coverage | high | 0.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| Queue video rate (Mbps) | — | 4.00 | 4.03 | 4.03 | 4.03 | 4.03 | 4.03 |
| Queue/iperf video rate ratio | ≈1 | 1.000 | 1.008 ± 0.001 | 1.008 | 1.009 | 1.008 | 1.009 |

## video_step

| Metric | Better | none | static | reactive | proactive | fused_pi_forecast | fused_qlearning |
|---|:---:|---:|---:|---:|---:|---:|---:|
| **Runs** | | 5 | 5 | 5 | 5 | 5 | 5 |
| **Delay budget (5QI share)** | | | | | | | |
| VoIP budget violation ratio | low | 0.960 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Video budget violation ratio | low | 0.960 | 0.680 | 0.100 | 0.200 | 0.004 ± 0.008 | 0.680 |
| Bulk budget violation ratio | low | 0.960 | 0.980 | 0.980 | 0.980 | 0.980 | 0.980 |
| Protected (VoIP+video) violation ratio | low | 0.960 | 0.680 | 0.100 | 0.200 | 0.004 ± 0.008 | 0.680 |
| VoIP delay mean (ms) | low | 95.0 ± 1.3 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 |
| VoIP delay p95 (ms) | low | 126.2 ± 2.4 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 |
| Video delay mean (ms) | low | 94.6 ± 1.9 | 114.2 ± 0.1 | 21.3 ± 0.1 | 37.6 ± 0.1 | 5.6 ± 0.4 | 114.6 ± 0.1 |
| Video delay p95 (ms) | low | 124.4 ± 3.9 | 167.1 ± 0.3 | 162.9 ± 0.7 | 165.9 ± 0.5 | 6.5 ± 0.7 | 168.5 ± 0.7 |
| Bulk delay mean (ms) | low | 94.7 ± 1.4 | 344.4 ± 8.8 | 1066.6 ± 25.1 | 466.1 ± 20.6 | 1565.8 ± 49.6 | 350.7 ± 11.6 |
| Bulk delay p95 (ms) | low | 123.2 ± 3.4 | 520.9 ± 20.6 | 2296.4 ± 90.6 | 804.5 ± 40.3 | 2216.2 ± 40.9 | 526.4 ± 17.6 |
| **RTT SLA** | | | | | | | |
| VoIP RTT violation ratio | low | 0.960 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Video RTT violation ratio | low | 0.960 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Bulk RTT violation ratio | low | 0.960 | 0.000 | 0.004 ± 0.008 | 0.000 | 0.000 | 0.000 |
| VoIP SLA violation ratio (RTT 20 ms) | low | 0.816 ± 0.001 | 0.003 ± 0.007 | 0.003 ± 0.007 | 0.003 ± 0.007 | 0.003 ± 0.007 | 0.003 ± 0.007 |
| Video SLA violation ratio | low | 0.000 | 0.033 | 0.033 | 0.033 | 0.033 | 0.033 |
| SLA violation ratio after warm-up | low | 0.960 | 0.980 | 0.980 | 0.980 | 0.980 | 0.980 |
| Ground-truth violation fraction | low | 0.813 ± 0.007 | 0.003 ± 0.007 | 0.003 ± 0.007 | 0.003 ± 0.007 | 0.003 ± 0.007 | 0.003 ± 0.007 |
| **VoIP** | | | | | | | |
| VoIP throughput (Mbps) | high | 0.100 | 0.100 | 0.100 | 0.100 | 0.100 | 0.100 |
| VoIP RTT mean (ms) | low | 85.5 ± 1.0 | 10.4 ± 0.3 | 10.4 ± 0.2 | 10.4 ± 0.2 | 10.5 ± 0.4 | 10.6 ± 0.4 |
| VoIP RTT p95 (ms) | low | 131.2 ± 2.4 | 10.3 | 10.5 ± 0.1 | 10.4 ± 0.1 | 10.4 ± 0.1 | 11.3 ± 0.8 |
| VoIP RTT p99 (ms) | low | 134.8 ± 2.6 | 10.5 ± 0.1 | 10.8 ± 0.2 | 10.6 ± 0.2 | 10.4 | 12.1 ± 1.1 |
| VoIP jitter (ms) | low | 13.85 ± 1.38 | 0.22 ± 0.31 | 0.23 ± 0.20 | 0.23 ± 0.17 | 0.30 ± 0.41 | 0.52 ± 0.40 |
| VoIP probe loss (%) | low | 1.00 ± 0.64 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| VoIP iperf loss (%) | low | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| VoIP MOS estimate | high | 4.37 | 4.40 | 4.40 | 4.40 | 4.40 | 4.40 |
| **Video** | | | | | | | |
| Video throughput (Mbps) | high | 5.69 ± 0.01 | 5.74 | 5.74 | 5.74 | 5.73 | 5.73 |
| Video stability fraction | high | 1.000 | 0.967 | 0.967 | 0.967 | 0.967 | 0.967 |
| Video throughput CV | low | 0.257 | 0.221 | 0.302 | 0.295 ± 0.001 | 0.294 ± 0.001 | 0.221 ± 0.001 |
| Video RTT mean (ms) | low | 84.9 ± 1.6 | 10.3 ± 0.1 | 10.5 ± 0.4 | 10.3 ± 0.2 | 10.3 | 10.7 ± 0.4 |
| Video RTT p95 (ms) | low | 129.4 ± 3.9 | 10.4 ± 0.1 | 10.4 | 10.4 ± 0.1 | 10.4 ± 0.1 | 11.3 ± 0.7 |
| Video RTT p99 (ms) | low | 136.6 ± 0.8 | 10.5 ± 0.1 | 11.0 ± 0.4 | 10.5 ± 0.1 | 10.8 ± 0.5 | 12.4 ± 1.6 |
| Video jitter (ms) | low | 13.81 ± 1.16 | 0.19 ± 0.21 | 0.43 ± 0.39 | 0.17 ± 0.18 | 0.15 ± 0.07 | 0.62 ± 0.42 |
| Video probe loss (%) | low | 0.75 ± 0.66 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| Video iperf loss (%) | low | 0.08 ± 0.02 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| **Bulk** | | | | | | | |
| Bulk throughput (Mbps) | high | 3.59 ± 0.02 | 4.50 ± 0.03 | 2.10 ± 0.03 | 3.83 ± 0.03 | 1.48 ± 0.05 | 4.48 ± 0.03 |
| Bulk goodput (Mbps) | high | — | 3.75 ± 0.02 | 1.75 ± 0.02 | 3.19 ± 0.03 | 1.23 ± 0.04 | 3.72 ± 0.03 |
| Bulk starvation (s) | low | 0.0 | 1.0 | 18.0 | 1.0 | 22.4 ± 1.0 | 1.0 |
| Bulk RTT mean (ms) | low | 85.9 ± 1.0 | 10.2 | 12.6 ± 4.5 | 10.4 ± 0.4 | 10.4 ± 0.2 | 10.5 ± 0.2 |
| Bulk RTT p95 (ms) | low | 128.2 ± 3.4 | 10.4 ± 0.1 | 10.5 ± 0.1 | 10.4 ± 0.1 | 10.5 | 11.2 ± 0.4 |
| Bulk RTT p99 (ms) | low | 134.2 ± 3.1 | 10.7 ± 0.4 | 10.8 ± 0.4 | 10.6 ± 0.1 | 11.9 ± 2.3 | 12.5 ± 0.7 |
| Bulk jitter (ms) | low | 13.80 ± 0.70 | 0.11 ± 0.05 | 4.82 ± 9.11 | 0.28 ± 0.36 | 0.29 ± 0.16 | 0.46 ± 0.24 |
| Bulk probe loss (%) | low | 1.74 ± 1.36 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| **Fairness** | | | | | | | |
| Jain index (vs class targets) | high | 0.769 ± 0.002 | 0.701 | 0.805 ± 0.001 | 0.762 | 0.872 | 0.702 |
| Jain index (vs offered load) | high | — | 1.000 | 0.934 ± 0.002 | 1.000 | 0.875 ± 0.005 | 1.000 |
| **Control** | | | | | | | |
| Policy changes | low | 0.0 | 0.0 | 49.8 ± 1.6 | 8.0 | 5.0 | 6.0 |
| Policy flaps | low | 0.0 | 0.0 | 0.0 | 3.0 | 0.0 | 0.0 |
| Decisions logged | — | 0.0 | 0.0 | 49.8 ± 1.6 | 8.0 | 5.0 | 16.0 |
| Rejection rate | low | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.625 |
| Protect lead time (s) | high | — | — | 17.2 ± 4.3 | 0.0 | 49.0 | 26.0 |
| Prediction lead (s) | high | — | — | 2.2 ± 4.3 | -15.0 | 10.0 | 11.0 |
| Forecast prediction lead (s) | high | — | — | — | 0.0 | 0.0 | — |
| Forecast MAE | low | 1.972 ± 0.105 | 3.497 ± 0.320 | 21.035 ± 0.807 | 5.259 ± 0.457 | 14.481 ± 0.403 | 3.168 ± 0.312 |
| Detection latency (s) | low | — | — | 0.0 | — | — | 22.5 ± 38.2 |
| Time to act (s) | low | — | — | -2.2 ± 4.3 | 15.0 | -10.0 | -11.0 |
| Time to recover (s) | low | — | — | 2.0 | — | 3.0 | — |
| Actuation latency (s) | low | — | — | 0.084 ± 0.004 | 0.082 ± 0.007 | 0.084 ± 0.006 | 0.031 ± 0.004 |
| Detector false-positive rate | low | 0.000 | 0.000 | 0.554 ± 0.030 | 0.000 | 0.807 | 0.000 |
| Detector missed-detection rate | low | 1.000 | 1.000 | 0.000 | 1.000 | 0.000 | 0.000 |
| False-alarm QoS cost | low | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| **Cost** | | | | | | | |
| Reserved rate (Mbps) | low | 0.00 | 5.50 | 6.39 ± 0.03 | 6.10 | 5.50 | 5.89 |
| Reservation fraction | low | 0.000 | 0.550 | 0.639 ± 0.003 | 0.610 | 0.550 | 0.589 |
| Actuation fraction | low | 0.000 | 0.000 | 1.000 | 1.000 | 0.833 | 1.000 |
| Compute fraction | low | 0.013 ± 0.004 | 0.010 ± 0.001 | 0.053 ± 0.004 | 0.017 ± 0.001 | 0.022 ± 0.002 | 0.025 ± 0.002 |
| Controller CPU (s/tick) | low | 0.0131 ± 0.0040 | 0.0103 ± 0.0006 | 0.0529 ± 0.0039 | 0.0174 ± 0.0012 | 0.0219 ± 0.0022 | 0.0249 ± 0.0021 |
| Operating cost index | low | 0.001 | 0.386 | 0.652 ± 0.002 | 0.629 | 0.554 | 0.615 |
| **Telemetry** | | | | | | | |
| Queue stats coverage | high | 0.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| Queue video rate (Mbps) | — | 5.75 | 5.09 | 5.79 | 5.66 | 5.81 | 5.09 ± 0.01 |
| Queue/iperf video rate ratio | ≈1 | 1.011 ± 0.002 | 0.888 | 1.009 | 0.987 ± 0.001 | 1.014 | 0.887 ± 0.001 |

## voip_surge

| Metric | Better | none | static | reactive | proactive | fused_pi_forecast | fused_qlearning |
|---|:---:|---:|---:|---:|---:|---:|---:|
| **Runs** | | 5 | 5 | 5 | 5 | 5 | 5 |
| **Delay budget (5QI share)** | | | | | | | |
| VoIP budget violation ratio | low | 0.960 | 0.300 | 0.060 | 0.056 ± 0.029 | 0.000 | 0.300 |
| Video budget violation ratio | low | 0.960 | 0.000 | 0.000 | 0.004 ± 0.008 | 0.000 | 0.012 ± 0.010 |
| Bulk budget violation ratio | low | 0.956 ± 0.008 | 0.980 | 0.980 | 0.980 | 0.980 | 0.980 |
| Protected (VoIP+video) violation ratio | low | 0.960 | 0.300 | 0.060 | 0.060 ± 0.033 | 0.000 | 0.312 ± 0.010 |
| VoIP delay mean (ms) | low | 86.9 ± 3.9 | 52.1 ± 0.1 | 14.6 ± 0.1 | 14.4 ± 4.3 | 5.1 | 52.3 ± 0.1 |
| VoIP delay p95 (ms) | low | 131.4 ± 1.7 | 162.5 ± 0.7 | 6.9 ± 0.6 | 93.8 ± 68.7 | 5.6 | 162.6 ± 0.2 |
| Video delay mean (ms) | low | 86.7 ± 3.9 | 5.4 ± 0.1 | 5.2 ± 0.1 | 5.5 ± 0.2 | 5.3 ± 0.1 | 5.7 ± 0.2 |
| Video delay p95 (ms) | low | 130.6 ± 1.5 | 7.2 | 7.2 | 7.2 | 7.2 | 7.2 |
| Bulk delay mean (ms) | low | 87.1 ± 3.8 | 292.1 ± 11.6 | 932.0 ± 22.4 | 313.5 ± 8.1 | 1589.9 ± 47.8 | 281.0 ± 27.2 |
| Bulk delay p95 (ms) | low | 129.8 ± 0.7 | 392.0 ± 10.4 | 2071.2 ± 136.4 | 443.2 ± 25.6 | 2223.9 ± 64.8 | 393.4 ± 9.0 |
| **RTT SLA** | | | | | | | |
| VoIP RTT violation ratio | low | 0.960 | 0.000 | 0.000 | 0.000 | 0.000 | 0.004 ± 0.008 |
| Video RTT violation ratio | low | 0.960 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Bulk RTT violation ratio | low | 0.700 ± 0.021 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| VoIP SLA violation ratio (RTT 20 ms) | low | 0.816 ± 0.001 | 0.003 ± 0.007 | 0.000 | 0.000 | 0.007 ± 0.008 | 0.013 ± 0.007 |
| Video SLA violation ratio | low | 0.007 ± 0.013 | 0.033 | 0.033 | 0.033 | 0.033 | 0.047 ± 0.026 |
| SLA violation ratio after warm-up | low | 0.960 | 0.980 | 0.980 | 0.980 | 0.980 | 0.984 ± 0.008 |
| Ground-truth violation fraction | low | 0.813 ± 0.007 | 0.003 ± 0.007 | 0.000 | 0.000 | 0.007 ± 0.008 | 0.013 ± 0.007 |
| **VoIP** | | | | | | | |
| VoIP throughput (Mbps) | high | 0.475 ± 0.001 | 0.475 | 0.475 | 0.475 | 0.475 | 0.475 |
| VoIP RTT mean (ms) | low | 78.8 ± 3.6 | 10.3 ± 0.2 | 10.2 | 10.2 | 10.5 ± 0.3 | 10.8 ± 0.3 |
| VoIP RTT p95 (ms) | low | 136.4 ± 1.7 | 10.3 | 10.3 ± 0.1 | 10.4 | 10.4 ± 0.1 | 10.8 ± 0.2 |
| VoIP RTT p99 (ms) | low | 172.2 ± 69.0 | 11.1 ± 1.2 | 10.3 | 10.5 ± 0.1 | 10.7 ± 0.2 | 12.2 ± 1.0 |
| VoIP jitter (ms) | low | 14.23 ± 3.20 | 0.18 ± 0.22 | 0.08 ± 0.05 | 0.08 ± 0.02 | 0.34 ± 0.29 | 0.73 ± 0.33 |
| VoIP probe loss (%) | low | 2.11 ± 1.68 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| VoIP iperf loss (%) | low | 1.41 ± 0.52 | 24.63 ± 0.40 | 4.01 ± 0.07 | 4.05 ± 2.28 | 0.00 | 24.15 ± 0.25 |
| VoIP MOS estimate | high | 4.37 | 4.40 | 4.40 | 4.40 | 4.40 | 4.40 |
| **Video** | | | | | | | |
| Video throughput (Mbps) | high | 4.00 | 4.00 | 4.00 | 4.00 | 4.00 | 4.00 |
| Video stability fraction | high | 0.993 ± 0.013 | 0.967 | 0.967 | 0.967 | 0.967 | 0.953 ± 0.026 |
| Video throughput CV | low | 0.011 ± 0.019 | 0.132 | 0.132 | 0.133 ± 0.001 | 0.132 | 0.149 ± 0.033 |
| Video RTT mean (ms) | low | 78.7 ± 3.0 | 10.3 ± 0.2 | 10.3 ± 0.2 | 10.4 ± 0.3 | 10.4 ± 0.2 | 10.8 ± 0.3 |
| Video RTT p95 (ms) | low | 135.6 ± 1.5 | 10.3 | 10.3 | 10.5 ± 0.3 | 10.4 ± 0.1 | 11.1 ± 0.4 |
| Video RTT p99 (ms) | low | 172.0 ± 69.1 | 10.4 ± 0.1 | 10.5 ± 0.2 | 12.7 ± 3.9 | 11.0 ± 1.1 | 13.8 ± 4.2 |
| Video jitter (ms) | low | 14.43 ± 3.19 | 0.17 ± 0.21 | 0.25 ± 0.24 | 0.32 ± 0.39 | 0.31 ± 0.30 | 0.75 ± 0.28 |
| Video probe loss (%) | low | 1.10 ± 0.59 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| Video iperf loss (%) | low | 0.28 ± 0.54 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| **Bulk** | | | | | | | |
| Bulk throughput (Mbps) | high | 5.09 ± 0.01 | 5.45 ± 0.03 | 3.01 ± 0.05 | 5.06 ± 0.09 | 1.48 ± 0.05 | 5.45 ± 0.01 |
| Bulk goodput (Mbps) | high | — | — | — | — | 1.23 ± 0.04 | 4.53 ± 0.01 |
| Bulk starvation (s) | low | 0.0 | 1.0 | 13.0 | 1.0 | 22.2 ± 1.9 | 1.2 ± 0.4 |
| Bulk RTT mean (ms) | low | 79.2 ± 3.5 | 10.2 | 10.3 ± 0.2 | 10.6 ± 0.5 | 10.2 | 10.8 ± 1.0 |
| Bulk RTT p95 (ms) | low | 134.8 ± 0.7 | 10.3 | 10.4 ± 0.1 | 10.4 ± 0.1 | 10.4 ± 0.1 | 10.7 ± 0.2 |
| Bulk RTT p99 (ms) | low | 171.8 ± 70.2 | 10.4 ± 0.1 | 10.4 ± 0.1 | 10.7 ± 0.2 | 10.5 ± 0.1 | 11.3 ± 0.5 |
| Bulk jitter (ms) | low | 14.28 ± 3.57 | 0.06 ± 0.02 | 0.19 ± 0.24 | 0.52 ± 0.53 | 0.07 ± 0.02 | 0.72 ± 1.06 |
| Bulk probe loss (%) | low | 1.75 ± 1.32 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| **Fairness** | | | | | | | |
| Jain index (vs class targets) | high | 0.588 ± 0.002 | 0.626 | 0.685 | 0.595 ± 0.005 | 0.747 | 0.626 ± 0.001 |
| Jain index (vs offered load) | high | — | — | — | — | 0.875 ± 0.005 | 1.000 |
| **Control** | | | | | | | |
| Policy changes | low | 0.0 | 0.0 | 49.0 | 4.0 ± 2.1 | 5.0 | 6.6 ± 0.8 |
| Policy flaps | low | 0.0 | 0.0 | 0.0 | 1.0 ± 1.1 | 0.0 | 0.0 |
| Decisions logged | — | 0.0 | 0.0 | 49.0 | 4.0 ± 2.1 | 5.0 | 16.8 ± 1.1 |
| Rejection rate | low | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.608 ± 0.020 |
| Protect lead time (s) | high | — | — | 10.0 | 0.0 | — | 17.8 ± 4.3 |
| Prediction lead (s) | high | — | — | 0.0 | -8.0 ± 3.9 | 10.0 | 10.8 ± 0.4 |
| Forecast prediction lead (s) | high | — | — | — | 0.0 | 0.0 | — |
| Forecast MAE | low | 3.250 ± 0.766 | 3.911 ± 0.005 | 20.566 ± 0.382 | 2.126 ± 0.069 | 14.368 ± 0.255 | 3.924 ± 0.008 |
| Detection latency (s) | low | — | — | 0.0 | — | — | — |
| Time to act (s) | low | — | — | 0.0 | 6.0 ± 7.8 | -10.0 | -11.0 |
| Time to recover (s) | low | 19.0 | — | 2.0 | 20.2 ± 9.4 | 3.0 | 19.0 |
| Actuation latency (s) | low | — | — | 0.072 ± 0.003 | 0.090 ± 0.011 | 0.078 ± 0.004 | 0.039 ± 0.010 |
| Detector false-positive rate | low | 0.000 | 0.000 | 0.512 | 0.000 | 0.807 | 0.072 ± 0.102 |
| Detector missed-detection rate | low | 1.000 | 1.000 | 0.000 | 1.000 | 0.000 | 0.000 |
| False-alarm QoS cost | low | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| **Cost** | | | | | | | |
| Reserved rate (Mbps) | low | 0.00 | 5.50 | 6.41 | 5.94 ± 0.08 | 5.50 | 5.89 |
| Reservation fraction | low | 0.000 | 0.550 | 0.641 | 0.594 ± 0.008 | 0.550 | 0.589 |
| Actuation fraction | low | 0.000 | 0.000 | 1.000 | 0.600 ± 0.244 | 0.833 | 1.000 |
| Compute fraction | low | 0.011 ± 0.004 | 0.009 ± 0.001 | 0.044 ± 0.002 | 0.016 ± 0.003 | 0.022 ± 0.001 | 0.026 ± 0.001 |
| Controller CPU (s/tick) | low | 0.0111 ± 0.0042 | 0.0087 ± 0.0006 | 0.0441 ± 0.0023 | 0.0156 ± 0.0034 | 0.0216 ± 0.0015 | 0.0261 ± 0.0015 |
| Operating cost index | low | 0.001 | 0.386 | 0.653 | 0.537 ± 0.051 | 0.554 | 0.615 |
| **Telemetry** | | | | | | | |
| Queue stats coverage | high | 0.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| Queue video rate (Mbps) | — | 3.99 ± 0.01 | 4.06 | 4.06 | 4.06 | 4.06 | 4.06 ± 0.01 |
| Queue/iperf video rate ratio | ≈1 | 0.998 ± 0.004 | 1.015 | 1.015 | 1.014 ± 0.001 | 1.015 | 1.014 ± 0.001 |

## Control overhead (all scenarios)

Computed from each run's decisions.csv and summary.json (scratchpad overhead.py), mean ? 95% CI across seeds. OVSDB changes / run = rate changes actually applied (blocked ones excluded). Applying = total time spent applying them. Controller CPU = manager CPU time per 1 s tick as % of one core (for none and static this is only the measurement loop). Step = mean time to apply one change. Bulk vs static = bulk iperf throughput relative to static in the same scenario. Video loss = iperf video packet loss.

| Mode | Scenario | Runs | OVSDB changes / run | Applying (s / run) | Controller CPU (% core) | Step (ms) | Bulk vs static (%) | Video loss (%) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| none | standard | 5 | 0.0 ± 0.0 | 0.00 ± 0.00 | 1.21 ± 0.24 | 0.0 ± 0.0 | -3.2 ± 0.2 | 0.00 ± 0.00 |
| none | flash_crowd | 5 | 0.0 ± 0.0 | 0.00 ± 0.00 | 0.97 ± 0.13 | 0.0 ± 0.0 | -2.5 ± 0.3 | 0.00 ± 0.00 |
| none | video_step | 5 | 0.0 ± 0.0 | 0.00 ± 0.00 | 1.31 ± 0.40 | 0.0 ± 0.0 | -20.2 ± 0.4 | 0.08 ± 0.02 |
| none | voip_surge | 5 | 0.0 ± 0.0 | 0.00 ± 0.00 | 1.11 ± 0.42 | 0.0 ± 0.0 | -6.7 ± 0.2 | 0.28 ± 0.54 |
| static | standard | 5 | 0.0 ± 0.0 | 0.00 ± 0.00 | 1.03 ± 0.12 | 0.0 ± 0.0 | 0.0 ± 0.9 | 0.00 ± 0.00 |
| static | flash_crowd | 5 | 0.0 ± 0.0 | 0.00 ± 0.00 | 1.81 ± 1.77 | 0.0 ± 0.0 | 0.0 ± 0.6 | 0.00 ± 0.00 |
| static | video_step | 5 | 0.0 ± 0.0 | 0.00 ± 0.00 | 1.03 ± 0.06 | 0.0 ± 0.0 | 0.0 ± 0.7 | 0.00 ± 0.00 |
| static | voip_surge | 5 | 0.0 ± 0.0 | 0.00 ± 0.00 | 0.87 ± 0.06 | 0.0 ± 0.0 | 0.0 ± 0.5 | 0.00 ± 0.00 |
| reactive | standard | 5 | 31.4 ± 1.9 | 2.32 ± 0.20 | 4.00 ± 0.27 | 73.8 ± 2.1 | -41.1 ± 1.5 | 0.00 ± 0.00 |
| reactive | flash_crowd | 5 | 31.4 ± 1.9 | 2.48 ± 0.19 | 4.11 ± 0.29 | 79.3 ± 6.6 | -41.2 ± 0.9 | 0.00 ± 0.00 |
| reactive | video_step | 5 | 49.8 ± 1.6 | 4.19 ± 0.18 | 5.29 ± 0.39 | 84.3 ± 4.2 | -53.2 ± 0.6 | 0.00 ± 0.00 |
| reactive | voip_surge | 5 | 49.0 ± 0.0 | 3.51 ± 0.13 | 4.41 ± 0.23 | 71.7 ± 2.6 | -44.9 ± 0.9 | 0.00 ± 0.00 |
| proactive | standard | 5 | 0.0 ± 0.0 | 0.00 ± 0.00 | 1.10 ± 0.14 | 0.0 ± 0.0 | -1.1 ± 0.2 | 0.00 ± 0.00 |
| proactive | flash_crowd | 5 | 0.0 ± 0.0 | 0.00 ± 0.00 | 1.05 ± 0.12 | 0.0 ± 0.0 | 0.2 ± 0.4 | 0.00 ± 0.00 |
| proactive | video_step | 5 | 8.0 ± 0.0 | 0.66 ± 0.05 | 1.74 ± 0.12 | 82.2 ± 6.6 | -14.8 ± 0.7 | 0.00 ± 0.00 |
| proactive | voip_surge | 5 | 4.0 ± 2.1 | 0.37 ± 0.21 | 1.56 ± 0.34 | 90.2 ± 11.4 | -7.3 ± 1.6 | 0.00 ± 0.00 |
| fused_pi_forecast | standard | 5 | 6.0 ± 0.0 | 0.48 ± 0.03 | 2.50 ± 0.16 | 79.3 ± 5.2 | -70.7 ± 0.5 | 0.00 ± 0.00 |
| fused_pi_forecast | flash_crowd | 5 | 6.0 ± 0.0 | 0.48 ± 0.04 | 3.07 ± 0.76 | 79.8 ± 7.4 | -73.4 ± 0.4 | 0.00 ± 0.00 |
| fused_pi_forecast | video_step | 5 | 5.0 ± 0.0 | 0.42 ± 0.03 | 2.19 ± 0.22 | 83.8 ± 6.5 | -67.2 ± 1.1 | 0.00 ± 0.00 |
| fused_pi_forecast | voip_surge | 5 | 5.0 ± 0.0 | 0.39 ± 0.02 | 2.16 ± 0.15 | 78.2 ± 4.1 | -72.9 ± 0.9 | 0.00 ± 0.00 |
| fused_qlearning | standard | 5 | 8.0 ± 0.0 | 0.63 ± 0.05 | 2.80 ± 0.26 | 79.1 ± 6.7 | -1.2 ± 0.3 | 0.00 ± 0.00 |
| fused_qlearning | flash_crowd | 5 | 8.0 ± 0.0 | 0.61 ± 0.05 | 2.80 ± 0.11 | 76.7 ± 5.6 | 0.4 ± 0.4 | 0.00 ± 0.00 |
| fused_qlearning | video_step | 5 | 6.0 ± 0.0 | 0.49 ± 0.06 | 2.49 ± 0.21 | 82.0 ± 9.7 | -0.4 ± 0.8 | 0.00 ± 0.00 |
| fused_qlearning | voip_surge | 5 | 6.6 ± 0.8 | 0.67 ± 0.23 | 2.61 ± 0.15 | 98.6 ± 20.9 | -0.1 ± 0.3 | 0.00 ± 0.00 |
