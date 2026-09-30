"""Validate native recordings, publish complete scores, and package the evidence."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "paper/analysis"))
sys.path.insert(0, str(ROOT / "scripts/lite"))
from streamdecisionbench.lite.core import compose, decode, digest, load_dataset, request_for
from streamdecisionbench.lite.__main__ import rescore_run
from lite_reports import evaluate_one


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate(run, audit_path, plan, setting):
    frozen = json.loads((run / "run.json").read_text())
    if frozen["status"] != "complete":
        raise ValueError("Incomplete recording has no full-dataset score")
    if sha(run / "events.jsonl") != frozen["events_sha256"]:
        raise ValueError("Event bytes differ from recorded hash")
    if frozen["config"]["model_revision"] != setting["revision"]:
        raise ValueError("Checkpoint identity differs from frozen plan")
    deployment = run.parents[1] / "deployment.tar.gz"
    if sha(deployment) != plan["deployment_archive_sha256"]:
        raise ValueError("Frozen deployment archive hash mismatch")
    # Provenance is checked against the archived deployment, never later source
    # changes in the working tree. Replay continues to use each run's own data.
    with tarfile.open(deployment) as archive, tempfile.TemporaryDirectory() as directory:
        data = Path(directory)
        for member in archive:
            prefix = "sdb/data/lite/v1/"
            if member.isfile() and member.name.startswith(prefix):
                name = member.name.removeprefix(prefix)
                if Path(name).name != name:
                    raise ValueError("Unexpected nested dataset member")
                (data / name).write_bytes(archive.extractfile(member).read())
        expected, manifest = load_dataset(data)
        recorder = archive.extractfile("sdb/scripts/runpod/decision_record.py").read()
        if hashlib.sha256(recorder).hexdigest() != frozen["config"]["adapter_sha256"]:
            raise ValueError("Recorder differs from frozen deployment")
        for name, checksum in frozen["run_sources"].items():
            content = archive.extractfile("sdb/src/streamdecisionbench/" + name).read()
            if hashlib.sha256(content).hexdigest() != checksum:
                raise ValueError(f"Frozen runtime source mismatch: {name}")
    actual = json.loads((run / "episodes.json").read_text())
    if manifest["dataset_hash"] != plan["dataset_sha256"] or actual != expected or frozen["dataset_manifest"] != manifest:
        raise ValueError("Dataset/episode hashes differ from frozen deployment")
    audit = json.loads(audit_path.read_text())
    if sha(audit_path) != frozen["config"]["input_audit_sha256"]:
        raise ValueError("Input audit differs from its recorded hash")
    if audit["requests"] != 480 or audit["issues"] or audit["dataset_hash"] != manifest["dataset_hash"]:
        raise ValueError("Incomplete native input audit")
    verified = rescore_run(run)
    coverage, seen, answers = [], set(), 0
    audited = {(r["episode_id"], r["t"]): r["request_sha256"] for r in audit["rows"]}
    for episode in expected:
        if len(verified["responses"][episode["episode_id"]]) != len(episode["steps"]):
            raise ValueError("Incomplete response coverage")
        for response in verified["responses"][episode["episode_id"]]:
            key = (episode["episode_id"], response["t"])
            request_hash = digest(request_for(episode, episode["steps"][response["t"]]))
            if key in seen or not response["ok"] or response["request_hash"] != request_hash or audited.get(key) != request_hash:
                raise ValueError("Duplicate, unsuccessful, or mismatched request")
            pred = decode(episode, response["wire_answers"])
            if pred != response["pred"] or compose(episode["decision_spec"], pred) != response["decision"]:
                raise ValueError("Committed decision differs from native wire answer")
            # Native candidate readouts retain their logits/distributions for verification.
            if setting["backend"] in {"nimble", "semif"}:
                fields = response["usage"]["native_fields"]
                if set(fields) != set(episode["questions"]):
                    raise ValueError("Missing native readout diagnostics")
                for qid, field in fields.items():
                    if setting["backend"] == "nimble":
                        native = field["value"]
                    else:
                        native = field["option_ids"][max(range(len(field["probabilities"])), key=field["probabilities"].__getitem__)]
                    if native != response["wire_answers"][qid]:
                        raise ValueError("Native readout changed before commitment")
            seen.add(key)
            answers += len(response["wire_answers"])
            coverage.append({"setting": setting["id"], "episode_id": key[0], "t": key[1],
                             "request_sha256": request_hash, "valid": True})
    if len(seen) != 480:
        raise ValueError("Expected exactly 480 unique requests")
    return coverage, answers


def summarize(raw, reports):
    plan = json.loads((raw / "plan.json").read_text())
    reports.mkdir(parents=True, exist_ok=True)
    rows, coverage, failures, question_answers = [], [], list(plan["unavailable_settings"]), 0
    for setting in plan["settings"]:
        label = setting["id"]
        run = raw / "runs" / label
        if not (run / "run.json").exists() or json.loads((run / "run.json").read_text())["status"] != "complete":
            status = json.loads((raw / "status.json").read_text()) if (raw / "status.json").exists() else {}
            failures.append({"id": label, "reason": status.get("settings", {}).get(label, {"status": "No complete recording"})})
            continue
        verified, count = validate(run, raw / f"{label}.input-audit.json", plan, setting)
        coverage.extend(verified)
        question_answers += count
        output = reports / label
        evaluate_one(run, output, setting["label"])
        analysis = json.loads((output / "analysis.json").read_text())
        if analysis["retry_reliability"]["successful_logical_requests"] != 480:
            raise ValueError("Analysis has incomplete coverage")
        primary = analysis["auc"]["primary"]
        row = {"setting": label, "model": setting["model"], "revision": setting["revision"],
               "requests": 480, "dataset_sha256": plan["dataset_sha256"], "events_sha256": sha(run / "events.jsonl"),
               "log_auc_pct": 100 * primary["overall"]["accuracy"],
               "untimed_accuracy_pct": 100 * primary["overall"]["untimed"],
               "latency_p50_s": analysis["latency_s"]["p50"], "latency_p95_s": analysis["latency_s"]["p95"],
               "failed_attempts": analysis["retry_reliability"]["failed_attempts"],
               **{f"{f}_log_auc_pct": 100 * v["accuracy"] for f, v in primary["by_family"].items()}}
        rows.append(row)
        witnesses = []
        families = set()
        for episode in analysis["scores"]["per_episode"]:
            if episode["task_family"] not in families and episode["mistakes"]:
                families.add(episode["task_family"])
                witnesses.append({"family": episode["task_family"], "episode_id": episode["episode_id"], **episode["mistakes"][0]})
        (output / "error-witnesses.json").write_text(json.dumps(witnesses, ensure_ascii=False, indent=2))
    for target, values in [(reports / "results.csv", rows), (raw / "coverage.csv", coverage)]:
        if values:
            with target.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(values[0])); writer.writeheader(); writer.writerows(values)
    summary = {"complete_settings": len(rows), "planned_executable_settings": len(plan["settings"]),
               "results": rows, "unavailable_or_failed": failures}
    (reports / "results.json").write_text(json.dumps(summary, indent=2) + "\n")
    validation = {"dataset_sha256": plan["dataset_sha256"], "complete_settings": len(rows),
                  "valid_requests": len(coverage), "question_answers": question_answers,
                  "events_hashes_verified": True, "episode_hashes_verified": True,
                  "public_request_hashes_verified": True, "runtime_source_hashes_verified": True,
                  "committed_decisions_verified": True, "input_audit_issues": 0}
    (raw / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    labels = {s["id"]: s["label"] for s in plan["settings"]}
    lines = ["# Native open-weight SDB experiment — round 2", "",
             f"{len(rows)} of {len(plan['settings'])} executable settings completed; 480 unique requests and 8 scenarios per completed setting.", "",
             "| Setting | Log-AUC 1–5 s (%) | Untimed (%) | p50 / p95 (s) | Failed attempts |",
             "|---|---:|---:|---:|---:|"]
    for row in rows:
        label = row["setting"]
        lines.append(f"| [{labels[label]}]({label}/REPORT.md) | {row['log_auc_pct']:.2f} | {row['untimed_accuracy_pct']:.2f} | {row['latency_p50_s']:.3f} / {row['latency_p95_s']:.3f} | {row['failed_attempts']} |")
    lines += ["", "## Measurement", "",
              f"One {plan['gpu']} GPU, BF16 backbones, native upstream decision code. Benchmark and model execute on the same Pod; latency includes tokenization, queueing and inference. Download, model initialization, input audits and three unrelated synthetic warmups are excluded. No internet round trip is included.", "",
              "The unchanged dataset uses a 2 s release cadence, 32 workers and serial scenarios. Complete results use the existing retry-excluded timing protocol and equal-family normalized log-AUC over 1–5 s. Failed or partial settings receive no complete score. No incorrect answer is retried, repaired or used to choose a configuration.", "",
              "Kev uses its native pointer head and fused CUDA runtime, with CUDA graphs, cross-request prefix caching and date-fact augmentation disabled. Nimble uses its released BF16 merged adapter, T=1.0 and independent full-prompt scoring per field. SemIf reads uncalibrated native option logits from the pinned untrained Qwen checkpoint, in fresh direct mode with thinking disabled. For Nimble and SemIf, latency includes answering every question in the decision, rather than one field.", "",
              "All state fields, structured instructions, choice descriptions, option order and opaque output IDs are preserved through native mappings. The native encoders audit all 480 requests before model recording and reject context overflow. There is no CPU offload or truncated-input path. Native probability/logit diagnostics are retained for Nimble and SemIf; Kev commits its native answers without retaining a full probability vector in the SDB event schema.", "",
              "One pass per setting. Related stream states are dependent. Differences describe this dataset and deployment; they do not establish significance, a stable model ranking, or a controlled comparison with the hosted API rows or the previous RTX PRO 6000 cohort. Standard reports also retain the secondary latency-intercept diagnostic and its range; its network + prefill + decode assumption can include fixed server time, and it does not replace the primary score.", "",
              "## Coverage and provenance", "",
              f"Dataset SHA-256: `{plan['dataset_sha256']}`. Verified {len(coverage)} requests and {question_answers} committed question answers. Raw events, episode hashes, public request hashes, actual weight/config hashes, upstream commits and installed dependencies are retained. Each setting includes deterministically selected first error witnesses per family; these do not establish an error cause.", "",
              "[results.csv](results.csv) contains unrounded results. Raw evidence contains coverage.csv, validation.json, the frozen plan, input audits, preparation logs and all recordings.", "",
              "## Unavailable or failed settings", ""]
    lines += [f"- {f['id']}: {f['reason']}" for f in failures]
    lines += ["", "## Resilience, cost and cleanup", "",
              "The detached Pod worker runs without a local connection. Results are flushed to /workspace/results on a retained 10 GB volume. Provider auto-stop caps GPU time at five hours; scheduled termination caps retained storage at 48 hours. The reconnecting collector copies and verifies all reachable evidence before deletion.", "",
              f"Original budget: US$10 across both rounds; previous round reserved US${plan['previous_charge_reserved_usd']:.2f}. This round's planned worst-case cost is US${plan['worst_case_round_usd']:.4f}; cumulative planned maximum US${plan['worst_case_total_usd']:.4f}. Actual costs and cleanup verification are in raw cost.json and billing.json.", ""]
    if (raw / "cost.json").exists():
        lines += ["```json", (raw / "cost.json").read_text().strip(), "```", ""]
    (reports / "README.md").write_text("\n".join(lines))
    return summary


def package(raw, reports, destination):
    cost = json.loads((raw / "cost.json").read_text())
    if not cost["deletion_verified"]:
        raise ValueError("Final bundle requires verified resource deletion")
    manifest = {"files": {}, "validation": json.loads((raw / "validation.json").read_text())}
    paths = []
    for folder in [raw, reports, ROOT / "scripts/runpod"]:
        for path in sorted(folder.rglob("*")):
            if path.is_file() and path.name != "bundle-manifest.json" and not path.name.endswith(".shadow.md") and "__pycache__" not in path.parts:
                name = str(path.relative_to(ROOT))
                paths.append((path, name)); manifest["files"][name] = sha(path)
    for name in ["test_runpod_decisions.py", "test_runpod_recording.py", "test_lite_core.py",
                 "test_lite_reports.py", "test_lite_runtime_retries.py"]:
        path = ROOT / "tests" / name
        if path.exists():
            relative = str(path.relative_to(ROOT))
            paths.append((path, relative)); manifest["files"][relative] = sha(path)
    # The exact deployment archive contains benchmark, data, analysis and native source.
    archive = raw / "deployment.tar.gz"
    if not archive.exists():
        raise ValueError("Frozen deployment source archive is required")
    manifest_path = raw / "bundle-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    paths.append((manifest_path, str(manifest_path.relative_to(ROOT))))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(destination, "w:gz") as bundle:
        for path, name in paths:
            bundle.add(path, arcname=name)
    destination.with_name(destination.name + ".sha256").write_text(sha(destination) + "\n")
    with tarfile.open(destination) as bundle:
        for name, checksum in manifest["files"].items():
            if hashlib.sha256(bundle.extractfile(name).read()).hexdigest() != checksum:
                raise ValueError(f"Bundle verification failed: {name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args()
    summarize(args.raw, args.reports)
    if args.bundle:
        package(args.raw, args.reports, args.bundle)
