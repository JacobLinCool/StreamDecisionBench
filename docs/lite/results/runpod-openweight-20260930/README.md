# RunPod open-weight SDB results

Completed 4 of 4 settings; each completed setting covers all 8 scenarios and 480 states.

| Setting | Log-AUC 0.5–8 s (%) | Untimed (%) | Latency p50 / p95 (s) | Failed attempts |
|---|---:|---:|---:|---:|
| [Laya English](laya-english/REPORT.md) | 0.42 | 0.42 | 0.126 / 0.240 | 0 |
| [Laya typed-decisions](laya-typed-decisions/REPORT.md) | 1.46 | 1.46 | 0.129 / 0.235 | 0 |
| [Laya multilingual](laya-multilingual/REPORT.md) | 0.21 | 0.21 | 0.068 / 0.132 | 0 |
| [DJev / DiffusionGemma 26B-A4B (BF16)](djev-diffusiongemma/REPORT.md) | 20.95 | 21.88 | 0.257 / 0.403 | 0 |

Regenerate all current evaluation scores with `uv run python paper/analysis/lite_reports.py`. The execution and cost records below describe the original recordings.

## Measurement and interpretation

Recorded on 2026-09-30 (Asia/Taipei), on one RunPod NVIDIA RTX PRO 6000 Blackwell Server Edition (96 GB). The benchmark and model are on the same host. Laya calls its native library; DJev calls its local HTTP server. Latency includes normal request dispatch and inference. It does not include an internet round trip. Consequently, these latency-dependent scores describe this deployment and must not be treated as a controlled hardware comparison with the paper's hosted API rows.

The unchanged four-family dataset, 2 s recording cadence, 32 client workers, one scenario at a time and retry_excluded_successful_attempt_v1 scoring are used. Only transport failures may be retried, at most three attempts. No incorrect answer is retried or repaired. Raw wall-clock metrics are preserved separately. The primary normalized log-AUC is recomputed by the existing paper analysis over 0.5–8 s with equal family weights.

The standard reports also retain the benchmark's secondary latency-intercept diagnostic and its range. It assumes latency can be decomposed into network, prefill and (when applicable) decode contributions; the intercept can also contain fixed server or client time. On these same-host deployments it is not a measurement of internet latency and does not replace the primary score.

Laya checkpoints use the upstream runtime's calibration policy, CUDA BF16 autocast, eager execution, max_len=8192 and head_max_len=1024. CPU fallback, dropped state tokens and collapsed options invalidate a recording. DJev uses unquantized DiffusionGemma BF16, a 128-token canvas, one denoise step, no thinking, and the upstream automatic noise sampling policy (up to four draws, threshold 0.1). Model revisions, upstream source commits and installed dependencies are frozen in the raw evidence.

Upstream sources: [Laya](https://github.com/NandhaKishorM/laya), [DJev](https://github.com/mmastrac/djev), [DiffusionGemma weights](https://huggingface.co/google/diffusiongemma-26B-A4B-it), [vLLM structured-read implementation](https://github.com/vllm-project/vllm/pull/57250).

One pass per setting. Adjacent stream states are dependent; no significance claim or stable ranking is inferred. Model download, initialization and three unrelated synthetic warm-up requests precede recording and are excluded from model latency.

## Files and reproduction

[results.csv](results.csv) contains unrounded machine-readable values; [results.json](results.json) also lists unavailable settings. Each setting folder contains the standard SDB report and analysis.json. Raw run folders contain frozen episodes, original events, configuration and scores.

Regenerate from the repository root:

```bash
uv run python scripts/runpod/summarize.py --recordings runs/runpod-openweight-20260930 --reports docs/lite/results/runpod-openweight-20260930
```

## Input coverage audit

Native tokenization was audited without additional model calls. Instructions, option text, option markers and state tokens were checked against each checkpoint's actual tokenizer.

| Setting | Question rows | Maximum sequence tokens | Truncation / option issues |
|---|---:|---:|---:|
| Laya English | 3120 | 4250 | 0 |
| Laya typed-decisions | 3120 | 4250 | 0 |
| Laya multilingual | 3120 | 4470 | 0 |

The complete audit is retained as input-audit.json with the raw recordings. The English and typed-decisions checkpoints warn that their choice:11+ temperature is clamped by the upstream runtime to 0.5; that runtime policy is preserved. These results evaluate committed decisions, without a calibration-quality claim.

## Cost and cleanup

Pod wr8xay3x75qxpa; GPU rate $2.09/h. Conservative elapsed-time GPU charge estimate: $2.6093. This estimate counts the full provisioning-to-deletion interval; RunPod billing evidence is preserved with the recording. Pod deletion verified: True. Budget: $10.

Including disk, the estimated total is $2.6265, using the observed Pod billing rate over that same conservative interval. The observed account balance decrease is $2.6242. The provider's billing snapshot is still partial; neither value is presented as a final invoice. Account spending rate after cleanup: $0.00/h.
