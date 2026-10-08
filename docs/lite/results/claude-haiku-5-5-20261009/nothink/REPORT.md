# SDB log-AUC: Claude Haiku 5.5 thinking off

Primary normalized log-AUC over 0.5–8 s: **20.50%**; untimed accuracy: 26.46%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 16.33 |
| procedural_coaching | 11.29 |
| support_call_assist | 31.26 |
| presenter_voice_control | 23.11 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000415 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: claude-haiku-5-5 low thinking off

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. HTTP 429 and 5xx honor Retry-After through a shared cooldown within the attempt budget. Requested model: claude-haiku-5-5, reasoning effort low, thinking disabled. All model scores use recorded responses.

**Untimed decision accuracy: 26.46%; In-force accuracy (failed attempts and retry waits excluded): 22.13%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 25.26% (range 25.19%–25.34%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 19.17% | 17.29% | 17.33% | 18.33% |
| Assembly | 14.17% | 12.79% | 12.27% | 10.83% |
| Support | 45.00% | 33.92% | 30.07% | 38.33% |
| Presenter voice control | 27.50% | 24.53% | 23.16% | 25.83% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Fitted-remainder removal (secondary)

Approximate send-to-receipt latency by a token-independent intercept plus slopes for uncached input tokens and, for text-generating models, output tokens. This secondary replay removes the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Fitted remainder 0.997 s (range 0.974–1.020 s); prefill 0.0 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.873 s; 48 requests clamped at receipt.

| Scope | Recorded-cadence score | Remainder removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 22.13% | 25.26% | 25.19%–25.34% | 26.46% |
| IDE debugging | 17.29% | 18.54% | 18.51%–18.57% | 19.17% |
| Assembly | 12.79% | 14.39% | 14.36%–14.42% | 14.17% |
| Support | 33.92% | 41.81% | 41.62%–41.99% | 45.00% |
| Presenter voice control | 24.53% | 26.32% | 26.25%–26.39% | 27.50% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include network delay, fixed server time and model misspecification; it does not identify network delay or guarantee an upper bound on its effect. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 30.00% | 26.39% | 1.51 / 1.64 | 0 |
| lite_debugging_b | 21 | 8.33% | 8.20% | 1.56 / 1.81 | 0 |
| lite_assembly_a | 21 | 15.00% | 14.63% | 1.49 / 1.65 | 0 |
| lite_assembly_b | 23 | 13.33% | 10.95% | 1.52 / 1.73 | 0 |
| lite_support_a | 22 | 41.67% | 30.75% | 1.48 / 1.72 | 0 |
| lite_support_b | 24 | 48.33% | 37.08% | 1.34 / 1.59 | 0 |
| lite_presenter_a | 24 | 25.00% | 23.66% | 1.13 / 1.50 | 0 |
| lite_presenter_b | 22 | 30.00% | 25.40% | 1.02 / 1.53 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 1.451 s, p95 1.712 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0074 s; maximum dispatch lag 0.0000 s.
- 15 states have only inactive-field errors, leaving the application decision correct.
- 479 updates accepted on the reconstructed timeline; rejected responses: {"older_than_active": 1}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 20 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 15.66 s; correct for its source but wrong for current evidence 58.13 s; wrong for both source and current evidence 673.73 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.215 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.
- The immediate-first-retry rule above applies to transport failures. HTTP 429 and 5xx uses Retry-After (delay-seconds or HTTP-date) as a minimum wait, with a shared episode cooldown. Without that header, bounded backoff starts at 1 s. The server's delay is not capped at 8 s. Concurrency is limited to 32 workers; rate-limit attempts count toward the same attempt budget.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 22.13% | 20.71% |
| IDE debugging | 17.29% | 17.33% |
| Assembly | 12.79% | 12.27% |
| Support | 33.91% | 30.07% |
| Presenter voice control | 24.53% | 23.16% |

Raw logical request duration, including failed attempts and retry waits: p50 1.451 s, p95 1.712 s; 479 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | claude-haiku-5-5 low thinking off decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 19.17% |
| Assembly | 0.00% | 0.00% | 14.17% |
| Support | 1.67% | 0.00% | 45.00% |
| Presenter voice control | 0.00% | 0.00% | 27.50% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 37, target_result: 13, rerun_scope: 8, inspect_file: 5, owner: 3 | 3, 4, 6, 7, 8, 11, 14, 15, 17, 18, 19, 23 |
| lite_debugging_b | route: 49, target_result: 16, process: 8, rerun_scope: 7, owner: 6, control_action: 2, inspect_file: 1 | 0, 2, 3, 4, 5, 6, 8, 9, 10, 11, 13, 14 |
| lite_assembly_a | stage: 38, route: 29, destination: 12, next_step: 10, method: 8, target: 5 | 0, 1, 2, 3, 5, 7, 8, 9, 11, 12, 13, 15 |
| lite_assembly_b | route: 37, stage: 22, destination: 17, target: 14, method: 13, next_step: 9 | 0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 16 |
| lite_support_a | recorder: 16, payment_stage: 14, route: 12, instrument: 10, service_action: 7, service_target: 6, hold_action: 2 | 4, 6, 8, 10, 12, 13, 14, 15, 17, 20, 21, 22 |
| lite_support_b | route: 20, repair_target: 9, repair_action: 7, contact_channel: 4, cancellation_action: 1 | 3, 6, 16, 17, 26, 27, 29, 30, 31, 32, 33, 34 |
| lite_presenter_a | slide: 28, host_cue: 14, mode: 10, captions: 10, clip_state: 3, question_card: 3 | 1, 4, 5, 6, 7, 8, 10, 13, 14, 15, 16, 18 |
| lite_presenter_b | slide: 26, mode: 17, clip_state: 10, host_cue: 7, question_card: 7, captions: 4 | 2, 5, 7, 9, 10, 11, 12, 13, 14, 15, 16, 17 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/lite-v1-claude-haiku-5-5-nothink-20261009-pass1-retry-v1/run.json)
- [Frozen episodes](../../../../../runs/lite-v1-claude-haiku-5-5-nothink-20261009-pass1-retry-v1/episodes.json)
- [Release and response events](../../../../../runs/lite-v1-claude-haiku-5-5-nothink-20261009-pass1-retry-v1/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py --run runs/lite-v1-claude-haiku-5-5-nothink-20261009-pass1-retry-v1 --out docs/lite/results/claude-haiku-5-5-20261009/nothink --label 'Claude Haiku 5.5 thinking off'
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 1400355,
  "cached_tokens": 886461,
  "output_tokens": 28179,
  "reasoning_tokens": 0
}
```
