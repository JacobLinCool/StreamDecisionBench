"""Execute the fixed cohort; preserve independent failures and all raw evidence."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = Path("/workspace/sdb")
OUT = Path("/workspace/results")
BENCH = "/workspace/bench-env/bin/python"
DJEV = "/workspace/djev-env/bin/python"
SETTINGS = [
    ("laya-english", "convaiinnovations/laya", "55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851"),
    ("laya-typed-decisions", "convaiinnovations/laya-typed-decisions", "1a793eb568e6718f15941d08f85432581df534e3"),
    ("laya-multilingual", "convaiinnovations/laya-multilingual", "e4e9ddf21a7b1903b7acffd8814ad4307bf63a67"),
]
DIFFUSION_MODEL = "google/diffusiongemma-26B-A4B-it"
DIFFUSION_REVISION = "f7f5b7f5fa82ffc52addd066915886d497f5517b"


def write_status(status):
    status["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    temporary = OUT / "status.tmp"
    temporary.write_text(json.dumps(status, indent=2) + "\n")
    temporary.replace(OUT / "status.json")


def record(backend, label, model, revision):
    with (OUT / "logs" / f"{label}.log").open("w") as log:
        result = subprocess.run([
            BENCH, str(ROOT / "scripts/runpod/record.py"), "--backend", backend,
            "--model", model, "--revision", revision, "--out", str(OUT / "runs" / label),
        ], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=2400)
    return result.returncode


def wait_ready(url, process, deadline):
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Server exited with {process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status == 200:
                    return
        except (OSError, TimeoutError):
            pass
        time.sleep(5)
    raise TimeoutError(f"Server did not become ready: {url}")


def main():
    OUT.mkdir(exist_ok=True)
    (OUT / "runs").mkdir(exist_ok=True)
    (OUT / "logs").mkdir(exist_ok=True)
    status = {"status": "running", "settings": {}, "started_at_utc": datetime.now(timezone.utc).isoformat()}
    write_status(status)
    # Download the largest checkpoint while the small encoders record, using the
    # same immutable revision later loaded by vLLM.
    download_log = (OUT / "logs/download.log").open("w")
    download = subprocess.Popen([
        DJEV, "-c", "from huggingface_hub import snapshot_download; "
        f"print(snapshot_download({DIFFUSION_MODEL!r}, revision={DIFFUSION_REVISION!r}, "
        "ignore_patterns=['*.msgpack','*.h5','*.bin','original/*']))",
    ], stdout=download_log, stderr=subprocess.STDOUT)
    for label, model, revision in SETTINGS:
        status["current_setting"] = label
        write_status(status)
        try:
            code = record("laya", label, model, revision)
            status["settings"][label] = {"status": "complete" if code == 0 else "failed", "exit_code": code}
        except Exception as error:
            status["settings"][label] = {"status": "failed", "error": repr(error)}
        write_status(status)
    processes = []
    logs = []
    label = "djev-diffusiongemma"
    status["current_setting"] = label
    write_status(status)
    try:
        if download.wait(timeout=900) != 0:
            raise RuntimeError("DiffusionGemma download failed")
        from huggingface_hub import snapshot_download

        model_path = snapshot_download(DIFFUSION_MODEL, revision=DIFFUSION_REVISION, local_files_only=True)
        log = (OUT / "logs/vllm.log").open("w")
        logs.append(log)
        engine = subprocess.Popen([
            "/workspace/djev-env/bin/vllm", "serve", model_path,
            "--served-model-name", "dgemma", "--host", "127.0.0.1", "--port", "8010",
            "--enforce-eager", "--language-model-only", "--attention-backend", "TRITON_ATTN",
            "--gpu-memory-utilization", "0.9", "--max-model-len", "16384",
            "--max-num-seqs", "32", "--max-logprobs", "32", "--enable-prefix-caching",
            "--diffusion-config", '{"canvas_length":128}',
        ], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(engine)
        wait_ready("http://127.0.0.1:8010/health", engine, time.monotonic() + 900)
        log = (OUT / "logs/djev-server.log").open("w")
        logs.append(log)
        server = subprocess.Popen([
            DJEV, "/workspace/djev/structured_server.py", "--upstream", "http://127.0.0.1:8010",
            "--model", "dgemma", "--tokenizer", model_path, "--canvas", "128",
            "--host", "127.0.0.1", "--port", "8011",
        ], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(server)
        wait_ready("http://127.0.0.1:8011/v1/models", server, time.monotonic() + 180)
        code = record("djev", label, "dgemma", DIFFUSION_REVISION)
        status["settings"][label] = {"status": "complete" if code == 0 else "failed", "exit_code": code}
    except Exception as error:
        status["settings"][label] = {"status": "failed", "error": repr(error)}
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        if download.poll() is None:
            download.terminate()
            download.wait(timeout=30)
        for log in logs + [download_log]:
            log.close()
    status["status"] = "complete" if all(s["status"] == "complete" for s in status["settings"].values()) else "finished_with_failures"
    status.pop("current_setting", None)
    write_status(status)


if __name__ == "__main__":
    main()
