# Four-family log-AUC results

Primary score: normalized area under in-force accuracy over 0.5–8 s, integrated with respect to log interval. Average scenarios equally within each family, then average the four families equally. All requests were recorded at 2 s; the replay retains each answer and measured latency.

The domain spans update rates four times faster and slower than the recording cadence, with equal log weight on each side. It defines a controlled evaluation domain; deployment-specific event rates can motivate other ranges.

## Hosted APIs

| Setting | Passes | IDE | Assembly | Support | Presenter | Mean log-AUC ± SD | Mean untimed | Report |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Jev | 3 | 38.80% | 61.16% | 67.84% | 66.21% | 58.50% ± 1.10 | 62.36% | [repeat reports](../hosted-api-repeats-20261003/README.md) |
| Terra none | 3 | 50.02% | 50.36% | 59.50% | 61.98% | 55.46% ± 1.29 | 81.88% | [repeat reports](../hosted-api-repeats-20261003/README.md) |
| Terra low | 3 | 51.92% | 49.34% | 54.56% | 52.40% | 52.06% ± 3.48 | 95.76% | [repeat reports](../hosted-api-repeats-20261003/README.md) |
| Astra low | 2 | 46.98% | 47.38% | 43.92% | 50.73% | 47.25% ± 2.97 | 99.90% | [repeat reports](../hosted-api-repeats-20261003/README.md) |
| Luna low | 3 | 48.03% | 44.04% | 44.40% | 45.33% | 45.45% ± 0.70 | 89.93% | [repeat reports](../hosted-api-repeats-20261003/README.md) |
| Clef | 3 | 35.22% | 13.60% | 59.25% | 17.48% | 31.39% ± 0.41 | 38.96% | [repeat reports](../hosted-api-repeats-20261003/README.md) |
| Luna none | 3 | 13.16% | 19.62% | 44.04% | 46.65% | 30.87% ± 1.12 | 43.54% | [repeat reports](../hosted-api-repeats-20261003/README.md) |
| Clef Flash | 3 | 13.27% | 23.71% | 28.67% | 13.90% | 19.89% ± 0.19 | 21.67% | [repeat reports](../hosted-api-repeats-20261003/README.md) |
| Wity-1 (off) | 1 | 0.00% | 3.01% | 22.59% | 8.85% | 8.61% (one pass) | 10.21% | [repeat reports](../hosted-api-repeats-20261003/README.md) |
| Wity-1 (auto) | 1 | 0.69% | 1.68% | 2.50% | 5.66% | 2.64% (one pass) | 27.50% | [repeat reports](../hosted-api-repeats-20261003/README.md) |

## Self-hosted settings

| Setting | IDE | Assembly | Support | Presenter | Macro log-AUC | Untimed | Report |
|---|---:|---:|---:|---:|---:|---:|---|
| Laya English | 0.00% | 0.00% | 1.67% | 0.00% | 0.42% | 0.42% | [report](../pro6000-lab-20261001/laya-english/REPORT.md) |
| Laya typed-decisions | 0.00% | 0.00% | 1.67% | 4.17% | 1.46% | 1.46% | [report](../pro6000-lab-20261001/laya-typed-decisions/REPORT.md) |
| Laya multilingual | 0.00% | 0.83% | 0.00% | 0.00% | 0.21% | 0.21% | [report](../pro6000-lab-20261001/laya-multilingual/REPORT.md) |
| DJev / DiffusionGemma | 25.72% | 5.65% | 25.91% | 25.15% | 20.61% | 22.92% | [report](../pro6000-lab-20261001/djev-diffusiongemma/REPORT.md) |
| Kev-4B | 17.77% | 12.76% | 35.96% | 18.29% | 21.20% | 22.08% | [report](../pro6000-lab-20261001/kev-4b/REPORT.md) |
| Kev-9B | 17.04% | 28.83% | 40.21% | 31.00% | 29.27% | 30.42% | [report](../pro6000-lab-20261001/kev-9b/REPORT.md) |
| Kev-27B | 41.41% | 67.38% | 71.69% | 67.38% | 61.97% | 72.50% | [report](../pro6000-lab-20261001/kev-27b/REPORT.md) |
| Bespoke Nimble-9B | 0.17% | 11.05% | 24.45% | 23.24% | 14.72% | 22.50% | [report](../pro6000-lab-20261001/nimble-9b/REPORT.md) |
| Qwen3.5-4B direct-logit | 0.00% | 12.40% | 27.09% | 22.36% | 15.46% | 17.71% | [report](../pro6000-lab-20261001/semif-qwen35-4b/REPORT.md) |
| Winnow-12B | 12.49% | 33.64% | 77.79% | 48.66% | 43.15% | 46.46% | [report](../winnow-pro6000-20261003/winnow-12b-pass1/REPORT.md) |
| Winnow-E4B | 11.18% | 16.22% | 11.35% | 37.09% | 18.96% | 19.79% | [report](../winnow-pro6000-20261003/winnow-e4b-pass1/REPORT.md) |

Wity auto/off each have one pass with 16 workers and Retry-After recovery; other hosted scores average two passes for Astra low and three for the remaining settings, each over all 480 states with 32 workers. SD is sample standard deviation across passes, in percentage points; unavailable for one pass. The original Luna, Terra and Jev passes combine disjoint six-scenario and presenter sessions. All 15 additional passes completed without retries; Clef Flash's original pass retains its two recovered timeout attempts. The self-hosted table shows the referenced individual recordings; the public leaderboard averages their three passes. No model query is made by this analysis.

Each analysis contains `auc.primary`, six `auc.sensitivity` conditions, and fixed 2 s diagnostics in `scores`. The physical wall-clock trace and secondary network-removal estimate are separate. The integration rule was adopted after inspecting the recorded passes; comparisons are descriptive and do not establish stable rankings.

The self-hosted settings use their respective GPU runtime and native decision interface. See the [deployment and composition analysis](../../../research/openweight-hybrids/README.md).

[Evaluation policy](../../../../paper/analysis/evaluation_policy.json). Regenerate: `uv run python paper/analysis/lite_reports.py`.
