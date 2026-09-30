# Runs

Git versions the hosted passes below (`runs/lite-v1-*-retry-v1/`), an explicit allowlist of self-hosted evidence and this index. Ad-hoc runs,
console logs (`*.log`) and `legacy/` stay local and are not versioned. Every file inside a run folder
is as recorded, with one exception: in the five merged `*-four-family-retry-v1/run.json` files, `combined_from[].run`
was rewritten on 2026-09-30 from absolute paths to paths relative to the merged run folder. No other field
changed, `events.jsonl` and `events_sha256` are untouched, and re-running `merge` on the two parts reproduces
these files byte for byte.

| Path | Contents |
|---|---|
| `lite-v1-<setting>-four-family-retry-v1/` | **The paper's recorded passes**: all eight scenarios of `data/lite/v1` (`fdfdd55d…`) for each of the six settings (`gpt-5.6-luna-low`, `gpt-5.6-luna-none`, `gpt-5.6-terra-low`, `gpt-5.6-terra-none`, `gpt-6-astra-low`, `jev-latest`) under `retry_excluded_successful_attempt_v1`. Five are the `merge` of the two parts below (`run.json:combined_from` lists them); `gpt-6-astra-low` was recorded in one session (next row). `paper/analysis/lite_numbers.py` and `lite_figures.py` rescore these folders. |
| `lite-v1-<setting>-retry-v1/` | Part 1: the six IDE debugging, assembly and support scenarios, recorded 2026-09-28 (UTC) on the build `60f6a877…`, whose six episodes are byte-identical in `data/lite/v1`. |
| `lite-v1-<setting>-presenter-retry-v1/` | Part 2: the two presenter voice control scenarios, recorded 2026-09-29 (UTC) on `data/lite/v1`. |
| `lite-v1-gpt-6-astra-low-four-family-retry-v1/` | Reported in the paper as Astra low: `gpt-6-astra` at reasoning effort low (the model does not accept `none`), all eight scenarios of `data/lite/v1` in one session on 2026-09-29 16:51–17:07 (UTC), same protocol. Not a merge, so its `run.json` has no `combined_from`. Report: `docs/lite/results/four-family/gpt-6-astra-low/`. |
| `runpod-openweight-20260930/runs/{laya-english,laya-typed-decisions,laya-multilingual,djev-diffusiongemma}/` | Four self-hosted BF16 settings on RTX PRO 6000 Blackwell Server (96 GB); each has the same eight frozen scenarios and 480 requests, recorded on 2026-09-30. |
| `runpod-openweight-20260930-round2/runs/{kev-4b,nimble-9b,semif-qwen35-4b}/` | Three self-hosted BF16 native settings on L40S (48 GB), recorded on 2026-09-30; Qwen is a direct-logit baseline. |

Each folder holds `run.json` (configuration, dataset hash, recording times, `events_sha256`), `episodes.json` (the frozen scenarios), `events.jsonl` (every release, request attempt and response; hashed byte for byte, see `.gitattributes`), `metrics.json` and `raw_wallclock_metrics.json`; the part folders and the single-session `lite-v1-gpt-6-astra-low-four-family-retry-v1` folder also keep per-scenario score files (`<episode>.json`, `<episode>.raw_wallclock.json`).

The self-hosted folders expose only `run.json`, `episodes.json` and `events.jsonl`. Their cohorts also expose input audits, native source revisions, prepared weight/config hashes and dependency versions through exact `.gitignore` allowlists. Raw logs and model weights remain local. Recompute from a clone with `uv run --group paper python paper/analysis/lite_openweight.py`; this needs no GPU or API key. Original events and configurations are unchanged.

A new pass needs a fresh `--out` folder (`run` refuses an existing one). Name it outside the `lite-v1-*-retry-v1` pattern unless it should be versioned.
