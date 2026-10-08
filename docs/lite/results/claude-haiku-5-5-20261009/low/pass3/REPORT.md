# SDB log-AUC: Claude Haiku 5.5 low — pass 3

Primary normalized log-AUC over 0.5–8 s: **36.67%**; untimed accuracy: 95.00%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 37.57 |
| procedural_coaching | 31.40 |
| support_call_assist | 40.38 |
| presenter_voice_control | 37.32 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000965 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: claude-haiku-5-5 low

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. HTTP 429 and 5xx honor Retry-After through a shared cooldown within the attempt budget. Requested model: claude-haiku-5-5, reasoning effort low, thinking adaptive. All model scores use recorded responses.

**Untimed decision accuracy: 95.00%; In-force accuracy (failed attempts and retry waits excluded): 33.24%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 65.69% (range 63.27%–68.52%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 99.17% | 34.68% | 28.01% | 99.17% |
| Assembly | 85.83% | 27.34% | 18.11% | 85.83% |
| Support | 96.67% | 38.71% | 28.40% | 90.00% |
| Presenter voice control | 98.33% | 32.24% | 20.91% | 98.33% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Fitted-remainder removal (secondary)

Approximate send-to-receipt latency by a token-independent intercept plus slopes for uncached input tokens and, for text-generating models, output tokens. This secondary replay removes the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Fitted remainder 2.283 s (range 2.128–2.465 s); prefill 439.7 ms/1k tokens; no decode term (the model does not generate text); fastest response 1.437 s; 19 requests clamped at receipt.

| Scope | Recorded-cadence score | Remainder removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 33.24% | 65.69% | 63.27%–68.52% | 95.00% |
| IDE debugging | 34.68% | 72.23% | 69.52%–75.41% | 99.17% |
| Assembly | 27.34% | 51.84% | 49.79%–54.25% | 85.83% |
| Support | 38.71% | 78.08% | 75.55%–80.90% | 96.67% |
| Presenter voice control | 32.24% | 60.64% | 58.23%–63.52% | 98.33% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include network delay, fixed server time and model misspecification; it does not identify network delay or guarantee an upper bound on its effect. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 100.00% | 36.33% | 3.38 / 5.21 | 0 |
| lite_debugging_b | 21 | 98.33% | 33.04% | 3.46 / 5.61 | 0 |
| lite_assembly_a | 21 | 86.67% | 28.15% | 5.06 / 7.65 | 0 |
| lite_assembly_b | 23 | 85.00% | 26.52% | 5.39 / 8.73 | 0 |
| lite_support_a | 22 | 93.33% | 39.57% | 3.24 / 4.33 | 0 |
| lite_support_b | 24 | 100.00% | 37.84% | 3.12 / 4.28 | 0 |
| lite_presenter_a | 24 | 98.33% | 33.43% | 4.26 / 6.43 | 0 |
| lite_presenter_b | 22 | 98.33% | 31.05% | 4.59 / 6.26 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 3.667 s, p95 6.710 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0058 s; maximum dispatch lag 0.0000 s.
- 8 states have only inactive-field errors, leaving the application decision correct.
- 453 updates accepted on the reconstructed timeline; rejected responses: {"older_than_active": 13, "after_horizon": 14}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 20 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 25.70 s; correct for its source but wrong for current evidence 580.95 s; wrong for both source and current evidence 34.24 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.197 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.
- The immediate-first-retry rule above applies to transport failures. HTTP 429 and 5xx uses Retry-After (delay-seconds or HTTP-date) as a minimum wait, with a shared episode cooldown. Without that header, bounded backoff starts at 1 s. The server's delay is not capped at 8 s. Concurrency is limited to 32 workers; rate-limit attempts count toward the same attempt budget.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 33.24% | 23.85% |
| IDE debugging | 34.68% | 28.01% |
| Assembly | 27.33% | 18.11% |
| Support | 38.70% | 28.39% |
| Presenter voice control | 32.23% | 20.91% |

Raw logical request duration, including failed attempts and retry waits: p50 3.667 s, p95 6.710 s; 453 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | claude-haiku-5-5 low decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 99.17% |
| Assembly | 0.00% | 0.00% | 85.83% |
| Support | 1.67% | 0.00% | 96.67% |
| Presenter voice control | 0.00% | 0.00% | 98.33% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | None | None |
| lite_debugging_b | target_result: 1 | 28 |
| lite_assembly_a | route: 8, next_step: 5, destination: 1 | 28, 32, 39, 40, 47, 48, 49, 50 |
| lite_assembly_b | route: 9, next_step: 3, destination: 1 | 6, 32, 38, 39, 42, 43, 46, 49, 59 |
| lite_support_a | recorder: 4 | 50, 52, 53, 55 |
| lite_support_b | None | None |
| lite_presenter_a | slide: 1 | 56 |
| lite_presenter_b | question_card: 1 | 38 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../../PROTOCOL.md)
- [Debugging rules](../../../../debugging.md), [assembly rules](../../../../assembly.md), [support rules](../../../../support.md), [presenter rules](../../../../presenter.md)
- [Frozen run](../../../../../../runs/lite-v1-claude-haiku-5-5-low-20261009-pass3-retry-v1/run.json)
- [Frozen episodes](../../../../../../runs/lite-v1-claude-haiku-5-5-low-20261009-pass3-retry-v1/episodes.json)
- [Release and response events](../../../../../../runs/lite-v1-claude-haiku-5-5-low-20261009-pass3-retry-v1/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py --run runs/lite-v1-claude-haiku-5-5-low-20261009-pass3-retry-v1 --out docs/lite/results/claude-haiku-5-5-20261009/low/pass3 --label 'Claude Haiku 5.5 low — pass 3'
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 1400355,
  "cached_tokens": 887400,
  "output_tokens": 342891,
  "reasoning_tokens": 0
}
```
