# SDB log-AUC: Luna none — pass 3

Primary normalized log-AUC over 0.5–8 s: **29.86%**; untimed accuracy: 41.87%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 12.57 |
| procedural_coaching | 16.30 |
| support_call_assist | 44.94 |
| presenter_voice_control | 45.65 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000373 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: gpt-5.6-luna none

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: gpt-5.6-luna, reasoning effort none. All model scores use recorded responses.

**Untimed decision accuracy: 41.87%; In-force accuracy (transport retries excluded): 32.08%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 39.88% (range 37.49%–39.96%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 15.83% | 13.64% | 11.81% | 13.33% |
| Assembly | 24.17% | 17.57% | 17.17% | 24.17% |
| Support | 66.67% | 48.24% | 45.23% | 56.67% |
| Presenter voice control | 60.83% | 48.86% | 42.65% | 58.33% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Network-removed estimate (secondary)

Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + decode (proportional to output tokens, for text-generating models). The token-independent remainder is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Estimated network 1.076 s (range 0.743–1.087 s); prefill 0.0 ms/1k tokens; decode 0.00 ms/token; fastest response 0.926 s; 48 requests clamped at receipt.

| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 32.08% | 39.88% | 37.49%–39.96% | 41.87% |
| IDE debugging | 13.64% | 14.95% | 14.56%–14.97% | 15.83% |
| Assembly | 17.57% | 22.90% | 21.28%–22.95% | 24.17% |
| Support | 48.24% | 62.12% | 57.83%–62.26% | 66.67% |
| Presenter voice control | 48.86% | 59.56% | 56.29%–59.67% | 60.83% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include fixed server time, so it bounds the network effect from above. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 13.33% | 10.98% | 1.24 / 1.59 | 0 |
| lite_debugging_b | 21 | 18.33% | 16.29% | 1.24 / 1.78 | 0 |
| lite_assembly_a | 21 | 20.00% | 16.19% | 1.47 / 1.86 | 0 |
| lite_assembly_b | 23 | 28.33% | 18.94% | 1.27 / 1.55 | 0 |
| lite_support_a | 22 | 63.33% | 44.96% | 1.49 / 1.93 | 0 |
| lite_support_b | 24 | 70.00% | 51.53% | 1.29 / 1.69 | 0 |
| lite_presenter_a | 24 | 73.33% | 60.42% | 1.20 / 1.89 | 0 |
| lite_presenter_b | 22 | 48.33% | 37.29% | 1.26 / 1.53 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 1.313 s, p95 1.742 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0101 s; maximum dispatch lag 0.0000 s.
- 18 states have only inactive-field errors, leaving the application decision correct.
- 478 updates accepted on the reconstructed timeline; rejected responses: {"older_than_active": 2}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 20 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 11.14 s; correct for its source but wrong for current evidence 99.11 s; wrong for both source and current evidence 541.81 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.249 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 32.07% | 29.21% |
| IDE debugging | 13.64% | 11.81% |
| Assembly | 17.57% | 17.16% |
| Support | 48.24% | 45.22% |
| Presenter voice control | 48.85% | 42.64% |

Raw logical request duration, including failed attempts and retry waits: p50 1.313 s, p95 1.742 s; 478 accepted raw-clock updates.

Exhausted retries or non-transport errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | gpt-5.6-luna none decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 15.83% |
| Assembly | 0.00% | 0.00% | 24.17% |
| Support | 1.67% | 0.00% | 66.67% |
| Presenter voice control | 0.00% | 0.00% | 60.83% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 37, target_result: 23, process: 22, rerun_scope: 10, inspect_file: 3, owner: 3 | 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13 |
| lite_debugging_b | route: 40, target_result: 23, rerun_scope: 8, process: 5, owner: 5, control_action: 2, inspect_file: 1 | 0, 2, 6, 7, 8, 9, 10, 11, 12, 17, 18, 19 |
| lite_assembly_a | route: 34, destination: 17, target: 13, next_step: 10, stage: 9, method: 8 | 0, 1, 2, 5, 6, 7, 8, 9, 10, 11, 12, 13 |
| lite_assembly_b | route: 33, stage: 15, destination: 15, next_step: 12, target: 3, method: 2 | 0, 1, 4, 5, 6, 7, 10, 11, 13, 16, 17, 18 |
| lite_support_a | recorder: 19, payment_stage: 4, hold_action: 3, instrument: 2, service_action: 1 | 10, 12, 13, 18, 19, 20, 21, 29, 30, 31, 32, 33 |
| lite_support_b | route: 16, repair_action: 7, repair_target: 3, delivery_action: 2 | 4, 11, 14, 16, 26, 27, 30, 42, 44, 46, 47, 49 |
| lite_presenter_a | captions: 8, mode: 4, question_card: 4, slide: 3, clip_state: 1 | 8, 22, 23, 29, 31, 32, 39, 45, 46, 50, 51, 52 |
| lite_presenter_b | slide: 25, host_cue: 9, mode: 7, question_card: 2, captions: 2, clip_state: 1 | 2, 4, 5, 6, 7, 8, 19, 20, 22, 23, 24, 26 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../../PROTOCOL.md)
- [Debugging rules](../../../../debugging.md), [assembly rules](../../../../assembly.md), [support rules](../../../../support.md), [presenter rules](../../../../presenter.md)
- [Frozen run](../../../../../../runs/hosted-api-repeats-20261003/pass3/gpt-5.6-luna-none/run.json)
- [Frozen episodes](../../../../../../runs/hosted-api-repeats-20261003/pass3/gpt-5.6-luna-none/episodes.json)
- [Release and response events](../../../../../../runs/hosted-api-repeats-20261003/pass3/gpt-5.6-luna-none/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_hosted.py --reports
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 1476489,
  "cached_tokens": 0,
  "output_tokens": 21480,
  "reasoning_tokens": 0
}
```
