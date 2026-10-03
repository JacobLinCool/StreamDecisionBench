# SDB log-AUC: Terra none — pass 2

Primary normalized log-AUC over 0.5–8 s: **55.62%**; untimed accuracy: 81.88%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 50.13 |
| procedural_coaching | 50.81 |
| support_call_assist | 60.80 |
| presenter_voice_control | 60.72 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000365 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: gpt-5.6-terra none

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: gpt-5.6-terra, reasoning effort none. All model scores use recorded responses.

**Untimed decision accuracy: 81.88%; In-force accuracy (transport retries excluded): 61.45%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 70.72% (range 69.08%–73.95%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 72.50% | 55.68% | 49.18% | 72.50% |
| Assembly | 74.17% | 55.91% | 49.33% | 74.17% |
| Support | 94.17% | 68.12% | 61.67% | 94.17% |
| Presenter voice control | 86.67% | 66.09% | 61.57% | 86.67% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Network-removed estimate (secondary)

Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + decode (proportional to output tokens, for text-generating models). The token-independent remainder is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Estimated network 0.645 s (range 0.531–0.872 s); prefill 0.0 ms/1k tokens; decode 10.75 ms/token; fastest response 1.013 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 61.45% | 70.72% | 69.08%–73.95% | 81.88% |
| IDE debugging | 55.68% | 62.92% | 61.65%–65.37% | 72.50% |
| Assembly | 55.91% | 64.24% | 62.77%–67.17% | 74.17% |
| Support | 68.12% | 79.68% | 77.63%–83.73% | 94.17% |
| Presenter voice control | 66.09% | 76.03% | 74.28%–79.53% | 86.67% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include fixed server time, so it bounds the network effect from above. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 76.67% | 60.76% | 1.37 / 2.05 | 0 |
| lite_debugging_b | 21 | 68.33% | 50.61% | 1.30 / 1.84 | 0 |
| lite_assembly_a | 21 | 78.33% | 57.38% | 1.34 / 1.78 | 0 |
| lite_assembly_b | 23 | 70.00% | 54.45% | 1.23 / 1.67 | 0 |
| lite_support_a | 22 | 91.67% | 70.19% | 1.36 / 1.78 | 0 |
| lite_support_b | 24 | 96.67% | 66.06% | 1.36 / 1.62 | 0 |
| lite_presenter_a | 24 | 93.33% | 71.30% | 1.20 / 1.50 | 0 |
| lite_presenter_b | 22 | 80.00% | 60.88% | 1.24 / 1.59 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 1.306 s, p95 1.732 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0123 s; maximum dispatch lag 0.0000 s.
- 0 states have only inactive-field errors, leaving the application decision correct.
- 479 updates accepted on the reconstructed timeline; rejected responses: {"older_than_active": 1}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 20 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 13.06 s; correct for its source but wrong for current evidence 198.72 s; wrong for both source and current evidence 158.29 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.274 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 61.44% | 55.43% |
| IDE debugging | 55.68% | 49.17% |
| Assembly | 55.90% | 49.32% |
| Support | 68.12% | 61.66% |
| Presenter voice control | 66.08% | 61.56% |

Raw logical request duration, including failed attempts and retry waits: p50 1.306 s, p95 1.732 s; 479 accepted raw-clock updates.

Exhausted retries or non-transport errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | gpt-5.6-terra none decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 72.50% |
| Assembly | 0.00% | 0.00% | 74.17% |
| Support | 1.67% | 0.00% | 94.17% |
| Presenter voice control | 0.00% | 0.00% | 86.67% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 12, rerun_scope: 7, process: 3, owner: 1 | 6, 9, 10, 29, 30, 33, 38, 44, 46, 49, 50, 55 |
| lite_debugging_b | route: 16, rerun_scope: 6, owner: 3, control_action: 2, process: 2 | 7, 8, 11, 12, 18, 19, 22, 26, 27, 32, 36, 39 |
| lite_assembly_a | route: 11, next_step: 5, destination: 3, stage: 1 | 8, 16, 17, 18, 25, 31, 32, 39, 40, 47, 48, 50 |
| lite_assembly_b | route: 16, destination: 6, next_step: 2, stage: 2, target: 1, method: 1 | 6, 7, 10, 11, 16, 32, 33, 37, 39, 41, 42, 43 |
| lite_support_a | recorder: 5 | 20, 21, 45, 49, 50 |
| lite_support_b | route: 2, repair_target: 2, repair_action: 2 | 54, 56 |
| lite_presenter_a | slide: 2, clip_state: 2, mode: 1 | 5, 14, 26, 32 |
| lite_presenter_b | slide: 10, mode: 3, host_cue: 1, clip_state: 1, question_card: 1 | 5, 7, 19, 35, 36, 52, 53, 54, 56, 57, 58, 59 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../../PROTOCOL.md)
- [Debugging rules](../../../../debugging.md), [assembly rules](../../../../assembly.md), [support rules](../../../../support.md), [presenter rules](../../../../presenter.md)
- [Frozen run](../../../../../../runs/hosted-api-repeats-20261003/pass2/gpt-5.6-terra-none/run.json)
- [Frozen episodes](../../../../../../runs/hosted-api-repeats-20261003/pass2/gpt-5.6-terra-none/episodes.json)
- [Release and response events](../../../../../../runs/hosted-api-repeats-20261003/pass2/gpt-5.6-terra-none/events.jsonl)
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
