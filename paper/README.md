# StreamDecisionBench: Evaluating Decisions in Force on Evolving Language Streams

ACL long paper on StreamDecisionBench (SDB). The benchmark's internal name `lite` appears only in paths and module names (`data/lite/v1`, `analysis/lite_*.py`); the manuscript calls it SDB. `main.tex` holds the paper and `appendix.tex` the appendices. The bibliography is `references.bib`, merged from `bib/part_a.bib` and `bib/part_b.bib` plus entries added during revision; `bib/*_notes.md` record where each entry was verified.

The manuscript's main analyses cover six hosted settings and nine same-host open-weight settings.
Its appendix "Hosted Settings Recorded Later" adds the seven hosted settings first recorded afterwards
with three complete passes under the same protocol (Perplexity Decider v1 27B, GLiDE, GPT-6-Luna
through the Decisions API, Clef, Clef Flash, Claude Haiku 5.5 low and thinking off), with
standalone results and compositions under the hosted rule. Wity-1 (one pass at 16 workers) and
self-hosted cohorts on other hosts appear only on the public leaderboard. See the
[documentation index](../docs/README.md) for current and historical cohorts.

## Build

```bash
cd paper
latexmk      # pdflatex + bibtex; builds submission.pdf and preprint.pdf, auxiliary files go to build/
latexmk -c   # remove auxiliary files
```

Both PDFs come from `main.tex`; the two entry files only set its `acl` option through `\SDBVersion`:

- `submission.tex` → `submission.pdf`: the anonymous review version (`review`: line numbers, the author block replaced by "Anonymous ACL submission").
- `preprint.tex` → `preprint.pdf`: the non-anonymous preprint (`preprint`: authors and page numbers, no line numbers).

Building `main.tex` on its own gives the review version. The built PDFs are not versioned (`.gitignore`); rebuild them after every change. `.latexmkrc` sets the build directory, the two default targets and non-stop mode. The main text ends on page 8 in both versions; Limitations, Ethics, references and the appendices follow.

For the camera-ready version, add an entry file that sets `\SDBVersion` to `final`, and add the acknowledgements. The author block is already in `main.tex`. The decision model's provider and interface are set once in `main.tex` (`\JevProvider`, `\JevInterface`); the reproduction commands in the Reproducibility appendix name the provider flag verbatim. Any relationship between the authors and a model vendor belongs in the submission form's conflict-of-interest declaration.

## Regenerate numbers, tables and figures

Run these from the repository root. They read frozen data and all three recorded passes per
manuscript setting, and make no model call or network request.

```bash
# Verify all passes; regenerate manuscript evidence, numbers, tables and figures.
uv run --group paper python paper/analysis/lite_repeated.py

# Regenerate only number/table macros from the verified three-pass manifest.
uv run python paper/analysis/lite_numbers.py
uv run python paper/analysis/lite_numbers.py --list

# Later hosted settings: docs/research/later-hosted/analysis.json and generated/later_*.tex.
uv run python paper/analysis/lite_later.py
```

The manifest is `docs/research/manuscript-three-pass/analysis.json`. Individual runs and
reports remain immutable inputs. Single-model statistics average independently evaluated
passes; composition pairs matching pass indices before averaging. Figure 1 and the detailed
stale-override example retain pass 1 and are labelled accordingly. The public composition
report commands do not overwrite manuscript tables or figures.

`lite_numbers.py` does the following:

- It rescores every run from its `events.jsonl` with the benchmark's scorer and network estimator, and requires each corresponding published `docs/lite/results/*/analysis.json` to match.
- It recomputes the remaining statistics independently.
- It re-runs the executable reference on all 480 states.
- It computes the counterfactual replays with the benchmark's replay scorer: the timing ceiling (reference answers replayed with each model's recorded delays) and the delay-scaling table (every recorded delay multiplied by 0.5, 2/3, 1.5 or 2).
- It recomputes the Figure 1 window with the rule in `lite_window.py`.
- It derives the audit counts from `notes/audit_record.json`.
- It regenerates `notes/FACTS.md` from verified results; the historical six-scenario audit remains a separate input in `notes/audit_summary.md`.

If any check fails, the script lists every failure and does not publish new number or table macros. `lite_figures.py` also checks its inputs before plotting and fails if the scores disagree with the frozen events. Both scripts produce byte-identical output when run again.

## Layout

