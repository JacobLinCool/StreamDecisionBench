# Self-hosted decisions and their counterfactual compositions

Reproduce: `uv run --group paper python paper/analysis/lite_openweight.py`.

All primary values are normalized log-AUC over 0.5–8 s, equally averaged over scenarios within each
family and then families. Standalone measurements retain their original release clocks; compositions
use common nominal releases. Every recorded successful-attempt duration plus commit lag is retained.

| Setting | Log-AUC 0.5–8 s (%) | Untimed (%) | p50 / p95 (s) | GPU; same-host latency |
|---|---:|---:|---:|---|
| [Laya English](../../../docs/lite/results/pro6000-lab-20261001/laya-english/REPORT.md) | 0.42 | 0.42 | 0.144 / 0.256 | RTX PRO 6000 (96 GB) |
| [Laya typed-decisions](../../../docs/lite/results/pro6000-lab-20261001/laya-typed-decisions/REPORT.md) | 1.46 | 1.46 | 0.144 / 0.257 | RTX PRO 6000 (96 GB) |
| [Laya multilingual](../../../docs/lite/results/pro6000-lab-20261001/laya-multilingual/REPORT.md) | 0.21 | 0.21 | 0.084 / 0.156 | RTX PRO 6000 (96 GB) |
| [DJev / DiffusionGemma](../../../docs/lite/results/pro6000-lab-20261001/djev-diffusiongemma/REPORT.md) | 20.61 | 22.92 | 0.565 / 0.675 | RTX PRO 6000 (96 GB) |
| [Kev-4B](../../../docs/lite/results/pro6000-lab-20261001/kev-4b/REPORT.md) | 21.20 | 22.08 | 0.231 / 0.337 | RTX PRO 6000 (96 GB) |
| [Kev-9B](../../../docs/lite/results/pro6000-lab-20261001/kev-9b/REPORT.md) | 29.27 | 30.42 | 0.229 / 0.368 | RTX PRO 6000 (96 GB) |
| [Kev-27B](../../../docs/lite/results/pro6000-lab-20261001/kev-27b/REPORT.md) | 61.97 | 72.50 | 0.538 / 0.916 | RTX PRO 6000 (96 GB) |
| [Bespoke Nimble-9B](../../../docs/lite/results/pro6000-lab-20261001/nimble-9b/REPORT.md) | 14.72 | 22.50 | 1.618 / 13.372 | RTX PRO 6000 (96 GB) |
| [Qwen3.5-4B direct-logit](../../../docs/lite/results/pro6000-lab-20261001/semif-qwen35-4b/REPORT.md) | 15.46 | 17.71 | 0.817 / 1.338 | RTX PRO 6000 (96 GB) |

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
| Laya English + Terra none | 27.32 |
| Laya typed-decisions + Terra none | 27.99 |
| Laya multilingual + Terra none | 26.43 |
| DJev / DiffusionGemma + Terra none | 44.90 |
| Kev-4B + Terra none | 41.89 |
| Kev-9B + Terra none | 46.89 |
| Kev-27B + Terra none | 66.52 |
| Bespoke Nimble-9B + Terra none | 53.46 |
| Qwen3.5-4B direct-logit + Terra none | 46.91 |

## Complete local/policy matrix

| Provisional setting | Arbitration | Log-AUC 0.5–8 s (%) | Fixed 2 s A (%) | Correction time share, log-weighted (%) |
|---|---|---:|---:|---:|
| Laya English | Freshest source | 27.32 | 24.14 | 33.74 |
| Laya English | One-tick lag | 33.63 | 25.41 | 46.88 |
| Laya English | Late override | 34.86 | 25.41 | 52.34 |
| Laya typed-decisions | Freshest source | 27.99 | 24.79 | 33.74 |
| Laya typed-decisions | One-tick lag | 34.16 | 26.06 | 46.88 |
| Laya typed-decisions | Late override | 35.36 | 26.06 | 52.34 |
| Laya multilingual | Freshest source | 26.43 | 22.39 | 32.40 |
| Laya multilingual | One-tick lag | 33.17 | 23.66 | 45.59 |
| Laya multilingual | Late override | 34.67 | 23.66 | 51.83 |
| DJev / DiffusionGemma | Freshest source | 44.90 | 46.70 | 46.47 |
| DJev / DiffusionGemma | One-tick lag | 46.39 | 46.80 | 57.37 |
| DJev / DiffusionGemma | Late override | 46.36 | 46.80 | 58.15 |
| Kev-4B | Freshest source | 41.89 | 40.85 | 36.19 |
| Kev-4B | One-tick lag | 45.06 | 40.87 | 49.17 |
| Kev-4B | Late override | 45.14 | 40.87 | 53.29 |
| Kev-9B | Freshest source | 46.89 | 45.90 | 36.24 |
| Kev-9B | One-tick lag | 49.01 | 45.88 | 49.20 |
| Kev-9B | Late override | 48.80 | 45.88 | 53.33 |
| Kev-27B | Freshest source | 66.52 | 69.71 | 47.56 |
| Kev-27B | One-tick lag | 64.64 | 69.58 | 57.44 |
| Kev-27B | Late override | 64.28 | 69.58 | 58.46 |
| Bespoke Nimble-9B | Freshest source | 53.46 | 58.57 | 90.16 |
| Bespoke Nimble-9B | One-tick lag | 53.48 | 58.57 | 90.35 |
| Bespoke Nimble-9B | Late override | 53.48 | 58.57 | 90.35 |
| Qwen3.5-4B direct-logit | Freshest source | 46.91 | 49.48 | 59.82 |
| Qwen3.5-4B direct-logit | One-tick lag | 47.52 | 49.59 | 65.32 |
| Qwen3.5-4B direct-logit | Late override | 47.50 | 49.59 | 65.47 |

## Verification and scope

Original-clock replay reproduces correctness and all six time classes in 120 setting/scenario checks.
The largest nominal/original-clock difference at 2 s is 0.017328 percentage points.
The log integral is analytical between every release/arrival crossing; a third interior point checks each affine piece.
Published standalone aggregates and family partitions are checked against independently recomputed areas.
The observations cover one pass per setting on synthetic development scenarios. Retiming assumes fixed
service latency; hardware normalization, joint contention, repeated-run stability and generative Qwen
performance are outside the measurements. Sol-2B had no executable public native runtime and receives no score.

[analysis.json](analysis.json) includes all scenario/family partitions, full curves, raw event and input-audit
hashes, execution configuration and analysis-source hashes. Original recording files are unchanged.
