"""Compare two verified SDB recordings with the same frozen data and protocol."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
from collections import Counter
from pathlib import Path

from lite_report import NAMES, ROOT, RETRY_PROTOCOL, analyze, command_path, model_label, relative_link


METRICS = (
    "untimed_decision_accuracy", "untimed_segment_accuracy", "time_accuracy",
    "segment_time_accuracy", "all_questions_exact_accuracy",
)
PAIR_KEYS = ("both_correct", "baseline_only_correct", "candidate_only_correct", "both_wrong")
# The compared model identity; every other config field must match.
MODEL_KEYS = ("provider", "model", "reasoning_effort")


def _score_comparison(baseline: dict, candidate: dict, latency_a: dict, latency_b: dict) -> dict:
    return {
        "baseline": {**{key: baseline[key] for key in METRICS}, "latency_s": latency_a},
        "candidate": {**{key: candidate[key] for key in METRICS}, "latency_s": latency_b},
        "candidate_minus_baseline": {
            **{f"{key}_pp": 100 * (candidate[key] - baseline[key]) for key in METRICS},
            **{f"latency_{key}_s": latency_b[key] - latency_a[key] for key in ("p50", "p95")},
        },
    }


def _paired_counts(a: dict, b: dict) -> dict[str, int]:
    if a["states"] != b["states"] or a["scenario_id"] != b["scenario_id"] or a["task_family"] != b["task_family"]:
        raise ValueError("paired episodes have different states, scenario, or family")
    n = a["states"]
    wrong_a = {m["t"] for m in a["mistakes"]}
    wrong_b = {m["t"] for m in b["mistakes"]}
    if not wrong_a <= set(range(n)) or not wrong_b <= set(range(n)):
        raise ValueError("mistake index is outside paired episode")
    return {
        "both_correct": n - len(wrong_a | wrong_b),
        "baseline_only_correct": len(wrong_b - wrong_a),
        "candidate_only_correct": len(wrong_a - wrong_b),
        "both_wrong": len(wrong_a & wrong_b),
    }


def _network_comparison(baseline: dict, candidate: dict) -> dict | None:
    """Both runs' network-removed estimates side by side; never rejects a comparison."""
    a, b = baseline.get("network_adjustment"), candidate.get("network_adjustment")
    if not a or not b:
        return None

    def scope(pick) -> dict:
        ranges = [[pick(net["scores"][k])["time_accuracy"] for k in ("estimate", "low", "high")] for net in (a, b)]
        (ea, la, ha), (eb, lb, hb) = ranges
        return {"baseline": {"estimate": ea, "low": la, "high": ha}, "candidate": {"estimate": eb, "low": lb, "high": hb},
                "candidate_minus_baseline_pp": 100 * (eb - ea), "ranges_overlap": la <= hb and lb <= ha}

    return {"method": a["method"],
            "network_s": {"baseline": a["network_s"], "candidate": b["network_s"]},
            "overall": scope(lambda block: block["overall"]),
            "by_family": {f: scope(lambda block, f=f: block["by_family"][f]) for f in a["scores"]["estimate"]["by_family"]}}


