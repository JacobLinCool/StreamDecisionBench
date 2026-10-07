# SDB log-AUC: Kev-4B

Primary normalized log-AUC over 0.5–8 s: **21.20%**; untimed accuracy: 22.08%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 17.77 |
| procedural_coaching | 12.76 |
| support_call_assist | 35.96 |
| presenter_voice_control | 18.29 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000239 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: jaredpalmer/kev-4b

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: jaredpalmer/kev-4b. All model scores use recorded responses.

**Untimed decision accuracy: 22.08%; In-force accuracy (transport retries excluded): 21.43%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 21.87% (range 21.82%–21.91%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 19.17% | 18.13% | 20.42% | 2.50% |
| Assembly | 13.33% | 12.91% | 8.06% | 10.83% |
| Support | 37.50% | 36.36% | 31.80% | 18.33% |
| Presenter voice control | 18.33% | 18.30% | 14.81% | 0.00% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Fitted-remainder removal (secondary)

Approximate send-to-receipt latency by a token-independent intercept plus slopes for uncached input tokens and, for text-generating models, output tokens. This secondary replay removes the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Fitted remainder 0.176 s (range 0.158–0.193 s); prefill 18.1 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.209 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Remainder removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 21.43% | 21.87% | 21.82%–21.91% | 22.08% |
| IDE debugging | 18.13% | 18.72% | 18.66%–18.78% | 19.17% |
| Assembly | 12.91% | 13.20% | 13.17%–13.23% | 13.33% |
| Support | 36.36% | 37.24% | 37.15%–37.33% | 37.50% |
| Presenter voice control | 18.30% | 18.30% | 18.30%–18.30% | 18.33% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include network delay, fixed server time and model misspecification; it does not identify network delay or guarantee an upper bound on its effect. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 26.67% | 25.15% | 0.23 / 0.33 | 0 |
| lite_debugging_b | 21 | 11.67% | 11.12% | 0.23 / 0.33 | 0 |
| lite_assembly_a | 21 | 25.00% | 24.35% | 0.23 / 0.34 | 0 |
| lite_assembly_b | 23 | 1.67% | 1.47% | 0.24 / 0.34 | 0 |
| lite_support_a | 22 | 31.67% | 30.71% | 0.22 / 0.23 | 0 |
| lite_support_b | 24 | 43.33% | 42.02% | 0.22 / 0.23 | 0 |
| lite_presenter_a | 24 | 16.67% | 17.35% | 0.32 / 0.34 | 0 |
| lite_presenter_b | 22 | 20.00% | 19.25% | 0.28 / 0.34 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 0.231 s, p95 0.337 s; includes same-host native calls, queueing and inference.
- Maximum recorded release lag 0.0002 s; maximum dispatch lag 0.0000 s.
- 68 states have only inactive-field errors, leaving the application decision correct.
- 480 updates accepted on the reconstructed timeline; rejected responses: {}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. Native calls have no network timeout. The setting's process timeout is 3600 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 2.12 s; correct for its source but wrong for current evidence 8.15 s; wrong for both source and current evidence 744.03 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.462 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 3 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 21.42% | 18.77% |
| IDE debugging | 18.13% | 20.41% |
| Assembly | 12.91% | 8.06% |
| Support | 36.36% | 31.79% |
| Presenter voice control | 18.30% | 14.81% |

Raw logical request duration, including failed attempts and retry waits: p50 0.231 s, p95 0.337 s; 480 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | jaredpalmer/kev-4b decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 19.17% |
| Assembly | 0.00% | 0.00% | 13.33% |
| Support | 1.67% | 0.00% | 37.50% |
| Presenter voice control | 0.00% | 0.00% | 18.33% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | process: 32, route: 23, target_result: 23, rerun_scope: 4, inspect_file: 2, owner: 1 | 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14 |
| lite_debugging_b | route: 39, process: 31, target_result: 9, rerun_scope: 7, owner: 5, control_action: 2 | 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14, 15 |
| lite_assembly_a | route: 33, destination: 14, stage: 12, next_step: 11, target: 11, method: 10 | 0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12 |
| lite_assembly_b | route: 35, destination: 24, target: 18, next_step: 12, method: 10, stage: 8 | 0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12 |
| lite_support_a | payment_stage: 15, recorder: 12, service_action: 11, route: 7, instrument: 4, service_target: 3, hold_action: 3 | 0, 1, 16, 17, 19, 20, 21, 22, 23, 24, 25, 26 |
| lite_support_b | delivery_action: 12, repair_action: 12, route: 8, cancellation_action: 2, repair_target: 2 | 4, 5, 6, 7, 8, 9, 10, 11, 16, 17, 18, 19 |
| lite_presenter_a | captions: 34, mode: 15, host_cue: 13, slide: 9, question_card: 8, clip_state: 2 | 0, 2, 3, 4, 5, 6, 7, 8, 16, 17, 18, 21 |
| lite_presenter_b | slide: 26, captions: 23, mode: 19, question_card: 9, host_cue: 1 | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/pro6000-lab-20261001/runs/kev-4b/run.json)
- [Frozen episodes](../../../../../runs/pro6000-lab-20261001/runs/kev-4b/episodes.json)
- [Release and response events](../../../../../runs/pro6000-lab-20261001/runs/kev-4b/events.jsonl)
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
  "output_tokens": 303398,
  "reasoning_tokens": 0
}
```
