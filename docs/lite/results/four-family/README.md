# Four-family log-AUC results

Primary score: normalized area under in-force accuracy over 1–5 s, integrated with respect to log interval. Average scenarios equally within each family, then average the four families equally. All requests were recorded at 2 s; the replay retains each answer and measured latency.

| Setting | IDE | Assembly | Support | Presenter | Macro log-AUC | Untimed | Report |
|---|---:|---:|---:|---:|---:|---:|---|
| Luna low | 52.61% | 47.19% | 51.10% | 48.92% | 49.96% | 88.75% | [report](gpt-5.6-luna-low/REPORT.md) |
| Luna none | 15.82% | 21.43% | 47.39% | 49.06% | 33.42% | 43.75% | [report](gpt-5.6-luna-none/REPORT.md) |
| Terra low | 50.17% | 50.51% | 56.04% | 53.66% | 52.60% | 95.42% | [report](gpt-5.6-terra-low/REPORT.md) |
| Terra none | 55.22% | 54.85% | 62.88% | 67.43% | 60.10% | 82.08% | [report](gpt-5.6-terra-none/REPORT.md) |
| Astra low | 51.29% | 50.64% | 42.15% | 52.98% | 49.27% | 99.79% | [report](gpt-6-astra-low/REPORT.md) |
| Jev | 42.06% | 63.82% | 68.94% | 68.06% | 60.72% | 63.75% | [report](jev-latest/REPORT.md) |

All 2880 logical requests have valid responses; 0 failed attempts. For Luna low, Luna none, Terra low, Terra none and Jev, the original six scenarios and the two presenter scenarios were recorded in separate sessions; Astra low was recorded in one session covering all eight scenarios. No new model query was made for this evaluation.

Each analysis contains `auc.primary`, three `auc.sensitivity` conditions, and fixed 2 s diagnostics in `scores`. The physical wall-clock trace and the secondary network-removal estimate are separate. The integration rule was adopted after inspecting the recorded passes; no claim of preregistration, significance or stable ranking is made.

[Evaluation policy](../../../../paper/analysis/evaluation_policy.json). Regenerate: `uv run python paper/analysis/lite_reports.py`.
