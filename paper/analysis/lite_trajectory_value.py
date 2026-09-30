"""Reproduce transition-local errors and fast/slow arbitration without API calls."""

from __future__ import annotations

import hashlib
from dataclasses import replace
import json
import math
from pathlib import Path
from statistics import mean
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from lite_numbers import FACTS_COLUMNS, MODELS, fixed, pct as tex_pct
from streamdecisionbench.lite.__main__ import rescore_run
from streamdecisionbench.lite.core import digest
from trajectory_replay import METRICS, aggregate, evaluate, prepare

POLICY_PATH = ROOT / "paper/analysis/trajectory_policy.json"
OUT = ROOT / "docs/research/trajectory-value"
LABELS = {"freshest": "Freshest source", "lag_one": "One-tick lag", "arrival": "Late override"}
POLICY_MACROS = {"freshest": "Freshest", "lag_one": "LagOne", "arrival": "Arrival"}


def transition_errors(scenarios, name, radius):
    """Unique state assignment to nearest actual change; ties go to earlier change.

    Initial availability is not a reference transition. Offsets are signed: -1
    is before the assigned transition and +1 after it. Report denominators:
    dense timelines can put most states in a transition neighborhood.
    """
    records = []
    for sc in scenarios:
        changes = [t for t in range(1, len(sc.gold)) if sc.gold[t] != sc.gold[t - 1]]
        if not changes:
            raise ValueError("transition analysis requires at least one change")
        for t, pred in enumerate(sc.components[name].predictions):
            nearest = min(changes, key=lambda c: (abs(t - c), c))
            records.append({"episode_id": sc.episode_id, "family": sc.family,
                            "t": t, "offset": t - nearest, "wrong": pred != sc.gold[t]})

    def counts(rows):
        n, wrong = len(rows), sum(r["wrong"] for r in rows)
        return {"states": n, "errors": wrong, "error_rate": wrong / n if n else None}

    def groups(rows):
        return {
            "near": counts([r for r in rows if abs(r["offset"]) <= radius]),
            "far": counts([r for r in rows if abs(r["offset"]) > radius]),
            "by_offset": {str(k): counts([r for r in rows if r["offset"] == k])
                          for k in sorted({r["offset"] for r in rows})},
        }

    return {**groups(records), "by_family": {f: groups([r for r in records if r["family"] == f])
            for f in sorted({r["family"] for r in records})}, "states": records}


def regression_example(data, scenarios):
    """Longest contiguous loss from one stale slow override of a correct fast source."""
    losses = []
    for fresh, late in zip(data["traces"]["freshest"], data["traces"]["arrival"], strict=True):
        pieces = []
        for f in fresh["spans"]:
            if f["kind"] != "current_correct" or f["component"] != "Jev":
                continue
            for s in late["spans"]:
                if s["kind"] != "stale" or s["component"] != "Terra" or s["source_t"] >= f["source_t"]:
                    continue
                start, end = max(f["start_s"], s["start_s"]), min(f["end_s"], s["end_s"])
                if end > start:
                    pieces.append({"episode_id": fresh["episode_id"], "start_s": start, "end_s": end,
                                   "fast_source": f["source_t"], "slow_source": s["source_t"]})
        for piece in sorted(pieces, key=lambda p: p["start_s"]):
            if (losses and all(losses[-1][k] == piece[k] for k in ("episode_id", "fast_source", "slow_source"))
                    and math.isclose(losses[-1]["end_s"], piece["start_s"], rel_tol=0, abs_tol=1e-12)):
                losses[-1]["end_s"] = piece["end_s"]
            else:
                losses.append(piece)
    example = max(losses, key=lambda p: p["end_s"] - p["start_s"])
    sc = next(sc for sc in scenarios if sc.episode_id == example["episode_id"])
    fresh = next(r for r in data["traces"]["freshest"] if r["episode_id"] == sc.episode_id)
    example["fast_arrival_s"] = next(r["arrival_s"] for r in fresh["accepted"]
                                    if r["component"] == "Jev" and r["source_t"] == example["fast_source"])
    example["duration_s"] = example["end_s"] - example["start_s"]
    example["old_reference"] = sc.gold[example["slow_source"]]
    example["new_reference"] = sc.gold[example["fast_source"]]
    before, after = example["old_reference"], example["new_reference"]
    example["decision_change"] = ", ".join(
        f"{k.replace('_', ' ')} from {before[k]} to {after[k]}"
        for k in sorted(before.keys() & after.keys()) if before[k] != after[k]
    )
    family, variant = sc.episode_id.split("_")[-2:]
    example["scenario_label"] = f"{family} {variant.upper()}"
    return example


