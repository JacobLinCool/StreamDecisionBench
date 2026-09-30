"""Regenerate clean tables from complete, hash-verified RunPod recordings."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
LABELS = {
    "laya-english": "Laya English",
    "laya-typed-decisions": "Laya typed-decisions",
    "laya-multilingual": "Laya multilingual",
    "djev-diffusiongemma": "DJev / DiffusionGemma 26B-A4B (BF16)",
}
FAMILIES = ["live_debugging", "procedural_coaching", "support_call_assist", "presenter_voice_control"]


def summarize(recordings: Path, reports: Path):
    reports.mkdir(parents=True, exist_ok=True)
    rows = []
    failures = []
    for folder, label in LABELS.items():
        run = recordings / "runs" / folder
        if not (run / "run.json").exists():
            failures.append({"setting": folder, "reason": "No recording"})
            continue
        frozen = json.loads((run / "run.json").read_text())
        if frozen["status"] != "complete":
            failures.append({"setting": folder, "reason": frozen["status"]})
            continue
        event_hash = hashlib.sha256((run / "events.jsonl").read_bytes()).hexdigest()
        if event_hash != frozen["events_sha256"]:
            raise ValueError(f"{folder}: event hash mismatch")
        episodes = json.loads((run / "episodes.json").read_text())
        if len(episodes) != 8 or sum(len(e["steps"]) for e in episodes) != 480:
            raise ValueError(f"{folder}: incomplete dataset coverage")
        out = reports / folder
        subprocess.run([
            sys.executable, str(ROOT / "paper/analysis/lite_reports.py"),
            "--run", str(run), "--out", str(out), "--label", label,
        ], cwd=ROOT, check=True)
        analysis = json.loads((out / "analysis.json").read_text())
        if analysis["retry_reliability"]["successful_logical_requests"] != 480:
            raise ValueError(f"{folder}: fewer than 480 successful responses")
        primary = analysis["auc"]["primary"]
        witnesses = []
        seen = set()
        for episode in analysis["scores"]["per_episode"]:
            family = episode["task_family"]
            if family not in seen and episode["mistakes"]:
                seen.add(family)
                witnesses.append({"family": family, "episode_id": episode["episode_id"], **episode["mistakes"][0]})
        (out / "error-witnesses.json").write_text(json.dumps(witnesses, ensure_ascii=False, indent=2) + "\n")
        findings = [f"# Recorded error witnesses: {label}", "",
                    "The first untimed decision mismatch in each family is selected deterministically. "
                    "These examples are observations from this pass; they do not establish a cause or estimate generalization.", ""]
        for witness in witnesses:
            findings += [f"## {witness['family']}: {witness['episode_id']}, tick {witness['t']}", "",
                         f"Wrong active fields: {', '.join(witness['wrong_active_questions'])}.", "",
                         "```json", json.dumps({k: witness[k] for k in ["reference_decision", "predicted_decision", "reference_evidence"]}, ensure_ascii=False, indent=2), "```", ""]
        if not witnesses:
            findings += ["No untimed decision mismatch occurred in this recording.", ""]
        findings += ["All mistakes and active-field accuracies remain available in analysis.json and the original metrics.json. "
                     "For deployment review, inspect route selection and the active fields together using these frozen states; "
                     "a wrong route changes which fields the application uses. No additional model pass was selected from these outcomes.", ""]
        (out / "FINDINGS.md").write_text("\n".join(findings))
        report_path = out / "REPORT.md"
        if "FINDINGS.md" not in report_path.read_text():
            with report_path.open("a") as stream:
                stream.write("\n[Recorded error witnesses and deployment review](FINDINGS.md).\n")
        row = {
            "setting": folder, "model": frozen["config"]["model"],
            "model_revision": frozen["config"]["model_revision"],
            "responses": 480, "dataset_sha256": analysis["dataset_hash"],
            "events_sha256": event_hash,
            "log_auc_pct": 100 * primary["overall"]["accuracy"],
            "untimed_accuracy_pct": 100 * primary["overall"]["untimed"],
            "all_questions_exact_accuracy_pct": 100 * analysis["scores"]["overall"]["all_questions_exact_accuracy"],
            "latency_p50_s": analysis["latency_s"]["p50"],
            "latency_p95_s": analysis["latency_s"]["p95"],
            "failed_attempts": analysis["retry_reliability"]["failed_attempts"],
            **{f"{kind}_time_pct": 100 * primary["overall"][kind] for kind in ["judgment", "stale", "compound", "no_decision"]},
            **{f"{f}_log_auc_pct": 100 * primary["by_family"][f]["accuracy"] for f in FAMILIES},
        }
        rows.append(row)
    if len({r["dataset_sha256"] for r in rows}) > 1:
        raise ValueError("Cohort mixes dataset revisions")
    if rows:
        with (reports / "results.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    summary = {"complete_settings": len(rows), "expected_settings": len(LABELS), "results": rows, "failures": failures}
    (reports / "results.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = [
        "# RunPod open-weight SDB results", "",
        f"Completed {len(rows)} of {len(LABELS)} settings; each completed setting covers all 8 scenarios and 480 states.", "",
        "| Setting | Log-AUC 1–5 s (%) | Untimed (%) | Latency p50 / p95 (s) | Failed attempts |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        folder = row["setting"]
        lines.append(f"| [{LABELS[folder]}]({folder}/REPORT.md) | {row['log_auc_pct']:.2f} | {row['untimed_accuracy_pct']:.2f} | {row['latency_p50_s']:.3f} / {row['latency_p95_s']:.3f} | {row['failed_attempts']} |")
    lines += [
        "", "## Measurement and interpretation", "",
        "Recorded on 2026-09-30 (Asia/Taipei), on one RunPod NVIDIA RTX PRO 6000 Blackwell Server Edition (96 GB). "
        "The benchmark and model are on the same host. Laya calls its native library; DJev calls its local HTTP server. "
        "Latency includes normal request dispatch and inference. It does not include an internet round trip. "
        "Consequently, these latency-dependent scores describe this deployment and must not be treated as a controlled hardware comparison with the paper's hosted API rows.", "",
        "The unchanged four-family dataset, 2 s recording cadence, 32 client workers, one scenario at a time and "
        "retry_excluded_successful_attempt_v1 scoring are used. Only transport failures may be retried, at most three attempts. "
        "No incorrect answer is retried or repaired. Raw wall-clock metrics are preserved separately. "
        "The primary normalized log-AUC is recomputed by the existing paper analysis over 1–5 s with equal family weights.", "",
        "The standard reports also retain the benchmark's secondary latency-intercept diagnostic and its range. "
        "It assumes latency can be decomposed into network, prefill and (when applicable) decode contributions; "
        "the intercept can also contain fixed server or client time. On these same-host deployments it is not a measurement "
        "of internet latency and does not replace the primary score.", "",
        "Laya checkpoints use the upstream runtime's calibration policy, CUDA BF16 autocast, eager execution, max_len=8192 and head_max_len=1024. "
        "CPU fallback, dropped state tokens and collapsed options invalidate a recording. "
        "DJev uses unquantized DiffusionGemma BF16, a 128-token canvas, one denoise step, no thinking, and "
        "the upstream automatic noise sampling policy (up to four draws, threshold 0.1). "
        "Model revisions, upstream source commits and installed dependencies are frozen in the raw evidence.", "",
        "Upstream sources: [Laya](https://github.com/NandhaKishorM/laya), "
        "[DJev](https://github.com/mmastrac/djev), "
        "[DiffusionGemma weights](https://huggingface.co/google/diffusiongemma-26B-A4B-it), "
        "[vLLM structured-read implementation](https://github.com/vllm-project/vllm/pull/57250).", "",
        "One pass per setting. Adjacent stream states are dependent; no significance claim or stable ranking is inferred. "
        "Model download, initialization and three unrelated synthetic warm-up requests precede recording and are excluded from model latency.", "",
        "## Files and reproduction", "",
        "[results.csv](results.csv) contains unrounded machine-readable values; [results.json](results.json) also lists unavailable settings. "
        "Each setting folder contains the standard SDB report and analysis.json. Raw run folders contain frozen episodes, original events, configuration and scores.", "",
        "Regenerate from the repository root:", "", "```bash",
        f"uv run python scripts/runpod/summarize.py --recordings {recordings.relative_to(ROOT)} --reports {reports.relative_to(ROOT)}",
        "```", "",
    ]
    if failures:
        lines += ["## Unavailable settings", "", *[f"- {f['setting']}: {f['reason']}. No complete benchmark score is published." for f in failures], ""]
    audit_path = recordings / "input-audit.json"
    if audit_path.exists():
        audit = json.loads(audit_path.read_text())
        lines += ["## Input coverage audit", "",
                  "Native tokenization was audited without additional model calls. Instructions, option text, "
                  "option markers and state tokens were checked against each checkpoint's actual tokenizer.", "",
                  "| Setting | Question rows | Maximum sequence tokens | Truncation / option issues |",
                  "|---|---:|---:|---:|"]
        for label, data in audit["settings"].items():
            lines.append(f"| {LABELS[label]} | {data['question_rows']} | {data['max_sequence_tokens']} | {len(data['issues'])} |")
        lines += ["", "The complete audit is retained as input-audit.json with the raw recordings. "
                  "The English and typed-decisions checkpoints warn that their choice:11+ temperature is clamped by the upstream runtime to 0.5; "
                  "that runtime policy is preserved. These results evaluate committed decisions, without a calibration-quality claim.", ""]
    cost_path = recordings / "cost.json"
    if cost_path.exists():
        cost = json.loads(cost_path.read_text())
        lines += ["## Cost and cleanup", "", f"Pod {cost['pod_id']}; GPU rate ${cost['gpu_hourly_rate_usd']:.2f}/h. "
                  f"Conservative elapsed-time GPU charge estimate: ${cost['estimated_gpu_charge_usd']:.4f}. "
                  "This estimate counts the full provisioning-to-deletion interval; RunPod billing evidence is preserved with the recording. "
                  f"Pod deletion verified: {cost['deletion_verified']}. Budget: $10.", ""]
        if "estimated_total_charge_usd" in cost:
            lines += [
                f"Including disk, the estimated total is ${cost['estimated_total_charge_usd']:.4f}, "
                "using the observed Pod billing rate over that same conservative interval. "
                f"The observed account balance decrease is ${cost['observed_balance_decrease_usd']:.4f}. "
                "The provider's billing snapshot is still partial; neither value is presented as a final invoice. "
                f"Account spending rate after cleanup: ${cost['current_account_spend_per_hour_after_cleanup_usd']:.2f}/h.", "",
            ]
    (reports / "README.md").write_text("\n".join(lines))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recordings", required=True, type=Path)
    parser.add_argument("--reports", required=True, type=Path)
    args = parser.parse_args()
    summarize(args.recordings.resolve(), args.reports.resolve())
