# SDB log-AUC: Astra low — pass 3

Primary normalized log-AUC over 0.5–8 s: **54.03%**; untimed accuracy: 99.79%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 55.45 |
| procedural_coaching | 52.53 |
| support_call_assist | 53.04 |
| presenter_voice_control | 55.09 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000351 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: gpt-6-astra low

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: gpt-6-astra, reasoning effort low. All model scores use recorded responses.

**Untimed decision accuracy: 99.79%; In-force accuracy (transport retries excluded): 58.56%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 75.49% (range 70.02%–85.85%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 100.00% | 61.66% | 55.29% | 100.00% |
| Assembly | 99.17% | 55.68% | 46.92% | 99.17% |
| Support | 100.00% | 58.43% | 50.33% | 100.00% |
| Presenter voice control | 100.00% | 58.46% | 47.61% | 100.00% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Fitted-remainder removal (secondary)

Approximate send-to-receipt latency by a token-independent intercept plus slopes for uncached input tokens and, for text-generating models, output tokens. This secondary replay removes the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Fitted remainder 0.894 s (range 0.609–1.435 s); prefill 34.3 ms/1k tokens; decode 16.77 ms/token; fastest response 1.450 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Remainder removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 58.56% | 75.49% | 70.02%–85.85% | 99.79% |
| IDE debugging | 61.66% | 77.50% | 72.38%–87.19% | 100.00% |
| Assembly | 55.68% | 72.74% | 67.27%–83.11% | 99.17% |
| Support | 58.43% | 75.88% | 70.17%–86.69% | 100.00% |
| Presenter voice control | 58.46% | 75.84% | 70.25%–86.43% | 100.00% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include network delay, fixed server time and model misspecification; it does not identify network delay or guarantee an upper bound on its effect. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 100.00% | 61.35% | 2.00 / 3.01 | 0 |
| lite_debugging_b | 21 | 100.00% | 61.97% | 2.05 / 2.56 | 0 |
| lite_assembly_a | 21 | 98.33% | 57.67% | 2.03 / 3.49 | 0 |
| lite_assembly_b | 23 | 100.00% | 53.68% | 2.13 / 3.07 | 0 |
| lite_support_a | 22 | 100.00% | 61.43% | 1.94 / 2.74 | 0 |
| lite_support_b | 24 | 100.00% | 55.43% | 2.03 / 2.49 | 0 |
| lite_presenter_a | 24 | 100.00% | 55.91% | 1.92 / 2.96 | 0 |
| lite_presenter_b | 22 | 100.00% | 61.01% | 2.00 / 2.44 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 2.012 s, p95 2.857 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0101 s; maximum dispatch lag 0.0000 s.
- 0 states have only inactive-field errors, leaving the application decision correct.
- 475 updates accepted on the reconstructed timeline; rejected responses: {"older_than_active": 3, "after_horizon": 2}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 20 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 19.04 s; correct for its source but wrong for current evidence 378.36 s; wrong for both source and current evidence 0.46 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.198 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 58.55% | 50.03% |
| IDE debugging | 61.65% | 55.29% |
| Assembly | 55.67% | 46.91% |
| Support | 58.42% | 50.32% |
| Presenter voice control | 58.45% | 47.60% |

Raw logical request duration, including failed attempts and retry waits: p50 2.012 s, p95 2.857 s; 475 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | gpt-6-astra low decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 100.00% |
| Assembly | 0.00% | 0.00% | 99.17% |
| Support | 1.67% | 0.00% | 100.00% |
| Presenter voice control | 0.00% | 0.00% | 100.00% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | None | None |
| lite_debugging_b | None | None |
| lite_assembly_a | route: 1, next_step: 1 | 50 |
| lite_assembly_b | None | None |
| lite_support_a | None | None |
| lite_support_b | None | None |
| lite_presenter_a | None | None |
| lite_presenter_b | None | None |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../../PROTOCOL.md)
- [Debugging rules](../../../../debugging.md), [assembly rules](../../../../assembly.md), [support rules](../../../../support.md), [presenter rules](../../../../presenter.md)
- [Frozen run](../../../../../../runs/hosted-api-repeats-20261003/pass3/gpt-6-astra-low/run.json)
- [Frozen episodes](../../../../../../runs/hosted-api-repeats-20261003/pass3/gpt-6-astra-low/episodes.json)
- [Release and response events](../../../../../../runs/hosted-api-repeats-20261003/pass3/gpt-6-astra-low/events.jsonl)
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
  "output_tokens": 22396,
  "reasoning_tokens": 860
}
```
