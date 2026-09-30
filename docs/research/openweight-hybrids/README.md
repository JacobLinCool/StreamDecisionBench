# Self-hosted decisions and their counterfactual compositions

Reproduce: `uv run --group paper python paper/analysis/lite_openweight.py`.

All primary values are normalized log-AUC over 1–5 s, equally averaged over scenarios within each
family and then families. Standalone measurements retain their original release clocks; compositions
use common nominal releases. Every recorded successful-attempt duration plus commit lag is retained.

| Setting | Log-AUC 1–5 s (%) | Untimed (%) | p50 / p95 (s) | GPU; same-host latency |
|---|---:|---:|---:|---|
| [Laya English](../../../docs/lite/results/runpod-openweight-20260930/laya-english/REPORT.md) | 0.42 | 0.42 | 0.126 / 0.240 | RTX PRO 6000 (96 GB) |
| [Laya typed-decisions](../../../docs/lite/results/runpod-openweight-20260930/laya-typed-decisions/REPORT.md) | 1.46 | 1.46 | 0.129 / 0.235 | RTX PRO 6000 (96 GB) |
| [Laya multilingual](../../../docs/lite/results/runpod-openweight-20260930/laya-multilingual/REPORT.md) | 0.21 | 0.21 | 0.068 / 0.132 | RTX PRO 6000 (96 GB) |
| [DJev / DiffusionGemma](../../../docs/lite/results/runpod-openweight-20260930/djev-diffusiongemma/REPORT.md) | 21.20 | 21.88 | 0.257 / 0.403 | RTX PRO 6000 (96 GB) |
| [Kev-4B](../../../docs/lite/results/runpod-openweight-20260930-round2/kev-4b/REPORT.md) | 21.06 | 21.46 | 0.160 / 0.261 | L40S (48 GB) |
| [Bespoke Nimble-9B](../../../docs/lite/results/runpod-openweight-20260930-round2/nimble-9b/REPORT.md) | 11.20 | 22.50 | 6.162 / 41.782 | L40S (48 GB) |
| [Qwen3.5-4B direct-logit](../../../docs/lite/results/runpod-openweight-20260930-round2/semif-qwen35-4b/REPORT.md) | 15.48 | 17.08 | 0.972 / 1.707 | L40S (48 GB) |

## Pair selection and acceptance

All seven completed self-hosted settings are paired with Terra none, the hosted GPT setting with the highest standalone log-AUC in the existing recordings. No pair is excluded based on its result; arbitration rules are unchanged from the Jev/GPT analysis.

The provisional component never regresses the active source; Terra none wins equal-source ties.
Its correction may regress by zero ticks (freshest), one tick (one-tick lag), or without a cross-component
bound (late override). Each component maintains its own source high-water mark even on rejected
deliveries. No rule consults references or output correctness. Nimble is a provisional-role control,
not a faster component in these recordings.

| System | Log-AUC 1–5 s (%) |
|---|---:|
| Terra none alone | 60.10 |
| Jev + Terra none | 67.82 |
| Laya English + Terra none | 28.37 |
| Laya typed-decisions + Terra none | 28.75 |
| Laya multilingual + Terra none | 26.86 |
| DJev / DiffusionGemma + Terra none | 43.75 |
| Kev-4B + Terra none | 42.13 |
| Bespoke Nimble-9B + Terra none | 60.07 |
| Qwen3.5-4B direct-logit + Terra none | 53.32 |

## Complete local/policy matrix

| Provisional setting | Arbitration | Log-AUC 1–5 s (%) | Fixed 2 s A (%) | Correction time share, log-weighted (%) |
|---|---|---:|---:|---:|
| Laya English | Freshest source | 28.37 | 24.00 | 35.31 |
| Laya English | One-tick lag | 35.38 | 25.10 | 49.17 |
| Laya English | Late override | 35.39 | 25.10 | 49.21 |
| Laya typed-decisions | Freshest source | 28.75 | 24.33 | 34.94 |
| Laya typed-decisions | One-tick lag | 35.81 | 25.60 | 48.93 |
| Laya typed-decisions | Late override | 35.82 | 25.60 | 48.97 |
| Laya multilingual | Freshest source | 26.86 | 21.91 | 32.93 |
| Laya multilingual | One-tick lag | 35.19 | 23.17 | 48.70 |
| Laya multilingual | Late override | 35.21 | 23.17 | 48.77 |
| DJev / DiffusionGemma | Freshest source | 43.75 | 41.20 | 40.24 |
| DJev / DiffusionGemma | One-tick lag | 46.40 | 41.25 | 50.04 |
| DJev / DiffusionGemma | Late override | 46.39 | 41.25 | 50.05 |
| Kev-4B | Freshest source | 42.13 | 39.08 | 36.21 |
| Kev-4B | One-tick lag | 45.94 | 39.23 | 49.09 |
| Kev-4B | Late override | 45.93 | 39.23 | 49.12 |
| Bespoke Nimble-9B | Freshest source | 60.07 | 59.83 | 97.82 |
| Bespoke Nimble-9B | One-tick lag | 60.07 | 59.83 | 97.82 |
| Bespoke Nimble-9B | Late override | 60.07 | 59.83 | 97.82 |
| Qwen3.5-4B direct-logit | Freshest source | 53.32 | 51.77 | 72.22 |
| Qwen3.5-4B direct-logit | One-tick lag | 53.49 | 51.89 | 72.95 |
| Qwen3.5-4B direct-logit | Late override | 53.49 | 51.89 | 72.95 |

## Verification and scope

Original-clock replay reproduces correctness and all six time classes in 104 setting/scenario checks.
The largest nominal/original-clock difference at 2 s is 0.017328 percentage points.
The log integral is analytical between every release/arrival crossing; a third interior point checks each affine piece.
Published standalone aggregates and family partitions are checked against independently recomputed areas.
The observations cover one pass per setting on synthetic development scenarios. Retiming assumes fixed
service latency; hardware normalization, joint contention, repeated-run stability and generative Qwen
performance are outside the measurements. Sol-2B had no executable public native runtime and receives no score.

[analysis.json](analysis.json) includes all scenario/family partitions, full curves, raw event and input-audit
hashes, execution configuration and analysis-source hashes. Original recording files are unchanged.
