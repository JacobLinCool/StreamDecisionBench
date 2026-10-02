# SDB log-AUC: Laya typed-decisions

Primary normalized log-AUC over 0.5–8 s: **1.46%**; untimed accuracy: 1.46%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 0.00 |
| procedural_coaching | 0.00 |
| support_call_assist | 1.67 |
| presenter_voice_control | 4.17 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000153 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: convaiinnovations/laya-typed-decisions

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: convaiinnovations/laya-typed-decisions. All model scores use recorded responses.

**Untimed decision accuracy: 1.46%; In-force accuracy (transport retries excluded): 1.46%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 1.46% (range 1.46%–1.46%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 0.00% | 0.00% |
| Assembly | 0.00% | 0.00% | 0.00% | 0.00% |
| Support | 1.67% | 1.67% | 4.17% | 0.00% |
| Presenter voice control | 4.17% | 4.17% | 6.00% | 0.00% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Network-removed estimate (secondary)

Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + decode (proportional to output tokens, for text-generating models). The token-independent remainder is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Estimated network 0.000 s (range 0.000–0.000 s); prefill 11.8 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.066 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 1.46% | 1.46% | 1.46%–1.46% | 1.46% |
| IDE debugging | 0.00% | 0.00% | 0.00%–0.00% | 0.00% |
| Assembly | 0.00% | 0.00% | 0.00%–0.00% | 0.00% |
| Support | 1.67% | 1.67% | 1.67%–1.67% | 1.67% |
| Presenter voice control | 4.17% | 4.17% | 4.17%–4.17% | 4.17% |

Unconstrained intercept -0.026295 s (range -0.033265–-0.020150 s). Extrapolation to zero tokens can be negative; negative latency cannot be removed, so replay projects it to zero. analysis.json retains the unconstrained estimate. Scores and recordings are unchanged.

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include fixed server time, so it bounds the network effect from above. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 0.00% | 0.00% | 0.15 / 0.21 | 0 |
| lite_debugging_b | 21 | 0.00% | 0.00% | 0.14 / 0.21 | 0 |
| lite_assembly_a | 21 | 0.00% | 0.00% | 0.17 / 0.30 | 0 |
| lite_assembly_b | 23 | 0.00% | 0.00% | 0.17 / 0.30 | 0 |
| lite_support_a | 22 | 1.67% | 1.67% | 0.10 / 0.12 | 0 |
| lite_support_b | 24 | 1.67% | 1.67% | 0.10 / 0.11 | 0 |
| lite_presenter_a | 24 | 8.33% | 8.33% | 0.18 / 0.22 | 0 |
| lite_presenter_b | 22 | 0.00% | 0.00% | 0.18 / 0.22 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 0.144 s, p95 0.257 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0003 s; maximum dispatch lag 0.0000 s.
- 7 states have only inactive-field errors, leaving the application decision correct.
- 480 updates accepted on the reconstructed timeline; rejected responses: {}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 90 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 1.03 s; correct for its source but wrong for current evidence 0.79 s; wrong for both source and current evidence 944.18 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.461 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 3 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 1.46% | 2.54% |
| IDE debugging | 0.00% | 0.00% |
| Assembly | 0.00% | 0.00% |
| Support | 1.67% | 4.17% |
| Presenter voice control | 4.17% | 6.00% |

Raw logical request duration, including failed attempts and retry waits: p50 0.144 s, p95 0.257 s; 480 accepted raw-clock updates.

Exhausted retries or non-transport errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | convaiinnovations/laya-typed-decisions decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 0.00% |
| Assembly | 0.00% | 0.00% | 0.00% |
| Support | 1.67% | 0.00% | 1.67% |
| Presenter voice control | 0.00% | 0.00% | 4.17% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 56, process: 45, target_result: 33, rerun_scope: 8, inspect_file: 2 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_debugging_b | route: 58, process: 46, target_result: 41, rerun_scope: 6, owner: 4, control_action: 2 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_assembly_a | route: 50, stage: 41, destination: 22, target: 15, method: 12, next_step: 6 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_assembly_b | stage: 48, route: 48, target: 17, method: 14, destination: 13, next_step: 8 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_support_a | recorder: 39, payment_stage: 36, route: 24, instrument: 24, service_target: 11, service_action: 11, hold_action: 4 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_support_b | route: 45, contact_channel: 43, repair_action: 25, repair_target: 17, delivery_action: 16, delivery_target: 8, cancellation_action: 4 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_presenter_a | mode: 37, host_cue: 37, slide: 35, captions: 16, question_card: 9, clip_state: 6 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_presenter_b | slide: 50, mode: 42, host_cue: 41, captions: 25, question_card: 16, clip_state: 6 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/pro6000-lab-20261001/runs/laya-typed-decisions/run.json)
- [Frozen episodes](../../../../../runs/pro6000-lab-20261001/runs/laya-typed-decisions/episodes.json)
- [Release and response events](../../../../../runs/pro6000-lab-20261001/runs/laya-typed-decisions/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 6807175,
  "cached_tokens": 0,
  "output_tokens": 0,
  "reasoning_tokens": 0
}
```
