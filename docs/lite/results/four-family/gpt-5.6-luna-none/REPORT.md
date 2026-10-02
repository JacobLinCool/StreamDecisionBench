# SDB log-AUC: Luna none

Primary normalized log-AUC over 0.5–8 s: **30.67%**; untimed accuracy: 43.75%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 14.31 |
| procedural_coaching | 19.52 |
| support_call_assist | 43.31 |
| presenter_voice_control | 45.53 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000521 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: gpt-5.6-luna none

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: gpt-5.6-luna, reasoning effort none. All model scores use recorded responses.

**Untimed decision accuracy: 43.75%; In-force accuracy (transport retries excluded): 33.26%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 39.49% (range 36.82%–41.11%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 19.17% | 15.86% | 14.03% | 17.50% |
| Assembly | 30.00% | 21.14% | 20.30% | 27.50% |
| Support | 64.17% | 47.05% | 43.74% | 55.00% |
| Presenter voice control | 61.67% | 48.98% | 43.76% | 59.17% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Network-removed estimate (secondary)

Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + decode (proportional to output tokens, for text-generating models). The token-independent remainder is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Estimated network 0.863 s (range 0.496–1.090 s); prefill 0.0 ms/1k tokens; decode 4.81 ms/token; fastest response 0.937 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 33.26% | 39.49% | 36.82%–41.11% | 43.75% |
| IDE debugging | 15.86% | 17.65% | 16.89%–18.09% | 19.17% |
| Assembly | 21.14% | 25.94% | 23.82%–27.29% | 30.00% |
| Support | 47.05% | 57.12% | 52.83%–59.74% | 64.17% |
| Presenter voice control | 48.98% | 57.25% | 53.73%–59.32% | 61.67% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include fixed server time, so it bounds the network effect from above. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 18.33% | 13.37% | 1.33 / 2.03 | 0 |
| lite_debugging_b | 21 | 20.00% | 18.34% | 1.36 / 1.91 | 0 |
| lite_assembly_a | 21 | 33.33% | 24.42% | 1.36 / 1.98 | 0 |
| lite_assembly_b | 23 | 26.67% | 17.86% | 1.37 / 1.93 | 0 |
| lite_support_a | 22 | 58.33% | 41.32% | 1.33 / 1.82 | 0 |
| lite_support_b | 24 | 70.00% | 52.77% | 1.40 / 1.80 | 0 |
| lite_presenter_a | 24 | 73.33% | 57.01% | 1.20 / 1.52 | 0 |
| lite_presenter_b | 22 | 50.00% | 40.95% | 1.22 / 1.54 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 1.318 s, p95 1.878 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0101 s; maximum dispatch lag 0.0000 s.
- 19 states have only inactive-field errors, leaving the application decision correct.
- 478 updates accepted on the reconstructed timeline; rejected responses: {"older_than_active": 2}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 20 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 12.90 s; correct for its source but wrong for current evidence 106.65 s; wrong for both source and current evidence 521.20 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.224 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 33.25% | 30.45% |
| IDE debugging | 15.86% | 14.03% |
| Assembly | 21.13% | 20.29% |
| Support | 47.04% | 43.73% |
| Presenter voice control | 48.97% | 43.76% |

Raw logical request duration, including failed attempts and retry waits: p50 1.318 s, p95 1.878 s; 478 accepted raw-clock updates.

Exhausted retries or non-transport errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | gpt-5.6-luna none decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 19.17% |
| Assembly | 0.00% | 0.00% | 30.00% |
| Support | 1.67% | 0.00% | 64.17% |
| Presenter voice control | 0.00% | 0.00% | 61.67% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 36, target_result: 26, process: 22, rerun_scope: 10, inspect_file: 3, owner: 2 | 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14 |
| lite_debugging_b | route: 37, target_result: 22, rerun_scope: 8, owner: 6, process: 5, control_action: 2, inspect_file: 1 | 0, 2, 4, 6, 7, 8, 9, 10, 11, 12, 18, 19 |
| lite_assembly_a | route: 30, destination: 15, target: 10, next_step: 9, stage: 9, method: 5 | 0, 2, 7, 8, 9, 10, 11, 12, 14, 17, 18, 22 |
| lite_assembly_b | route: 36, stage: 15, destination: 15, next_step: 12, target: 4, method: 4 | 0, 1, 4, 5, 6, 7, 10, 11, 16, 17, 18, 19 |
| lite_support_a | recorder: 20, payment_stage: 3, service_action: 2, hold_action: 2, instrument: 2 | 1, 10, 12, 13, 19, 20, 21, 22, 23, 29, 30, 31 |
| lite_support_b | route: 16, repair_action: 8, repair_target: 2, delivery_action: 1 | 4, 23, 26, 27, 30, 37, 42, 44, 46, 47, 49, 50 |
| lite_presenter_a | captions: 8, mode: 5, slide: 4, question_card: 4, clip_state: 1, host_cue: 1 | 8, 22, 23, 27, 29, 32, 34, 39, 46, 50, 51, 52 |
| lite_presenter_b | slide: 23, host_cue: 10, mode: 8, question_card: 3, captions: 3 | 2, 3, 4, 5, 6, 7, 8, 20, 21, 23, 26, 27 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/lite-v1-gpt-5.6-luna-none-four-family-retry-v1/run.json)
- [Frozen episodes](../../../../../runs/lite-v1-gpt-5.6-luna-none-four-family-retry-v1/episodes.json)
- [Release and response events](../../../../../runs/lite-v1-gpt-5.6-luna-none-four-family-retry-v1/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py --run runs/lite-v1-gpt-5.6-luna-none-four-family-retry-v1 --out docs/lite/results/four-family/gpt-5.6-luna-none --label 'Luna none'
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
