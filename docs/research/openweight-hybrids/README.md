# Self-hosted decisions and their counterfactual compositions

Reproduce: `uv run --group paper python paper/analysis/lite_openweight.py`.

All primary values are normalized log-AUC over 0.5–8 s, equally averaged over scenarios within each
family and then families. Standalone measurements retain their original release clocks; compositions
use common nominal releases. Every recorded successful-attempt duration plus commit lag is retained.
Self-hosted results and curves average three passes; latency summaries average per-pass quantiles.

| Setting | Mean log-AUC 0.5–8 s (%) | Mean untimed (%) | Mean p50 / p95 (s) | GPU; same-host latency |
|---|---:|---:|---:|---|
| Laya English | 0.42 | 0.42 | 0.144 / 0.256 | RTX PRO 6000 (96 GB) |
| Laya typed-decisions | 1.46 | 1.46 | 0.143 / 0.254 | RTX PRO 6000 (96 GB) |
| Laya multilingual | 0.21 | 0.21 | 0.084 / 0.154 | RTX PRO 6000 (96 GB) |
| DJev / DiffusionGemma | 20.89 | 23.13 | 0.549 / 0.650 | RTX PRO 6000 (96 GB) |
| Kev-4B | 21.22 | 22.08 | 0.223 / 0.328 | RTX PRO 6000 (96 GB) |
| Kev-9B | 28.76 | 29.86 | 0.229 / 0.369 | RTX PRO 6000 (96 GB) |
| Kev-27B | 62.15 | 72.64 | 0.529 / 0.903 | RTX PRO 6000 (96 GB) |
| Bespoke Nimble-9B | 14.43 | 22.36 | 1.711 / 12.122 | RTX PRO 6000 (96 GB) |
| Qwen3.5-4B direct-logit | 15.61 | 17.71 | 0.777 / 1.254 | RTX PRO 6000 (96 GB) |
| Winnow-12B | 43.15 | 46.46 | 0.328 / 0.453 | RTX PRO 6000 (96 GB; RunPod) |
| Winnow-E4B | 18.97 | 19.79 | 0.170 / 0.235 | RTX PRO 6000 (96 GB; RunPod) |
| Decision 2.0 Kai-0.6B | 3.63 | 3.75 | 0.198 / 0.340 | RTX PRO 6000 (96 GB; RunPod) |
| Decision 2.0 Eos-0.8B | 5.02 | 5.21 | 0.307 / 0.453 | RTX PRO 6000 (96 GB; RunPod) |
| Decision 2.0 Sol-2B | 3.59 | 3.54 | 0.404 / 0.582 | RTX PRO 6000 (96 GB; RunPod) |
| Decision 2.0 Nox-4B | 15.85 | 18.33 | 0.936 / 1.350 | RTX PRO 6000 (96 GB; RunPod) |
| Decision 2.0 Lux-9B | 24.38 | 29.58 | 1.201 / 1.731 | RTX PRO 6000 (96 GB; RunPod) |
| Decision 2.0 Vega-27B | 7.47 | 68.54 | 53.020 / 174.150 | RTX PRO 6000 (96 GB; RunPod) |

## Pair selection and acceptance

All completed self-hosted settings are paired with Terra none, the hosted GPT setting with the highest standalone log-AUC in the existing recordings. No pair is excluded based on its result; arbitration rules are unchanged from the Jev/GPT analysis.

The provisional component never regresses the active source; Terra none wins equal-source ties.
Its correction may regress by zero ticks (freshest), one tick (one-tick lag), or without a cross-component
bound (late override). Each component maintains its own source high-water mark even on rejected
deliveries. No rule consults references or output correctness. Nimble is a provisional-role control,
not a faster component in these recordings.

| System | Log-AUC 0.5–8 s (%) |
|---|---:|
| Terra none alone | 54.11 |
| Jev + Terra none | 66.21 |
| Laya English + Terra none | 27.31 |
| Laya typed-decisions + Terra none | 27.97 |
| Laya multilingual + Terra none | 26.44 |
| DJev / DiffusionGemma + Terra none | 44.74 |
| Kev-4B + Terra none | 41.84 |
| Kev-9B + Terra none | 46.61 |
| Kev-27B + Terra none | 66.76 |
| Bespoke Nimble-9B + Terra none | 53.41 |
| Qwen3.5-4B direct-logit + Terra none | 46.22 |
| Winnow-12B + Terra none | 56.09 |
| Winnow-E4B + Terra none | 39.52 |
| Decision 2.0 Kai-0.6B + Terra none | 30.10 |
| Decision 2.0 Eos-0.8B + Terra none | 32.15 |
| Decision 2.0 Sol-2B + Terra none | 32.69 |
| Decision 2.0 Nox-4B + Terra none | 48.12 |
| Decision 2.0 Lux-9B + Terra none | 52.81 |
| Decision 2.0 Vega-27B + Terra none | 54.11 |

## Complete local/policy matrix

