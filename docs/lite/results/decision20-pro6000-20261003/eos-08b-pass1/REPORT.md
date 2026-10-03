# SDB log-AUC: Decision-2.0-Eos-0.8B — pass 1

Primary normalized log-AUC over 0.5–8 s: **5.02%**; untimed accuracy: 5.21%.
Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.

| Family | Log-AUC (%) |
|---|---:|
| live_debugging | 3.80 |
| procedural_coaching | 0.83 |
| support_call_assist | 9.82 |
| presenter_voice_control | 5.63 |

Quadrature: 256 log-spaced subintervals; maximum change from the preceding grid 0.000322 percentage points across all scenario metrics.
This is numerical convergence, not statistical uncertainty. One recorded pass per setting.

The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.

## SDB recording-cadence diagnostics: vllm-sr/Decision-2.0-Eos-0.8B

4 families, 8 scenarios; duration 120 s per scenario, evidence releases every 2 s, 480 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: vllm-sr/Decision-2.0-Eos-0.8B. All model scores use recorded responses.

**Untimed decision accuracy: 5.21%; In-force accuracy (transport retries excluded): 5.07%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 5.07% (range 5.07%–5.07%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 4.17% | 3.90% | 3.75% | 0.00% |
| Assembly | 0.83% | 0.83% | 2.08% | 0.00% |
| Support | 10.00% | 9.87% | 6.76% | 0.00% |
| Presenter voice control | 5.83% | 5.69% | 6.59% | 0.00% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Network-removed estimate (secondary)

Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + decode (proportional to output tokens, for text-generating models). The token-independent remainder is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Estimated network 0.000 s (range 0.000–0.000 s); prefill 25.3 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.131 s; 0 requests clamped at receipt.

| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 5.07% | 5.07% | 5.07%–5.07% | 5.21% |
| IDE debugging | 3.90% | 3.90% | 3.90%–3.90% | 4.17% |
| Assembly | 0.83% | 0.83% | 0.83%–0.83% | 0.83% |
| Support | 9.87% | 9.87% | 9.87%–9.87% | 10.00% |
| Presenter voice control | 5.69% | 5.69% | 5.69%–5.69% | 5.83% |

Unconstrained intercept -0.028209 s (range -0.032102–-0.025193 s). Extrapolation to zero tokens can be negative; negative latency cannot be removed, so replay projects it to zero. analysis.json retains the unconstrained estimate. Scores and recordings are unchanged.

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include fixed server time, so it bounds the network effect from above. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 6.67% | 6.13% | 0.29 / 0.40 | 0 |
| lite_debugging_b | 21 | 1.67% | 1.67% | 0.29 / 0.39 | 0 |
| lite_assembly_a | 21 | 0.00% | 0.00% | 0.32 / 0.49 | 0 |
| lite_assembly_b | 23 | 1.67% | 1.67% | 0.33 / 0.51 | 0 |
| lite_support_a | 22 | 11.67% | 11.40% | 0.22 / 0.26 | 0 |
| lite_support_b | 24 | 8.33% | 8.34% | 0.20 / 0.24 | 0 |
| lite_presenter_a | 24 | 10.00% | 9.69% | 0.39 / 0.45 | 0 |
| lite_presenter_b | 22 | 1.67% | 1.68% | 0.39 / 0.45 | 0 |

## Execution and scoring checks

- Completed 480 states in 8 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 0.305 s, p95 0.450 s; includes same-host native calls, queueing and inference.
- Maximum recorded release lag 0.0002 s; maximum dispatch lag 0.0000 s.
- 25 states have only inactive-field errors, leaving the application decision correct.
- 480 updates accepted on the reconstructed timeline; rejected responses: {}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. Native calls have no network timeout.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 1.62 s; correct for its source but wrong for current evidence 2.80 s; wrong for both source and current evidence 906.89 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 480 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 480 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.234 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 3 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 5.07% | 4.79% |
| IDE debugging | 3.90% | 3.75% |
| Assembly | 0.83% | 2.08% |
| Support | 9.87% | 6.76% |
| Presenter voice control | 5.69% | 6.59% |

Raw logical request duration, including failed attempts and retry waits: p50 0.305 s, p95 0.450 s; 480 accepted raw-clock updates.

Exhausted retries or non-transport errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | vllm-sr/Decision-2.0-Eos-0.8B decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 4.17% |
| Assembly | 0.00% | 0.00% | 0.83% |
| Support | 1.67% | 0.00% | 10.00% |
| Presenter voice control | 0.00% | 0.00% | 5.83% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 51, target_result: 27, process: 11, rerun_scope: 9, inspect_file: 2, owner: 1 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_debugging_b | target_result: 46, route: 45, process: 33, rerun_scope: 4, owner: 3 | 0, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 |
| lite_assembly_a | route: 54, stage: 41, destination: 26, target: 15, method: 14, next_step: 6 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_assembly_b | route: 53, stage: 36, destination: 17, method: 15, target: 14, next_step: 8 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_support_a | recorder: 44, payment_stage: 29, instrument: 13, route: 12, service_action: 8, service_target: 5, hold_action: 1 | 0, 1, 4, 5, 6, 7, 12, 13, 14, 15, 16, 17 |
| lite_support_b | route: 47, contact_channel: 24, repair_action: 22, delivery_action: 16, repair_target: 7, delivery_target: 3, cancellation_action: 2 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_presenter_a | host_cue: 37, slide: 35, mode: 32, captions: 28, question_card: 10, clip_state: 4 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| lite_presenter_b | slide: 50, host_cue: 41, mode: 31, question_card: 17, captions: 15, clip_state: 1 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../../PROTOCOL.md)
- [Debugging rules](../../../debugging.md), [assembly rules](../../../assembly.md), [support rules](../../../support.md), [presenter rules](../../../presenter.md)
- [Frozen run](../../../../../runs/decision20-pro6000-20261003/pass1/eos-08b/run.json)
- [Frozen episodes](../../../../../runs/decision20-pro6000-20261003/pass1/eos-08b/episodes.json)
- [Release and response events](../../../../../runs/decision20-pro6000-20261003/pass1/eos-08b/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python paper/analysis/lite_reports.py --run runs/decision20-pro6000-20261003/pass1/eos-08b --out docs/lite/results/decision20-pro6000-20261003/eos-08b-pass1 --label 'Decision-2.0-Eos-0.8B — pass 1'
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 6079091,
  "cached_tokens": 0,
  "output_tokens": 0,
  "reasoning_tokens": 0
}
```
