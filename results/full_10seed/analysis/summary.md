# Experiment summary

Means and normal-approximation 95% confidence intervals across seeds.

| Mode | Scenario | Runs | VoIP RTT mean (ms) | Video stability | Policy changes |
|---|---|---:|---:|---:|---:|
| forecast_weight | baseline_shift | 6 | 16.002 [13.475, 18.529] | 0.969 [0.964, 0.975] | 0.00 |
| forecast_weight | bulk_ramp | 10 | 10.033 [9.344, 10.722] | 0.968 [0.965, 0.972] | 0.00 |
| forecast_weight | false_alarms | 4 | 10.219 [10.179, 10.259] | 0.961 [0.950, 0.972] | 0.00 |
| forecast_weight | flash_crowd | 4 | 10.548 [10.093, 11.003] | 0.956 [0.956, 0.956] | 1.50 |
| forecast_weight | misclassified | 7 | 10.402 [10.176, 10.627] | 0.962 [0.954, 0.970] | 0.43 |
| forecast_weight | noisy_telemetry | 3 | 10.277 [10.167, 10.388] | 0.970 [0.956, 0.985] | 0.00 |
| forecast_weight | standard | 6 | 10.175 [10.145, 10.205] | 0.959 [0.952, 0.967] | 0.00 |
| forecast_weight | voip_surge | 2 | 6.769 [0.010, 13.527] | 0.975 [0.959, 0.991] | 0.00 |
| fq_codel_ecn | baseline_shift | 10 | 17.654 [16.656, 18.653] | 0.992 [0.984, 0.999] | 0.00 |
| fq_codel_ecn | bulk_ramp | 10 | 9.899 [9.137, 10.660] | 0.997 [0.992, 1.001] | 0.00 |
| fq_codel_ecn | capacity_step | 10 | 13.205 [8.905, 17.505] | 1.000 [1.000, 1.000] | 0.00 |
| fq_codel_ecn | false_alarms | 10 | 12.820 [7.939, 17.701] | 0.993 [0.987, 1.000] | 0.00 |
| fq_codel_ecn | flash_crowd | 10 | 10.956 [10.804, 11.108] | 1.000 [1.000, 1.000] | 0.00 |
| fq_codel_ecn | misclassified | 9 | 10.230 [8.347, 12.112] | 0.998 [0.993, 1.002] | 0.00 |
| fq_codel_ecn | noisy_telemetry | 4 | 11.441 [11.120, 11.761] | 0.983 [0.951, 1.016] | 0.00 |
| fq_codel_ecn | repeated_bursts | 10 | 10.729 [10.593, 10.866] | 0.300 [0.300, 0.300] | 0.00 |
| fq_codel_ecn | standard | 10 | 11.355 [11.115, 11.596] | 0.998 [0.993, 1.002] | 0.00 |
| fq_codel_ecn | voip_surge | 10 | 13.101 [9.714, 16.488] | 0.998 [0.995, 1.002] | 0.00 |
| fused_pi | misclassified | 1 | 11.022 [11.022, 11.022] | 0.978 [0.978, 0.978] | 0.00 |
| fused_pi | noisy_telemetry | 4 | 10.629 [10.181, 11.076] | 0.978 [0.978, 0.978] | 0.00 |
| fused_pi | standard | 1 | 10.973 [10.973, 10.973] | 0.978 [0.978, 0.978] | 1.00 |
| fused_pi_forecast | bulk_ramp | 2 | 10.168 [10.135, 10.201] | 0.983 [0.983, 0.983] | 0.00 |
| fused_pi_forecast | noisy_telemetry | 1 | 10.206 [10.206, 10.206] | 0.978 [0.978, 0.978] | 0.00 |
| fused_qlearning_unshielded | baseline_shift | 10 | 17.382 [17.276, 17.489] | 0.967 [0.960, 0.974] | 28.00 |
| fused_qlearning_unshielded | bulk_ramp | 10 | 10.399 [10.215, 10.584] | 0.967 [0.957, 0.976] | 27.20 |
| fused_qlearning_unshielded | capacity_step | 10 | 10.481 [10.222, 10.740] | 0.962 [0.953, 0.971] | 24.20 |
| fused_qlearning_unshielded | false_alarms | 10 | 10.639 [10.295, 10.982] | 0.964 [0.955, 0.974] | 27.00 |
| fused_qlearning_unshielded | flash_crowd | 10 | 10.945 [10.584, 11.306] | 0.960 [0.949, 0.971] | 27.00 |
| fused_qlearning_unshielded | misclassified | 10 | 10.791 [10.570, 11.011] | 0.951 [0.940, 0.962] | 27.00 |
| fused_qlearning_unshielded | noisy_telemetry | 10 | 10.660 [10.332, 10.989] | 0.960 [0.949, 0.971] | 21.80 |
| fused_qlearning_unshielded | standard | 10 | 10.817 [10.362, 11.272] | 0.958 [0.948, 0.968] | 27.20 |
| fused_qlearning_unshielded | video_step | 10 | 10.589 [10.356, 10.822] | 0.923 [0.916, 0.931] | 24.60 |
| fused_qlearning_unshielded | voip_surge | 10 | 10.635 [10.468, 10.802] | 0.963 [0.955, 0.971] | 25.20 |
| none | baseline_shift | 10 | 319.921 [147.023, 492.819] | 1.000 [1.000, 1.000] | 0.00 |
| none | bulk_ramp | 10 | 10.452 [10.373, 10.531] | 1.000 [1.000, 1.000] | 0.00 |
| none | capacity_step | 10 | 79.769 [61.451, 98.088] | 1.000 [1.000, 1.000] | 0.00 |
| none | false_alarms | 10 | 55.456 [38.256, 72.656] | 1.000 [1.000, 1.000] | 0.00 |
| none | flash_crowd | 10 | 42.570 [18.208, 66.931] | 1.000 [1.000, 1.000] | 0.00 |
| none | misclassified | 10 | 142.422 [-16.359, 301.202] | 1.000 [1.000, 1.000] | 0.00 |
| none | noisy_telemetry | 4 | 15.663 [5.164, 26.162] | 1.000 [1.000, 1.000] | 0.00 |
| none | repeated_bursts | 10 | 19.940 [16.856, 23.024] | 0.300 [0.300, 0.300] | 0.00 |
| none | standard | 10 | 51.436 [33.397, 69.475] | 1.000 [1.000, 1.000] | 0.00 |
| none | video_step | 1 | 86.307 [86.307, 86.307] | 0.983 [0.983, 0.983] | 0.00 |
| none | voip_surge | 10 | 91.160 [34.811, 147.508] | 1.000 [1.000, 1.000] | 0.00 |
| stat_pi | misclassified | 2 | 8.090 [3.740, 12.440] | 0.978 [0.978, 0.978] | 5.50 |
| stat_pi | noisy_telemetry | 4 | 10.225 [10.208, 10.242] | 0.978 [0.978, 0.978] | 0.00 |
| stat_pi | standard | 1 | 10.909 [10.909, 10.909] | 0.978 [0.978, 0.978] | 0.00 |
| stat_pi | voip_surge | 1 | 16.973 [16.973, 16.973] | 0.983 [0.983, 0.983] | 10.00 |
| static | baseline_shift | 10 | 16.570 [14.908, 18.232] | 0.968 [0.965, 0.972] | 0.00 |
| static | bulk_ramp | 9 | 10.588 [10.303, 10.873] | 0.969 [0.965, 0.972] | 0.00 |
| static | capacity_step | 10 | 11.890 [8.843, 14.937] | 0.960 [0.960, 0.960] | 0.00 |
| static | false_alarms | 10 | 9.943 [9.009, 10.877] | 0.956 [0.956, 0.956] | 0.00 |
| static | flash_crowd | 10 | 10.464 [10.212, 10.716] | 0.956 [0.956, 0.956] | 0.00 |
| static | misclassified | 10 | 94.790 [-16.502, 206.082] | 0.956 [0.956, 0.956] | 0.00 |
| static | noisy_telemetry | 10 | 10.892 [9.221, 12.564] | 0.960 [0.954, 0.966] | 0.00 |
| static | standard | 10 | 10.182 [9.120, 11.245] | 0.956 [0.956, 0.956] | 0.00 |
| static | voip_surge | 10 | 105.240 [-44.006, 254.487] | 0.942 [0.916, 0.967] | 0.00 |
| supervised_rule | bulk_ramp | 10 | 10.675 [10.512, 10.838] | 0.972 [0.967, 0.977] | 0.00 |
| threshold_rule | bulk_ramp | 7 | 9.743 [8.838, 10.647] | 0.964 [0.960, 0.969] | 0.00 |
