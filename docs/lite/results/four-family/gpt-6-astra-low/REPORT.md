# SDB log-AUC: Astra low

Primary normalized log-AUC over 0.5–8 s: **45.15%**; untimed accuracy: 99.79%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 45.58 |
| procedural_coaching | 47.16 |
| support_call_assist | 39.20 |
| presenter_voice_control | 48.66 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000465 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: gpt-6-astra low

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: gpt-6-astra, reasoning effort low. All model scores use recorded responses.

**Untimed decision accuracy: 99.79%; In-force accuracy (transport retries excluded): 45.84%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 61.57% (range 56.17%–68.16%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 100.00% | 48.79% | 42.14% | 100.00% |
| Assembly | 99.17% | 47.16% | 37.27% | 99.17% |
| Support | 100.00% | 37.79% | 28.39% | 100.00% |
| Presenter voice control | 100.00% | 49.60% | 37.68% | 100.00% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Network-removed estimate (secondary)

Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + decode (proportional to output tokens, for text-generating models). The token-independent remainder is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Estimated network 0.939 s (range 0.631–1.302 s); prefill 0.0 ms/1k tokens; decode 28.31 ms/token; fastest response 1.744 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 45.84% | 61.57% | 56.17%–68.16% | 99.79% |
| IDE debugging | 48.79% | 64.96% | 59.46%–71.46% | 100.00% |
| Assembly | 47.16% | 64.29% | 58.51%–71.10% | 99.17% |
| Support | 37.79% | 52.32% | 47.36%–58.53% | 100.00% |
| Presenter voice control | 49.60% | 64.73% | 59.36%–71.54% | 100.00% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include fixed server time, so it bounds the network effect from above. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 100.00% | 48.82% | 2.54 / 4.18 | 0 |
| lite_debugging_b | 21 | 100.00% | 48.77% | 2.59 / 3.48 | 0 |
| lite_assembly_a | 21 | 98.33% | 49.48% | 2.49 / 3.88 | 0 |
| lite_assembly_b | 23 | 100.00% | 44.84% | 2.54 / 3.95 | 0 |
| lite_support_a | 22 | 100.00% | 37.04% | 3.38 / 6.34 | 0 |
| lite_support_b | 24 | 100.00% | 38.54% | 2.76 / 4.23 | 0 |
| lite_presenter_a | 24 | 100.00% | 46.71% | 2.70 / 3.98 | 0 |
| lite_presenter_b | 22 | 100.00% | 52.50% | 2.49 / 3.60 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 2.671 s, p95 4.447 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0092 s; maximum dispatch lag 0.0000 s.
- 0 states have only inactive-field errors, leaving the application decision correct.
- 466 updates accepted on the reconstructed timeline; rejected responses: {"older_than_active": 6, "after_horizon": 8}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 20 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 23.41 s; correct for its source but wrong for current evidence 494.98 s; wrong for both source and current evidence 1.56 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.225 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 45.83% | 36.36% |
| IDE debugging | 48.79% | 42.13% |
| Assembly | 47.15% | 37.26% |
| Support | 37.79% | 28.38% |
| Presenter voice control | 49.60% | 37.67% |

Raw logical request duration, including failed attempts and retry waits: p50 2.671 s, p95 4.447 s; 466 accepted raw-clock updates.

Exhausted retries or non-transport errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

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
| lite_assembly_a | route: 1, next_step: 1 | 32 |
| lite_assembly_b | None | None |
| lite_support_a | None | None |
| lite_support_b | None | None |
| lite_presenter_a | None | None |
| lite_presenter_b | None | None |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/lite-v1-gpt-6-astra-low-four-family-retry-v1/run.json)
- [Frozen episodes](../../../../../runs/lite-v1-gpt-6-astra-low-four-family-retry-v1/episodes.json)
- [Release and response events](../../../../../runs/lite-v1-gpt-6-astra-low-four-family-retry-v1/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py --run runs/lite-v1-gpt-6-astra-low-four-family-retry-v1 --out docs/lite/results/four-family/gpt-6-astra-low --label 'Astra low'
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 1476489,
  "cached_tokens": 0,
  "output_tokens": 22305,
  "reasoning_tokens": 773
}
```
