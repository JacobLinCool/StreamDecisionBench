# SDB log-AUC: DJev / DiffusionGemma

Primary normalized log-AUC over 0.5–8 s: **21.19%**; untimed accuracy: 23.33%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 26.76 |
| procedural_coaching | 6.59 |
| support_call_assist | 26.14 |
| presenter_voice_control | 25.28 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000405 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: dgemma

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: dgemma. All model scores use recorded responses.

**Untimed decision accuracy: 23.33%; In-force accuracy (transport retries excluded): 21.75%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 23.09% (range 23.05%–23.13%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 29.17% | 27.39% | 23.34% | 17.50% |
| Assembly | 7.50% | 6.83% | 7.88% | 5.00% |
| Support | 29.17% | 26.93% | 26.32% | 11.67% |
| Presenter voice control | 27.50% | 25.85% | 20.36% | 16.67% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Network-removed estimate (secondary)

Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + decode (proportional to output tokens, for text-generating models). The token-independent remainder is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Estimated network 0.460 s (range 0.446–0.472 s); prefill 22.7 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.206 s; 3 requests clamped at receipt.

| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 21.75% | 23.09% | 23.05%–23.13% | 23.33% |
| IDE debugging | 27.39% | 28.92% | 28.88%–28.96% | 29.17% |
| Assembly | 6.83% | 7.41% | 7.39%–7.42% | 7.50% |
| Support | 26.93% | 28.85% | 28.79%–28.90% | 29.17% |
| Presenter voice control | 25.85% | 27.20% | 27.15%–27.23% | 27.50% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include fixed server time, so it bounds the network effect from above. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 15.00% | 14.09% | 0.54 / 4.10 | 0 |
| lite_debugging_b | 21 | 43.33% | 40.69% | 0.52 / 0.54 | 0 |
| lite_assembly_a | 21 | 6.67% | 6.73% | 0.55 / 0.65 | 0 |
| lite_assembly_b | 23 | 8.33% | 6.93% | 0.57 / 0.66 | 0 |
| lite_support_a | 22 | 13.33% | 12.87% | 0.52 / 0.54 | 0 |
| lite_support_b | 24 | 45.00% | 40.99% | 0.54 / 0.54 | 0 |
| lite_presenter_a | 24 | 31.67% | 30.26% | 0.57 / 0.58 | 0 |
| lite_presenter_b | 22 | 23.33% | 21.44% | 0.57 / 0.58 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 0.539 s, p95 0.646 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0002 s; maximum dispatch lag 0.0000 s.
- 51 states have only inactive-field errors, leaving the application decision correct.
- 480 updates accepted on the reconstructed timeline; rejected responses: {}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 90 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 12.87 s; correct for its source but wrong for current evidence 20.11 s; wrong for both source and current evidence 718.20 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.457 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 3 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 21.75% | 19.47% |
| IDE debugging | 27.39% | 23.34% |
| Assembly | 6.83% | 7.87% |
| Support | 26.93% | 26.32% |
| Presenter voice control | 25.85% | 20.35% |

Raw logical request duration, including failed attempts and retry waits: p50 0.539 s, p95 0.646 s; 480 accepted raw-clock updates.

Exhausted retries or non-transport errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | dgemma decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 29.17% |
| Assembly | 0.00% | 0.00% | 7.50% |
| Support | 1.67% | 0.00% | 29.17% |
| Presenter voice control | 0.00% | 0.00% | 27.50% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 49, rerun_scope: 9, target_result: 9, inspect_file: 4, owner: 3 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_debugging_b | route: 22, target_result: 10, process: 8, rerun_scope: 7, control_action: 4, owner: 4, inspect_file: 1 | 0, 7, 8, 11, 12, 18, 19, 20, 21, 22, 23, 26 |
| lite_assembly_a | route: 35, stage: 28, destination: 22, target: 11, next_step: 10, method: 8 | 0, 1, 3, 4, 7, 8, 9, 10, 11, 12, 13, 14 |
| lite_assembly_b | route: 39, stage: 33, next_step: 11, destination: 10, method: 7, target: 7 | 0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 |
| lite_support_a | recorder: 41, payment_stage: 16, service_target: 7, instrument: 5, hold_action: 4, service_action: 2, route: 2 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_support_b | route: 24, repair_target: 17, repair_action: 9, delivery_action: 1 | 0, 1, 2, 3, 5, 6, 7, 8, 9, 18, 19, 20 |
| lite_presenter_a | mode: 20, captions: 18, slide: 15, host_cue: 9, clip_state: 6, question_card: 6 | 0, 1, 4, 5, 6, 7, 8, 14, 17, 18, 19, 20 |
| lite_presenter_b | mode: 31, slide: 23, captions: 14, question_card: 12, clip_state: 6, host_cue: 2 | 0, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/pro6000-lab-20261001-pass3/runs/djev-diffusiongemma/run.json)
- [Frozen episodes](../../../../../runs/pro6000-lab-20261001-pass3/runs/djev-diffusiongemma/episodes.json)
- [Release and response events](../../../../../runs/pro6000-lab-20261001-pass3/runs/djev-diffusiongemma/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 1427008,
  "cached_tokens": 0,
  "output_tokens": 17820,
  "reasoning_tokens": 0
}
```
