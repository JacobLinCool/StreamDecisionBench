# Claude Haiku 5.5: three benchmark passes per thinking mode

| Setting | Mean log-AUC ± SD (%) | Mean untimed (%) | Mean p50 / p95 latency (s) |
|---|---:|---:|---:|
| Claude Haiku 5.5 low (adaptive thinking) | **36.56 ± 0.09** | 95.35 | 3.660 / 7.001 |
| Claude Haiku 5.5 thinking off | **19.38 ± 1.09** | 25.56 | 1.439 / 1.683 |

SD is the sample standard deviation across three passes, in percentage points.

The model is `claude-haiku-5-5` through the Anthropic Messages API. Both settings request effort `low` (`output_config.effort`). The first leaves thinking adaptive, the API default; the second sends `thinking: {"type": "disabled"}`. Each request carries the same system prompt as the OpenAI Responses adapter, then the questions and the state as two text blocks with a prompt-cache breakpoint after the questions. Strict structured outputs (`output_config.format`) admit only the request's own option labels and level indices.

Each pass uses the same frozen dataset and recording source versions: four families, eight scenarios, 480 requests, one release every 2 s, 32 workers, a 20 s request timeout, and at most five attempts. The six passes ran back to back on 2026-10-08 (UTC), the three low passes first. SDK retries are disabled; HTTP 429 and 5xx responses are retried within the attempt budget, honoring Retry-After through a shared episode cooldown. Every response named `claude-haiku-5-5`.

| Setting | Pass | Log-AUC (%) | Untimed (%) | p50 latency (s) | p95 latency (s) | Failed attempts | Report |
|---|---:|---:|---:|---:|---:|---:|---|
| low | 1 | 36.49 | 96.25 | 3.722 | 6.903 | 0 | [report](low/REPORT.md) |
| low | 2 | 36.53 | 94.79 | 3.593 | 7.389 | 1 | [report](low/pass2/REPORT.md) |
| low | 3 | 36.67 | 95.00 | 3.667 | 6.710 | 0 | [report](low/pass3/REPORT.md) |
| thinking off | 1 | 20.50 | 26.46 | 1.451 | 1.712 | 0 | [report](nothink/REPORT.md) |
| thinking off | 2 | 18.31 | 25.21 | 1.453 | 1.691 | 0 | [report](nothink/pass2/REPORT.md) |
| thinking off | 3 | 19.33 | 25.00 | 1.413 | 1.644 | 0 | [report](nothink/pass3/REPORT.md) |

| Family | low log-AUC (%) | low untimed (%) | thinking off log-AUC (%) | thinking off untimed (%) |
|---|---:|---:|---:|---:|
| live_debugging | 37.45 ± 0.16 | 99.44 | 12.66 ± 3.19 | 16.11 |
| presenter_voice_control | 36.61 ± 0.62 | 98.33 | 22.58 ± 1.31 | 26.67 |
| procedural_coaching | 32.26 ± 0.77 | 88.61 | 11.67 ± 0.34 | 15.28 |
| support_call_assist | 39.93 ± 0.40 | 95.00 | 30.61 ± 0.69 | 44.17 |

All 2,880 logical requests produced valid responses. One low request (pass 2, `lite_presenter_b` t=26) timed out after 20 s and succeeded on its second attempt; no other attempt failed. No response stopped with a safeguard refusal (`stop_reason: "refusal"`); such a refusal would refuse every question of its state and count as wrong wherever the composed decision uses it.

With thinking, the model answers almost every state correctly, but its median response takes longer than the 2 s release interval, so most answers arrive after the state has moved on. Without thinking, responses are fast and stable, and most errors are judgments.

Per pass, both settings sent about 1.40M uncached input tokens and read about 0.89M tokens from the prompt cache. Output, including thinking, was about 346k tokens per low pass and 28k per thinking-off pass. At the October 2026 list price for prompts under 100k tokens ($0.10 input, $0.01 cache read, $0.50 output per million tokens), a pass costs about $0.32 at low and $0.17 with thinking off.

Scores are equal means of independently integrated per-pass log-AUC, with equal scenario weights within each family and equal family weights. Latency means average the within-pass quantiles; they are not pooled-request quantiles. The primary timeline excludes failed attempts, retry waits and dispatch queueing; each report also retains raw wall-clock diagnostics. Sample SD describes variation on the fixed dataset; it is not a confidence interval.

Machine-readable aggregates and evidence hashes: [low](low/repeats.json), [thinking off](nothink/repeats.json).

## Reproduce the individual reports

```bash
uv run python paper/analysis/lite_reports.py --run runs/lite-v1-claude-haiku-5-5-low-20261009-pass1-retry-v1 --out docs/lite/results/claude-haiku-5-5-20261009/low --label 'Claude Haiku 5.5 low'
uv run python paper/analysis/lite_reports.py --run runs/lite-v1-claude-haiku-5-5-low-20261009-pass2-retry-v1 --out docs/lite/results/claude-haiku-5-5-20261009/low/pass2 --label 'Claude Haiku 5.5 low — pass 2'
uv run python paper/analysis/lite_reports.py --run runs/lite-v1-claude-haiku-5-5-low-20261009-pass3-retry-v1 --out docs/lite/results/claude-haiku-5-5-20261009/low/pass3 --label 'Claude Haiku 5.5 low — pass 3'
uv run python paper/analysis/lite_reports.py --run runs/lite-v1-claude-haiku-5-5-nothink-20261009-pass1-retry-v1 --out docs/lite/results/claude-haiku-5-5-20261009/nothink --label 'Claude Haiku 5.5 thinking off'
uv run python paper/analysis/lite_reports.py --run runs/lite-v1-claude-haiku-5-5-nothink-20261009-pass2-retry-v1 --out docs/lite/results/claude-haiku-5-5-20261009/nothink/pass2 --label 'Claude Haiku 5.5 thinking off — pass 2'
uv run python paper/analysis/lite_reports.py --run runs/lite-v1-claude-haiku-5-5-nothink-20261009-pass3-retry-v1 --out docs/lite/results/claude-haiku-5-5-20261009/nothink/pass3 --label 'Claude Haiku 5.5 thinking off — pass 3'
```
