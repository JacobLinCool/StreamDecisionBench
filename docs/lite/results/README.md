# SDB results

## Current four-family evaluation

See [the log-AUC results](four-family/README.md): normalized area under in-force accuracy over a common 0.5–8 s range, giving equal weight to equal multiplicative ranges and to each family. All API recordings used a 2 s cadence. For Luna low, Luna none, Terra low, Terra none and Jev, a separate presenter pass contributes 120 responses per setting, merged with the unchanged original 360; Astra low recorded all 480 in one session. The paper reports these 480-state evaluations, aggregate and family curves, and sensitivity to the integration bounds and weights.

The per-run reports (`REPORT.md`, `COMPARISON.md`) are written in Traditional Chinese, apart from the English log-AUC summary that opens each four-family report; [the protocol](../PROTOCOL.md) and the paper are the English references.

## Original three-family recordings

The per-model reports and comparisons in this section are frozen as written on 2026-09-28 (their run paths were later made relative). Re-running `scripts/lite/lite_report.py` or `lite_compare.py` into these folders would rewrite their headings and recorded sources, so write new reports to a scratch folder.

Data: the build `60f6a877…` (tick-based time, now `data/legacy/lite-v1-60f6a877/`, local only), whose six episodes are unchanged in the current `data/lite/v1` (`fdfdd55d…`); the presenter recordings and current four-family evaluation are available in [four-family](four-family/README.md). Protocol
`retry_excluded_successful_attempt_v1`, one pass per setting, recorded back to back on 2026-09-28 (UTC). Time scores use the reconstructed
timeline that excludes transport retries.

| Model | Effective decision (untimed) | Correct duration | Correct duration, network removed (range) | Estimated network (s) | Latency p50 / p95 (s) | Report |
|---|---:|---:|---:|---:|---:|---|
| GPT-5.6-Luna low | 86.11% | 48.45% | 53.81% (48.52–56.03%) | 0.38 (0.00–0.53) | 2.29 / 4.07 | [report](gpt-5.6-luna-low/REPORT.md) |
| GPT-5.6-Luna none | 37.78% | 28.01% | 33.57% (31.18–35.20%) | 0.86 (0.50–1.12) | 1.36 / 1.93 | [report](gpt-5.6-luna-none/REPORT.md), [vs Luna low](gpt-5.6-luna-none/COMPARISON.md) |
| GPT-5.6-Terra low | 95.00% | 50.36% | 58.79% (57.07–60.79%) | 0.52 (0.41–0.64) | 2.39 / 3.79 | [report](gpt-5.6-terra-low/REPORT.md), [vs Luna](gpt-5.6-terra-low/COMPARISON.md) |
| GPT-5.6-Terra none | 80.28% | 57.42% | 74.14% (70.28–75.36%) | 1.21 (0.94–1.30) | 1.52 / 2.15 | [report](gpt-5.6-terra-none/REPORT.md), [vs Terra low](gpt-5.6-terra-none/COMPARISON.md) |
| Jev (`jev-latest`, served `jev-1.13.0`) | 60.83% | 58.26% | 60.14% (60.01–60.22%) | 0.19 (0.17–0.19) | 0.24 / 0.36 | [report](jev-latest/REPORT.md), [vs Luna](jev-latest/COMPARISON.md) |

All five runs had 0 failed attempts out of 360. The network-removed column is a secondary estimate that bounds the
network effect from above (see [the protocol](../PROTOCOL.md)); correct duration stays the primary score. Adjacent
states are dependent and each setting has one recording, so differences describe these runs only.

## Legacy

The `legacy/` folders below are kept locally and are not versioned, so the paths below exist only in the original working copy.

`legacy/lite-v1-8ecaffa7/` (local only): the five retry-protocol runs on the previous build (hash
`8ecaffa7…`), which had the same events and reference answers but wrote times in seconds. Their summary:

| Model | Effective decision (untimed) | Correct duration | Correct duration, network removed (range) | Estimated network (s) | Latency p50 / p95 (s) | Report (in `legacy/lite-v1-8ecaffa7/`, local only) |
|---|---:|---:|---:|---:|---:|---|
| GPT-5.6-Luna low | 87.50% | 52.93% | 62.31% (56.13–65.33%) | 0.62 (0.22–0.81) | 1.97 / 3.15 | `gpt-5.6-luna-low/REPORT.md` |
| GPT-5.6-Luna none | 39.72% | 30.29% | 37.42% (35.68–37.54%) | 1.12 (0.85–1.14) | 1.32 / 1.87 | `gpt-5.6-luna-none/REPORT.md`, `gpt-5.6-luna-none/COMPARISON.md` (vs Luna low) |
| GPT-5.6-Terra low | 93.33% | 58.75% | 65.80% (64.92–67.47%) | 0.41 (0.36–0.51) | 1.85 / 2.85 | `gpt-5.6-terra-low/REPORT.md`, `gpt-5.6-terra-low/COMPARISON.md` (vs Luna) |
| GPT-5.6-Terra none | 78.06% | 57.06% | 72.63% (69.73–73.56%) | 1.12 (0.91–1.19) | 1.39 / 1.86 | `gpt-5.6-terra-none/REPORT.md`, `gpt-5.6-terra-none/COMPARISON.md` (vs Terra low) |
| Jev (`jev-latest`, served `jev-1.13.0`) | 51.39% | 49.21% | 50.73% (50.67–50.79%) | 0.18 (0.17–0.18) | 0.22 / 0.33 | `jev-latest/REPORT.md`, `jev-latest/COMPARISON.md` (vs Luna) |

All five runs had 0 failed attempts out of 360. The two `none` settings use reasoning effort `none` (no reasoning tokens); their output length is almost constant, so the non-token remainder also absorbs fixed server time and some requests are clamped at receipt (reported in each REPORT). The network-removed column is a
secondary estimate: the time before each response is received is modelled as
network + prefill (proportional to input tokens) + decode (proportional to output
tokens, for text-generating models), and the per-run remainder that does not
scale with tokens is removed as network. It is estimated from the fast envelope
of each run's own requests; the range is a block-bootstrap interval. The
remainder can include fixed server time, so the column bounds the network effect
from above. Correct duration stays the primary score.

Adjacent states are dependent and each model has one recording, so differences
describe these runs only. Jev's first attempt stopped at `lite_assembly_a` t15
when a response's `choice` was not its highest reported probability; the contract
check now allows one reporting step (0.01) for rounded near-ties, and the run
above is the rerun. Luna and Terra were not rerun.


`legacy/lite-v1-b03d8c9d/` (local only; comparison in `legacy/lite-v1-b03d8c9d/gpt-5.6-terra-low/COMPARISON.md`):
GPT-5.6-Luna low and GPT-5.6-Terra low on the earlier v1 build (hash
`b03d8c9d…`, before two rule sentences were clarified), under the original
physical wall-clock protocol without retries. Not comparable with the current
results.
