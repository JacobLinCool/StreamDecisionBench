# GLiDE (Fastino): three benchmark passes

Mean normalized log-AUC over 0.5–8 s: **39.43% ± 2.11 percentage points** (sample SD across three passes).
Mean untimed decision accuracy: **80.49%**.

Each pass uses the same frozen dataset and recording source versions: four families, eight scenarios, 480 requests, one release every 2 s, 32 workers, a 300 s request timeout, and at most five attempts. The two additional passes ran sequentially. SDK retries are disabled; every attempt is recorded.

| Pass | Log-AUC (%) | Untimed (%) | p50 latency (s) | p95 latency (s) | Failed attempts | Report |
|---|---:|---:|---:|---:|---:|---|
| 1 | 39.50 | 80.00 | 5.439 | 16.271 | 0 | [report](REPORT.md) |
| 2 | 37.28 | 80.42 | 8.182 | 21.497 | 0 | [report](pass2/REPORT.md) |
| 3 | 41.50 | 81.04 | 3.016 | 14.204 | 0 | [report](pass3/REPORT.md) |

| Family | Mean log-AUC (%) | Sample SD (points) | Mean untimed (%) |
|---|---:|---:|---:|
| live_debugging | 31.76 | 3.13 | 56.11 |
| presenter_voice_control | 49.72 | 2.35 | 92.22 |
| procedural_coaching | 35.12 | 3.13 | 75.00 |
| support_call_assist | 41.11 | 1.32 | 98.61 |

1440/1440 logical requests produced valid responses; 0 failed attempts and 0 retried logical requests across all three passes.

Scores are equal means of independently integrated per-pass log-AUC, with equal scenario weights within each family and equal family weights. Latency means average the within-pass quantiles; they are not pooled-request quantiles. The primary timeline excludes failed attempts, retry waits and dispatch queueing; each report also retains raw wall-clock diagnostics.

These repeated measurements describe variation on the fixed dataset. Sample SD is not a confidence interval or evidence of population-level ranking stability. Served model identifiers and exact execution provenance remain in the individual analyses.

[Machine-readable aggregate and evidence hashes](repeats.json)

## Reproduce the individual reports

```bash
.venv/bin/python paper/analysis/lite_reports.py --run runs/lite-v1-glide-20261003-pass1-retry-v1 --out docs/lite/results/glide-20261003 --label 'GLiDE (Fastino)'
.venv/bin/python paper/analysis/lite_reports.py --run runs/lite-v1-glide-20261003-pass2-retry-v1 --out docs/lite/results/glide-20261003/pass2 --label 'GLiDE (Fastino), pass 2'
.venv/bin/python paper/analysis/lite_reports.py --run runs/lite-v1-glide-20261003-pass3-retry-v1 --out docs/lite/results/glide-20261003/pass3 --label 'GLiDE (Fastino), pass 3'
```
