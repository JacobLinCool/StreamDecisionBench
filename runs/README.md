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
| `lite-v1-clef-four-family-retry-v1/` | Cloudflare-hosted Clef through its native Workers AI decision API, recorded 2026-10-02 in one session on the same `fdfdd55d…` build and retry protocol. All 480 requests succeeded with no failed attempts or retries. Report: `docs/lite/results/four-family/clef/`. |
| `lite-v1-clef-flash-four-family-retry-v1/` | Cloudflare-hosted Clef Flash through the same native API, recorded 2026-10-02 in one session with identical data, source versions and execution settings except the model selector. All 480 requests succeeded; two timeout attempts recovered through the declared retry policy. Report: `docs/lite/results/four-family/clef-flash/`. |
| `wity-1-{auto,off}-workers16-retry-after-20261003-pass1/` | One complete hosted pass per Wity mode, 480 states each, 16 workers and a 180 s timeout. Auto recovered 26 HTTP 429 rejections and one timeout; off had no failed attempts. [Reports](../docs/lite/results/wity-20261003/README.md). |
| `hosted-api-repeats-20261003/pass{2,3}/<setting>/` | Sixteen additional hosted passes on the same frozen dataset and execution protocol: Astra low, Luna low/none, Terra low/none, Jev, Clef and Clef Flash each have passes 2 and 3. The original fifteen additional passes succeeded without retries; Astra pass 3 retains its own attempt record. The public leaderboard averages these with each original pass. [Per-pass scores and provenance](../docs/lite/results/hosted-api-repeats-20261003/README.md). |
| `pro6000-lab-20261001/runs/<setting>/` | Current self-hosted cohort: nine native BF16 settings on the same RTX PRO 6000 lab host (96 GB), recorded 2026-10-01, with 480 states each. Supersedes the two RunPod cohorts in the public leaderboard. [Settings and deployment details](../docs/lite/results/pro6000-lab-20261001/README.md). |
| `winnow-pro6000-20261003/pass{1,2,3}/{winnow-12b,winnow-e4b}/` | Three BF16 passes per Winnow model on one RunPod RTX PRO 6000 Blackwell Server (96 GB), with a fresh native server per pass. All 2,880 requests succeeded without retries. [Repeated measurements and provenance](../docs/lite/results/winnow-pro6000-20261003/README.md). |
| `decision20-pro6000-20261003/pass{1,2,3}/<setting>/` | Three native BF16-resident passes for each of the six Decision 2.0 models on one RunPod RTX PRO 6000 Blackwell Server (96 GB), with a fresh runtime per pass. All 8,640 requests succeeded without retries; committed answers were identical across the three passes. [Repeated measurements and provenance](../docs/lite/results/decision20-pro6000-20261003/README.md). |
| `runpod-openweight-20260930/runs/{laya-english,laya-typed-decisions,laya-multilingual,djev-diffusiongemma}/` | Four self-hosted BF16 settings on RTX PRO 6000 Blackwell Server (96 GB); each has the same eight frozen scenarios and 480 requests, recorded on 2026-09-30. |
| `runpod-openweight-20260930-round2/runs/{kev-4b,nimble-9b,semif-qwen35-4b}/` | Three self-hosted BF16 native settings on L40S (48 GB), recorded on 2026-09-30; Qwen is a direct-logit baseline. |

Each hosted folder holds `run.json` (configuration, dataset hash, recording times, `events_sha256`), `episodes.json` (the frozen scenarios), `events.jsonl` (every release, request attempt and response; hashed byte for byte, see `.gitattributes`), `metrics.json` and `raw_wallclock_metrics.json`; the part folders and single-session Astra, Clef and Clef Flash folders also keep per-scenario score files (`<episode>.json`, `<episode>.raw_wallclock.json`).

The self-hosted folders expose only `run.json`, `episodes.json` and `events.jsonl`. Their cohorts also expose input audits, native source revisions, prepared weight/config hashes and dependency versions through exact `.gitignore` allowlists. Raw logs and model weights remain local. Recompute from a clone with `uv run --group paper python paper/analysis/lite_openweight.py`; this needs no GPU or API key. Original events and configurations are unchanged.

The Winnow cohort additionally preserves frozen source archives and recorder snapshots.
Recompute its reports with `uv run python scripts/runpod/winnow_report.py`.

The Decision 2.0 cohort preserves the exact benchmark deployment, upstream native
source and license archives, release manifests, dependency versions and per-pass
input audits. Recompute its reports and equal-pass means with
`uv run python scripts/runpod/decision20_report.py`; no GPU or API key is needed.

A new pass needs a fresh `--out` folder (`run` refuses an existing one). Name it outside the `lite-v1-*-retry-v1` pattern unless it should be versioned.

Hosted repeats expose only `run.json`, `episodes.json`, `events.jsonl`, the frozen queue plan and dependency versions through an exact allowlist. Queue state, logs and local source copies remain unversioned. Recompute their reports and equal-pass aggregates with `uv run python paper/analysis/lite_hosted.py --reports`; no API key or model inference is needed.
