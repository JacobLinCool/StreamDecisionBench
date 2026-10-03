# SDB log-AUC: Terra low — pass 2

Primary normalized log-AUC over 0.5–8 s: **54.03%**; untimed accuracy: 96.25%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 56.23 |
| procedural_coaching | 50.36 |
| support_call_assist | 57.06 |
| presenter_voice_control | 52.47 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000412 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: gpt-5.6-terra low

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: gpt-5.6-terra, reasoning effort low. All model scores use recorded responses.

**Untimed decision accuracy: 96.25%; In-force accuracy (transport retries excluded): 58.82%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 70.19% (range 66.68%–72.51%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 100.00% | 63.09% | 57.34% | 100.00% |
| Assembly | 90.00% | 53.88% | 44.05% | 90.00% |
| Support | 98.33% | 63.26% | 55.30% | 98.33% |
| Presenter voice control | 96.67% | 55.07% | 43.99% | 96.67% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Network-removed estimate (secondary)

Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + decode (proportional to output tokens, for text-generating models). The token-independent remainder is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Estimated network 0.665 s (range 0.463–0.798 s); prefill 0.0 ms/1k tokens; decode 9.20 ms/token; fastest response 1.071 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 58.82% | 70.19% | 66.68%–72.51% | 96.25% |
| IDE debugging | 63.09% | 74.86% | 71.23%–77.24% | 100.00% |
| Assembly | 53.88% | 64.78% | 61.42%–66.99% | 90.00% |
| Support | 63.26% | 75.44% | 71.73%–77.87% | 98.33% |
| Presenter voice control | 55.07% | 65.69% | 62.33%–67.95% | 96.67% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include fixed server time, so it bounds the network effect from above. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 100.00% | 64.78% | 2.03 / 2.66 | 0 |
| lite_debugging_b | 21 | 100.00% | 61.39% | 1.96 / 3.07 | 0 |
| lite_assembly_a | 21 | 93.33% | 57.81% | 1.98 / 2.76 | 0 |
| lite_assembly_b | 23 | 86.67% | 49.96% | 2.16 / 3.13 | 0 |
| lite_support_a | 22 | 100.00% | 62.92% | 1.86 / 2.35 | 0 |
| lite_support_b | 24 | 96.67% | 63.59% | 1.64 / 2.26 | 0 |
| lite_presenter_a | 24 | 98.33% | 56.60% | 2.06 / 2.81 | 0 |
| lite_presenter_b | 22 | 95.00% | 53.54% | 2.38 / 3.38 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 2.005 s, p95 3.022 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0103 s; maximum dispatch lag 0.0000 s.
- 0 states have only inactive-field errors, leaving the application decision correct.
- 476 updates accepted on the reconstructed timeline; rejected responses: {"after_horizon": 4}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 20 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 14.80 s; correct for its source but wrong for current evidence 349.38 s; wrong for both source and current evidence 31.12 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.252 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 58.82% | 50.16% |
| IDE debugging | 63.08% | 57.33% |
| Assembly | 53.87% | 44.04% |
| Support | 63.25% | 55.29% |
| Presenter voice control | 55.06% | 43.98% |

Raw logical request duration, including failed attempts and retry waits: p50 2.005 s, p95 3.022 s; 476 accepted raw-clock updates.

Exhausted retries or non-transport errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | gpt-5.6-terra low decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 100.00% |
| Assembly | 0.00% | 0.00% | 90.00% |
| Support | 1.67% | 0.00% | 98.33% |
| Presenter voice control | 0.00% | 0.00% | 96.67% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | None | None |
| lite_debugging_b | None | None |
| lite_assembly_a | route: 4, next_step: 2 | 0, 40, 47, 48 |
| lite_assembly_b | route: 8, next_step: 1 | 7, 32, 33, 38, 42, 43, 48, 49 |
| lite_support_a | None | None |
| lite_support_b | route: 2, repair_target: 2, repair_action: 2 | 50, 53 |
| lite_presenter_a | slide: 1 | 14 |
| lite_presenter_b | question_card: 1, mode: 1, slide: 1 | 35, 42, 56 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../../PROTOCOL.md)
- [Debugging rules](../../../../debugging.md), [assembly rules](../../../../assembly.md), [support rules](../../../../support.md), [presenter rules](../../../../presenter.md)
- [Frozen run](../../../../../../runs/hosted-api-repeats-20261003/pass2/gpt-5.6-terra-low/run.json)
- [Frozen episodes](../../../../../../runs/hosted-api-repeats-20261003/pass2/gpt-5.6-terra-low/episodes.json)
- [Release and response events](../../../../../../runs/hosted-api-repeats-20261003/pass2/gpt-5.6-terra-low/events.jsonl)
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
  "output_tokens": 57215,
  "reasoning_tokens": 34881
}
```
