# SDB log-AUC: Terra low — pass 3

Primary normalized log-AUC over 0.5–8 s: **54.10%**; untimed accuracy: 95.62%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 54.90 |
| procedural_coaching | 51.05 |
| support_call_assist | 56.31 |
| presenter_voice_control | 54.16 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000411 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: gpt-5.6-terra low

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: gpt-5.6-terra, reasoning effort low. All model scores use recorded responses.

**Untimed decision accuracy: 95.62%; In-force accuracy (transport retries excluded): 58.63%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 70.51% (range 68.14%–71.07%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 98.33% | 61.18% | 55.08% | 98.33% |
| Assembly | 91.67% | 54.48% | 45.18% | 91.67% |
| Support | 93.33% | 62.41% | 53.81% | 93.33% |
| Presenter voice control | 99.17% | 56.43% | 44.70% | 99.17% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Network-removed estimate (secondary)

Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + decode (proportional to output tokens, for text-generating models). The token-independent remainder is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Estimated network 0.688 s (range 0.554–0.720 s); prefill 0.0 ms/1k tokens; decode 8.91 ms/token; fastest response 0.976 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 58.63% | 70.51% | 68.14%–71.07% | 95.62% |
| IDE debugging | 61.18% | 73.27% | 70.92%–73.82% | 98.33% |
| Assembly | 54.48% | 66.12% | 63.83%–66.66% | 91.67% |
| Support | 62.41% | 74.22% | 71.87%–74.77% | 93.33% |
| Presenter voice control | 56.43% | 68.43% | 65.96%–69.01% | 99.17% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include fixed server time, so it bounds the network effect from above. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 100.00% | 62.94% | 1.95 / 2.84 | 0 |
| lite_debugging_b | 21 | 96.67% | 59.43% | 1.91 / 3.03 | 0 |
| lite_assembly_a | 21 | 96.67% | 59.48% | 2.02 / 3.08 | 0 |
| lite_assembly_b | 23 | 86.67% | 49.48% | 2.37 / 3.19 | 0 |
| lite_support_a | 22 | 95.00% | 63.79% | 1.89 / 2.17 | 0 |
| lite_support_b | 24 | 91.67% | 61.03% | 1.62 / 2.20 | 0 |
| lite_presenter_a | 24 | 100.00% | 54.62% | 2.16 / 2.91 | 0 |
| lite_presenter_b | 22 | 98.33% | 58.25% | 2.29 / 3.01 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 1.958 s, p95 2.958 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0101 s; maximum dispatch lag 0.0000 s.
- 0 states have only inactive-field errors, leaving the application decision correct.
- 476 updates accepted on the reconstructed timeline; rejected responses: {"older_than_active": 2, "after_horizon": 2}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 20 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 16.06 s; correct for its source but wrong for current evidence 343.34 s; wrong for both source and current evidence 37.80 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.246 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 58.62% | 49.68% |
| IDE debugging | 61.18% | 55.07% |
| Assembly | 54.47% | 45.17% |
| Support | 62.40% | 53.80% |
| Presenter voice control | 56.43% | 44.69% |

Raw logical request duration, including failed attempts and retry waits: p50 1.958 s, p95 2.958 s; 476 accepted raw-clock updates.

Exhausted retries or non-transport errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | gpt-5.6-terra low decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 98.33% |
| Assembly | 0.00% | 0.00% | 91.67% |
| Support | 1.67% | 0.00% | 93.33% |
| Presenter voice control | 0.00% | 0.00% | 99.17% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | None | None |
| lite_debugging_b | rerun_scope: 2, route: 1 | 11, 27 |
| lite_assembly_a | route: 2, destination: 1 | 16, 48 |
| lite_assembly_b | route: 8, next_step: 1 | 7, 32, 33, 38, 42, 43, 48, 49 |
| lite_support_a | recorder: 3 | 48, 51, 53 |
| lite_support_b | route: 5, repair_target: 5, repair_action: 5 | 51, 53, 55, 56, 57 |
| lite_presenter_a | None | None |
| lite_presenter_b | slide: 1 | 55 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../../PROTOCOL.md)
- [Debugging rules](../../../../debugging.md), [assembly rules](../../../../assembly.md), [support rules](../../../../support.md), [presenter rules](../../../../presenter.md)
- [Frozen run](../../../../../../runs/hosted-api-repeats-20261003/pass3/gpt-5.6-terra-low/run.json)
- [Frozen episodes](../../../../../../runs/hosted-api-repeats-20261003/pass3/gpt-5.6-terra-low/episodes.json)
- [Release and response events](../../../../../../runs/hosted-api-repeats-20261003/pass3/gpt-5.6-terra-low/events.jsonl)
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
  "output_tokens": 57629,
  "reasoning_tokens": 35301
}
```
