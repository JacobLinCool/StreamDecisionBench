"""Record native decision runtimes with lossless inputs and immutable provenance."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from streamdecisionbench.adapters.base import StatelessAdapter
from streamdecisionbench.jev import validate_response
from streamdecisionbench.lite.core import digest, load_dataset, request_for
from streamdecisionbench.lite.runtime import run_dataset


def text(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def enum_schema(request):
    result = {}
    for key, question in request["questions"].items():
        if question["type"] != "choice":
            raise ValueError("This adapter accepts the choice-only SDB cohort")
        result[key] = {"type": "enum", "description": text(question["instructions"]),
                       "choices": list(question["criteria"]),
                       "choice_descriptions": {k: text(v) if v is not None else ""
                                               for k, v in question["criteria"].items()}}
    return result


def direct_rows(request):
    for key, question in request["questions"].items():
        if question["type"] != "choice":
            raise ValueError("This adapter accepts the choice-only SDB cohort")
        yield {"id": key, "state": request["state"], "question": text(question["instructions"]),
               "options": [{"id": k, "description": text(v) if v is not None else k}
                           for k, v in question["criteria"].items()]}


def choice_answer(choice, probabilities):
    k = len(probabilities)
    confidence = 1.0 if k == 1 else (max(probabilities.values()) - 1 / k) / (1 - 1 / k)
    return {"type": "choice", "choice": choice, "probabilities": probabilities,
            "confidence": max(0.0, min(1.0, confidence))}


class NativeAdapter(StatelessAdapter):
    def __init__(self, backend, model, runtime, lock):
        self.backend, self.model, self.runtime, self.lock = backend, model, runtime, lock
        self.name = f"{backend}:{model}"

    def system_one(self, request):
        import torch
        if self.backend == "kev":
            from kev.api import SystemOneRequest
            return self.runtime.answer(SystemOneRequest(**request, model=self.model))
        with self.lock:
            if self.backend == "nimble":
                result = self.runtime.score(text(request["state"]), enum_schema(request))
                answers = {key: choice_answer(value, result["fields"][key]["scores"])
                           for key, value in result["output"].items()}
                usage = {"input_tokens": sum(f["prompt_token_count"] for f in result["fields"].values()),
                         "output_tokens": 0, "native_fields": result["fields"],
                         "native_metrics": result["metrics"]}
            else:
                from semif_phase1.direct import score
                model, tokenizer, metadata = self.runtime
                answers, fields = {}, {}
                for row in direct_rows(request):
                    result = score(model, tokenizer, row, metadata, max_tokens=8192)
                    probabilities = dict(zip(result["option_ids"], result["probabilities"]))
                    best = max(probabilities, key=probabilities.get)
                    answers[row["id"]] = choice_answer(best, probabilities)
                    fields[row["id"]] = result
                usage = {"input_tokens": sum(f["input_tokens"] for f in fields.values()),
                         "output_tokens": 0, "native_fields": fields}
            torch.cuda.synchronize()
            return {"model": self.model, "answers": answers, "usage": usage}


def input_audit(backend, runtime, episodes, manifest):
    rows = []
    for episode in episodes:
        for step in episode["steps"]:
            request = request_for(episode, step)
            if backend == "kev":
                from kev.api import SystemOneRequest, to_record
                rec, meta = to_record(SystemOneRequest(**request))
                enc = runtime.model.encode(runtime.tok, rec, max_state=65536, max_branch=73728, strict=True)
                if enc["state_truncated"] or [len(x) for x in enc["opt_idx"]] != [len(q["criteria"]) for q in request["questions"].values()]:
                    raise ValueError("Native Kev input coverage mismatch")
                tokens = [enc["seg"].count(0) + enc["seg"].count(i + 1) for i in range(len(meta))]
            elif backend == "nimble":
                prepared = runtime.prepare(text(request["state"]), enum_schema(request))
                if list(prepared.names) != list(request["questions"]) or [list(x) for x in prepared.choices] != [list(q["criteria"]) for q in request["questions"].values()]:
                    raise ValueError("Native Nimble input coverage mismatch")
                tokens = [len(x) for x in prepared.full_ids]
            else:
                from semif_phase1.direct import encode_prompt
                tokens = [len(encode_prompt(runtime[1], row, 8192)[0]) for row in direct_rows(request)]
            rows.append({"episode_id": episode["episode_id"], "t": step["t"],
                         "request_sha256": digest(request), "question_tokens": tokens})
    if len(rows) != 480:
        raise ValueError("Expected 480 audited requests")
    return {"backend": backend, "dataset_hash": manifest["dataset_hash"], "requests": 480,
            "question_rows": sum(len(r["question_tokens"]) for r in rows), "issues": [],
            "max_sequence_tokens": max(n for r in rows for n in r["question_tokens"]), "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--setting", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    setting = next(s for s in plan["settings"] if s["id"] == args.setting)
    backend = setting["backend"]
    import torch
    torch.manual_seed(42)
    torch.set_num_threads(4)
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("Native CUDA BF16 is required")
    if os.environ.get("HF_HUB_OFFLINE") != "1":
        raise RuntimeError("Recording must use the prepared offline checkpoints")
    path = Path(os.environ.get("SDB_MODELS", "/opt/sdb-models")) / setting["id"]
    prepared = json.loads((path / "prepared.json").read_text())
    if prepared["model_revision"] != setting["revision"]:
        raise ValueError("Prepared checkpoint differs from plan")
    if backend == "kev":
        from kev.checkpoint import Checkpoint, LoadOptions
        from kev.serve import Server
        checkpoint = Checkpoint(prepared["model_path"])
        tok, model = checkpoint.load("cuda", LoadOptions(dtype=torch.bfloat16, backend="torch",
                                                         cuda_graphs=False, fused=True))
        runtime = Server(checkpoint, tok, model, "cuda", release_date="2026-09-24")
        placement = {str(p.device) for p in model.parameters()}
        inference = {"dtype": model.dtype, "fused": True, "cuda_graphs": False,
                     "prefix_cache_size": runtime.prefix_cache.size,
                     "temperature": model.head.temperature, "date_facts": False}
    elif backend == "nimble":
        from nimble.scoring.cuda_scorer import CudaCandidateScorer
        runtime = CudaCandidateScorer(prepared["model_path"], setting["model"], setting["revision"],
                                      max_input_tokens=8192, temperature=1.0, device_map=None)
        placement = {str(p.device) for p in runtime.model.parameters()}
        inference = {**runtime.runtime, "temperature": runtime.temperature, "mode": "independent",
                     "max_input_tokens": 8192, "merged": True}
    else:
        from semif_phase1.core import load_causal_model
        runtime = load_causal_model(prepared["model_path"], setting["revision"], device="cuda", dtype="bfloat16")
        placement = {str(p.device) for p in runtime[0].parameters()}
        inference = {**runtime[2], "mode": "direct", "max_input_tokens": 8192,
                     "thinking_enabled": False, "generated_tokens": 0}
    if any(not d.startswith("cuda") for d in placement):
        raise RuntimeError(f"CPU/offload execution is forbidden: {placement}")
    episodes, manifest = load_dataset(ROOT / "data/lite/v1")
    if manifest["dataset_hash"] != plan["dataset_sha256"]:
        raise ValueError("Dataset differs from plan")
    audit = input_audit(backend, runtime, episodes, manifest)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    (args.out.parent.parent / f"{args.setting}.input-audit.json").write_text(json.dumps(audit, indent=2))
    lock = threading.Lock()
    factory = lambda: NativeAdapter(backend, setting["model"], runtime, lock)
    probe = {"state": {"message": "The meeting is tomorrow."}, "questions": {
        "when": {"type": "choice", "instructions": "When does the meeting start?",
                 "criteria": {"today": "today", "tomorrow": "tomorrow"}}}}
    adapter = factory()
    for _ in range(3):
        validate_response(adapter.system_one(probe), probe["questions"])
    config = {"provider": backend, "model": setting["model"], "model_revision": setting["revision"],
              "reasoning_effort": None, "protocol": "retry_excluded_successful_attempt_v1",
              "workers": 32, "episode_concurrency": 1, "request_timeout_s": None,
              "transport": "native_library", "setting_process_timeout_s": 3600,
              "max_attempts": 3, "retry_delay_s": 0.5, "sdk_retries": 0, "custom_endpoint": False,
              "measurement_location": os.environ.get("SDB_MEASUREMENT_LOCATION", "RunPod; native library and benchmark on same GPU host"),
              "untimed": "final successful response per state; transport failures excluded",
              "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "inference": inference, "prepared_checkpoint": prepared,
              "input_audit_sha256": hashlib.sha256(json.dumps(audit, indent=2).encode()).hexdigest()}
    print(json.dumps(config), flush=True)
    try:
        run_dataset(episodes, manifest, factory, args.out, config)
    finally:
        if backend == "kev":
            runtime.close()


if __name__ == "__main__":
    main()
