"""Package this experiment's evidence and the code needed to reproduce its reports."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "runs/runpod-openweight-20260930"
REPORTS = ROOT / "docs/lite/results/runpod-openweight-20260930"
BUNDLE = ROOT / "output/runpod-openweight-20260930.tar.gz"


def main():
    cost = json.loads((RAW / "cost.json").read_text())
    if not cost["deletion_verified"]:
        raise ValueError("Verify Pod deletion before publishing the final bundle")
    results = json.loads((REPORTS / "results.json").read_text())
    if results["complete_settings"] != results["expected_settings"] or results["failures"]:
        raise ValueError("All cohort settings must be complete before publishing the final bundle")
    validation = json.loads((RAW / "validation.json").read_text())
    if validation["valid_requests"] != 1920 or validation["input_audit_issues"]:
        raise ValueError("Verify all requests and input coverage before publishing the final bundle")
    paths = set()
    for folder in [RAW, REPORTS, ROOT / "scripts/runpod"]:
        paths.update(p for p in folder.rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts and p.name != "account-after.json"
                     and not p.name.endswith(".shadow.md"))
    tracked = subprocess.check_output([
        "git", "ls-files", "src", "data/lite/v1", "scripts/lite", "paper/analysis/lite_*.py",
        "paper/analysis/evaluation_policy.json", "pyproject.toml", "uv.lock", "LICENSE", "README.md",
        "tests/test_lite_core.py", "tests/test_lite_reports.py", "tests/test_lite_runtime_retries.py",
    ], cwd=ROOT, text=True).splitlines()
    paths.update(ROOT / name for name in tracked if not name.endswith(".shadow.md"))
    paths.add(ROOT / "tests/test_runpod_recording.py")
    manifest = {
        "complete_settings": results["complete_settings"],
        "expected_settings": results["expected_settings"],
        "pod_deletion_verified": True,
        "files": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)},
    }
    manifest_path = RAW / "bundle-manifest.json"
    # The manifest describes the payload; it does not recursively hash itself.
    manifest["files"].pop(str(manifest_path.relative_to(ROOT)), None)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    paths.add(manifest_path)
    BUNDLE.parent.mkdir(exist_ok=True)
    with tarfile.open(BUNDLE, "w:gz") as archive:
        for path in sorted(paths):
            archive.add(path, arcname=str(path.relative_to(ROOT)))
    with BUNDLE.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    BUNDLE.with_name(BUNDLE.name + ".sha256").write_text(checksum + "\n")
    print(json.dumps({"bundle": str(BUNDLE), "sha256": checksum, "files": len(paths),
                      "complete_settings": results["complete_settings"]}, indent=2))


if __name__ == "__main__":
    main()
