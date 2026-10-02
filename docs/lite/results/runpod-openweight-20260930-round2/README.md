# Native open-weight SDB experiment — round 2

3 of 3 executable settings completed; 480 unique requests and 8 scenarios per completed setting.

| Setting | Log-AUC 0.5–8 s (%) | Untimed (%) | p50 / p95 (s) | Failed attempts |
|---|---:|---:|---:|---:|
| [Kev-4B](kev-4b/REPORT.md) | 20.91 | 21.46 | 0.160 / 0.261 | 0 |
| [Bespoke Nimble-9B](nimble-9b/REPORT.md) | 10.42 | 22.50 | 6.162 / 41.782 | 0 |
| [SemIf / Qwen3.5-4B (direct logits)](semif-qwen35-4b/REPORT.md) | 14.79 | 17.08 | 0.972 / 1.707 | 0 |

Historical deployment cohort, superseded in the public leaderboard by the [same-host RTX PRO 6000 lab recordings](../pro6000-lab-20261001/README.md). The scores, execution and cost records below describe these original recordings. The current-report generator does not rebuild this cohort; use the frozen per-setting reproduction commands in its reports and write new outputs to a scratch directory.

## Measurement

One NVIDIA L40S GPU, BF16 backbones, native upstream decision code. Benchmark and model execute on the same Pod; latency includes tokenization, queueing and inference. Download, model initialization, input audits and three unrelated synthetic warmups are excluded. No internet round trip is included.

The unchanged dataset uses a 2 s release cadence, 32 workers and serial scenarios. Complete results use the existing retry-excluded timing protocol and equal-family normalized log-AUC over 0.5–8 s. Failed or partial settings receive no complete score. No incorrect answer is retried, repaired or used to choose a configuration.

Kev uses its native pointer head and fused CUDA runtime, with CUDA graphs, cross-request prefix caching and date-fact augmentation disabled. Nimble uses its released BF16 merged adapter, T=1.0 and independent full-prompt scoring per field. SemIf reads uncalibrated native option logits from the pinned untrained Qwen checkpoint, in fresh direct mode with thinking disabled. For Nimble and SemIf, latency includes answering every question in the decision, rather than one field.

All state fields, structured instructions, choice descriptions, option order and opaque output IDs are preserved through native mappings. The native encoders audit all 480 requests before model recording and reject context overflow. There is no CPU offload or truncated-input path. Native probability/logit diagnostics are retained for Nimble and SemIf; Kev commits its native answers without retaining a full probability vector in the SDB event schema.

One pass per setting. Related stream states are dependent. Differences describe this dataset and deployment; they do not establish significance, a stable model ranking, or a controlled comparison with the hosted API rows or the previous RTX PRO 6000 cohort. Standard reports also retain the secondary latency-intercept diagnostic and its range; its network + prefill + decode assumption can include fixed server time, and it does not replace the primary score.

## Coverage and provenance

Dataset SHA-256: `fdfdd55d0f304cfdd63a283ad073755750fb934d093309034d3051a5c6b7e1af`. Verified 1440 requests and 9360 committed question answers. Raw events, episode hashes, public request hashes, actual weight/config hashes, upstream commits and installed dependencies are retained. Each setting includes deterministically selected first error witnesses per family; these do not establish an error cause.

[results.csv](results.csv) contains unrounded results. Raw evidence contains coverage.csv, validation.json, the frozen plan, input audits, preparation logs and all recordings.

## Unavailable or failed settings

- sol-2b: Public release contains weights only. Referenced Decision runtime absent from semantic-router main 101639482e0345b62abd339d8fa0a7c226500b7f. Official decision-studio 1ab04aedc51a41f57e6ea98c480664972c5dc49c imports private decision_runtime/decision_inference modules from external DECISION_RUNTIME_PATH and requires ROCm. No native CUDA loader is published at the inspected revisions. No model inference attempted.

## Resilience, cost and cleanup

The detached Pod worker runs without a local connection. Results are flushed to /workspace/results on a retained 10 GB volume. Provider auto-stop caps GPU time at five hours; scheduled termination caps retained storage at 48 hours. The reconnecting collector copies and verifies all reachable evidence before deletion.

Original budget: US$10 across both rounds; previous round reserved US$2.63. This round's planned worst-case cost is US$5.6458; cumulative planned maximum US$8.2758. Actual costs and cleanup verification are in raw cost.json and billing.json.

```json
{
  "pod_id": "j5wuwq0av438fo",
  "deletion_verified": true,
  "gpu_hourly_rate_usd": 1.09,
  "created_at_utc": "2026-09-30T08:48:49.974458+00:00",
  "deleted_at_utc": "2026-09-30T10:06:39.715198+00:00",
  "estimated_gpu_charge_usd": 1.4138937240555558,
  "estimated_total_round_charge_usd": 1.4301081016250001,
  "previous_round_reserved_usd": 2.63,
  "cumulative_observed_balance_decrease_usd": 4.005384121399999,
  "account_current_spend_per_hour_usd": 0,
  "billing_limitation": "Provider snapshots may lag; elapsed-time estimates and observed balance decrease are not a final invoice.",
  "estimate_method": "Conservative provisioning-to-verified-deletion elapsed time at advertised GPU rate plus configured disk rates. The GPU was explicitly stopped earlier, so this estimate includes some stopped time as if GPU-billed.",
  "gpu_stop_requested_at_utc": "2026-09-30T10:04:00.427961+00:00",
  "previous_round_observed_charge_usd": 2.6242432954999977,
  "observed_round_balance_decrease_usd": 1.381140825900001
}
```

## Reproduction verification

46 relevant tests passed against a freshly extracted deployment source. Original event files were preserved. At the original evaluation domain, Pod and local result fields agreed within an absolute tolerance of 1e-12; the largest observed difference is 4.44e-16 percentage points in one family score. Coverage, event hashes and latency quantiles agree exactly. The original failed extraction and a local test-interpreter invocation failure are preserved separately from model attempts. There were zero failed benchmark attempts.
