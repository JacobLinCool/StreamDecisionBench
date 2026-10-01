"""Figures for the SDB Lite paper, computed from the recorded runs and their analyses.

Regenerate (no API calls, no network):

    uv run --group paper python paper/analysis/lite_figures.py

Inputs (read only):
  runs/lite-v1-*-retry-v1/{run.json,episodes.json,events.jsonl}  recorded passes
  docs/lite/results/*/analysis.json                               scored summaries
  data/lite/v1/lite_presenter_a.json                              slide names (Figure 1 check)
  scripts/lite/network.py                                         lower-envelope fit

Outputs: paper/figures/fig_{trajectory,errortime,pace}.{pdf,svg} (main text),
fig_{map,latency,separability}.{pdf,svg} (appendix) and paper/figures/lite_figures_data.json,
which records every plotted value.
Widths are the ACL layout's (one column 7.7 cm, text block 16 cm; see figstyle).
"""

from __future__ import annotations

import json
import sys

sys.dont_write_bytecode = True  # imports src/ and scripts/ read-only; leave no bytecode behind
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "scripts" / "lite"))
sys.path.insert(0, str(ROOT / "src"))

import matplotlib as mpl  # noqa: E402
from matplotlib.legend_handler import HandlerTuple  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.transforms as mtransforms  # noqa: E402

from figstyle import COLUMN, PALETTE, TEXT, panel_labels, save, use_style  # noqa: E402
from lite_window import scan as window_scan  # noqa: E402
from network import _received_s, fit  # noqa: E402
from streamdecisionbench.lite.__main__ import rescore_run  # noqa: E402
from streamdecisionbench.lite.core import compose  # noqa: E402
from streamdecisionbench.lite.retry_scoring import normalized_episode_scores
from streamdecisionbench.lite.reference_scoring import family_mean
from lite_numbers import POLICY  # noqa: E402

OUT = ROOT / "paper" / "figures"


@dataclass(frozen=True)
class Model:
    key: str
    name: str
    run: str
    results: str


# Fixed order everywhere, the same as the paper's tables (lite_numbers.MODELS): the GPT settings
# together (each GPT-5.6 model at low then no reasoning, then GPT-6 Astra at low), then Jev.
MODELS = [
    Model("luna", "Luna low", "lite-v1-gpt-5.6-luna-low-four-family-retry-v1", "four-family/gpt-5.6-luna-low"),
    Model("luna_none", "Luna none", "lite-v1-gpt-5.6-luna-none-four-family-retry-v1", "four-family/gpt-5.6-luna-none"),
    Model("terra", "Terra low", "lite-v1-gpt-5.6-terra-low-four-family-retry-v1", "four-family/gpt-5.6-terra-low"),
    Model("terra_none", "Terra none", "lite-v1-gpt-5.6-terra-none-four-family-retry-v1", "four-family/gpt-5.6-terra-none"),
    Model("astra", "Astra low", "lite-v1-gpt-6-astra-low-four-family-retry-v1", "four-family/gpt-6-astra-low"),
    Model("jev", "Jev", "lite-v1-jev-latest-four-family-retry-v1", "four-family/jev-latest"),
]
# Figure 1 keeps the three settings its window rule was defined for.
TRAJ_MODELS = [m for m in MODELS if m.key in ("luna", "terra", "jev")]
# No figure text is smaller than this (pt); figures are included at 100% scale.
SMALL = 7
FAMILIES = [
    ("live_debugging", "IDE debugging"),
    ("procedural_coaching", "Assembly station"),
    ("support_call_assist", "Support call"),
    ("presenter_voice_control", "Presenter control"),
]

# The timing-by-judgment partition of the benchmark scorer (scoring.episode_scores), shared by
# Figures 1 and 2 in this order. Hue and hatch both separate the classes, so they survive
# colour-vision deficiency and greyscale print. Compound errors carry a darker judgment colour
# with the stale hatch, since both conditions hold. "text" is the colour of a value printed on
# the class; "gloss" is the paper's definition, which Figure 1's legend carries because it is
# read before the definitions.
PARTITION_KINDS = {
    "correct": {"label": "Correct", "face": "#D3E4F1", "hatch": None, "ink": None, "text": "black",
                "gloss": "Correct"},
    "judgment": {"label": "Judgment", "face": PALETTE["red"], "hatch": "xxxx", "ink": "#3A1400", "text": "black",
                 "gloss": "Judgment (current source, wrong)"},
    "compound": {"label": "Compound", "face": "#8A3300", "hatch": "////", "ink": "#F2C38B", "text": "white",
                 "gloss": "Compound (both)"},
    "stale": {"label": "Stale", "face": PALETTE["orange"], "hatch": "////", "ink": "#4A3200", "text": "black",
              "gloss": "Stale (outdated source, right for it)"},
    "no_decision": {"label": "No decision", "face": "#4D4D4D", "hatch": None, "ink": None, "text": "white",
                    "gloss": "No decision"},
}
PARTITION_ORDER = list(PARTITION_KINDS)


def partition_patch(kind: str, label: str | None = None) -> Patch:
    """A legend patch for a partition class. The edge takes the face colour at zero width, so
    the PDF shows the hatch (an edgeless patch leaves a hairline or loses the hatch)."""
    style = PARTITION_KINDS[kind]
    return Patch(facecolor=style["face"], hatch=style["hatch"], hatchcolor=style["ink"] or style["face"],
                 edgecolor=style["face"], linewidth=0, label=label or style["label"])

# ---------------------------------------------------------------- loading


def load() -> dict:
    data = {}
    for model in MODELS:
        analysis = json.loads((ROOT / "docs/lite/results" / model.results / "analysis.json").read_text())
        run = rescore_run(ROOT / "runs" / model.run)
        if analysis["events_sha256"] != run["frozen"]["events_sha256"]:
            raise ValueError(f"{model.key}: analysis.json does not describe the recorded events")
        if analysis["evaluation_policy"] != POLICY:
            raise ValueError(f"{model.key}: regenerate the report for the declared evaluation policy")
        import hashlib
        auc = analysis["auc"]
        if auc["events_sha256"] != run["frozen"]["events_sha256"]:
            raise ValueError("AUC describes another recording")
        # The AUC's source digests are provenance: they are recorded with the figures, and a
        # later edit of a source is reported, not treated as invalidating the recorded analysis.
        for path, digest in auc["sources_sha256"].items():
            if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest:
                print(f"note: {model.key}: {path} changed after its AUC was computed", file=sys.stderr)
        evaluated = run
        saved, current = analysis["scores"]["per_episode"], evaluated["scores"]["per_episode"]
        if [s["episode_id"] for s in saved] != [s["episode_id"] for s in current]:
            raise ValueError(f"{model.key}: report scenario coverage disagrees with the run")
        for a, b in zip(saved, current):
            fields = ("time_accuracy", "untimed_decision_accuracy", "current_source_share")
            if not np.allclose([a[k] for k in fields], [b[k] for k in fields], rtol=0, atol=1e-12):
                raise ValueError(f"{model.key}/{a['episode_id']}: report disagrees with reference replay")
        data[model.key] = {"analysis": analysis, "recorded": run, "run": evaluated}
    return data


def window_check(data: dict) -> dict:
    intervals = {m.key: {row["episode_id"]: row["intervals"] for row in data[m.key]["run"]["scores"]["per_episode"]}
                 for m in TRAJ_MODELS}
    overall = {m.key: data[m.key]["analysis"]["scores"]["overall"]["time_accuracy"] for m in TRAJ_MODELS}
    episode = next(e for e in data[TRAJ_MODELS[0].key]["run"]["episodes"] if e["episode_id"] == "lite_presenter_a")
    return window_scan(intervals, overall, [episode["episode_id"]], episode["tick_seconds"],
                       len(episode["steps"]) * episode["tick_seconds"])