| Path | Content |
| --- | --- |
| `main.tex`, `appendix.tex`, `model-provenance.tex` | Paper, appendices and the pinned self-hosted model provenance table |
| `submission.tex`, `preprint.tex`, `.latexmkrc` | Entry files and latexmk configuration |
| `analysis/lite_later.py`, `analysis/later_policy.json` | Later hosted settings: standalone three-pass means checked against independent integrations, compositions of fast decision interfaces with the five GPT correctors under the hosted rule, and weighting sensitivity of the headline systems; writes `generated/later_numbers.tex` and `generated/later_tables.tex` |
| `analysis/lite_repeated.py` | Three-pass manuscript manifest, matching-index compositions, all six pass-matchings for the headline pairs, field agreement analysis, and regeneration entry point; writes `generated/summary_tables.tex` |
| `analysis/lite_numbers.py` | Writes `generated/numbers.tex` (one macro per stated number, each with its source) and `generated/tables.tex` (table bodies) |
| `analysis/lite_figures.py`, `analysis/figstyle.py` | Figures in `figures/`, drawn at ACL print width (column 7.7 cm, text block 16 cm) with no text below 7 pt |
| `analysis/lite_window.py` | The rule that selects the Figure 1 window, shared by both scripts |
| `analysis/lite_reports.py`, `analysis/lite_auc.py`, `analysis/evaluation_policy.json` | Primary log-AUC reports in `docs/lite/results/four-family/` and the declared integration policy |
| `analysis/lite_trajectory_value.py`, `analysis/trajectory_replay.py`, `analysis/trajectory_policy.json` | Transition-local judgment errors and all five Jev/GPT pairs under three arbitration rules; exact log integration between arrival-order crossings; reproducible report in `docs/research/trajectory-value/` |
| `analysis/lite_openweight.py`, `analysis/openweight_policy.json` | Nine self-hosted settings and every local/Terra-none pair under three rules; verified original-clock standalone results, common-clock compositions, generated README tables and reproducible report in `docs/research/openweight-hybrids/` |
| `generated/` | Generated macros and table bodies. Do not edit these by hand |
| `figures/` | Main text: `fig_trajectory` (Figure 1, full width), `fig_errortime` (column width) and `fig_pace` (full width, one row of five panels: all families, then each family). Appendix: `fig_map`, `fig_latency` and `fig_separability`. Each is a vector PDF (the LaTeX input, versioned) with a local SVG preview that is not versioned; `lite_figures_data.json` holds every plotted value and the window scan |
| `notes/FACTS.md` | Fact sheet for the standalone measurements, with source provenance; the composition and transition-local measurements are in `docs/research/trajectory-value/` and `generated/trajectory_numbers.tex` |
| `notes/audit_record.json` | Extract of the LLM-agent validity audit: every check with its reported agreement and every grouped finding with its adjudication votes |
| `notes/audit_presenter_record.json` | Record of the LLM-agent checks of the two presenter scenarios (2026-09-29, three rounds, with the fixes made between rounds); the paper's audit numbers come from `audit_record.json` and cover the original six scenarios only |
| `notes/audit_summary.md`, `notes/pricing.md`, `notes/latency_grounding.md`, `notes/terminology_audit.md` | Historical six-scenario audit summary (an input of `lite_numbers.py`), the list prices behind the cost rows, and working notes on latency literature and terminology |
| `bib/` | Bibliography parts and verification notes (`part_c_notes.md` covers the entries added during revision) |
| `bib/sources/` | Retrieved BibTeX, metadata and quotes used to verify entries |
| `template/` | Unmodified ACL template and formatting guide |
| `legacy/` | Archived earlier draft, kept locally and not versioned. It is not in active use, and its results are not cited |

## Evidence rules

- Every measured number in the text is a macro from `generated/`. Percentages carry no `%` sign; write `\LunaAuc\%`.
- Differences between models are named so the value is nonnegative, for example `\LunaMinusJevInForce`. If the data change which model is ahead, the macro name changes and the paper fails to compile. The primary score is identified by the `Auc` suffix; `InForce` denotes the fixed 2 s diagnostic.
- Load `generated/numbers.tex` before `generated/tables.tex`. The paper defines the model labels, such as `\LunaLabel`, before loading the tables.
- The inputs are `data/lite/v1` (dataset hash `fdfdd55d…`), `runs/lite-v1-*-retry-v1/` and `docs/lite/results/*/`. Number and figure generation treat these inputs as read only; `lite_reports.py` rebuilds the published analyses from the frozen recordings.
- All manuscript settings average three independently evaluated passes; compositions pair matching pass indices. Latency summaries average per-pass quantiles. Comparisons remain descriptive. Scores after removing the fitted non-token remainder always appear with their range and assumptions; the intercept is not an identified network delay or a guaranteed bound. Timing ceilings and delay scaling are labelled as counterfactual replays.
- The validity audit was run by LLM agents. It is not human validation.


