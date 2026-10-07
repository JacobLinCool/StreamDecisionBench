# SDB log-AUC: Winnow-E4B

Primary normalized log-AUC over 0.5–8 s: **18.97%**; untimed accuracy: 19.79%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 11.18 |
| procedural_coaching | 16.22 |
| support_call_assist | 11.36 |
| presenter_voice_control | 37.13 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000170 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: EldanRing/Winnow-E4B

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: EldanRing/Winnow-E4B. All model scores use recorded responses.

**Untimed decision accuracy: 19.79%; In-force accuracy (transport retries excluded): 19.19%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 19.24% (range 19.21%–19.25%).

[Recorded error witnesses](FINDINGS.md) compare specific mistakes with the public rules.

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 11.67% | 11.31% | 12.46% | 10.83% |
| Assembly | 16.67% | 16.34% | 17.56% | 0.00% |
| Support | 11.67% | 11.44% | 9.20% | 0.00% |
| Presenter voice control | 39.17% | 37.66% | 38.41% | 11.67% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Fitted-remainder removal (secondary)

Approximate send-to-receipt latency by a token-independent intercept plus slopes for uncached input tokens and, for text-generating models, output tokens. This secondary replay removes the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Fitted remainder 0.015 s (range 0.008–0.019 s); prefill 53.8 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.106 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Remainder removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 19.19% | 19.24% | 19.21%–19.25% | 19.79% |
| IDE debugging | 11.31% | 11.34% | 11.33%–11.35% | 11.67% |
| Assembly | 16.34% | 16.37% | 16.36%–16.38% | 16.67% |
| Support | 11.44% | 11.47% | 11.45%–11.47% | 11.67% |
| Presenter voice control | 37.66% | 37.77% | 37.72%–37.80% | 39.17% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include network delay, fixed server time and model misspecification; it does not identify network delay or guarantee an upper bound on its effect. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 15.00% | 14.59% | 0.16 / 0.19 | 0 |
| lite_debugging_b | 21 | 8.33% | 8.02% | 0.16 / 0.19 | 0 |
| lite_assembly_a | 21 | 28.33% | 27.82% | 0.19 / 0.26 | 0 |
| lite_assembly_b | 23 | 5.00% | 4.85% | 0.19 / 0.26 | 0 |
| lite_support_a | 22 | 18.33% | 18.00% | 0.13 / 0.14 | 0 |
| lite_support_b | 24 | 5.00% | 4.88% | 0.13 / 0.14 | 0 |
| lite_presenter_a | 24 | 41.67% | 39.83% | 0.20 / 0.23 | 0 |
| lite_presenter_b | 22 | 36.67% | 35.49% | 0.20 / 0.23 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 0.171 s, p95 0.235 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0003 s; maximum dispatch lag 0.0000 s.
- 68 states have only inactive-field errors, leaving the application decision correct.
- 480 updates accepted on the reconstructed timeline; rejected responses: {}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 90 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 1.22 s; correct for its source but wrong for current evidence 5.87 s; wrong for both source and current evidence 768.72 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.285 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 3 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 19.18% | 19.41% |
| IDE debugging | 11.31% | 12.46% |
| Assembly | 16.34% | 17.56% |
| Support | 11.44% | 9.19% |
| Presenter voice control | 37.65% | 38.41% |

Raw logical request duration, including failed attempts and retry waits: p50 0.171 s, p95 0.235 s; 480 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | EldanRing/Winnow-E4B decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 11.67% |
| Assembly | 0.00% | 0.00% | 16.67% |
| Support | 1.67% | 0.00% | 11.67% |
| Presenter voice control | 0.00% | 0.00% | 39.17% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 51, rerun_scope: 10, owner: 3, process: 2, target_result: 1 | 0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12 |
| lite_debugging_b | route: 55, rerun_scope: 8, owner: 6, control_action: 4, process: 4, target_result: 3 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_assembly_a | route: 27, stage: 16, destination: 14, target: 11, method: 8, next_step: 6 | 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18 |
| lite_assembly_b | route: 28, destination: 19, target: 15, method: 12, next_step: 11, stage: 11 | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 |
| lite_support_a | recorder: 47, payment_stage: 13, hold_action: 4, service_action: 3, instrument: 2 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_support_b | route: 51, contact_channel: 18, repair_action: 9, delivery_action: 3, repair_target: 2 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_presenter_a | slide: 16, mode: 14, question_card: 7, host_cue: 5, clip_state: 4, captions: 3 | 4, 5, 6, 7, 8, 15, 16, 24, 25, 30, 32, 33 |
| lite_presenter_b | slide: 26, mode: 12, question_card: 8, host_cue: 4, captions: 1 | 2, 4, 5, 6, 7, 8, 20, 21, 22, 26, 27, 30 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/winnow-pro6000-20261003/pass2/winnow-e4b/run.json)
- [Frozen episodes](../../../../../runs/winnow-pro6000-20261003/pass2/winnow-e4b/episodes.json)
- [Release and response events](../../../../../runs/winnow-pro6000-20261003/pass2/winnow-e4b/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 1359783,
  "cached_tokens": 0,
  "output_tokens": 0,
  "reasoning_tokens": 0
}
```
