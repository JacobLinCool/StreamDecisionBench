"""Keep results local and delete only this experiment's Pod on completion/deadline."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache/openweight-20260930"
OUT = ROOT / "runs/runpod-openweight-20260930"
REPORTS = ROOT / "docs/lite/results/runpod-openweight-20260930"
POD = "wr8xay3x75qxpa"
SSH = ["ssh", "-i", str(Path.home() / ".ssh/id_ed25519"), "-p", "11930",
       "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
       "-o", f"UserKnownHostsFile={CACHE / 'known_hosts'}", "-o", "ConnectTimeout=15"]
REMOTE = "root@69.8.146.175"


def command(args, *, timeout=180, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, **kwargs)


def sync():
    result = command(["rsync", "-az", "--checksum", "-e", shlex.join(SSH), f"{REMOTE}:/workspace/results/", str(OUT) + "/"])
    if result.returncode:
        raise RuntimeError(result.stderr)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    budget = json.loads((CACHE / "budget.json").read_text())
    deadline = datetime.fromisoformat(budget["terminate_at_utc"]) - timedelta(minutes=20)
    started = datetime.fromisoformat(budget["created_at_utc"])
    (OUT / "budget.json").write_text(json.dumps({k: v for k, v in budget.items() if k != "pod"}, indent=2) + "\n")
    while True:
        try:
            sync()
            status_path = OUT / "status.json"
            status = json.loads(status_path.read_text()) if status_path.exists() else {}
            print(datetime.now(timezone.utc).isoformat(), status.get("status", "installing"), status.get("current_setting"), flush=True)
            if status.get("status") == "complete" or (CACHE / "ready-to-delete").exists():
                break
        except Exception as error:
            print("Collection:", repr(error), flush=True)
        if datetime.now(timezone.utc) >= deadline:
            print("Experiment deadline reached; preserving partial evidence and deleting Pod", flush=True)
            break
        time.sleep(60)
    try:
        audit = command(SSH + [REMOTE, "HF_HOME=/workspace/hf /workspace/bench-env/bin/python /workspace/sdb/scripts/runpod/input_audit.py"])
        (OUT / "input-audit-execution.json").write_text(json.dumps({"exit_code": audit.returncode, "stderr": audit.stderr}, indent=2))
    except Exception as error:
        print("Input audit:", repr(error), flush=True)
    try:
        sync()
    except Exception as error:
        print("Final collection:", repr(error), flush=True)
    # Never mark incomplete recordings complete. Validate and report what actually exists.
    try:
        report = command([str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/runpod/summarize.py"),
                          "--recordings", str(OUT), "--reports", str(REPORTS)], timeout=900)
        print(report.stdout, report.stderr, flush=True)
    except Exception as error:
        print("Analysis failed; preserving evidence and continuing cleanup:", repr(error), flush=True)
    # Ensure cleanup still occurs if analysis fails. This Pod is disposable and
    # all reachable experiment evidence has already been copied locally.
    deletion = command(["runpodctl", "pod", "delete", POD])
    (OUT / "pod-deletion.json").write_text(json.dumps({"exit_code": deletion.returncode, "stdout": deletion.stdout, "stderr": deletion.stderr}, indent=2))
    verified = False
    for _ in range(3):
        listing = command(["runpodctl", "pod", "list"])
        if listing.returncode == 0:
            pods = json.loads(listing.stdout)
            if not any(p["id"] == POD for p in pods):
                verified = True
                (OUT / "pods-after-cleanup.json").write_text(listing.stdout)
                break
        command(["runpodctl", "pod", "delete", POD])
        time.sleep(5)
    deleted_at = datetime.now(timezone.utc)
    cost = {"pod_id": POD, "budget_usd": 10, "gpu_hourly_rate_usd": 2.09,
            "created_at_utc": started.isoformat(), "deleted_at_utc": deleted_at.isoformat(),
            "estimated_gpu_charge_usd": 2.09 * (deleted_at - started).total_seconds() / 3600,
            "deletion_verified": verified}
    (OUT / "cost.json").write_text(json.dumps(cost, indent=2) + "\n")
    for name, args in [("account-after.json", ["runpodctl", "user"]),
                       ("billing.json", ["runpodctl", "billing", "pods", "--pod-id", POD, "--grouping", "podId", "--bucket-size", "hour"] )]:
        result = command(args)
        (OUT / name).write_text(result.stdout if result.returncode == 0 else json.dumps({"error": result.stderr}))
    final_report = command([str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/runpod/summarize.py"),
                            "--recordings", str(OUT), "--reports", str(REPORTS)], timeout=900)
    print(final_report.stdout, final_report.stderr, flush=True)
    (OUT / "collection-finished.json").write_text(json.dumps({"deletion_verified": verified, "report_exit_code": final_report.returncode}, indent=2))
    bundle = ROOT / "output/runpod-openweight-20260930.tar.gz"
    bundle.parent.mkdir(exist_ok=True)
    with tarfile.open(bundle, "w:gz") as archive:
        for directory in [OUT, REPORTS, ROOT / "scripts/runpod"]:
            for path in sorted(directory.rglob("*")):
                if path.is_file() and path.name != "account-after.json" and "__pycache__" not in path.parts:
                    archive.add(path, arcname=str(path.relative_to(ROOT)))
    (bundle.parent / (bundle.name + ".sha256")).write_text(__import__("hashlib").sha256(bundle.read_bytes()).hexdigest() + "\n")


if __name__ == "__main__":
    main()