def _request_rows(run: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Time before receipt, uncached input tokens and output tokens, in network.py's order."""
    rows = [r for e in run["episodes"] for r in sorted(run["responses"][e["episode_id"]], key=lambda r: r["t"])]
    usage = [r.get("usage") or {} for r in rows]
    y = np.array([_received_s(r) for r in rows])
    uncached = np.array([u.get("input_tokens", 0) - (u.get("cached_tokens") or 0) for u in usage], float)
    output = np.array([u.get("output_tokens", 0) for u in usage], float)
    return y, uncached, output


# ------------------------------------------------------- figure 1: trajectory


def _merge(intervals: list[dict], start: float, end: float) -> list[dict]:
    """Clip scored intervals to the window and merge contiguous runs of one kind."""
    runs = []
    for iv in intervals:
        a, b = max(iv["start_s"], start), min(iv["end_s"], end)
        if b <= a:
            continue
        if runs and runs[-1]["kind"] == iv["kind"] and abs(runs[-1]["end"] - a) < 1e-9:
            runs[-1]["end"] = b
            runs[-1]["parts"].append(iv)
        else:
            runs.append({"kind": iv["kind"], "start": a, "end": b, "parts": [iv]})
    return runs


def partition_class(part: dict, gold: list[dict]) -> str:
    """scoring.episode_scores' timing-by-judgment class of one scored interval.

    `gold` holds the composed reference decision of every time step. The source is current
    when its reference decision equals the one in force at the interval's own time step; the
    class never compares time-step indices, since two steps can share a reference decision."""
    if part["kind"] == "no_decision":
        return "no_decision"
    current = gold[part["source_t"]] == gold[part["reference_t"]]
    if part["kind"] == "correct":
        return "correct"  # current-correct and lucky time both count as correct
    if part["kind"] == "source_correct":
        if current:
            raise ValueError("a decision right for a current source cannot be an error")
        return "stale"
    return "judgment" if current else "compound"


def _class_runs(intervals: list[dict], gold: list[dict], start: float, end: float) -> list[dict]:
    """Scored intervals clipped to the window, as contiguous runs of one partition class."""
    runs = []
    for iv in intervals:
        a, b = max(iv["start_s"], start), min(iv["end_s"], end)
        if b <= a:
            continue
        kind = partition_class(iv, gold)
        if runs and runs[-1]["class"] == kind and abs(runs[-1]["end"] - a) < 1e-9:
            runs[-1]["end"] = b
            runs[-1]["parts"].append(iv)
        else:
            runs.append({"class": kind, "start": a, "end": b, "parts": [iv]})
    return runs


# Reference fields in Figure 1's row order. A field gets a row only when its value changes
# inside the window; every composed change must alter at least one shown field.
TRAJ_FIELDS = [("host_cue", "Chair cue"), ("slide", "Slide"), ("captions", "Caption source"),
               ("mode", "Mode"), ("clip_state", "Clip"), ("question_card", "Question card")]
TRAJ_DASH = {"color": "#6F6F6F", "dashes": (2.2, 1.8), "linewidth": 0.55}
TRAJ_MARK = {"marker": "o", "markersize": 4.2, "markeredgewidth": 0.9, "markeredgecolor": "black",
             "linestyle": "none"}
UTTERANCE_INK = "#555555"
# Reference cells are white with a grey outline, so in greyscale they stay apart from the
# light Correct fill of the model rows.
REF_EDGE = "#8C8C8C"
QUOTE_GAP, QUOTE_CLEAR = 0.12, 0.22  # quote offset from its leader; clearance before an obstacle (s)


def _fit_quote(text: str, room_px: float, width_px) -> str:
    """The verbatim quote, or its shortest leading elision (marked by an ellipsis) that fits."""
    words = text.split()
    for k in range(len(words)):
        shown = ("“" if k == 0 else "“…") + " ".join(words[k:]) + "”"
        if width_px(shown) <= room_px:
            return shown
    raise ValueError(f"no room for the quote {text!r}")


def fig_trajectory(data: dict) -> dict:
    """Presenter A's selected window: public ASR evidence, the composed reference decision and
    three recorded decisions in force, on one axis of time at the 2 s recording cadence.

    Evidence rule: every transcript change in the window is a marker at its time step on its
    speaker's row (hollow = partial hypothesis, filled = final text), and a line joins the
    changes of one utterance. A change is quoted exactly when the composed reference decision
    changes at its time step. Presenter quotes alternate between two rows above the markers and
    hang from a leader at their time; another speaker's quote sits on a row above both, ending
    at its leader. A quote is verbatim and loses leading words (marked by an ellipsis) only when
    it would otherwise come within QUOTE_CLEAR of a leader that crosses its row.
    """
    selection = window_check(data)
    chosen = selection["chosen"]
    eid, start, end = chosen["episode"], chosen["start"], chosen["end"]
    lead = TRAJ_MODELS[0]
    episode = next(e for e in data[lead.key]["run"]["episodes"] if e["episode_id"] == eid)
    tick = episode["tick_seconds"]
    if [st["t"] for st in episode["steps"]] != list(range(len(episode["steps"]))):
        raise ValueError("Figure 1 needs one state per time step")
    rows = [{"time_s": st["t"] * tick, "decision": compose(episode["decision_spec"], st["gold"])}
            for st in episode["steps"]]
    gold = [r["decision"] for r in rows]
    changes = [r["time_s"] for i, r in enumerate(rows) if i and r["decision"] != rows[i-1]["decision"]
               and start <= r["time_s"] < end]
    events, previous = [], {}
    for st in episode["steps"]:
        for utterance in st["state"]["transcript"]:
            uid = utterance["utterance_id"]
            if start <= st["t"] * tick < end and previous.get(uid) != utterance:
                events.append({"time_s": st["t"] * tick, **utterance})
            previous[uid] = utterance

    # Slide names come from the scenario's own slide criteria ("s7: Slide 7: demo (has a clip)"),
    # as recorded with the run and as frozen in the dataset.
    criteria = episode["questions"]["slide"]["criteria"]
    frozen_path = f"data/lite/v1/{eid}.json"
    if json.loads((ROOT / frozen_path).read_text())["questions"]["slide"]["criteria"] != criteria:
        raise ValueError("the run's slide criteria differ from the frozen scenario")
    slide_names = {}
    for text in criteria.values():
        key, description = text.split(": ", 1)
        number, name = description.split(": ", 1)
        slide_names[key] = f"{number.split()[-1]}: {name.split(' (')[0]}"

    def value_label(field: str, value) -> str:
        if field == "slide":
            return slide_names[value]
        return {"stand_by": "stand-by"}.get(value, str(value).replace("_", " "))

    window_rows = [r for r in rows if start <= r["time_s"] < end]
    fields = [(f, name) for f, name in TRAJ_FIELDS
              if len({json.dumps(r["decision"].get(f)) for r in window_rows}) > 1]
    for t in changes:
        i = round(t / tick)
        if not any(gold[i].get(f) != gold[i - 1].get(f) for f, _ in fields):
            raise ValueError(f"the reference change at {t} s alters no shown field")

    # Decisions in force, in Figure 2's classes; the correct share must be the window rule's.
    classes, plotted = {}, {}
    for model in TRAJ_MODELS:
        score = next(r for r in data[model.key]["run"]["scores"]["per_episode"] if r["episode_id"] == eid)
        plotted[model.key] = _merge(score["intervals"], start, end)
        classes[model.key] = _class_runs(score["intervals"], gold, start, end)
        share = sum(r["end"] - r["start"] for r in classes[model.key] if r["class"] == "correct") / (end - start)
        if abs(share - chosen["share"][model.key]) > 1e-9:
            raise ValueError(f"{model.key}: plotted correct share differs from the window rule")
    present = [k for k in PARTITION_ORDER if any(r["class"] == k for runs in classes.values() for r in runs)]

    # The two brackets at the first slide change: the first model's stale span and Jev's
    # judgment span, with values measured from the scored intervals.
    slide_t = next(t for t in changes if gold[round(t / tick)]["slide"] != gold[round(t / tick) - 1]["slide"])
    old_slide, new_slide = gold[round(slide_t / tick) - 1]["slide"], gold[round(slide_t / tick)]["slide"]
    old_number = slide_names[old_slide].split(":")[0]
    stale_run = next(r for r in classes[lead.key] if r["start"] >= slide_t - 1e-9)
    if stale_run["class"] != "stale" or stale_run["start"] - slide_t >= tick:
        raise ValueError("the first model's decision after the slide change is not stale")
    if any(gold[p["source_t"]]["slide"] != old_slide or gold[p["reference_t"]]["slide"] != new_slide
           for p in stale_run["parts"]):
        raise ValueError("the stale span does not keep the previous slide in force")
    jev = next(m for m in TRAJ_MODELS if m.key == "jev")
    after = [r for r in classes[jev.key] if slide_t - 1e-9 <= r["start"] < slide_t + tick]
    judgment_run = next(r for r in after if r["class"] == "judgment")
    if any(r["class"] != "stale" for r in after[:after.index(judgment_run)]):
        raise ValueError("Jev's judgment span does not follow its previous decision")
    sources = {p["source_t"] for p in judgment_run["parts"]}
    if sources != {round(slide_t / tick)}:
        raise ValueError("Jev's judgment span must answer the state that changed the slide")
    response = next(r for r in data[jev.key]["run"]["responses"][eid] if r["t"] == round(slide_t / tick))
    predicted = compose(episode["decision_spec"], response["pred"])
    if predicted["slide"] != old_slide:
        raise ValueError("Jev's judgment span does not keep the previous slide")
    brackets = {
        "change_s": slide_t, "field": "slide", "reference_before": old_slide, "reference_after": new_slide,
        "stale": {"model": lead.key, "start_s": stale_run["start"], "end_s": stale_run["end"],
                  "in_force_after_change_s": stale_run["end"] - slide_t, "slide_in_force": old_slide},
        "judgment": {"model": jev.key, "start_s": judgment_run["start"], "end_s": judgment_run["end"],
                     "takes_force_after_change_s": judgment_run["start"] - slide_t,
                     "source_t": round(slide_t / tick), "predicted_slide": predicted["slide"]},
    }
    brackets["stale"]["label"] = (f"stale: slide {old_number} in force "
                                  f"{brackets['stale']['in_force_after_change_s']:.1f} s")
    brackets["judgment"]["label"] = (f"judgment: new answer after "
                                     f"{brackets['judgment']['takes_force_after_change_s']:.2f} s, "
                                     f"still slide {old_number}")

    # ------------------------------------------------ rows (data units, y grows downward)
    quote_y = {"top": 0.0, "upper": 0.7, "lower": 1.4}
    depth = {"top": 0, "upper": 1, "lower": 2}  # a leader to row r crosses every deeper row
    speakers = [s for s in ("Presenter", "Host", "Audience") if any(e["speaker"] == s for e in events)]
    y_speaker = {s: quote_y["lower"] + 0.74 + 0.64 * i for i, s in enumerate(speakers)}
    y_field = {f: y_speaker[speakers[-1]] + 0.9 + i for i, (f, _) in enumerate(fields)}
    y_model = {m.key: y_field[fields[-1][0]] + 2.45 + i for i, m in enumerate(TRAJ_MODELS)}
    half = 0.31
    floor = y_model[TRAJ_MODELS[-1].key] + half  # dashed lines stop at the last model row
    bottom = floor + 0.8                           # room for the judgment bracket and its label

    fig = plt.figure(figsize=(TEXT, 2.55), layout="constrained")
    fig.get_layout_engine().set(w_pad=0.02, h_pad=0.02)
    ax = fig.add_subplot()

    for f, _ in fields:
        spans = []
        for row in rows:
            a, b = max(start, row["time_s"]), min(end, row["time_s"] + tick)
            if b <= a:
                continue
            value = row["decision"].get(f)
            if spans and spans[-1][2] == value:
                spans[-1][1] = b
            else:
                spans.append([a, b, value])
        for a, b, value in spans:
            # Inset so a dashed line shows between two cells of a field that changes there.
            ax.add_patch(Rectangle((a + 0.05, y_field[f] - half), b - a - 0.1, 2 * half, facecolor="white",
                                   edgecolor=REF_EDGE, linewidth=0.6, zorder=2))
            ax.text((a + b) / 2, y_field[f], value_label(f, value), fontsize=SMALL, ha="center", va="center",
                    zorder=3)

    for model in TRAJ_MODELS:
        for run in classes[model.key]:
            style = PARTITION_KINDS[run["class"]]
            ax.add_patch(Rectangle((run["start"], y_model[model.key] - half), run["end"] - run["start"], 2 * half,
                                   facecolor=style["face"], hatch=style["hatch"],
                                   hatchcolor=style["ink"] or style["face"],
                                   edgecolor=style["ink"] or "white", linewidth=0.3, zorder=2))
        ax.text(end + 0.22, y_model[model.key], f"{100 * chosen['share'][model.key]:.1f}%", fontsize=SMALL,
                ha="left", va="center")

    by_utterance = {}
    for e in events:
        by_utterance.setdefault(e["utterance_id"], []).append(e)
    for changes_of_one in by_utterance.values():
        if len(changes_of_one) > 1:
            ax.plot([e["time_s"] for e in changes_of_one], [y_speaker[changes_of_one[0]["speaker"]]] * len(changes_of_one),
                    color=UTTERANCE_INK, linewidth=0.8, zorder=2, solid_capstyle="butt")
    for e in events:
        ax.plot(e["time_s"], y_speaker[e["speaker"]], color="none", zorder=4, clip_on=False,
                markerfacecolor="black" if e["final"] else "white", **TRAJ_MARK)

    quoted = [dict(e) for e in events if any(abs(e["time_s"] - c) < 1e-9 for c in changes)]
    if [e["time_s"] for e in quoted] != changes:
        raise ValueError("quote exactly one transcript change per reference change")
    presenter = [e for e in quoted if e["speaker"] == speakers[0]]
    for e in quoted:
        e["row"] = ("upper", "lower")[presenter.index(e) % 2] if e in presenter else "top"
    # Reference changes, from the transcript change that caused them down through every lane.
    for e in quoted:
        ax.plot([e["time_s"], e["time_s"]], [y_speaker[e["speaker"]], floor], zorder=1, **TRAJ_DASH)

    ticks = [*y_speaker.values(), *y_field.values(), *y_model.values()]
    ax.set_yticks(ticks, [*speakers, *[n for _, n in fields], *[m.name for m in TRAJ_MODELS]])
    ax.set_ylim(bottom, quote_y["top"] - 0.36)
    right = end + 2.37  # the "Correct in this window" column
    ax.set_xlim(start - 0.25, right)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_bounds(start, end)
    ax.tick_params(axis="y", length=0)
    ax.grid(False)
    xt = [start + tick * i for i in range(int(round((end - start) / tick)) + 1)]
    ax.set_xticks(xt, [f"{x:g}" for x in xt])
    ax.set_xlabel(f"Time (s), with a time step every {tick:g} s", labelpad=2)

    header_y = y_model[TRAJ_MODELS[0].key] - half - 0.2
    ax.text(end + 0.22, header_y - 0.08, "Correct in\nthis window", fontsize=SMALL, ha="left", va="bottom",
            linespacing=1.0)
    ax.plot([end + 0.22, right - 0.03], [header_y, header_y], color="black", linewidth=0.5, clip_on=False)

    # Key to the evidence rows: one line at the figure's left edge, on the top quote row, which
    # other speakers' quotes use only on its right. Placed by hand, outside the layout.
    key = [Line2D([], [], markerfacecolor="white", label="Partial hypothesis", **TRAJ_MARK),
           Line2D([], [], markerfacecolor="black", label="Final text", **TRAJ_MARK),
           Line2D([], [], color=UTTERANCE_INK, linewidth=0.8, label="One utterance")]
    key_legend = ax.legend(handles=key, loc="center left", bbox_to_anchor=(0.004, quote_y["top"]),
                           bbox_transform=mtransforms.blended_transform_factory(fig.transFigure, ax.transData),
                           ncol=len(key), fontsize=SMALL, numpoints=1, handlelength=1.3, handletextpad=0.4,
                           columnspacing=1.2, borderaxespad=0.0, borderpad=0.0)
    key_legend.set_in_layout(False)
    handles = [Line2D([], [], label="Reference decision changes", **{**TRAJ_DASH, "linewidth": 0.8})]
    handles += [partition_patch(k, PARTITION_KINDS[k]["gloss"]) for k in present]
    fig.legend(handles=handles, loc="outside lower center", ncol=len(handles), fontsize=SMALL,
               handlelength=1.6, columnspacing=1.3, handletextpad=0.5)

    # Group labels left of the row labels, each with a rule spanning its rows.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    px_per_pt = fig.dpi / 72
    label_pt = max(t.get_window_extent(renderer).width for t in ax.get_yticklabels()) / px_per_pt
    groups = [("ASR", y_speaker[speakers[0]], y_speaker[speakers[-1]]),
              ("Reference\ndecision", y_field[fields[0][0]], y_field[fields[-1][0]]),
              ("Decision\nin force", y_model[TRAJ_MODELS[0].key], y_model[TRAJ_MODELS[-1].key])]
    for name, y_a, y_b in groups:
        rule = mtransforms.offset_copy(ax.get_yaxis_transform(), fig=fig, x=-(label_pt + 6), units="points")
        ax.add_line(Line2D([0, 0], [y_a - half + 0.04, y_b + half - 0.04], transform=rule, color="black",
                           linewidth=0.6, clip_on=False))
        where = mtransforms.offset_copy(ax.get_yaxis_transform(), fig=fig, x=-(label_pt + 8), units="points")
        ax.text(0, (y_a + y_b) / 2, name, transform=where, rotation=90, ha="right", va="center",
                multialignment="center", fontsize=SMALL, linespacing=1.0, clip_on=False)
    # Settle the layout, then freeze it: the quotes and bracket labels are fitted in data units.
    fig.canvas.draw()
    fig.canvas.draw()
    fig.set_layout_engine("none")
    px_per_s = ax.bbox.width / (ax.get_xlim()[1] - ax.get_xlim()[0])

    def width_px(text: str) -> float:
        probe = ax.text(0, 0, text, fontsize=SMALL)
        width = probe.get_window_extent(renderer).width
        probe.remove()
        return width

    leaders = [(e["time_s"], e["row"]) for e in quoted]
    for e in quoted:
        t, row = e["time_s"], e["row"]
        crossing = [lt for lt, lrow in leaders if depth[row] >= depth[lrow]]
        ax.plot([t, t], [y_speaker[e["speaker"]] - 0.13, quote_y[row] + 0.2], color="#333333", linewidth=0.5,
                zorder=3)
        if e["speaker"] == speakers[0]:
            limit = min([lt for lt in crossing if lt > t] + [right]) - QUOTE_CLEAR
            e["quote"] = _fit_quote(e["text"], (limit - t - QUOTE_GAP) * px_per_s, width_px)
            ax.text(t + QUOTE_GAP, quote_y[row], e["quote"], fontsize=SMALL, ha="left", va="center")
        else:
            limit = max([lt for lt in crossing if lt < t] + [start - 0.25]) + QUOTE_CLEAR
            e["quote"] = _fit_quote(e["text"], (t - QUOTE_GAP - limit) * px_per_s, width_px)
            ax.text(t - QUOTE_GAP, quote_y[row], e["quote"], fontsize=SMALL, ha="right", va="center")

    # Stale bracket above the first model row, labelled to its left before the change's line;
    # judgment bracket below Jev's row, labelled to its right (no dashed line runs there).
    notes = []
    y_b = y_model[lead.key] - half - 0.24
    a, b = brackets["stale"]["start_s"], brackets["stale"]["end_s"]
    ax.plot([a, a, b, b], [y_b + 0.14, y_b, y_b, y_b + 0.14], color="black", linewidth=0.7, zorder=6,
            solid_joinstyle="miter")
    notes.append(ax.text(slide_t - 0.15, y_b - 0.04, brackets["stale"]["label"], fontsize=SMALL, ha="right",
                         va="center", zorder=6))
    y_j = floor + 0.3
    a, b = brackets["judgment"]["start_s"], brackets["judgment"]["end_s"]
    ax.plot([a, a, b, b], [y_j - 0.14, y_j, y_j, y_j - 0.14], color="black", linewidth=0.7, zorder=6,
            solid_joinstyle="miter")
    notes.append(ax.text(b + 0.15, y_j + 0.06, brackets["judgment"]["label"], fontsize=SMALL, ha="left",
                         va="center", zorder=6))

    # No quote or bracket label may reach a dashed line, a leader or the right-hand column.
    to_data = ax.transData.inverted()
    texts = [t for t in ax.texts if t.get_text().startswith("“")] + notes
    for text in texts:
        (x0, y0), (x1, y1) = to_data.transform(text.get_window_extent(renderer).get_points())
        lo, hi = sorted((y0, y1))
        for e in quoted:
            if x0 - 0.05 < e["time_s"] < x1 + 0.05 and lo < floor and hi > y_speaker[e["speaker"]]:
                raise ValueError(f"{text.get_text()!r} crosses the dashed line at {e['time_s']} s")
            if x0 - 0.05 < e["time_s"] < x1 + 0.05 and hi > quote_y[e["row"]] + 0.2 and lo < y_speaker[e["speaker"]]:
                raise ValueError(f"{text.get_text()!r} crosses the leader at {e['time_s']} s")
        if text in notes and lo < floor and x1 > end:
            raise ValueError(f"{text.get_text()!r} reaches the right-hand column")
    key_box = key_legend.get_window_extent(renderer)
    key_end = to_data.transform((key_box.x1, key_box.y1))[0]
    if any(key_box.overlaps(text.get_window_extent(renderer)) for text in texts):
        raise ValueError("the evidence key overlaps a quote")
    if any(e["row"] == "top" and e["time_s"] < key_end + QUOTE_CLEAR for e in quoted):
        raise ValueError("the evidence key reaches a leader")

    save(fig, str(OUT / "fig_trajectory"))
    return {"selection": selection, "events": events,
            "quoted_events": [{k: e[k] for k in ("time_s", "utterance_id", "speaker", "final", "text", "quote", "row")}
                              for e in quoted],
            "reference": rows, "reference_fields": [f for f, _ in fields], "composed_changes_s": changes,
            "intervals": plotted,
            "classes": {k: [{kk: r[kk] for kk in ("class", "start", "end")} for r in v] for k, v in classes.items()},
            "brackets": brackets,
            "slide_names": {"labels": slide_names,
                            "source": f"runs/{lead.run}/episodes.json: {eid} questions.slide.criteria",
                            "checked_against": frozen_path}}


# --------------------------------------------------------- appendix: latency


def latency_data(data: dict) -> dict:
    out = {}
    for model in MODELS:
        run, net = data[model.key]["run"], data[model.key]["analysis"]["network_adjustment"]
        generates_text = run["frozen"]["config"].get("provider", "openai") == "openai"
        y, uncached, output = _request_rows(run)
        X = np.column_stack([np.ones(len(y)), uncached / 1000] + ([output] if generates_text else []))
        coef = fit(X, y)
        # The refit must be the analysis's own fit, or the figure describes another model.
        stored = [net["network_s"]["estimate"], net["prefill_s_per_1k_input_tokens"]]
        if generates_text:
            stored.append(net["decode_s_per_output_token"])
        if not np.allclose(coef, stored, rtol=0, atol=1e-9):
            raise ValueError(f"{model.key}: refit {coef} differs from analysis.json {stored}")
        med_in, med_out = float(np.median(uncached)), float(np.median(output))
        network, prefill = float(coef[0]), float(coef[1]) * med_in / 1000
        decode = float(coef[2]) * med_out if generates_text else 0.0
        median = float(np.median(y))
        out[model.key] = {
            "generates_text": generates_text, "requests": int(len(y)),
            "median_uncached_input_tokens": med_in, "median_output_tokens": med_out,
            "network_s": network, "network_range_s": [net["network_s"]["low"], net["network_s"]["high"]],
            "prefill_s_per_1k_input_tokens": float(coef[1]),
            "decode_s_per_output_token": float(coef[2]) if generates_text else None,
            "prefill_s": prefill, "decode_s": decode, "tokens_s": prefill + decode,
            "median_time_before_receipt_s": median,
            "above_envelope_s": median - network - prefill - decode,
            "points": {"output_tokens": output.tolist(), "time_before_receipt_s": y.tolist()},
        }
    return out


# Stacking order of the median request; prefill and decode share a token-proportional
# component, and Jev has no decode term. Names follow the paper: the non-token remainder is the
# fit's intercept, an upper bound on fixed network delay. Components are grey so that no
# colour here repeats a setting's colour from the other figures.
COMPONENTS = [
    ("network_s", "Non-token remainder", {"facecolor": "#7A7A7A"}),
    ("tokens_s", "Prefill + decode", {"facecolor": "#CFCFCF"}),
    ("above_envelope_s", "Above the fit", {"facecolor": "white", "hatch": "//////", "hatchcolor": "#9A9A9A",
                                           "edgecolor": "#9A9A9A", "linewidth": 0.4}),
]
# Colour by model, marker by setting: a GPT-5.6 model at low effort is a circle and without
# reasoning a triangle; the fill repeats it (filled = low effort, hollow = none). Every setting stays
# identifiable in greyscale. Astra low is Okabe-Ito black with a filled diamond: black is the one
# palette colour left that is neither a timing-by-judgment class colour of Figures 1-2 (vermillion
# = judgment, orange = stale) nor a near neighbour of another setting (sky blue sits next to Terra's
# blue and the Correct fill), and in greyscale it is far from blue, green and purple (CIE L* 0 against
# 46-61); the diamond differs from every other marker shape.
SETTING_STYLE = {
    "luna": (PALETTE["purple"], "o"), "luna_none": (PALETTE["purple"], "^"),
    "terra": (PALETTE["blue"], "o"), "terra_none": (PALETTE["blue"], "^"),
    "astra": (PALETTE["black"], "D"),
    "jev": (PALETTE["green"], "s"),
}

MODEL_INK = {key: style[0] for key, style in SETTING_STYLE.items()}
MODEL_MARK = {key: style[1] for key, style in SETTING_STYLE.items()}
# A diamond's corners reach sqrt(2) times as far as a circle of the same marker size; this scale
# gives it about a circle's extent. Astra low, drawn in black, also goes under the other settings'
# points so that it hides none of them.
MARKER_SCALE = {"D": 0.85}
UNDER = {"astra"}


def marker_size(key: str, size: float) -> float:
    return size * MARKER_SCALE.get(MODEL_MARK[key], 1.0)


def low_effort(key: str) -> bool:
    """Filled marker: a GPT setting at low reasoning effort (and Jev); hollow: no reasoning."""
    return not key.endswith("none")


def _points_under(ax, artist, xs, ys) -> int:
    """How many data points fall inside an artist's drawn extent (e.g. a legend)."""
    box = artist.get_window_extent(ax.figure.canvas.get_renderer())
    shown = ax.transData.transform(np.column_stack([xs, ys]))
    inside = (shown[:, 0] >= box.x0) & (shown[:, 0] <= box.x1) & (shown[:, 1] >= box.y0) & (shown[:, 1] <= box.y1)
    return int(inside.sum())


def fig_latency(data: dict) -> dict:
    values = latency_data(data)
    fig, (ax_a, ax_b) = plt.subplots(2, 1, figsize=(COLUMN, 3.75), layout="constrained",
                                     gridspec_kw={"height_ratios": [1.15, 1.95]})

    # (a) the median request, split by the lower-envelope coefficients.
    for i, model in enumerate(MODELS):
        v = values[model.key]
        left = 0.0
        for key, _, style in COMPONENTS:
            width = v[key]
            if width > 0:
                ax_a.barh(i, width, left=left, height=0.62, zorder=2, **style)
            left += width
        lo, hi = v["network_range_s"]
        ax_a.plot([lo, hi], [i, i], color="black", linewidth=0.7, zorder=3)
        for x in (lo, hi):
            ax_a.plot([x, x], [i - 0.13, i + 0.13], color="black", linewidth=0.7, zorder=3)
        ax_a.annotate(f"{v['median_time_before_receipt_s']:.2f} s", xy=(left, i), xytext=(3, 0),
                      textcoords="offset points", ha="left", va="center", fontsize=SMALL)
    ax_a.set_yticks(range(len(MODELS)), [m.name for m in MODELS])
    ax_a.set_ylim(len(MODELS) - 0.45, -0.55)
    ax_a.tick_params(axis="y", length=0)
    ax_a.grid(axis="y", visible=False)
    ax_a.grid(axis="x", color="#E4E4E4", linewidth=0.4)
    ax_a.spines["left"].set_visible(False)
    ax_a.set_xlim(0, 1.3 * max(v["median_time_before_receipt_s"] for v in values.values()))
    ax_a.set_xlabel("Median time before receipt (s)")
    # One row, in stacking order.
    fig.legend(handles=[Patch(label=label, **style) for _, label, style in COMPONENTS],
               loc="outside upper center", ncol=len(COMPONENTS), fontsize=SMALL, handlelength=1.1,
               columnspacing=0.8, handletextpad=0.3)

    # (b) every GPT request, with the fitted 10th-percentile line. Every request is drawn.
    top = right = 0.0
    handles, every_x, every_y = {}, [], []
    for model in MODELS:
        v = values[model.key]
        if not v["generates_text"]:
            continue
        # A nonzero prefill slope is drawn at the median uncached input, so the line is the
        # envelope of a typical request of that length.
        prefill = v["prefill_s_per_1k_input_tokens"] * v["median_uncached_input_tokens"] / 1000
        x = np.array(v["points"]["output_tokens"])
        y = np.array(v["points"]["time_before_receipt_s"])
        every_x += x.tolist()
        every_y += y.tolist()
        top, right = max(top, y.max()), max(right, x.max())
        ink = MODEL_INK[model.key]
        low = low_effort(model.key)  # filled = low effort, hollow = none, as in Figure 3
        ax_b.scatter(x, y, s=4 * MARKER_SCALE.get(MODEL_MARK[model.key], 1.0) ** 2, marker=MODEL_MARK[model.key],
                     facecolors=ink if low else "none", edgecolors=ink, linewidths=0.45, alpha=0.55,
                     zorder=1.9 if model.key in UNDER else 2, rasterized=False)
        envelope = lambda tokens, p=prefill: v["network_s"] + p + v["decode_s_per_output_token"] * np.asarray(tokens)
        # Dashed where it extrapolates to zero output tokens. It meets the axis at the non-token
        # remainder plus the prefill time of the median input, so only with a zero prefill slope
        # does it end at the remainder itself.
        ax_b.plot([0, x.min()], envelope([0, x.min()]), color=ink, linewidth=0.9, dashes=(2, 1.5), zorder=3)
        ax_b.plot([x.min(), x.max()], envelope([x.min(), x.max()]), color=ink, linewidth=1.1, zorder=3)
        line_x = np.linspace(0, x.max(), 200)
        every_x += line_x.tolist()
        every_y += envelope(line_x).tolist()
        # The legend pairs each fit with its setting's marker, so low and none stay apart.
        handles[model.key] = Line2D([], [], color=ink, linewidth=1.1, marker=MODEL_MARK[model.key],
                                    markersize=marker_size(model.key, 3.6),
                                    markerfacecolor=ink if low else "white", markeredgecolor=ink,
                                    markeredgewidth=0.7)
    ax_b.set_xlim(0, 100 * np.ceil(right * 1.05 / 100))
    ax_b.set_ylim(0, np.ceil(top * 2) / 2)
    ax_b.set_xlabel("Output tokens, including reasoning")
    ax_b.set_ylabel("Time before receipt (s)")
    ax_b.grid(axis="both", color="#E4E4E4", linewidth=0.4)
    # Low effort in the first column, no reasoning in the second (a column fills before the next).
    order = [k for k in ("luna", "terra", "astra", "luna_none", "terra_none") if k in handles]
    if sorted(order) != sorted(handles):
        raise ValueError("fig_latency (b): every fitted setting needs a legend entry")
    legend = ax_b.legend([handles[k] for k in order], [next(m.name for m in MODELS if m.key == k) for k in order],
                         loc="upper right", ncol=2, fontsize=SMALL, title="10th-percentile fit",
                         title_fontsize=SMALL, handlelength=1.6, handletextpad=0.4, columnspacing=0.8,
                         frameon=False, borderaxespad=0.1, borderpad=0.1, labelspacing=0.3)
    panel_labels([ax_a, ax_b])
    # The legend keeps the upper right; the y range grows in half-second steps until it covers no
    # request or fit (the empty cell beside Astra low counts as covered).
    y_top = np.ceil(top * 2) / 2
    for _ in range(8):
        fig.canvas.draw()
        if not _points_under(ax_b, legend, every_x, every_y):
            break
        y_top += 0.5
        ax_b.set_ylim(0, y_top)
    else:
        raise ValueError("fig_latency (b): the legend covers requests or fits")
    save(fig, str(OUT / "fig_latency"))
    return {k: {kk: vv for kk, vv in v.items() if kk != "points"} for k, v in values.items()}


# -------------------------------------------------------- figure 2: error time


def errortime_data(data: dict) -> dict:
    out = {}
    for model in MODELS:
        scores = data[model.key]["analysis"]["auc"]["primary"]["overall"]
        keys = ("current_correct", "outdated_correct", "judgment", "stale", "compound", "no_decision")
        part = {k: 100 * scores[k] for k in keys}
        if abs(sum(part.values())-100) > 1e-7:
            raise ValueError("macro time classes must partition 100 percent")
        out[model.key] = {"correct": part["current_correct"]+part["outdated_correct"], "lucky": part["outdated_correct"],
                          **{k: part[k] for k in ("judgment", "stale", "compound", "no_decision")}}
    return out


ERRORTIME_LABEL_MIN = 10.0  # percent; narrower segments stay unlabelled


def fig_errortime(data: dict) -> dict:
    values = errortime_data(data)
    # Rows grouped by model: a gap of 0.35 rows separates Luna, Terra, Astra and Jev.
    rows, y, previous = {}, 0.0, None
    for model in MODELS:
        group = model.key.split("_")[0]
        if previous is not None:
            y += 1.0 + (0.35 if group != previous else 0.0)
        rows[model.key], previous = y, group
    fig, ax = plt.subplots(figsize=(COLUMN, 1.8), layout="constrained")
    fig.get_layout_engine().set(w_pad=0.02, h_pad=0.02)
    for model in MODELS:
        left = 0.0
        for kind in PARTITION_ORDER:
            width = values[model.key][kind]
            style = PARTITION_KINDS[kind]
            ax.barh(rows[model.key], width, left=left, height=0.72, facecolor=style["face"], hatch=style["hatch"],
                    hatchcolor=style["ink"] or style["face"], edgecolor="white", linewidth=0.5, zorder=2)
            # The axis carries the unit; a label on a hatched class sits on a small box of the
            # class's own colour, which masks the hatch under the digits only.
            if width >= ERRORTIME_LABEL_MIN:
                ax.text(left + width / 2, rows[model.key], f"{width:.0f}", ha="center", va="center",
                        fontsize=SMALL, color=style["text"], zorder=4,
                        bbox=None if style["hatch"] is None else
                        {"boxstyle": "round,pad=0.14,rounding_size=0.25", "facecolor": style["face"],
                         "edgecolor": "none"})
            left += width
    ax.set_yticks([rows[m.key] for m in MODELS], [m.name for m in MODELS])
    ax.set_ylim(rows[MODELS[-1].key] + 0.5, -0.5)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color="#E4E4E4", linewidth=0.4)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.set_xlim(0, 100)
    ax.set_xticks(range(0, 101, 20))
    ax.set_xlabel("Share of log-weighted time over 0.5–8 s (%)")
    # One row, in the bars' left-to-right order.
    fig.legend(handles=[partition_patch(k) for k in PARTITION_ORDER], loc="outside upper center",
               ncol=len(PARTITION_ORDER), fontsize=SMALL, handlelength=1.1, handleheight=0.9, columnspacing=0.65,
               handletextpad=0.3, borderaxespad=0.1)
    save(fig, str(OUT / "fig_errortime"))
    return values


