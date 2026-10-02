# SDB comparison: gpt-5.6-luna low and gpt-5.6-luna none

6 scenarios and 360 matching states from the same frozen dataset. Both analyses re-score their original events. Episodes and execution settings match except model identity (provider, model and reasoning effort). The comparison JSON retains each recording's source versions.

The comparison uses reconstructed timelines excluding transport retries: successful-attempt durations start at evidence release and retain postprocessing time. Failed attempts, retry waits and dispatch queueing are excluded. Raw-clock diagnostics use a different time basis.

All duration scores below use the recording cadence; the public leaderboard uses log-AUC over 0.5–8 s.

Baseline: **gpt-5.6-luna low**. Candidate: **gpt-5.6-luna none**.

Overall candidate minus baseline: **-48.33 percentage points** untimed and **-20.44 percentage points** in-force accuracy. Family and overall scores give scenarios equal weight. The JSON retains all differences.

## Overall and families

| Scope | Baseline untimed | Candidate untimed | Baseline in-force | Candidate in-force |
|---|---:|---:|---:|---:|
| Overall | 86.11% | 37.78% | 48.45% | 28.01% |
| IDE debugging | 84.17% | 19.17% | 51.63% | 15.86% |
| Assembly | 87.50% | 30.00% | 44.00% | 21.14% |
| Support | 86.67% | 64.17% | 49.74% | 47.05% |

## Network-removed estimate (secondary)

Estimate the token-independent latency from each recording's fast envelope, subtract it from each response and replay. This assumes network + prefill + decode where applicable; the remainder can include fixed service time, so it is an upper bound on the network effect. Baseline network estimate 0.378 s (0.005–0.530); candidate 0.863 s (0.496–1.115). Parentheses show bootstrap ranges. Primary scores remain unchanged.

| Scope | Baseline network removed | Candidate network removed | Estimated difference | Ranges overlap |
|---|---:|---:|---:|---|
| Overall | 53.81% (48.52%–56.03%) | 33.57% (31.18%–35.20%) | -20.24 pp | No |
| IDE debugging | 56.46% (51.69%–58.55%) | 17.65% (16.89%–18.14%) | -38.80 pp | No |
| Assembly | 49.29% (44.06%–51.58%) | 25.94% (23.82%–27.44%) | -23.35 pp | No |
| Support | 55.70% (49.82%–57.98%) | 57.11% (52.83%–60.01%) | +1.42 pp | Yes |

## Matching scenarios

| Scope | Baseline untimed | Candidate untimed | Baseline in-force | Candidate in-force |
|---|---:|---:|---:|---:|
| lite_debugging_a | 83.33% | 18.33% | 52.31% | 13.37% |
| lite_debugging_b | 85.00% | 20.00% | 50.95% | 18.34% |
| lite_assembly_a | 91.67% | 33.33% | 50.55% | 24.42% |
| lite_assembly_b | 83.33% | 26.67% | 37.45% | 17.86% |
| lite_support_a | 81.67% | 58.33% | 48.67% | 41.32% |
| lite_support_b | 91.67% | 70.00% | 50.80% | 52.77% |

## Response latency

Only final successful-attempt durations are used; failures and retry waits are excluded. Quantiles use all requests in each scope, rather than averaging scenario quantiles. Units are seconds and include client processing and the recorded service/network path.

| Scope | Baseline p50 / p95 | Candidate p50 / p95 |
|---|---:|---:|
| Overall | 2.29 / 4.07 | 1.36 / 1.93 |
| IDE debugging | 2.27 / 3.74 | 1.35 / 2.02 |
| Assembly | 2.63 / 4.68 | 1.36 / 1.98 |
| Support | 2.02 / 2.96 | 1.37 / 1.82 |

## Paired decisions on identical states

Untimed comparisons retain each model's own route; inactive answers do not affect correctness. The four columns partition all states. Adjacent states are dependent.

| Scope | Both correct | Only baseline correct | Only candidate correct | Both wrong |
|---|---:|---:|---:|---:|
| Overall | 129 | 181 | 7 | 43 |
| IDE debugging | 21 | 80 | 2 | 17 |
| Assembly | 35 | 70 | 1 | 14 |
| Support | 73 | 31 | 4 | 12 |

## Transport reliability and raw clock

Attempt error rates divide by all physical attempts, including final successes. Logical retry rates divide by all released states. Raw-clock diagnostics retain failures, waits and actual delivery order.

| Metric | Baseline | Candidate |
|---|---:|---:|
| Attempt error rate | 0.00% (0/360) | 0.00% (0/360) |
| Logical retry rate | 0.00% (0/360) | 0.00% (0/360) |
| Raw in-force accuracy | 48.45% | 28.01% |
| Raw request p50 / p95 (s) | 2.29 / 4.07 | 1.36 / 1.93 |

## Execution and interpretation

- Protocol: retry_excluded_successful_attempt_v1; workers: 32; timeout: 20 s; SDK retries: 0.
- gpt-5.6-luna low: 0 failed requests, 349 accepted updates.
- gpt-5.6-luna none: 0 failed requests, 359 accepted updates.
- Served model names: {"gpt-5.6-luna": 360}; {"gpt-5.6-luna": 360}.

One recording per model and scenario. Differences do not establish significance, stable rankings or causal effects of model speed. Recordings occurred at different times and may have different service and network conditions. In-force accuracy depends jointly on answers, delays, acceptance and reference dwell times. Untimed scores use the same responses, without additional calls or question edits.

## Reproduction files

- [Candidate recording report](REPORT.md)
- [gpt-5.6-luna low frozen run](../../../../runs/lite-v1-gpt-5.6-luna-low-retry-v1/run.json)
- [gpt-5.6-luna none frozen run](../../../../runs/lite-v1-gpt-5.6-luna-none-retry-v1/run.json)
- [Complete comparison data](comparison.json)

Reproduce from the repository root:

```sh
uv run python scripts/lite/lite_compare.py --baseline runs/lite-v1-gpt-5.6-luna-low-retry-v1 --candidate runs/lite-v1-gpt-5.6-luna-none-retry-v1 --out docs/lite/results/gpt-5.6-luna-none
```