def compare(baseline: dict, candidate: dict) -> dict:
    """Compare outputs of analyze; never infer matching conditions from scores."""
    # Only conditions that change what a paired comparison means are required;
    # code versions are recorded per run, not matched.
    for key in ("time_basis", "episode_hashes"):
        if baseline[key] != candidate[key]:
            raise ValueError(f"runs differ in {key}; not a matched SDB comparison")
    protocol_a = {key: value for key, value in baseline["config"].items() if key not in MODEL_KEYS}
    protocol_b = {key: value for key, value in candidate["config"].items() if key not in MODEL_KEYS}
    if protocol_a != protocol_b:
        differences = sorted(key for key in protocol_a.keys() | protocol_b.keys() if protocol_a.get(key) != protocol_b.get(key))
        raise ValueError(f"run configurations differ beyond model: {', '.join(differences)}")
    rows_a = {row["episode_id"]: row for row in baseline["scores"]["per_episode"]}
    rows_b = {row["episode_id"]: row for row in candidate["scores"]["per_episode"]}
    if set(rows_a) != set(rows_b) or set(rows_a) != set(baseline["episode_order"]):
        raise ValueError("score episode sets do not match frozen data")
    pairs_by_family: dict[str, Counter] = {}
    pairs_overall: Counter = Counter()
    episodes = []
    for eid in baseline["episode_order"]:
        a, b = rows_a[eid], rows_b[eid]
        paired = _paired_counts(a, b)
        pairs_overall.update(paired)
        pairs_by_family.setdefault(a["task_family"], Counter()).update(paired)
        row = _score_comparison(
            a, b,
            {"p50": a["latency_s_p50"], "p95": a["latency_s_p95"]},
            {"p50": b["latency_s_p50"], "p95": b["latency_s_p95"]},
        )
        episodes.append({"episode_id": eid, "task_family": a["task_family"], "states": a["states"],
                         "paired_decision_counts": paired, **row})
    families = {}
    for family, a in baseline["scores"]["by_family"].items():
        b = candidate["scores"]["by_family"][family]
        families[family] = {
            "episodes": a["episodes"], "paired_decision_counts": dict(pairs_by_family[family]),
            **_score_comparison(a, b, baseline["latency_by_family_s"][family], candidate["latency_by_family_s"][family]),
        }

    def identity(data: dict) -> dict:
        identity = {key: data[key] for key in ("run", "config", "run_sources", "started_at_utc", "finished_at_utc", "models_returned",
                                             "events_sha256", "total_failed", "accepted_updates", "discarded_updates", "usage",
                                             "analysis_sources", "retry_reliability", "raw_wallclock_latency_s")}
        identity["raw_wallclock_overall"] = (data["raw_wallclock_scores"]["overall"] if data["raw_wallclock_scores"] is not None else None)
        return identity

    return {
        "baseline": identity(baseline), "candidate": identity(candidate),
        "time_basis": baseline["time_basis"],
        "same_recording": baseline["events_sha256"] == candidate["events_sha256"],
        "dataset_hash": baseline["dataset_hash"], "episode_hashes": baseline["episode_hashes"],
        "matched_config_excluding_model": protocol_a,
        "comparison_analysis_sources": {"scripts/lite/lite_compare.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        "verification": "Both complete runs re-scored from their own events with the current scorer; identical time basis, frozen episodes, and config except model identity (provider, model, reasoning effort). Each run's recorded source versions are kept in its identity.",
        "overall": {
            "episodes": baseline["scores"]["episodes"], "states": baseline["scores"]["states"],
            "paired_decision_counts": dict(pairs_overall),
            **_score_comparison(baseline["scores"]["overall"], candidate["scores"]["overall"], baseline["latency_s"], candidate["latency_s"]),
        },
        "by_family": families, "per_episode": episodes,
        "network_adjustment": _network_comparison(baseline, candidate),
        "interpretation": "Descriptive single-recording comparison. Adjacent states are dependent. Score and latency differences do not establish statistical significance, stable rankings, or causal effects of speed or model changes.",
    }


def render_report(data: dict, output: Path) -> str:
    """Render an English comparison while preserving the supplied analysis."""
    a, b = data["baseline"], data["candidate"]
    label_a, label_b = model_label(a["config"]), model_label(b["config"])
    normalized = a["config"]["protocol"] == RETRY_PROTOCOL
    pct = lambda value: f"{100 * value:.2f}%"

    def table_row(name: str, row: dict) -> str:
        first, second = row["baseline"], row["candidate"]
        return (f"| {name} | {pct(first['untimed_decision_accuracy'])} | {pct(second['untimed_decision_accuracy'])} "
                f"| {pct(first['time_accuracy'])} | {pct(second['time_accuracy'])} |")

    headings = [
        "| Scope | Baseline untimed | Candidate untimed | Baseline in-force | Candidate in-force |",
        "|---|---:|---:|---:|---:|",
    ]
    lines = [f"# SDB comparison: {label_a} and {label_b}", "",
             f"{data['overall']['episodes']} scenarios and {data['overall']['states']} matching states from the same frozen dataset. "
             "Both analyses re-score their original events. Episodes and execution settings match except model identity "
             "(provider, model and reasoning effort). The comparison JSON retains each recording's source versions.", "",
             ("The comparison uses reconstructed timelines excluding transport retries: successful-attempt durations "
              "start at evidence release and retain postprocessing time. Failed attempts, retry waits and dispatch "
              "queueing are excluded. Raw-clock diagnostics use a different time basis."
              if normalized else "The comparison uses each recording's original clock, retaining failures and waits."), "",
             "All duration scores below use the recording cadence; the public leaderboard uses log-AUC over 0.5–8 s.", ""]
    if data["same_recording"]:
        lines += ["This self-comparison validates the tool; it is not an experiment comparing two models.", ""]
    delta = data["overall"]["candidate_minus_baseline"]
    lines += [f"Baseline: **{label_a}**. Candidate: **{label_b}**.", "",
              f"Overall candidate minus baseline: **{delta['untimed_decision_accuracy_pp']:+.2f} percentage points** "
              f"untimed and **{delta['time_accuracy_pp']:+.2f} percentage points** in-force accuracy. "
              "Family and overall scores give scenarios equal weight. The JSON retains all differences.", "",
              "## Overall and families", "", *headings, table_row("Overall", data["overall"])]
    for family, row in data["by_family"].items():
        lines.append(table_row(NAMES[family], row))
    if (net := data.get("network_adjustment")):
        span = lambda r: f"{pct(r['estimate'])} ({pct(r['low'])}–{pct(r['high'])})"
        na, nb = net["network_s"]["baseline"], net["network_s"]["candidate"]
        lines += ["", "## Network-removed estimate (secondary)", "",
                  "Estimate the token-independent latency from each recording's fast envelope, subtract it from "
                  "each response and replay. This assumes network + prefill + decode where applicable; the remainder "
                  "can include fixed service time, so it is an upper bound on the network effect. "
                  f"Baseline network estimate {na['estimate']:.3f} s ({na['low']:.3f}–{na['high']:.3f}); "
                  f"candidate {nb['estimate']:.3f} s ({nb['low']:.3f}–{nb['high']:.3f}). "
                  "Parentheses show bootstrap ranges. Primary scores remain unchanged.", "",
                  "| Scope | Baseline network removed | Candidate network removed | Estimated difference | Ranges overlap |",
                  "|---|---:|---:|---:|---|"]
        for name, row in [("Overall", net["overall"]), *[(NAMES[f], r) for f, r in net["by_family"].items()]]:
            lines.append(f"| {name} | {span(row['baseline'])} | {span(row['candidate'])} | "
                         f"{row['candidate_minus_baseline_pp']:+.2f} pp | {'Yes' if row['ranges_overlap'] else 'No'} |")
    lines += ["", "## Matching scenarios", "", *headings]
    for row in data["per_episode"]:
        lines.append(table_row(row["episode_id"], row))
    lines += ["", "## Response latency", "",
              ("Only final successful-attempt durations are used; failures and retry waits are excluded. "
               if normalized else "Full request durations are used. ")
              + "Quantiles use all requests in each scope, rather than averaging scenario quantiles. "
              "Units are seconds and include client processing and the recorded service/network path.", "",
              "| Scope | Baseline p50 / p95 | Candidate p50 / p95 |", "|---|---:|---:|"]
    for name, row in [("Overall", data["overall"]), *[(NAMES[f], r) for f, r in data["by_family"].items()]]:
        first, second = row["baseline"]["latency_s"], row["candidate"]["latency_s"]
        lines.append(f"| {name} | {first['p50']:.2f} / {first['p95']:.2f} | {second['p50']:.2f} / {second['p95']:.2f} |")
    lines += ["", "## Paired decisions on identical states", "",
              "Untimed comparisons retain each model's own route; inactive answers do not affect correctness. "
              "The four columns partition all states. Adjacent states are dependent.", "",
              "| Scope | Both correct | Only baseline correct | Only candidate correct | Both wrong |",
              "|---|---:|---:|---:|---:|"]
    for name, row in [("Overall", data["overall"]), *[(NAMES[f], r) for f, r in data["by_family"].items()]]:
        values = row["paired_decision_counts"]
        lines.append(f"| {name} | " + " | ".join(str(values[key]) for key in PAIR_KEYS) + " |")
    config = data["matched_config_excluding_model"]
    if normalized:
        lines += ["", "## Transport reliability and raw clock", "",
                  "Attempt error rates divide by all physical attempts, including final successes. Logical retry "
                  "rates divide by all released states. Raw-clock diagnostics retain failures, waits and actual delivery order.", "",
                  "| Metric | Baseline | Candidate |", "|---|---:|---:|"]
        rel_a, rel_b = a["retry_reliability"], b["retry_reliability"]
        for name, key, numerator, denominator in [
            ("Attempt error rate", "attempt_error_rate", "failed_attempts", "attempts"),
            ("Logical retry rate", "retried_logical_rate", "retried_logical_requests", "logical_requests"),
        ]:
            lines.append(f"| {name} | {rel_a[key]:.2%} ({rel_a[numerator]}/{rel_a[denominator]}) | {rel_b[key]:.2%} ({rel_b[numerator]}/{rel_b[denominator]}) |")
        lines.append(f"| Raw in-force accuracy | {a['raw_wallclock_overall']['time_accuracy']:.2%} | {b['raw_wallclock_overall']['time_accuracy']:.2%} |")
        la, lb = a["raw_wallclock_latency_s"], b["raw_wallclock_latency_s"]
        lines.append(f"| Raw request p50 / p95 (s) | {la['p50']:.2f} / {la['p95']:.2f} | {lb['p50']:.2f} / {lb['p95']:.2f} |")
    lines += ["", "## Execution and interpretation", "",
              f"- Protocol: {config['protocol']}; workers: {config['workers']}; timeout: {config['request_timeout_s']:g} s; SDK retries: {config['sdk_retries']}.",
              f"- {label_a}: {a['total_failed']} failed requests, {a['accepted_updates']} accepted updates.",
              f"- {label_b}: {b['total_failed']} failed requests, {b['accepted_updates']} accepted updates.",
              f"- Served model names: {json.dumps(a['models_returned'], ensure_ascii=False)}; {json.dumps(b['models_returned'], ensure_ascii=False)}.", "",
              "One recording per model and scenario. Differences do not establish significance, stable rankings or "
              "causal effects of model speed. Recordings occurred at different times and may have different service "
              "and network conditions. In-force accuracy depends jointly on answers, delays, acceptance and reference "
              "dwell times. Untimed scores use the same responses, without additional calls or question edits.", "",
              "## Reproduction files", "",
              *(["- [Recorded error witnesses](FINDINGS.md)"] if (output / "FINDINGS.md").exists() else []),
              *(["- [Candidate recording report](REPORT.md)"] if (output / "REPORT.md").exists() else []),
              f"- [{label_a} frozen run]({relative_link(ROOT / a['run'] / 'run.json', output)})",
              f"- [{label_b} frozen run]({relative_link(ROOT / b['run'] / 'run.json', output)})",
              "- [Complete comparison data](comparison.json)", "",
              "Reproduce from the repository root:", "", "```sh",
              shlex.join(["uv", "run", "python", "scripts/lite/lite_compare.py", "--baseline", command_path(ROOT / a["run"]),
                          "--candidate", command_path(ROOT / b["run"]), "--out", command_path(output)]),
              "```", ""]
    return "\n".join(lines)


def report(data: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "COMPARISON.md").write_text(render_report(data, output))
    (output / "comparison.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report(compare(analyze(args.baseline), analyze(args.candidate)), args.out)
