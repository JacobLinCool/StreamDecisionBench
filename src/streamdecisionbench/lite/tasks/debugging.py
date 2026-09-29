"""Deterministic, public-evidence-only debugging episodes for SDB Lite."""

from __future__ import annotations

from copy import deepcopy
from fnmatch import fnmatchcase
import re
from typing import Any


POLICY = """You maintain an IDE status badge and its next-action card. All times are
ticks on the session clock; snapshot t is published at tick t and is complete;
decisions are reevaluated only at ticks. A finished run is one with a non-null finished
time. The latest finished run has the greatest finished time; an unfinished run
never replaces its result. Runner results and debugger events override spoken
claims. All lists include every item needed by these rules.

Relevant writes/dirty files match a session.scope_rules pattern (last matching
rule wins); other files are irrelevant. Tests load saved files at run start.
In scope_rules and owners patterns, * matches any characters, including /.
The result badge reports the pinned target in the latest finished run: passed,
failed with the exact original message, failed differently, or not run. Compile
failure, interruption, a missing target or SKIPPED target means not run.

Process badge: no unfinished run -> idle; debugger paused -> paused; otherwise
silence of at least 4 ticks -> stalled; otherwise running. Silence is measured
from the latest of run start, that run's terminal line times, and continued
debugger events for that run. Unrelated terminal output does not reset silence.
Evaluate/step do not resume a paused run. Paused time is measured since its most
recent debugger event, including evaluate/step, not since a save or a comment.

Choose the route by FIRST matching rule:
1. Unfinished run paused, with no debugger event for at least 4 ticks:
   control/continue. Unfinished run not paused, silent at least 6 ticks:
   control/stop. These override dirty buffers and recent writes.
2. Any unfinished run, relevant dirty file, or relevant write less than 2
   ticks old: wait.
3. No finished run, or a relevant write strictly after latest finished run's
   start: rerun. Determine scope from ALL relevant writes after that start:
   choose widest mapped scope, target < module < full. If no such writes,
   choose target. A write exactly at run start is included in that run.
4. Latest finished run has compiler errors: inspect its FIRST compiler file.
5. Latest finished run interrupted or did not execute pinned target: rerun
   target (takes precedence over other test failures).
6. Latest finished run has failed tests: select first newly failing test
   compared with the previous finished run; if none, select pinned target if
   failed; otherwise first failing test. Result list order defines first.
   Select its last trace frame under a session.project_roots prefix (trace is
   outermost first). Its owner is the LAST matching session.owners rule.
   If owner is another team: delegate to that team, unless a final teammate
   message makes a positive first-person commitment to contact that exact team
   about that exact run, or says they have done so; then wait. A question,
   suggestion, negation, partial message, other run or other team does not count.
   If owner is own team: inspect selected frame's file.
7. More skipped tests than session.allowed_skips: rerun module.
8. There are tracked uncommitted files: ready. Otherwise wait.

Answer every question independently from this same snapshot. The consumer uses
route, process and target_result, plus only rerun_scope for rerun, inspect_file
for inspect, control_action for control, or owner for delegate. Inactive branch
answers do not affect the application decision. Return none for those fields.
"""


def _scope(state: dict[str, Any], path: str) -> str | None:
    answer = None
    for pattern, scope in state["session"]["scope_rules"]:
        if fnmatchcase(path, pattern):
            answer = scope
    return answer


def _failure(state: dict[str, Any], finished: list[dict]) -> dict | None:
    latest = finished[-1]
    failures = [row for row in latest["results"] if row["outcome"] == "FAILED"]
    if not failures:
        return None
    before = {
        row["test"] for row in finished[-2]["results"] if row["outcome"] == "FAILED"
    } if len(finished) > 1 else set()
    new = [row for row in failures if row["test"] not in before]
    target = state["session"]["target_test"]
    return next(iter(new), next((row for row in failures if row["test"] == target), failures[0]))


def _contacted(state: dict[str, Any], team: str, run_id: str) -> bool:
    # The scenario utterance grammar contains these positive first-person forms.
    # No hidden speech-act annotations are used by the evaluator.
    pattern = (
        r"(?:I'll|I will|I'm going to) (?:contact|message) "
        + re.escape(team) + r" about " + re.escape(run_id) + r"[.!]?"
        + r"|(?:I've|I have) (?:contacted|messaged) "
        + re.escape(team) + r" about " + re.escape(run_id) + r"[.!]?"
    )
    return any(
        row["final"] and row["speaker"] in state["session"]["teammates"]
        and re.fullmatch(pattern, row["text"]) is not None
        for row in state["call"]
    )


