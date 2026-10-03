# Hosted API repeated measurements

Wity auto and off each have one complete pass; all other hosted settings have three. Wity uses 16 workers and the recorded Retry-After policy; other hosted settings use 32 workers. Each pass covers the same 480 states in eight scenarios and four families. The original repeat cohort's 7,200 additional requests succeeded without retries. Astra low has a further third pass; its transport attempts are preserved in the individual report. Wity auto recovered 26 HTTP 429 rejections and one timeout; Wity off had no failed attempts.

Scores are equal means of independently integrated log-AUC over 0.5–8 s. SD is sample standard deviation across passes, in percentage points; it is unavailable for a single pass. Latency values average within-pass quantiles.

| Setting | Passes | Mean log-AUC ± SD (%) | Mean untimed (%) | Mean p50 / p95 (s) | Individual log-AUC (%) |
|---|---:|---:|---:|---:|---|
| Jev | 3 | 58.50 ± 1.10 | 62.36 | 0.232 / 0.366 | [59.63](../four-family/jev-latest/REPORT.md), [57.43](pass2/jev-latest/REPORT.md), [58.45](pass3/jev-latest/REPORT.md) |
| Terra none | 3 | 55.46 ± 1.29 | 81.88 | 1.360 / 1.824 | [54.11](../four-family/gpt-5.6-terra-none/REPORT.md), [55.62](pass2/gpt-5.6-terra-none/REPORT.md), [56.67](pass3/gpt-5.6-terra-none/REPORT.md) |
| Terra low | 3 | 52.06 ± 3.48 | 95.76 | 2.134 / 3.251 | [48.04](../four-family/gpt-5.6-terra-low/REPORT.md), [54.03](pass2/gpt-5.6-terra-low/REPORT.md), [54.10](pass3/gpt-5.6-terra-low/REPORT.md) |
| Astra low | 3 | 49.51 ± 4.44 | 99.86 | 2.353 / 3.668 | [45.15](../four-family/gpt-6-astra-low/REPORT.md), [49.35](pass2/gpt-6-astra-low/REPORT.md), [54.03](pass3/gpt-6-astra-low/REPORT.md) |
| Luna low | 3 | 45.45 ± 0.70 | 89.93 | 2.443 / 3.976 | [45.26](../four-family/gpt-5.6-luna-low/REPORT.md), [46.23](pass2/gpt-5.6-luna-low/REPORT.md), [44.86](pass3/gpt-5.6-luna-low/REPORT.md) |
| Clef | 3 | 31.39 ± 0.41 | 38.96 | 0.885 / 1.349 | [30.96](../four-family/clef/REPORT.md), [31.76](pass2/clef/REPORT.md), [31.44](pass3/clef/REPORT.md) |
| Luna none | 3 | 30.87 ± 1.12 | 43.54 | 1.312 / 1.777 | [30.67](../four-family/gpt-5.6-luna-none/REPORT.md), [32.08](pass2/gpt-5.6-luna-none/REPORT.md), [29.86](pass3/gpt-5.6-luna-none/REPORT.md) |
| Clef Flash | 3 | 19.89 ± 0.19 | 21.67 | 0.437 / 0.954 | [19.69](../four-family/clef-flash/REPORT.md), [19.92](pass2/clef-flash/REPORT.md), [20.06](pass3/clef-flash/REPORT.md) |
| Wity-1 (off) | 1 | 8.61 (one pass) | 10.21 | 1.291 / 6.214 | [8.61](../wity-20261003/off/REPORT.md) |
| Wity-1 (auto) | 1 | 2.64 (one pass) | 27.50 | 63.534 / 124.721 | [2.64](../wity-20261003/auto/REPORT.md) |

These are descriptive measurements on a fixed dataset; two or three passes do not establish stable rankings. Served model identifiers are preserved in each analysis; Jev returned `jev-1.13.0` on every pass. Matching identifiers do not guarantee immutable provider backends.

The manuscript and counterfactual composition analyses retain their original hosted recordings. Their single-pass controls are distinct from these public leaderboard means.

Regenerate from frozen evidence without API calls:

```bash
uv run python paper/analysis/lite_hosted.py --reports
```
