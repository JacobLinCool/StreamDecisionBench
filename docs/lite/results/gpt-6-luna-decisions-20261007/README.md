# GPT-6-Luna (Decisions API): three benchmark passes

Mean normalized log-AUC over 0.5–8 s: **32.39% ± 0.70 percentage points** (sample SD across three passes).
Mean untimed decision accuracy: **36.04%** (identical in every pass).

The model is `gpt-6-luna` through OpenAI's [Decisions API](https://developers.openai.com/api/docs/guides/decisions) (`POST /v1/decisions`, public beta), not the Responses API. Each state is sent as JSON text in `input`; every question keeps its instructions, and each option becomes a `choice` with its opaque label as `value` and its text as `description`. The API returns a choice, a probability distribution and a confidence per question; the benchmark keeps all three. The API has no reasoning-effort setting and reports no output tokens.

Each pass uses the same frozen dataset and recording source versions: four families, eight scenarios, 480 requests, one release every 2 s, 32 workers, a 20 s request timeout, and at most five attempts. The three passes ran back to back on 2026-10-06 (UTC). HTTP client retries are disabled; HTTP 429 and 5xx responses are retried within the attempt budget, honoring Retry-After through a shared episode cooldown.

| Pass | Log-AUC (%) | Untimed (%) | p50 latency (s) | p95 latency (s) | Failed attempts | Report |
|---|---:|---:|---:|---:|---:|---|
| 1 | 31.59 | 36.04 | 0.340 | 0.729 | 0 | [report](REPORT.md) |
| 2 | 32.66 | 36.04 | 0.346 | 0.615 | 0 | [report](pass2/REPORT.md) |
| 3 | 32.92 | 36.04 | 0.346 | 0.483 | 0 | [report](pass3/REPORT.md) |

| Family | Mean log-AUC (%) | Sample SD (points) | Mean untimed (%) |
|---|---:|---:|---:|
| live_debugging | 21.27 | 0.45 | 23.33 |
| presenter_voice_control | 33.06 | 0.49 | 36.67 |
| procedural_coaching | 20.39 | 1.11 | 23.33 |
| support_call_assist | 54.84 | 0.80 | 60.83 |

1440/1440 logical requests produced valid responses; 0 failed attempts and 0 retried logical requests across all three passes. Answers were identical across passes, so pass-to-pass variation comes from latency alone.

## Refused questions

The API can return `{"type": "refusal"}` for one question while answering the others; the guide does not document this answer type. It occurred at the same two states in every pass (`lite_presenter_b` t=0 and t=2, question `question_card`). A refused question commits to no option and counts as wrong wherever the composed decision uses it. At all six occurrences the model's own route was `talk`, which does not use `question_card`, so no decision was affected.

Scores are equal means of independently integrated per-pass log-AUC, with equal scenario weights within each family and equal family weights. Latency means average the within-pass quantiles; they are not pooled-request quantiles. The primary timeline excludes failed attempts, retry waits and dispatch queueing; each report also retains raw wall-clock diagnostics.

These repeated measurements describe variation on the fixed dataset. Sample SD is not a confidence interval or evidence of population-level ranking stability. Served model identifiers and exact execution provenance remain in the individual analyses.

[Machine-readable aggregate and evidence hashes](repeats.json)

## Reproduce the individual reports

```bash
uv run python paper/analysis/lite_reports.py --run runs/lite-v1-gpt-6-luna-decisions-20261007-pass1-retry-v1 --out docs/lite/results/gpt-6-luna-decisions-20261007 --label 'GPT-6-Luna (Decisions API)'
uv run python paper/analysis/lite_reports.py --run runs/lite-v1-gpt-6-luna-decisions-20261007-pass2-retry-v1 --out docs/lite/results/gpt-6-luna-decisions-20261007/pass2 --label 'GPT-6-Luna (Decisions API) — pass 2'
uv run python paper/analysis/lite_reports.py --run runs/lite-v1-gpt-6-luna-decisions-20261007-pass3-retry-v1 --out docs/lite/results/gpt-6-luna-decisions-20261007/pass3 --label 'GPT-6-Luna (Decisions API) — pass 3'
```
