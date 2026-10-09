# SDB results

## Current four-family evaluation

The combined public leaderboard contains **32 settings: fifteen hosted APIs and seventeen self-hosted open-weight settings**. Its primary score is normalized log-AUC over 0.5–8 s, with equal scenario weights within each family and equal family weights. All recordings use a 2 s cadence and cover eight scenarios and 480 states per complete setting.

- [Hosted API results](four-family/README.md): Luna low/none, Terra low/none, Astra low, Jev, Cloudflare Clef and Clef Flash, Perplexity Decider v1 27B, GLiDE (Fastino), GPT-6-Luna (Decisions API), Claude Haiku 5.5 low and thinking off, and Wity auto/off.
- [RTX PRO 6000 lab results](pro6000-lab-20261001/README.md): nine open-weight settings on the same lab host.
- [Winnow RunPod RTX PRO 6000 results](winnow-pro6000-20261003/README.md): Winnow-12B and Winnow-E4B, three passes each.
- [Decision 2.0 RunPod results](decision20-pro6000-20261003/README.md): six native BF16 models, three passes each.
- [Claude Haiku 5.5 three-pass results](claude-haiku-5-5-20261009/README.md): Messages API scores for adaptive thinking at low effort and thinking off, with recording evidence.
- [GPT-6-Luna Decisions API three-pass results](gpt-6-luna-decisions-20261007/README.md): native Decisions API scores, refused questions and recording evidence.
- [GLiDE three-pass results](glide-20261003/README.md): native Fastino decisions, repeat variation and recording evidence.
- [Perplexity three-pass results](hosted-api-repeats-20261003/README.md): native Decisions API scores, retries and provenance.
- [Combined leaderboard and interval figures](../../figures/README.md).

The manuscript's main analyses use six hosted settings plus the nine lab settings; its appendix on hosted settings recorded later reports Cloudflare Clef and Clef Flash, Perplexity, GLiDE, the Luna Decisions API and Claude Haiku 5.5. Wity, Winnow and Decision 2.0 extend the public leaderboard only. Luna, Terra and Jev combine the unchanged original 360 responses with separate 120-response presenter passes. Astra, Clef and Clef Flash each recorded all 480 states in one session.

Per-setting reports are English. Their opening summaries use log-AUC; recording-cadence diagnostics, raw-clock results and secondary network estimates retain separate labels. See the [protocol](../PROTOCOL.md) for clock and interpretation rules. Reproduce current reports with `uv run python paper/analysis/lite_reports.py`, without model calls.

## Winnow repeated measurements

[Winnow-12B and Winnow-E4B on RunPod RTX PRO 6000](winnow-pro6000-20261003/README.md)
records three fresh-server BF16 passes per model on the same frozen 480-state
dataset. All six passes completed with no failed attempts. The cohort report
contains per-pass scores, three-pass means and variation, latency, pinned runtime
and weight provenance, and recorded error examples. Reproduce it with
`uv run python scripts/runpod/winnow_report.py`.

## Earlier open-weight deployments

The [RunPod RTX PRO 6000 cohort](runpod-openweight-20260930/README.md) and [RunPod L40S cohort](runpod-openweight-20260930-round2/README.md) preserve deployment and native-runtime evidence. Their public leaderboard entries were superseded by the lab cohort. Retain their hardware labels and original measurements; they do not supply additional settings to the current leaderboard.

## Original three-family recordings

These reports describe the original recordings from 2026-09-28. Their prose has been translated to English; frozen runs and saved analysis values are unchanged. Re-analysis may update code provenance, so write new historical diagnostics to a scratch directory rather than overwriting the saved analysis.

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

All five runs had 0 failed attempts out of 360. The network-removed column is a historical sensitivity estimate obtained by removing a fitted non-token remainder. That remainder can include fixed server time and does not identify or bound the network-only effect (see [the protocol](../PROTOCOL.md)); correct duration is the main fixed-cadence diagnostic for these historical recordings. The current leaderboard uses four-family log-AUC. Adjacent
states are dependent and each setting has one recording, so differences describe these runs only.

### Recording contract history

On the preceding seconds-written build (`8ecaffa7…`), Jev's first attempt stopped at `lite_assembly_a` t15
when a response's committed choice was not its highest reported probability. The contract now allows one
reporting step (0.01) for rounded near-ties. That first pass and the rerun remain local historical evidence;
their older scores are not current leaderboard entries. This history is retained because the manuscript's
provenance audit checks the recorded stop location and the reporting tolerance.
