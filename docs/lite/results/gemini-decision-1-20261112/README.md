# Gemini Decision 1 (Decisions API): three benchmark passes

Mean normalized log-AUC over 0.5–8 s: **63.73% ± 0.46 percentage points** (sample SD across three passes).
Mean untimed decision accuracy: **72.71%** (identical in every pass).

The model is `gemini-decision-1` through Google's [Decisions API](https://aistudio.google.com/docs/decisions-api) (`POST /v1beta/decisions`), not the `generateContent` API. Each state is sent as JSON text in `input`. Questions keep their keys and types (`noul`, `choice`, `score`); question text, option descriptions and score levels go in as text, and the opaque option labels stay the choice keys. The API returns a probability distribution and a confidence per question; the benchmark keeps both. It has no generation settings, reports no output tokens and echoes no model name.

Each pass uses the same frozen dataset and recording source versions: four families, eight scenarios, 480 requests, one release every 2 s, 32 workers and a 20 s request timeout. HTTP client retries are disabled; HTTP 429 and 5xx responses are retried within the attempt budget, honoring Retry-After through a shared episode cooldown. Passes 1 and 3 ran back to back on 2026-11-11 (UTC) and pass 2 on 2026-11-12.

| Pass | Log-AUC (%) | Untimed (%) | p50 latency (s) | p95 latency (s) | Max attempts | Failed attempts | Retried requests | Report |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 63.97 | 72.71 | 0.526 | 0.751 | 5 | 281 | 160 | [report](REPORT.md) |
| 2 | 63.20 | 72.71 | 0.549 | 0.941 | 10 | 404 | 243 | [report](pass2/REPORT.md) |
| 3 | 64.03 | 72.71 | 0.524 | 0.819 | 5 | 201 | 145 | [report](pass3/REPORT.md) |

| Family | Mean log-AUC (%) | Sample SD (points) | Mean untimed (%) |
|---|---:|---:|---:|
| live_debugging | 47.87 | 0.98 | 53.33 |
| presenter_voice_control | 65.11 | 0.67 | 76.67 |
| procedural_coaching | 64.91 | 1.05 | 74.17 |
| support_call_assist | 77.05 | 1.22 | 86.67 |

1440/1440 logical requests produced valid responses. Every one of the 886 failed attempts was an HTTP 429 rejection from the key's rate limit, retried after the Retry-After delay; 548 logical requests needed a retry. Answers were identical across passes, so pass-to-pass variation comes from latency alone.

## Rate limits and the second pass

Two earlier sessions of pass 2, with the standard budget of five attempts, stopped when a request's five attempts all met HTTP 429. They are kept outside the published evidence. The published pass 2 allows ten attempts per request and is otherwise identical. The attempt budget only decides whether a pass completes: failed attempts, retry waits and dispatch queueing never enter model timing or scores. A key with a higher rate limit should complete a pass at the standard budget.

## Safety blocks

The API rejects a request blocked by its safety filters with HTTP 400 and an error code (`safety`, `prohibited_content`, `blocklist`, `image_safety` or `content_blocked`). Every question of a blocked state then commits to no option and counts as wrong wherever the composed decision uses it. No request was blocked in any pass.

Scores are equal means of independently integrated per-pass log-AUC, with equal scenario weights within each family and equal family weights. Latency means average the within-pass quantiles; they are not pooled-request quantiles. The primary timeline excludes failed attempts, retry waits and dispatch queueing; each report also retains raw wall-clock diagnostics.

These repeated measurements describe variation on the fixed dataset. Sample SD is not a confidence interval or evidence of population-level ranking stability. Served model identifiers and exact execution provenance remain in the individual analyses.

[Machine-readable aggregate and evidence hashes](repeats.json)

## Reproduce the individual reports

```bash
uv run python paper/analysis/lite_reports.py --run runs/lite-v1-gemini-decision-1-20261112-pass1-retry-v1 --out docs/lite/results/gemini-decision-1-20261112 --label 'Gemini Decision 1 (Decisions API)'
uv run python paper/analysis/lite_reports.py --run runs/lite-v1-gemini-decision-1-20261112-pass2-retry-v1 --out docs/lite/results/gemini-decision-1-20261112/pass2 --label 'Gemini Decision 1 (Decisions API) — pass 2'
uv run python paper/analysis/lite_reports.py --run runs/lite-v1-gemini-decision-1-20261112-pass3-retry-v1 --out docs/lite/results/gemini-decision-1-20261112/pass3 --label 'Gemini Decision 1 (Decisions API) — pass 3'
```
