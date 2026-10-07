# SDB log-AUC: GPT-6-Luna (Decisions API)

Primary normalized log-AUC over 0.5–8 s: **31.59%**; untimed accuracy: 36.04%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 20.75 |
| procedural_coaching | 19.13 |
| support_call_assist | 53.92 |
| presenter_voice_control | 32.58 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000338 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: gpt-6-luna

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. HTTP 429 and 5xx honor Retry-After through a shared cooldown within the attempt budget. Requested model: gpt-6-luna. All model scores use recorded responses.

**Untimed decision accuracy: 36.04%; In-force accuracy (failed attempts and retry waits excluded): 32.53%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 34.27% (range 33.90%–34.37%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 23.33% | 21.19% | 22.83% | 11.67% |
| Assembly | 23.33% | 19.94% | 19.33% | 5.83% |
| Support | 60.83% | 55.72% | 53.27% | 26.67% |
| Presenter voice control | 36.67% | 33.30% | 28.92% | 22.50% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Fitted-remainder removal (secondary)

Approximate send-to-receipt latency by a token-independent intercept plus slopes for uncached input tokens and, for text-generating models, output tokens. This secondary replay removes the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Fitted remainder 0.264 s (range 0.209–0.280 s); prefill 3.2 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.224 s; 38 requests clamped at receipt.

| Scope | Recorded-cadence score | Remainder removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 32.53% | 34.27% | 33.90%–34.37% | 36.04% |
| IDE debugging | 21.19% | 22.18% | 21.97%–22.24% | 23.33% |
| Assembly | 19.94% | 21.37% | 21.07%–21.45% | 23.33% |
| Support | 55.72% | 58.58% | 57.98%–58.74% | 60.83% |
| Presenter voice control | 33.30% | 34.95% | 34.60%–35.03% | 36.67% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include network delay, fixed server time and model misspecification; it does not identify network delay or guarantee an upper bound on its effect. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 28.33% | 25.54% | 0.34 / 0.59 | 0 |
| lite_debugging_b | 21 | 18.33% | 16.83% | 0.34 / 0.41 | 0 |
| lite_assembly_a | 21 | 28.33% | 24.64% | 0.35 / 0.75 | 0 |
| lite_assembly_b | 23 | 18.33% | 15.23% | 0.33 / 0.74 | 0 |
| lite_support_a | 22 | 60.00% | 54.69% | 0.34 / 0.74 | 0 |
| lite_support_b | 24 | 61.67% | 56.74% | 0.34 / 0.58 | 0 |
| lite_presenter_a | 24 | 41.67% | 36.99% | 0.33 / 1.13 | 0 |
| lite_presenter_b | 22 | 31.67% | 29.60% | 0.35 / 0.49 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 0.340 s, p95 0.729 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0101 s; maximum dispatch lag 0.0000 s.
- 93 states have only inactive-field errors, leaving the application decision correct.
- 2 responses refused at least one question (lite_presenter_b t=0: question_card, lite_presenter_b t=2: question_card). A refused question commits to no option and is wrong wherever the decision uses it; 0 of these decisions used a refused question.
- 478 updates accepted on the reconstructed timeline; rejected responses: {"older_than_active": 2}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 20 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 4.52 s; correct for its source but wrong for current evidence 26.63 s; wrong for both source and current evidence 616.52 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.167 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.
- The immediate-first-retry rule above applies to transport failures. HTTP 429 and 5xx uses Retry-After (delay-seconds or HTTP-date) as a minimum wait, with a shared episode cooldown. Without that header, bounded backoff starts at 1 s. The server's delay is not capped at 8 s. Concurrency is limited to 32 workers; rate-limit attempts count toward the same attempt budget.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 32.53% | 31.09% |
| IDE debugging | 21.18% | 22.83% |
| Assembly | 19.94% | 19.33% |
| Support | 55.71% | 53.26% |
| Presenter voice control | 33.30% | 28.92% |

Raw logical request duration, including failed attempts and retry waits: p50 0.340 s, p95 0.729 s; 478 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | gpt-6-luna decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 23.33% |
| Assembly | 0.00% | 0.00% | 23.33% |
| Support | 1.67% | 0.00% | 60.83% |
| Presenter voice control | 0.00% | 0.00% | 36.67% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 34, rerun_scope: 10, process: 7, target_result: 6, inspect_file: 1 | 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 17 |
| lite_debugging_b | route: 44, rerun_scope: 8, target_result: 6, process: 4, owner: 3, control_action: 2, inspect_file: 1 | 0, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14 |
| lite_assembly_a | route: 33, destination: 16, next_step: 10, stage: 5, target: 4, method: 4 | 0, 1, 2, 3, 4, 7, 8, 9, 12, 13, 14, 16 |
| lite_assembly_b | route: 34, destination: 16, next_step: 12, stage: 7, method: 4, target: 4 | 0, 1, 3, 4, 5, 6, 7, 8, 10, 11, 16, 17 |
| lite_support_a | payment_stage: 13, recorder: 9, route: 6, hold_action: 4, service_target: 2 | 5, 6, 7, 20, 21, 29, 30, 31, 32, 33, 36, 38 |
| lite_support_b | route: 19, repair_action: 5, repair_target: 2 | 4, 11, 12, 13, 14, 15, 16, 17, 21, 26, 30, 31 |
| lite_presenter_a | host_cue: 22, slide: 14, clip_state: 7, question_card: 5, mode: 3 | 0, 3, 4, 5, 6, 7, 8, 11, 13, 14, 16, 17 |
| lite_presenter_b | slide: 24, mode: 15, clip_state: 8, question_card: 5, host_cue: 3 | 2, 5, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../PROTOCOL.md)
- [Debugging rules](../../debugging.md), [assembly rules](../../assembly.md), [support rules](../../support.md), [presenter rules](../../presenter.md)
- [Frozen run](../../../../runs/lite-v1-gpt-6-luna-decisions-20261007-pass1-retry-v1/run.json)
- [Frozen episodes](../../../../runs/lite-v1-gpt-6-luna-decisions-20261007-pass1-retry-v1/episodes.json)
- [Release and response events](../../../../runs/lite-v1-gpt-6-luna-decisions-20261007-pass1-retry-v1/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 1550604,
  "cached_tokens": 0,
  "output_tokens": 0,
  "reasoning_tokens": 0
}
```
