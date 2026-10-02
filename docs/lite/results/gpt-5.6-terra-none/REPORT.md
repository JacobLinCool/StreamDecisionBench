# SDB recording-cadence diagnostics: gpt-5.6-terra none

3 families, 6 scenarios; duration 120 s per scenario, evidence releases every 2 s, 360 logical requests. One final valid response per state; transport failures are retried as configured. Requested model: gpt-5.6-terra, reasoning effort none. All model scores use recorded responses.

**Untimed decision accuracy: 80.28%; In-force accuracy (transport retries excluded): 57.42%.**

These are recording-cadence diagnostics. The published leaderboard uses normalized log-AUC over 0.5–8 s.

Network-removed in-force accuracy (secondary estimate): 74.14% (range 70.28%–75.36%).

## Family results

| Family | Untimed decision | In-force accuracy | Segment-balanced accuracy | All questions exact (diagnostic) |
|---|---:|---:|---:|---:|
| IDE debugging | 72.50% | 55.58% | 50.77% | 72.50% |
| Assembly | 76.67% | 54.55% | 45.58% | 76.67% |
| Support | 91.67% | 62.12% | 54.55% | 91.67% |

The application decision contains the model's own route, globally required answers and fields used by that route. Incorrect inactive fields do not lower decision accuracy. The reconstructed timeline anchors each successful attempt's duration at its evidence release, retains postprocessing commit lag, excludes failed attempts, retry waits and dispatch queueing, and recomputes arrival order and acceptance. This differs from observed deployment time; raw-clock results appear separately. Family and overall recording-cadence scores give scenarios equal weight.

## Network-removed estimate (secondary)

Assume send-to-receipt latency = network + prefill (proportional to uncached input tokens) + decode (proportional to output tokens, for text-generating models). The token-independent remainder is treated as network. Queueing only adds time, so the estimate uses the fast envelope: the intercept of a 10th-percentile regression with nonnegative token slopes. The range uses 500 within-scenario bootstrap samples with blocks of 10 consecutive releases.

Estimated network 1.214 s (range 0.937–1.304 s); prefill 25.8 ms/1k tokens; decode 0.00 ms/token; fastest response 1.109 s; 12 requests clamped at receipt.

| Scope | Recorded-cadence score | Network removed (estimate) | Range | Untimed accuracy |
|---|---:|---:|---:|---:|
| Overall | 57.42% | 74.14% | 70.28%–75.36% | 80.28% |
| IDE debugging | 55.58% | 67.21% | 64.55%–68.10% | 72.50% |
| Assembly | 54.55% | 71.58% | 67.76%–72.79% | 76.67% |
| Support | 62.12% | 83.62% | 78.53%–85.18% | 91.67% |

This secondary estimate leaves the primary score unchanged. The token-independent remainder can include fixed server time, so it bounds the network effect from above. The range reflects estimator uncertainty, not variation across repeated model runs. Untimed accuracy is a state-level diagnostic, not an upper bound for arbitrary in-force trajectories.

## Scenario results

| Scenario | Reference transitions | Untimed | In-force accuracy | Response p50 / p95 (s) | Failed requests |
|---|---:|---:|---:|---:|---:|
| lite_debugging_a | 20 | 76.67% | 59.09% | 1.58 / 1.94 | 0 |
| lite_debugging_b | 21 | 68.33% | 52.06% | 1.51 / 2.16 | 0 |
| lite_assembly_a | 21 | 76.67% | 53.15% | 1.60 / 2.34 | 0 |
| lite_assembly_b | 23 | 76.67% | 55.96% | 1.50 / 2.17 | 0 |
| lite_support_a | 22 | 88.33% | 62.64% | 1.47 / 2.17 | 0 |
| lite_support_b | 24 | 95.00% | 61.61% | 1.48 / 2.02 | 0 |

## Execution and scoring checks

