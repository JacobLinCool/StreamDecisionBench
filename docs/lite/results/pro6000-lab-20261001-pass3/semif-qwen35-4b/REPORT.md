# SDB log-AUC: Qwen3.5-4B direct-logit

Primary normalized log-AUC over 0.5–8 s: **15.70%**; untimed accuracy: 17.71%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 0.00 |
| procedural_coaching | 12.48 |
| support_call_assist | 27.58 |
| presenter_voice_control | 22.74 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000511 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: Qwen/Qwen3.5-4B

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: Qwen/Qwen3.5-4B. All model scores use recorded responses.

**Untimed decision accuracy: 17.71%; In-force accuracy (transport retries excluded): 16.28%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 16.77% (range 16.57%–16.89%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 0.00% | 0.00% |
| Assembly | 14.17% | 12.91% | 8.11% | 10.83% |
| Support | 30.83% | 28.44% | 23.75% | 0.00% |
| Presenter voice control | 25.83% | 23.78% | 19.78% | 1.67% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Fitted-remainder removal (secondary)

Approximate send-to-receipt latency by a token-independent intercept plus slopes for uncached input tokens and, for text-generating models, output tokens. This secondary replay removes the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Fitted remainder 0.247 s (range 0.146–0.307 s); prefill 34.8 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.555 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Remainder removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 16.28% | 16.77% | 16.57%–16.89% | 17.71% |
| IDE debugging | 0.00% | 0.00% | 0.00%–0.00% | 0.00% |
| Assembly | 12.91% | 13.32% | 13.15%–13.42% | 14.17% |
| Support | 28.44% | 29.37% | 28.99%–29.59% | 30.83% |
| Presenter voice control | 23.78% | 24.40% | 24.15%–24.55% | 25.83% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include network delay, fixed server time and model misspecification; it does not identify network delay or guarantee an upper bound on its effect. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 0.00% | 0.00% | 0.78 / 6.23 | 0 |
| lite_debugging_b | 21 | 0.00% | 0.00% | 0.72 / 0.94 | 0 |
| lite_assembly_a | 21 | 16.67% | 14.73% | 0.89 / 8.66 | 0 |
| lite_assembly_b | 23 | 11.67% | 11.09% | 0.94 / 1.39 | 0 |
| lite_support_a | 22 | 20.00% | 19.43% | 0.65 / 0.71 | 0 |
| lite_support_b | 24 | 41.67% | 37.45% | 0.64 / 0.68 | 0 |
| lite_presenter_a | 24 | 31.67% | 28.10% | 0.91 / 1.05 | 0 |
| lite_presenter_b | 22 | 20.00% | 19.46% | 0.90 / 1.06 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 0.768 s, p95 1.280 s; includes same-host native calls, queueing and inference.
- Maximum recorded release lag 0.0133 s; maximum dispatch lag 0.0000 s.
- 70 states have only inactive-field errors, leaving the application decision correct.
- 475 updates accepted on the reconstructed timeline; rejected responses: {"after_horizon": 5}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. Native calls have no network timeout. The setting's process timeout is 3600 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 5.37 s; correct for its source but wrong for current evidence 19.02 s; wrong for both source and current evidence 779.30 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.474 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 3 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 16.28% | 12.91% |
| IDE debugging | 0.00% | 0.00% |
| Assembly | 12.91% | 8.11% |
| Support | 28.44% | 23.75% |
| Presenter voice control | 23.78% | 19.77% |

Raw logical request duration, including failed attempts and retry waits: p50 0.768 s, p95 1.280 s; 475 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | Qwen/Qwen3.5-4B decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 0.00% |
| Assembly | 0.00% | 0.00% | 14.17% |
| Support | 1.67% | 0.00% | 30.83% |
| Presenter voice control | 0.00% | 0.00% | 25.83% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 56, process: 46, target_result: 9, rerun_scope: 4, inspect_file: 2 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_debugging_b | route: 58, process: 36, target_result: 18, rerun_scope: 6, control_action: 2, owner: 2 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_assembly_a | route: 42, stage: 24, target: 17, destination: 17, next_step: 12, method: 11 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_assembly_b | route: 47, stage: 23, target: 17, method: 15, next_step: 12, destination: 7 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_support_a | recorder: 42, payment_stage: 15, service_action: 13, route: 8, hold_action: 4, instrument: 2, service_target: 1 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_support_b | route: 15, repair_action: 14, delivery_action: 10, contact_channel: 7 | 4, 8, 9, 10, 11, 12, 13, 18, 19, 20, 21, 22 |
| lite_presenter_a | slide: 23, mode: 19, captions: 10, question_card: 8, clip_state: 3, host_cue: 3 | 4, 5, 6, 7, 8, 18, 19, 20, 21, 22, 23, 24 |
| lite_presenter_b | slide: 35, mode: 29, question_card: 13, captions: 12, host_cue: 10 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 11, 14, 20 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/pro6000-lab-20261001-pass3/runs/semif-qwen35-4b/run.json)
- [Frozen episodes](../../../../../runs/pro6000-lab-20261001-pass3/runs/semif-qwen35-4b/episodes.json)
- [Release and response events](../../../../../runs/pro6000-lab-20261001-pass3/runs/semif-qwen35-4b/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 6870592,
  "cached_tokens": 0,
  "output_tokens": 0,
  "reasoning_tokens": 0
}
```