def separability_data(data: dict) -> dict:
    """Per scenario: in-force accuracy against untimed accuracy x oracle in-force accuracy."""
    from decimal import Decimal
    from lite_numbers import _scaled, replay as scaled_replay  # noqa: E402

    rows = {}
    for model in MODELS:
        run = data[model.key]["run"]
        same = scaled_replay(run, lambda ep, r, rel: _scaled(r, rel, Decimal(1)))
        oracle = scaled_replay(run, lambda ep, r, rel: _oracle(ep, r, rel))
        rows[model.key] = [{"episode": s["episode_id"], "in_force": s["time_accuracy"],
                            "product": s["untimed_decision_accuracy"] * o["time_accuracy"]} for s, o in zip(same, oracle)]
    return rows


def fig_separability(data: dict) -> dict:
    rows = separability_data(data)
    fig, ax = plt.subplots(figsize=(COLUMN, 2.35), layout="constrained")
    ax.plot([0, 100], [0, 100], color="#8C8C8C", linewidth=0.8, dashes=(3, 2), zorder=1)
    for model in MODELS:
        colour, marker = SETTING_STYLE[model.key]
        xs = [100 * r["product"] for r in rows[model.key]]
        ys = [100 * r["in_force"] for r in rows[model.key]]
        ax.plot(xs, ys, linestyle="none", marker=marker, markersize=marker_size(model.key, 3), markeredgewidth=0.8,
                color=colour, markerfacecolor=colour if low_effort(model.key) else "white", label=model.name,
                zorder=2.9 if model.key in UNDER else 3)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_xticks(range(0, 101, 20))
    ax.set_yticks(range(0, 101, 20))
    ax.set_aspect("equal")
    ax.set_xlabel("Untimed × oracle in-force accuracy (%)")
    ax.set_ylabel("In-force accuracy (%)")
    fig.legend(loc="outside upper center", ncol=3, fontsize=SMALL, handlelength=1.2, columnspacing=0.8)
    save(fig, str(OUT / "fig_separability"))
    return rows


