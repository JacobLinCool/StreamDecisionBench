# SDB log-AUC: Kev-9B

Primary normalized log-AUC over 0.5–8 s: **29.27%**; untimed accuracy: 30.42%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 17.04 |
| procedural_coaching | 28.83 |
| support_call_assist | 40.21 |
| presenter_voice_control | 31.00 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000243 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: jaredpalmer/kev-9b

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: jaredpalmer/kev-9b. All model scores use recorded responses.

**Untimed decision accuracy: 30.42%; In-force accuracy (transport retries excluded): 29.56%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 30.02% (range 30.00%–30.06%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 18.33% | 17.34% | 16.35% | 3.33% |
| Assembly | 30.00% | 29.14% | 19.00% | 12.50% |
| Support | 41.67% | 40.59% | 36.30% | 20.83% |
| Presenter voice control | 31.67% | 31.17% | 25.95% | 6.67% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Fitted-remainder removal (secondary)

Approximate send-to-receipt latency by a token-independent intercept plus slopes for uncached input tokens and, for text-generating models, output tokens. This secondary replay removes the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Fitted remainder 0.143 s (range 0.135–0.153 s); prefill 30.9 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.200 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Remainder removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 29.56% | 30.02% | 30.00%–30.06% | 30.42% |
| IDE debugging | 17.34% | 17.76% | 17.74%–17.79% | 18.33% |
| Assembly | 29.14% | 29.55% | 29.53%–29.58% | 30.00% |
| Support | 40.59% | 41.30% | 41.26%–41.36% | 41.67% |
| Presenter voice control | 31.17% | 31.47% | 31.46%–31.49% | 31.67% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include network delay, fixed server time and model misspecification; it does not identify network delay or guarantee an upper bound on its effect. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 6.67% | 5.78% | 0.22 / 0.33 | 0 |
| lite_debugging_b | 21 | 30.00% | 28.91% | 0.22 / 0.33 | 0 |
| lite_assembly_a | 21 | 38.33% | 37.62% | 0.24 / 0.38 | 0 |
| lite_assembly_b | 23 | 21.67% | 20.65% | 0.24 / 0.38 | 0 |
| lite_support_a | 22 | 41.67% | 40.58% | 0.22 / 0.22 | 0 |
| lite_support_b | 24 | 41.67% | 40.59% | 0.21 / 0.22 | 0 |
| lite_presenter_a | 24 | 33.33% | 33.14% | 0.33 / 0.35 | 0 |
| lite_presenter_b | 22 | 30.00% | 29.21% | 0.29 / 0.35 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 0.229 s, p95 0.368 s; includes same-host native calls, queueing and inference.
- Maximum recorded release lag 0.0002 s; maximum dispatch lag 0.0000 s.
- 94 states have only inactive-field errors, leaving the application decision correct.
- 480 updates accepted on the reconstructed timeline; rejected responses: {}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. Native calls have no network timeout. The setting's process timeout is 3600 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 2.65 s; correct for its source but wrong for current evidence 10.16 s; wrong for both source and current evidence 663.42 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.477 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 3 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 29.56% | 24.40% |
| IDE debugging | 17.34% | 16.34% |
| Assembly | 29.13% | 18.99% |
| Support | 40.58% | 36.30% |
| Presenter voice control | 31.17% | 25.95% |

Raw logical request duration, including failed attempts and retry waits: p50 0.229 s, p95 0.368 s; 480 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | jaredpalmer/kev-9b decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 18.33% |
| Assembly | 0.00% | 0.00% | 30.00% |
| Support | 1.67% | 0.00% | 41.67% |
| Presenter voice control | 0.00% | 0.00% | 31.67% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 44, process: 42, rerun_scope: 9, owner: 3, inspect_file: 2 | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 |
| lite_debugging_b | process: 35, route: 30, rerun_scope: 8, control_action: 4, owner: 4 | 7, 8, 11, 12, 18, 19, 20, 21, 22, 23, 24, 25 |
| lite_assembly_a | route: 25, next_step: 12, target: 8, method: 7, destination: 7, stage: 5 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_assembly_b | route: 30, stage: 9, destination: 8, next_step: 7, target: 7, method: 5 | 0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13 |
| lite_support_a | payment_stage: 14, recorder: 14, service_action: 6, hold_action: 4, service_target: 2, instrument: 2, route: 2 | 0, 1, 4, 5, 6, 7, 22, 23, 24, 25, 26, 27 |
| lite_support_b | repair_action: 21, route: 8, delivery_action: 8, repair_target: 2 | 10, 11, 18, 19, 20, 21, 22, 23, 26, 27, 28, 29 |
| lite_presenter_a | captions: 24, slide: 5, mode: 5, host_cue: 4, question_card: 4, clip_state: 1 | 0, 1, 6, 7, 8, 13, 14, 15, 16, 22, 23, 24 |
| lite_presenter_b | slide: 31, mode: 16, captions: 15, question_card: 3, host_cue: 1 | 0, 4, 5, 6, 7, 8, 20, 22, 23, 24, 25, 26 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/pro6000-lab-20261001/runs/kev-9b/run.json)
- [Frozen episodes](../../../../../runs/pro6000-lab-20261001/runs/kev-9b/episodes.json)
- [Release and response events](../../../../../runs/pro6000-lab-20261001/runs/kev-9b/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 1290219,
  "cached_tokens": 0,
  "output_tokens": 303412,
  "reasoning_tokens": 0
}
```
