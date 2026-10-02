# SDB log-AUC: Luna low

Primary normalized log-AUC over 0.5–8 s: **45.26%**; untimed accuracy: 88.75%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 46.70 |
| procedural_coaching | 43.28 |
| support_call_assist | 45.72 |
| presenter_voice_control | 45.36 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000537 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: gpt-5.6-luna low

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: gpt-5.6-luna, reasoning effort low. All model scores use recorded responses.

**Untimed decision accuracy: 88.75%; In-force accuracy (transport retries excluded): 47.70%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 56.04% (range 52.08%–57.62%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 84.17% | 51.63% | 45.54% | 84.17% |
| Assembly | 87.50% | 44.00% | 33.83% | 85.83% |
| Support | 86.67% | 49.74% | 41.71% | 80.83% |
| Presenter voice control | 96.67% | 45.45% | 33.73% | 96.67% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Network-removed estimate (secondary)

Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + decode (proportional to output tokens, for text-generating models). The token-independent remainder is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Estimated network 0.585 s (range 0.310–0.694 s); prefill 59.5 ms/1k tokens; decode 8.34 ms/token; fastest response 1.432 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 47.70% | 56.04% | 52.08%–57.62% | 88.75% |
| IDE debugging | 51.63% | 59.27% | 55.53%–60.63% | 84.17% |
| Assembly | 44.00% | 52.42% | 48.32%–54.10% | 87.50% |
| Support | 49.74% | 58.80% | 54.66%–60.45% | 86.67% |
| Presenter voice control | 45.45% | 53.69% | 49.80%–55.30% | 96.67% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include fixed server time, so it bounds the network effect from above. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 83.33% | 52.31% | 2.18 / 3.55 | 0 |
| lite_debugging_b | 21 | 85.00% | 50.95% | 2.31 / 3.76 | 0 |
| lite_assembly_a | 21 | 91.67% | 50.55% | 2.44 / 3.59 | 0 |
| lite_assembly_b | 23 | 83.33% | 37.45% | 3.17 / 5.02 | 0 |
| lite_support_a | 22 | 81.67% | 48.67% | 1.91 / 2.86 | 0 |
| lite_support_b | 24 | 91.67% | 50.80% | 2.18 / 3.39 | 0 |
| lite_presenter_a | 24 | 100.00% | 47.18% | 2.73 / 3.76 | 0 |
| lite_presenter_b | 22 | 93.33% | 43.73% | 3.14 / 4.17 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 2.405 s, p95 4.099 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0053 s; maximum dispatch lag 0.0000 s.
- 9 states have only inactive-field errors, leaving the application decision correct.
- 464 updates accepted on the reconstructed timeline; rejected responses: {"older_than_active": 7, "after_horizon": 9}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 20 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 21.55 s; correct for its source but wrong for current evidence 386.34 s; wrong for both source and current evidence 94.15 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.219 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 47.70% | 38.70% |
| IDE debugging | 51.62% | 45.53% |
| Assembly | 43.99% | 33.83% |
| Support | 49.73% | 41.70% |
| Presenter voice control | 45.45% | 33.73% |

Raw logical request duration, including failed attempts and retry waits: p50 2.405 s, p95 4.099 s; 464 accepted raw-clock updates.

Exhausted retries or non-transport errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | gpt-5.6-luna low decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 84.17% |
| Assembly | 0.00% | 0.00% | 87.50% |
| Support | 1.67% | 0.00% | 86.67% |
| Presenter voice control | 0.00% | 0.00% | 96.67% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 10, rerun_scope: 3, inspect_file: 2 | 7, 8, 14, 18, 23, 26, 28, 29, 30, 58 |
| lite_debugging_b | route: 8, rerun_scope: 3, owner: 3, target_result: 1 | 25, 26, 28, 31, 32, 40, 44, 49, 50 |
| lite_assembly_a | route: 4, stage: 1, next_step: 1 | 14, 20, 31, 47, 48 |
| lite_assembly_b | route: 9, stage: 1, target: 1, method: 1, destination: 1 | 6, 7, 33, 40, 41, 42, 43, 48, 49, 51 |
| lite_support_a | recorder: 11 | 12, 13, 18, 20, 21, 43, 45, 46, 47, 48, 49 |
| lite_support_b | route: 5, repair_target: 2, repair_action: 2, delivery_target: 1, delivery_action: 1 | 5, 19, 40, 53, 55 |
| lite_presenter_a | None | None |
| lite_presenter_b | slide: 3, question_card: 1 | 41, 45, 47, 54 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/lite-v1-gpt-5.6-luna-low-four-family-retry-v1/run.json)
- [Frozen episodes](../../../../../runs/lite-v1-gpt-5.6-luna-low-four-family-retry-v1/episodes.json)
- [Release and response events](../../../../../runs/lite-v1-gpt-5.6-luna-low-four-family-retry-v1/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py --run runs/lite-v1-gpt-5.6-luna-low-four-family-retry-v1 --out docs/lite/results/four-family/gpt-5.6-luna-low --label 'Luna low'
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 1476489,
  "cached_tokens": 0,
  "output_tokens": 80072,
  "reasoning_tokens": 57632
}
```
