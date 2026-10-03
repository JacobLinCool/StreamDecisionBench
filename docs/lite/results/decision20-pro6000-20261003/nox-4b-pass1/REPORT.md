# SDB log-AUC: Decision-2.0-Nox-4B — pass 1

Primary normalized log-AUC over 0.5–8 s: **15.85%**; untimed accuracy: 18.33%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 2.13 |
| procedural_coaching | 6.50 |
| support_call_assist | 32.76 |
| presenter_voice_control | 22.02 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000532 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: vllm-sr/Decision-2.0-Nox-4B

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: vllm-sr/Decision-2.0-Nox-4B. All model scores use recorded responses.

**Untimed decision accuracy: 18.33%; In-force accuracy (transport retries excluded): 16.47%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 16.47% (range 16.47%–16.47%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 3.33% | 2.44% | 2.46% | 0.83% |
| Assembly | 6.67% | 6.74% | 6.22% | 0.00% |
| Support | 36.67% | 33.78% | 33.47% | 9.17% |
| Presenter voice control | 26.67% | 22.91% | 22.35% | 4.17% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Network-removed estimate (secondary)

Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + decode (proportional to output tokens, for text-generating models). The token-independent remainder is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Estimated network 0.000 s (range 0.000–0.000 s); prefill 74.5 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.396 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 16.47% | 16.47% | 16.47%–16.47% | 18.33% |
| IDE debugging | 2.44% | 2.44% | 2.44%–2.44% | 3.33% |
| Assembly | 6.74% | 6.74% | 6.74%–6.74% | 6.67% |
| Support | 33.78% | 33.78% | 33.78%–33.78% | 36.67% |
| Presenter voice control | 22.91% | 22.91% | 22.91%–22.91% | 26.67% |

Unconstrained intercept -0.039071 s (range -0.044139–-0.021412 s). Extrapolation to zero tokens can be negative; negative latency cannot be removed, so replay projects it to zero. analysis.json retains the unconstrained estimate. Scores and recordings are unchanged.

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include fixed server time, so it bounds the network effect from above. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 0.00% | 0.00% | 0.89 / 1.23 | 0 |
| lite_debugging_b | 21 | 6.67% | 4.87% | 0.88 / 1.19 | 0 |
| lite_assembly_a | 21 | 11.67% | 11.80% | 0.97 / 1.48 | 0 |
| lite_assembly_b | 23 | 1.67% | 1.68% | 1.01 / 1.51 | 0 |
| lite_support_a | 22 | 23.33% | 21.84% | 0.70 / 0.82 | 0 |
| lite_support_b | 24 | 50.00% | 45.73% | 0.65 / 0.75 | 0 |
| lite_presenter_a | 24 | 40.00% | 33.32% | 1.16 / 1.33 | 0 |
| lite_presenter_b | 22 | 13.33% | 12.50% | 1.16 / 1.35 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 0.936 s, p95 1.347 s; includes same-host native calls, queueing and inference.
- Maximum recorded release lag 0.0005 s; maximum dispatch lag 0.0000 s.
- 71 states have only inactive-field errors, leaving the application decision correct.
- 480 updates accepted on the reconstructed timeline; rejected responses: {}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. Native calls have no network timeout.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 4.97 s; correct for its source but wrong for current evidence 26.55 s; wrong for both source and current evidence 770.40 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.237 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 3 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 16.47% | 16.12% |
| IDE debugging | 2.44% | 2.46% |
| Assembly | 6.74% | 6.22% |
| Support | 33.78% | 33.47% |
| Presenter voice control | 22.91% | 22.35% |

Raw logical request duration, including failed attempts and retry waits: p50 0.936 s, p95 1.347 s; 480 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | vllm-sr/Decision-2.0-Nox-4B decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 3.33% |
| Assembly | 0.00% | 0.00% | 6.67% |
| Support | 1.67% | 0.00% | 36.67% |
| Presenter voice control | 0.00% | 0.00% | 26.67% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 46, process: 42, target_result: 8, rerun_scope: 4, owner: 1 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_debugging_b | route: 52, target_result: 20, process: 16, control_action: 4, rerun_scope: 4, owner: 2 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_assembly_a | route: 42, stage: 26, destination: 21, target: 9, method: 8, next_step: 4 | 0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12 |
| lite_assembly_b | stage: 50, route: 35, destination: 16, next_step: 12, target: 8, method: 4 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_support_a | recorder: 39, payment_stage: 16, hold_action: 4, route: 4, service_target: 3, service_action: 3, instrument: 1 | 4, 5, 6, 7, 8, 9, 11, 16, 18, 19, 22, 23 |
| lite_support_b | repair_action: 16, route: 9, delivery_action: 5, cancellation_action: 2, repair_target: 2 | 4, 5, 8, 9, 10, 11, 14, 15, 21, 26, 27, 28 |
| lite_presenter_a | slide: 26, mode: 11, host_cue: 10, question_card: 5, captions: 4, clip_state: 1 | 1, 2, 3, 5, 6, 7, 8, 13, 14, 15, 24, 25 |
| lite_presenter_b | slide: 29, mode: 25, question_card: 14, captions: 8, clip_state: 5, host_cue: 2 | 0, 2, 3, 4, 5, 6, 7, 11, 12, 13, 14, 16 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/decision20-pro6000-20261003/pass1/nox-4b/run.json)
- [Frozen episodes](../../../../../runs/decision20-pro6000-20261003/pass1/nox-4b/episodes.json)
- [Release and response events](../../../../../runs/decision20-pro6000-20261003/pass1/nox-4b/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py --run runs/decision20-pro6000-20261003/pass1/nox-4b --out docs/lite/results/decision20-pro6000-20261003/nox-4b-pass1 --label 'Decision-2.0-Nox-4B — pass 1'
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
