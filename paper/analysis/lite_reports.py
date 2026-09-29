"""Primary log-AUC reports and recorded-cadence diagnostics; no API calls.

Without arguments, regenerate the published reports of the paper's settings. With --run, evaluate any
recorded pass (for example a new model) the same way and write its report to --out.
"""
import argparse
from pathlib import Path
import shlex
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts/lite"))
from lite_numbers import FACTS_COLUMNS, FAMILIES, MODELS, POLICY
from lite_report import analyze, command_path, report
from lite_auc import compute_auc
from streamdecisionbench.lite.__main__ import rescore_run

# Recordings on the same build that the paper does not report; indexed separately. None at present: every
# recorded setting (GPT-6 Astra low included) is in lite_numbers.MODELS and reported in the paper.
EXTRA = ()

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
        f"Primary normalized log-AUC over 1–5 s: **{100*auc['overall']['accuracy']:.2f}%**; untimed accuracy: {100*auc['overall']['untimed']:.2f}%.",
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
        "\n".join(intro)
        + diagnostics.replace("# SDB 錄製間距診斷", "## SDB 錄製間距診斷", 1)
        .replace(single, reproduce, 1)
    )
    print(f"Reproduced {folder}: {values[-2]*100:.4f}%", flush=True)
    return row, data["retry_reliability"], len(data.get("combined_from") or [data])


def _join(labels: list[str]) -> str:
    return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]


def evaluate_one(run: Path, out: Path, label: str | None) -> None:
    """Evaluate one recorded pass with the paper's primary score and print a Table 1 style row."""
    label = label or run.resolve().name
    reproduce = shlex.join(["uv", "run", "python", "paper/analysis/lite_reports.py", "--run", command_path(run),
                            "--out", command_path(out), "--label", label])
    row, reliability, _ = write_setting(label, out.name, run.name, run_dir=run, out=out, reproduce=reproduce)
    print("\n".join(["", *HEADER, row, ""]))
    print(f"{reliability['successful_logical_requests']} logical requests with valid responses, "
          f"{reliability['failed_attempts']} failed attempts. Report: {command_path(out)}/REPORT.md")


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
    lines = [
        "# Four-family log-AUC results",
        "",
        "Primary score: normalized area under in-force accuracy over 1–5 s, integrated with respect to log interval. "
        "Average scenarios equally within each family, then average the four families equally. "
        "All requests were recorded at 2 s; the replay retains each answer and measured latency.",
        "",
        *HEADER,
    ]
    failures = responses = 0
    sessions = {}
    for prefix, folder, run in MODELS:
        row, reliability, sessions[FACTS_COLUMNS[prefix]] = write_setting(FACTS_COLUMNS[prefix], folder, run)
        lines.append(row)
        failures += reliability["failed_attempts"]
        responses += reliability["successful_logical_requests"]
    merged = [label for label, n in sessions.items() if n > 1]
    single = [label for label, n in sessions.items() if n == 1]
    recorded = []
    if merged:
        recorded.append(f"For {_join(merged)}, the original six scenarios and the two presenter scenarios were recorded in separate sessions")
    if single:
        recorded.append(f"{_join(single)} {'was' if len(single) == 1 else 'were each'} recorded in one session covering all eight scenarios")
    lines += [
        "",
        f"All {responses} logical requests have valid responses; {failures} failed attempts. "
        + "; ".join(recorded) + ". No new model query was made for this evaluation.",
        "",
        "Each analysis contains `auc.primary`, three `auc.sensitivity` conditions, and fixed 2 s diagnostics in `scores`. "
        "The physical wall-clock trace and the secondary network-removal estimate are separate. "
        "The integration rule was adopted after inspecting the recorded passes; no claim of preregistration, significance or stable ranking is made.",
        "",
    ]
    if EXTRA:
        extra_failures = extra_responses = 0
        extra_rows = []
        for label, folder, run in EXTRA:
            row, reliability, _ = write_setting(label, folder, run)
            extra_rows.append(row)
            extra_failures += reliability["failed_attempts"]
            extra_responses += reliability["successful_logical_requests"]
        lines += [
            "## Additional recordings (not reported in the paper)",
            "",
            "Same build, protocol and evaluation rule; each was recorded in one session covering all eight scenarios.",
            "",
            *HEADER,
            *extra_rows,
            "",
            f"All {extra_responses} logical requests have valid responses; {extra_failures} failed attempts.",
            "",
        ]
    lines += [
        "[Evaluation policy](../../../../paper/analysis/evaluation_policy.json). "
        "Regenerate: `uv run python paper/analysis/lite_reports.py`.",
        "",
    ]
    (ROOT / "docs/lite/results/four-family/README.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
