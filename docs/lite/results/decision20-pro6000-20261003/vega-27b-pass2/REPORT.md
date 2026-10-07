# SDB log-AUC: Decision 2.0 Vega-27B

Primary normalized log-AUC over 0.5–8 s: **7.48%**; untimed accuracy: 68.54%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 5.56 |
| procedural_coaching | 10.07 |
| support_call_assist | 7.50 |
| presenter_voice_control | 6.78 |

Quadrature: 512 log-spaced subintervals; maximum change from the preceding grid 0.000291 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: vllm-sr/Decision-2.0-Vega-27B

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: vllm-sr/Decision-2.0-Vega-27B. All model scores use recorded responses.

**Untimed decision accuracy: 68.54%; In-force accuracy (transport retries excluded): 6.32%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 6.32% (range 6.32%–6.32%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 60.00% | 6.74% | 5.11% | 49.17% |
| Assembly | 74.17% | 5.30% | 5.83% | 32.50% |
| Support | 45.00% | 7.51% | 4.70% | 29.17% |
| Presenter voice control | 95.00% | 5.71% | 2.66% | 86.67% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Fitted-remainder removal (secondary)

Approximate send-to-receipt latency by a token-independent intercept plus slopes for uncached input tokens and, for text-generating models, output tokens. This secondary replay removes the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Fitted remainder 0.000 s (range 0.000–0.000 s); prefill 9748.9 ms/1k tokens; no decode term (the model does not generate text); fastest response 2.116 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Remainder removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 6.32% | 6.32% | 6.32%–6.32% | 68.54% |
| IDE debugging | 6.74% | 6.74% | 6.74%–6.74% | 60.00% |
| Assembly | 5.30% | 5.30% | 5.30%–5.30% | 74.17% |
| Support | 7.51% | 7.51% | 7.51%–7.51% | 45.00% |
| Presenter voice control | 5.71% | 5.71% | 5.71%–5.71% | 95.00% |

Unconstrained intercept -84.388303 s (range -105.928033–-45.336981 s). Extrapolation to zero tokens can be negative; negative latency cannot be removed, so replay projects it to zero. analysis.json retains the unconstrained estimate. Scores and recordings are unchanged.

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include network delay, fixed server time and model misspecification; it does not identify network delay or guarantee an upper bound on its effect. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 61.67% | 8.24% | 60.32 / 149.71 | 0 |
| lite_debugging_b | 21 | 58.33% | 5.24% | 58.78 / 144.61 | 0 |
| lite_assembly_a | 21 | 68.33% | 5.65% | 45.84 / 153.21 | 0 |
| lite_assembly_b | 23 | 80.00% | 4.95% | 52.44 / 163.32 | 0 |
| lite_support_a | 22 | 81.67% | 13.79% | 31.09 / 77.82 | 0 |
| lite_support_b | 24 | 8.33% | 1.23% | 29.69 / 69.98 | 0 |
| lite_presenter_a | 24 | 98.33% | 3.76% | 98.20 / 193.03 | 0 |
| lite_presenter_b | 22 | 91.67% | 7.67% | 100.82 / 193.06 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 52.952 s, p95 174.002 s; includes same-host native calls, queueing and inference.
- Maximum recorded release lag 0.0002 s; maximum dispatch lag 0.0000 s.
- 92 states have only inactive-field errors, leaving the application decision correct.
- 249 updates accepted on the reconstructed timeline; rejected responses: {"after_horizon": 231}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. Native calls have no network timeout.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 25.31 s; correct for its source but wrong for current evidence 573.74 s; wrong for both source and current evidence 300.30 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 224.250 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 3 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 6.32% | 4.57% |
| IDE debugging | 6.74% | 5.11% |
| Assembly | 5.30% | 5.83% |
| Support | 7.51% | 4.70% |
| Presenter voice control | 5.71% | 2.66% |

Raw logical request duration, including failed attempts and retry waits: p50 52.952 s, p95 174.002 s; 249 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | vllm-sr/Decision-2.0-Vega-27B decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 60.00% |
| Assembly | 0.00% | 0.00% | 74.17% |
| Support | 1.67% | 0.00% | 45.00% |
| Presenter voice control | 0.00% | 0.00% | 95.00% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 19, process: 8 | 5, 6, 7, 8, 10, 16, 17, 18, 19, 25, 26, 27 |
| lite_debugging_b | route: 17, process: 5, control_action: 4, rerun_scope: 3, owner: 3, target_result: 2 | 0, 7, 8, 11, 12, 19, 20, 21, 22, 23, 24, 25 |
| lite_assembly_a | route: 14, next_step: 5, target: 4, method: 4, destination: 4, stage: 1 | 8, 9, 10, 11, 12, 13, 16, 17, 18, 31, 32, 35 |
| lite_assembly_b | route: 10, next_step: 3, method: 3, target: 2, stage: 1 | 10, 11, 33, 38, 39, 40, 41, 43, 45, 46, 47, 49 |
| lite_support_a | recorder: 8, service_action: 2, payment_stage: 2, hold_action: 1 | 24, 25, 32, 43, 44, 45, 46, 47, 48, 49, 51 |
| lite_support_b | route: 55, delivery_action: 2 | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 |
| lite_presenter_a | mode: 1 | 7 |
| lite_presenter_b | host_cue: 4, mode: 3, slide: 1 | 5, 6, 7, 8, 39 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/decision20-pro6000-20261003/pass2/vega-27b/run.json)
- [Frozen episodes](../../../../../runs/decision20-pro6000-20261003/pass2/vega-27b/episodes.json)
- [Release and response events](../../../../../runs/decision20-pro6000-20261003/pass2/vega-27b/events.jsonl)
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
