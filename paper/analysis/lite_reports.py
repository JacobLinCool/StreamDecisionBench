"""Primary log-AUC reports and recorded-cadence diagnostics; no API calls.

Without arguments, regenerate the public leaderboard's published reports. With --run, evaluate any
recorded pass (for example a new model) the same way and write its report to --out.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import shlex
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts/lite"))
from leaderboard_models import HOSTED_LABELS, HOSTED_MODELS
from lite_numbers import FAMILIES, POLICY
from lite_report import analyze, command_path, report
from lite_auc import compute_auc
from streamdecisionbench.lite.__main__ import rescore_run

HEADER = [
    "| Setting | IDE | Assembly | Support | Presenter | Macro log-AUC | Untimed | Report |",
    "|---|---:|---:|---:|---:|---:|---:|---|",
]


def write_setting(label: str, folder: str, run: str, *, run_dir: Path | None = None, out: Path | None = None,
                  reproduce: str = "uv run python paper/analysis/lite_reports.py") -> tuple[str, dict, int]:
    """Analyze one recorded pass, write its report and analysis, and return its table row, its retry
    reliability and the number of recording sessions it combines."""
    run_dir = run_dir or ROOT / "runs" / run
    data = analyze(run_dir)
    data["evaluation_policy"] = POLICY
    data["auc"] = compute_auc(rescore_run(run_dir))
    out = out or ROOT / "docs/lite/results" / folder
    report(data, out)
    auc = data["auc"]["primary"]
    values = [auc["by_family"][f]["accuracy"] for _, f in FAMILIES] + [
        auc["overall"]["accuracy"],
        auc["overall"]["untimed"],
    ]
    row = (
        "| "
        + " | ".join(
            [
                label,
                *[f"{100*v:.2f}%" for v in values],
                f"[report]({Path(folder).name}/REPORT.md)",
            ]
        )
        + " |"
    )
    intro = [
        f"# SDB log-AUC: {label}",
        "",
        f"Primary normalized log-AUC over 0.5–8 s: **{100*auc['overall']['accuracy']:.2f}%**; untimed accuracy: {100*auc['overall']['untimed']:.2f}%.",
        "Equal multiplicative interval ranges receive equal weight. This is a benchmark weighting rule, not an empirical usage distribution.",
        "",
        "| Family | Log-AUC (%) |",
        "|---|---:|",
        *[
            f"| {f} | {100*auc['by_family'][f]['accuracy']:.2f} |"
            for _, f in FAMILIES
        ],
        "",
        f"Quadrature: {auc['quadrature']['subintervals']} log-spaced subintervals; maximum change from the preceding grid {100*auc['quadrature']['max_successive_change']:.6f} percentage points across all scenario metrics.",
        "This is numerical convergence, not statistical uncertainty. One recorded pass per setting.",
        "",
        "The following diagnostics use the fixed **2 s recording cadence**, not the integrated primary score.",
        "",
    ]
    # The diagnostics section written by lite_report.report becomes a subsection, and its reproduction command
    # (lite_report.py alone, which writes diagnostics without the log-AUC) is replaced by this script's command.
    diagnostics = (out / "REPORT.md").read_text()
    single = shlex.join(["uv", "run", "python", "scripts/lite/lite_report.py", "--run", data["run"],
                         "--out", command_path(out)])
    if diagnostics.count(single) != 1:
        raise SystemExit(f"{folder}: reproduction command not found in the diagnostics report: {single}")
    (out / "REPORT.md").write_text(
        "\n".join(intro) + "\n"
        + diagnostics.replace("# SDB recording-cadence diagnostics", "## SDB recording-cadence diagnostics", 1)
        .replace(single, reproduce, 1)
    )
    print(f"Reproduced {folder}: {values[-2]*100:.4f}%", flush=True)
    return row, data["retry_reliability"], len(data.get("combined_from") or [data])


def refresh_cohort_summary(directory: Path) -> None:
    """Refresh derived cohort scores, preserving the historical execution record."""
    path = directory / "results.json"
    summary = json.loads(path.read_text())
    for row in summary["results"]:
        analysis = json.loads((directory / row["setting"] / "analysis.json").read_text())
        if row["events_sha256"] != analysis["events_sha256"]:
            raise ValueError(f"{directory}/{row['setting']}: cohort event hash mismatch")
        primary = analysis["auc"]["primary"]
        if (primary["min_s"], primary["max_s"], primary["weighting"]) != (.5, 8, "log"):
            raise ValueError(f"{directory}: stale primary domain")
        row["log_auc_pct"] = 100 * primary["overall"]["accuracy"]
        for family, result in primary["by_family"].items():
            row[f"{family}_log_auc_pct"] = 100 * result["accuracy"]
        for kind in ("judgment", "stale", "compound", "no_decision"):
            key = f"{kind}_time_pct"
            if key in row:  # The first cohort publishes the integrated partition.
                row[key] = 100 * primary["overall"][kind]
    summary["evaluation_domain"] = {"min_s": .5, "max_s": 8, "weighting": "log"}
    path.write_text(json.dumps(summary, indent=2) + "\n")
    with (directory / "results.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary["results"][0]))
        writer.writeheader()
        writer.writerows(summary["results"])
    readme = directory / "README.md"
    lines = readme.read_text().splitlines()
    for index, line in enumerate(lines):
        for row in summary["results"]:
            if f"]({row['setting']}/REPORT.md)" in line:
                cells = line.split("|")
                cells[2] = f" {row['log_auc_pct']:.2f} "
                lines[index] = "|".join(cells)
    readme.write_text("\n".join(lines) + "\n")


def evaluate_one(run: Path, out: Path, label: str | None) -> None:
    """Evaluate one recorded pass with the paper's primary score and print a Table 1 style row."""
    label = label or run.resolve().name
    reproduce = shlex.join(["uv", "run", "python", "paper/analysis/lite_reports.py", "--run", command_path(run),
                            "--out", command_path(out), "--label", label])
    row, reliability, _ = write_setting(label, out.name, run.name, run_dir=run, out=out, reproduce=reproduce)
    print("\n".join(["", *HEADER, row, ""]))
    print(f"{reliability['successful_logical_requests']} logical requests with valid responses, "
          f"{reliability['failed_attempts']} failed attempts. Report: {command_path(out)}/REPORT.md")