# ---------------------------------------- figure 3 and appendix: pace, position map

# Time-step intervals for the interval figure: each recorded pass is evaluated with every
# latency scaled by (SDB Lite interval) / (interval), which is equivalent.
PACE_INTERVALS = tuple(float(x) for x in np.geomspace(.5, 8, 129))
RECORDED_INK = "#9A9A9A"
# Name placement (points offset, horizontal and vertical alignment) beside a setting's untimed point,
# or below its in-force point where the space beside the untimed point is taken (Luna none's name
# would otherwise run under Astra low's in-force point, and Astra low's would meet Terra low's).
MAP_LABEL = {"luna": ((-5, 0.5), "right", "center", "untimed"), "luna_none": ((0, -5), "center", "top", "in_force"),
             "terra": ((-5, 2.5), "right", "center", "untimed"), "terra_none": ((-5, -1), "right", "center", "untimed"),
             "astra": ((6, -5), "right", "top", "in_force"), "jev": ((5, 2), "left", "center", "untimed")}
# Luna low, Terra low and Astra low have median latencies within 11% of one another (Luna and Terra
# about 1.4% apart), so on the log axis their untimed-to-in-force lines would coincide. Each is drawn
# this many points left or right of its data position, in latency order (display offset only; the
# plotted values are recorded unchanged).
MAP_NUDGE_PT = {"luna": -2.0, "terra": 2.0, "astra": 4.0}
MAP_NUDGE_SPAN = 1.15  # the offset is only for medians within this factor of one another
MAP_TINT = 0.4  # share of the setting colour in the network-removed marker's fill (rest white)