## Integrated evaluation and recording provenance

`analysis/evaluation_policy.json` declares the primary normalized log-AUC over 0.5–8 s, plus linear 0.5–8 s and the five other log ranges formed by lower bounds 0.1, 0.5 and 1 s and upper bounds 4 and 8 s. Equal multiplicative ranges have equal weight; each family averages scenarios equally, and the macro score averages families equally. `src/streamdecisionbench/lite/interval_scoring.py` integrates scenario fractions on nested grids, refining until all metrics change by at most 0.001 percentage point. This is numerical convergence, not statistical uncertainty.

The aggregation rule was adopted after inspecting the recorded passes, not preregistered. All six manuscript hosted and nine self-hosted settings were recorded at 2 s. In pass 1 of Luna low, Luna none, Terra low, Terra none and Jev, the original six scenarios and a disjoint two-scenario presenter pass were recorded in separate sessions and merged; merged artifacts retain both sessions. Each repeat covers all eight scenarios in one session. Astra low pass 1 was recorded in one session covering all eight scenarios (2026-09-29 16:51–17:07 UTC). All seven later hosted settings (appendix "Hosted Settings Recorded Later", including Clef and Clef Flash) also use complete eight-scenario passes at 2 s. All three complete passes are evaluated without excluding valid responses.

Each per-setting `analysis.json` has `auc.primary` and `auc.sensitivity`; `scores` and `network_adjustment` describe fixed 2 s diagnostics. The fitted-remainder analysis, its uncertainty ranges and adjusted figures are confined to the appendix. `fig_pace` plots the aggregate curve and the four family curves on log interval axes in one main-text figure; `fig_errortime` integrates the partition with the primary score's weights. `fig_trajectory` illustrates presenter voice control (presenter A) on the 2 s recording-cadence replay: every public ASR change in the window on the shared time axis, quoted where the composed reference decision changes, the reference fields that change, and the decisions in force of Luna low, Terra low and Jev in the error-time classes, with each setting's correct share of the window and two brackets measured at the slide change.

The separate composition reports contain `standalone`, `systems`, `controls` and provenance. `lite_openweight.py` verifies all registered public settings' original-clock time partitions, validates input audits and published standalone areas, and analytically integrates the nine local/Terra-none pairs under every existing rule. Its self-hosted inputs are exposed through exact file allowlists in `runs/`; no GPU or model runtime is needed. `fig_openweight_hybrids` and the full local tables are in the appendix.

To rebuild a merged recording (the five merged settings) in a fresh directory:

```sh
uv run python -m streamdecisionbench.lite merge --data data/lite/v1 \
  --runs runs/lite-v1-<setting>-retry-v1 \
         runs/lite-v1-<setting>-presenter-retry-v1 \
  --out runs/<fresh-merged-dir>
uv run python scripts/lite/lite_report.py --run runs/<fresh-merged-dir> \
  --out /tmp/sdb-<setting>-report
```

The generic report command above writes recording-cadence diagnostics to a scratch folder; do not point it at `docs/lite/results/four-family/`, whose reports it would overwrite. Run `paper/analysis/lite_reports.py` to produce the complete primary AUC reports for all registered public settings.

## Anonymous review artifacts

After regenerating the manuscript, build the manuscript-scoped review copies with:

```sh
uv run --group paper python scripts/paper/build_submission.py \
  --out output/submission-2026-10-10 --reproduce --latex
```

The builder preserves the original research evidence, checks the manuscript input
closure, redacts identifying metadata in copies and propagates their SHA-256 receipts.
It produces separate `software.zip` and `data.zip` archives below the ARR size
limit. `--reproduce` extracts and verifies the actual archives, blocks network
access during analysis, and checks that regeneration preserves the manuscript's
rendered values. `--latex` compiles those anonymous sources and exports
`submission.pdf`. Use a fresh output directory for a new verification run.
The review artifact's README describes its exact contents and the metadata
redactions; author-only submission notes must remain outside both archives.
