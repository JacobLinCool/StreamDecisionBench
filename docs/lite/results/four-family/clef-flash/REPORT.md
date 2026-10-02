# SDB log-AUC: Clef Flash

Primary normalized log-AUC over 0.5–8 s: **19.69%**; untimed accuracy: 21.67%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 12.80 |
| procedural_coaching | 24.13 |
| support_call_assist | 28.38 |
| presenter_voice_control | 13.44 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000417 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: clef-flash

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: clef-flash. All model scores use recorded responses.

**Untimed decision accuracy: 21.67%; In-force accuracy (transport retries excluded): 20.24%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 21.10% (range 20.76%–21.13%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 15.00% | 13.34% | 12.28% | 11.67% |
| Assembly | 25.83% | 24.62% | 20.54% | 17.50% |
| Support | 30.83% | 29.20% | 28.84% | 27.50% |
| Presenter voice control | 15.00% | 13.81% | 13.34% | 3.33% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Network-removed estimate (secondary)

Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + decode (proportional to output tokens, for text-generating models). The token-independent remainder is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Estimated network 0.318 s (range 0.189–0.330 s); prefill 0.0 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.241 s; 48 requests clamped at receipt.

| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 20.24% | 21.10% | 20.76%–21.13% | 21.67% |
| IDE debugging | 13.34% | 14.13% | 13.81%–14.15% | 15.00% |
| Assembly | 24.62% | 25.68% | 25.25%–25.72% | 25.83% |
| Support | 29.20% | 30.24% | 29.83%–30.28% | 30.83% |
| Presenter voice control | 13.81% | 14.34% | 14.13%–14.36% | 15.00% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include fixed server time, so it bounds the network effect from above. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 18.33% | 16.66% | 0.54 / 1.05 | 0 |
| lite_debugging_b | 21 | 11.67% | 10.02% | 0.57 / 1.18 | 0 |
| lite_assembly_a | 21 | 31.67% | 30.92% | 0.56 / 1.01 | 0 |
| lite_assembly_b | 23 | 20.00% | 18.33% | 0.56 / 0.90 | 0 |
| lite_support_a | 22 | 20.00% | 18.21% | 0.55 / 1.08 | 0 |
| lite_support_b | 24 | 41.67% | 40.19% | 0.52 / 0.82 | 0 |
| lite_presenter_a | 24 | 18.33% | 17.65% | 0.49 / 1.03 | 0 |
| lite_presenter_b | 22 | 11.67% | 9.97% | 0.42 / 1.25 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 0.537 s, p95 1.096 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0064 s; maximum dispatch lag 0.0000 s.
- 32 states have only inactive-field errors, leaving the application decision correct.
- 480 updates accepted on the reconstructed timeline; rejected responses: {}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 20 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 6.46 s; correct for its source but wrong for current evidence 23.11 s; wrong for both source and current evidence 736.08 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.41% (2 failed attempts / 482 total attempts, including final successes).
- Logical request retry rate: 0.42% (2 retried requests / 480 logical requests).
- Failed attempt types: {"TimeoutError": 2}.
- Failed attempts took 40.224 s in total; excluded failures and retry waits total 40.224 s, and excluded dispatch queueing totals 0.229 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 20.24% | 18.75% |
| IDE debugging | 13.34% | 12.27% |
| Assembly | 24.62% | 20.54% |
| Support | 29.20% | 28.84% |
| Presenter voice control | 13.81% | 13.33% |

Raw logical request duration, including failed attempts and retry waits: p50 0.537 s, p95 1.113 s; 478 accepted raw-clock updates.

Exhausted retries or non-transport errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | clef-flash decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 15.00% |
| Assembly | 0.00% | 0.00% | 25.83% |
| Support | 1.67% | 0.00% | 30.83% |
| Presenter voice control | 0.00% | 0.00% | 15.00% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 46, process: 14, rerun_scope: 8, target_result: 6, inspect_file: 3, owner: 3 | 0, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13 |
| lite_debugging_b | route: 39, target_result: 21, process: 10, rerun_scope: 7, control_action: 4, owner: 4 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_assembly_a | route: 27, stage: 19, destination: 13, method: 12, target: 9, next_step: 7 | 2, 4, 5, 8, 9, 10, 11, 12, 13, 14, 15, 16 |
| lite_assembly_b | route: 31, stage: 20, method: 9, destination: 8, target: 7, next_step: 6 | 3, 6, 7, 8, 9, 11, 14, 16, 17, 19, 20, 21 |
| lite_support_a | recorder: 41, payment_stage: 21, hold_action: 4, service_action: 3, instrument: 2, route: 2 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_support_b | repair_action: 16, route: 10, delivery_action: 7, contact_channel: 2, cancellation_action: 2, repair_target: 2 | 0, 1, 4, 8, 9, 10, 11, 14, 15, 20, 21, 26 |
| lite_presenter_a | slide: 31, mode: 28, captions: 16, question_card: 11, clip_state: 6, host_cue: 4 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 11, 14, 15 |
| lite_presenter_b | slide: 47, mode: 43, question_card: 18, captions: 16, clip_state: 5, host_cue: 4 | 0, 1, 2, 3, 4, 5, 6, 11, 15, 16, 17, 18 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/lite-v1-clef-flash-four-family-retry-v1/run.json)
- [Frozen episodes](../../../../../runs/lite-v1-clef-flash-four-family-retry-v1/episodes.json)
- [Release and response events](../../../../../runs/lite-v1-clef-flash-four-family-retry-v1/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py --run runs/lite-v1-clef-flash-four-family-retry-v1 --out docs/lite/results/four-family/clef-flash --label 'Clef Flash'
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
