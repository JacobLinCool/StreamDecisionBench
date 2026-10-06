"""Verify and aggregate the public hosted repeats without querying any model."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import statistics

from leaderboard_models import HOSTED_LABELS, HOSTED_PASSES, HOSTED_REPEAT_COHORT
from lite_numbers import FAMILIES, POLICY

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/lite/results" / HOSTED_REPEAT_COHORT


def aggregate_passes(name: str, model: str, records: list[dict]) -> dict:
    families = {family: {key: statistics.mean(r["primary"]["by_family"][family][key] for r in records)
                         for key in records[0]["primary"]["by_family"][family]}
                for _, family in FAMILIES}
    aucs = [r["primary"]["overall"]["accuracy"] for r in records]
    return {"label": HOSTED_LABELS[name], "model": model,
        "report": f"{HOSTED_REPEAT_COHORT}/README.md", "passes": records,
        "accuracy": statistics.mean(aucs), "auc_sample_sd": statistics.stdev(aucs) if len(aucs) > 1 else None,
        "untimed": statistics.mean(r["untimed"] for r in records), "by_family": families,
        "latency_s": {q: statistics.mean(r["latency_s"][q] for r in records) for q in records[0]["latency_s"]}}


def analyze() -> dict:
    from lite_openweight import compare_published, sha, verified_run, verify_standalone
    from lite_trajectory_value import integrate
    from trajectory_replay import prepare
    from lite_report import analyze as analyze_recording

    hosted = {}
    for name, specs in HOSTED_PASSES.items():
        records, runs = [], {}
        for index, (folder, path) in enumerate(specs, 1):
            run, hashes = verified_run(ROOT / "runs" / path)
            runs[str(index)] = run
            report_path = ROOT / "docs/lite/results" / folder / "analysis.json"
            report = json.loads(report_path.read_text())
            if (report["events_sha256"] != hashes["events.jsonl"] or report["config"] != run["frozen"]["config"]
                    or report["dataset_hash"] != run["frozen"]["dataset_manifest"]["dataset_hash"]
                    or report["evaluation_policy"] != POLICY):
                raise ValueError(f"{name}/pass{index}: report differs from recording or evaluation policy")
            raw = analyze_recording(ROOT / "runs" / path)
            for key in ("latency_s", "models_returned", "retry_reliability", "scores"):
                if raw[key] != report[key]:
                    raise ValueError(f"{name}/pass{index}: published {key} differs from recorded evidence")
            auc = report["auc"]["primary"]
            if (auc["min_s"], auc["max_s"], auc["weighting"], auc["network_s"]) != (.5, 8, "log", 0):
                raise ValueError(f"{name}/pass{index}: incompatible primary metric")
            own, _ = verify_standalone(prepare({name: run}), name, run)
            independent = integrate(own, name, None, "freshest", POLICY["primary"])
            compare_published(independent, report, f"{name}/pass{index}", POLICY["integration"]["tolerance"])
            if index > 1 and run["frozen"]["config"] != runs["1"]["frozen"]["config"]:
                raise ValueError(f"{name}: execution settings differ across passes")
            records.append({"pass": index, "primary": auc,
                "untimed": raw["scores"]["overall"]["untimed_decision_accuracy"],
                "latency_s": raw["latency_s"], "served_models": sorted(raw["models_returned"]),
                "retry_reliability": raw["retry_reliability"],
                "provenance": {"run": f"runs/{path}", "sha256": hashes,
                    "published_report": {"path": str(report_path.relative_to(ROOT)), "sha256": sha(report_path)}}})
            print(f"Verified {name}/pass{index}: {100*auc['overall']['accuracy']:.4f}%", flush=True)
        prepare(runs)  # All repeats must use identical frozen episode content.
        hosted[name] = aggregate_passes(name, runs["1"]["frozen"]["config"]["model"], records)
    return {"evaluation_policy": POLICY, "hosted": hosted,
        "aggregation": "equal mean of per-pass metrics; mean of within-pass latency quantiles; sample SD across passes",
        "sources_sha256": {p: sha(ROOT / p) for p in (
            "paper/analysis/lite_hosted.py", "paper/analysis/leaderboard_models.py",
            "paper/analysis/evaluation_policy.json", "paper/analysis/lite_openweight.py",
            "paper/analysis/lite_trajectory_value.py", "paper/analysis/trajectory_replay.py",
            "scripts/lite/lite_report.py")}}


def load_summary() -> dict:
    from lite_openweight import sha

    data = json.loads((OUT / "analysis.json").read_text())
    if set(data["hosted"]) != set(HOSTED_PASSES):
        raise ValueError("Hosted summary must include every registered setting")
    for path, checksum in data["sources_sha256"].items():
        if sha(ROOT / path) != checksum:
            raise ValueError(f"Stale hosted summary source: {path}; regenerate lite_hosted.py")
    for name, row in data["hosted"].items():
        if len(row["passes"]) != len(HOSTED_PASSES[name]):
            raise ValueError(f"{name}: incorrect repeat count")
        for index, (record, (folder, run)) in enumerate(zip(row["passes"], HOSTED_PASSES[name], strict=True), 1):
            source = record["provenance"]
            if record["pass"] != index or source["run"] != f"runs/{run}" or source["published_report"]["path"] != f"docs/lite/results/{folder}/analysis.json":
                raise ValueError(f"{name}: repeat registry differs from summary")
            for file, checksum in source["sha256"].items():
                if sha(ROOT / source["run"] / file) != checksum:
                    raise ValueError(f"{name}: recorded evidence changed")
            report = source["published_report"]
            if sha(ROOT / report["path"]) != report["sha256"]:
                raise ValueError(f"{name}: published report changed")
            measured = json.loads((ROOT / report["path"]).read_text())
            if (record["primary"] != measured["auc"]["primary"] or record["latency_s"] != measured["latency_s"]
                    or record["untimed"] != measured["scores"]["overall"]["untimed_decision_accuracy"]):
                raise ValueError(f"{name}: per-pass metrics differ from published report")
        if row != aggregate_passes(name, row["model"], row["passes"]):
            raise ValueError(f"{name}: aggregate differs from independently evaluated passes")
    return data


def publish(data: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "analysis.json").write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    lines = ["# Hosted API repeated measurements", "",
        "Wity auto and off each have one complete pass; all other hosted settings have three. Wity uses 16 workers and the recorded Retry-After policy; other hosted settings use 32 workers. Each pass covers the same 480 states in eight scenarios and four families. The original repeat cohort's 7,200 additional requests succeeded without retries. Astra low has a further third pass; its transport attempts are preserved in the individual report. Wity auto recovered 26 HTTP 429 rejections and one timeout; Wity off had no failed attempts. Perplexity's first pass recovered 12 timeouts and three HTTP 503 failures; its second and third passes had no failed attempts. GLiDE completed all 1,440 logical requests across three passes without failed attempts or retries.", "",
        "Scores are equal means of independently integrated log-AUC over 0.5–8 s. SD is sample standard deviation across passes, in percentage points; it is unavailable for a single pass. Latency values average within-pass quantiles.", "",
        "| Setting | Passes | Mean log-AUC ± SD (%) | Mean untimed (%) | Mean p50 / p95 (s) | Individual log-AUC (%) |",
        "|---|---:|---:|---:|---:|---|"]
    for row in sorted(data["hosted"].values(), key=lambda r: -r["accuracy"]):
        links = [f"[{100*r['primary']['overall']['accuracy']:.2f}]({Path(os.path.relpath((ROOT / r['provenance']['published_report']['path']).with_name('REPORT.md'), OUT)).as_posix()})"
                 for r in row["passes"]]
        lines.append(f"| {row['label']} | {len(row['passes'])} | {100*row['accuracy']:.2f}"
                     + (f" ± {100*row['auc_sample_sd']:.2f}" if row['auc_sample_sd'] is not None else " (one pass)") + " | "
                     f"{100*row['untimed']:.2f} | {row['latency_s']['p50']:.3f} / {row['latency_s']['p95']:.3f} | {', '.join(links)} |")
    lines += ["", "These are descriptive measurements on a fixed dataset; two or three passes do not establish stable rankings. Served model identifiers are preserved in each analysis; Jev returned `jev-1.13.0` on every pass. Matching identifiers do not guarantee immutable provider backends.", "",
        "The manuscript evaluates six hosted and nine self-hosted settings with three passes each, pairing matching pass indices for composition. Historical composition reports retain their original single-pass controls.", "",
        "Regenerate from frozen evidence without API calls:", "", "```bash", "uv run python paper/analysis/lite_hosted.py --reports", "```", ""]
    (OUT / "README.md").write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", action="store_true", help="recompute all hosted pass reports from raw events")
    args = parser.parse_args()
    if args.reports:
        from lite_reports import evaluate_one
        for name, specs in HOSTED_PASSES.items():
            for index, (folder, run) in enumerate(specs, 1):
                evaluate_one(ROOT / "runs" / run, ROOT / "docs/lite/results" / folder,
                             f"{HOSTED_LABELS[name]} — pass {index}")
    publish(analyze())
    print(f"Published {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
