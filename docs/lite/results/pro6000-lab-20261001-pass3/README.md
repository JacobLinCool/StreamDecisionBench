# Open-weight SDB settings on one RTX PRO 6000 — pass3

9 of 9 settings completed; 480 unique requests and 8 scenarios per setting.

| Setting | Log-AUC 0.5–8 s (%) | Untimed (%) | p50 / p95 (s) | Failed attempts |
|---|---:|---:|---:|---:|
| [Laya English](laya-english/REPORT.md) | 0.42 | 0.42 | 0.144 / 0.255 | 0 |
| [Laya typed-decisions](laya-typed-decisions/REPORT.md) | 1.46 | 1.46 | 0.142 / 0.253 | 0 |
| [Laya multilingual](laya-multilingual/REPORT.md) | 0.21 | 0.21 | 0.085 / 0.154 | 0 |
| [DJev / DiffusionGemma](djev-diffusiongemma/REPORT.md) | 21.19 | 23.33 | 0.539 / 0.646 | 0 |
| [Kev-4B](kev-4b/REPORT.md) | 21.23 | 22.08 | 0.217 / 0.334 | 0 |
| [Kev-9B](kev-9b/REPORT.md) | 28.57 | 29.58 | 0.227 / 0.362 | 0 |
| [Kev-27B](kev-27b/REPORT.md) | 62.30 | 72.71 | 0.523 / 0.893 | 0 |
| [Bespoke Nimble-9B](nimble-9b/REPORT.md) | 15.21 | 22.29 | 1.542 / 5.780 | 0 |
| [SemIf / Qwen3.5-4B (direct logits)](semif-qwen35-4b/REPORT.md) | 15.70 | 17.71 | 0.768 / 1.280 | 0 |

Regenerate all current evaluation scores with `uv run python paper/analysis/lite_reports.py`.

## Measurement

One NVIDIA RTX PRO 6000 Blackwell Server Edition (96 GB) in a lab host, BF16 backbones, native upstream decision code. Benchmark and model execute on the same host; latency includes tokenization, queueing and inference. Download, model initialization, input audits and three unrelated synthetic warmups are excluded. No internet round trip is included.

The recorders, pinned checkpoints, upstream commits and frozen dependency sets are those of the two earlier RunPod cohorts ([RTX PRO 6000](../runpod-openweight-20260930/README.md), [L40S](../runpod-openweight-20260930-round2/README.md)), which remain in the repository. Kev-9B and Kev-27B are added; all three Kev checkpoints use Kev commit `90512f1` (Kev-27B v2 is a full-weight checkpoint that needs it). Execution: `scripts/lab/pro6000.sh`.

The unchanged dataset uses a 2 s release cadence, 32 workers and serial scenarios. Complete results use the retry-excluded timing protocol and equal-family normalized log-AUC over 0.5–8 s. One pass per setting; related stream states are dependent.

## Provenance

Dataset SHA-256: `fdfdd55d0f304cfdd63a283ad073755750fb934d093309034d3051a5c6b7e1af`. Raw events, episode hashes, request hashes, prepared weight/config hashes, input audits, upstream commits (`source-provenance.json`) and installed dependencies are retained under [`runs/pro6000-lab-20261001-pass3`](../../../../runs/pro6000-lab-20261001-pass3). Laya input audits are model-free tokenizer audits of the same revisions and dataset, reused from the first RunPod cohort.

