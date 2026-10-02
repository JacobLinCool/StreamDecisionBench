# SDB comparison: gpt-5.6-terra low and gpt-5.6-terra none

6 scenarios and 360 matching states from the same frozen dataset. Both analyses re-score their original events. Episodes and execution settings match except model identity (provider, model and reasoning effort). The comparison JSON retains each recording's source versions.

The comparison uses reconstructed timelines excluding transport retries: successful-attempt durations start at evidence release and retain postprocessing time. Failed attempts, retry waits and dispatch queueing are excluded. Raw-clock diagnostics use a different time basis.

All duration scores below use the recording cadence; the public leaderboard uses log-AUC over 0.5–8 s.

Baseline: **gpt-5.6-terra low**. Candidate: **gpt-5.6-terra none**.

Overall candidate minus baseline: **-14.72 percentage points** untimed and **+7.06 percentage points** in-force accuracy. Family and overall scores give scenarios equal weight. The JSON retains all differences.

## Overall and families

| Scope | Baseline untimed | Candidate untimed | Baseline in-force | Candidate in-force |
|---|---:|---:|---:|---:|
| Overall | 95.00% | 80.28% | 50.36% | 57.42% |
| IDE debugging | 99.17% | 72.50% | 48.18% | 55.58% |
| Assembly | 92.50% | 76.67% | 47.97% | 54.55% |
| Support | 93.33% | 91.67% | 54.92% | 62.12% |

## Network-removed estimate (secondary)

Estimate the token-independent latency from each recording's fast envelope, subtract it from each response and replay. This assumes network + prefill + decode where applicable; the remainder can include fixed service time, so it is an upper bound on the network effect. Baseline network estimate 0.520 s (0.414–0.642); candidate 1.214 s (0.937–1.304). Parentheses show bootstrap ranges. Primary scores remain unchanged.

| Scope | Baseline network removed | Candidate network removed | Estimated difference | Ranges overlap |
|---|---:|---:|---:|---|
| Overall | 58.79% (57.07%–60.79%) | 74.14% (70.28%–75.36%) | +15.35 pp | No |
| IDE debugging | 56.79% (55.03%–58.85%) | 67.21% (64.55%–68.10%) | +10.43 pp | No |
| Assembly | 56.11% (54.44%–58.05%) | 71.58% (67.76%–72.79%) | +15.47 pp | No |
| Support | 63.46% (61.73%–65.46%) | 83.62% (78.53%–85.18%) | +20.16 pp | No |

## Matching scenarios

| Scope | Baseline untimed | Candidate untimed | Baseline in-force | Candidate in-force |
|---|---:|---:|---:|---:|
| lite_debugging_a | 100.00% | 76.67% | 48.11% | 59.09% |
| lite_debugging_b | 98.33% | 68.33% | 48.25% | 52.06% |
| lite_assembly_a | 95.00% | 76.67% | 50.89% | 53.15% |
| lite_assembly_b | 90.00% | 76.67% | 45.05% | 55.96% |
| lite_support_a | 95.00% | 88.33% | 54.32% | 62.64% |
| lite_support_b | 91.67% | 95.00% | 55.53% | 61.61% |

## Response latency

Only final successful-attempt durations are used; failures and retry waits are excluded. Quantiles use all requests in each scope, rather than averaging scenario quantiles. Units are seconds and include client processing and the recorded service/network path.

| Scope | Baseline p50 / p95 | Candidate p50 / p95 |
|---|---:|---:|
| Overall | 2.39 / 3.79 | 1.52 / 2.15 |
| IDE debugging | 2.50 / 4.45 | 1.54 / 2.08 |
| Assembly | 2.62 / 3.72 | 1.55 / 2.34 |
| Support | 2.17 / 2.93 | 1.48 / 2.15 |

## Paired decisions on identical states

Untimed comparisons retain each model's own route; inactive answers do not affect correctness. The four columns partition all states. Adjacent states are dependent.

| Scope | Both correct | Only baseline correct | Only candidate correct | Both wrong |
|---|---:|---:|---:|---:|
| Overall | 285 | 57 | 4 | 14 |
| IDE debugging | 87 | 32 | 0 | 1 |
| Assembly | 92 | 19 | 0 | 9 |
| Support | 106 | 6 | 4 | 4 |

## Transport reliability and raw clock

Attempt error rates divide by all physical attempts, including final successes. Logical retry rates divide by all released states. Raw-clock diagnostics retain failures, waits and actual delivery order.

| Metric | Baseline | Candidate |
|---|---:|---:|
| Attempt error rate | 0.00% (0/360) | 0.00% (0/360) |
| Logical retry rate | 0.00% (0/360) | 0.00% (0/360) |
| Raw in-force accuracy | 50.35% | 57.41% |
| Raw request p50 / p95 (s) | 2.39 / 3.79 | 1.52 / 2.15 |

## Execution and interpretation

- Protocol: retry_excluded_successful_attempt_v1; workers: 32; timeout: 20 s; SDK retries: 0.
- gpt-5.6-terra low: 0 failed requests, 346 accepted updates.
- gpt-5.6-terra none: 0 failed requests, 358 accepted updates.
- Served model names: {"gpt-5.6-terra": 360}; {"gpt-5.6-terra": 360}.

One recording per model and scenario. Differences do not establish significance, stable rankings or causal effects of model speed. Recordings occurred at different times and may have different service and network conditions. In-force accuracy depends jointly on answers, delays, acceptance and reference dwell times. Untimed scores use the same responses, without additional calls or question edits.

## Reproduction files

- [Candidate recording report](REPORT.md)
- [gpt-5.6-terra low frozen run](../../../../runs/lite-v1-gpt-5.6-terra-low-retry-v1/run.json)
- [gpt-5.6-terra none frozen run](../../../../runs/lite-v1-gpt-5.6-terra-none-retry-v1/run.json)
- [Complete comparison data](comparison.json)

Reproduce from the repository root:

```sh
uv run python scripts/lite/lite_compare.py --baseline runs/lite-v1-gpt-5.6-terra-low-retry-v1 --candidate runs/lite-v1-gpt-5.6-terra-none-retry-v1 --out docs/lite/results/gpt-5.6-terra-none
```
