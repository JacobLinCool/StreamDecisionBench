"""Publish verified single-model leaderboard data and original-clock curves."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "paper/analysis"))

from lite_openweight import original_clock, verified_run, verify_standalone
from trajectory_replay import aggregate, evaluate, prepare

SUMMARY = ROOT / "docs/research/openweight-hybrids/analysis.json"
OUT = Path(__file__).with_name("data.json")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    summary = json.loads(SUMMARY.read_text())
    for filename, expected in summary["sources_sha256"].items():
        if sha(ROOT / filename) != expected:
            raise ValueError(f"Stale analysis source: {filename}; regenerate the analysis first")
    specs = summary["policy"]["settings"]
    names = [*summary["hosted"], *summary["standalone"]]
    if len(names) != 15 or len(set(names)) != 15:
        raise ValueError("The leaderboard requires all six hosted and nine self-hosted settings")
    runs, reports, provenance = {}, {}, {}
    for name in names:
        source = summary["provenance"][name]
        path = ROOT / source["run"]
        runs[name], hashes = verified_run(path)
        if hashes != source["sha256"]:
            raise ValueError(f"{name}: recorded evidence changed")
        report_source = source["published_report"]
        report_path = ROOT / report_source["path"]
        if sha(report_path) != report_source["sha256"]:
            raise ValueError(f"{name}: published analysis changed")
        reports[name] = json.loads(report_path.read_text())
        if reports[name]["events_sha256"] != hashes["events.jsonl"]:
            raise ValueError(f"{name}: report uses a different recording")
        provenance[name] = {"run": source["run"], "sha256": hashes,
                            "published_report": report_source}
    scenarios = prepare(runs)
    intervals = sorted(set(np.geomspace(.5, 8, 161).tolist()) | {.5, 1., 2., 4., 8.})
    series = []
    for name in names:
        run = runs[name]
        verify_standalone(scenarios, name, run)
        own = original_clock(scenarios, run)
        report = reports[name]
        auc = report["auc"]["primary"]
        if (auc["min_s"], auc["max_s"], auc["weighting"], auc["network_s"]) != (.5, 8, "log", 0):
            raise ValueError(f"{name}: incompatible primary metric")
        hosted = name in summary["hosted"]
        row = summary["hosted"][name] if hosted else summary["standalone"][name]
        expected = row["accuracy"] if hosted else row["integrated"]["overall"]["accuracy"]
        if abs(auc["overall"]["accuracy"] - expected) > summary["auc_policy"]["integration"]["tolerance"]:
            raise ValueError(f"{name}: primary score disagrees with the verified summary")
        accuracy = [aggregate([evaluate(sc, name, None, interval) for sc in own])["overall"]["accuracy"]
                    for interval in intervals]
        if any(not 0 <= value <= 1 for value in accuracy):
            raise ValueError(f"{name}: invalid curve values")
        fixed_two = accuracy[intervals.index(2.)]
        if abs(fixed_two - run["scores"]["overall"]["time_accuracy"]) > 1e-12:
            raise ValueError(f"{name}: curve does not reproduce recorded-cadence evaluation")
        label = row["label"] if hosted else next(spec["label"] for spec in specs if spec["name"] == name)
        series.append({"id": name, "label": label, "deployment": "hosted" if hosted else "self-hosted",
                       "log_auc_pct": 100 * expected, "untimed_pct": 100 * row["untimed"],
                       "accuracy_pct": [100 * value for value in accuracy],
                       "report": provenance[name]["published_report"]["path"]})
        print(f"Verified {name}: {100 * expected:.2f}% log-AUC; {len(intervals)} curve points", flush=True)
    series.sort(key=lambda row: -row["log_auc_pct"])
    sources = ["docs/figures/prepare.py", "paper/analysis/lite_openweight.py",
               "paper/analysis/trajectory_replay.py", "paper/analysis/evaluation_policy.json"]
    return {"benchmark": "StreamDecisionBench", "metric": "Normalized log-AUC over 0.5–8 s (%)",
            "states": 480, "scenarios": 8, "families": 4, "passes_per_setting": 1,
            "clock": "original recorded release clock; successful-attempt latency and commit lag retained",
            "weighting": "equal scenarios within each family, then equal families; logarithmic interval weighting",
            "intervals_s": intervals, "series": series, "provenance": provenance,
            "summary": {"path": str(SUMMARY.relative_to(ROOT)), "sha256": sha(SUMMARY)},
            "sources_sha256": {filename: sha(ROOT / filename) for filename in sources}}


def main() -> None:
    result = build()
    OUT.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(f"Wrote {OUT.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
