# SDB log-AUC: Kev-27B

Primary normalized log-AUC over 0.5–8 s: **62.17%**; untimed accuracy: 72.71%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 43.95 |
| procedural_coaching | 65.98 |
| support_call_assist | 72.09 |
| presenter_voice_control | 66.66 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000474 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: jaredpalmer/kev-27b

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: jaredpalmer/kev-27b. All model scores use recorded responses.

**Untimed decision accuracy: 72.71%; In-force accuracy (transport retries excluded): 64.80%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 65.61% (range 64.80%–66.91%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 49.17% | 45.29% | 46.37% | 30.00% |
| Assembly | 78.33% | 69.00% | 65.56% | 46.67% |
| Support | 80.83% | 74.37% | 68.68% | 41.67% |
| Presenter voice control | 82.50% | 70.55% | 66.79% | 54.17% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Network-removed estimate (secondary)

Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + decode (proportional to output tokens, for text-generating models). The token-independent remainder is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Estimated network 0.061 s (range 0.000–0.160 s); prefill 178.9 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.378 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 64.80% | 65.61% | 64.80%–66.91% | 72.71% |
| IDE debugging | 45.29% | 45.67% | 45.29%–46.29% | 49.17% |
| Assembly | 69.00% | 69.91% | 69.00%–71.39% | 78.33% |
| Support | 74.37% | 75.31% | 74.37%–76.83% | 80.83% |
| Presenter voice control | 70.55% | 71.54% | 70.55%–73.14% | 82.50% |

Unconstrained intercept 0.060875 s (range -0.026278–0.159680 s). Extrapolation to zero tokens can be negative; negative latency cannot be removed, so replay projects it to zero. analysis.json retains the unconstrained estimate. Scores and recordings are unchanged.

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include fixed server time, so it bounds the network effect from above. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 46.67% | 42.73% | 0.49 / 0.78 | 0 |
| lite_debugging_b | 21 | 51.67% | 47.85% | 0.49 / 0.74 | 0 |
| lite_assembly_a | 21 | 85.00% | 75.32% | 0.57 / 0.95 | 0 |
| lite_assembly_b | 23 | 71.67% | 62.67% | 0.63 / 0.97 | 0 |
| lite_support_a | 22 | 73.33% | 67.65% | 0.42 / 0.46 | 0 |
| lite_support_b | 24 | 88.33% | 81.10% | 0.41 / 0.44 | 0 |
| lite_presenter_a | 24 | 93.33% | 79.82% | 0.80 / 0.89 | 0 |
| lite_presenter_b | 22 | 71.67% | 61.28% | 0.74 / 0.91 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 0.525 s, p95 0.900 s; includes same-host native calls, queueing and inference.
- Maximum recorded release lag 0.0003 s; maximum dispatch lag 0.0000 s.
- 142 states have only inactive-field errors, leaving the application decision correct.
- 480 updates accepted on the reconstructed timeline; rejected responses: {}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. Native calls have no network timeout; the setting's process timeout is 3600 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 4.43 s; correct for its source but wrong for current evidence 77.58 s; wrong for both source and current evidence 255.89 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.475 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 3 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 64.79% | 61.83% |
| IDE debugging | 45.29% | 46.36% |
| Assembly | 68.98% | 65.54% |
| Support | 74.36% | 68.67% |
| Presenter voice control | 70.53% | 66.76% |

Raw logical request duration, including failed attempts and retry waits: p50 0.525 s, p95 0.900 s; 480 accepted raw-clock updates.

Exhausted retries or non-transport errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | jaredpalmer/kev-27b decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 49.17% |
| Assembly | 0.00% | 0.00% | 78.33% |
| Support | 1.67% | 0.00% | 80.83% |
| Presenter voice control | 0.00% | 0.00% | 82.50% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 30, rerun_scope: 4, inspect_file: 2, process: 1 | 3, 4, 6, 7, 8, 14, 15, 16, 17, 18, 19, 25 |
| lite_debugging_b | route: 25, process: 4, rerun_scope: 2, owner: 1 | 0, 5, 6, 9, 11, 12, 16, 17, 18, 20, 21, 22 |
| lite_assembly_a | route: 8, destination: 3, next_step: 2 | 16, 17, 18, 31, 32, 33, 34, 35, 40 |
| lite_assembly_b | route: 11, next_step: 4, destination: 3, target: 2, stage: 2 | 10, 11, 20, 22, 28, 38, 39, 40, 41, 42, 43, 46 |
| lite_support_a | recorder: 13, service_action: 2, hold_action: 1 | 12, 13, 20, 21, 33, 42, 43, 44, 45, 46, 47, 48 |
| lite_support_b | route: 3, delivery_action: 2, repair_action: 2 | 10, 11, 48, 54, 55, 56, 57 |
| lite_presenter_a | question_card: 3, slide: 1 | 7, 46, 47, 52 |
| lite_presenter_b | slide: 9, mode: 6, host_cue: 2 | 5, 6, 20, 36, 37, 38, 39, 40, 49, 51, 52, 53 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/pro6000-lab-20261001-pass2/runs/kev-27b/run.json)
- [Frozen episodes](../../../../../runs/pro6000-lab-20261001-pass2/runs/kev-27b/episodes.json)
- [Release and response events](../../../../../runs/pro6000-lab-20261001-pass2/runs/kev-27b/events.jsonl)
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
  "output_tokens": 302002,
  "reasoning_tokens": 0
}
```
