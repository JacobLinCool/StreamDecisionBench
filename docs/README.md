# Documentation

Start with the [project README](../README.md) for installation, credentials, a new model run, and the combined leaderboard. The current benchmark is named SDB; “lite” is its internal module and directory name.

## Current benchmark contract

| Document | Purpose |
|---|---|
| [Protocol](lite/PROTOCOL.md) | Public inputs, composed decisions, request execution, transport retries, acceptance, clocks, and primary log-AUC scoring. This is the authoritative evaluation contract. |
| [IDE debugging](lite/debugging.md) | Debugging state and next-action rules. |
| [Assembly](lite/assembly.md) | Procedural guidance, scans, prerequisites, and recovery rules. |
| [Support workflows](lite/support.md) | Recorder, service, hold, and delivery branches. |
| [Presenter voice control](lite/presenter.md) | Slide advance, clip pause, and captions-source routing under revised transcript evidence. |

The frozen [dataset manifest](../data/lite/v1/manifest.json) identifies eight scenarios, two per family, with 60 states each. A complete pass covers 480 states. Task documents explain the rules; versioned episodes and executable references define the exact evaluated states and answers.

## Published results and figures

| Document | Status and scope |
|---|---|
| [Results index](lite/results/README.md) | Entry point for current cohorts and retained historical evidence. |
| [Hosted API results](lite/results/four-family/README.md) | Fifteen complete settings, including Claude Haiku 5.5 low and thinking off, GPT-6-Luna (Decisions API), GLiDE (Fastino), Perplexity, Wity auto/off, Cloudflare Clef and Clef Flash. The manuscript's hosted subset contains six settings. |
| [RTX PRO 6000 lab results](lite/results/pro6000-lab-20261001/README.md) | Nine open-weight settings recorded on the same host; the current public and manuscript self-hosted cohort. |
| [README figures](figures/README.md) | Provenance and reproduction of the combined 30-setting leaderboard and interval curves. |
| [Run index](../runs/README.md) | Frozen recording paths, manifests, episode coverage, and recorded configurations. |

Wity auto/off each have one recorded pass; all other registered settings have three. Hosted APIs and local GPU deployments have different latency paths; the combined leaderboard describes those deployments rather than isolating model architecture or hardware effects. Per-setting reports link original runs and analysis JSON. Recording-cadence and secondary network estimates remain separate from the primary log-AUC.

## Design and research

| Document | Status and purpose |
|---|---|
| [Design rationale](MINIMAL_DESIGN.md) | Nine scoped conditions, deletion witnesses, and proposed acceptance audits. Held-out shortcut resistance is an unverified criterion, not a completed result. |
| [Literature catalog](LITERATURE.md) | Bounded reading set: 39 research papers and 3 official technical articles, with explicit relationships to SDB. Source audit dated 2026-09-27. |
| [Trajectory analysis](research/trajectory-value/README.md) | Diagnostics for the six hosted manuscript settings and all five Jev/GPT pairs, separating answer quality, update timing, and error duration. The [reviewer response](research/trajectory-value/reviewer-response.md) explains the measurement's additional information. This analysis does not include the later Cloudflare settings. |
| [Open-weight and hybrid analysis](research/openweight-hybrids/README.md) | Frozen single-model results and derived hybrid replay analyses, with deployment and counterfactual assumptions. Hybrid replays are separate from the single-model leaderboard. |
| [Reference-interval evidence review](research/reference-intervals/README.md) | Historical proposal dated 2026-09-29. Candidate family-specific points are not the adopted evaluation policy. Includes [assembly source extraction](research/reference-intervals/assembly-evidence.md) and a reproducible synthetic timeline audit. |

Research proposals do not override the protocol. Retiming recorded answers is conditional on the stated replay assumptions and is not a measurement of a new online request load.

## Historical evidence still used

The [original three-family reports](lite/results/README.md#original-three-family-recordings) retain the six-scenario recordings later combined with presenter passes. Their fixed-cadence scores are historical diagnostics, not current four-family ranks.

The earlier [RunPod RTX PRO 6000 cohort](lite/results/runpod-openweight-20260930/README.md) and [RunPod L40S cohort](lite/results/runpod-openweight-20260930-round2/README.md) preserve native-runtime provenance, input audits, deployment measurements, and specific error witnesses. They are superseded in the leaderboard by the lab cohort, but remain useful evidence for how the recorders were prepared. Compare hardware-dependent measurements only with their deployment labels.

The retired CLI guide and completed research work plan are local archives under the ignored legacy directory. They are not part of the current public instructions.

## Rebuilding documentation

Run commands from the repository root. None of these analysis or rendering commands queries a model.

| Output | Owner / reproduction |
|---|---|
| Current per-setting reports and cohort score tables | `uv run python paper/analysis/lite_reports.py` |
| Recording-cadence diagnostics for a frozen run | `uv run python scripts/lite/lite_report.py --run <frozen-run> --out /tmp/sdb-report` |
| Matched frozen-run comparison | `uv run python scripts/lite/lite_compare.py --help` describes the two input runs and output directory. Use a scratch output when inspecting historical recordings. |
| Trajectory analysis | `uv run --group paper python paper/analysis/lite_trajectory_value.py`; see its report for artifacts and assumptions. |
| Open-weight/hybrid analysis | `uv run python paper/analysis/lite_openweight.py` |
| README figures | Follow the pinned ECharts pipeline in the [figure guide](figures/README.md). |
| Results website | `python3 site/build.py --out /tmp/sdb-site` |
| Reference-change timeline audit | `uv run python docs/research/reference-intervals/timeline_audit.py` |

The [paper guide](../paper/README.md) owns manuscript figures, numeric macros, and PDF reproduction. Historical infrastructure summaries can depend on additional local provisioning/billing records; the public frozen events, configuration, episodes, and report analyses are the evidence used for score reproduction.

## Language and maintenance

Public documentation and generated reports are English. Original Traditional Chinese versions are preserved locally as sibling `*.zh-tw.md` files and excluded by Git. They are archives, not a second maintained public documentation set.

When changing the protocol, update its task documents and reproduction instructions together. Label unadopted proposals and historical cohorts explicitly, keep frozen evidence intact, and link only files available in a clean checkout. Documentation tests enforce the language and local-link rules.
