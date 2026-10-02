# SDB log-AUC: Bespoke Nimble-9B

Primary normalized log-AUC over 0.5–8 s: **13.34%**; untimed accuracy: 22.29%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 0.82 |
| procedural_coaching | 8.92 |
| support_call_assist | 24.09 |
| presenter_voice_control | 19.54 |

Quadrature: 512 log-spaced subintervals; maximum change from the preceding grid 0.000309 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: bespokelabs/Bespoke-Nimble-9B

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: bespokelabs/Bespoke-Nimble-9B. All model scores use recorded responses.

**Untimed decision accuracy: 22.29%; In-force accuracy (transport retries excluded): 13.16%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 13.16% (range 13.16%–13.16%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 0.00% | 0.77% | 0.70% | 0.00% |
| Assembly | 26.67% | 7.13% | 7.85% | 5.00% |
| Support | 30.83% | 25.76% | 22.73% | 11.67% |
| Presenter voice control | 31.67% | 18.98% | 12.79% | 21.67% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Network-removed estimate (secondary)

Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + decode (proportional to output tokens, for text-generating models). The token-independent remainder is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Estimated network 0.000 s (range 0.000–0.000 s); prefill 139.5 ms/1k tokens; no decode term (the model does not generate text); fastest response 1.059 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 13.16% | 13.16% | 13.16%–13.16% | 22.29% |
| IDE debugging | 0.77% | 0.77% | 0.77%–0.77% | 0.00% |
| Assembly | 7.13% | 7.13% | 7.13%–7.13% | 26.67% |
| Support | 25.76% | 25.76% | 25.76%–25.76% | 30.83% |
| Presenter voice control | 18.98% | 18.98% | 18.98%–18.98% | 31.67% |

Unconstrained intercept -1.356233 s (range -7.188245–-0.136548 s). Extrapolation to zero tokens can be negative; negative latency cannot be removed, so replay projects it to zero. analysis.json retains the unconstrained estimate. Scores and recordings are unchanged.

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include fixed server time, so it bounds the network effect from above. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 0.00% | 0.00% | 1.82 / 9.44 | 0 |
| lite_debugging_b | 21 | 0.00% | 1.53% | 2.48 / 8.67 | 0 |
| lite_assembly_a | 21 | 28.33% | 5.77% | 2.16 / 26.62 | 0 |
| lite_assembly_b | 23 | 25.00% | 8.49% | 3.38 / 24.02 | 0 |
| lite_support_a | 22 | 30.00% | 26.79% | 1.34 / 1.70 | 0 |
| lite_support_b | 24 | 31.67% | 24.73% | 1.38 / 1.63 | 0 |
| lite_presenter_a | 24 | 48.33% | 28.97% | 3.62 / 12.82 | 0 |
| lite_presenter_b | 22 | 15.00% | 8.99% | 2.98 / 10.42 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 1.973 s, p95 17.212 s; includes same-host native calls, queueing and inference.
- Maximum recorded release lag 0.0467 s; maximum dispatch lag 0.0000 s.
- 61 states have only inactive-field errors, leaving the application decision correct.
- 445 updates accepted on the reconstructed timeline; rejected responses: {"after_horizon": 35}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. Native calls have no network timeout; the setting's process timeout is 3600 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 22.01 s; correct for its source but wrong for current evidence 90.83 s; wrong for both source and current evidence 720.85 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.502 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 3 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 13.16% | 11.01% |
| IDE debugging | 0.77% | 0.70% |
| Assembly | 7.13% | 7.85% |
| Support | 25.76% | 22.72% |
| Presenter voice control | 18.97% | 12.78% |

Raw logical request duration, including failed attempts and retry waits: p50 1.973 s, p95 17.212 s; 445 accepted raw-clock updates.

Exhausted retries or non-transport errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | bespokelabs/Bespoke-Nimble-9B decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 0.00% |
| Assembly | 0.00% | 0.00% | 26.67% |
| Support | 1.67% | 0.00% | 30.83% |
| Presenter voice control | 0.00% | 0.00% | 31.67% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 52, process: 42, target_result: 9, rerun_scope: 6, owner: 2, inspect_file: 1 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_debugging_b | route: 51, process: 38, target_result: 5, owner: 2, rerun_scope: 2 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_assembly_a | route: 37, destination: 15, next_step: 9, stage: 7, target: 6, method: 1 | 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13 |
| lite_assembly_b | route: 38, target: 18, stage: 12, destination: 8, next_step: 6, method: 3 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_support_a | payment_stage: 20, recorder: 20, route: 7, service_action: 6, hold_action: 4, instrument: 2 | 0, 4, 5, 6, 7, 11, 18, 19, 20, 21, 22, 23 |
| lite_support_b | route: 31, repair_action: 14, contact_channel: 7, delivery_action: 4, cancellation_action: 2 | 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 14, 15 |
| lite_presenter_a | slide: 21, host_cue: 17, mode: 8, question_card: 8, captions: 5 | 3, 6, 7, 8, 14, 15, 16, 30, 33, 36, 37, 40 |
| lite_presenter_b | host_cue: 38, slide: 28, mode: 22, question_card: 11, captions: 7 | 0, 1, 2, 4, 5, 6, 7, 8, 16, 17, 18, 19 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/pro6000-lab-20261001-pass2/runs/nimble-9b/run.json)
- [Frozen episodes](../../../../../runs/pro6000-lab-20261001-pass2/runs/nimble-9b/episodes.json)
- [Release and response events](../../../../../runs/pro6000-lab-20261001-pass2/runs/nimble-9b/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py
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
