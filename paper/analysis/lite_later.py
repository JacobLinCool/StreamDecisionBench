"""Hosted settings recorded after the manuscript's six hosted settings.

Reads frozen recordings and their published reports; makes no model call.
Standalone scores average the three published per-pass analyses, each checked
against an independent original-clock integration. Compositions follow the
manuscript's hosted rule (trajectory_policy.json): every later fast decision
interface is paired with the same correctors under the same arbitration rules,
matching pass indices on common nominal releases.

Writes docs/research/later-hosted/analysis.json, paper/generated/later_numbers.tex
and paper/generated/later_tables.tex.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, stdev
import sys

import numpy as np

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts/runpod"))

from leaderboard_models import HOSTED_LABELS, HOSTED_PASSES
from lite_numbers import FAMILIES, fixed, pct as pct1
from lite_openweight import compare_published, mean_evaluations, pct, sha, verified_run, verify_standalone
from lite_trajectory_value import POLICY_MACROS, integrate
from trajectory_replay import METRICS, PARTITION, aggregate, evaluate, prepare

POLICY_PATH = ROOT / "paper/analysis/later_policy.json"
OUT = ROOT / "docs/research/later-hosted"
REPORT = "docs/research/later-hosted/analysis.json"
PASSES = 3


def isolate_worker():
    """Workers read frozen files only; refuse any network connection."""
    sys.dont_write_bytecode = True
    def block(event, args):
        if event in {"socket.connect", "socket.connect_ex", "socket.getaddrinfo", "socket.gethostbyname"}:
            raise RuntimeError(f"lite_later workers cannot use network access: {event}")
    sys.addaudithook(block)


def load_pass(name, index):
    folder, run_folder = HOSTED_PASSES[name][index]
    path = ROOT / "runs" / run_folder
    run, hashes = verified_run(path)
    report_path = ROOT / "docs/lite/results" / folder / "analysis.json"
    report = json.loads(report_path.read_text())
    if report["events_sha256"] != hashes["events.jsonl"]:
        raise ValueError(f"{name} pass {index + 1}: report differs from recording")
    provenance = {"run": str(path.relative_to(ROOT)), "sha256": hashes,
                  "published_report": {"path": str(report_path.relative_to(ROOT)), "sha256": sha(report_path)}}
    return run, report, provenance


def standalone_pass(args):
    name, index, auc = args
    run, report, provenance = load_pass(name, index)
    own, gap = verify_standalone(prepare({name: run}), name, run)
    compare_published(integrate(own, name, None, "freshest", auc["primary"]), report, name,
                      auc["integration"]["tolerance"])
    config = report["config"]
    return {"pass": index + 1, "provenance": provenance, "nominal_gap_points": gap,
            "started_at_utc": report["started_at_utc"], "served": report["models_returned"],
            "config": {key: config.get(key) for key in ("provider", "model", "reasoning_effort", "thinking",
                                                         "workers", "request_timeout_s", "max_attempts")},
            "auc": {"overall": report["auc"]["primary"]["overall"],
                    "by_family": {family: report["auc"]["primary"]["by_family"][family]["accuracy"]
                                  for _, family in FAMILIES}},
            "untimed": report["scores"]["overall"]["untimed_decision_accuracy"],
            "latency_s": {key: report["latency_s"][key] for key in ("p50", "p95")},
            "reliability": {key: report["retry_reliability"][key]
                            for key in ("attempts", "failed_attempts", "retried_logical_requests")},
            "refused_answers": len(report.get("refused_answers") or [])}


def composition_pass(args):
    fast, slow, index, policies, auc = args
    runs = {fast: load_pass(fast, index)[0], slow: verified_run(ROOT / "runs" / HOSTED_PASSES[slow][index][1])[0]}
    scenarios = prepare(runs)
    result = {"pass": index + 1, "alone": {name: integrate(scenarios, name, None, "freshest", auc)["overall"]["accuracy"]
                                           for name in (fast, slow)}, "systems": {}}
    for policy in policies:
        integrated = integrate(scenarios, fast, slow, policy, auc)
        integrated.pop("curve", None)
        result["systems"][policy] = {"integrated": integrated,
                                     "fixed_two": aggregate([evaluate(sc, fast, slow, 2, policy) for sc in scenarios])}
    return result


def manuscript_run(name, index):
    if name in HOSTED_PASSES:
        return ROOT / "runs" / HOSTED_PASSES[name][index][1]
    manifest = json.loads((ROOT / "docs/research/manuscript-three-pass/analysis.json").read_text())
    return ROOT / manifest["passes"][index]["provenance"][name]["run"]


def conditions(auc):
    return [("Primary", auc["primary"])] + [(c["name"], c) for c in auc["sensitivity"]]


def integrate_linear(scenarios, fast, slow, policy, lo, hi):
    """Linear-weight counterpart of lite_trajectory_value.integrate, on the same exact pieces.

    Between release/arrival-order crossings each normalized fraction is c0 + c1/delta,
    whose linear integral over [a, b] is c0 (b - a) + c1 ln(b / a).
    """
    rows = []
    for sc in scenarios:
        slopes = [r / sc.tick_s for r in sc.releases_s]
        lines = [(s, 0.0) for s in slopes] + [(len(sc.gold), 0.0)]
        for name in [fast] if slow is None else [fast, slow]:
            lines += list(zip(slopes, sc.components[name].delays_s, strict=True))
        breaks = {lo, hi}
        for i, (a, b) in enumerate(lines):
            for c, d in lines[i + 1:]:
                if a != c and lo < (d - b) / (a - c) < hi:
                    breaks.add((d - b) / (a - c))
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
            if float(np.max(np.abs(c0 + c1 / z - vz))) > 1e-9:
                raise ValueError(f"{sc.episode_id}: affine span identity failed")
            total += c0 * (b - a) + c1 * math.log(b / a)
        rows.append({"episode_id": sc.episode_id, "task_family": sc.family,
                     **dict(zip(METRICS, map(float, total / (hi - lo)), strict=True))})
    return aggregate(rows)


def area(scenarios, fast, slow, policy, condition):
    if condition["weighting"] == "log":
        return integrate(scenarios, fast, slow, policy, condition)["overall"]["accuracy"]
    return integrate_linear(scenarios, fast, slow, policy, condition["min_s"], condition["max_s"])["overall"]["accuracy"]


def sensitivity_pass(args):
    """Every evaluation condition for one composed system, with matching pass indices."""
    fast, slow, rule, index, auc = args
    runs = {name: verified_run(manuscript_run(name, index))[0] for name in (fast, slow)}
    scenarios = prepare(runs)
    singles = {name: aggregate([evaluate(sc, name, None, 2) for sc in scenarios])["overall"]["accuracy"]
               for name in (fast, slow)}
    return {"areas": {key: area(scenarios, fast, slow, rule, c) for key, c in conditions(auc)},
            "two": aggregate([evaluate(sc, fast, slow, 2, rule) for sc in scenarios])["overall"]["accuracy"],
            "singles_two": singles}


def single_areas(report_paths, auc):
    """Three-pass means of the published original-clock areas under every condition."""
    reports = [json.loads((ROOT / path).read_text()) for path in report_paths]
    return {key: mean((r["auc"]["primary"] if key == "Primary" else r["auc"]["sensitivity"][key])["overall"]["accuracy"]
                      for r in reports) for key, _ in conditions(auc)}


def sensitivity(data, pool, auc):
    """Compare headline systems with every single setting under every declared condition."""
    manifest = json.loads((ROOT / "docs/research/manuscript-three-pass/analysis.json").read_text())
    singles = {name: single_areas([row["provenance"][name]["published_report"]["path"] for row in manifest["passes"]], auc)
               for name in manifest["passes"][0]["provenance"]}
    singles.update({name: single_areas([p["provenance"]["published_report"]["path"] for p in row["passes"]], auc)
                    for name, row in data["standalone"].items()})
    best = data["best_system"]
    systems = [("Jev", "TerraNone", "freshest"), ("KevTwentySeven", "TerraNone", "freshest"),
               (best["fast"], best["slow"], best["rule"])]
    jobs = [(*system, index, auc) for system in systems for index in range(PASSES)]
    rows = list(pool.map(sensitivity_pass, jobs))
    result = {"singles": singles, "systems": {}}
    for system in systems:
        passes = [row for job, row in zip(jobs, rows) if job[:3] == system]
        areas = {key: mean(p["areas"][key] for p in passes) for key, _ in conditions(auc)}
        above = [key for key, _ in conditions(auc) if areas[key] > max(s[key] for s in singles.values())]
        result["systems"]["+".join(system)] = {"fast": system[0], "slow": system[1], "rule": system[2],
            "areas": areas, "two": mean(p["two"] for p in passes), "above_every_single": above}
        for name in system[:2]:
            result.setdefault("singles_two", {})[name] = mean(p["singles_two"][name] for p in passes)
    return result


def summarize(passes):
    keys = passes[0]["auc"]["overall"].keys()
    return {"auc": {key: mean(p["auc"]["overall"][key] for p in passes) for key in keys},
            "auc_sd": stdev(p["auc"]["overall"]["accuracy"] for p in passes),
            "by_family": {family: mean(p["auc"]["by_family"][family] for p in passes) for _, family in FAMILIES},
            "untimed": mean(p["untimed"] for p in passes),
            "latency_s": {key: mean(p["latency_s"][key] for p in passes) for key in ("p50", "p95")},
            "failed_attempts": sum(p["reliability"]["failed_attempts"] for p in passes),
            "refused_answers": sum(p["refused_answers"] for p in passes)}


def analyze():
    policy = json.loads(POLICY_PATH.read_text())
    hosted = json.loads((ROOT / "paper/analysis/trajectory_policy.json").read_text())
    auc = json.loads((ROOT / "paper/analysis/evaluation_policy.json").read_text())
    with ProcessPoolExecutor(initializer=isolate_worker) as pool:
        jobs = [(name, index, auc) for name in policy["settings"] for index in range(PASSES)]
        rows = list(pool.map(standalone_pass, jobs))
        standalone = {name: {"label": HOSTED_LABELS[name],
                             "passes": [r for r, (n, _, _) in zip(rows, jobs) if n == name]}
                      for name in policy["settings"]}
        for name, row in standalone.items():
            row.update(summarize(row["passes"]))
        interval = auc["recording_interval_s"]
        fast = [name for name in policy["decision_interfaces"] if standalone[name]["latency_s"]["p50"] < interval]
        jobs = [(f, s, index, hosted["policies"], auc["primary"])
                for f in fast for s in hosted["slow_settings"] for index in range(PASSES)]
        rows = list(pool.map(composition_pass, jobs))
        systems = {}
        for (f, s, _, _, _), row in zip(jobs, rows):
            systems.setdefault(f, {}).setdefault(s, []).append(row)
        data = {"policy": policy, "correctors": hosted["slow_settings"], "rules": hosted["policies"],
                "fast_components": fast, "standalone": standalone,
                "systems": summarize_systems(systems, hosted["policies"])}
        best = max(((f, s, rule) for f, pairs in data["systems"].items() for s in pairs for rule in hosted["policies"]),
                   key=lambda k: data["systems"][k[0]][k[1]][k[2]]["integrated"]["overall"]["accuracy"])
        data["best_system"] = {"fast": best[0], "slow": best[1], "rule": best[2]}
        data["sensitivity"] = sensitivity(data, pool, auc)
    data["verification"] = {"max_nominal_recorded_gap_points":
                            max(p["nominal_gap_points"] for row in standalone.values() for p in row["passes"])}
    data["sources_sha256"] = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in (
        "paper/analysis/lite_later.py", "paper/analysis/later_policy.json",
        "paper/analysis/trajectory_policy.json", "paper/analysis/evaluation_policy.json",
        "paper/analysis/lite_trajectory_value.py", "paper/analysis/trajectory_replay.py",
        "paper/analysis/leaderboard_models.py", "paper/analysis/lite_openweight.py", "paper/analysis/lite_numbers.py",
        "src/streamdecisionbench/lite/scoring.py", "src/streamdecisionbench/lite/retry_scoring.py",
        "src/streamdecisionbench/lite/interval_scoring.py")}
    return data


def summarize_systems(systems, policies):
    """Equal means of matched passes for every fast/corrector pair and rule."""
    result = {}
    for f, pairs in systems.items():
        for s, passes in pairs.items():
            summary = {"alone": {name: mean(p["alone"][name] for p in passes) for name in (f, s)}}
            for rule in policies:
                values = [p["systems"][rule] for p in passes]
                areas = [v["integrated"]["overall"]["accuracy"] for v in values]
                summary[rule] = {"integrated": mean_evaluations([v["integrated"] for v in values]),
                                 "fixed_two": mean_evaluations([v["fixed_two"] for v in values]),
                                 "per_pass": areas, "auc_sample_sd": stdev(areas)}
            result.setdefault(f, {})[s] = summary
    return result


SETTING_MACROS = {"Perplexity": "Perplexity", "Glide": "Glide", "LunaDecisions": "LunaDecisions",
                  "Clef": "Clef", "ClefFlash": "ClefFlash", "HaikuLow": "Haiku", "HaikuNoThink": "HaikuOff"}
CORRECTOR_LABELS = {"Luna": "Luna low", "LunaNone": "Luna none", "Terra": "Terra low",
                    "TerraNone": "Terra none", "Astra": "Astra low"}
WORDS = {4: "four", 5: "five", 6: "six", 7: "seven", 20: "twenty", 60: "sixty"}
SHORT_LABELS = {"Perplexity": "Perplexity", "LunaDecisions": "GPT-6-Luna", "Clef": "Clef", "ClefFlash": "Clef Flash"}
SETTING_LABELS = {"Jev": "Jev", "TerraNone": "Terra none", "KevTwentySeven": "Kev-27B", **CORRECTOR_LABELS}
SYSTEM_MACROS = {"Jev+TerraNone+freshest": "JevTerraNone", "KevTwentySeven+TerraNone+freshest": "KevTerraNone"}


def write_tex(data):
    numbers = ["% Generated by paper/analysis/lite_later.py; do not edit."]
    def add(name, value, source):
        numbers.extend([f"% {REPORT}: {source}", f"\\newcommand{{\\Later{name}}}{{{value}}}"])
    add("NumSettingsWord", WORDS[len(data["standalone"])], "policy.settings")
    add("NumFastWord", WORDS[len(data["fast_components"])], "fast_components")
    systems = len(data["fast_components"]) * len(data["correctors"]) * len(data["rules"])
    add("NumSystemsWord", WORDS[systems], "fast components x correctors x rules")
    add("NominalGap", fixed(data["verification"]["max_nominal_recorded_gap_points"], 3),
        "verification.max_nominal_recorded_gap_points")
    for name, row in data["standalone"].items():
        key = SETTING_MACROS[name]
        # Two decimals match the headline table; one decimal matches Table 1 and the prose.
        for suffix, value in [("Auc", pct(row["auc"]["accuracy"])), ("AucOne", pct1(row["auc"]["accuracy"])),
                              ("AucSD", fixed(100 * row["auc_sd"], 2)),
                              ("Untimed", pct1(row["untimed"])), ("Oracle", pct1(row["auc"]["oracle"])),
                              ("Stale", pct1(row["auc"]["stale"])), ("Judgment", pct1(row["auc"]["judgment"])),
                              ("Compound", pct1(row["auc"]["compound"])),
                              ("Median", fixed(row["latency_s"]["p50"], 2)), ("Tail", fixed(row["latency_s"]["p95"], 2)),
                              ("FailedAttempts", str(row["failed_attempts"]))]:
            add(key + suffix, value, f"standalone.{name}")
        for prefix, family in FAMILIES:
            add(key + prefix + "Auc", pct1(row["by_family"][family]), f"standalone.{name}.by_family.{family}")
    for fast, pairs in data["systems"].items():
        for slow, summary in pairs.items():
            for rule in data["rules"]:
                name = SETTING_MACROS[fast] + slow + POLICY_MACROS[rule]
                add(name + "Auc", pct(summary[rule]["integrated"]["overall"]["accuracy"]),
                    f"systems.{fast}.{slow}.{rule}.integrated.overall.accuracy")
                add(name + "SD", fixed(100 * summary[rule]["auc_sample_sd"], 2), f"systems.{fast}.{slow}.{rule}.auc_sample_sd")
    best = data["best_system"]
    best_row = data["systems"][best["fast"]][best["slow"]][best["rule"]]
    add("BestFastLabel", data["standalone"][best["fast"]]["label"], "best_system.fast")
    add("BestSlowLabel", CORRECTOR_LABELS[best["slow"]], "best_system.slow")
    add("BestAuc", pct(best_row["integrated"]["overall"]["accuracy"]), "best_system")
    add("BestSD", fixed(100 * best_row["auc_sample_sd"], 2), "best_system")
    sens = data["sensitivity"]
    keys = list(next(iter(sens["systems"].values()))["areas"])
    add("SensConditionsWord", WORDS.get(len(keys), str(len(keys))), "sensitivity: evaluation_policy conditions")
    rows = []
    for name in ("KevTwentySeven", best["fast"]):
        label = SETTING_LABELS.get(name) or data["standalone"][name]["label"] + r"$^\dagger$"
        for key in keys:
            add(f"Sens{name}{key}", pct1(sens["singles"][name][key]), f"sensitivity.singles.{name}.{key}")
        add(f"Sens{name}Two", pct1(sens["singles_two"][name]), f"sensitivity.singles_two.{name}")
        rows.append(" & ".join([label, *[f"\\LaterSens{name}{key}" for key in keys], f"\\LaterSens{name}Two"]) + r" \\")
    for system, row in sens["systems"].items():
        name = SYSTEM_MACROS.get(system, "Best")
        label = " + ".join(SETTING_LABELS.get(part) or data["standalone"][part]["label"] + r"$^\dagger$"
                           for part in (row["fast"], row["slow"]))
        for key in keys:
            add(f"Sens{name}{key}", pct1(row["areas"][key]), f"sensitivity.systems.{system}.areas.{key}")
        add(f"Sens{name}Two", pct1(row["two"]), f"sensitivity.systems.{system}.two")
        above = len(row["above_every_single"])
        add(f"Sens{name}AboveWord", WORDS.get(above, str(above)), f"sensitivity.systems.{system}.above_every_single")
        rows.append(" & ".join([label, *[f"\\LaterSens{name}{key}" for key in keys], f"\\LaterSens{name}Two"]) + r" \\")
    (ROOT / "paper/generated/later_numbers.tex").write_text("\n".join(numbers) + "\n")
    sensitivity_rows = rows
    tables = ["% Generated by paper/analysis/lite_later.py; do not edit."]
    rows = []
    for name, row in data["standalone"].items():
        key = SETTING_MACROS[name]
        rows.append(" & ".join([row["label"], *[f"\\Later{key}{prefix}Auc" for prefix, _ in FAMILIES],
            f"\\Later{key}AucOne~$\\pm$~\\Later{key}AucSD", f"\\Later{key}Untimed", f"\\Later{key}Median",
            f"\\Later{key}Stale", f"\\Later{key}Judgment"]) + r" \\")
    tables.append("\\newcommand{\\TabLaterStandalone}{%\n" + "\n".join(rows) + "\n}")
    rows = []
    for fast, pairs in data["systems"].items():
        for index, slow in enumerate(pairs):
            name = SETTING_MACROS[fast] + slow
            rows.append(" & ".join([SHORT_LABELS[fast] if index == 0 else "", CORRECTOR_LABELS[slow],
                *[f"\\Later{name}{POLICY_MACROS[rule]}Auc" for rule in data["rules"]]]) + r" \\")
    tables.append("\\newcommand{\\TabLaterSystems}{%\n" + "\n".join(rows) + "\n}")
    tables.append("\\newcommand{\\TabLaterSensitivityBody}{%\n" + "\n".join(sensitivity_rows) + "\n}")
    (ROOT / "paper/generated/later_tables.tex").write_text("\n".join(tables) + "\n")


def main():
    data = analyze()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "analysis.json").write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    write_tex(data)
    best = data["best_system"]
    print(f"Later hosted settings: {len(data['standalone'])} standalone, best system "
          f"{best['fast']} + {best['slow']} ({best['rule']})", flush=True)


if __name__ == "__main__":
    main()
