"""Audit the exact native Laya token budgets without making model calls."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from streamdecisionbench.lite.core import load_dataset, request_for


def main():
    from huggingface_hub import snapshot_download
    from laya import Agent
    from laya.common import build_sequence, encode_text, render_options, serialize_state
    from transformers import AutoTokenizer
    from cohort import SETTINGS

    episodes, manifest = load_dataset(ROOT / "data/lite/v1")
    audit = {"dataset_hash": manifest["dataset_hash"], "max_len": 8192, "head_max_len": 1024, "settings": {}}
    for label, model, revision in SETTINGS:
        path = snapshot_download(
            model, revision=revision, local_files_only=True,
            allow_patterns=["rl_agent_config.json", "model.safetensors", "tokenizer/*", "encoder/*"],
        )
        tokenizer = AutoTokenizer.from_pretrained(Path(path) / "tokenizer")
        rows = []
        issues = []
        for episode in episodes:
            for step in episode["steps"]:
                request = request_for(episode, step)
                state_ids = encode_text(tokenizer, serialize_state(request["state"]).replace(tokenizer.mask_token, " "), add_special_tokens=False)["input_ids"]
                for qid, definition in request["questions"].items():
                    question = Agent._to_internal(definition)
                    instructions = f"{question['t']} question: {question['ins']}".replace(tokenizer.mask_token, " ")
                    head_tokens = len(encode_text(tokenizer, instructions, add_special_tokens=False)["input_ids"])
                    option_tokens = [len(encode_text(tokenizer, " " + value.replace(tokenizer.mask_token, " "), add_special_tokens=False)["input_ids"]) for value in render_options(question)]
                    sequence, markers, options, state = build_sequence(
                        tokenizer, request["state"], question, max_len=8192, head_max_len=1024,
                        state_ids=state_ids, return_stats=True, return_truncation_stats=True,
                    )
                    row = {"episode_id": episode["episode_id"], "t": step["t"], "question": qid,
                           "state_tokens": len(state_ids), "sequence_tokens": len(sequence),
                           "instruction_tokens": head_tokens, "longest_option_tokens": max(option_tokens),
                           "instruction_truncated": head_tokens > max(8, 1024 - sum(1 + min(n, 48) for n in option_tokens)),
                           "option_text_truncated": max(option_tokens) > 48,
                           "state_tokens_dropped": state["state_tokens_dropped"],
                           "option_markers": len(markers), "options_distinct": options["options_distinct"]}
                    rows.append(row)
                    if row["instruction_truncated"] or row["option_text_truncated"] or row["state_tokens_dropped"] or options["options_distinct"] != len(option_tokens):
                        issues.append(row)
        with (Path(path) / "model.safetensors").open("rb") as weights:
            weights_sha256 = hashlib.file_digest(weights, "sha256").hexdigest()
        audit["settings"][label] = {
            "model_revision": revision, "states": 480, "question_rows": len(rows),
            "weights_sha256": weights_sha256,
            "max_state_tokens": max(r["state_tokens"] for r in rows),
            "max_sequence_tokens": max(r["sequence_tokens"] for r in rows),
            "max_instruction_tokens": max(r["instruction_tokens"] for r in rows),
            "max_option_tokens": max(r["longest_option_tokens"] for r in rows),
            "issues": issues,
        }
    output = Path("/workspace/results/input-audit.json")
    output.write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit, indent=2), flush=True)


if __name__ == "__main__":
    main()
