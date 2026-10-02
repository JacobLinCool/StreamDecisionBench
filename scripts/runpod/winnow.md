# Winnow: three repeated open-weight passes

The frozen `winnow-plan.json` specifies two BF16 GGUF checkpoints and three passes
per checkpoint on one NVIDIA RTX PRO 6000 Blackwell Server Edition (96 GB).
`winnow_bootstrap.sh` prepares a dedicated CUDA 12.8+ development container;
`winnow_cohort.py` restarts the native upstream server for each pass, verifies
weight hashes and GPU layer residency, and invokes `winnow_record.py`.

The recorder submits the original System One requests without modifying states,
instructions or criteria. It audits all 480 requests through the native inspect
endpoint before three unrelated synthetic warmups, then uses the existing SDB
runtime: 2 s cadence, 32 workers, serial scenarios and retry-excluded timing.
The request audit does no answer inference. The native decision cache is enabled
within each pass and reset by server restart between passes. BF16 weights use F16
KV cache and a 32,768-position context, four question branches, selected answer
head, exclusive memory scheduling, full GPU offload and no generated answer text.

Model revisions, weight checksums, upstream commit and native temperature are
fixed before inference. E4B uses its published BF16 calibration temperature;
12B uses 1.0. Calibration does not change the candidate argmax. Each complete pass
retains raw events, source hashes, request hashes, input audit and server logs.

On the local host, copy `/workspace/results/` into
`runs/winnow-pro6000-20261003/`, preserving the original deployment source archive
as `deployment.tar.gz`. Its members begin with `src/`, `data/`, and `scripts/`.
After confirming all event hashes and transferring evidence, delete the rented
Pod. Provisioning must set a provider termination deadline before execution;
credentials and account metadata do not belong in the evidence export.

Generate the validated per-pass reports and descriptive three-pass summary:

```bash
uv run python scripts/runpod/winnow_report.py
```

The summary reports every completed pass and only computes a three-pass model
mean when all three passes are complete. Partial recordings receive no full-dataset
score. The report validates native committed answers, all 480 unique requests,
event hashes, model identity, recorder source and frozen runtime source.
