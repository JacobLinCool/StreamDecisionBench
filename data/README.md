# Data

| Path | Status | Contents |
|---|---|---|
| `lite/v1/` | **Current** | SDB: eight episodes (IDE debugging, assembly, support, presenter voice control; two each), 480 states. Dataset hash `fdfdd55d…`. The first six episodes are byte-identical to `legacy/lite-v1-60f6a877/`. All model-visible time is in ticks (snapshot t at tick t); the recording publishes one tick every `tick_seconds` = 2 s. See [the protocol](../docs/lite/PROTOCOL.md). |
| `lite/train-v1/` | **Training only** | Two further scenarios per family (`train_*`, 480 states) for training decision components; never part of an evaluation score. Dataset hash `50d2ee35…`. The build is audited to share no evaluation instance content, and the variants write their own rules, questions and state layout (the assembly variants keep the family's common station rules). See [the training split](../docs/lite/training.md); rebuild with `uv run python -m streamdecisionbench.lite build --split train --data <empty dir>`. |
| `legacy/lite-v1-60f6a877/` | Legacy | Previous build: the six episodes of IDE debugging, assembly and support (360 states) in tick-based time. Input of the five part-1 runs (`runs/lite-v1-<setting>-retry-v1/`); its episodes are unchanged in `lite/v1`. |
| `legacy/lite-v1-9845dd0c/` | Legacy | First tick-based build, superseded before any complete run: one support rule ("hold lasting at least hold_check_ticks") could be read as counting snapshots. Same references. |
| `legacy/lite-v1-8ecaffa7/` | Legacy | Previous build of v1 (hash `8ecaffa7…`) with the same events and reference answers, but times written in seconds (clock, utterance times, thresholds). Input of the five earlier retry-protocol runs (local only). |
| `legacy/lite-v1-b03d8c9d/` | Legacy | Earlier build of v1 (hash `b03d8c9d…`), before two public rule sentences were clarified. Input of the two historical no-retry runs. |
| `legacy/v0/` | Legacy | Dataset of the `sdb` CLI: 90 `sdb/0.1` pilot episodes and 10 rebuilt `sdb/0.2` presentation_navigation episodes. Not used by the current benchmark. Regenerate it with `uv run sdb build`. |

The `legacy/` builds are kept locally for provenance and are not versioned; only `lite/v1/` and `lite/train-v1/` are.
During development `lite/v1` was rebuilt in place (the builder requires an empty directory, so each
superseded build moved to `legacy/lite-v1-<hash8>/`). Every run records the dataset hash of the build
it used, and `uv run python -m streamdecisionbench.lite build --data <empty dir>` reproduces `fdfdd55d…`.
