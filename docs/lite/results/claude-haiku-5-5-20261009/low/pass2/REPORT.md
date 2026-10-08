# SDB log-AUC: Claude Haiku 5.5 low — pass 2

Primary normalized log-AUC over 0.5–8 s: **36.53%**; untimed accuracy: 94.79%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 37.27 |
| procedural_coaching | 32.87 |
| support_call_assist | 39.77 |
| presenter_voice_control | 36.21 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000524 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: claude-haiku-5-5 low

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. HTTP 429 and 5xx honor Retry-After through a shared cooldown within the attempt budget. Requested model: claude-haiku-5-5, reasoning effort low, thinking adaptive. All model scores use recorded responses.

**Untimed decision accuracy: 94.79%; In-force accuracy (failed attempts and retry waits excluded): 33.65%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 65.77% (range 64.76%–68.82%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 99.17% | 34.84% | 28.03% | 99.17% |
| Assembly | 89.17% | 28.48% | 17.92% | 89.17% |
| Support | 93.33% | 39.12% | 29.17% | 84.17% |
| Presenter voice control | 97.50% | 32.16% | 21.23% | 97.50% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Fitted-remainder removal (secondary)

Approximate send-to-receipt latency by a token-independent intercept plus slopes for uncached input tokens and, for text-generating models, output tokens. This secondary replay removes the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Fitted remainder 2.322 s (range 2.255–2.529 s); prefill 401.6 ms/1k tokens; no decode term (the model does not generate text); fastest response 1.401 s; 21 requests clamped at receipt.

| Scope | Recorded-cadence score | Remainder removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 33.65% | 65.77% | 64.76%–68.82% | 94.79% |
| IDE debugging | 34.84% | 72.51% | 71.37%–75.99% | 99.17% |
| Assembly | 28.48% | 52.26% | 51.46%–54.67% | 89.17% |
| Support | 39.12% | 77.90% | 76.86%–81.06% | 93.33% |
| Presenter voice control | 32.16% | 60.42% | 59.37%–63.56% | 97.50% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include network delay, fixed server time and model misspecification; it does not identify network delay or guarantee an upper bound on its effect. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 100.00% | 38.75% | 3.36 / 4.98 | 0 |
| lite_debugging_b | 21 | 98.33% | 30.94% | 3.30 / 8.06 | 0 |
| lite_assembly_a | 21 | 91.67% | 29.91% | 4.75 / 7.99 | 0 |
| lite_assembly_b | 23 | 86.67% | 27.05% | 5.38 / 8.72 | 0 |
| lite_support_a | 22 | 91.67% | 39.78% | 3.32 / 4.30 | 0 |
| lite_support_b | 24 | 95.00% | 38.47% | 3.12 / 4.69 | 0 |
| lite_presenter_a | 24 | 96.67% | 31.95% | 4.14 / 6.07 | 0 |
| lite_presenter_b | 22 | 98.33% | 32.37% | 4.58 / 6.16 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 3.593 s, p95 7.389 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0051 s; maximum dispatch lag 0.0000 s.
- 11 states have only inactive-field errors, leaving the application decision correct.
- 446 updates accepted on the reconstructed timeline; rejected responses: {"older_than_active": 19, "after_horizon": 15}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 20 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 25.90 s; correct for its source but wrong for current evidence 562.29 s; wrong for both source and current evidence 48.73 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.21% (1 failed attempts / 481 total attempts, including final successes).
- Logical request retry rate: 0.21% (1 retried requests / 480 logical requests).
- Failed attempt types: {"TimeoutError": 1}.
- Failed attempts took 20.166 s in total; excluded failures and retry waits total 20.166 s, and excluded dispatch queueing totals 0.189 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.
- The immediate-first-retry rule above applies to transport failures. HTTP 429 and 5xx uses Retry-After (delay-seconds or HTTP-date) as a minimum wait, with a shared episode cooldown. Without that header, bounded backoff starts at 1 s. The server's delay is not capped at 8 s. Concurrency is limited to 32 workers; rate-limit attempts count toward the same attempt budget.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 33.65% | 24.09% |
| IDE debugging | 34.84% | 28.03% |
| Assembly | 28.48% | 17.92% |
| Support | 39.12% | 29.16% |
| Presenter voice control | 32.16% | 21.23% |

Raw logical request duration, including failed attempts and retry waits: p50 3.593 s, p95 7.578 s; 445 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | claude-haiku-5-5 low decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 99.17% |
| Assembly | 0.00% | 0.00% | 89.17% |
| Support | 1.67% | 0.00% | 93.33% |
| Presenter voice control | 0.00% | 0.00% | 97.50% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | None | None |
| lite_debugging_b | target_result: 1 | 28 |
| lite_assembly_a | route: 5, next_step: 4 | 31, 39, 40, 47, 50 |
| lite_assembly_b | route: 8, next_step: 2, destination: 1 | 7, 11, 32, 38, 39, 42, 43, 48 |
| lite_support_a | recorder: 5 | 50, 52, 53, 54, 55 |
| lite_support_b | route: 3, repair_target: 3, repair_action: 3 | 39, 54, 57 |
| lite_presenter_a | slide: 2 | 50, 54 |
| lite_presenter_b | captions: 1 | 23 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../../PROTOCOL.md)
- [Debugging rules](../../../../debugging.md), [assembly rules](../../../../assembly.md), [support rules](../../../../support.md), [presenter rules](../../../../presenter.md)
- [Frozen run](../../../../../../runs/lite-v1-claude-haiku-5-5-low-20261009-pass2-retry-v1/run.json)
- [Frozen episodes](../../../../../../runs/lite-v1-claude-haiku-5-5-low-20261009-pass2-retry-v1/episodes.json)
- [Release and response events](../../../../../../runs/lite-v1-claude-haiku-5-5-low-20261009-pass2-retry-v1/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py --run runs/lite-v1-claude-haiku-5-5-low-20261009-pass2-retry-v1 --out docs/lite/results/claude-haiku-5-5-20261009/low/pass2 --label 'Claude Haiku 5.5 low — pass 2'
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 1400355,
  "cached_tokens": 889012,
  "output_tokens": 347873,
  "reasoning_tokens": 0
}
```
