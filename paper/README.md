# StreamDecisionBench: Evaluating Decisions in Force on Evolving Language Streams

ACL long paper on StreamDecisionBench (SDB). The benchmark's internal name `lite` appears only in paths and module names (`data/lite/v1`, `analysis/lite_*.py`); the manuscript calls it SDB. `main.tex` holds the paper and `appendix.tex` the appendices. The bibliography is `references.bib`, merged from `bib/part_a.bib` and `bib/part_b.bib` plus entries added during revision; `bib/*_notes.md` record where each entry was verified.

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

Run these from the repository root. They read the frozen data and the recorded runs, and they make no model call or network request.

```bash
# primary log-AUC reports and recorded-cadence diagnostics -> docs/lite/results/four-family/
uv run python paper/analysis/lite_reports.py

# numbers and table bodies -> generated/numbers.tex, generated/tables.tex
uv run python paper/analysis/lite_numbers.py
uv run python paper/analysis/lite_numbers.py --list   # also prints every macro with its source

# figures -> figures/fig_*.pdf (+ local .svg previews, not versioned) and figures/lite_figures_data.json
# matplotlib comes from the `paper` dependency group in pyproject.toml
uv run --group paper python paper/analysis/lite_figures.py

# transition-local errors and fast/slow arbitration -> docs/research/trajectory-value/
# plus generated/trajectory_{numbers,tables}.tex and figures/fig_arbitration.pdf
uv run --group paper python paper/analysis/lite_trajectory_value.py

# seven self-hosted settings and all seven/Terra-none pairs under three policies
# -> docs/research/openweight-hybrids/, generated/openweight_{numbers,tables}.tex
# plus the generated Results section in the root README and a composition figure
uv run --group paper python paper/analysis/lite_openweight.py
```

`lite_numbers.py` does the following:

- It rescores every run from its `events.jsonl` with the benchmark's scorer and network estimator, and requires the published `docs/lite/results/four-family/*/analysis.json` to match.
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
| `main.tex`, `appendix.tex` | Paper and appendices |
| `submission.tex`, `preprint.tex`, `.latexmkrc` | Entry files and latexmk configuration |
| `analysis/lite_numbers.py` | Writes `generated/numbers.tex` (one macro per stated number, each with its source) and `generated/tables.tex` (table bodies) |
| `analysis/lite_figures.py`, `analysis/figstyle.py` | Figures in `figures/`, drawn at ACL print width (column 7.7 cm, text block 16 cm) with no text below 7 pt |
| `analysis/lite_window.py` | The rule that selects the Figure 1 window, shared by both scripts |
| `analysis/lite_reports.py`, `analysis/lite_auc.py`, `analysis/evaluation_policy.json` | Primary log-AUC reports in `docs/lite/results/four-family/` and the declared integration policy |
| `analysis/lite_trajectory_value.py`, `analysis/trajectory_replay.py`, `analysis/trajectory_policy.json` | Transition-local judgment errors and all five Jev/GPT pairs under three arbitration rules; exact log integration between arrival-order crossings; reproducible report in `docs/research/trajectory-value/` |
| `analysis/lite_openweight.py`, `analysis/openweight_policy.json` | Seven self-hosted settings and every local/Terra-none pair under three rules; verified original-clock standalone results, common-clock compositions, generated README tables and reproducible report in `docs/research/openweight-hybrids/` |
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

- Every measured number in the text is a macro from `generated/numbers.tex`. Percentages carry no `%` sign; write `\LunaAuc\%`.
- Differences between models are named so the value is nonnegative, for example `\LunaMinusJevInForce`. If the data change which model is ahead, the macro name changes and the paper fails to compile. The primary score is identified by the `Auc` suffix; `InForce` denotes the fixed 2 s diagnostic.
- Load `generated/numbers.tex` before `generated/tables.tex`. The paper defines the model labels, such as `\LunaLabel`, before loading the tables.
- The inputs are `data/lite/v1` (dataset hash `fdfdd55d…`), `runs/lite-v1-*-retry-v1/` and `docs/lite/results/*/`. Number and figure generation treat these inputs as read only; `lite_reports.py` rebuilds the published analyses from the frozen recordings.
- Each model has one recorded pass, so the text describes differences without significance tests or ranking claims. Network-removed scores always appear with their range and the assumption behind them. Timing ceilings and delay scaling are labelled as counterfactual replays.
- The validity audit was run by LLM agents. It is not human validation.


## Integrated evaluation and recording provenance

`analysis/evaluation_policy.json` declares the primary normalized log-AUC over 1–5 s, plus linear 1–5 s and log 1–3 s / 0.5–5 s sensitivity conditions. Equal multiplicative ranges have equal weight; each family averages scenarios equally, and the macro score averages families equally. `src/streamdecisionbench/lite/interval_scoring.py` integrates scenario fractions on nested grids, refining until all metrics change by at most 0.001 percentage point. This is numerical convergence, not statistical uncertainty.

The aggregation rule was adopted after inspecting the recorded passes, not preregistered. All six hosted and seven self-hosted settings were recorded at 2 s. For Luna low, Luna none, Terra low, Terra none and Jev, the original six scenarios and a disjoint two-scenario presenter pass were recorded in separate sessions and merged; merged artifacts retain both sessions. Astra low was recorded in one session covering all eight scenarios (2026-09-29 16:51–17:07 UTC). No existing response was re-queried or excluded for this evaluation.

Each per-setting `analysis.json` has `auc.primary` and `auc.sensitivity`; `scores` and `network_adjustment` describe fixed 2 s diagnostics. Network-removal methods, ranges and adjusted figures are confined to the appendix. `fig_pace` plots the aggregate curve and the four family curves on log interval axes in one main-text figure; `fig_errortime` integrates the partition with the primary score's weights. `fig_trajectory` illustrates presenter voice control (presenter A) on the 2 s recording-cadence replay: every public ASR change in the window on the shared time axis, quoted where the composed reference decision changes, the reference fields that change, and the decisions in force of Luna low, Terra low and Jev in the error-time classes, with each setting's correct share of the window and two brackets measured at the slide change.

The separate composition reports contain `standalone`, `systems`, `controls` and provenance. `lite_openweight.py` verifies all thirteen original-clock time partitions, validates input audits and published standalone areas, and analytically integrates the seven local/Terra-none pairs under every existing rule. Its self-hosted inputs are exposed through exact file allowlists in `runs/`; no GPU or model runtime is needed. `fig_openweight_hybrids` and the full local tables are in the appendix.

To rebuild a merged recording (the five merged settings) in a fresh directory:

```sh
uv run python -m streamdecisionbench.lite merge --data data/lite/v1 \
  --runs runs/lite-v1-<setting>-retry-v1 \
         runs/lite-v1-<setting>-presenter-retry-v1 \
  --out runs/<fresh-merged-dir>
uv run python scripts/lite/lite_report.py --run runs/<fresh-merged-dir> \
  --out /tmp/sdb-<setting>-report
```

The generic report command above writes recording-cadence diagnostics to a scratch folder; do not point it at `docs/lite/results/four-family/`, whose reports it would overwrite. Run `paper/analysis/lite_reports.py` to produce the complete primary AUC report for all six frozen settings.
