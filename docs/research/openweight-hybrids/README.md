# Self-hosted decisions and their counterfactual compositions

Reproduce: `uv run --group paper python paper/analysis/lite_openweight.py`.

All primary values are normalized log-AUC over 0.5–8 s, equally averaged over scenarios within each
family and then families. Standalone measurements retain their original release clocks; compositions
use common nominal releases. Every recorded successful-attempt duration plus commit lag is retained.

| Setting | Log-AUC 0.5–8 s (%) | Untimed (%) | p50 / p95 (s) | GPU; same-host latency |
|---|---:|---:|---:|---|
| [Laya English](../../../docs/lite/results/runpod-openweight-20260930/laya-english/REPORT.md) | 0.42 | 0.42 | 0.126 / 0.240 | RTX PRO 6000 (96 GB) |
| [Laya typed-decisions](../../../docs/lite/results/runpod-openweight-20260930/laya-typed-decisions/REPORT.md) | 1.46 | 1.46 | 0.129 / 0.235 | RTX PRO 6000 (96 GB) |
| [Laya multilingual](../../../docs/lite/results/runpod-openweight-20260930/laya-multilingual/REPORT.md) | 0.21 | 0.21 | 0.068 / 0.132 | RTX PRO 6000 (96 GB) |
| [DJev / DiffusionGemma](../../../docs/lite/results/runpod-openweight-20260930/djev-diffusiongemma/REPORT.md) | 20.95 | 21.88 | 0.257 / 0.403 | RTX PRO 6000 (96 GB) |
| [Kev-4B](../../../docs/lite/results/runpod-openweight-20260930-round2/kev-4b/REPORT.md) | 20.91 | 21.46 | 0.160 / 0.261 | L40S (48 GB) |
| [Bespoke Nimble-9B](../../../docs/lite/results/runpod-openweight-20260930-round2/nimble-9b/REPORT.md) | 10.42 | 22.50 | 6.162 / 41.782 | L40S (48 GB) |
| [Qwen3.5-4B direct-logit](../../../docs/lite/results/runpod-openweight-20260930-round2/semif-qwen35-4b/REPORT.md) | 14.79 | 17.08 | 0.972 / 1.707 | L40S (48 GB) |

## Pair selection and acceptance

All seven completed self-hosted settings are paired with Terra none, the hosted GPT setting with the highest standalone log-AUC in the existing recordings. No pair is excluded based on its result; arbitration rules are unchanged from the Jev/GPT analysis.

The provisional component never regresses the active source; Terra none wins equal-source ties.
Its correction may regress by zero ticks (freshest), one tick (one-tick lag), or without a cross-component
bound (late override). Each component maintains its own source high-water mark even on rejected
deliveries. No rule consults references or output correctness. Nimble is a provisional-role control,
not a faster component in these recordings.

| System | Log-AUC 0.5–8 s (%) |
|---|---:|
| Terra none alone | 54.11 |
| Jev + Terra none | 66.21 |
| Laya English + Terra none | 27.27 |
| Laya typed-decisions + Terra none | 27.77 |
| Laya multilingual + Terra none | 26.22 |
| DJev / DiffusionGemma + Terra none | 42.07 |
| Kev-4B + Terra none | 41.05 |
| Bespoke Nimble-9B + Terra none | 54.08 |
| Qwen3.5-4B direct-logit + Terra none | 48.73 |

## Complete local/policy matrix

| Provisional setting | Arbitration | Log-AUC 0.5–8 s (%) | Fixed 2 s A (%) | Correction time share, log-weighted (%) |
|---|---|---:|---:|---:|
| Laya English | Freshest source | 27.27 | 24.00 | 33.62 |
| Laya English | One-tick lag | 33.65 | 25.10 | 46.79 |
| Laya English | Late override | 34.94 | 25.10 | 52.45 |
| Laya typed-decisions | Freshest source | 27.77 | 24.33 | 33.36 |
| Laya typed-decisions | One-tick lag | 34.07 | 25.60 | 46.51 |
| Laya typed-decisions | Late override | 35.33 | 25.60 | 52.19 |
| Laya multilingual | Freshest source | 26.22 | 21.91 | 32.03 |
| Laya multilingual | One-tick lag | 33.06 | 23.17 | 45.23 |
| Laya multilingual | Late override | 34.64 | 23.17 | 51.67 |
| DJev / DiffusionGemma | Freshest source | 42.07 | 41.20 | 37.02 |
| DJev / DiffusionGemma | One-tick lag | 45.11 | 41.25 | 49.94 |
| DJev / DiffusionGemma | Late override | 45.16 | 41.25 | 53.91 |
| Kev-4B | Freshest source | 41.05 | 39.08 | 34.20 |
| Kev-4B | One-tick lag | 44.73 | 39.23 | 47.30 |
| Kev-4B | Late override | 44.87 | 39.23 | 52.51 |
| Bespoke Nimble-9B | Freshest source | 54.08 | 59.83 | 97.31 |
| Bespoke Nimble-9B | One-tick lag | 54.08 | 59.83 | 97.31 |
| Bespoke Nimble-9B | Late override | 54.08 | 59.83 | 97.31 |
| Qwen3.5-4B direct-logit | Freshest source | 48.73 | 51.77 | 66.09 |
| Qwen3.5-4B direct-logit | One-tick lag | 49.10 | 51.89 | 70.45 |
| Qwen3.5-4B direct-logit | Late override | 49.08 | 51.89 | 70.64 |

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
