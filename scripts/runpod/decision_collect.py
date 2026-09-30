"""Reconnect, verify complete remote evidence, then delete only the owned Pod."""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/runpod"))
from decision_cohort import bounded_run


def call(command, timeout=90):
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=True)


def mirror(plan, raw):
    x = plan["ssh"]
    ssh = ["ssh", "-i", x["key_path"], "-p", str(x["port"]), "-o", "BatchMode=yes",
           "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + x["known_hosts_path"],
           "-o", "ConnectTimeout=12", "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=2"]
    call(["rsync", "-az", "--partial", "--delay-updates", "--timeout=30", "-e", shlex.join(ssh),
          f"root@{x['ip']}:/workspace/results/", str(raw) + "/"], timeout=120)
    return ssh


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    if plan["pod_id"] != "j5wuwq0av438fo":
        raise ValueError("This collector owns only the explicitly authorized round-2 Pod")
    cache = args.plan.parent
    raw = ROOT / "runs" / plan["experiment_id"]
    raw.mkdir(parents=True, exist_ok=True)
    reports = ROOT / "docs/lite/results" / plan["experiment_id"]
    shutil.copyfile(cache / "deployment.tar.gz", raw / "deployment.tar.gz")
    if hashlib.sha256((raw / "deployment.tar.gz").read_bytes()).hexdigest() != plan["deployment_archive_sha256"]:
        raise ValueError("Deployment archive differs from the frozen plan")
    (raw / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    failure = cache / "deployment-attempt-1.json"
    if failure.exists():
        shutil.copyfile(failure, raw / failure.name)
    while True:
        try:
            ssh = mirror(plan, raw)
            status = json.loads((raw / "status.json").read_text()) if (raw / "status.json").exists() else {}
            print(datetime.now(timezone.utc).isoformat(), status.get("status", "bootstrapping"), status.get("current_setting"), flush=True)
            finished = raw / "remote-finished.json"
            if finished.exists():
                metadata = json.loads(finished.read_text())
                evidence = raw / "remote-evidence.tar.gz"
                call(["rsync", "-az", "--partial", "--timeout=30", "-e", shlex.join(ssh),
                      f"root@{plan['ssh']['ip']}:/workspace/evidence.tar.gz", str(evidence)], timeout=150)
                with evidence.open("rb") as stream:
                    checksum = hashlib.file_digest(stream, "sha256").hexdigest()
                if checksum != metadata["evidence_sha256"]:
                    raise ValueError("Remote evidence archive checksum mismatch")
                break
        except Exception as error:
            detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
            print("Collection", type(error).__name__, str(detail).strip()[:350], flush=True)
        # A stopped Pod keeps the durable evidence. Do not terminate it just
        # because a local outage prevented collection; the provider owns the cap.
        time.sleep(60)
    bounded_run([str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/runpod/decision_report.py"),
                 "--raw", str(raw), "--reports", str(reports)], cache / "local-report.log", 1500, cwd=ROOT)
    validation = json.loads((raw / "validation.json").read_text())
    print("Evidence verified", validation, flush=True)
    deletion = call(["runpodctl", "pod", "delete", plan["pod_id"]])
    (raw / "pod-deletion.json").write_text(json.dumps({"exit_code": 0, "stdout": deletion.stdout}, indent=2))
    pods = json.loads(call(["runpodctl", "pod", "list"]).stdout)
    if any(p["id"] == plan["pod_id"] for p in pods):
        raise RuntimeError("Pod deletion not yet verified")
    deleted = datetime.now(timezone.utc)
    started = datetime.fromisoformat(plan["created_at_utc"])
    account = json.loads(call(["runpodctl", "user"]).stdout)
    billing = call(["runpodctl", "billing", "pods", "--pod-id", plan["pod_id"],
                    "--grouping", "podId", "--bucket-size", "hour"])
    (raw / "billing.json").write_text(billing.stdout)
    hours = (deleted - started).total_seconds() / 3600
    cost = {"pod_id": plan["pod_id"], "deletion_verified": True,
            "gpu_hourly_rate_usd": plan["gpu_hourly_rate_usd"], "created_at_utc": started.isoformat(),
            "deleted_at_utc": deleted.isoformat(), "estimated_gpu_charge_usd": min(hours, 5) * plan["gpu_hourly_rate_usd"],
            "estimated_total_round_charge_usd": min(hours, 5) * (plan["gpu_hourly_rate_usd"] + 90 * .1 / 720) + max(0, hours - 5) * 10 * .2 / 720,
            "previous_round_reserved_usd": plan["previous_charge_reserved_usd"],
            "cumulative_observed_balance_decrease_usd": 30.2267312812 - account["clientBalance"],
            "account_current_spend_per_hour_usd": account["currentSpendPerHr"],
            "billing_limitation": "Provider snapshots may lag; elapsed-time estimates and observed balance decrease are not a final invoice."}
    if cost["estimated_total_round_charge_usd"] + cost["previous_round_reserved_usd"] > 10:
        raise RuntimeError("Cost estimate exceeds authorized aggregate allocation")
    (raw / "cost.json").write_text(json.dumps(cost, indent=2) + "\n")
    bounded_run([str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/runpod/decision_report.py"),
                 "--raw", str(raw), "--reports", str(reports),
                 "--bundle", str(ROOT / "output" / (plan["experiment_id"] + ".tar.gz"))],
                cache / "final-report.log", 1500, cwd=ROOT)
    (raw / "collection-finished.json").write_text(json.dumps({"deletion_verified": True, "report_complete": True}, indent=2))
    print("COMPLETE", reports / "README.md", flush=True)


if __name__ == "__main__":
    main()
