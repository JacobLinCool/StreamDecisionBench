# SDB log-AUC: Luna low — pass 3

Primary normalized log-AUC over 0.5–8 s: **44.86%**; untimed accuracy: 91.04%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 47.53 |
| procedural_coaching | 43.97 |
| support_call_assist | 42.46 |
| presenter_voice_control | 45.47 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000415 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: gpt-5.6-luna low

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: gpt-5.6-luna, reasoning effort low. All model scores use recorded responses.

**Untimed decision accuracy: 91.04%; In-force accuracy (transport retries excluded): 46.98%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 56.85% (range 53.86%–58.58%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 94.17% | 51.47% | 46.44% | 94.17% |
| Assembly | 86.67% | 45.49% | 34.89% | 85.00% |
| Support | 85.83% | 46.44% | 38.40% | 80.00% |
| Presenter voice control | 97.50% | 44.52% | 32.49% | 97.50% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Network-removed estimate (secondary)

Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + decode (proportional to output tokens, for text-generating models). The token-independent remainder is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Estimated network 0.673 s (range 0.476–0.784 s); prefill 39.6 ms/1k tokens; decode 9.04 ms/token; fastest response 1.681 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 46.98% | 56.85% | 53.86%–58.58% | 91.04% |
| IDE debugging | 51.47% | 61.54% | 58.66%–63.16% | 94.17% |
| Assembly | 45.49% | 55.44% | 52.37%–57.20% | 86.67% |
| Support | 46.44% | 56.62% | 53.47%–58.42% | 85.83% |
| Presenter voice control | 44.52% | 53.81% | 50.94%–55.56% | 97.50% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include fixed server time, so it bounds the network effect from above. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 96.67% | 60.88% | 2.29 / 3.23 | 0 |
| lite_debugging_b | 21 | 91.67% | 42.07% | 2.87 / 4.08 | 0 |
| lite_assembly_a | 21 | 91.67% | 48.89% | 2.63 / 4.17 | 0 |
| lite_assembly_b | 23 | 81.67% | 42.09% | 2.68 / 4.05 | 0 |
| lite_support_a | 22 | 83.33% | 45.03% | 2.20 / 2.93 | 0 |
| lite_support_b | 24 | 88.33% | 47.86% | 2.26 / 2.73 | 0 |
| lite_presenter_a | 24 | 100.00% | 46.29% | 2.67 / 3.82 | 0 |
| lite_presenter_b | 22 | 95.00% | 42.74% | 3.16 / 4.21 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 2.516 s, p95 3.979 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0101 s; maximum dispatch lag 0.0000 s.
- 9 states have only inactive-field errors, leaving the application decision correct.
- 469 updates accepted on the reconstructed timeline; rejected responses: {"after_horizon": 7, "older_than_active": 4}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 20 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 17.88 s; correct for its source but wrong for current evidence 414.21 s; wrong for both source and current evidence 76.89 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.251 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 46.97% | 38.04% |
| IDE debugging | 51.47% | 46.43% |
| Assembly | 45.48% | 34.88% |
| Support | 46.44% | 38.39% |
| Presenter voice control | 44.51% | 32.48% |

Raw logical request duration, including failed attempts and retry waits: p50 2.516 s, p95 3.979 s; 469 accepted raw-clock updates.

Exhausted retries or non-transport errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | gpt-5.6-luna low decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 94.17% |
| Assembly | 0.00% | 0.00% | 86.67% |
| Support | 1.67% | 0.00% | 85.83% |
| Presenter voice control | 0.00% | 0.00% | 97.50% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 2 | 8, 42 |
| lite_debugging_b | route: 4, owner: 2, process: 1, target_result: 1 | 22, 31, 32, 37, 49 |
| lite_assembly_a | route: 3, next_step: 2, target: 2 | 31, 32, 45, 46, 48 |
| lite_assembly_b | route: 10, target: 2, method: 2, next_step: 1 | 4, 6, 7, 32, 33, 41, 42, 43, 44, 48, 49 |
| lite_support_a | recorder: 10 | 13, 18, 20, 21, 42, 43, 44, 46, 48, 49 |
| lite_support_b | route: 7, repair_target: 3, repair_action: 3, delivery_action: 2, delivery_target: 1 | 4, 8, 39, 42, 54, 55, 57 |
| lite_presenter_a | None | None |
| lite_presenter_b | slide: 2, question_card: 1 | 5, 38, 45 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../../PROTOCOL.md)
- [Debugging rules](../../../../debugging.md), [assembly rules](../../../../assembly.md), [support rules](../../../../support.md), [presenter rules](../../../../presenter.md)
- [Frozen run](../../../../../../runs/hosted-api-repeats-20261003/pass3/gpt-5.6-luna-low/run.json)
- [Frozen episodes](../../../../../../runs/hosted-api-repeats-20261003/pass3/gpt-5.6-luna-low/episodes.json)
- [Release and response events](../../../../../../runs/hosted-api-repeats-20261003/pass3/gpt-5.6-luna-low/events.jsonl)
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
  "output_tokens": 79906,
  "reasoning_tokens": 57466
}
```
