# SDB recording-cadence diagnostics: jev-latest

3 families, 6 scenarios; duration 120 s per scenario, evidence releases every 2 s, 360 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: jev-latest. All model scores use recorded responses.

**Untimed decision accuracy: 60.83%; In-force accuracy (transport retries excluded): 58.26%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 60.14% (range 60.01%–60.22%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 44.17% | 42.05% | 42.03% | 35.83% |
| Assembly | 66.67% | 63.81% | 58.41% | 34.17% |
| Support | 71.67% | 68.92% | 66.55% | 32.50% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Network-removed estimate (secondary)

Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + decode (proportional to output tokens, for text-generating models). The token-independent remainder is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Estimated network 0.185 s (range 0.173–0.194 s); prefill 6.1 ms/1k tokens; no decode term (the model does not generate text); fastest response 0.185 s; 1 requests clamped at receipt.

| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 58.26% | 60.14% | 60.01%–60.22% | 60.83% |
| IDE debugging | 42.05% | 43.44% | 43.35%–43.50% | 44.17% |
| Assembly | 63.81% | 65.81% | 65.68%–65.90% | 66.67% |
| Support | 68.92% | 71.16% | 71.01%–71.26% | 71.67% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include fixed server time, so it bounds the network effect from above. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 43.33% | 41.10% | 0.26 / 0.36 | 0 |
| lite_debugging_b | 21 | 45.00% | 43.00% | 0.24 / 0.38 | 0 |
| lite_assembly_a | 21 | 73.33% | 70.15% | 0.25 / 0.35 | 0 |
| lite_assembly_b | 23 | 60.00% | 57.46% | 0.24 / 0.37 | 0 |
| lite_support_a | 22 | 66.67% | 64.04% | 0.22 / 0.30 | 0 |
| lite_support_b | 24 | 76.67% | 73.80% | 0.22 / 0.31 | 0 |

## Execution and scoring checks

- Completed 360 states in 6 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 0.236 s, p95 0.363 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0103 s; maximum dispatch lag 0.0000 s.
- 96 states have only inactive-field errors, leaving the application decision correct.
- 360 updates accepted on the reconstructed timeline; rejected responses: {}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 20 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 2.78 s; correct for its source but wrong for current evidence 18.41 s; wrong for both source and current evidence 279.35 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 360 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 360 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.136 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 58.25% | 55.66% |
| IDE debugging | 42.04% | 42.03% |
| Assembly | 63.80% | 58.40% |
| Support | 68.92% | 66.54% |

Raw logical request duration, including failed attempts and retry waits: p50 0.236 s, p95 0.363 s; 360 accepted raw-clock updates.

Exhausted retries or non-transport errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | jev-latest decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 44.17% |
| Assembly | 0.00% | 0.00% | 66.67% |
| Support | 1.67% | 0.00% | 71.67% |

## Error localization

Counts use fields active in the reference decision; a wrong route still makes the whole decision wrong. Several fields can be wrong at one state, so counts cannot be summed into error duration. Branch-field errors can coexist with route errors and do not establish independent capability deficits.

| Scenario | Wrong active fields and state counts | First error ticks |
|---|---|---|
| lite_debugging_a | route: 31, process: 12, rerun_scope: 10, inspect_file: 2, owner: 2 | 5, 6, 7, 8, 9, 10, 14, 15, 17, 18, 19, 25 |
| lite_debugging_b | route: 27, rerun_scope: 6, process: 5, target_result: 3, owner: 3, control_action: 2 | 2, 3, 4, 5, 6, 9, 10, 11, 12, 18, 19, 20 |
| lite_assembly_a | route: 13, next_step: 6, stage: 3, destination: 1 | 8, 9, 16, 17, 18, 23, 24, 31, 32, 35, 39, 40 |
| lite_assembly_b | route: 20, next_step: 7, target: 2, method: 2, stage: 2, destination: 1 | 4, 5, 6, 7, 10, 11, 21, 22, 32, 33, 36, 37 |
| lite_support_a | recorder: 11, payment_stage: 8, hold_action: 4 | 0, 1, 20, 21, 23, 27, 29, 30, 31, 32, 44, 45 |
| lite_support_b | route: 6, repair_action: 5, repair_target: 2, delivery_action: 1 | 4, 5, 10, 11, 20, 26, 27, 43, 46, 47, 49, 50 |

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../PROTOCOL.md)
- [Debugging rules](../../debugging.md), [assembly rules](../../assembly.md), [support rules](../../support.md)
- [Frozen run](../../../../runs/lite-v1-jev-latest-retry-v1/run.json)
- [Frozen episodes](../../../../runs/lite-v1-jev-latest-retry-v1/episodes.json)
- [Release and response events](../../../../runs/lite-v1-jev-latest-retry-v1/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python scripts/lite/lite_report.py --run runs/lite-v1-jev-latest-retry-v1 --out docs/lite/results/jev-latest
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 1250145,
  "cached_tokens": 0,
  "output_tokens": 147480,
  "reasoning_tokens": 0
}
```