def integrate(scenarios, fast, slow, policy, options):
    """Exact log integral, split at every release/arrival-order crossing.

    Arbitration can jump when an arrival switches from preceding to following
    a newer fast answer. A smooth-grid convergence check can miss these jumps.
    Between all crossings the accepted path is fixed; every span length is
    affine in delta and its normalized fraction is c0 + c1/delta. Integrate
    that form analytically. The two interior evaluations recover its two
    coefficients; a third checks the affine form independently.
    """
    if options["weighting"] != "log":
        raise ValueError("this analysis uses the paper's declared log weighting")
    lo, hi = options["min_s"], options["max_s"]
    rows, pieces, residual = [], {}, 0.0
    for sc in scenarios:
        slopes = [r / sc.tick_s for r in sc.releases_s]
        lines = [(s, 0.0) for s in slopes] + [(len(sc.gold), 0.0)]
        for name in [fast] if slow is None else [fast, slow]:
            lines += list(zip(slopes, sc.components[name].delays_s, strict=True))
        breaks = {lo, hi}
        for i, (a, b) in enumerate(lines):
            for c, d in lines[i + 1:]:
                if a != c:
                    crossing = (d - b) / (a - c)
                    if lo < crossing < hi:
                        breaks.add(crossing)
        breaks = sorted(breaks)
        total = np.zeros(len(METRICS))
        for a, b in zip(breaks, breaks[1:]):
            if b - a <= 1e-12:
                continue  # negligible floating-point duplicates of one crossing
            x, y, z = a + (b - a) / 4, a + 3 * (b - a) / 4, (a + b) / 2
            vx, vy, vz = [np.array([row[k] for k in METRICS]) for row in
                          [evaluate(sc, fast, slow, d, policy) for d in (x, y, z)]]
            c1 = (vx - vy) / (1 / x - 1 / y)
            c0 = vx - c1 / x
            error = float(np.max(np.abs(c0 + c1 / z - vz)))
            residual = max(residual, error)
            if error > 1e-9:
                raise ValueError(f"{sc.episode_id}: affine span identity failed")
            total += c0 * math.log(b / a) + c1 * (1 / a - 1 / b)
        rows.append({"episode_id": sc.episode_id, "task_family": sc.family,
                     **dict(zip(METRICS, map(float, total / math.log(hi / lo)), strict=True))})
        pieces[sc.episode_id] = len(breaks) - 1
    # The sampled curve is for display only; the reported area is analytical.
    display_intervals = np.geomspace(lo, hi, 161).tolist()
    curve = [aggregate([evaluate(sc, fast, slow, d, policy) for sc in scenarios])["overall"]["accuracy"]
             for d in display_intervals]
    return {**aggregate(rows), "integration": {"method": "exact_piecewise_affine_in_inverse_interval",
            "pieces_by_episode": pieces, "max_affine_check_residual": residual},
            "curve": {"intervals_s": display_intervals, "accuracy": curve}}


