# SDB log-AUC: Decision 2.0 Sol-2B

Primary normalized log-AUC over 0.5–8 s: **3.59%**; untimed accuracy: 3.54%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 2.71 |
| procedural_coaching | 1.31 |
| support_call_assist | 8.36 |
| presenter_voice_control | 1.98 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000323 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: vllm-sr/Decision-2.0-Sol-2B

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: vllm-sr/Decision-2.0-Sol-2B. All model scores use recorded responses.

**Untimed decision accuracy: 3.54%; In-force accuracy (transport retries excluded): 3.58%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 3.58% (range 3.58%–3.58%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 2.50% | 2.66% | 2.54% | 2.50% |
| Assembly | 1.67% | 1.40% | 1.96% | 0.00% |
| Support | 8.33% | 8.35% | 6.68% | 3.33% |
| Presenter voice control | 1.67% | 1.90% | 1.42% | 1.67% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Fitted-remainder removal (secondary)

Approximate send-to-receipt latency by a token-independent intercept plus slopes for uncached input tokens and, for text-generating models, output tokens. This secondary replay removes the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Fitted remainder 0.000 s (range 0.000–0.000 s); prefill 33.3 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.172 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Remainder removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 3.58% | 3.58% | 3.58%–3.58% | 3.54% |
| IDE debugging | 2.66% | 2.66% | 2.66%–2.66% | 2.50% |
| Assembly | 1.40% | 1.40% | 1.40%–1.40% | 1.67% |
| Support | 8.35% | 8.35% | 8.35%–8.35% | 8.33% |
| Presenter voice control | 1.90% | 1.90% | 1.90%–1.90% | 1.67% |

Unconstrained intercept -0.037252 s (range -0.042839–-0.034020 s). Extrapolation to zero tokens can be negative; negative latency cannot be removed, so replay projects it to zero. analysis.json retains the unconstrained estimate. Scores and recordings are unchanged.

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include network delay, fixed server time and model misspecification; it does not identify network delay or guarantee an upper bound on its effect. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 3.33% | 3.34% | 0.39 / 0.53 | 0 |
| lite_debugging_b | 21 | 1.67% | 1.97% | 0.38 / 0.51 | 0 |
| lite_assembly_a | 21 | 1.67% | 1.68% | 0.42 / 0.63 | 0 |
| lite_assembly_b | 23 | 1.67% | 1.11% | 0.43 / 0.65 | 0 |
| lite_support_a | 22 | 6.67% | 6.51% | 0.29 / 0.34 | 0 |
| lite_support_b | 24 | 10.00% | 10.19% | 0.27 / 0.31 | 0 |
| lite_presenter_a | 24 | 1.67% | 1.67% | 0.50 / 0.59 | 0 |
| lite_presenter_b | 22 | 1.67% | 2.14% | 0.50 / 0.58 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 0.404 s, p95 0.590 s; includes same-host native calls, queueing and inference.
- Maximum recorded release lag 0.0003 s; maximum dispatch lag 0.0000 s.
- 8 states have only inactive-field errors, leaving the application decision correct.
- 480 updates accepted on the reconstructed timeline; rejected responses: {}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. Native calls have no network timeout.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 2.10 s; correct for its source but wrong for current evidence 1.09 s; wrong for both source and current evidence 922.48 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.226 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 3 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 3.58% | 3.15% |
| IDE debugging | 2.66% | 2.54% |
| Assembly | 1.40% | 1.96% |
| Support | 8.35% | 6.68% |
| Presenter voice control | 1.90% | 1.42% |

Raw logical request duration, including failed attempts and retry waits: p50 0.404 s, p95 0.590 s; 480 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | vllm-sr/Decision-2.0-Sol-2B decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 2.50% |
| Assembly | 0.00% | 0.00% | 1.67% |
| Support | 1.67% | 0.00% | 8.33% |
| Presenter voice control | 0.00% | 0.00% | 1.67% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 51, process: 36, target_result: 27, rerun_scope: 7, inspect_file: 5, owner: 2 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_debugging_b | route: 51, process: 38, target_result: 30, control_action: 4, rerun_scope: 3, owner: 3 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_assembly_a | route: 45, stage: 37, destination: 17, target: 13, method: 12, next_step: 6 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_assembly_b | route: 45, stage: 21, destination: 20, method: 14, target: 13, next_step: 10 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_support_a | recorder: 54, payment_stage: 26, route: 16, service_action: 10, instrument: 6, hold_action: 5, service_target: 3 | 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15 |
| lite_support_b | route: 29, repair_action: 19, delivery_target: 15, delivery_action: 13, contact_channel: 5, cancellation_action: 3, repair_target: 3 | 0, 1, 2, 3, 4, 5, 10, 11, 12, 13, 14, 15 |
| lite_presenter_a | host_cue: 36, slide: 32, mode: 20, captions: 19, clip_state: 13, question_card: 10 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_presenter_b | slide: 49, host_cue: 32, mode: 26, captions: 18, question_card: 16, clip_state: 7 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/decision20-pro6000-20261003/pass3/sol-2b/run.json)
- [Frozen episodes](../../../../../runs/decision20-pro6000-20261003/pass3/sol-2b/episodes.json)
- [Release and response events](../../../../../runs/decision20-pro6000-20261003/pass3/sol-2b/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 6079091,
  "cached_tokens": 0,
  "output_tokens": 0,
  "reasoning_tokens": 0
}
```
