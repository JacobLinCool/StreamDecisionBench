# SDB log-AUC: Gemini Decision 1 (Decisions API) — pass 3

Primary normalized log-AUC over 0.5–8 s: **64.03%**; untimed accuracy: 72.71%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 47.06 |
| procedural_coaching | 65.52 |
| support_call_assist | 78.28 |
| presenter_voice_control | 65.29 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000481 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: gemini-decision-1

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. HTTP 429 and 5xx honor Retry-After through a shared cooldown within the attempt budget. Requested model: gemini-decision-1. All model scores use recorded responses.

**Untimed decision accuracy: 72.71%; In-force accuracy (failed attempts and retry waits excluded): 66.25%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 68.77% (range 68.30%–69.11%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 53.33% | 48.65% | 46.36% | 38.33% |
| Assembly | 74.17% | 67.72% | 60.93% | 24.17% |
| Support | 86.67% | 80.47% | 75.81% | 55.00% |
| Presenter voice control | 76.67% | 68.17% | 64.33% | 55.83% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Fitted-remainder removal (secondary)

Approximate send-to-receipt latency by a token-independent intercept plus slopes for uncached input tokens and, for text-generating models, output tokens. This secondary replay removes the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Fitted remainder 0.198 s (range 0.161–0.225 s); prefill 34.9 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.201 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Remainder removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 66.25% | 68.77% | 68.30%–69.11% | 72.71% |
| IDE debugging | 48.65% | 50.13% | 49.86%–50.34% | 53.33% |
| Assembly | 67.72% | 70.36% | 69.87%–70.72% | 74.17% |
| Support | 80.47% | 83.44% | 82.89%–83.85% | 86.67% |
| Presenter voice control | 68.17% | 71.14% | 70.59%–71.55% | 76.67% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include network delay, fixed server time and model misspecification; it does not identify network delay or guarantee an upper bound on its effect. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 53.33% | 49.46% | 0.51 / 0.66 | 0 |
| lite_debugging_b | 21 | 53.33% | 47.84% | 0.73 / 0.93 | 0 |
| lite_assembly_a | 21 | 71.67% | 66.24% | 0.47 / 0.66 | 0 |
| lite_assembly_b | 23 | 76.67% | 69.19% | 0.54 / 0.85 | 0 |
| lite_support_a | 22 | 78.33% | 71.85% | 0.52 / 0.70 | 0 |
| lite_support_b | 24 | 95.00% | 89.09% | 0.30 / 0.48 | 0 |
| lite_presenter_a | 24 | 83.33% | 75.18% | 0.50 / 0.62 | 0 |
| lite_presenter_b | 22 | 70.00% | 61.17% | 0.63 / 0.75 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 0.524 s, p95 0.819 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0261 s; maximum dispatch lag 0.0000 s.
- 141 states have only inactive-field errors, leaving the application decision correct.
- 480 updates accepted on the reconstructed timeline; rejected responses: {}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 20 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 3.84 s; correct for its source but wrong for current evidence 61.80 s; wrong for both source and current evidence 258.35 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 29.52% (201 failed attempts / 681 total attempts, including final successes).
- Logical request retry rate: 30.21% (145 retried requests / 480 logical requests).
- Failed attempt types: {"RetryableHTTPError": 201}.
- Failed attempts took 54.745 s in total; excluded failures and retry waits total 8289.511 s, and excluded dispatch queueing totals 9024.917 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.
- The immediate-first-retry rule above applies to transport failures. HTTP 429 and 5xx uses Retry-After (delay-seconds or HTTP-date) as a minimum wait, with a shared episode cooldown. Without that header, bounded backoff starts at 1 s. The server's delay is not capped at 8 s. Concurrency is limited to 32 workers; rate-limit attempts count toward the same attempt budget.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 19.56% | 18.22% |
| IDE debugging | 4.87% | 5.24% |
| Assembly | 19.91% | 21.72% |
| Support | 39.20% | 38.39% |
| Presenter voice control | 14.24% | 7.52% |

Raw logical request duration, including failed attempts and retry waits: p50 0.652 s, p95 89.915 s; 149 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | gemini-decision-1 decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 53.33% |
| Assembly | 0.00% | 0.00% | 74.17% |
| Support | 1.67% | 0.00% | 86.67% |
| Presenter voice control | 0.00% | 0.00% | 76.67% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 16, process: 16, rerun_scope: 7, inspect_file: 2 | 5, 6, 7, 8, 9, 10, 14, 15, 16, 17, 19, 25 |
| lite_debugging_b | route: 16, process: 13, target_result: 6, owner: 3, rerun_scope: 2, control_action: 2 | 0, 6, 11, 12, 18, 20, 21, 22, 23, 24, 25, 27 |
| lite_assembly_a | route: 11, method: 4, stage: 2, next_step: 1 | 8, 9, 12, 13, 14, 15, 16, 17, 18, 31, 32, 39 |
| lite_assembly_b | route: 14, target: 2, next_step: 1 | 6, 7, 10, 11, 32, 33, 38, 39, 40, 41, 42, 43 |
| lite_support_a | recorder: 6, payment_stage: 5, service_action: 2, hold_action: 2 | 20, 21, 29, 32, 38, 39, 42, 46, 49, 50, 51, 52 |
| lite_support_b | route: 3 | 47, 53, 55 |
| lite_presenter_a | host_cue: 6, clip_state: 2, mode: 1, slide: 1 | 15, 23, 32, 37, 39, 45, 46, 47, 49, 50 |
| lite_presenter_b | slide: 14, mode: 7, host_cue: 2 | 5, 6, 7, 20, 36, 37, 39, 40, 48, 49, 51, 52 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/lite-v1-gemini-decision-1-20261112-pass3-retry-v1/run.json)
- [Frozen episodes](../../../../../runs/lite-v1-gemini-decision-1-20261112-pass3-retry-v1/episodes.json)
- [Release and response events](../../../../../runs/lite-v1-gemini-decision-1-20261112-pass3-retry-v1/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py --run runs/lite-v1-gemini-decision-1-20261112-pass3-retry-v1 --out docs/lite/results/gemini-decision-1-20261112/pass3 --label 'Gemini Decision 1 (Decisions API) — pass 3'
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 1459408,
  "cached_tokens": 0,
  "output_tokens": 0,
  "reasoning_tokens": 0
}
```
