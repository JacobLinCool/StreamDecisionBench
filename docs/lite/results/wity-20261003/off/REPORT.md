# SDB log-AUC: Wity-1 (off)

Primary normalized log-AUC over 0.5–8 s: **8.61%**; untimed accuracy: 10.21%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 0.00 |
| procedural_coaching | 3.01 |
| support_call_assist | 22.59 |
| presenter_voice_control | 8.85 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000832 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: wity-1

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. HTTP 429 honors Retry-After through a shared cooldown within the attempt budget. Requested model: wity-1. All model scores use recorded responses.

**Untimed decision accuracy: 10.21%; In-force accuracy (failed attempts and retry waits excluded): 9.22%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 9.22% (range 9.22%–9.43%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 0.00% | 0.00% |
| Assembly | 4.17% | 3.42% | 2.30% | 0.00% |
| Support | 26.67% | 24.32% | 21.12% | 7.50% |
| Presenter voice control | 10.00% | 9.14% | 5.47% | 6.67% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Network-removed estimate (secondary)

Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + decode (proportional to output tokens, for text-generating models). The token-independent remainder is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Estimated network 0.000 s (range 0.000–0.225 s); prefill 270.2 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.529 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 9.22% | 9.22% | 9.22%–9.43% | 10.21% |
| IDE debugging | 0.00% | 0.00% | 0.00%–0.00% | 0.00% |
| Assembly | 3.42% | 3.42% | 3.42%–3.52% | 4.17% |
| Support | 24.32% | 24.32% | 24.32%–24.88% | 26.67% |
| Presenter voice control | 9.14% | 9.14% | 9.14%–9.32% | 10.00% |

Unconstrained intercept -0.063708 s (range -0.348572–0.225363 s). Extrapolation to zero tokens can be negative; negative latency cannot be removed, so replay projects it to zero. analysis.json retains the unconstrained estimate. Scores and recordings are unchanged.

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include fixed server time, so it bounds the network effect from above. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 0.00% | 0.00% | 1.08 / 1.36 | 0 |
| lite_debugging_b | 21 | 0.00% | 0.00% | 1.19 / 1.53 | 0 |
| lite_assembly_a | 21 | 6.67% | 5.59% | 3.03 / 4.65 | 0 |
| lite_assembly_b | 23 | 1.67% | 1.25% | 5.79 / 25.95 | 0 |
| lite_support_a | 22 | 28.33% | 25.89% | 1.94 / 3.18 | 0 |
| lite_support_b | 24 | 25.00% | 22.75% | 0.72 / 1.41 | 0 |
| lite_presenter_a | 24 | 18.33% | 15.57% | 1.06 / 1.42 | 0 |
| lite_presenter_b | 22 | 1.67% | 2.70% | 1.34 / 1.60 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 1.291 s, p95 6.214 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0101 s; maximum dispatch lag 0.0000 s.
- 32 states have only inactive-field errors, leaving the application decision correct.
- 468 updates accepted on the reconstructed timeline; rejected responses: {"after_horizon": 12}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 180 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 16 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 10.00 s; correct for its source but wrong for current evidence 16.41 s; wrong for both source and current evidence 845.09 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.196 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.
- The immediate-first-retry rule above applies to transport failures. HTTP 429 uses Retry-After (delay-seconds or HTTP-date) as a minimum wait, with a shared episode cooldown. Without that header, bounded backoff starts at 1 s. The server's delay is not capped at 8 s. Concurrency is limited to 16 workers; rate-limit attempts count toward the same attempt budget.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 9.22% | 7.22% |
| IDE debugging | 0.00% | 0.00% |
| Assembly | 3.42% | 2.30% |
| Support | 24.32% | 21.12% |
| Presenter voice control | 9.14% | 5.47% |

Raw logical request duration, including failed attempts and retry waits: p50 1.291 s, p95 6.214 s; 468 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | wity-1 decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 0.00% |
| Assembly | 0.00% | 0.00% | 4.17% |
| Support | 1.67% | 0.00% | 26.67% |
| Presenter voice control | 0.00% | 0.00% | 10.00% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 49, process: 44, target_result: 17, inspect_file: 6, rerun_scope: 4, owner: 1 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_debugging_b | route: 52, process: 43, target_result: 21, rerun_scope: 5, control_action: 3, owner: 2, inspect_file: 1 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_assembly_a | route: 49, destination: 18, stage: 17, method: 13, next_step: 11, target: 9 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_assembly_b | route: 39, stage: 30, target: 18, method: 16, next_step: 12, destination: 10 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_support_a | recorder: 28, payment_stage: 21, service_action: 11, service_target: 10, route: 7, hold_action: 4, instrument: 1 | 4, 5, 6, 7, 10, 11, 12, 13, 20, 21, 22, 23 |
| lite_support_b | repair_action: 25, delivery_action: 12, route: 10, contact_channel: 4, cancellation_action: 2, repair_target: 2 | 0, 1, 4, 8, 9, 10, 11, 16, 17, 18, 19, 20 |
| lite_presenter_a | slide: 29, mode: 24, host_cue: 19, captions: 19, clip_state: 5, question_card: 4 | 0, 4, 5, 6, 7, 8, 13, 17, 18, 20, 21, 22 |
| lite_presenter_b | slide: 51, host_cue: 31, mode: 17, question_card: 8, captions: 3, clip_state: 2 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/wity-1-off-workers16-retry-after-20261003-pass1/run.json)
- [Frozen episodes](../../../../../runs/wity-1-off-workers16-retry-after-20261003-pass1/episodes.json)
- [Release and response events](../../../../../runs/wity-1-off-workers16-retry-after-20261003-pass1/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py --run runs/wity-1-off-workers16-retry-after-20261003-pass1 --out docs/lite/results/wity-20261003/off --label 'Wity-1 (off)'
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 1599899,
  "cached_tokens": 0,
  "output_tokens": 0,
  "reasoning_tokens": 0
}
```
