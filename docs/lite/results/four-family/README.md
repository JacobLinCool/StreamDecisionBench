# Four-family log-AUC results

Primary score: normalized area under in-force accuracy over 0.5–8 s, integrated with respect to log interval. Average scenarios equally within each family, then average the four families equally. All requests were recorded at 2 s; the replay retains each answer and measured latency.

The domain spans update rates four times faster and slower than the recording cadence, with equal log weight on each side. It defines a controlled evaluation domain; deployment-specific event rates can motivate other ranges.

## Hosted APIs

| Setting | IDE | Assembly | Support | Presenter | Macro log-AUC | Untimed | Report |
|---|---:|---:|---:|---:|---:|---:|---|
| Luna low | 46.70% | 43.28% | 45.72% | 45.36% | 45.26% | 88.75% | [report](gpt-5.6-luna-low/REPORT.md) |
| Luna none | 14.31% | 19.52% | 43.31% | 45.53% | 30.67% | 43.75% | [report](gpt-5.6-luna-none/REPORT.md) |
| Terra low | 44.63% | 46.61% | 50.32% | 50.59% | 48.04% | 95.42% | [report](gpt-5.6-terra-low/REPORT.md) |
| Terra none | 48.84% | 49.91% | 56.18% | 61.48% | 54.11% | 82.08% | [report](gpt-5.6-terra-none/REPORT.md) |
| Astra low | 45.58% | 47.16% | 39.20% | 48.66% | 45.15% | 99.79% | [report](gpt-6-astra-low/REPORT.md) |
| Jev | 41.30% | 62.79% | 67.95% | 66.46% | 59.63% | 63.75% | [report](jev-latest/REPORT.md) |

## Self-hosted settings

| Setting | IDE | Assembly | Support | Presenter | Macro log-AUC | Untimed | Report |
|---|---:|---:|---:|---:|---:|---:|---|
| Laya English | 0.00% | 0.00% | 1.67% | 0.00% | 0.42% | 0.42% | [report](../runpod-openweight-20260930/laya-english/REPORT.md) |
| Laya typed-decisions | 0.00% | 0.00% | 1.67% | 4.17% | 1.46% | 1.46% | [report](../runpod-openweight-20260930/laya-typed-decisions/REPORT.md) |
| Laya multilingual | 0.00% | 0.84% | 0.00% | 0.00% | 0.21% | 0.21% | [report](../runpod-openweight-20260930/laya-multilingual/REPORT.md) |
| DJev / DiffusionGemma | 22.59% | 6.15% | 28.63% | 26.43% | 20.95% | 21.88% | [report](../runpod-openweight-20260930/djev-diffusiongemma/REPORT.md) |
| Kev-4B | 15.69% | 12.94% | 36.71% | 18.30% | 20.91% | 21.46% | [report](../runpod-openweight-20260930-round2/kev-4b/REPORT.md) |
| Bespoke Nimble-9B | 1.25% | 6.03% | 21.36% | 13.05% | 10.42% | 22.50% | [report](../runpod-openweight-20260930-round2/nimble-9b/REPORT.md) |
| Qwen3.5-4B direct-logit | 0.00% | 11.68% | 27.61% | 19.88% | 14.79% | 17.08% | [report](../runpod-openweight-20260930-round2/semif-qwen35-4b/REPORT.md) |

Each setting has one complete pass over all 480 states. For Luna low, Luna none, Terra low, Terra none and Jev, the original six scenarios and the two presenter scenarios were recorded in separate sessions; Astra low was recorded in one session covering all eight scenarios. No new model query was made for this evaluation.

Each analysis contains `auc.primary`, six `auc.sensitivity` conditions, and fixed 2 s diagnostics in `scores`. The physical wall-clock trace and secondary network-removal estimate are separate. The integration rule was adopted after inspecting the recorded passes; comparisons are descriptive and do not establish stable rankings.

The self-hosted settings use their respective GPU runtime and native decision interface. See the [deployment and composition analysis](../../../research/openweight-hybrids/README.md).

[Evaluation policy](../../../../paper/analysis/evaluation_policy.json). Regenerate: `uv run python paper/analysis/lite_reports.py`.
