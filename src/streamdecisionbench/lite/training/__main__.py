"""python -m streamdecisionbench.lite.training check|dump

check [MODULE ...]   validate training modules (default: all) and audit them for evaluation leakage
dump MODULE --out D  write a module's public states, questions and decision spec without gold, plus gold separately
"""

from __future__ import annotations

import argparse
import json
from importlib import import_module
from pathlib import Path

from streamdecisionbench.lite.training import MODULES
from streamdecisionbench.lite.training.audit import check_module


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check")
    check.add_argument("modules", nargs="*", default=MODULES)
    dump = commands.add_parser("dump")
    dump.add_argument("module")
    dump.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "check":
        for name in args.modules:
            result = check_module(import_module(f"streamdecisionbench.lite.training.{name}"))
            print(json.dumps(result, indent=2))
        return
    module = import_module(f"streamdecisionbench.lite.training.{args.module}")
    args.out.mkdir(parents=True, exist_ok=True)
    for scenario in module.scenarios():
        eid = scenario["episode_id"]
        public = {k: scenario[k] for k in ("episode_id", "task_family", "title", "tick_seconds", "questions", "decision_spec")}
        (args.out / f"{eid}.public.json").write_text(json.dumps(public, ensure_ascii=False, indent=2) + "\n")
        with (args.out / f"{eid}.states.jsonl").open("w") as states, (args.out / f"{eid}.gold.jsonl").open("w") as gold:
            for step in scenario["steps"]:
                states.write(json.dumps({"t": step["t"], "state": step["state"]}, ensure_ascii=False) + "\n")
                gold.write(json.dumps({"t": step["t"], "gold": step["gold"]}, ensure_ascii=False) + "\n")
        print(f"{eid}: {args.out / (eid + '.public.json')}, .states.jsonl (no gold), .gold.jsonl")


if __name__ == "__main__":
    main()