| Provisional setting | Arbitration | Mean log-AUC 0.5–8 s (%) | Range (points) | Mean fixed 2 s A (%) | Mean correction time share, log-weighted (%) |
|---|---|---:|---:|---:|---:|
| Laya English | Freshest source | 27.31 | 0.02 | 24.12 | 33.73 |
| Laya English | One-tick lag | 33.63 | 0.01 | 25.39 | 46.86 |
| Laya English | Late override | 34.86 | 0.00 | 25.39 | 52.33 |
| Laya typed-decisions | Freshest source | 27.97 | 0.03 | 24.75 | 33.72 |
| Laya typed-decisions | One-tick lag | 34.16 | 0.01 | 26.02 | 46.85 |
| Laya typed-decisions | Late override | 35.35 | 0.01 | 26.02 | 52.33 |
| Laya multilingual | Freshest source | 26.44 | 0.07 | 22.40 | 32.41 |
| Laya multilingual | One-tick lag | 33.18 | 0.09 | 23.67 | 45.60 |
| Laya multilingual | Late override | 34.68 | 0.07 | 23.67 | 51.84 |
| DJev / DiffusionGemma | Freshest source | 44.74 | 0.54 | 46.38 | 45.36 |
| DJev / DiffusionGemma | One-tick lag | 46.28 | 0.43 | 46.47 | 56.61 |
| DJev / DiffusionGemma | Late override | 46.26 | 0.41 | 46.47 | 57.50 |
| Kev-4B | Freshest source | 41.84 | 0.07 | 40.74 | 35.96 |
| Kev-4B | One-tick lag | 45.06 | 0.02 | 40.77 | 48.96 |
| Kev-4B | Late override | 45.15 | 0.02 | 40.77 | 53.19 |
| Kev-9B | Freshest source | 46.61 | 0.46 | 45.63 | 36.27 |
| Kev-9B | One-tick lag | 48.78 | 0.40 | 45.61 | 49.24 |
| Kev-9B | Late override | 48.58 | 0.39 | 45.61 | 53.34 |
| Kev-27B | Freshest source | 66.76 | 0.42 | 70.00 | 47.09 |
| Kev-27B | One-tick lag | 64.86 | 0.38 | 69.87 | 57.11 |
| Kev-27B | Late override | 64.47 | 0.34 | 69.87 | 58.20 |
| Bespoke Nimble-9B | Freshest source | 53.41 | 0.51 | 58.53 | 90.23 |
| Bespoke Nimble-9B | One-tick lag | 53.44 | 0.49 | 58.53 | 90.45 |
| Bespoke Nimble-9B | Late override | 53.44 | 0.49 | 58.53 | 90.45 |
| Qwen3.5-4B direct-logit | Freshest source | 46.22 | 1.43 | 48.58 | 57.25 |
| Qwen3.5-4B direct-logit | One-tick lag | 46.96 | 1.16 | 48.70 | 63.60 |
| Qwen3.5-4B direct-logit | Late override | 46.93 | 1.16 | 48.70 | 63.80 |
| Winnow-12B | Freshest source | 56.09 | 0.01 | 56.73 | 38.17 |
| Winnow-12B | One-tick lag | 56.43 | 0.01 | 56.60 | 50.98 |
| Winnow-12B | Late override | 55.80 | 0.01 | 56.60 | 54.10 |
| Winnow-E4B | Freshest source | 39.52 | 0.01 | 37.36 | 34.14 |
| Winnow-E4B | One-tick lag | 43.51 | 0.00 | 38.06 | 47.25 |
| Winnow-E4B | Late override | 43.85 | 0.00 | 38.06 | 52.48 |
| Decision 2.0 Kai-0.6B | Freshest source | 30.10 | 0.03 | 27.84 | 34.92 |
| Decision 2.0 Kai-0.6B | One-tick lag | 35.76 | 0.01 | 28.32 | 48.00 |
| Decision 2.0 Kai-0.6B | Late override | 36.64 | 0.01 | 28.32 | 52.81 |
| Decision 2.0 Eos-0.8B | Freshest source | 32.15 | 0.04 | 30.96 | 37.43 |
| Decision 2.0 Eos-0.8B | One-tick lag | 36.97 | 0.03 | 31.17 | 50.30 |
| Decision 2.0 Eos-0.8B | Late override | 37.52 | 0.02 | 31.17 | 53.83 |
| Decision 2.0 Sol-2B | Freshest source | 32.69 | 0.05 | 32.44 | 39.98 |
| Decision 2.0 Sol-2B | One-tick lag | 37.06 | 0.02 | 32.56 | 52.42 |
| Decision 2.0 Sol-2B | Late override | 37.44 | 0.02 | 32.56 | 54.95 |
| Decision 2.0 Nox-4B | Freshest source | 48.12 | 0.03 | 51.07 | 62.26 |
| Decision 2.0 Nox-4B | One-tick lag | 48.53 | 0.03 | 51.16 | 67.43 |
| Decision 2.0 Nox-4B | Late override | 48.52 | 0.03 | 51.16 | 67.67 |
| Decision 2.0 Lux-9B | Freshest source | 52.81 | 0.01 | 56.81 | 74.13 |
| Decision 2.0 Lux-9B | One-tick lag | 52.73 | 0.01 | 56.90 | 76.66 |
| Decision 2.0 Lux-9B | Late override | 52.72 | 0.01 | 56.90 | 76.75 |
| Decision 2.0 Vega-27B | Freshest source | 54.11 | 0.00 | 59.86 | 97.95 |
| Decision 2.0 Vega-27B | One-tick lag | 54.11 | 0.00 | 59.86 | 97.95 |
| Decision 2.0 Vega-27B | Late override | 54.11 | 0.00 | 59.86 | 97.95 |

## Verification and scope

Original-clock replay reproduces correctness and all six time classes in 600 setting/scenario checks.
The largest nominal/original-clock difference at 2 s is 0.017328 percentage points.
The log integral is analytical between every release/arrival crossing; a third interior point checks each affine piece.
Published standalone aggregates and family partitions are checked against independently recomputed areas.
Compositions average three self-hosted passes, each paired with the same hosted recording. Retiming assumes fixed
service latency; hardware normalization, joint contention, variability across hosted passes and generative Qwen
performance are outside the measurements. Decision 2.0 releases use their preserved native runtime and exact input audits.

[analysis.json](analysis.json) includes all scenario/family partitions, full curves, raw event and input-audit
hashes, execution configuration and analysis-source hashes. Original recording files are unchanged.
