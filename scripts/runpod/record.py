"""Record one pinned open-weight setting on the unmodified SDB dataset."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from streamdecisionbench.adapters.base import FatalAdapterError, StatelessAdapter
from streamdecisionbench.jev import validate_response
from streamdecisionbench.lite.core import load_dataset, request_for
from streamdecisionbench.lite.runtime import run_dataset


class LayaAdapter(StatelessAdapter):
    def __init__(self, agent, model: str, lock: threading.Lock):
        self.agent, self.model, self.lock = agent, model, lock
        self.name = f"laya:{model}"

    def system_one(self, request):
        import torch

        with self.lock:
            if self.agent.device.type != "cuda" or self.agent.cpu_fallback_count:
                raise FatalAdapterError("Laya must stay on CUDA without CPU fallback")
            response = self.agent.system_one(
                request["state"], request["questions"], max_len=8192, head_max_len=1024,
            )
            torch.cuda.synchronize()
            if self.agent.cpu_fallback_count:
                raise FatalAdapterError("Laya attempted a CPU fallback")
            usage = response["usage"]
            if usage["truncated"] or usage["state_tokens_dropped"] or usage.get("options"):
                raise FatalAdapterError("Laya truncated state or collapsed question options")
            response["model"] = self.model
            return response


class DJevAdapter(StatelessAdapter):
    def __init__(self, endpoint: str, model: str):
        import httpx

        self.client = httpx.Client(base_url=endpoint, timeout=90.0)
        self.model, self.name = model, f"djev:{model}"

    def system_one(self, request):
        import httpx

        try:
            reply = self.client.post("/v1/systemone", json={
                **request, "model": self.model, "steps": 1, "think": 0,
                "samples": "auto", "auto_max": 4, "auto_threshold": 0.1,
                "seed": 42,
            })
            reply.raise_for_status()
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise ConnectionError("DJev transport failed") from error
        except httpx.HTTPStatusError as error:
            raise FatalAdapterError(f"DJev returned HTTP {error.response.status_code}") from error
        result = reply.json()
        # Keep upstream diagnostics with the response usage, without changing any answer.
        result.setdefault("usage", {})["djev_diagnostics"] = result.get("diagnostics")
        return result

    def close(self):
        self.client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", required=True, choices=("laya", "djev"))
    parser.add_argument("--model", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8011")
    args = parser.parse_args()
    episodes, manifest = load_dataset(ROOT / "data/lite/v1")
    if len(episodes) != 8 or sum(len(e["steps"]) for e in episodes) != 480:
        raise ValueError("This cohort requires all eight scenarios and 480 states")
    config = {
        "provider": args.backend, "model": args.model, "model_revision": args.revision,
        "reasoning_effort": None, "protocol": "retry_excluded_successful_attempt_v1",
        "workers": 32, "episode_concurrency": 1, "request_timeout_s": 90.0,
        "max_attempts": 3, "retry_delay_s": 0.5, "sdk_retries": 0,
        "custom_endpoint": args.backend == "djev",
        "measurement_location": "RunPod; benchmark and model on the same GPU host",
        "untimed": "one final successful response per state; failed transport attempts excluded from model timing",
        "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    if args.backend == "laya":
        import torch
        from laya import Agent

        torch.set_num_threads(4)
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is required")
        agent = Agent(args.model, device="cuda", revision=args.revision, fast=False, compile=False)
        config["inference"] = {
            "max_len": 8192, "head_max_len": 1024, "compile": False, "fast": False,
            "amp_dtype": str(agent.dtype), "cpu_fallback_allowed": False,
            "checkpoint_config": agent.cfg,
        }
        lock = threading.Lock()
        factory = lambda: LayaAdapter(agent, args.model, lock)
    else:
        config["inference"] = {
            "steps": 1, "think": 0, "samples": "auto", "auto_max": 4,
            "auto_threshold": 0.1, "seed": 42, "canvas_length": 128,
        }
        factory = lambda: DJevAdapter(args.endpoint, args.model)
    # Check only contract/input compatibility before recording. Do not consult gold,
    # select a setting from accuracy, or warm up on a benchmark request.
    probe = {
        "state": {"message": "The meeting starts tomorrow."},
        "questions": {"today": {"type": "noul", "instructions": "Does the meeting start today?"}},
    }
    adapter = factory()
    try:
        for _ in range(3):
            validate_response(adapter.system_one(probe), probe["questions"])
    finally:
        adapter.close()
    print(json.dumps(config, ensure_ascii=False), flush=True)
    scores = run_dataset(episodes, manifest, factory, args.out, config)
    print(json.dumps({k: v for k, v in scores.items() if k != "per_episode"}), flush=True)


if __name__ == "__main__":
    main()
