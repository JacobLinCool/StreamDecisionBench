# What the trajectory adds beyond accuracy and latency summaries

Reproduce from the repository root: `uv run --group paper python paper/analysis/lite_trajectory_value.py`.
No API calls. All six settings, eight frozen scenarios and all five Jev/GPT pairs are included.

## Errors relative to reference transitions

Assign each state to the nearest change of the composed reference, excluding initial availability; ties go to the earlier change. Near means within one tick (before, at or after that change). Each state is counted once. This labels untimed judgment errors using trajectory position; it does not use arrival timing.

| Setting | Near errors / states | Near error (%) | Far errors / states | Far error (%) |
|---|---:|---:|---:|---:|
| Luna low | 51 / 400 | 12.75 | 3 / 80 | 3.75 |
| Luna none | 226 / 400 | 56.50 | 44 / 80 | 55.00 |
| Terra low | 21 / 400 | 5.25 | 1 / 80 | 1.25 |
| Terra none | 78 / 400 | 19.50 | 8 / 80 | 10.00 |
| Astra low | 1 / 400 | 0.25 | 0 / 80 | 0.00 |
| Jev | 150 / 400 | 37.50 | 24 / 80 | 30.00 |

The neighborhood already contains 400/480 states (83.3%): raw error counts alone would exaggerate concentration. Luna low and Terra low show higher error rates near changes; Luna none does not. These descriptive counts do not establish causality or statistical significance. The signed offsets and family breakdowns are in `analysis.json`.

## Fast response followed by a slow correction

At every state, dispatch both components. Retain their recorded successful-attempt duration plus commit lag, but place both on common nominal releases t × Δ. Recompute all acceptance times and integrate the held decisions exactly. Each component discards arrivals older than a source it has already delivered, even if arbitration rejected that delivery. Fast answers never move the active source backward. Slow answers win same-source ties and can replace fast answers for that state.

- **Freshest source:** slow output must be at least as recent as the active source.
- **One-tick lag:** slow output may be one source tick older than the active decision.
- **Late override:** slow output may be arbitrarily older than the active decision.

All rules depend on source order and component identity, never reference answers or correctness. Newest source, then slow, is processed first at exactly simultaneous arrivals; arrivals at the horizon are excluded.

| Slow component (fast = Jev) | Policy | 1 s | 2 s | 4 s | 8 s | Log-AUC 0.5–8 s |
|---|---|---:|---:|---:|---:|---:|
| Luna low | Freshest source | 57.65 | 61.17 | 70.97 | 79.67 | 63.93 |
| Luna low | One-tick lag | 56.00 | 58.18 | 71.11 | 79.67 | 62.94 |
| Luna low | Late override | 47.04 | 57.62 | 71.11 | 79.67 | 59.33 |
| Luna none | Freshest source | 57.30 | 52.80 | 48.30 | 46.03 | 51.99 |
| Luna none | One-tick lag | 43.14 | 52.63 | 48.30 | 46.03 | 48.22 |
| Luna none | Late override | 43.12 | 52.63 | 48.30 | 46.03 | 47.44 |
| Terra low | Freshest source | 57.70 | 61.60 | 73.27 | 84.07 | 65.13 |
| Terra low | One-tick lag | 56.23 | 58.29 | 73.47 | 84.08 | 64.45 |
| Terra low | Late override | 47.59 | 58.15 | 73.47 | 84.08 | 61.06 |
| Terra none | Freshest source | 57.72 | 67.23 | 74.65 | 78.36 | 66.21 |
| Terra none | One-tick lag | 52.82 | 67.16 | 74.65 | 78.39 | 64.86 |
| Terra none | Late override | 52.66 | 67.16 | 74.65 | 78.39 | 63.64 |
| Astra low | Freshest source | 57.65 | 60.93 | 74.21 | 86.76 | 65.48 |
| Astra low | One-tick lag | 57.58 | 59.05 | 74.42 | 86.76 | 64.96 |
| Astra low | Late override | 45.02 | 58.51 | 74.42 | 86.76 | 60.41 |

| Standalone setting, same nominal releases | 2 s | Log-AUC 0.5–8 s |
|---|---:|---:|
| Luna low | 47.71 | 45.27 |
| Luna none | 33.26 | 30.67 |
| Terra low | 50.37 | 48.04 |
| Terra none | 59.85 | 54.11 |
| Astra low | 45.84 | 45.15 |
| Jev | 60.70 | 59.63 |

## Why the scalar summaries are insufficient

All arbitration variants of a pair have exactly the same component answers, untimed accuracies, full latency distributions (hence medians), reference schedule and request count. Those summaries cannot distinguish variants; the interleaved path and acceptance rule can. For Jev + Terra low at 2 s, freshest-source arbitration beats standalone Jev, whereas late override falls below it. At 1 s, loosening arbitration admits many outdated slow answers and causes a larger loss. The conclusion is conditional on the recorded traces, rather than a claim that one policy always wins.

The longest contiguous loss from one stale Terra-low override of a correct Jev source occurs in `lite_presenter_a`. At 60.304213 s Jev's source-30 answer correctly applies the new decision. At 60.399600 s Terra's source-29 answer arrives, correct for its own state, and late override reinstates the old decision until 62.376500 s (1.976900 s of added stale time). The reference changes clip state from pause to play. Freshest-source arbitration rejects that old answer. The full old/new composed references are saved in `analysis.json`.

A two-output system has no unique per-state untimed answer: the provisional answer and its correction have different durations. Using the slow component's final-answer accuracy as U is an explicit proxy, not the system's measured current-source judgment. Even with the exact policy-specific oracle O, that proxy can badly overpredict correctness:

| Pair / freshest policy, 2 s | Slow final U (%) | Exact O (%) | Slow U × O (%) | Actual A (%) | Slow time share (%) |
|---|---:|---:|---:|---:|---:|
| Luna low | 88.75 | 94.82 | 84.13 | 61.17 | 5.77 |
| Luna none | 43.75 | 94.82 | 41.43 | 52.80 | 45.01 |
| Terra low | 95.42 | 94.82 | 90.47 | 61.60 | 6.99 |
| Terra none | 82.08 | 94.82 | 77.82 | 67.23 | 36.08 |
| Astra low | 99.79 | 94.82 | 94.62 | 60.93 | 1.13 |

The exact identity A = O × U_cur + lucky still holds: O is the current-source time share, and U_cur is computed from whichever component actually remains in force during that share. The analysis challenges replacement of the path by marginal summaries; it does not challenge the identity.

## Scope and limitations

Exploratory analysis of all five Jev/GPT pairs and three explicitly defined policies, using the existing recordings. No policy was tuned on reference answers.

Counterfactual composition of separately recorded components; simultaneous deployment, shared service contention and repeated-run stability are not measured.

Common nominal releases differ slightly from the recorded client releases. Standalone replays are cross-checked against the published 2 s scores; the maximum absolute discrepancy is 0.017328 percentage points. Log-AUC uses the paper's family weights and log bounds, integrating analytically between all release/arrival-order crossings. On each piece, the metric has form c0 + c1/Δ; a third interior evaluation checks this form. Display curves are sampled separately and do not determine the reported area. No new evidence addresses recording-rate effects, reference audit validity or empirical transition-rate calibration.

`analysis.json` includes per-scenario partitions, accepted-response counts, curves, hashes and the complete 2 s Jev/Terra-low traces for both freshest-source and late-override arbitration.