def render(data):
    pct = lambda x: f"{100*x:.2f}"
    lines = [
        "# What the trajectory adds beyond accuracy and latency summaries", "",
        "Reproduce from the repository root: `uv run --group paper python paper/analysis/lite_trajectory_value.py`.",
        "No API calls. All six settings, eight frozen scenarios and all five Jev/GPT pairs are included.", "",
        "## Errors relative to reference transitions", "",
        "Assign each state to the nearest change of the composed reference, excluding initial availability; ties go to the earlier change. "
        "Near means within one tick (before, at or after that change). Each state is counted once. "
        "This labels untimed judgment errors using trajectory position; it does not use arrival timing.", "",
        "| Setting | Near errors / states | Near error (%) | Far errors / states | Far error (%) |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, row in data["transition_errors"].items():
        a, b = row["near"], row["far"]
        lines.append(f"| {FACTS_COLUMNS[name]} | {a['errors']} / {a['states']} | {pct(a['error_rate'])} | "
                     f"{b['errors']} / {b['states']} | {pct(b['error_rate'])} |")
    near = data["transition_errors"]["Luna"]["near"]["states"]
    far = data["transition_errors"]["Luna"]["far"]["states"]
    lines += ["", f"The neighborhood already contains {near}/{near+far} states ({100*near/(near+far):.1f}%): raw error counts alone would exaggerate concentration. "
              "Luna low and Terra low show higher error rates near changes; Luna none does not. "
              "These descriptive counts do not establish causality or statistical significance. The signed offsets and family breakdowns are in `analysis.json`.",
              "", "## Fast response followed by a slow correction", "",
              "At every state, dispatch both components. Retain their recorded successful-attempt duration plus commit lag, "
              "but place both on common nominal releases t × Δ. Recompute all acceptance times and integrate the held decisions exactly. "
              "Each component discards arrivals older than a source it has already delivered, even if arbitration rejected that delivery. "
              "Fast answers never move the active source backward. Slow answers win same-source ties and can replace fast answers for that state.", "",
              "- **Freshest source:** slow output must be at least as recent as the active source.",
              "- **One-tick lag:** slow output may be one source tick older than the active decision.",
              "- **Late override:** slow output may be arbitrarily older than the active decision.", "",
              "All rules depend on source order and component identity, never reference answers or correctness. "
              "Newest source, then slow, is processed first at exactly simultaneous arrivals; arrivals at the horizon are excluded.", "",
              "| Slow component (fast = Jev) | Policy | 1 s | 2 s | 4 s | 5 s | Log-AUC 1–5 s |",
              "|---|---|---:|---:|---:|---:|---:|",
    ]
    for slow, systems in data["systems"].items():
        for policy, result in systems.items():
            scores = [pct(result["fixed"][str(d)]["overall"]["accuracy"])
                      for d in data["policy"]["fixed_intervals_s"]]
            lines.append("| " + " | ".join([FACTS_COLUMNS[slow], LABELS[policy], *scores,
                                          pct(result["integrated"]["overall"]["accuracy"])]) + " |")
    lines += ["", "| Standalone setting, same nominal releases | 2 s | Log-AUC 1–5 s |",
              "|---|---:|---:|"]
    for name, row in data["standalone"].items():
        lines.append(f"| {FACTS_COLUMNS[name]} | {pct(row['fixed']['2']['overall']['accuracy'])} | "
                     f"{pct(row['integrated']['overall']['accuracy'])} |")
    lines += ["", "## Why the scalar summaries are insufficient", "",
              "All arbitration variants of a pair have exactly the same component answers, untimed accuracies, "
              "full latency distributions (hence medians), reference schedule and request count. "
              "Those summaries cannot distinguish variants; the interleaved path and acceptance rule can. "
              "For Jev + Terra low at 2 s, freshest-source arbitration beats standalone Jev, whereas late override falls below it. "
              "At 1 s, loosening arbitration admits many outdated slow answers and causes a larger loss. "
              "The conclusion is conditional on the recorded traces, rather than a claim that one policy always wins.", ""]
    e = data["regression_example"]
    lines += [f"The longest contiguous loss from one stale Terra-low override of a correct Jev source occurs in `{e['episode_id']}`. "
              f"At {e['fast_arrival_s']:.6f} s Jev's source-{e['fast_source']} answer correctly applies the new decision. "
              f"At {e['start_s']:.6f} s Terra's source-{e['slow_source']} answer arrives, correct for its own state, "
              f"and late override reinstates the old decision until {e['end_s']:.6f} s ({e['duration_s']:.6f} s of added stale time). "
              f"The reference changes {e['decision_change']}. "
              "Freshest-source arbitration rejects that old answer. The full old/new composed references are saved in `analysis.json`.", "",
              "A two-output system has no unique per-state untimed answer: the provisional answer and its correction "
              "have different durations. Using the slow component's final-answer accuracy as U is an explicit proxy, "
              "not the system's measured current-source judgment. Even with the exact policy-specific oracle O, "
              "that proxy can badly overpredict correctness:", "",
              "| Pair / freshest policy, 2 s | Slow final U (%) | Exact O (%) | Slow U × O (%) | Actual A (%) | Slow time share (%) |",
              "|---|---:|---:|---:|---:|---:|",
    ]
    for slow, systems in data["systems"].items():
        result = systems["freshest"]["fixed"]["2"]
        row = result["overall"]
        u = mean(r["terminal_untimed"] for r in result["per_episode"])
        lines.append("| " + " | ".join([FACTS_COLUMNS[slow], pct(u), pct(row["oracle"]),
                     pct(row["terminal_product"]), pct(row["accuracy"]), pct(row["slow_share"])]) + " |")
    lines += ["", "The exact identity A = O × U_cur + lucky still holds: O is the current-source time share, "
              "and U_cur is computed from whichever component actually remains in force during that share. "
              "The analysis challenges replacement of the path by marginal summaries; it does not challenge the identity.", "",
              "## Scope and limitations", "",
              data["policy"]["selection"], "", data["policy"]["limitations"], "",
              "Common nominal releases differ slightly from the recorded client releases. Standalone replays are cross-checked "
              "against the published 2 s scores; the maximum absolute discrepancy is "
              f"{data['verification']['max_nominal_recorded_gap_points']:.6f} percentage points. "
              "Log-AUC uses the paper's family weights and log bounds, integrating analytically between all release/arrival-order "
              "crossings. On each piece, the metric has form c0 + c1/Δ; a third interior evaluation checks this form. "
              "Display curves are sampled separately and do not determine the reported area. No new evidence addresses recording-rate effects, "
              "reference audit validity or empirical transition-rate calibration.", "",
              "`analysis.json` includes per-scenario partitions, accepted-response counts, curves, hashes and the complete 2 s "
              "Jev/Terra-low traces for both freshest-source and late-override arbitration.", ""]
    return "\n".join(lines)


def write_tex(data):
    macros = {}
    def add(name, value, source):
        macros[name] = (value, source)
    add("TrajNominalGap", fixed(data["verification"]["max_nominal_recorded_gap_points"], 6),
        "verification.max_nominal_recorded_gap_points")
    add("TrajExampleScenario", data["regression_example"]["scenario_label"], "regression_example.scenario_label")
    add("TrajExampleChange", data["regression_example"]["decision_change"], "regression_example.decision_change")
    for suffix, key in (("FastArrival", "fast_arrival_s"), ("OldArrival", "start_s"),
                        ("Restore", "end_s"), ("Loss", "duration_s")):
        add(f"TrajExample{suffix}", fixed(data["regression_example"][key], 3), f"regression_example.{key}")
    for suffix, key in (("FastSource", "fast_source"), ("OldSource", "slow_source")):
        add(f"TrajExample{suffix}", str(data["regression_example"][key]), f"regression_example.{key}")
    for name, row in data["transition_errors"].items():
        for prefix in ("near", "far"):
            r = row[prefix]
            for suffix, value in (("States", str(r["states"])), ("Errors", str(r["errors"])),
                                  ("Error", tex_pct(r['error_rate']))):
                add(f"Traj{name}{prefix.title()}{suffix}", value, f"transition_errors.{name}.{prefix}")
    for name, result in data["standalone"].items():
        add(f"Traj{name}Two", tex_pct(result['fixed']['2']['overall']['accuracy']), f"standalone.{name}.fixed.2")
        add(f"Traj{name}Auc", tex_pct(result['integrated']['overall']['accuracy']), f"standalone.{name}.integrated")
    for name, systems in data["systems"].items():
        for policy, result in systems.items():
            for suffix, row in [("One", result["fixed"]["1"]), ("Two", result["fixed"]["2"]),
                                ("Auc", result["integrated"])]:
                add(f"Traj{name}{POLICY_MACROS[policy]}{suffix}", tex_pct(row['overall']['accuracy']),
                    f"systems.{name}.{policy}.{'integrated' if suffix == 'Auc' else 'fixed.' + ('1' if suffix == 'One' else '2')}")
            row = result["fixed"]["2"]["overall"]
            for suffix, key in (("SlowShare", "slow_share"), ("Proxy", "terminal_product")):
                add(f"Traj{name}{POLICY_MACROS[policy]}{suffix}", tex_pct(row[key]), f"systems.{name}.{policy}.fixed.2.overall.{key}")
    lines = ["% Generated by paper/analysis/lite_trajectory_value.py; do not edit."]
    for name, (value, source) in macros.items():
        lines.extend([f"% docs/research/trajectory-value/analysis.json: {source}",
                      f"\\newcommand{{\\{name}}}{{{value}}}"])
    (ROOT / "paper/generated/trajectory_numbers.tex").write_text("\n".join(lines) + "\n")
    rows = []
    for name in data["systems"]:
        for policy in data["policy"]["policies"]:
            label = {"freshest": "Freshest", "lag_one": "Lag $\\leq 1$", "arrival": "Override"}[policy]
            rows.append(" & ".join([f"\\{name}RowLabel", label,
                *[f"\\Traj{name}{POLICY_MACROS[policy]}{suffix}" for suffix in ("One", "Two", "Auc")]]) + r" \\")
    (ROOT / "paper/generated/trajectory_tables.tex").write_text(
        "% Generated by paper/analysis/lite_trajectory_value.py; do not edit.\n"
        + "\\newcommand{\\TabTrajectoryBody}{%\n" + "\n".join(rows) + "\n}\n")


def reviewer_response(data):
    pct = lambda x: f"{100*x:.2f}"
    systems = data["systems"]
    two = lambda slow, policy: systems[slow][policy]["fixed"]["2"]["overall"]["accuracy"]
    jev = data["standalone"]["Jev"]
    e = data["regression_example"]
    rates = data["transition_errors"]
    local = lambda name: (f"{rates[name]['near']['errors']} errors in {rates[name]['near']['states']} states "
                         f"({pct(rates[name]['near']['error_rate'])}%), versus "
                         f"{rates[name]['far']['errors']} in {rates[name]['far']['states']} "
                         f"({pct(rates[name]['far']['error_rate'])}%) farther away")
    return f"""# Response: information beyond an accuracy–latency product

The scalar approximation is useful for the isolated components in our recordings. We have added two analyses that identify information lost by those marginal summaries, using all existing recordings without further model queries.

First, we assign each state to its nearest actual change of the composed reference and report error rates with denominators. Within one tick of a change, Luna low makes {local('Luna')}; Terra low makes {local('Terra')}. Luna none gives {pct(rates['LunaNone']['near']['error_rate'])}% versus {pct(rates['LunaNone']['far']['error_rate'])}%, so we describe this as setting-dependent concentration rather than a universal result. Initial availability is excluded; each state is counted once, and signed offsets and family breakdowns are provided. This finding uses temporal position, which untimed accuracy and median latency do not retain.

Second, we replay all five Jev/GPT pairs under three explicit, correctness-independent arbitration rules. Both components are requested at every state; the slow component may correct the fast component for that same state. The rules allow a slow answer to regress the active source by zero ticks, one tick, or arbitrarily many ticks. Every variant uses identical answers, complete latency distributions, reference transitions and request counts.

At the recorded 2 s cadence, Jev plus Terra low obtains {pct(two('Terra', 'freshest'))}% in-force accuracy with the freshness rule, exceeding Jev alone ({pct(jev['fixed']['2']['overall']['accuracy'])}%). Allowing old slow answers to override newer fast answers instead gives {pct(two('Terra', 'arrival'))}%, below Jev alone: the system-design conclusion reverses while all component summaries remain unchanged. The penalty becomes larger at 1 s. Jev plus Terra none under the freshness rule reaches {pct(systems['TerraNone']['freshest']['integrated']['overall']['accuracy'])}% log-AUC over 1–5 s, compared with {pct(jev['integrated']['overall']['accuracy'])}% for Jev alone. The complete matrix includes all pairs and policies, including combinations that reduce accuracy.

A concrete trace explains the reversal. In {e['scenario_label']}, the reference changes {e['decision_change']}. Jev's correct source-{e['fast_source']} answer arrives at {e['fast_arrival_s']:.3f} s; Terra's source-{e['slow_source']} answer arrives at {e['start_s']:.3f} s, correct for its own state. Late override reinstates the previous decision for {e['duration_s']:.3f} s, until {e['end_s']:.3f} s. Freshest-source arbitration rejects it. This is the longest contiguous stale loss from a single Terra-low override of a correct Jev source in the eight scenarios, selected by an explicit rule.

The exact identity A = O × U_cur + lucky remains valid. A system that first emits a provisional answer and later corrects it has no unique state-level untimed answer that represents both exposure durations. For example, multiplying Terra low's final-answer accuracy by the freshness system's exact oracle predicts {pct(systems['Terra']['freshest']['fixed']['2']['overall']['terminal_product'])}%, versus its actual {pct(two('Terra', 'freshest'))}%; we explicitly label this as a final-answer proxy, not a uniquely defined system U. The trajectory measures which answer remains in force and supplies U_cur. Thus our added evidence concerns both temporal error localization and a concrete arbitration decision that marginal component summaries cannot determine.

These are counterfactual compositions of separately recorded components. We do not claim measured joint service performance or stable rankings across recordings. We use common nominal releases for the joint application; the largest standalone difference from the original release clocks is {data['verification']['max_nominal_recorded_gap_points']:.6f} percentage points. Acceptance-order changes can make the composed accuracy curve discontinuous, so its log-AUC is integrated analytically between every release/arrival-order crossing, with independently checked affine pieces. The manuscript reports the central finding; its new appendix gives all policies, results, transition definitions and assumptions. The reproducible analysis and full provenance are in `docs/research/trajectory-value/`.
"""


def plot(data):
    from figstyle import PALETTE, TEXT, save, use_style
    import matplotlib.pyplot as plt
    use_style()
    fig, axes = plt.subplots(1, 2, figsize=(TEXT, 2.4), layout="constrained")
    styles = [("freshest", "blue", "-"), ("lag_one", "orange", "--"), ("arrival", "red", ":")]
    for ax, slow in zip(axes, ["Terra", "TerraNone"], strict=True):
        for policy, color, style in styles:
            curve = data["systems"][slow][policy]["integrated"]["curve"]
            ax.plot(curve["intervals_s"], np.array(curve["accuracy"]) * 100,
                    color=PALETTE[color], linestyle=style, label=LABELS[policy])
        curve = data["standalone"]["Jev"]["integrated"]["curve"]
        ax.plot(curve["intervals_s"], np.array(curve["accuracy"]) * 100,
                color="#777777", linestyle="-.", label="Jev alone")
        ax.text(0.04, 0.97, f"Jev + {FACTS_COLUMNS[slow]}", transform=ax.transAxes, va="top", fontsize=8)
        ax.set(xscale="log", xlim=(1, 5), ylim=(45, 82),
               xlabel="Time-step interval (s)", ylabel="In-force accuracy (%)")
        ax.set_xticks([1, 2, 3, 4, 5], labels=["1", "2", "3", "4", "5"])
        ax.minorticks_off()
    axes[1].legend(loc="lower right", fontsize=7)
    save(fig, str(ROOT / "paper/figures/fig_arbitration"))


def main():
    policy = json.loads(POLICY_PATH.read_text())
    auc_policy = json.loads((ROOT / "paper/analysis/evaluation_policy.json").read_text())
    runs, provenance = {}, {}
    for name, _, run_name in MODELS:
        path = ROOT / "runs" / run_name
        run = rescore_run(path)
        actual = hashlib.sha256((path / "events.jsonl").read_bytes()).hexdigest()
        if actual != run["frozen"]["events_sha256"]:
            raise ValueError(f"{name}: events differ from recorded hash")
        for ep in run["episodes"]:
            if digest(ep) != run["frozen"]["dataset_manifest"]["hashes"][ep["episode_id"]]:
                raise ValueError(f"{name}: frozen episode hash mismatch")
        runs[name] = run
        provenance[name] = {"run": str(path.relative_to(ROOT)), "events_sha256": actual}
    scenarios = prepare(runs)
    data = {"policy": policy, "auc_policy": auc_policy, "provenance": provenance,
            "transition_errors": {}, "standalone": {}, "systems": {}, "verification": {}}
    for name in runs:
        data["transition_errors"][name] = transition_errors(scenarios, name, policy["transition_neighborhood_ticks"])
        fixed = {str(d): aggregate([evaluate(sc, name, None, d) for sc in scenarios])
                 for d in policy["fixed_intervals_s"]}
        data["standalone"][name] = {"fixed": fixed, "integrated": integrate(
            scenarios, name, None, "freshest", auc_policy["primary"])}
        print(f"Standalone {name} verified", flush=True)
    gaps = [abs(row["accuracy"] - recorded["time_accuracy"]) * 100
            for name, run in runs.items()
            for row, recorded in zip(data["standalone"][name]["fixed"]["2"]["per_episode"],
                                     run["scores"]["per_episode"], strict=True)]
    for name, run in runs.items():
        for sc, recorded in zip(scenarios, run["scores"]["per_episode"], strict=True):
            own_clock = replace(sc, releases_s=tuple(r["release_s"] for r in run["releases"][sc.episode_id]))
            independent = evaluate(own_clock, name, None, 2)
            if not math.isclose(independent["accuracy"], recorded["time_accuracy"], abs_tol=1e-12):
                raise ValueError(f"{name}/{sc.episode_id}: standalone scorer disagrees")
            for kind in recorded["time_partition_seconds"]:
                if not math.isclose(independent[kind], recorded["time_partition_seconds"][kind]
                                    / recorded["observed_duration_s"], abs_tol=1e-12):
                    raise ValueError(f"{name}/{sc.episode_id}: partition disagrees: {kind}")
    data["verification"]["standalone_partition_checks"] = len(gaps)
    data["verification"]["max_nominal_recorded_gap_points"] = max(gaps)
    for slow in policy["slow_settings"]:
        data["systems"][slow] = {}
        for arbitration in policy["policies"]:
            fixed = {str(d): aggregate([evaluate(sc, policy["fast_setting"], slow, d, arbitration)
                                      for sc in scenarios]) for d in policy["fixed_intervals_s"]}
            data["systems"][slow][arbitration] = {"fixed": fixed, "integrated": integrate(
                scenarios, policy["fast_setting"], slow, arbitration, auc_policy["primary"])}
            print(f"Replayed {slow}/{arbitration}", flush=True)
    data["traces"] = {p: [evaluate(sc, "Jev", "Terra", 2, p, trace=True) for sc in scenarios]
                      for p in ("freshest", "arrival")}
    data["regression_example"] = regression_example(data, scenarios)
    sources = ["paper/analysis/lite_trajectory_value.py", "paper/analysis/trajectory_replay.py",
               "paper/analysis/lite_numbers.py",
               "paper/analysis/trajectory_policy.json", "paper/analysis/evaluation_policy.json",
               "src/streamdecisionbench/lite/scoring.py", "src/streamdecisionbench/lite/retry_scoring.py",
               "src/streamdecisionbench/lite/core.py", "src/streamdecisionbench/lite/__main__.py",
               "paper/analysis/figstyle.py"]
    data["sources_sha256"] = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "analysis.json").write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    (OUT / "README.md").write_text(render(data))
    (OUT / "reviewer-response.md").write_text(reviewer_response(data))
    write_tex(data)
    plot(data)
    print(f"Wrote {OUT.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
