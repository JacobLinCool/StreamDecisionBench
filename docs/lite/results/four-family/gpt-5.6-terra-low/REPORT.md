# SDB log-AUC: Terra low

Primary normalized log-AUC over 0.5–8 s: **48.04%**; untimed accuracy: 95.42%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 44.63 |
| procedural_coaching | 46.61 |
| support_call_assist | 50.32 |
| presenter_voice_control | 50.59 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000395 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: gpt-5.6-terra low

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: gpt-5.6-terra, reasoning effort low. All model scores use recorded responses.

**Untimed decision accuracy: 95.42%; In-force accuracy (transport retries excluded): 50.37%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 60.90% (range 59.05%–62.27%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 99.17% | 48.18% | 42.35% | 99.17% |
| Assembly | 92.50% | 47.97% | 37.80% | 92.50% |
| Support | 93.33% | 54.92% | 47.39% | 93.33% |
| Presenter voice control | 96.67% | 50.39% | 39.11% | 96.67% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Fitted-remainder removal (secondary)

Approximate send-to-receipt latency by a token-independent intercept plus slopes for uncached input tokens and, for text-generating models, output tokens. This secondary replay removes the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Fitted remainder 0.673 s (range 0.558–0.754 s); prefill 0.0 ms/1k tokens; decode 12.10 ms/token; fastest response 1.168 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Remainder removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 50.37% | 60.90% | 59.05%–62.27% | 95.42% |
| IDE debugging | 48.18% | 59.37% | 57.43%–60.76% | 99.17% |
| Assembly | 47.97% | 58.53% | 56.72%–59.91% | 92.50% |
| Support | 54.92% | 65.96% | 64.09%–67.35% | 93.33% |
| Presenter voice control | 50.39% | 59.73% | 57.97%–61.06% | 96.67% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include network delay, fixed server time and model misspecification; it does not identify network delay or guarantee an upper bound on its effect. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 100.00% | 48.11% | 2.50 / 3.95 | 0 |
| lite_debugging_b | 21 | 98.33% | 48.25% | 2.52 / 4.45 | 0 |
| lite_assembly_a | 21 | 95.00% | 50.89% | 2.54 / 3.41 | 0 |
| lite_assembly_b | 23 | 90.00% | 45.05% | 2.83 / 3.91 | 0 |
| lite_support_a | 22 | 95.00% | 54.32% | 2.26 / 2.97 | 0 |
| lite_support_b | 24 | 91.67% | 55.53% | 2.04 / 2.89 | 0 |
| lite_presenter_a | 24 | 96.67% | 52.80% | 2.41 / 3.24 | 0 |
| lite_presenter_b | 22 | 96.67% | 47.98% | 2.91 / 3.61 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 2.439 s, p95 3.774 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0101 s; maximum dispatch lag 0.0000 s.
- 0 states have only inactive-field errors, leaving the application decision correct.
- 464 updates accepted on the reconstructed timeline; rejected responses: {"older_than_active": 8, "after_horizon": 8}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 20 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 18.95 s; correct for its source but wrong for current evidence 416.52 s; wrong for both source and current evidence 41.02 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.260 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 50.36% | 41.65% |
| IDE debugging | 48.17% | 42.34% |
| Assembly | 47.96% | 37.79% |
| Support | 54.91% | 47.38% |
| Presenter voice control | 50.38% | 39.10% |

Raw logical request duration, including failed attempts and retry waits: p50 2.439 s, p95 3.774 s; 464 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | gpt-5.6-terra low decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 99.17% |
| Assembly | 0.00% | 0.00% | 92.50% |
| Support | 1.67% | 0.00% | 93.33% |
| Presenter voice control | 0.00% | 0.00% | 96.67% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | None | None |
| lite_debugging_b | rerun_scope: 1 | 27 |
| lite_assembly_a | route: 3, next_step: 1 | 31, 47, 48 |
| lite_assembly_b | route: 6 | 32, 33, 42, 43, 48, 49 |
| lite_support_a | recorder: 3 | 17, 42, 50 |
| lite_support_b | route: 5, repair_target: 5, repair_action: 5 | 50, 52, 54, 55, 57 |
| lite_presenter_a | slide: 1, clip_state: 1 | 4, 26 |
| lite_presenter_b | question_card: 1, slide: 1 | 31, 53 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/lite-v1-gpt-5.6-terra-low-four-family-retry-v1/run.json)
- [Frozen episodes](../../../../../runs/lite-v1-gpt-5.6-terra-low-four-family-retry-v1/episodes.json)
- [Release and response events](../../../../../runs/lite-v1-gpt-5.6-terra-low-four-family-retry-v1/events.jsonl)
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
  "output_tokens": 58236,
  "reasoning_tokens": 35884
}
```
