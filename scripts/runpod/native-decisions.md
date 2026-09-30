# Native decision-model experiment

The round-2 cohort uses one RunPod L40S (48 GB), native upstream decision code,
and the unchanged four-family dataset with 480 states and eight scenarios.
Checkpoint revisions, base revisions, source commits and execution settings
are frozen in `runs/runpod-openweight-20260930-round2/plan.json`.

The executable cohort consists of Kev-4B, Bespoke Nimble-9B and SemIf using
Qwen3.5-4B in direct-logit mode. Sol-2B remains a documented preflight failure:
its weights were published without the referenced compatible Decision runtime.
The official Studio imports private runtime modules and requires ROCm. The
preflight evidence is retained separately from model recording failures.

`decision_bootstrap.sh` creates separate pinned CUDA environments for the
decision models and SemIf. `decision_cohort.py` prepares immutable checkpoints,
hashes the actual files and launches `decision_record.py` in isolated process
groups. Timed-out jobs are terminated with their descendants. Model calls and
report generation run on the Pod after SSH disconnects. GPU auto-stop and final
termination are scheduled through `runpodctl pod create` before execution.

The 10 GB `/workspace` volume retains source, raw events, audits, logs and a
checksum-protected evidence archive across GPU stop. Model weights and dependency
caches use disposable `/opt` storage. The local reconnecting collector mirrors
evidence every minute, verifies the complete remote archive and all request,
dataset, episode, event and recording-source hashes before deleting the owned Pod.
No benchmark call is made over the unstable local internet connection.

Every question's native committed answer is preserved. Structured instructions,
state fields, option descriptions and ordering pass through explicit native
input mappings. Before recording, all 480 requests pass native token-budget
audits. There is no context truncation or CPU offload. Three unrelated synthetic
warmups precede each pass. Native Nimble and SemIf probabilities/logits are kept
in event usage diagnostics. Kev's full probability vectors are not retained by
the benchmark event schema.

Nimble and SemIf process fields independently on CUDA. Their request latency
includes answering the whole question map, including queueing and tokenization.
Kev uses the released pointer head and fused native runtime; CUDA graphs,
cross-request caching and date-fact augmentation are disabled. All backbones
use BF16; native head precision and calibration policies are recorded explicitly.

Regenerate complete results without model calls:

```sh
.venv/bin/python scripts/runpod/decision_report.py \
  --raw runs/runpod-openweight-20260930-round2 \
  --reports docs/lite/results/runpod-openweight-20260930-round2
```

Add `--bundle output/runpod-openweight-20260930-round2.tar.gz` after verified
resource deletion. The bundle includes the exact deployment source archive,
raw evidence, CSV, standard log-AUC reports, native input audits, first error
witnesses per family, cost evidence and per-file SHA-256 checksums. Partial or
failed settings never receive a full-dataset score.

Validation:

```sh
.venv/bin/python -m pytest -q tests/test_runpod_decisions.py \
  tests/test_runpod_recording.py tests/test_lite_runtime_retries.py \
  tests/test_lite_reports.py
```

The aggregate authorized budget is US$10 across both rounds. Round 1 reserves
US$2.63; the five-hour round-2 GPU cap and 48-hour storage cap put the planned
combined maximum at US$8.276. Actual cost evidence distinguishes elapsed-time
estimates, balance changes and delayed provider billing. One pass per setting
describes this dataset and deployment; it does not establish a stable ranking
or a controlled hardware comparison with hosted API measurements.
