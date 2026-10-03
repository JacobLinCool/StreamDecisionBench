"""Detached Pod supervisor: prepare pinned models, record, and preserve failures."""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tarfile
import time


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def bounded_run(command, log, timeout, *, cwd=None, env=None):
    """A timed-out command must not leave GPU or installer descendants running."""
    with log.open("w") as stream:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except BaseException:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise
    if code:
        raise RuntimeError(f"Command failed with exit code {code}; see {log.name}")


def prepare(setting):
    from huggingface_hub import snapshot_download
    import torch
    destination = Path(os.environ.get("SDB_MODELS", "/opt/sdb-models")) / setting["id"]
    destination.mkdir(parents=True, exist_ok=True)
    snapshot = Path(snapshot_download(setting["model"], revision=setting["revision"],
                                     ignore_patterns=["*.msgpack", "*.h5", "*.bin", "assets/*"]))
    base = None
    if setting["backend"] == "kev":
        from kev.checkpoint import Checkpoint
        # Fetch exactly the base Kev loads offline; a full-weight checkpoint only needs its tokenizer.
        checkpoint = Checkpoint(str(snapshot))
        meta = checkpoint.meta
        if meta.base != setting["base_model"] or not meta.base_revision.startswith(setting["base_revision"]):
            raise ValueError("Kev base identity differs from plan")
        base = snapshot_download(meta.base, revision=meta.base_revision,
                                 ignore_patterns=["*.msgpack", "*.h5", "*.bin"] + (["*.safetensors"] if checkpoint.full else []))
        model_path = snapshot
    elif setting["backend"] == "nimble":
        from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration
        from peft import PeftModel
        from nimble.training.candidate_schema import validate_contract
        contract = json.loads((snapshot / "schema_config.json").read_text())
        if (contract["model"], contract["revision"]) != (setting["base_model"], setting["base_revision"]):
            raise ValueError("Nimble base identity differs from plan")
        tokenizer = AutoTokenizer.from_pretrained(snapshot)
        validate_contract(contract, tokenizer)
        base = snapshot_download(contract["model"], revision=contract["revision"],
                                 ignore_patterns=["*.msgpack", "*.h5", "*.bin"])
        backbone = Qwen3_5ForConditionalGeneration.from_pretrained(base, dtype=torch.bfloat16,
                                                                  device_map="cpu", local_files_only=True)
        adapter = PeftModel.from_pretrained(backbone, snapshot, local_files_only=True)
        merged = adapter.merge_and_unload(safe_merge=True)
        model_path = destination / "merged"
        merged.save_pretrained(model_path)
        tokenizer.save_pretrained(model_path)
        (model_path / "schema_config.json").write_text(json.dumps(contract, indent=2))
        (model_path / "READY.json").write_text(json.dumps({"model": setting["model"], "revision": setting["revision"]}))
    else:
        model_path = snapshot
    # Hash the files actually used, including the immutable base and merged weights.
    hashes = {}
    for tag, directory in [("release", snapshot), ("base", Path(base) if base else None), ("loaded", model_path)]:
        if directory is not None:
            for path in sorted(directory.rglob("*")):
                if path.is_file() and path.suffix in {".safetensors", ".pt", ".json", ".jinja"}:
                    with path.open("rb") as stream:
                        hashes[f"{tag}/{path.relative_to(directory)}"] = hashlib.file_digest(stream, "sha256").hexdigest()
    atomic_json(destination / "prepared.json", {"model": setting["model"], "model_revision": setting["revision"],
                                                "model_path": str(model_path), "weight_and_config_sha256": hashes})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--prepare", help="prepare this setting only")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    if args.prepare:
        prepare(next(s for s in plan["settings"] if s["id"] == args.prepare))
        return
    root = Path(__file__).resolve().parents[2]
    out = Path("/workspace/results")
    out.mkdir(exist_ok=True)
    (out / "logs").mkdir(exist_ok=True)
    (out / "runs").mkdir(exist_ok=True)
    status = {"status": "running", "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "settings": {s["id"]: {"status": "pending"} for s in plan["settings"]},
              "unavailable_settings": plan["unavailable_settings"]}
    deadline = datetime.fromisoformat(plan["worker_deadline_utc"]).timestamp()
    def update():
        status["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        atomic_json(out / "status.json", status)
        os.sync()
    update()
    for setting in plan["settings"]:
        label = setting["id"]
        status["current_setting"] = label
        if time.time() + 1200 > deadline:
            status["settings"][label] = {"status": "not_started", "reason": "Insufficient time before remote budget deadline"}
            update()
            continue
        python = setting["python"]
        env = os.environ.copy()
        env["PYTHONPATH"] = "/workspace/upstream/kev:/workspace/upstream/nimble:/workspace/upstream/semif/src"
        env.update({"HF_HOME": "/opt/sdb-hf", "PYTHONUNBUFFERED": "1", "TOKENIZERS_PARALLELISM": "false",
                    "OMP_NUM_THREADS": "4", "KEV_PREFIX_CACHE": "0", "KEV_DATE_FACTS": "0"})
        try:
            status["settings"][label] = {"status": "preparing"}
            update()
            bounded_run([python, __file__, "--plan", str(args.plan), "--prepare", label],
                        out / "logs" / f"{label}.prepare.log", min(1500, deadline - time.time() - 1000), env=env)
            prepared = Path("/opt/sdb-models") / label / "prepared.json"
            (out / f"{label}.prepared.json").write_bytes(prepared.read_bytes())
            status["settings"][label] = {"status": "recording"}
            update()
            env["HF_HUB_OFFLINE"] = "1"
            bounded_run([python, str(root / "scripts/runpod/decision_record.py"), "--plan", str(args.plan),
                         "--setting", label, "--out", str(out / "runs" / label)],
                        out / "logs" / f"{label}.record.log", min(3600, deadline - time.time()), cwd=root, env=env)
            status["settings"][label] = {"status": "complete"}
        except Exception as error:
            status["settings"][label] = {"status": "failed", "error": repr(error)}
        update()
    status.pop("current_setting", None)
    status["status"] = "complete" if all(s["status"] == "complete" for s in status["settings"].values()) else "finished_with_failures"
    update()
    try:
        bounded_run(["/opt/sdb-native-env/bin/python", str(root / "scripts/runpod/decision_report.py"),
                     "--raw", str(out), "--reports", "/workspace/reports"],
                    out / "logs/report.log", min(1200, max(1, deadline - time.time())), cwd=root)
        status["remote_report"] = "complete"
    except Exception as error:
        status["remote_report"] = repr(error)
    update()
    # A small, self-contained durable snapshot exists before provider auto-stop.
    with tarfile.open("/workspace/evidence.tar.gz", "w:gz") as archive:
        archive.add(out, arcname="results")
        archive.add(args.plan, arcname="plan.json")
        if Path("/workspace/reports").exists():
            archive.add("/workspace/reports", arcname="reports")
    with Path("/workspace/evidence.tar.gz").open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    atomic_json(out / "remote-finished.json", {"evidence_sha256": checksum,
                                               "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                                               "compute_independent_of_local_connection": True})
    os.sync()


if __name__ == "__main__":
    main()