def _oracle(episode: dict, record: dict, release_s: float) -> dict:
    out = json.loads(json.dumps(record))
    out["pred"] = json.loads(json.dumps(episode["steps"][record["t"]]["gold"]))
    return out


def map_data(data: dict) -> dict:
    from lite_numbers import replay as scaled_replay  # noqa: E402  (paper/analysis, read-only)

    rows, slopes = {}, []
    for model in MODELS:
        a = data[model.key]["analysis"]
        net = a["network_adjustment"]
        ceiling = scaled_replay(data[model.key]["run"], _oracle)
        rows[model.key] = {
            "name": model.name,
            "median_response_s": a["latency_s"]["p50"],
            "untimed": a["scores"]["overall"]["untimed_decision_accuracy"],
            "in_force": a["scores"]["overall"]["time_accuracy"],
            "timing_ceiling": float(np.mean([s["time_accuracy"] for s in ceiling])),
            "network_s": net["network_s"],
            "network_removed": {k: net["scores"][k]["overall"]["time_accuracy"] for k in ("estimate", "low", "high")},
        }
        if not slopes:
            slopes = [(row["reference_transitions"] + 1) / row["observed_duration_s"]
                      for row in a["scores"]["per_episode"]]
    # Equation 3 with every answer correct: 1 - L * mean(K_e / (H - r0)_e).
    return {"rows": rows, "segments_per_second": float(np.mean(slopes))}


