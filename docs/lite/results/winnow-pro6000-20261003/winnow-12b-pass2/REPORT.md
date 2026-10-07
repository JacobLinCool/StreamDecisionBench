# SDB log-AUC: Winnow-12B

Primary normalized log-AUC over 0.5–8 s: **43.14%**; untimed accuracy: 46.46%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 12.49 |
| procedural_coaching | 33.63 |
| support_call_assist | 77.80 |
| presenter_voice_control | 48.64 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000330 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: EldanRing/Winnow-12B

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: EldanRing/Winnow-12B. All model scores use recorded responses.

**Untimed decision accuracy: 46.46%; In-force accuracy (transport retries excluded): 44.00%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 44.33% (range 44.28%–44.41%).

[Recorded error witnesses](FINDINGS.md) compare specific mistakes with the public rules.

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 12.50% | 12.49% | 12.17% | 5.00% |
| Assembly | 36.67% | 34.42% | 35.10% | 0.83% |
| Support | 83.33% | 79.24% | 75.58% | 50.00% |
| Presenter voice control | 53.33% | 49.86% | 46.17% | 27.50% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Fitted-remainder removal (secondary)

Approximate send-to-receipt latency by a token-independent intercept plus slopes for uncached input tokens and, for text-generating models, output tokens. This secondary replay removes the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Fitted remainder 0.042 s (range 0.036–0.053 s); prefill 99.6 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.215 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Remainder removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 44.00% | 44.33% | 44.28%–44.41% | 46.46% |
| IDE debugging | 12.49% | 12.49% | 12.49%–12.49% | 12.50% |
| Assembly | 34.42% | 34.70% | 34.66%–34.77% | 36.67% |
| Support | 79.24% | 79.89% | 79.80%–80.05% | 83.33% |
| Presenter voice control | 49.86% | 50.23% | 50.18%–50.33% | 53.33% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include network delay, fixed server time and model misspecification; it does not identify network delay or guarantee an upper bound on its effect. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 11.67% | 11.68% | 0.32 / 0.39 | 0 |
| lite_debugging_b | 21 | 13.33% | 13.30% | 0.30 / 0.37 | 0 |
| lite_assembly_a | 21 | 33.33% | 31.31% | 0.37 / 0.50 | 0 |
| lite_assembly_b | 23 | 40.00% | 37.53% | 0.38 / 0.51 | 0 |
| lite_support_a | 22 | 76.67% | 73.42% | 0.27 / 0.29 | 0 |
| lite_support_b | 24 | 90.00% | 85.06% | 0.27 / 0.29 | 0 |
| lite_presenter_a | 24 | 65.00% | 60.82% | 0.40 / 0.45 | 0 |
| lite_presenter_b | 22 | 41.67% | 38.90% | 0.40 / 0.45 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 0.332 s, p95 0.455 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0005 s; maximum dispatch lag 0.0000 s.
- 123 states have only inactive-field errors, leaving the application decision correct.
- 480 updates accepted on the reconstructed timeline; rejected responses: {}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 90 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 2.24 s; correct for its source but wrong for current evidence 24.97 s; wrong for both source and current evidence 510.36 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.270 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 3 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 44.00% | 42.25% |
| IDE debugging | 12.49% | 12.17% |
| Assembly | 34.42% | 35.09% |
| Support | 79.23% | 75.57% |
| Presenter voice control | 49.86% | 46.16% |

Raw logical request duration, including failed attempts and retry waits: p50 0.332 s, p95 0.455 s; 480 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | EldanRing/Winnow-12B decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 12.50% |
| Assembly | 0.00% | 0.00% | 36.67% |
| Support | 1.67% | 0.00% | 83.33% |
| Presenter voice control | 0.00% | 0.00% | 53.33% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 47, target_result: 11, rerun_scope: 10, inspect_file: 4, process: 3, owner: 3 | 0, 1, 2, 3, 4, 7, 8, 9, 10, 11, 12, 13 |
| lite_debugging_b | route: 51, rerun_scope: 6, process: 6, owner: 6, target_result: 4, inspect_file: 1 | 0, 2, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15 |
| lite_assembly_a | route: 30, stage: 8, destination: 7, next_step: 2, method: 2 | 1, 6, 7, 8, 9, 16, 17, 18, 23, 25, 26, 27 |
| lite_assembly_b | route: 32, destination: 7, target: 4, method: 4, next_step: 3, stage: 2 | 1, 4, 5, 6, 7, 8, 9, 10, 11, 22, 23, 28 |
| lite_support_a | payment_stage: 10, recorder: 6, instrument: 2, hold_action: 1 | 29, 38, 39, 45, 46, 47, 48, 49, 50, 51, 52, 53 |
| lite_support_b | route: 3, delivery_action: 3 | 4, 6, 7, 10, 46, 47 |
| lite_presenter_a | slide: 8, host_cue: 7, clip_state: 5, question_card: 3, mode: 1 | 7, 22, 28, 30, 31, 32, 33, 34, 35, 36, 37, 38 |
| lite_presenter_b | slide: 24, mode: 16, question_card: 7, clip_state: 1, host_cue: 1 | 5, 6, 7, 8, 12, 13, 14, 15, 17, 18, 19, 20 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/winnow-pro6000-20261003/pass2/winnow-12b/run.json)
- [Frozen episodes](../../../../../runs/winnow-pro6000-20261003/pass2/winnow-12b/episodes.json)
- [Release and response events](../../../../../runs/winnow-pro6000-20261003/pass2/winnow-12b/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 1372263,
  "cached_tokens": 0,
  "output_tokens": 0,
  "reasoning_tokens": 0
}
```
