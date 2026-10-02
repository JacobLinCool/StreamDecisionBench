# Winnow on RTX PRO 6000

6 of 6 full-dataset passes completed and hash-verified.

| Model | Mean log-AUC (%) | Sample SD (pp) | Range (%) | Mean untimed (%) |
|---|---:|---:|---:|---:|
| EldanRing/Winnow-12B | 43.15 | 0.01 | 43.14–43.16 | 46.46 |
| EldanRing/Winnow-E4B | 18.97 | 0.01 | 18.96–18.98 | 19.79 |

| Pass | Log-AUC (%) | Untimed (%) | p50 / p95 (s) | Failed attempts |
|---|---:|---:|---:|---:|
| [winnow-12b-pass1](winnow-12b-pass1/REPORT.md) | 43.15 | 46.46 | 0.325 / 0.455 | 0 |
| [winnow-e4b-pass1](winnow-e4b-pass1/REPORT.md) | 18.96 | 19.79 | 0.171 / 0.238 | 0 |
| [winnow-12b-pass2](winnow-12b-pass2/REPORT.md) | 43.14 | 46.46 | 0.332 / 0.455 | 0 |
| [winnow-e4b-pass2](winnow-e4b-pass2/REPORT.md) | 18.97 | 19.79 | 0.171 / 0.235 | 0 |
| [winnow-12b-pass3](winnow-12b-pass3/REPORT.md) | 43.16 | 46.46 | 0.326 / 0.450 | 0 |
| [winnow-e4b-pass3](winnow-e4b-pass3/REPORT.md) | 18.98 | 19.79 | 0.169 / 0.232 | 0 |

## Measurement

One RunPod NVIDIA RTX PRO 6000 Blackwell Server Edition (96 GB), with model and benchmark on the same host. Both models use verified BF16 GGUF weights, the pinned upstream Winnow native CUDA decision server, F16 KV cache, a 32,768-position context, four decision branches, selected answer head and exclusive memory scheduling. Native prefix reuse is enabled within each pass. Each pass starts a fresh server; three unrelated synthetic warmups and a model-free input audit are excluded from recording. Loopback HTTP, tokenization, queueing and inference are included in latency.

The unchanged dataset contains 480 states across eight scenarios, released at a 2 s cadence with 32 workers and serial scenarios. The primary score is equal-family normalized log-AUC over 0.5–8 s under the existing retry-excluded protocol. Reported means give each of the three passes equal weight. Sample SD and ranges describe repeat variation on this fixed dataset; they are not uncertainty estimates over independent tasks.

Winnow-12B uses upstream temperature 1.0. Winnow-E4B uses its published BF16 calibration temperature 1.3331553765162731. Native committed choices are preserved; no setting was selected using SDB accuracy.

## Reproduction and provenance

`uv run python scripts/runpod/winnow_report.py`

Dataset SHA-256: `fdfdd55d0f304cfdd63a283ad073755750fb934d093309034d3051a5c6b7e1af`. Winnow inference commit: `77d14580c6732ca2f3745750c1dc1fd446d8bcee`. The frozen plan records model revisions and weight checksums. Raw events, request audits, dependencies, source snapshots, GPU details and server logs are retained in `runs/winnow-pro6000-20261003`.

## Rental cleanup

Pod deletion verified: True. Estimated GPU charge across both allocations: US$4.22, excluding container-disk charges. This is an elapsed-time estimate, not a final invoice. The first allocation ended during a pre-recording residency-log check and produced no benchmark requests. The replacement used the same termination deadline and completed the recorded cohort.
