# SDB comparison: gpt-5.6-luna low and jev-latest

6 scenarios and 360 matching states from the same frozen dataset. Both analyses re-score their original events. Episodes and execution settings match except model identity (provider, model and reasoning effort). The comparison JSON retains each recording's source versions.

The comparison uses reconstructed timelines excluding transport retries: successful-attempt durations start at evidence release and retain postprocessing time. Failed attempts, retry waits and dispatch queueing are excluded. Raw-clock diagnostics use a different time basis.

All duration scores below use the recording cadence; the public leaderboard uses log-AUC over 0.5–8 s.

Baseline: **gpt-5.6-luna low**. Candidate: **jev-latest**.

Overall candidate minus baseline: **-25.28 percentage points** untimed and **+9.80 percentage points** in-force accuracy. Family and overall scores give scenarios equal weight. The JSON retains all differences.

## Overall and families

| Scope | Baseline untimed | Candidate untimed | Baseline in-force | Candidate in-force |
|---|---:|---:|---:|---:|
| Overall | 86.11% | 60.83% | 48.45% | 58.26% |
| IDE debugging | 84.17% | 44.17% | 51.63% | 42.05% |
| Assembly | 87.50% | 66.67% | 44.00% | 63.81% |
| Support | 86.67% | 71.67% | 49.74% | 68.92% |

## Network-removed estimate (secondary)

Estimate the token-independent latency from each recording's fast envelope, subtract it from each response and replay. This assumes network + prefill + decode where applicable; the remainder can include fixed service time, so it is an upper bound on the network effect. Baseline network estimate 0.378 s (0.005–0.530); candidate 0.185 s (0.173–0.194). Parentheses show bootstrap ranges. Primary scores remain unchanged.

| Scope | Baseline network removed | Candidate network removed | Estimated difference | Ranges overlap |
|---|---:|---:|---:|---|
| Overall | 53.81% (48.52%–56.03%) | 60.14% (60.01%–60.22%) | +6.32 pp | No |
| IDE debugging | 56.46% (51.69%–58.55%) | 43.44% (43.35%–43.50%) | -13.02 pp | No |
| Assembly | 49.29% (44.06%–51.58%) | 65.81% (65.68%–65.90%) | +16.52 pp | No |
| Support | 55.70% (49.82%–57.98%) | 71.16% (71.01%–71.26%) | +15.46 pp | No |

## Matching scenarios

| Scope | Baseline untimed | Candidate untimed | Baseline in-force | Candidate in-force |
|---|---:|---:|---:|---:|
| lite_debugging_a | 83.33% | 43.33% | 52.31% | 41.10% |
| lite_debugging_b | 85.00% | 45.00% | 50.95% | 43.00% |
| lite_assembly_a | 91.67% | 73.33% | 50.55% | 70.15% |
| lite_assembly_b | 83.33% | 60.00% | 37.45% | 57.46% |
| lite_support_a | 81.67% | 66.67% | 48.67% | 64.04% |
| lite_support_b | 91.67% | 76.67% | 50.80% | 73.80% |

## Response latency

Only final successful-attempt durations are used; failures and retry waits are excluded. Quantiles use all requests in each scope, rather than averaging scenario quantiles. Units are seconds and include client processing and the recorded service/network path.

| Scope | Baseline p50 / p95 | Candidate p50 / p95 |
|---|---:|---:|
| Overall | 2.29 / 4.07 | 0.24 / 0.36 |
| IDE debugging | 2.27 / 3.74 | 0.26 / 0.38 |
| Assembly | 2.63 / 4.68 | 0.24 / 0.37 |
| Support | 2.02 / 2.96 | 0.22 / 0.31 |

## Paired decisions on identical states

Untimed comparisons retain each model's own route; inactive answers do not affect correctness. The four columns partition all states. Adjacent states are dependent.

| Scope | Both correct | Only baseline correct | Only candidate correct | Both wrong |
|---|---:|---:|---:|---:|
| Overall | 205 | 105 | 14 | 36 |
| IDE debugging | 50 | 51 | 3 | 16 |
| Assembly | 77 | 28 | 3 | 12 |
| Support | 78 | 26 | 8 | 8 |

## Transport reliability and raw clock

Attempt error rates divide by all physical attempts, including final successes. Logical retry rates divide by all released states. Raw-clock diagnostics retain failures, waits and actual delivery order.

| Metric | Baseline | Candidate |
|---|---:|---:|
| Attempt error rate | 0.00% (0/360) | 0.00% (0/360) |
| Logical retry rate | 0.00% (0/360) | 0.00% (0/360) |
| Raw in-force accuracy | 48.45% | 58.25% |
| Raw request p50 / p95 (s) | 2.29 / 4.07 | 0.24 / 0.36 |

## Execution and interpretation

- Protocol: retry_excluded_successful_attempt_v1; workers: 32; timeout: 20 s; SDK retries: 0.
- gpt-5.6-luna low: 0 failed requests, 349 accepted updates.
- jev-latest: 0 failed requests, 360 accepted updates.
- Served model names: {"gpt-5.6-luna": 360}; {"jev-1.13.0": 360}.

One recording per model and scenario. Differences do not establish significance, stable rankings or causal effects of model speed. Recordings occurred at different times and may have different service and network conditions. In-force accuracy depends jointly on answers, delays, acceptance and reference dwell times. Untimed scores use the same responses, without additional calls or question edits.

## Reproduction files

- [Candidate recording report](REPORT.md)
- [gpt-5.6-luna low frozen run](../../../../runs/lite-v1-gpt-5.6-luna-low-retry-v1/run.json)
- [jev-latest frozen run](../../../../runs/lite-v1-jev-latest-retry-v1/run.json)
- [Complete comparison data](comparison.json)

Reproduce from the repository root:

```sh
uv run python scripts/lite/lite_compare.py --baseline runs/lite-v1-gpt-5.6-luna-low-retry-v1 --candidate runs/lite-v1-jev-latest-retry-v1 --out docs/lite/results/jev-latest
```
