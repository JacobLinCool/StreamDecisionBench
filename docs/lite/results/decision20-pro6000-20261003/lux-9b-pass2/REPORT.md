# SDB log-AUC: Decision 2.0 Lux-9B

Primary normalized log-AUC over 0.5–8 s: **24.39%**; untimed accuracy: 29.58%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 7.23 |
| procedural_coaching | 23.97 |
| support_call_assist | 41.10 |
| presenter_voice_control | 25.24 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000638 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: vllm-sr/Decision-2.0-Lux-9B

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: vllm-sr/Decision-2.0-Lux-9B. All model scores use recorded responses.

**Untimed decision accuracy: 29.58%; In-force accuracy (transport retries excluded): 25.81%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 25.81% (range 25.81%–25.81%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 10.83% | 8.28% | 7.90% | 0.83% |
| Assembly | 28.33% | 24.95% | 18.82% | 0.00% |
| Support | 49.17% | 43.18% | 42.02% | 19.17% |
| Presenter voice control | 30.00% | 26.82% | 25.12% | 15.83% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Fitted-remainder removal (secondary)

Approximate send-to-receipt latency by a token-independent intercept plus slopes for uncached input tokens and, for text-generating models, output tokens. This secondary replay removes the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Fitted remainder 0.000 s (range 0.000–0.000 s); prefill 93.7 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.540 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Remainder removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 25.81% | 25.81% | 25.81%–25.81% | 29.58% |
| IDE debugging | 8.28% | 8.28% | 8.28%–8.28% | 10.83% |
| Assembly | 24.95% | 24.95% | 24.95%–24.95% | 28.33% |
| Support | 43.18% | 43.18% | 43.18%–43.18% | 49.17% |
| Presenter voice control | 26.82% | 26.82% | 26.82%–26.82% | 30.00% |

Unconstrained intercept -0.020683 s (range -0.033088–-0.005449 s). Extrapolation to zero tokens can be negative; negative latency cannot be removed, so replay projects it to zero. analysis.json retains the unconstrained estimate. Scores and recordings are unchanged.

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include network delay, fixed server time and model misspecification; it does not identify network delay or guarantee an upper bound on its effect. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 15.00% | 12.20% | 1.16 / 1.57 | 0 |
| lite_debugging_b | 21 | 6.67% | 4.35% | 1.14 / 1.53 | 0 |
| lite_assembly_a | 21 | 31.67% | 28.53% | 1.26 / 1.90 | 0 |
| lite_assembly_b | 23 | 25.00% | 21.37% | 1.30 / 1.92 | 0 |
| lite_support_a | 22 | 36.67% | 32.29% | 0.89 / 1.05 | 0 |
| lite_support_b | 24 | 61.67% | 54.06% | 0.84 / 0.97 | 0 |
| lite_presenter_a | 24 | 48.33% | 43.24% | 1.49 / 1.72 | 0 |
| lite_presenter_b | 22 | 11.67% | 10.41% | 1.48 / 1.73 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 1.200 s, p95 1.728 s; includes same-host native calls, queueing and inference.
- Maximum recorded release lag 0.0002 s; maximum dispatch lag 0.0000 s.
- 99 states have only inactive-field errors, leaving the application decision correct.
- 479 updates accepted on the reconstructed timeline; rejected responses: {"after_horizon": 1}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. Native calls have no network timeout.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 6.56 s; correct for its source but wrong for current evidence 51.98 s; wrong for both source and current evidence 653.72 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.181 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 3 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 25.80% | 23.46% |
| IDE debugging | 8.27% | 7.90% |
| Assembly | 24.95% | 18.82% |
| Support | 43.17% | 42.02% |
| Presenter voice control | 26.82% | 25.12% |

Raw logical request duration, including failed attempts and retry waits: p50 1.200 s, p95 1.728 s; 479 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | vllm-sr/Decision-2.0-Lux-9B decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 10.83% |
| Assembly | 0.00% | 0.00% | 28.33% |
| Support | 1.67% | 0.00% | 49.17% |
| Presenter voice control | 0.00% | 0.00% | 30.00% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 49, process: 16, target_result: 4, rerun_scope: 4, inspect_file: 2, owner: 1 | 0, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13 |
| lite_debugging_b | route: 48, target_result: 18, process: 6, rerun_scope: 6, owner: 4, control_action: 2 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_assembly_a | route: 34, stage: 16, destination: 10, method: 8, target: 7, next_step: 5 | 0, 1, 2, 3, 5, 8, 9, 10, 11, 12, 13, 14 |
| lite_assembly_b | route: 39, destination: 10, next_step: 8, target: 7, stage: 6, method: 6 | 0, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 14 |
| lite_support_a | recorder: 30, payment_stage: 16, service_action: 4, hold_action: 4, instrument: 2, route: 2 | 0, 1, 2, 3, 8, 9, 18, 19, 22, 23, 24, 25 |
| lite_support_b | route: 11, repair_action: 9, delivery_target: 1, delivery_action: 1, cancellation_action: 1, repair_target: 1 | 2, 4, 5, 10, 11, 15, 26, 27, 30, 31, 32, 33 |
| lite_presenter_a | slide: 24, mode: 10, question_card: 4, clip_state: 2, captions: 1, host_cue: 1 | 3, 4, 5, 6, 7, 8, 14, 15, 16, 26, 30, 31 |
| lite_presenter_b | slide: 37, mode: 25, question_card: 12, clip_state: 3, captions: 1 | 0, 1, 2, 3, 4, 5, 6, 8, 11, 12, 13, 14 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/decision20-pro6000-20261003/pass2/lux-9b/run.json)
- [Frozen episodes](../../../../../runs/decision20-pro6000-20261003/pass2/lux-9b/episodes.json)
- [Release and response events](../../../../../runs/decision20-pro6000-20261003/pass2/lux-9b/events.jsonl)
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