- Completed 360 states in 6 scenarios; 0 failed logical requests.
- Successful-attempt latency: p50 1.524 s, p95 2.146 s; includes client processing and the recorded service/network path.
- Maximum recorded release lag 0.0101 s; maximum dispatch lag 0.0000 s.
- 0 states have only inactive-field errors, leaving the application decision correct.
- 358 updates accepted on the reconstructed timeline; rejected responses: {"older_than_active": 2}.
- Pipelined execution dispatches a request at every release. A complete newer-source response becomes active atomically; older arrivals cannot overwrite it. Scenarios execute serially.
- Untimed accuracy uses the same responses without another model pass. SDK retries: 0; network timeout: 20 s.
- Protocol: retry_excluded_successful_attempt_v1; at most 32 request workers; scenario concurrency 1.
- The analysis re-scores original events. Recorded-run and analysis-source manifests remain separate for traceability.

Error duration grouped by the source of the decision in force: no decision 11.15 s; correct for its source but wrong for current evidence 164.90 s; wrong for both source and current evidence 130.55 s. These sums span all scenarios; source groups are not causal attribution.

## Transport reliability and raw-clock diagnostics

- Attempt error rate: 0.00% (0 failed attempts / 360 total attempts, including final successes).
- Logical request retry rate: 0.00% (0 retried requests / 360 logical requests).
- Failed attempt types: {}.
- Failed attempts took 0.000 s in total; excluded failures and retry waits total 0.000 s, and excluded dispatch queueing totals 0.165 s. Requests can overlap, so these sums are not the recording's wall-clock duration.
- At most 5 attempts per request; the first retry is immediate, then backoff starts at 0.5 s and is capped at 8 s. SDK retries are disabled.

The raw clock retains failures, waits and actual late deliveries. It is a separate diagnostic:

| Scope | Raw in-force accuracy | Raw segment-balanced accuracy |
|---|---:|---:|
| Overall | 57.41% | 50.29% |
| IDE debugging | 55.57% | 50.76% |
| Assembly | 54.55% | 45.57% |
| Support | 62.11% | 54.54% |

Raw logical request duration, including failed attempts and retry waits: p50 1.524 s, p95 2.146 s; 358 accepted raw-clock updates.

Exhausted retries or non-transport errors make a run incomplete; no complete primary score is published. API and response validity determine success. Reference-answer correctness never triggers a retry.

## Simple baselines

Local offline baselines compare answer correctness; their duration scores were not measured.

| Family | First option | Lexical overlap | gpt-5.6-terra none decision |
|---|---:|---:|---:|
| IDE debugging | 0.00% | 0.00% | 72.50% |
| Assembly | 0.00% | 0.00% | 76.67% |
| Support | 1.67% | 0.00% | 91.67% |

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

## Interpretation limits

One recorded model pass on development scenarios. Adjacent states are dependent; these observations do not establish general model discrimination, repeated-run stability or deployment validity. Release cadence is controlled and has no independent human-timing calibration. The language reference supports a finite authored expression set, rather than arbitrary natural language.

The difference between timed and untimed accuracy is descriptive, not a causal estimate of changing model speed. The current and v0 datasets differ in questions, composition, scenarios and timing rules; their score differences cannot be attributed solely to fan-out. Data and references were frozen before each pass; model mistakes did not trigger question edits or additional model calls for this analysis.

## Reproduction files

- [Task and execution protocol](../../PROTOCOL.md)
- [Debugging rules](../../debugging.md), [assembly rules](../../assembly.md), [support rules](../../support.md)
- [Frozen run](../../../../runs/lite-v1-gpt-5.6-terra-none-retry-v1/run.json)
- [Frozen episodes](../../../../runs/lite-v1-gpt-5.6-terra-none-retry-v1/episodes.json)
- [Release and response events](../../../../runs/lite-v1-gpt-5.6-terra-none-retry-v1/events.jsonl)
- [Complete scores, errors and raw-clock diagnostics](analysis.json)

From the repository root, reproduce the report and local baselines without model calls:

```sh
uv run python scripts/lite/lite_report.py --run runs/lite-v1-gpt-5.6-terra-none-retry-v1 --out docs/lite/results/gpt-5.6-terra-none
```

Token usage includes cached input. Only returned usage is summed; usage for failed requests that returned none is unknown. No cost estimate is inferred here.

```json
{
  "input_tokens": 1031609,
  "cached_tokens": 0,
  "output_tokens": 16320,
  "reasoning_tokens": 0
}
```
