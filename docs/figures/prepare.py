"""Publish verified single-model leaderboard data and original-clock curves."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "paper/analysis"))

from leaderboard_models import HOSTED_MODELS
from lite_hosted import load_summary
from lite_openweight import verified_run, verify_standalone
from trajectory_replay import aggregate, evaluate, prepare

SUMMARY = ROOT / "docs/research/openweight-hybrids/analysis.json"
OUT = Path(__file__).with_name("data.json")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    summary = json.loads(SUMMARY.read_text())
    hosted_summary = load_summary()
    for filename, expected in summary["sources_sha256"].items():
        if sha(ROOT / filename) != expected:
            raise ValueError(f"Stale analysis source: {filename}; regenerate the analysis first")
    specs = summary["policy"]["settings"]
    names = [*summary["hosted"], *summary["standalone"]]
    hosted_names = {name for name, _, _ in HOSTED_MODELS}
    local_names = {spec["name"] for spec in specs}
    if (set(summary["hosted"]) != hosted_names or set(summary["standalone"]) != local_names
            or len(names) != len(set(names))):
        raise ValueError("The leaderboard requires every registered hosted and self-hosted setting exactly once")
    provenance = {}
    intervals = sorted(set(np.geomspace(.5, 8, 161).tolist()) | {.5, 1., 2., 4., 8.})
    series = []
    for name in names:
        hosted = name in summary["hosted"]
        row = hosted_summary["hosted"][name] if hosted else summary["standalone"][name]
        sources = [p["provenance"] for p in row["passes"]]
        curves, areas = [], []
        for source in sources:
            run, hashes = verified_run(ROOT / source["run"])
            if hashes != source["sha256"]:
                raise ValueError(f"{name}: recorded evidence changed")
            report_source = source["published_report"]
            report_path = ROOT / report_source["path"]
            if sha(report_path) != report_source["sha256"]:
                raise ValueError(f"{name}: published analysis changed")
            report = json.loads(report_path.read_text())
            if report["events_sha256"] != hashes["events.jsonl"]:
                raise ValueError(f"{name}: report uses a different recording")
            auc = report["auc"]["primary"]
            if (auc["min_s"], auc["max_s"], auc["weighting"], auc["network_s"]) != (.5, 8, "log", 0):
                raise ValueError(f"{name}: incompatible primary metric")
            scenarios = prepare({name: run})
            own, _ = verify_standalone(scenarios, name, run)
            curve = [aggregate([evaluate(sc, name, None, interval) for sc in own])["overall"]["accuracy"]
                     for interval in intervals]
            if any(not 0 <= value <= 1 for value in curve):
                raise ValueError(f"{name}: invalid curve values")
            if abs(curve[intervals.index(2.)] - run["scores"]["overall"]["time_accuracy"]) > 1e-12:
                raise ValueError(f"{name}: curve does not reproduce recorded-cadence evaluation")
            curves.append(curve)
            areas.append(auc["overall"]["accuracy"])
        expected = row["accuracy"] if hosted else row["integrated"]["overall"]["accuracy"]
        if abs(float(np.mean(areas)) - expected) > summary["auc_policy"]["integration"]["tolerance"]:
            raise ValueError(f"{name}: primary score disagrees with the verified summary")
        provenance[name] = sources
        label = row["label"] if hosted else row["spec"]["label"]
        series.append({"id": name, "label": label, "deployment": "hosted" if hosted else "self-hosted",
                       "passes": len(sources), "latency_s": row["latency_s"], "log_auc_pct": 100 * expected,
                       "log_auc_sd_pct": 100 * float(np.std(areas, ddof=1)), "untimed_pct": 100 * row["untimed"],
                       "accuracy_pct": (100 * np.mean(curves, axis=0)).tolist(),
                       "report": "docs/lite/results/hosted-api-repeats-20261003/README.md" if hosted else "docs/research/openweight-hybrids/README.md"})
        print(f"Verified {name}: {100 * expected:.2f}% log-AUC; {len(sources)} passes", flush=True)
    series.sort(key=lambda row: -row["log_auc_pct"])
    sources = ["docs/figures/prepare.py", "paper/analysis/leaderboard_models.py", "paper/analysis/lite_openweight.py",
               "paper/analysis/trajectory_replay.py", "paper/analysis/evaluation_policy.json", "paper/analysis/lite_hosted.py"]
    return {"benchmark": "StreamDecisionBench", "metric": "Normalized log-AUC over 0.5–8 s (%)",
            "states": 480, "scenarios": 8, "families": 4, "passes_per_setting": {row["id"]: row["passes"] for row in series},
            "clock": "original recorded release clock; successful-attempt latency and commit lag retained",
            "weighting": "equal scenarios within each family, then equal families; logarithmic interval weighting",
            "intervals_s": intervals, "series": series, "provenance": provenance,
            "summary": {"path": str(SUMMARY.relative_to(ROOT)), "sha256": sha(SUMMARY)},
            "hosted_summary": {"path": "docs/lite/results/hosted-api-repeats-20261003/analysis.json", "sha256": sha(ROOT / "docs/lite/results/hosted-api-repeats-20261003/analysis.json")},
            "sources_sha256": {filename: sha(ROOT / filename) for filename in sources}}


def main() -> None:
    result = build()
    OUT.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(f"Wrote {OUT.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
