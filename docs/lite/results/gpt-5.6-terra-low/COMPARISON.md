# SDB comparison: gpt-5.6-luna low and gpt-5.6-terra low

6 scenarios and 360 matching states from the same frozen dataset. Both analyses re-score their original events. Episodes and execution settings match except model identity (provider, model and reasoning effort). The comparison JSON retains each recording's source versions.

The comparison uses reconstructed timelines excluding transport retries: successful-attempt durations start at evidence release and retain postprocessing time. Failed attempts, retry waits and dispatch queueing are excluded. Raw-clock diagnostics use a different time basis.

All duration scores below use the recording cadence; the public leaderboard uses log-AUC over 0.5–8 s.

Baseline: **gpt-5.6-luna low**. Candidate: **gpt-5.6-terra low**.

Overall candidate minus baseline: **+8.89 percentage points** untimed and **+1.90 percentage points** in-force accuracy. Family and overall scores give scenarios equal weight. The JSON retains all differences.

## Overall and families

| Scope | Baseline untimed | Candidate untimed | Baseline in-force | Candidate in-force |
|---|---:|---:|---:|---:|
| Overall | 86.11% | 95.00% | 48.45% | 50.36% |
| IDE debugging | 84.17% | 99.17% | 51.63% | 48.18% |
| Assembly | 87.50% | 92.50% | 44.00% | 47.97% |
| Support | 86.67% | 93.33% | 49.74% | 54.92% |

## Network-removed estimate (secondary)

Estimate the token-independent latency from each recording's fast envelope, subtract it from each response and replay. This assumes network + prefill + decode where applicable; the remainder can include fixed service time, so it is an upper bound on the network effect. Baseline network estimate 0.378 s (0.005–0.530); candidate 0.520 s (0.414–0.642). Parentheses show bootstrap ranges. Primary scores remain unchanged.

| Scope | Baseline network removed | Candidate network removed | Estimated difference | Ranges overlap |
|---|---:|---:|---:|---|
| Overall | 53.81% (48.52%–56.03%) | 58.79% (57.07%–60.79%) | +4.97 pp | No |
| IDE debugging | 56.46% (51.69%–58.55%) | 56.79% (55.03%–58.85%) | +0.33 pp | Yes |
| Assembly | 49.29% (44.06%–51.58%) | 56.11% (54.44%–58.05%) | +6.82 pp | No |
| Support | 55.70% (49.82%–57.98%) | 63.46% (61.73%–65.46%) | +7.76 pp | No |

## Matching scenarios

| Scope | Baseline untimed | Candidate untimed | Baseline in-force | Candidate in-force |
|---|---:|---:|---:|---:|
| lite_debugging_a | 83.33% | 100.00% | 52.31% | 48.11% |
| lite_debugging_b | 85.00% | 98.33% | 50.95% | 48.25% |
| lite_assembly_a | 91.67% | 95.00% | 50.55% | 50.89% |
| lite_assembly_b | 83.33% | 90.00% | 37.45% | 45.05% |
| lite_support_a | 81.67% | 95.00% | 48.67% | 54.32% |
| lite_support_b | 91.67% | 91.67% | 50.80% | 55.53% |

## Response latency

Only final successful-attempt durations are used; failures and retry waits are excluded. Quantiles use all requests in each scope, rather than averaging scenario quantiles. Units are seconds and include client processing and the recorded service/network path.

| Scope | Baseline p50 / p95 | Candidate p50 / p95 |
|---|---:|---:|
| Overall | 2.29 / 4.07 | 2.39 / 3.79 |
| IDE debugging | 2.27 / 3.74 | 2.50 / 4.45 |
| Assembly | 2.63 / 4.68 | 2.62 / 3.72 |
| Support | 2.02 / 2.96 | 2.17 / 2.93 |

## Paired decisions on identical states

Untimed comparisons retain each model's own route; inactive answers do not affect correctness. The four columns partition all states. Adjacent states are dependent.

| Scope | Both correct | Only baseline correct | Only candidate correct | Both wrong |
|---|---:|---:|---:|---:|
| Overall | 301 | 9 | 41 | 9 |
| IDE debugging | 100 | 1 | 19 | 0 |
| Assembly | 104 | 1 | 7 | 8 |
| Support | 97 | 7 | 15 | 1 |

## Transport reliability and raw clock

Attempt error rates divide by all physical attempts, including final successes. Logical retry rates divide by all released states. Raw-clock diagnostics retain failures, waits and actual delivery order.

| Metric | Baseline | Candidate |
|---|---:|---:|
| Attempt error rate | 0.00% (0/360) | 0.00% (0/360) |
| Logical retry rate | 0.00% (0/360) | 0.00% (0/360) |
| Raw in-force accuracy | 48.45% | 50.35% |
| Raw request p50 / p95 (s) | 2.29 / 4.07 | 2.39 / 3.79 |

## Execution and interpretation

- Protocol: retry_excluded_successful_attempt_v1; workers: 32; timeout: 20 s; SDK retries: 0.
- gpt-5.6-luna low: 0 failed requests, 349 accepted updates.
- gpt-5.6-terra low: 0 failed requests, 346 accepted updates.
- Served model names: {"gpt-5.6-luna": 360}; {"gpt-5.6-terra": 360}.

One recording per model and scenario. Differences do not establish significance, stable rankings or causal effects of model speed. Recordings occurred at different times and may have different service and network conditions. In-force accuracy depends jointly on answers, delays, acceptance and reference dwell times. Untimed scores use the same responses, without additional calls or question edits.

## Reproduction files

- [Candidate recording report](REPORT.md)
- [gpt-5.6-luna low frozen run](../../../../runs/lite-v1-gpt-5.6-luna-low-retry-v1/run.json)
- [gpt-5.6-terra low frozen run](../../../../runs/lite-v1-gpt-5.6-terra-low-retry-v1/run.json)
- [Complete comparison data](comparison.json)

Reproduce from the repository root:

```sh
uv run python scripts/lite/lite_compare.py --baseline runs/lite-v1-gpt-5.6-luna-low-retry-v1 --candidate runs/lite-v1-gpt-5.6-terra-low-retry-v1 --out docs/lite/results/gpt-5.6-terra-low
```
