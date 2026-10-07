# SDB log-AUC: Terra none

Primary normalized log-AUC over 0.5–8 s: **54.11%**; untimed accuracy: 82.08%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 48.84 |
| procedural_coaching | 49.91 |
| support_call_assist | 56.18 |
| presenter_voice_control | 61.48 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000490 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: gpt-5.6-terra none

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: gpt-5.6-terra, reasoning effort none. All model scores use recorded responses.

**Untimed decision accuracy: 82.08%; In-force accuracy (transport retries excluded): 59.85%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 77.40% (range 74.39%–77.55%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 72.50% | 55.58% | 50.77% | 72.50% |
| Assembly | 76.67% | 54.55% | 45.58% | 76.67% |
| Support | 91.67% | 62.12% | 54.55% | 91.67% |
| Presenter voice control | 87.50% | 67.14% | 61.78% | 87.50% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Fitted-remainder removal (secondary)

Approximate send-to-receipt latency by a token-independent intercept plus slopes for uncached input tokens and, for text-generating models, output tokens. This secondary replay removes the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Fitted remainder 1.264 s (range 1.050–1.275 s); prefill 0.0 ms/1k tokens; decode 0.00 ms/token; fastest response 1.109 s; 48 requests clamped at receipt.

| Scope | Recorded-cadence score | Remainder removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 59.85% | 77.40% | 74.39%–77.55% | 82.08% |
| IDE debugging | 55.58% | 67.71% | 65.63%–67.82% | 72.50% |
| Assembly | 54.55% | 72.26% | 69.31%–72.41% | 76.67% |
| Support | 62.12% | 84.51% | 80.60%–84.69% | 91.67% |
| Presenter voice control | 67.14% | 85.10% | 82.01%–85.26% | 87.50% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include network delay, fixed server time and model misspecification; it does not identify network delay or guarantee an upper bound on its effect. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 76.67% | 59.09% | 1.58 / 1.94 | 0 |
| lite_debugging_b | 21 | 68.33% | 52.06% | 1.51 / 2.16 | 0 |
| lite_assembly_a | 21 | 76.67% | 53.15% | 1.60 / 2.34 | 0 |
| lite_assembly_b | 23 | 76.67% | 55.96% | 1.50 / 2.17 | 0 |
| lite_support_a | 22 | 88.33% | 62.64% | 1.47 / 2.17 | 0 |
| lite_support_b | 24 | 95.00% | 61.61% | 1.48 / 2.02 | 0 |
| lite_presenter_a | 24 | 88.33% | 67.30% | 1.39 / 1.82 | 0 |
| lite_presenter_b | 22 | 86.67% | 66.97% | 1.43 / 1.89 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 1.493 s, p95 2.078 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0102 s; maximum dispatch lag 0.0000 s.
- 0 states have only inactive-field errors, leaving the application decision correct.
- 478 updates accepted on the reconstructed timeline; rejected responses: {"older_than_active": 2}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 20 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 14.48 s; correct for its source but wrong for current evidence 219.60 s; wrong for both source and current evidence 151.38 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.229 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 59.84% | 53.16% |
| IDE debugging | 55.57% | 50.76% |
| Assembly | 54.55% | 45.57% |
| Support | 62.11% | 54.54% |
| Presenter voice control | 67.13% | 61.77% |

Raw logical request duration, including failed attempts and retry waits: p50 1.493 s, p95 2.078 s; 478 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | gpt-5.6-terra none decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 72.50% |
| Assembly | 0.00% | 0.00% | 76.67% |
| Support | 1.67% | 0.00% | 91.67% |
| Presenter voice control | 0.00% | 0.00% | 87.50% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 11, rerun_scope: 7, process: 4 | 6, 9, 22, 29, 30, 33, 34, 38, 44, 46, 49, 54 |
| lite_debugging_b | route: 13, process: 5, rerun_scope: 4, owner: 3, control_action: 2, inspect_file: 1 | 0, 7, 8, 11, 16, 17, 19, 22, 26, 27, 30, 32 |
| lite_assembly_a | route: 10, next_step: 6, destination: 3, stage: 2 | 0, 8, 14, 16, 17, 18, 31, 32, 39, 40, 47, 48 |
| lite_assembly_b | route: 12, destination: 3, next_step: 2, target: 1, method: 1, stage: 1 | 6, 10, 16, 28, 32, 33, 37, 39, 41, 42, 43, 48 |
| lite_support_a | recorder: 7 | 17, 20, 21, 42, 45, 48, 49 |
| lite_support_b | route: 3, repair_target: 3, repair_action: 3 | 54, 56, 57 |
| lite_presenter_a | slide: 5, clip_state: 1, mode: 1 | 3, 5, 7, 8, 14, 26, 32 |
| lite_presenter_b | slide: 7, mode: 2, host_cue: 1, clip_state: 1 | 5, 7, 19, 35, 53, 54, 58, 59 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/lite-v1-gpt-5.6-terra-none-four-family-retry-v1/run.json)
- [Frozen episodes](../../../../../runs/lite-v1-gpt-5.6-terra-none-four-family-retry-v1/episodes.json)
- [Release and response events](../../../../../runs/lite-v1-gpt-5.6-terra-none-four-family-retry-v1/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py
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
