# SDB log-AUC: Clef

Primary normalized log-AUC over 0.5–8 s: **30.96%**; untimed accuracy: 38.96%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 34.53 |
| procedural_coaching | 13.51 |
| support_call_assist | 58.20 |
| presenter_voice_control | 17.58 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000489 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: clef

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: clef. All model scores use recorded responses.

**Untimed decision accuracy: 38.96%; In-force accuracy (transport retries excluded): 33.22%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 37.40% (range 36.47%–37.83%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 45.00% | 36.90% | 34.53% | 45.00% |
| Assembly | 15.83% | 14.71% | 17.30% | 8.33% |
| Support | 75.83% | 62.58% | 56.25% | 60.00% |
| Presenter voice control | 19.17% | 18.70% | 12.75% | 15.00% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Network-removed estimate (secondary)

Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + decode (proportional to output tokens, for text-generating models). The token-independent remainder is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Estimated network 0.683 s (range 0.530–0.759 s); prefill 29.9 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.477 s; 13 requests clamped at receipt.

| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 33.22% | 37.40% | 36.47%–37.83% | 38.96% |
| IDE debugging | 36.90% | 42.31% | 41.10%–42.91% | 45.00% |
| Assembly | 14.71% | 15.83% | 15.59%–15.93% | 15.83% |
| Support | 62.58% | 72.18% | 70.06%–73.17% | 75.83% |
| Presenter voice control | 18.70% | 19.26% | 19.14%–19.33% | 19.17% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include fixed server time, so it bounds the network effect from above. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 45.00% | 37.36% | 0.90 / 1.22 | 0 |
| lite_debugging_b | 21 | 45.00% | 36.44% | 0.91 / 1.41 | 0 |
| lite_assembly_a | 21 | 13.33% | 11.92% | 0.97 / 1.30 | 0 |
| lite_assembly_b | 23 | 18.33% | 17.50% | 1.00 / 1.33 | 0 |
| lite_support_a | 22 | 70.00% | 59.92% | 0.84 / 1.26 | 0 |
| lite_support_b | 24 | 81.67% | 65.24% | 0.96 / 1.23 | 0 |
| lite_presenter_a | 24 | 20.00% | 19.62% | 1.00 / 1.36 | 0 |
| lite_presenter_b | 22 | 18.33% | 17.77% | 1.02 / 1.55 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 0.947 s, p95 1.360 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0101 s; maximum dispatch lag 0.0000 s.
- 33 states have only inactive-field errors, leaving the application decision correct.
- 480 updates accepted on the reconstructed timeline; rejected responses: {}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 20 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 9.35 s; correct for its source but wrong for current evidence 59.35 s; wrong for both source and current evidence 572.36 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.223 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 33.22% | 30.21% |
| IDE debugging | 36.90% | 34.52% |
| Assembly | 14.71% | 17.30% |
| Support | 62.57% | 56.25% |
| Presenter voice control | 18.70% | 12.75% |

Raw logical request duration, including failed attempts and retry waits: p50 0.947 s, p95 1.360 s; 480 accepted raw-clock updates.

Exhausted retries or non-transport errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | clef decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 45.00% |
| Assembly | 0.00% | 0.00% | 15.83% |
| Support | 1.67% | 0.00% | 75.83% |
| Presenter voice control | 0.00% | 0.00% | 19.17% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 29, rerun_scope: 8, process: 4, inspect_file: 2 | 5, 6, 7, 8, 9, 10, 14, 15, 16, 17, 18, 19 |
| lite_debugging_b | route: 27, process: 10, rerun_scope: 6, owner: 6, control_action: 4 | 7, 8, 9, 11, 12, 18, 19, 20, 21, 22, 23, 24 |
| lite_assembly_a | route: 32, stage: 32, destination: 26, target: 12, method: 7, next_step: 6 | 1, 3, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17 |
| lite_assembly_b | route: 32, destination: 20, stage: 14, method: 8, next_step: 7, target: 4 | 1, 3, 4, 5, 6, 9, 10, 11, 16, 17, 18, 19 |
| lite_support_a | recorder: 9, payment_stage: 8, hold_action: 4 | 0, 1, 20, 21, 29, 30, 31, 32, 44, 45, 46, 47 |
| lite_support_b | repair_action: 6, delivery_action: 3, route: 2 | 10, 20, 21, 44, 48, 49, 50, 54, 55, 56, 57 |
| lite_presenter_a | mode: 27, slide: 24, clip_state: 16, captions: 16, question_card: 11, host_cue: 4 | 5, 6, 8, 14, 15, 16, 17, 18, 19, 20, 21, 22 |
| lite_presenter_b | mode: 43, slide: 42, question_card: 18, captions: 15, clip_state: 6, host_cue: 4 | 5, 6, 8, 12, 15, 16, 17, 18, 19, 20, 21, 22 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/lite-v1-clef-four-family-retry-v1/run.json)
- [Frozen episodes](../../../../../runs/lite-v1-clef-four-family-retry-v1/episodes.json)
- [Release and response events](../../../../../runs/lite-v1-clef-four-family-retry-v1/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py --run runs/lite-v1-clef-four-family-retry-v1 --out docs/lite/results/four-family/clef --label Clef
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 1379440,
  "cached_tokens": 0,
  "output_tokens": 0,
  "reasoning_tokens": 0
}
```