def _tint(colour: str, share: float) -> tuple:
    rgb = np.array(mpl.colors.to_rgb(colour))
    return tuple(share * rgb + (1 - share) * np.ones(3))


def fig_map(data: dict) -> dict:
    values = map_data(data)
    medians = {k: v["median_response_s"] for k, v in values["rows"].items()}
    nudged = sorted(MAP_NUDGE_PT, key=lambda k: MAP_NUDGE_PT[k])
    ordered = all(medians[a] <= medians[b] for a, b in zip(nudged, nudged[1:]))
    if not (ordered and medians[nudged[-1]] < MAP_NUDGE_SPAN * medians[nudged[0]]):
        raise ValueError("fig_map: the display offset is only for nearly coincident latencies, kept in order")
    fig, ax = plt.subplots(figsize=(COLUMN, 2.55), layout="constrained")
    # The axis spans the plotted latencies (medians and network-removed positions) with a margin.
    xs = [x for v in values["rows"].values()
          for x in (v["median_response_s"], v["median_response_s"] - v["network_s"]["estimate"])]
    x_lo, x_hi = min(xs) / 1.25, max(xs) * 1.25
    # Eq. 4 holds only while the latency is shorter than every reference segment; the shortest
    # SDB Lite segment is one time step, so the curve stops at the time-step interval.
    tick = data[MODELS[0].key]["run"]["episodes"][0]["tick_seconds"]
    grid = np.geomspace(x_lo, tick, 200)
    ax.plot(grid, 100 * np.clip(1 - grid * values["segments_per_second"], 0, 1), color="#8C8C8C",
            linewidth=0.8, dashes=(3, 2), zorder=1)
    x_note = x_lo * 1.12
    ax.text(x_note, 100 * (1 - x_note * values["segments_per_second"]) - 5, "every answer correct",
            fontsize=SMALL, color="#6E6E6E", ha="left", va="top", linespacing=1.0)
    for model in MODELS:
        v = values["rows"][model.key]
        colour, marker = SETTING_STYLE[model.key]
        x = v["median_response_s"]
        # Measured points in data coordinates, shifted in display space only (MAP_NUDGE_PT).
        shift = mtransforms.offset_copy(ax.transData, fig=fig, x=MAP_NUDGE_PT.get(model.key, 0.0), units="points")
        # Markers are not clipped: an untimed accuracy near 100% would lose its top half at the frame.
        ax.plot([x, x], [100 * v["in_force"], 100 * v["untimed"]], color=colour, linewidth=0.8, zorder=2,
                transform=shift)
        ax.plot([x], [100 * v["untimed"]], marker=marker, markersize=marker_size(model.key, 5), markerfacecolor="white",
                markeredgecolor=colour, markeredgewidth=1.0, linestyle="none", zorder=3, transform=shift, clip_on=False)
        ax.plot([x], [100 * v["in_force"]], marker=marker, markersize=marker_size(model.key, 5), color=colour,
                linestyle="none", zorder=3, transform=shift, clip_on=False)
        xn = x - v["network_s"]["estimate"]
        est, lo, hi = (100 * v["network_removed"][k] for k in ("estimate", "low", "high"))
        ax.annotate("", xy=(xn, est), xytext=(x, 100 * v["in_force"]), textcoords=shift,
                    arrowprops={"arrowstyle": "-|>", "color": colour, "linewidth": 0.6, "mutation_scale": 6,
                                "linestyle": (0, (2, 1.2))}, zorder=2)
        # Astra low's network-removed point falls on Terra low's; it is drawn beneath it.
        under = model.key in UNDER
        ax.plot([xn, xn], [lo, hi], color=colour, linewidth=0.8, zorder=2.9 if under else 3)
        ax.plot([xn], [est], marker=marker, markersize=marker_size(model.key, 3.5), color=colour,
                markerfacecolor=_tint(colour, MAP_TINT), markeredgewidth=0.8, linestyle="none", zorder=3.9 if under else 4)
        offset, ha, va, anchor = MAP_LABEL[model.key]
        ax.annotate(model.name, xy=(x, 100 * v[anchor]), xycoords=shift, xytext=offset,
                    textcoords="offset points", fontsize=SMALL, color=colour, ha=ha, va=va)
    ax.set_xscale("log")
    ticks = [t for t in (0.05, 0.1, 0.2, 0.5, 1, 2, 5) if x_lo <= t <= x_hi]
    ax.set_xticks(ticks, [f"{t:g}" for t in ticks])
    ax.xaxis.set_minor_formatter(mpl.ticker.NullFormatter())
    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(0, 100)
    ax.set_xlabel("Median latency (s, log scale)")
    ax.set_ylabel("Accuracy (%)")
    ink = "#737373"  # grey, so the key's generic markers are not read as Astra low's black
    handles = [Line2D([], [], marker="o", markerfacecolor="white", markeredgecolor=ink, linestyle="none",
                      label="Untimed"),
               Line2D([], [], marker="o", color=ink, linestyle="none", label="In force"),
               (Line2D([], [], marker="|", markersize=8, markeredgewidth=0.8, color=ink, linestyle="none"),
                Line2D([], [], marker="o", markersize=3.5, markerfacecolor=_tint(ink, MAP_TINT), markeredgecolor=ink,
                       markeredgewidth=0.8, linestyle="none"))]
    fig.legend(handles=handles, labels=["Untimed", "In force", "Network removed (range)"],
               handler_map={tuple: HandlerTuple(ndivide=1, pad=0.0)},
               loc="outside upper center", ncol=3, fontsize=SMALL, handlelength=1.2, columnspacing=0.8,
               handletextpad=0.3)
    save(fig, str(OUT / "fig_map"))
    values["display_offset_pt"] = dict(MAP_NUDGE_PT)
    values["x_limits_s"] = [x_lo, x_hi]
    return values


