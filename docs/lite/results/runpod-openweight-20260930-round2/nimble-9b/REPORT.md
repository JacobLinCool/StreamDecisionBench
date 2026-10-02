# SDB log-AUC: Bespoke Nimble-9B

Primary normalized log-AUC over 0.5–8 s: **10.42%**; untimed accuracy: 22.50%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 1.25 |
| procedural_coaching | 6.03 |
| support_call_assist | 21.36 |
| presenter_voice_control | 13.05 |

Quadrature: 512 log-spaced subintervals; maximum change from the preceding grid 0.000601 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: bespokelabs/Bespoke-Nimble-9B

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: bespokelabs/Bespoke-Nimble-9B. All model scores use recorded responses.

**Untimed decision accuracy: 22.50%; In-force accuracy (transport retries excluded): 11.78%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 11.78% (range 11.78%–11.78%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 0.00% | 2.50% | 2.27% | 0.00% |
| Assembly | 26.67% | 9.19% | 5.76% | 5.00% |
| Support | 30.83% | 22.29% | 18.70% | 11.67% |
| Presenter voice control | 32.50% | 13.13% | 8.88% | 21.67% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Network-removed estimate (secondary)

Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + decode (proportional to output tokens, for text-generating models). The token-independent remainder is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Estimated network 0.000 s (range 0.000–0.000 s); prefill 1773.1 ms/1k tokens; no decode term (the model does not generate text); fastest response 1.511 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 11.78% | 11.78% | 11.78%–11.78% | 22.50% |
| IDE debugging | 2.50% | 2.50% | 2.50%–2.50% | 0.00% |
| Assembly | 9.19% | 9.19% | 9.19%–9.19% | 26.67% |
| Support | 22.29% | 22.29% | 22.29%–22.29% | 30.83% |
| Presenter voice control | 13.13% | 13.13% | 13.13%–13.13% | 32.50% |

Unconstrained intercept -33.381043 s (range -47.405119–-24.108623 s). Extrapolation to zero tokens can be negative; negative latency cannot be removed, so replay projects it to zero. analysis.json retains the unconstrained estimate. Scores and recordings are unchanged.

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include fixed server time, so it bounds the network effect from above. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 0.00% | 0.00% | 8.29 / 26.30 | 0 |
| lite_debugging_b | 21 | 0.00% | 5.00% | 3.78 / 19.79 | 0 |
| lite_assembly_a | 21 | 28.33% | 11.93% | 8.41 / 52.50 | 0 |
| lite_assembly_b | 23 | 25.00% | 6.46% | 11.08 / 52.00 | 0 |
| lite_support_a | 22 | 30.00% | 23.55% | 2.00 / 5.14 | 0 |
| lite_support_b | 24 | 31.67% | 21.02% | 2.02 / 4.80 | 0 |
| lite_presenter_a | 24 | 50.00% | 17.79% | 16.72 / 41.58 | 0 |
| lite_presenter_b | 22 | 15.00% | 8.46% | 17.40 / 41.91 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 6.162 s, p95 41.782 s; includes same-host native calls, queueing and inference.
- Maximum recorded release lag 0.0023 s; maximum dispatch lag 0.0000 s.
- 62 states have only inactive-field errors, leaving the application decision correct.
- 400 updates accepted on the reconstructed timeline; rejected responses: {"after_horizon": 80}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. Native calls have no network timeout; the setting's process timeout is 3600 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 21.11 s; correct for its source but wrong for current evidence 130.45 s; wrong for both source and current evidence 695.38 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.346 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 3 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 11.77% | 8.90% |
| IDE debugging | 2.50% | 2.27% |
| Assembly | 9.19% | 5.76% |
| Support | 22.28% | 18.69% |
| Presenter voice control | 13.12% | 8.88% |

Raw logical request duration, including failed attempts and retry waits: p50 6.162 s, p95 41.782 s; 400 accepted raw-clock updates.

Exhausted retries or non-transport errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | bespokelabs/Bespoke-Nimble-9B decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 0.00% |
| Assembly | 0.00% | 0.00% | 26.67% |
| Support | 1.67% | 0.00% | 30.83% |
| Presenter voice control | 0.00% | 0.00% | 32.50% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 52, process: 42, target_result: 9, rerun_scope: 6, owner: 2, inspect_file: 1 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_debugging_b | route: 50, process: 37, target_result: 5, owner: 3, rerun_scope: 2 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_assembly_a | route: 37, destination: 15, next_step: 9, stage: 7, target: 6, method: 1 | 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13 |
| lite_assembly_b | route: 38, target: 18, stage: 12, destination: 8, next_step: 6, method: 3 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_support_a | payment_stage: 20, recorder: 20, route: 7, service_action: 6, hold_action: 4, instrument: 2 | 0, 4, 5, 6, 7, 11, 18, 19, 20, 21, 22, 23 |
| lite_support_b | route: 31, repair_action: 14, contact_channel: 7, delivery_action: 4, cancellation_action: 2 | 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 14, 15 |
| lite_presenter_a | slide: 21, host_cue: 16, mode: 8, question_card: 8, captions: 5 | 3, 6, 7, 8, 14, 15, 16, 30, 33, 36, 40, 41 |
| lite_presenter_b | host_cue: 38, slide: 28, mode: 22, question_card: 11, captions: 7 | 0, 1, 2, 4, 5, 6, 7, 8, 16, 17, 18, 19 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/runpod-openweight-20260930-round2/runs/nimble-9b/run.json)
- [Frozen episodes](../../../../../runs/runpod-openweight-20260930-round2/runs/nimble-9b/episodes.json)
- [Release and response events](../../../../../runs/runpod-openweight-20260930-round2/runs/nimble-9b/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py --run runs/runpod-openweight-20260930-round2/runs/nimble-9b --out docs/lite/results/runpod-openweight-20260930-round2/nimble-9b --label 'Bespoke Nimble-9B'
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 10652818,
  "cached_tokens": 0,
  "output_tokens": 0,
  "reasoning_tokens": 0
}
```