def write_index() -> None:
    """Render the published index and cohort summaries from verified reports."""
    local_policy = json.loads((ROOT / "paper/analysis/openweight_policy.json").read_text())
    from lite_hosted import load_summary
    hosted = load_summary()["hosted"]
    groups = [
        ("Hosted APIs", [(HOSTED_LABELS[name], folder, run) for name, folder, run in HOSTED_MODELS]),
        ("Self-hosted settings", [(spec["label"], spec["reports"][0] if "reports" in spec else spec["run"].replace("/runs/", "/"), spec["run"])
                                  for spec in local_policy["settings"]]),
    ]
    index_dir = ROOT / "docs/lite/results/four-family"
    lines = ["# Four-family log-AUC results", "",
        "Primary score: normalized area under in-force accuracy over 0.5–8 s, integrated with respect to log interval. "
        "Average scenarios equally within each family, then average the four families equally. "
        "All requests were recorded at 2 s; the replay retains each answer and measured latency.", "",
        "The domain spans update rates four times faster and slower than the recording cadence, "
        "with equal log weight on each side. It defines a controlled evaluation domain; deployment-specific "
        "event rates can motivate other ranges.", ""]
    for title, settings in groups:
        if title == "Hosted APIs":
            lines += [f"## {title}", "",
                "| Setting | Passes | IDE | Assembly | Support | Presenter | Mean log-AUC ± SD | Mean untimed | Report |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
            for row in sorted(hosted.values(), key=lambda r: -r["accuracy"]):
                families = [f"{100*row['by_family'][family]['accuracy']:.2f}%" for _, family in FAMILIES]
                lines.append("| " + " | ".join([row["label"], str(len(row["passes"])), *families,
                    f"{100*row['accuracy']:.2f}% ± {100*row['auc_sample_sd']:.2f}", f"{100*row['untimed']:.2f}%",
                    "[repeat reports](../hosted-api-repeats-20261003/README.md)"]) + " |")
            lines += [""]
            continue
        lines += [f"## {title}", "", *HEADER]
        for label, folder, run in settings:
            path = ROOT / "docs/lite/results" / folder / "analysis.json"
            data = json.loads(path.read_text())
            frozen = json.loads((ROOT / "runs" / run / "run.json").read_text())
            if data["events_sha256"] != frozen["events_sha256"]:
                raise ValueError(f"{folder}: report event hash mismatch")
            auc = data["auc"]["primary"]
            if (auc["min_s"], auc["max_s"], auc["weighting"]) != (.5, 8, "log"):
                raise ValueError(f"{folder}: stale primary domain")
            values = [auc["by_family"][f]["accuracy"] for _, f in FAMILIES]
            values += [auc["overall"]["accuracy"], auc["overall"]["untimed"]]
            link = Path(os.path.relpath(path.with_name("REPORT.md"), index_dir)).as_posix()
            lines.append("| " + " | ".join([label, *[f"{100*v:.2f}%" for v in values], f"[report]({link})"]) + " |")
        lines += [""]
    lines += [
        "Hosted scores average two passes for Astra low and three for every other setting, each over all 480 states. "
        "SD is sample standard deviation across passes, in percentage points. The original Luna, Terra and Jev passes "
        "combine disjoint six-scenario and presenter sessions. All 15 additional passes completed without retries; "
        "Clef Flash's original pass retains its two recovered timeout attempts. "
        "The self-hosted table shows the referenced individual recordings; the public leaderboard averages their three passes. "
        "No model query is made by this analysis.", "",
        "Each analysis contains `auc.primary`, six `auc.sensitivity` conditions, and fixed 2 s diagnostics in `scores`. "
        "The physical wall-clock trace and secondary network-removal estimate are separate. The integration rule "
        "was adopted after inspecting the recorded passes; comparisons are descriptive and do not establish stable rankings.", "",
        "The self-hosted settings use their respective GPU runtime and native decision interface. "
        "See the [deployment and composition analysis](../../../research/openweight-hybrids/README.md).", "",
        "[Evaluation policy](../../../../paper/analysis/evaluation_policy.json). "
        "Regenerate: `uv run python paper/analysis/lite_reports.py`.", ""]
    (index_dir / "README.md").write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", type=Path, help="evaluate this recorded pass instead of regenerating the published reports")
    parser.add_argument("--out", type=Path, help="report folder for --run (created if missing)")
    parser.add_argument("--label", help="setting name for --run (default: the run folder name)")
    args = parser.parse_args()
    if args.run:
        if args.out is None:
            parser.error("--out is required with --run")
        evaluate_one(args.run, args.out, args.label)
        return
    if args.out or args.label:
        parser.error("--out and --label need --run")
    for name, folder, run in HOSTED_MODELS:
        write_setting(HOSTED_LABELS[name], folder, run)
    from leaderboard_models import HOSTED_PASSES
    from lite_hosted import analyze as analyze_hosted, publish as publish_hosted
    for name, specs in HOSTED_PASSES.items():
        for index, (folder, run) in enumerate(specs[1:], 2):
            write_setting(f"{HOSTED_LABELS[name]} — pass {index}", folder, run)
    publish_hosted(analyze_hosted())
    local_policy = json.loads((ROOT / "paper/analysis/openweight_policy.json").read_text())
    for spec in local_policy["settings"]:
        runs = [spec["run"], *spec.get("repeats", [])]
        reports = spec["reports"] if "reports" in spec else [run.replace("/runs/", "/") for run in runs]
        for run, folder in zip(runs, reports, strict=True):
            write_setting(spec["label"], folder, run)
    for cohort in sorted({Path(run).parts[0] for spec in local_policy["settings"]
                          for run in [spec["run"], *spec.get("repeats", [])]}):
        refresh_cohort_summary(ROOT / "docs/lite/results" / cohort)
    write_index()


if __name__ == "__main__":
    main()