def reference(state: dict[str, Any]) -> dict[str, str]:
    """Evaluate only public fields; never reads scenario/tick/gold metadata."""
    now = state["clock_tick"]
    finished = sorted(
        (run for run in state["runs"] if run["finished"] is not None),
        key=lambda run: run["finished"],
    )
    active = next((run for run in state["runs"] if run["finished"] is None), None)
    latest = finished[-1] if finished else None
    target = next((row for row in latest["results"]
                   if row["test"] == state["session"]["target_test"]), None) if latest else None
    badge = "not_run"
    if latest and not latest["compiler_errors"] and not latest["interrupted"] and target:
        if target["outcome"] == "PASSED":
            badge = "passed"
        elif target["outcome"] == "FAILED":
            badge = "original_error" if target["message"] == state["session"]["original_failure"] else "different_error"
    answer = {"route": "wait", "process": "idle", "target_result": badge,
              "rerun_scope": "none", "inspect_file": "none",
              "control_action": "none", "owner": "none"}
    if active:
        events = [e for e in state["debugger"]["events"] if e["run"] == active["id"]]
        paused = state["debugger"]["status"] == "paused"
        activity = [active["started"]]
        activity += [row["time"] for row in state["terminal"] if row["run"] == active["id"]]
        activity += [event["time"] for event in events if event["kind"] == "continued"]
        silence = now - max(activity)
        answer["process"] = "paused" if paused else "stalled" if silence >= 4 else "running"
        if paused and now - max(event["time"] for event in events) >= 4:
            return answer | {"route": "control", "control_action": "continue"}
        if not paused and silence >= 6:
            return answer | {"route": "control", "control_action": "stop"}
        return answer
    relevant = [row for row in state["saves"] if _scope(state, row["file"])]
    if any(_scope(state, path) for path in state["editor"]["dirty_files"]):
        return answer
    if relevant and now - max(row["time"] for row in relevant) < 2:
        return answer
    writes = [row for row in relevant if latest is None or row["time"] > latest["started"]]
    if latest is None or writes:
        scopes = [_scope(state, row["file"]) for row in writes] or ["target"]
        scope = max(scopes, key=lambda value: {"target": 0, "module": 1, "full": 2}[value])
        return answer | {"route": "rerun", "rerun_scope": scope}
    if latest["compiler_errors"]:
        return answer | {"route": "inspect", "inspect_file": latest["compiler_errors"][0]["file"]}
    if latest["interrupted"] or target is None or target["outcome"] == "SKIPPED":
        return answer | {"route": "rerun", "rerun_scope": "target"}
    failure = _failure(state, finished)
    if failure:
        frame = [path for path in failure["trace"] if any(
            path.startswith(root) for root in state["session"]["project_roots"]
        )][-1]
        owner = state["session"]["own_team"]
        for pattern, team in state["session"]["owners"]:
            if fnmatchcase(frame, pattern):
                owner = team
        if owner != state["session"]["own_team"]:
            if _contacted(state, owner, latest["id"]):
                return answer
            return answer | {"route": "delegate", "owner": owner}
        return answer | {"route": "inspect", "inspect_file": frame}
    skipped = sum(row["outcome"] == "SKIPPED" for row in latest["results"])
    if skipped > state["session"]["allowed_skips"]:
        return answer | {"route": "rerun", "rerun_scope": "module"}
    if state["git"]["uncommitted"]:
        return answer | {"route": "ready"}
    return answer


