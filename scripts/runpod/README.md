# Pinned RunPod open-weight experiment

This cohort records the unchanged four-family SDB dataset on one NVIDIA RTX PRO 6000
Blackwell Server Edition. Each of four settings records all 480 states once, at the
dataset's 2 s cadence. Model and benchmark run on the same host.

| Setting | Weights | Immutable revision |
|---|---|---|
| Laya English | `convaiinnovations/laya` | `55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851` |
| Laya typed-decisions | `convaiinnovations/laya-typed-decisions` | `1a793eb568e6718f15941d08f85432581df534e3` |
| Laya multilingual | `convaiinnovations/laya-multilingual` | `e4e9ddf21a7b1903b7acffd8814ad4307bf63a67` |
| DJev / DiffusionGemma BF16 | `google/diffusiongemma-26B-A4B-it` | `f7f5b7f5fa82ffc52addd066915886d497f5517b` |

Upstream Laya code is pinned to `6d942c92081fbc139e736bbd9ac0023223c29b7f`, DJev to
`e5841cf41e9211608e698492658685c36e24e77a`, and the vLLM wheel to
`1ee7f78e806b5e9b7476c74edf453b58fe108157`. Installed dependency versions and GPU/driver
details are saved with the evidence. No credential is copied into the benchmark bundle.

`bootstrap.sh` installs separate Python 3.12 environments and invokes `cohort.py`.
The cohort downloads DiffusionGemma while recording the three small Laya models, then
starts vLLM and the upstream DJev server. `record.py` uses the existing SDB runtime and
preserves native committed answers. Laya's native calibration policy is used; CPU
fallback, state truncation and collapsed options reject a recording. `input_audit.py`
checks instruction, option and state token coverage without additional model inference.

`collect.py` is the local controller for the 2026-09-30 deployment, whose Pod identity
and SSH destination are deliberately explicit. Run it under `caffeinate` while the
machine remains online. It mirrors evidence every minute, reports only complete,
hash-verified runs and deletes this Pod on completion or its conservative deadline.
The Pod is also created with a four-hour provider termination deadline. The $2.09/h
GPU charge plus the 100 GB container disk stays below the $10 allocation over this
deadline. No persistent volume is provisioned. Failed settings remain identified;
they never receive a complete benchmark score.

Regenerate reports from local evidence:

```bash
uv run python scripts/runpod/summarize.py \
  --recordings runs/runpod-openweight-20260930 \
  --reports docs/lite/results/runpod-openweight-20260930
```

The controller produces an export at `output/runpod-openweight-20260930.tar.gz` with a
SHA-256 companion. It includes the raw runs, installed dependencies, provenance,
cleanup/billing evidence, CSV/JSON summaries, reports and recording scripts. Account
profile information is excluded from the export.

After the final request/hash validation and Pod cleanup, enrich the export with the
frozen dataset, benchmark and analysis source, tests, and a per-file SHA-256 manifest:

```bash
uv run python scripts/runpod/package.py
```

`coverage.csv` and `validation.json` in the raw evidence record unique request
coverage, public request hashes, original event hashes, source hashes, and committed
answer consistency. The provider billing snapshot may lag; cost estimates are
identified separately from observed charges.

Validation:

```bash
uv run pytest -q tests/test_runpod_recording.py \
  tests/test_lite_runtime_retries.py tests/test_lite_reports.py
```

The result interpretation concerns this deployment. Same-host latency is different
from the paper's hosted API measurements, and a single pass cannot establish a stable
ranking or statistical significance.
