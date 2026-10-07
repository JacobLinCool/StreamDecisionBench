# SDB log-AUC: Wity-1 (auto)

Primary normalized log-AUC over 0.5–8 s: **2.64%**; untimed accuracy: 27.50%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 0.69 |
| procedural_coaching | 1.68 |
| support_call_assist | 2.50 |
| presenter_voice_control | 5.66 |

Quadrature: 512 log-spaced subintervals; maximum change from the preceding grid 0.000549 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: wity-1

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. HTTP 429 honors Retry-After through a shared cooldown within the attempt budget. Requested model: wity-1. All model scores use recorded responses.

**Untimed decision accuracy: 27.50%; In-force accuracy (failed attempts and retry waits excluded): 1.08%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 1.08% (range 1.08%–1.08%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 5.00% | 0.00% | 0.00% | 1.67% |
| Assembly | 21.67% | 0.00% | 0.00% | 0.00% |
| Support | 49.17% | 0.57% | 0.34% | 15.00% |
| Presenter voice control | 34.17% | 3.74% | 1.80% | 17.50% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Fitted-remainder removal (secondary)

Approximate send-to-receipt latency by a token-independent intercept plus slopes for uncached input tokens and, for text-generating models, output tokens. This secondary replay removes the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Fitted remainder 0.000 s (range 0.000–0.000 s); prefill 23784.9 ms/1k tokens; no decode term (the model does not generate text); fastest response 1.981 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Remainder removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 1.08% | 1.08% | 1.08%–1.08% | 27.50% |
| IDE debugging | 0.00% | 0.00% | 0.00%–0.00% | 5.00% |
| Assembly | 0.00% | 0.00% | 0.00%–0.00% | 21.67% |
| Support | 0.57% | 0.57% | 0.57%–0.57% | 49.17% |
| Presenter voice control | 3.74% | 3.74% | 3.74%–3.74% | 34.17% |

Unconstrained intercept -46.588846 s (range -70.956183–-29.392451 s). Extrapolation to zero tokens can be negative; negative latency cannot be removed, so replay projects it to zero. analysis.json retains the unconstrained estimate. Scores and recordings are unchanged.

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include network delay, fixed server time and model misspecification; it does not identify network delay or guarantee an upper bound on its effect. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 5.00% | 0.00% | 57.48 / 102.92 | 0 |
| lite_debugging_b | 21 | 5.00% | 0.00% | 63.66 / 86.11 | 0 |
| lite_assembly_a | 21 | 18.33% | 0.00% | 73.64 / 133.72 | 0 |
| lite_assembly_b | 23 | 25.00% | 0.00% | 109.71 / 147.80 | 0 |
| lite_support_a | 22 | 45.00% | 0.00% | 43.51 / 80.20 | 0 |
| lite_support_b | 24 | 53.33% | 1.15% | 56.60 / 84.33 | 0 |
| lite_presenter_a | 24 | 46.67% | 5.01% | 70.03 / 100.75 | 0 |
| lite_presenter_b | 22 | 21.67% | 2.48% | 103.63 / 126.71 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 63.534 s, p95 124.721 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0101 s; maximum dispatch lag 0.0000 s.
- 91 states have only inactive-field errors, leaving the application decision correct.
- 158 updates accepted on the reconstructed timeline; rejected responses: {"older_than_active": 60, "after_horizon": 262}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 180 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 16 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 65.96 s; correct for its source but wrong for current evidence 411.56 s; wrong for both source and current evidence 472.12 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 5.33% (27 failed attempts / 507 total attempts, including final successes).
- Logical request retry rate: 4.17% (20 retried requests / 480 logical requests).
- Failed attempt types: {"RateLimitError": 26, "TimeoutError": 1}.
- Failed attempts took 2591.038 s in total; excluded failures and retry waits total 2643.127 s, and excluded dispatch queueing totals 14234.979 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.
- The immediate-first-retry rule above applies to transport failures. HTTP 429 uses Retry-After (delay-seconds or HTTP-date) as a minimum wait, with a shared episode cooldown. Without that header, bounded backoff starts at 1 s. The server's delay is not capped at 8 s. Concurrency is limited to 16 workers; rate-limit attempts count toward the same attempt budget.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 1.08% | 0.54% |
| IDE debugging | 0.00% | 0.00% |
| Assembly | 0.00% | 0.00% |
| Support | 0.57% | 0.34% |
| Presenter voice control | 3.74% | 1.80% |

Raw logical request duration, including failed attempts and retry waits: p50 63.664 s, p95 147.440 s; 158 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | wity-1 decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 5.00% |
| Assembly | 0.00% | 0.00% | 21.67% |
| Support | 1.67% | 0.00% | 49.17% |
| Presenter voice control | 0.00% | 0.00% | 34.17% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 50, target_result: 15, process: 11, rerun_scope: 3, owner: 3, inspect_file: 2 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_debugging_b | route: 46, process: 25, target_result: 15, rerun_scope: 4, control_action: 3, owner: 2 | 0, 1, 2, 4, 5, 6, 7, 9, 10, 11, 12, 13 |
| lite_assembly_a | route: 32, destination: 14, next_step: 12, target: 7, method: 5, stage: 4 | 0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 12, 13 |
| lite_assembly_b | route: 28, target: 14, method: 11, next_step: 8, destination: 4, stage: 2 | 6, 7, 8, 9, 10, 11, 13, 18, 22, 23, 24, 25 |
| lite_support_a | payment_stage: 15, service_action: 11, recorder: 10, route: 8, instrument: 3, service_target: 3 | 3, 4, 20, 21, 22, 23, 24, 25, 26, 27, 28, 34 |
| lite_support_b | route: 16, repair_action: 11, delivery_action: 8, cancellation_action: 1, contact_channel: 1 | 4, 8, 10, 11, 16, 18, 20, 21, 22, 23, 28, 34 |
| lite_presenter_a | mode: 22, captions: 13, slide: 11, host_cue: 10, question_card: 6, clip_state: 5 | 22, 24, 25, 27, 28, 29, 30, 31, 32, 33, 34, 35 |
| lite_presenter_b | slide: 35, mode: 25, host_cue: 10, question_card: 6, clip_state: 1, captions: 1 | 5, 6, 7, 8, 9, 12, 13, 14, 16, 18, 19, 20 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/wity-1-auto-workers16-retry-after-20261003-pass1/run.json)
- [Frozen episodes](../../../../../runs/wity-1-auto-workers16-retry-after-20261003-pass1/episodes.json)
- [Release and response events](../../../../../runs/wity-1-auto-workers16-retry-after-20261003-pass1/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 1599899,
  "cached_tokens": 0,
  "output_tokens": 0,
  "reasoning_tokens": 0
}
```
