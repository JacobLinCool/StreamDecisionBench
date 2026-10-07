# SDB log-AUC: GLiDE (Fastino)

Primary normalized log-AUC over 0.5–8 s: **39.50%**; untimed accuracy: 80.00%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 29.12 |
| procedural_coaching | 36.36 |
| support_call_assist | 41.81 |
| presenter_voice_control | 50.71 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000439 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: fastino/GLiDE

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: fastino/GLiDE. All model scores use recorded responses.

**Untimed decision accuracy: 80.00%; In-force accuracy (transport retries excluded): 40.14%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 40.14% (range 40.14%–43.42%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 55.83% | 30.25% | 28.19% | 53.33% |
| Assembly | 74.17% | 36.08% | 25.95% | 60.00% |
| Support | 99.17% | 41.69% | 34.69% | 73.33% |
| Presenter voice control | 90.83% | 52.55% | 43.71% | 61.67% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Fitted-remainder removal (secondary)

Approximate send-to-receipt latency by a token-independent intercept plus slopes for uncached input tokens and, for text-generating models, output tokens. This secondary replay removes the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Fitted remainder 0.000 s (range 0.000–0.370 s); prefill 67.0 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.562 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Remainder removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 40.14% | 40.14% | 40.14%–43.42% | 80.00% |
| IDE debugging | 30.25% | 30.25% | 30.25%–32.57% | 55.83% |
| Assembly | 36.08% | 36.08% | 36.08%–38.86% | 74.17% |
| Support | 41.69% | 41.69% | 41.69%–45.54% | 99.17% |
| Presenter voice control | 52.55% | 52.55% | 52.55%–56.72% | 90.83% |

Unconstrained intercept -0.121489 s (range -5.483783–0.370333 s). Extrapolation to zero tokens can be negative; negative latency cannot be removed, so replay projects it to zero. analysis.json retains the unconstrained estimate. Scores and recordings are unchanged.

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include network delay, fixed server time and model misspecification; it does not identify network delay or guarantee an upper bound on its effect. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 63.33% | 32.11% | 4.94 / 16.40 | 0 |
| lite_debugging_b | 21 | 48.33% | 28.39% | 12.92 / 20.53 | 0 |
| lite_assembly_a | 21 | 73.33% | 31.51% | 13.41 / 16.75 | 0 |
| lite_assembly_b | 23 | 75.00% | 40.65% | 13.28 / 16.33 | 0 |
| lite_support_a | 22 | 98.33% | 44.84% | 2.79 / 14.22 | 0 |
| lite_support_b | 24 | 100.00% | 38.53% | 10.14 / 14.29 | 0 |
| lite_presenter_a | 24 | 96.67% | 71.77% | 0.91 / 12.91 | 0 |
| lite_presenter_b | 22 | 85.00% | 33.33% | 13.07 / 15.03 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 5.439 s, p95 16.271 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0052 s; maximum dispatch lag 0.0000 s.
- 86 states have only inactive-field errors, leaving the application decision correct.
- 288 updates accepted on the reconstructed timeline; rejected responses: {"older_than_active": 167, "after_horizon": 25}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 300 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 31.02 s; correct for its source but wrong for current evidence 466.16 s; wrong for both source and current evidence 77.45 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.233 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.
- The immediate-first-retry rule above applies to transport failures. HTTP 425, 429, and 503 uses Retry-After (delay-seconds or HTTP-date) as a minimum wait, with a shared episode cooldown. Without that header, bounded backoff starts at 1 s. The server's delay is not capped at 8 s. Concurrency is limited to 32 workers; rate-limit attempts count toward the same attempt budget.
- Fastino HTTP 425 waits at least 60 s for model warmup; all transient HTTP attempts share the same cooldown and bounded attempt budget.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 40.14% | 33.13% |
| IDE debugging | 30.25% | 28.19% |
| Assembly | 36.08% | 25.95% |
| Support | 41.68% | 34.69% |
| Presenter voice control | 52.55% | 43.70% |

Raw logical request duration, including failed attempts and retry waits: p50 5.439 s, p95 16.271 s; 288 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | fastino/GLiDE decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 55.83% |
| Assembly | 0.00% | 0.00% | 74.17% |
| Support | 1.67% | 0.00% | 99.17% |
| Presenter voice control | 0.00% | 0.00% | 90.83% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 18, rerun_scope: 8, inspect_file: 1, owner: 1 | 5, 6, 8, 9, 10, 15, 25, 26, 27, 28, 29, 30 |
| lite_debugging_b | route: 25, rerun_scope: 8, owner: 3, process: 2 | 5, 6, 9, 10, 11, 12, 16, 17, 18, 22, 23, 24 |
| lite_assembly_a | route: 12, next_step: 6, destination: 3, method: 2 | 8, 12, 16, 17, 18, 27, 28, 31, 32, 39, 40, 45 |
| lite_assembly_b | route: 14, next_step: 4, destination: 2, target: 2, stage: 1 | 10, 11, 32, 33, 38, 39, 40, 41, 42, 43, 46, 47 |
| lite_support_a | recorder: 1 | 50 |
| lite_support_b | None | None |
| lite_presenter_a | question_card: 2 | 46, 47 |
| lite_presenter_b | mode: 4, host_cue: 3, slide: 3 | 5, 6, 8, 22, 36, 37, 51, 54, 59 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../PROTOCOL.md)
- [Debugging rules](../../debugging.md), [assembly rules](../../assembly.md), [support rules](../../support.md), [presenter rules](../../presenter.md)
- [Frozen run](../../../../runs/lite-v1-glide-20261003-pass1-retry-v1/run.json)
- [Frozen episodes](../../../../runs/lite-v1-glide-20261003-pass1-retry-v1/episodes.json)
- [Release and response events](../../../../runs/lite-v1-glide-20261003-pass1-retry-v1/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 7791796,
  "cached_tokens": 0,
  "output_tokens": 350405,
  "reasoning_tokens": 0
}
```
