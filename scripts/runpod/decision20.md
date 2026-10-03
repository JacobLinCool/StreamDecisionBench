# Decision 2.0: three native passes per model

`decision20-plan.json` freezes all six releases in the Decision 2.0 collection:
Kai-0.6B, Eos-0.8B, Sol-2B, Nox-4B, Lux-9B and Vega-27B. Vega's adapter uses
the base repository revision and per-file checksums declared by its native
manifest. All model package inventories and loaded parameter counts must match
their published manifests.

One dedicated RunPod RTX PRO 6000 Blackwell Server Edition (96 GB) runs the
benchmark and model together. The provider termination deadline is configured
before launch. `decision20_bootstrap.sh` installs the pinned environment;
`decision20_cohort.py` downloads and verifies every package and base before
starting eighteen independent recording processes. Each pass loads a fresh
native runtime with BF16 residency and the exact independent-question path.
Native CUDA precision and the decision head are retained. The upstream fast
path currently targets ROCm; this deployment uses its native CUDA eager path.

`decision20_record.py` passes original System One requests directly to the
runtime. Before inference, all 480 requests pass native token-budget and
candidate-identity checks, including structured instructions, state and nullable
criteria. Three unrelated synthetic warmups precede recording. The existing
2 s cadence, 32 workers, serial scenarios and retry-excluded protocol apply.
Request latency includes tokenization, inference and serialized runtime queueing.
Events retain native answers and probabilities. Inputs are never truncated and
parameters must all reside on CUDA.

The detached worker continues independently of SSH. The local collector mirrors
evidence, validates complete recordings, and deletes only its owned rental when
the remote cohort ends. Provider termination caps compute even if collection is
interrupted. Logs and connection metadata remain private.

Reproduce complete reports from preserved evidence without model inference:

```bash
uv run python scripts/runpod/decision20_report.py
```

Only complete, hash-verified 480-state recordings receive scores. Three-pass
means require all three passes for a model. The public primary metric is
equal-family normalized log-AUC over 0.5–8 s. Pass variation describes this fixed
dataset and deployment, rather than uncertainty over independent tasks.

Validation:

```bash
uv run pytest -q tests/test_decision20_recording.py tests/test_lite_runtime_retries.py
```
