#!/bin/bash
# Report reproduction: S1-S4 main matrix, then the budget-share sensitivity
# batch (reactive and proactive on S2 and S4 at s = 0.15 and 0.20).
# --resume skips runs that already have a valid summary.json.
set -e
cd /app
python3 run_experiments.py --config configs/report.yaml --output results/report \
    --modes fused_pi_forecast_cost fused_pi_forecast none static reactive proactive fq_codel_ecn \
    --scenarios S1 S2 S3 S4 --repeats 5 --resume
for share in s15 s20; do
    python3 run_experiments.py --config configs/report_${share}.yaml --output results/report_${share} \
        --modes reactive proactive --scenarios S2 S4 --repeats 5 --resume
done
python3 analyze.py --results results/report
python3 analyze.py --results results/report_s15
python3 analyze.py --results results/report_s20
