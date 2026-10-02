# SDB log-AUC: Kev-27B

Primary normalized log-AUC over 0.5–8 s: **61.97%**; untimed accuracy: 72.50%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 41.41 |
| procedural_coaching | 67.38 |
| support_call_assist | 71.69 |
| presenter_voice_control | 67.38 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000467 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: jaredpalmer/kev-27b

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: jaredpalmer/kev-27b. All model scores use recorded responses.

**Untimed decision accuracy: 72.50%; In-force accuracy (transport retries excluded): 64.58%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 65.97% (range 64.87%–67.02%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 46.67% | 42.65% | 43.28% | 30.83% |
| Assembly | 80.00% | 70.46% | 65.90% | 49.17% |
| Support | 80.83% | 74.07% | 68.36% | 42.50% |
| Presenter voice control | 82.50% | 71.13% | 66.69% | 52.50% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Network-removed estimate (secondary)

Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + decode (proportional to output tokens, for text-generating models). The token-independent remainder is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Estimated network 0.108 s (range 0.023–0.189 s); prefill 163.7 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.409 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 64.58% | 65.97% | 64.87%–67.02% | 72.50% |
| IDE debugging | 42.65% | 43.27% | 42.78%–43.75% | 46.67% |
| Assembly | 70.46% | 72.07% | 70.80%–73.30% | 80.00% |
| Support | 74.07% | 75.73% | 74.42%–76.99% | 80.83% |
| Presenter voice control | 71.13% | 72.79% | 71.48%–74.04% | 82.50% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include fixed server time, so it bounds the network effect from above. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 46.67% | 42.13% | 0.51 / 0.92 | 0 |
| lite_debugging_b | 21 | 46.67% | 43.17% | 0.50 / 0.77 | 0 |
| lite_assembly_a | 21 | 85.00% | 74.99% | 0.58 / 0.98 | 0 |
| lite_assembly_b | 23 | 75.00% | 65.93% | 0.63 / 1.00 | 0 |
| lite_support_a | 22 | 73.33% | 67.36% | 0.44 / 0.48 | 0 |
| lite_support_b | 24 | 88.33% | 80.79% | 0.43 / 0.46 | 0 |
| lite_presenter_a | 24 | 93.33% | 79.54% | 0.82 / 0.91 | 0 |
| lite_presenter_b | 22 | 71.67% | 62.71% | 0.75 / 0.91 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 0.538 s, p95 0.916 s; includes same-host native calls, queueing and inference.
- Maximum recorded release lag 0.0002 s; maximum dispatch lag 0.0000 s.
- 138 states have only inactive-field errors, leaving the application decision correct.
- 480 updates accepted on the reconstructed timeline; rejected responses: {}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. Native calls have no network timeout; the setting's process timeout is 3600 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 5.11 s; correct for its source but wrong for current evidence 78.11 s; wrong for both source and current evidence 256.85 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.475 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 3 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 64.56% | 61.04% |
| IDE debugging | 42.64% | 43.27% |
| Assembly | 70.45% | 65.88% |
| Support | 74.06% | 68.34% |
| Presenter voice control | 71.11% | 66.67% |

Raw logical request duration, including failed attempts and retry waits: p50 0.538 s, p95 0.916 s; 480 accepted raw-clock updates.

Exhausted retries or non-transport errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | jaredpalmer/kev-27b decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 46.67% |
| Assembly | 0.00% | 0.00% | 80.00% |
| Support | 1.67% | 0.00% | 80.83% |
| Presenter voice control | 0.00% | 0.00% | 82.50% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 30, rerun_scope: 4, inspect_file: 2, process: 1 | 3, 4, 6, 7, 8, 14, 15, 16, 17, 18, 19, 25 |
| lite_debugging_b | route: 26, rerun_scope: 4, process: 4, owner: 1 | 0, 5, 6, 9, 11, 12, 16, 17, 18, 20, 21, 22 |
| lite_assembly_a | route: 8, destination: 3, next_step: 2 | 16, 17, 18, 31, 32, 33, 34, 35, 40 |
| lite_assembly_b | route: 12, next_step: 4, destination: 2, target: 2, stage: 1 | 10, 11, 22, 28, 38, 39, 40, 41, 42, 43, 46, 47 |
| lite_support_a | recorder: 13, service_action: 2, hold_action: 1 | 12, 13, 20, 21, 33, 42, 43, 44, 45, 46, 47, 48 |
| lite_support_b | route: 3, delivery_action: 2, repair_action: 2 | 10, 11, 48, 54, 55, 56, 57 |
| lite_presenter_a | question_card: 3, slide: 1 | 7, 46, 47, 52 |
| lite_presenter_b | slide: 8, mode: 6, host_cue: 2, question_card: 1 | 5, 6, 20, 28, 32, 36, 37, 38, 39, 40, 51, 53 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/pro6000-lab-20261001/runs/kev-27b/run.json)
- [Frozen episodes](../../../../../runs/pro6000-lab-20261001/runs/kev-27b/episodes.json)
- [Release and response events](../../../../../runs/pro6000-lab-20261001/runs/kev-27b/events.jsonl)
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
  "output_tokens": 302003,
  "reasoning_tokens": 0
}
```
