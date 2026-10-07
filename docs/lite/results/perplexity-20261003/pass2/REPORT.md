# SDB log-AUC: Perplexity Decider v1 27B — pass 2

Primary normalized log-AUC over 0.5–8 s: **63.60%**; untimed accuracy: 70.00%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 47.25 |
| procedural_coaching | 66.94 |
| support_call_assist | 80.11 |
| presenter_voice_control | 60.09 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000411 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: pplx-decider-v1-27b

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. HTTP 429 honors Retry-After through a shared cooldown within the attempt budget. Requested model: pplx-decider-v1-27b. All model scores use recorded responses.

**Untimed decision accuracy: 70.00%; In-force accuracy (failed attempts and retry waits excluded): 65.27%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 68.51% (range 68.40%–68.69%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 50.83% | 48.18% | 47.41% | 50.83% |
| Assembly | 74.17% | 68.82% | 66.76% | 62.50% |
| Support | 88.33% | 82.25% | 79.55% | 79.17% |
| Presenter voice control | 66.67% | 61.80% | 58.27% | 60.83% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Fitted-remainder removal (secondary)

Approximate send-to-receipt latency by a token-independent intercept plus slopes for uncached input tokens and, for text-generating models, output tokens. This secondary replay removes the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Fitted remainder 0.264 s (range 0.255–0.279 s); prefill 4.5 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.297 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Remainder removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 65.27% | 68.51% | 68.40%–68.69% | 70.00% |
| IDE debugging | 48.18% | 49.83% | 49.78%–49.92% | 50.83% |
| Assembly | 68.82% | 72.45% | 72.33%–72.66% | 74.17% |
| Support | 82.25% | 86.65% | 86.50%–86.90% | 88.33% |
| Presenter voice control | 61.80% | 65.10% | 64.99%–65.29% | 66.67% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include network delay, fixed server time and model misspecification; it does not identify network delay or guarantee an upper bound on its effect. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 50.00% | 47.15% | 0.35 / 0.71 | 0 |
| lite_debugging_b | 21 | 51.67% | 49.22% | 0.36 / 0.49 | 0 |
| lite_assembly_a | 21 | 76.67% | 71.68% | 0.37 / 0.52 | 0 |
| lite_assembly_b | 23 | 71.67% | 65.97% | 0.40 / 0.56 | 0 |
| lite_support_a | 22 | 80.00% | 74.85% | 0.34 / 0.47 | 0 |
| lite_support_b | 24 | 96.67% | 89.66% | 0.33 / 0.50 | 0 |
| lite_presenter_a | 24 | 98.33% | 90.54% | 0.36 / 0.53 | 0 |
| lite_presenter_b | 22 | 35.00% | 33.07% | 0.36 / 0.49 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 0.359 s, p95 0.529 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0051 s; maximum dispatch lag 0.0000 s.
- 32 states have only inactive-field errors, leaving the application decision correct.
- 480 updates accepted on the reconstructed timeline; rejected responses: {}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 30 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 3.39 s; correct for its source but wrong for current evidence 44.51 s; wrong for both source and current evidence 285.54 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.216 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.
- The immediate-first-retry rule above applies to transport failures. HTTP 429 uses Retry-After (delay-seconds or HTTP-date) as a minimum wait, with a shared episode cooldown. Without that header, bounded backoff starts at 1 s. The server's delay is not capped at 8 s. Concurrency is limited to 32 workers; rate-limit attempts count toward the same attempt budget.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 65.26% | 62.99% |
| IDE debugging | 48.18% | 47.41% |
| Assembly | 68.82% | 66.76% |
| Support | 82.25% | 79.55% |
| Presenter voice control | 61.80% | 58.26% |

Raw logical request duration, including failed attempts and retry waits: p50 0.359 s, p95 0.529 s; 480 accepted raw-clock updates.

Exhausted retries or nonretryable errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | pplx-decider-v1-27b decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 50.83% |
| Assembly | 0.00% | 0.00% | 74.17% |
| Support | 1.67% | 0.00% | 88.33% |
| Presenter voice control | 0.00% | 0.00% | 66.67% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 27, rerun_scope: 8, inspect_file: 2, owner: 2 | 5, 6, 7, 8, 9, 10, 14, 15, 16, 17, 18, 19 |
| lite_debugging_b | route: 20, rerun_scope: 8, owner: 6, process: 2, control_action: 2 | 5, 6, 11, 12, 18, 19, 20, 21, 22, 23, 24, 25 |
| lite_assembly_a | route: 7, destination: 7, next_step: 5, method: 2 | 13, 14, 16, 17, 18, 25, 27, 29, 30, 31, 32, 39 |
| lite_assembly_b | route: 11, destination: 6, next_step: 4, target: 2, stage: 1 | 10, 11, 19, 20, 21, 28, 38, 39, 40, 41, 42, 43 |
| lite_support_a | recorder: 6, service_action: 2, payment_stage: 2, service_target: 2 | 12, 25, 26, 38, 39, 42, 43, 48, 49, 51, 56, 57 |
| lite_support_b | delivery_action: 2 | 10, 11 |
| lite_presenter_a | question_card: 1 | 47 |
| lite_presenter_b | host_cue: 38, mode: 8, slide: 4 | 0, 2, 3, 4, 5, 6, 7, 8, 20, 21, 22, 23 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/perplexity-pass2/run.json)
- [Frozen episodes](../../../../../runs/perplexity-pass2/episodes.json)
- [Release and response events](../../../../../runs/perplexity-pass2/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 6834052,
  "cached_tokens": 0,
  "output_tokens": 3120,
  "reasoning_tokens": 0
}
```
