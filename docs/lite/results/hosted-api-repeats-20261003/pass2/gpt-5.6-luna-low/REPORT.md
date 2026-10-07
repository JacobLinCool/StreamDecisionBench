# SDB log-AUC: Luna low — pass 2

Primary normalized log-AUC over 0.5–8 s: **46.23%**; untimed accuracy: 90.00%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 49.86 |
| procedural_coaching | 44.88 |
| support_call_assist | 45.00 |
| presenter_voice_control | 45.17 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000364 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: gpt-5.6-luna low

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: gpt-5.6-luna, reasoning effort low. All model scores use recorded responses.

**Untimed decision accuracy: 90.00%; In-force accuracy (transport retries excluded): 49.02%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 60.60% (range 59.34%–62.01%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 88.33% | 54.89% | 50.86% | 88.33% |
| Assembly | 86.67% | 47.48% | 36.89% | 86.67% |
| Support | 89.17% | 48.96% | 41.39% | 83.33% |
| Presenter voice control | 95.83% | 44.75% | 32.68% | 95.83% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Fitted-remainder removal (secondary)

Approximate send-to-receipt latency by a token-independent intercept plus slopes for uncached input tokens and, for text-generating models, output tokens. This secondary replay removes the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Fitted remainder 0.806 s (range 0.722–0.900 s); prefill 0.0 ms/1k tokens; decode 8.32 ms/token; fastest response 1.520 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Remainder removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 49.02% | 60.60% | 59.34%–62.01% | 90.00% |
| IDE debugging | 54.89% | 65.10% | 64.00%–66.30% | 88.33% |
| Assembly | 47.48% | 58.74% | 57.54%–60.06% | 86.67% |
| Support | 48.96% | 61.78% | 60.41%–63.30% | 89.17% |
| Presenter voice control | 44.75% | 56.81% | 55.40%–58.37% | 95.83% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include network delay, fixed server time and model misspecification; it does not identify network delay or guarantee an upper bound on its effect. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 83.33% | 60.48% | 2.11 / 2.97 | 0 |
| lite_debugging_b | 21 | 93.33% | 49.31% | 2.54 / 4.19 | 0 |
| lite_assembly_a | 21 | 88.33% | 50.60% | 2.29 / 3.51 | 0 |
| lite_assembly_b | 23 | 85.00% | 44.36% | 2.86 / 4.69 | 0 |
| lite_support_a | 22 | 83.33% | 45.48% | 2.29 / 3.09 | 0 |
| lite_support_b | 24 | 95.00% | 52.44% | 2.26 / 2.70 | 0 |
| lite_presenter_a | 24 | 98.33% | 47.62% | 2.72 / 3.72 | 0 |
| lite_presenter_b | 22 | 93.33% | 41.89% | 2.99 / 3.88 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 2.408 s, p95 3.849 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0101 s; maximum dispatch lag 0.0000 s.
- 7 states have only inactive-field errors, leaving the application decision correct.
- 471 updates accepted on the reconstructed timeline; rejected responses: {"after_horizon": 7, "older_than_active": 2}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 20 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 20.28 s; correct for its source but wrong for current evidence 387.44 s; wrong for both source and current evidence 81.67 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.255 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 49.01% | 40.45% |
| IDE debugging | 54.89% | 50.85% |
| Assembly | 47.47% | 36.89% |
| Support | 48.95% | 41.38% |
| Presenter voice control | 44.74% | 32.67% |

Raw logical request duration, including failed attempts and retry waits: p50 2.408 s, p95 3.849 s; 471 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | gpt-5.6-luna low decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 88.33% |
| Assembly | 0.00% | 0.00% | 86.67% |
| Support | 1.67% | 0.00% | 89.17% |
| Presenter voice control | 0.00% | 0.00% | 95.83% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 10, inspect_file: 1, rerun_scope: 1 | 7, 8, 19, 24, 25, 27, 28, 43, 57, 59 |
| lite_debugging_b | route: 4, owner: 2, rerun_scope: 1 | 25, 26, 31, 32 |
| lite_assembly_a | route: 5, target: 2, next_step: 1, method: 1 | 8, 9, 31, 45, 46, 47, 48 |
| lite_assembly_b | route: 7, target: 2, next_step: 1 | 6, 7, 9, 11, 39, 42, 43, 48, 49 |
| lite_support_a | recorder: 10 | 12, 13, 17, 18, 21, 44, 45, 46, 47, 49 |
| lite_support_b | route: 3, delivery_target: 1, delivery_action: 1 | 7, 21, 34 |
| lite_presenter_a | captions: 1 | 22 |
| lite_presenter_b | slide: 3, question_card: 1 | 37, 46, 47, 56 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../../PROTOCOL.md)
- [Debugging rules](../../../../debugging.md), [assembly rules](../../../../assembly.md), [support rules](../../../../support.md), [presenter rules](../../../../presenter.md)
- [Frozen run](../../../../../../runs/hosted-api-repeats-20261003/pass2/gpt-5.6-luna-low/run.json)
- [Frozen episodes](../../../../../../runs/hosted-api-repeats-20261003/pass2/gpt-5.6-luna-low/episodes.json)
- [Release and response events](../../../../../../runs/hosted-api-repeats-20261003/pass2/gpt-5.6-luna-low/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 1476489,
  "cached_tokens": 0,
  "output_tokens": 79817,
  "reasoning_tokens": 57377
}
```