def _questions(files: list[str], teams: list[str]) -> dict[str, dict]:
    choices = {
        "route": {"wait": "Leave action card empty", "rerun": "Run tests at the selected scope",
                  "inspect": "Open the selected error file", "control": "Control the active run",
                  "delegate": "Ask the selected external team", "ready": "Mark changes ready to commit"},
        "process": {"idle": "No run in progress", "running": "Active, not paused, silence below 4 ticks",
                    "paused": "Debugger currently paused", "stalled": "Active, not paused, silence at least 4 ticks"},
        "target_result": {"not_run": "Latest finished run did not execute the target",
                          "passed": "Target passed in latest finished run", "original_error": "Target failed with original message",
                          "different_error": "Target failed with a different message"},
        "rerun_scope": {"none": "No rerun route", "target": "Pinned target only", "module": "Whole target test module", "full": "Full project suite"},
        "inspect_file": {"none": "No inspect route", **{path: "Open " + path for path in files}},
        "control_action": {"none": "No control route", "continue": "Continue the paused debugger", "stop": "Stop the silent running process"},
        "owner": {"none": "No delegation route", **{team: "Contact " + team for team in teams}},
    }
    prompts = {
        "route": "Which action card route should the IDE use now?",
        "process": "What process badge is correct now?",
        "target_result": "What pinned-target result badge is correct now?",
        "rerun_scope": "If the rules choose rerun, which scope must that action use? Otherwise none.",
        "inspect_file": "If the rules choose inspect, which file must that action open? Otherwise none.",
        "control_action": "If the rules choose control, what action must that branch use? Otherwise none.",
        "owner": "If the rules choose delegate, which team must that branch contact? Otherwise none.",
    }
    return {qid: {"type": "choice", "instructions": prompts[qid] + " Apply session.policy.",
                  "criteria": criteria} for qid, criteria in choices.items()}


def _run(run_id: str, started: int, finished: int | None, results: list[dict],
         *, errors: list[dict] | None = None, interrupted: bool = False) -> dict:
    return {"id": run_id, "started": started, "finished": finished, "results": results,
            "compiler_errors": errors or [], "interrupted": interrupted,
            "command": "test-runner --reporter=json", "summary": "running" if finished is None else
            "interrupted; no completed result" if interrupted else
            "compilation failed; 0 tests executed" if errors else
            ", ".join(f"{sum(row['outcome'] == status for row in results)} {status.lower()}"
                      for status in ("PASSED", "FAILED", "SKIPPED"))}


def _result(test: str, outcome: str, message: str = "", trace: list[str] | None = None) -> dict:
    return {"test": test, "outcome": outcome, "message": message, "trace": trace or []}


