# Wity hosted measurements

One complete pass per reasoning mode on the same frozen data/lite/v1 dataset and source versions. Both use 16 workers, 2 s releases, a 180 s timeout, at most five attempts per state, and Retry-After shared-cooldown recovery. Other hosted leaderboard settings use 32 workers. SD across passes is unavailable here.

| Mode | Primary log-AUC 0.5–8 s | Untimed accuracy | Successful-attempt p50 | p95 | Valid states | Failed attempts |
|---|---:|---:|---:|---:|---:|---:|
| [auto](auto/REPORT.md) | 2.64% | 27.50% | 63.53 s | 124.72 s | 480/480 | 26 HTTP 429 + 1 timeout, all recovered |
| [off](off/REPORT.md) | 8.61% | 10.21% | 1.29 s | 6.21 s | 480/480 | 0 |

Scores are reconstructed from final successful attempts, excluding dispatch queues, failed attempts and waits; the reports preserve raw wall-clock diagnostics separately. These single passes were recorded at different times and describe the measured service conditions.

Original configurations, frozen episodes and event logs are preserved in runs/wity-1-auto-workers16-retry-after-20261003-pass1 and runs/wity-1-off-workers16-retry-after-20261003-pass1. Neither incomplete launches nor partial scenarios enter the leaderboard. The manuscript and counterfactual controls retain their original cohort.
