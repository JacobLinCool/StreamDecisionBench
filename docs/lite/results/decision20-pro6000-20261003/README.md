# Decision 2.0 on RunPod RTX PRO 6000

18 of 18 passes complete and verified.

| Model | Mean log-AUC (%) | Mean untimed (%) | SD (pp) | Mean p50 / p95 (s) |
|---|---:|---:|---:|---:|
| vllm-sr/Decision-2.0-Kai-0.6B | 3.63 | 3.75 | 0.00 | 0.198 / 0.340 |
| vllm-sr/Decision-2.0-Eos-0.8B | 5.02 | 5.21 | 0.00 | 0.307 / 0.453 |
| vllm-sr/Decision-2.0-Sol-2B | 3.59 | 3.54 | 0.00 | 0.404 / 0.582 |
| vllm-sr/Decision-2.0-Nox-4B | 15.85 | 18.33 | 0.01 | 0.936 / 1.350 |
| vllm-sr/Decision-2.0-Lux-9B | 24.38 | 29.58 | 0.01 | 1.201 / 1.731 |
| vllm-sr/Decision-2.0-Vega-27B | 7.47 | 68.54 | 0.00 | 53.020 / 174.150 |

Each pass records all 480 states across eight scenarios at the unchanged 2 s cadence, 32 workers and serial scenarios. Primary scores use equal-family normalized log-AUC over 0.5–8 s. Three-pass means give each complete pass equal weight. Partial recordings receive no full-dataset score.

All six models use the immutable model release and its native Decision 2.0 CUDA runtime, BF16-resident backbones and the exact independent-question path. Model and benchmark run on the same RTX PRO 6000 Blackwell Server Edition (96 GB). Native manifest checks, loaded parameter counts, CUDA placement and all 480 untruncated input encodings are checked before three unrelated warmups. Every pass loads a fresh process. Latency includes queueing, tokenization and native inference. Native answers and probabilities are preserved in events.

Reproduce: `uv run python scripts/runpod/decision20_report.py`.

| Pass | Log-AUC (%) | Untimed (%) | p50 / p95 (s) | Failed attempts |
|---|---:|---:|---:|---:|
| [kai-06b-pass1](kai-06b-pass1/REPORT.md) | 3.63 | 3.75 | 0.201 / 0.340 | 0 |
| [eos-08b-pass1](eos-08b-pass1/REPORT.md) | 5.02 | 5.21 | 0.305 / 0.450 | 0 |
| [sol-2b-pass1](sol-2b-pass1/REPORT.md) | 3.59 | 3.54 | 0.403 / 0.576 | 0 |
| [nox-4b-pass1](nox-4b-pass1/REPORT.md) | 15.85 | 18.33 | 0.936 / 1.347 | 0 |
| [lux-9b-pass1](lux-9b-pass1/REPORT.md) | 24.39 | 29.58 | 1.201 / 1.731 | 0 |
| [vega-27b-pass1](vega-27b-pass1/REPORT.md) | 7.47 | 68.54 | 53.067 / 174.275 | 0 |
| [kai-06b-pass2](kai-06b-pass2/REPORT.md) | 3.63 | 3.75 | 0.195 / 0.339 | 0 |
| [eos-08b-pass2](eos-08b-pass2/REPORT.md) | 5.02 | 5.21 | 0.308 / 0.457 | 0 |
| [sol-2b-pass2](sol-2b-pass2/REPORT.md) | 3.59 | 3.54 | 0.404 / 0.581 | 0 |
| [nox-4b-pass2](nox-4b-pass2/REPORT.md) | 15.86 | 18.33 | 0.935 / 1.345 | 0 |
| [lux-9b-pass2](lux-9b-pass2/REPORT.md) | 24.39 | 29.58 | 1.200 / 1.728 | 0 |
| [vega-27b-pass2](vega-27b-pass2/REPORT.md) | 7.48 | 68.54 | 52.952 / 174.002 | 0 |
| [kai-06b-pass3](kai-06b-pass3/REPORT.md) | 3.63 | 3.75 | 0.199 / 0.340 | 0 |
| [eos-08b-pass3](eos-08b-pass3/REPORT.md) | 5.02 | 5.21 | 0.307 / 0.453 | 0 |
| [sol-2b-pass3](sol-2b-pass3/REPORT.md) | 3.59 | 3.54 | 0.404 / 0.590 | 0 |
| [nox-4b-pass3](nox-4b-pass3/REPORT.md) | 15.84 | 18.33 | 0.937 / 1.358 | 0 |
| [lux-9b-pass3](lux-9b-pass3/REPORT.md) | 24.37 | 29.58 | 1.204 / 1.733 | 0 |
| [vega-27b-pass3](vega-27b-pass3/REPORT.md) | 7.47 | 68.54 | 53.040 / 174.172 | 0 |

Pinned revisions, native file checksums and parameter counts are recorded in [the frozen plan](../../../../scripts/runpod/decision20-plan.json). [Raw events, input audits and source receipts](../../../../runs/decision20-pro6000-20261003/) preserve each measurement. The deployment archive freezes the benchmark source and dataset; the upstream source archive preserves each native runtime and is checked against its release manifest. Dependency versions and GPU identity are retained alongside the recordings. The upstream optimized path targets ROCm; these measurements use the native CUDA eager path.

Rental deletion and absence were verified at 2026-10-03T13:11:05.650300+00:00. Estimated GPU charge: US$12.98 at US$2.09/h; disk charges are additional.