def pace_data(data: dict) -> dict:
    from decimal import Decimal
    from lite_numbers import _scaled, replay as scaled_replay

    recorded = {ep["tick_seconds"] for m in MODELS for ep in data[m.key]["recorded"]["episodes"]}
    if len(recorded) != 1:
        raise ValueError("every scenario must share the recording's time-step interval")
    curves, family_curves = {}, {}
    for model in MODELS:
        run = data[model.key]["recorded"]
        points = []; by_family = {f: [] for f, _ in FAMILIES}
        for target in PACE_INTERVALS:
            scores = scaled_replay(run, lambda ep, r, rel: _scaled(r, rel, Decimal(str(ep["tick_seconds"])) / Decimal(str(target))))
            points.append(family_mean(scores, lambda s: s["time_accuracy"]))
            for f in by_family:
                by_family[f].append(float(np.mean([s["time_accuracy"] for s in scores if s["task_family"] == f])))
        curves[model.key] = points
        family_curves[model.key] = by_family
    return {"intervals_s": list(PACE_INTERVALS), "recorded_interval_s": float(recorded.pop()),
            "weighting": "log", "in_force": curves, "by_family": family_curves}


def fig_pace(data: dict) -> dict:
    """One full-width row: (a) the equal family mean, then (b)-(e) the four families."""
    values = pace_data(data)
    x = np.array(values["intervals_s"])
    panels = [("All families (Macro)", values["in_force"])]
    panels += [(name, {k: values["by_family"][k][family] for k in values["by_family"]}) for family, name in FAMILIES]
    fig = plt.figure(figsize=(TEXT, 2.05), layout="constrained")
    # wspace keeps a panel's "5" clear of the next panel's "1".
    fig.get_layout_engine().set(w_pad=0.02, h_pad=0.02, wspace=0.08)
    # A narrow empty column separates the aggregate (a) from the four families it averages.
    grid = fig.add_gridspec(1, 6, width_ratios=[1, 0.07, 1, 1, 1, 1])
    axes = []
    for column in (0, 2, 3, 4, 5):
        axes.append(fig.add_subplot(grid[0, column], sharex=axes[0] if axes else None,
                                    sharey=axes[0] if axes else None))
    for i, (ax, (name, curves)) in enumerate(zip(axes, panels)):
        # The recorded interval: every other interval re-evaluates this pass's answers and latencies.
        ax.axvline(values["recorded_interval_s"], color=RECORDED_INK, linewidth=0.6, dashes=(1, 1.6), zorder=1)
        for model in MODELS:
            colour, marker = SETTING_STYLE[model.key]
            ax.plot(x, 100 * np.array(curves[model.key]), color=colour, marker=marker,
                    markersize=marker_size(model.key, 3.0), markevery=32,
                    markerfacecolor=colour if low_effort(model.key) else "white",
                    markeredgewidth=0.8, linewidth=0.9, zorder=3, clip_on=False)
        ax.set_xscale("log")
        ax.set_xlim(.5, 8)
        ax.set_ylim(0, 100)
        ax.set_yticks(range(0, 101, 20))
        ax.set_xticks([.5, 1, 2, 4, 8], [".5", "1", "2", "4", "8"])
        ax.xaxis.set_minor_locator(mpl.ticker.NullLocator())
        ax.annotate(f"({'abcde'[i]}) {name}", xy=(0, 1), xycoords="axes fraction", xytext=(0, 2.5),
                    textcoords="offset points", ha="left", va="bottom", fontsize=SMALL,
                    fontweight="bold" if i == 0 else "normal")
        if i:
            ax.tick_params(labelleft=False)
    axes[0].set_ylabel("In-force accuracy (%)")
    middle = axes[2]
    middle.set_xlabel("Time-step interval (s, log scale)")
    fig.canvas.draw()
    # One x label for the row, centred on the figure.
    middle.xaxis.label.set_x(middle.transAxes.inverted().transform(fig.transFigure.transform((0.5, 0)))[0])
    handles = []
    for model in MODELS:
        colour, marker = SETTING_STYLE[model.key]
        handles.append(Line2D([], [], color=colour, marker=marker, markersize=marker_size(model.key, 3.6), linewidth=0.9,
                              markerfacecolor=colour if low_effort(model.key) else "white", label=model.name))
    handles.append(Line2D([], [], color=RECORDED_INK, linewidth=0.6, dashes=(1, 1.6),
                          label=f"Recording interval ({values['recorded_interval_s']:g} s)"))
    fig.legend(handles=handles, loc="outside upper center", ncol=len(handles), fontsize=SMALL, handlelength=1.6,
               columnspacing=1.1, handletextpad=0.4)
    save(fig, str(OUT / "fig_pace"))
    return values


def main() -> None:
    use_style()
    mpl.rcParams["hatch.linewidth"] = 0.6  # one hatch weight in every figure
    OUT.mkdir(parents=True, exist_ok=True)
    data = load()
    record = {
        "sources": {m.key: {"run": f"runs/{m.run}", "analysis": f"docs/lite/results/{m.results}/analysis.json",
                            "events_sha256": data[m.key]["analysis"]["events_sha256"],
                            "dataset_hash": data[m.key]["analysis"]["dataset_hash"],
                            "auc_sources_sha256": data[m.key]["analysis"]["auc"]["sources_sha256"]} for m in MODELS},
        "fig_trajectory_window": window_check(data),
        "fig_trajectory": fig_trajectory(data),
        "fig_latency": fig_latency(data),
        "fig_errortime": fig_errortime(data),
        "fig_map": fig_map(data),
        "fig_pace": fig_pace(data),
        "fig_separability": fig_separability(data),
    }
    # The by-family curves of fig_pace (b)-(e), kept under their earlier key.
    record["fig_family_pace"] = record["fig_pace"]["by_family"]
    (OUT / "lite_figures_data.json").write_text(json.dumps(record, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
