# SDB log-AUC: Jev — pass 3

Primary normalized log-AUC over 0.5–8 s: **58.45%**; untimed accuracy: 62.29%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 36.54 |
| procedural_coaching | 60.45 |
| support_call_assist | 70.17 |
| presenter_voice_control | 66.65 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000204 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: jev-latest

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: jev-latest. All model scores use recorded responses.

**Untimed decision accuracy: 62.29%; In-force accuracy (transport retries excluded): 59.45%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 61.36% (range 61.32%–61.41%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 38.33% | 37.01% | 35.56% | 33.33% |
| Assembly | 64.17% | 61.42% | 57.23% | 35.00% |
| Support | 75.00% | 71.43% | 68.95% | 31.67% |
| Presenter voice control | 71.67% | 67.96% | 64.17% | 33.33% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Fitted-remainder removal (secondary)

Approximate send-to-receipt latency by a token-independent intercept plus slopes for uncached input tokens and, for text-generating models, output tokens. This secondary replay removes the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Fitted remainder 0.176 s (range 0.172–0.181 s); prefill 7.5 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.180 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Remainder removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 59.45% | 61.36% | 61.32%–61.41% | 62.29% |
| IDE debugging | 37.01% | 37.82% | 37.80%–37.84% | 38.33% |
| Assembly | 61.42% | 63.47% | 63.43%–63.53% | 64.17% |
| Support | 71.43% | 73.85% | 73.79%–73.91% | 75.00% |
| Presenter voice control | 67.96% | 70.30% | 70.25%–70.37% | 71.67% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include network delay, fixed server time and model misspecification; it does not identify network delay or guarantee an upper bound on its effect. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 41.67% | 39.73% | 0.22 / 0.33 | 0 |
| lite_debugging_b | 21 | 35.00% | 34.29% | 0.22 / 0.33 | 0 |
| lite_assembly_a | 21 | 66.67% | 64.06% | 0.23 / 0.46 | 0 |
| lite_assembly_b | 23 | 61.67% | 58.78% | 0.24 / 0.37 | 0 |
| lite_support_a | 22 | 70.00% | 66.40% | 0.21 / 0.39 | 0 |
| lite_support_b | 24 | 80.00% | 76.45% | 0.22 / 0.31 | 0 |
| lite_presenter_a | 24 | 68.33% | 64.43% | 0.23 / 0.31 | 0 |
| lite_presenter_b | 22 | 75.00% | 71.48% | 0.22 / 0.35 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 0.224 s, p95 0.371 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0102 s; maximum dispatch lag 0.0000 s.
- 139 states have only inactive-field errors, leaving the application decision correct.
- 480 updates accepted on the reconstructed timeline; rejected responses: {}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 20 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 3.09 s; correct for its source but wrong for current evidence 25.97 s; wrong for both source and current evidence 360.19 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.242 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 59.45% | 56.47% |
| IDE debugging | 37.01% | 35.55% |
| Assembly | 61.41% | 57.22% |
| Support | 71.42% | 68.94% |
| Presenter voice control | 67.95% | 64.16% |

Raw logical request duration, including failed attempts and retry waits: p50 0.224 s, p95 0.371 s; 480 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | jev-latest decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 38.33% |
| Assembly | 0.00% | 0.00% | 64.17% |
| Support | 1.67% | 0.00% | 75.00% |
| Presenter voice control | 0.00% | 0.00% | 71.67% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 30, process: 16, rerun_scope: 10, inspect_file: 2, owner: 2 | 5, 6, 7, 8, 9, 10, 14, 15, 17, 18, 19, 25 |
| lite_debugging_b | route: 32, target_result: 8, rerun_scope: 5, process: 5, owner: 3, control_action: 2 | 0, 2, 3, 4, 5, 6, 9, 10, 11, 12, 16, 17 |
| lite_assembly_a | route: 14, next_step: 6, stage: 5, destination: 1 | 8, 9, 16, 17, 18, 21, 23, 24, 25, 31, 32, 35 |
| lite_assembly_b | route: 17, next_step: 7, destination: 2, target: 2, method: 2, stage: 2 | 4, 5, 6, 7, 10, 11, 16, 28, 32, 33, 36, 38 |
| lite_support_a | recorder: 10, payment_stage: 8, hold_action: 3 | 0, 1, 20, 22, 25, 30, 31, 32, 44, 45, 46, 47 |
| lite_support_b | route: 5, repair_action: 4, repair_target: 2, delivery_action: 1 | 4, 5, 10, 20, 26, 27, 46, 47, 49, 50, 56, 57 |
| lite_presenter_a | slide: 19, host_cue: 3 | 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52 |
| lite_presenter_b | mode: 8, slide: 7, question_card: 1, host_cue: 1 | 5, 6, 7, 31, 36, 37, 38, 39, 40, 41, 42, 43 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../../PROTOCOL.md)
- [Debugging rules](../../../../debugging.md), [assembly rules](../../../../assembly.md), [support rules](../../../../support.md), [presenter rules](../../../../presenter.md)
- [Frozen run](../../../../../../runs/hosted-api-repeats-20261003/pass3/jev-latest/run.json)
- [Frozen episodes](../../../../../../runs/hosted-api-repeats-20261003/pass3/jev-latest/episodes.json)
- [Release and response events](../../../../../../runs/hosted-api-repeats-20261003/pass3/jev-latest/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 1754113,
  "cached_tokens": 0,
  "output_tokens": 194520,
  "reasoning_tokens": 0
}
```