def _scenario(which: str) -> dict:
    a = which == "a"
    target = "grace window refund" if a else "nightly settlement is idempotent"
    original = "Expected 4800; received 4320" if a else "UniqueViolation: settlement_batch_uniq"
    own = "@billing" if a else "@payments-core"
    primary = "src/refunds/grace.ts" if a else "ledger/settlement/batch.py"
    secondary = "src/refunds/fees.ts" if a else "ledger/settlement/scheduler.py"
    external = "src/runtime/clock.ts" if a else "ledger/fx/rates.py"
    other = "tests/grace.test.ts" if a else "ledger/common/pool.py"
    external_team = "@runtime" if a else "@fx-platform"
    files = [primary, secondary] if a else [primary]
    teams = [external_team] if a else [external_team, "@platform-core"]
    target_row = lambda outcome, message="", file=primary: _result(
        target, outcome, message, ["tests/target_test.py", file, ".venv/vendor/assert.py"] if outcome == "FAILED" else [])
    old_id = "R17" if a else "D6"
    active_id = "R18" if a else "D7"
    state = {
        "session": {
            "title": "Refund watch loop" if a else "Settlement integration debug session",
            "policy": POLICY,
            "target_test": target, "original_failure": original, "own_team": own,
            "teammates": ["Priya"] if a else ["Mateo", "Ines"], "allowed_skips": 1 if a else 0,
            "project_roots": ["src/", "tests/"] if a else ["ledger/", "tests/"],
            "scope_rules": [["src/*", "module"], [primary, "target"], ["tests/*", "module"],
                            ["project.config.*", "full"]] if a else
                           [["ledger/*", "module"], [primary, "target"], ["tests/*", "module"], ["ledger/common/*", "full"]],
            "owners": [["*", own], ["src/runtime/*", external_team]] if a else
                      [["*", own], ["ledger/*", "@platform-core"], ["ledger/settlement/*", own], ["ledger/fx/*", external_team]],
        },
        "clock_tick": 0,
        "editor": {"active_file": primary, "cursor_line": 30, "dirty_files": []},
        "saves": [{"time": -2, "file": primary, "diff": "- return cached\n+ return recomputed"}],
        "runs": [_run(old_id, -7, -4, [target_row("FAILED", original)]),
                 _run(active_id, -1, None, [])],
        "terminal": [{"time": 0, "run": active_id, "text": "collected tests; starting target"}],
        "debugger": {"status": "running", "events": []}, "call": [],
        "git": {"uncommitted": [primary]}, "diagnostics": [],
    }
    if not a:
        state["saves"][0]["time"] = -8
        state["runs"] = state["runs"][:1]
        state["terminal"] = [{"time": -4, "run": old_id, "text": "1 failed; settlement_batch_uniq"}]
        state["debugger"]["status"] = "inactive"
    evidence: list[str] = []

    def say(text: str, *, final: bool = True, speaker: str | None = None) -> None:
        state["call"].append({"time": now, "speaker": speaker or state["session"]["teammates"][-1], "text": text, "final": final})
        evidence.append("call: " + text + (" [partial]" if not final else ""))

    def save(path: str, diff: str = "- old_value\n+ revised_value") -> None:
        state["saves"].append({"time": now, "file": path, "diff": diff})
        state["editor"]["dirty_files"] = []
        if path not in state["git"]["uncommitted"]:
            state["git"]["uncommitted"].append(path)
        evidence.append(f"saved {path} at {now}")

    def dirty(path: str) -> None:
        state["editor"]["dirty_files"] = [path]
        evidence.append("buffer edited: " + path)

    def start(run_id: str) -> None:
        state["runs"].append(_run(run_id, now, None, []))
        state["terminal"].append({"time": now, "run": run_id, "text": "$ test-runner; collecting tests"})
        state["debugger"]["status"] = "running"
        evidence.append("run started: " + run_id)

    def finish(results: list[dict], *, errors: list[dict] | None = None, interrupted: bool = False) -> None:
        current = next(run for run in state["runs"] if run["finished"] is None)
        current.update(_run(current["id"], current["started"], now, results, errors=errors, interrupted=interrupted))
        state["terminal"].append({"time": now, "run": current["id"], "text": current["summary"]})
        state["debugger"]["status"] = "inactive"
        evidence.append("run finished: " + current["id"] + "; " + current["summary"])

    def dap(kind: str) -> None:
        current = next(run for run in state["runs"] if run["finished"] is None)
        state["debugger"]["events"].append({"time": now, "run": current["id"], "kind": kind, "file": primary})
        if kind in ("paused", "continued"):
            state["debugger"]["status"] = "paused" if kind == "paused" else "running"
        evidence.append("debugger: " + kind)

    steps = []
    for tick in range(60):
        now = tick
        evidence = []
        state["clock_tick"] = now
        state["editor"]["cursor_line"] = 30 + (tick % 9)
        if a:
            if tick == 3: finish([target_row("FAILED", "Expected 4800; received 4560")])
            if tick == 4: say("The red console message means everything is broken, right?")
            if tick == 5: dirty(primary)
            if tick == 7: save(primary, "- withinGrace(hours < 24)\n+ withinGrace(hours <= 24)")
            if tick == 10: save("CHANGELOG.md", "+ Document the refund change")
            if tick == 11: start("R19")
            if tick == 14:
                finish([target_row("FAILED", "Expected 4800; received 4560"),
                        _result("fee rounding", "FAILED", "RangeError: fee", ["tests/grace.test.ts", secondary])])
            if tick == 16:
                dirty(primary)
                state["diagnostics"] = [{"file": primary, "message": "TS2304: Cannot find name withinGrace"}]
            if tick == 18: save(primary, "- return raw\n+ return withinGrace(raw)")
            if tick == 20: start("R20")
            if tick == 23: finish([], errors=[{"file": primary, "message": "TS2304: Cannot find name withinGrace"}])
            if tick == 25: dirty(primary)
            if tick == 27:
                save(primary, "+ import { withinGrace } from './clock'")
                state["diagnostics"] = []
            if tick == 29: say("The last run was green: it had zero failed tests.")
            if tick == 31: start("R21")
            if tick == 34:
                finish([target_row("PASSED"), _result("group booking", "SKIPPED"), _result("fee rounding", "SKIPPED")])
            if tick == 35: say("Only the target ran; that should be enough to commit.")
            if tick == 36: start("R22")
            if tick == 39:
                finish([target_row("PASSED"), _result("group booking", "SKIPPED"), _result("fee rounding", "PASSED")])
            if tick == 41: save("CHANGELOG.md", "- grace perod\n+ grace period")
            if tick == 43: save("project.config.ts", "- timezone: 'local'\n+ timezone: 'UTC'")
            if tick == 47: start("R23")
            if tick == 50:
                finish([target_row("PASSED"), _result("clock boundaries", "FAILED", "RangeError: zone",
                                                    ["tests/clock.test.ts", primary, external])])
            if tick == 51: say("I'll contact @runtime about R22.")
            if tick == 52: say("I'll contact @runtime about R23.", final=False)
            if tick == 53: say("I'll contact @runtime about R23.")
            if tick == 55: dirty(primary)
            if tick == 56: save(primary, "- clock.localNow()\n+ clock.utcNow()")
        else:
            if tick == 1: start("D7")
            if tick == 2: dap("paused")
            if tick == 3: dap("evaluate")
            if tick == 4: dirty(primary)
            if tick == 5: save(primary, "+ if existing: return existing")
            if tick == 6: say("It has hung. We should kill the process.")
            if tick == 8: dirty(primary)  # Control wins over an unsaved buffer.
            if tick == 9:
                dap("continued")
                state["editor"]["dirty_files"] = []
            if tick == 11: finish([target_row("FAILED", original)])
            if tick == 12: say("I saved the fix, so this old error cannot matter.")
            if tick == 13: start("D8")
            if tick == 14:
                state["terminal"].append({"time": now, "run": "D8", "text": target + " [started]"})
                evidence.append("D8 printed target start")
            if tick == 17:
                state["terminal"].append({"time": now, "run": None, "text": "file indexer: scan complete"})
                evidence.append("background indexer output, unrelated to D8")
            if tick == 19: say("Give it more time; I think it is still fine.")
            if tick == 21: dirty(primary)
            if tick == 22: finish([], interrupted=True)
            if tick == 24: save("tests/settlement_helpers.py", "+ fixture.close_transaction()")
            if tick == 28: start("D9")
            if tick == 31:
                finish([target_row("PASSED"), _result("EUR conversion", "FAILED", "KeyError: EUR",
                                                    ["tests/fx_test.py", primary, external, ".venv/sql/engine.py"])])
            if tick == 32: say("I'll contact @platform-core about D9.")
            if tick == 33: say("I'll contact @fx-platform about D9.", final=False)
            if tick == 34: say("Could you contact @fx-platform about D9?")
            if tick == 35: say("I'll contact @fx-platform about D9.")
            if tick == 37: save(secondary, "- rate = raw\n+ rate = checked")
            if tick == 41: start("D10")
            if tick == 44:
                finish([target_row("FAILED", "TimeoutError: pool exhausted", other),
                        _result("EUR conversion", "PASSED")])
            if tick == 45: say("I'll contact @platform-core about D9.")
            if tick == 46: say("I have contacted @platform-core about D10.")
            if tick == 48: save(other, "- release = False\n+ release = True")
            if tick == 52: start("D11")
            if tick == 55: finish([target_row("PASSED"), _result("EUR conversion", "PASSED")])
            if tick == 57:
                state["git"]["uncommitted"] = []
                evidence.append("git index and working tree clean after commit")
            if tick == 58:
                state["editor"]["dirty_files"] = ["notes.md"]
                evidence.append("untracked notes buffer edited")
        if not evidence:
            evidence = [f"clock advanced to {now}; cursor moved to line {state['editor']['cursor_line']}; no relevant event"]
        public = deepcopy(state)
        steps.append({"t": tick, "state": public, "gold": reference(public), "evidence": evidence})
    return {
        "episode_id": f"lite_debugging_{which}", "task_family": "live_debugging",
        "scenario_id": f"debugging_{which}", "title": state["session"]["title"], "tick_seconds": 2.0,
        "questions": _questions(files, teams),
        "decision_spec": {"route_question": "route", "always": ["process", "target_result"],
                          "branches": {"wait": [], "rerun": ["rerun_scope"], "inspect": ["inspect_file"],
                                       "control": ["control_action"], "delegate": ["owner"], "ready": []}},
        "steps": steps,
    }


def scenarios() -> list[dict]:
    """Return two independent 60-tick scripted sessions."""
    return [_scenario("a"), _scenario("b")]
