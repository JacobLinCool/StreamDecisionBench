# SDB log-AUC: Decision-2.0-Kai-0.6B — pass 3

Primary normalized log-AUC over 0.5–8 s: **3.63%**; untimed accuracy: 3.75%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 5.62 |
| procedural_coaching | 2.50 |
| support_call_assist | 2.42 |
| presenter_voice_control | 3.98 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000227 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: vllm-sr/Decision-2.0-Kai-0.6B

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: vllm-sr/Decision-2.0-Kai-0.6B. All model scores use recorded responses.

**Untimed decision accuracy: 3.75%; In-force accuracy (transport retries excluded): 3.66%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 3.66% (range 3.66%–3.66%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 5.83% | 5.68% | 5.41% | 0.00% |
| Assembly | 2.50% | 2.50% | 3.12% | 0.00% |
| Support | 2.50% | 2.44% | 3.02% | 0.00% |
| Presenter voice control | 4.17% | 4.03% | 4.21% | 0.00% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Network-removed estimate (secondary)

Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + decode (proportional to output tokens, for text-generating models). The token-independent remainder is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Estimated network 0.000 s (range 0.000–0.000 s); prefill 20.6 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.076 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 3.66% | 3.66% | 3.66%–3.66% | 3.75% |
| IDE debugging | 5.68% | 5.68% | 5.68%–5.68% | 5.83% |
| Assembly | 2.50% | 2.50% | 2.50%–2.50% | 2.50% |
| Support | 2.44% | 2.44% | 2.44%–2.44% | 2.50% |
| Presenter voice control | 4.03% | 4.03% | 4.03%–4.03% | 4.17% |

Unconstrained intercept -0.073471 s (range -0.085385–-0.060806 s). Extrapolation to zero tokens can be negative; negative latency cannot be removed, so replay projects it to zero. analysis.json retains the unconstrained estimate. Scores and recordings are unchanged.

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include fixed server time, so it bounds the network effect from above. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 5.00% | 4.90% | 0.18 / 0.28 | 0 |
| lite_debugging_b | 21 | 6.67% | 6.45% | 0.18 / 0.27 | 0 |
| lite_assembly_a | 21 | 0.00% | 0.00% | 0.21 / 0.39 | 0 |
| lite_assembly_b | 23 | 5.00% | 4.99% | 0.22 / 0.40 | 0 |
| lite_support_a | 22 | 1.67% | 1.67% | 0.13 / 0.16 | 0 |
| lite_support_b | 24 | 3.33% | 3.21% | 0.12 / 0.14 | 0 |
| lite_presenter_a | 24 | 8.33% | 8.06% | 0.27 / 0.33 | 0 |
| lite_presenter_b | 22 | 0.00% | 0.00% | 0.27 / 0.34 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 0.199 s, p95 0.340 s; includes same-host native calls, queueing and inference.
- Maximum recorded release lag 0.0021 s; maximum dispatch lag 0.0000 s.
- 18 states have only inactive-field errors, leaving the application decision correct.
- 480 updates accepted on the reconstructed timeline; rejected responses: {}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. Native calls have no network timeout.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 0.99 s; correct for its source but wrong for current evidence 1.54 s; wrong for both source and current evidence 922.33 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.217 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 3 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 3.66% | 3.94% |
| IDE debugging | 5.68% | 5.41% |
| Assembly | 2.50% | 3.12% |
| Support | 2.44% | 3.01% |
| Presenter voice control | 4.03% | 4.21% |

Raw logical request duration, including failed attempts and retry waits: p50 0.199 s, p95 0.340 s; 480 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | vllm-sr/Decision-2.0-Kai-0.6B decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 5.83% |
| Assembly | 0.00% | 0.00% | 2.50% |
| Support | 1.67% | 0.00% | 2.50% |
| Presenter voice control | 0.00% | 0.00% | 4.17% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 44, target_result: 43, rerun_scope: 8, process: 3, owner: 3, inspect_file: 2 | 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14 |
| lite_debugging_b | route: 46, target_result: 37, process: 12, rerun_scope: 8, control_action: 4, owner: 4 | 0, 1, 2, 3, 4, 5, 7, 8, 11, 12, 14, 15 |
| lite_assembly_a | route: 51, stage: 40, destination: 19, target: 15, method: 14, next_step: 6 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_assembly_b | route: 49, stage: 44, destination: 16, target: 15, method: 15, next_step: 8 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_support_a | payment_stage: 37, recorder: 30, instrument: 22, route: 17, service_action: 11, hold_action: 5, service_target: 3 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_support_b | contact_channel: 48, route: 47, repair_action: 29, delivery_action: 18, repair_target: 10, cancellation_action: 4, delivery_target: 2 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_presenter_a | slide: 32, mode: 30, host_cue: 25, captions: 21, clip_state: 10, question_card: 9 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_presenter_b | slide: 56, host_cue: 45, captions: 37, mode: 33, question_card: 16, clip_state: 5 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/decision20-pro6000-20261003/pass3/kai-06b/run.json)
- [Frozen episodes](../../../../../runs/decision20-pro6000-20261003/pass3/kai-06b/episodes.json)
- [Release and response events](../../../../../runs/decision20-pro6000-20261003/pass3/kai-06b/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py --run runs/decision20-pro6000-20261003/pass3/kai-06b --out docs/lite/results/decision20-pro6000-20261003/kai-06b-pass3 --label 'Decision-2.0-Kai-0.6B — pass 3'
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 6037458,
  "cached_tokens": 0,
  "output_tokens": 0,
  "reasoning_tokens": 0
}
```
