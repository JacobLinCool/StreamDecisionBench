"""Training variant C of the IDE debugging family: a Go stock-reservation service.

Shared-rules variant. The published debugging policy, question set, runner
record helpers and public-state reference are reused unchanged from the
evaluation family; only the session is new: a Go microservice that places
time-limited stock holds, its own and external teams, files, runs, tests,
terminal output and teammate talk.

Story: a hold-expiry test first fails with its original message, then with a
different message whose innermost in-project frame is the TTL helper. A
two-error compile failure must open the first reported file, not the one just
edited. A module run goes quiet; its own terminal line resets the silence once
while editor-tool output does not, so it stalls again and must be stopped even
with an unsaved relevant buffer. The interrupted run needs a target rerun; the
focused green run skips too many tests; a module run (whose test-file save
happened exactly at its start) exposes a retry failure owned, by the last
matching owners rule, by the storage team. Suggesting, questioning, wrong-run,
wrong-team and partial messages leave delegation active until the partial's
final transcript says the teammate has messaged the right team about the right
run. A dependency bump in go.mod (re-vendored; vendor/ matches no scope rule)
forces the full suite, which passes with only the allowed skip; the change is
ready until it is committed.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from streamdecisionbench.lite.tasks import debugging
from streamdecisionbench.lite.tasks.debugging import POLICY, _questions, _result, _run

# Shared family rules: the evaluation reference, never reimplemented here.
reference = debugging.reference

TARGET = "TestHoldExpiresAfterTTL"
RETRY = "TestReserveRetriesOnConflict"
METRIC = "TestReleaseEmitsMetric"
SOAK = "TestReserveUnderSoakLoad"
FLAGS = "TestServeFlagDefaults"
ORIGINAL = "reserved after TTL = 12, want 9"
DRIFTED = "reserved after TTL = 10, want 9"
CONFLICT = "kvclient: txn conflict on holds/sku-2093 (no retry policy)"
SOAK_SKIP = "skipping: requires the soak build tag"

HOLD = "internal/reserve/hold.go"
TTL = "internal/reserve/ttl.go"
HOLD_TEST = "internal/reserve/hold_test.go"
KV = "internal/storage/kvclient/txn.go"
GOMOD = "go.mod"
DOCS = "docs/reservations.md"
VENDOR_MODULES = "vendor/modules.txt"

OWN = "@reservations"
KV_TEAM = "@kv-storage"
FOUNDATION = "@svc-foundation"
TEAMMATES = ["Halvard", "Noor"]

GOROOT_TESTING = "/usr/local/go/src/testing/testing.go"
TTL_TRACE = [GOROOT_TESTING, HOLD_TEST, HOLD, TTL, "/usr/local/go/src/time/time.go"]
KV_TRACE = [GOROOT_TESTING, HOLD_TEST, HOLD, KV, "vendor/go.etcd.io/etcd/client/v3/txn.go",
            "/usr/local/go/src/context/context.go"]

HOLD_TYPE = "cannot use ttl (variable of type int) as time.Duration value in argument to h.extend"
TTL_UNUSED = "declared and not used: grace"
HOLD_ERROR = HOLD + ":88:14: " + HOLD_TYPE
TTL_ERROR = TTL + ":41:2: " + TTL_UNUSED


# Authoring witnesses for ticks whose decision changes only because a timer crossed a boundary.
NOTES = {
    1: "hold.go write (-1) is now two ticks old; ttl.go write (-8) predates G40's start (-6)",
    8: "ttl.go write (7) is one tick old: save grace still applies",
    9: "ttl.go write is two ticks old and is the only write after G41's start: module scope",
    17: "hold.go write (16) is one tick old although the ttl.go write (15) is two ticks old",
    18: "writes after G42's start: ttl.go (module) and hold.go (target); the widest is module",
    22: "G43 silent for 1 tick since its own line at 21",
    25: "G43 silent for 4 ticks since 21; the gopls line at 23 is not G43 output",
    27: "G43 silent for 1 tick since its own line at 26",
    29: "G43 silent for 3 ticks; the lint watcher line at 28 is not G43 output",
    30: "G43 silent for 4 ticks since 26",
    31: "G43 silent for 5 ticks",
    32: "G43 silent for 6 ticks; stop outranks the unsaved hold.go buffer",
    52: ("hold.go write (50) is two ticks old; relevant writes after G45's start: go.mod (full), "
         "hold.go (target); vendor/modules.txt matches no scope rule"),
}


def _soak() -> dict:
    return _result(SOAK, "SKIPPED", SOAK_SKIP)


def _scenario() -> dict[str, Any]:
    state: dict[str, Any] = {
        "session": {
            "title": "Stock hold expiry hunt",
            "policy": POLICY,
            "target_test": TARGET, "original_failure": ORIGINAL, "own_team": OWN,
            "teammates": list(TEAMMATES), "allowed_skips": 1,
            "project_roots": ["internal/", "cmd/"],
            "scope_rules": [["internal/*", "module"], [HOLD, "target"], ["*_test.go", "module"],
                            ["cmd/*", "module"], ["internal/storage/*", "full"], [GOMOD, "full"]],
            "owners": [["*", OWN], ["internal/*", FOUNDATION], ["internal/reserve/*", OWN],
                       ["*/kvclient/*", KV_TEAM]],
        },
        "clock_tick": 0,
        "editor": {"active_file": HOLD, "cursor_line": 72, "dirty_files": []},
        "saves": [
            {"time": -8, "file": TTL,
             "diff": "- return h.created.Add(h.ttl)\n+ return h.created.Add(h.ttl).Truncate(time.Second)"},
            {"time": -1, "file": HOLD,
             "diff": "- if now.After(h.expiresAt) {\n+ if !now.Before(h.expiresAt) {"},
        ],
        "runs": [_run("G40", -6, -3, [_result(TARGET, "FAILED", ORIGINAL, TTL_TRACE),
                                      _result(RETRY, "PASSED"), _result(METRIC, "PASSED"), _soak()])],
        "terminal": [],
        "debugger": {"status": "inactive", "events": []},
        "call": [],
        "git": {"uncommitted": [TTL, HOLD]},
        "diagnostics": [],
    }
    state["terminal"] = [
        {"time": -6, "run": "G40", "text": "$ test-runner; collecting tests"},
        {"time": -3, "run": "G40", "text": state["runs"][0]["summary"]},
    ]
    now = 0
    evidence: list[str] = []

    def say(speaker: str, text: str, *, final: bool = True) -> None:
        state["call"].append({"time": now, "speaker": speaker, "text": text, "final": final})
        evidence.append(f"call {speaker}: {text}" + ("" if final else " [partial]"))

    def dirty(path: str) -> None:
        state["editor"]["dirty_files"] = [path]
        state["editor"]["active_file"] = path
        evidence.append("unsaved buffer: " + path)

    def revert() -> None:
        evidence.append("discarded unsaved edits in " + ", ".join(state["editor"]["dirty_files"]))
        state["editor"]["dirty_files"] = []

    def save(path: str, diff: str) -> None:
        state["saves"].append({"time": now, "file": path, "diff": diff})
        state["editor"]["dirty_files"] = [p for p in state["editor"]["dirty_files"] if p != path]
        state["editor"]["active_file"] = path
        if path not in state["git"]["uncommitted"]:
            state["git"]["uncommitted"].append(path)
        evidence.append(f"saved {path} at {now}")

    def out(text: str, run: str | None) -> None:
        state["terminal"].append({"time": now, "run": run, "text": text})
        evidence.append(f"terminal ({run or 'no run'}): {text}")

    def start(run_id: str) -> None:
        state["runs"].append(_run(run_id, now, None, []))
        state["terminal"].append({"time": now, "run": run_id, "text": "$ test-runner; collecting tests"})
        state["debugger"]["status"] = "running"
        evidence.append("run started: " + run_id)

    def finish(results: list[dict], *, errors: list[dict] | None = None, interrupted: bool = False) -> None:
        current = next(run for run in state["runs"] if run["finished"] is None)
        current.update(_run(current["id"], current["started"], now, results,
                            errors=errors, interrupted=interrupted))
        state["terminal"].append({"time": now, "run": current["id"], "text": current["summary"]})
        state["debugger"]["status"] = "inactive"
        evidence.append("run finished: " + current["id"] + "; " + current["summary"])

    def skipped_except_target(target: dict) -> list[dict]:
        return [target, _result(RETRY, "SKIPPED"), _result(METRIC, "SKIPPED"), _soak()]

    steps = []
    for tick in range(60):
        now = tick
        evidence = []
        state["clock_tick"] = now
        state["editor"]["cursor_line"] = 72 + (tick * 5) % 23
        if tick == 0:
            evidence.append("hold.go saved at -1, after G40 (started -6) failed with the original message")
        if tick == 2:
            start("G41")
            say("Esme", "Is the hold fix going out with today's deploy?")
        if tick == 3:
            out("=== RUN   " + TARGET, "G41")
        if tick == 4:
            finish(skipped_except_target(_result(TARGET, "FAILED", DRIFTED, TTL_TRACE)))
        if tick == 5:
            say("Noor", "That trace is noise; the real bug is in hold.go.")
        if tick == 6:
            dirty(TTL)
        if tick == 7:
            save(TTL, "- func holdTTL(cfg Config) time.Duration {\n+ func holdTTL(cfg Config) int {\n"
                      "+ grace := cfg.TTLSeconds / 10")
            state["diagnostics"] = [{"file": TTL, "message": TTL_UNUSED}, {"file": HOLD, "message": HOLD_TYPE}]
            evidence.append("language server flags both files after the save, the active ttl.go first")
        if tick == 10:
            start("G42")
        if tick == 11:
            out("# warehouse.dev/stockhold/internal/reserve", "G42")
        if tick == 12:
            finish([], errors=[{"file": HOLD, "message": HOLD_ERROR}, {"file": TTL, "message": TTL_ERROR}])
            evidence.append("the compiler reports hold.go first; editor diagnostics still list ttl.go first")
        if tick == 13:
            say("Halvard", "Open ttl.go first, that's the file you just changed.")
        if tick == 14:
            dirty(TTL)
        if tick == 15:
            save(TTL, "- grace := cfg.TTLSeconds / 10")
            state["diagnostics"] = [row for row in state["diagnostics"] if row["file"] != TTL]
            dirty(HOLD)
        if tick == 16:
            save(HOLD, "- h.extend(ttl)\n+ h.extend(time.Duration(ttl) * time.Second)")
            state["diagnostics"] = []
            evidence.append("diagnostics cleared")
        if tick == 19:
            start("G43")
        if tick == 20:
            out("=== RUN   " + TARGET, "G43")
        if tick == 21:
            out("--- PASS: " + TARGET + " (0.04s)", "G43")
        if tick == 23:
            out("gopls: workspace packages reloaded", None)
        if tick == 24:
            say("Noor", "gopls just reloaded, so the runner is still alive.")
        if tick == 26:
            out("=== RUN   " + RETRY, "G43")
        if tick == 28:
            out("lint watcher: 0 findings in internal/reserve", None)
        if tick == 30:
            dirty(HOLD)
        if tick == 33:
            say("Halvard", "Don't kill it, it was almost done.")
        if tick == 34:
            finish([], interrupted=True)
        if tick == 35:
            revert()
        if tick == 36:
            start("G44")
        if tick == 37:
            out("=== RUN   " + TARGET, "G44")
        if tick == 38:
            finish(skipped_except_target(_result(TARGET, "PASSED")))
        if tick == 39:
            say("Noor", "The soak test always skips, so the skip count is fine.")
        if tick == 40:
            # Run-on-save: the write and the module run start share tick 40.
            save(HOLD_TEST, "- t.Run(\"conflict\", testConflict)\n+ t.Run(\"conflict_retry\", testConflict)")
            start("G45")
        if tick == 41:
            out("=== RUN   " + RETRY, "G45")
        if tick == 42:
            finish([_result(TARGET, "PASSED"), _result(RETRY, "FAILED", CONFLICT, KV_TRACE),
                    _result(METRIC, "PASSED"), _soak()])
        if tick == 43:
            say("Noor", f"Maybe someone should contact {KV_TEAM} about G45.")
        if tick == 44:
            say("Halvard", f"Should I message {KV_TEAM} about G45?")
        if tick == 45:
            say("Noor", f"I'll contact {KV_TEAM} about G44.")
        if tick == 46:
            say("Noor", f"I'll contact {FOUNDATION} about G45.")
        if tick == 47:
            say("Halvard", f"I have messaged {KV_TEAM} about G45.", final=False)
        if tick == 48:
            say("Halvard", f"I have messaged {KV_TEAM} about G45.")
        if tick == 49:
            save(GOMOD, "- require go.etcd.io/etcd/client/v3 v3.5.9\n+ require go.etcd.io/etcd/client/v3 v3.5.12")
            out("$ go mod vendor", None)
            save(VENDOR_MODULES, "- # go.etcd.io/etcd/client/v3 v3.5.9\n+ # go.etcd.io/etcd/client/v3 v3.5.12")
            dirty(HOLD)
        if tick == 50:
            save(HOLD, "- res, err := kv.Txn(ctx).Commit()\n+ res, err := kv.TxnWithRetry(ctx, 3)")
        if tick == 51:
            say("Halvard", "The newer client is pinned now; that should settle the retries.")
        if tick == 53:
            start("G46")
        if tick == 54:
            out("ok   warehouse.dev/stockhold/internal/reserve 1.84s", "G46")
        if tick == 55:
            finish([_result(TARGET, "PASSED"), _result(RETRY, "PASSED"), _result(METRIC, "PASSED"),
                    _soak(), _result(FLAGS, "PASSED")])
        if tick == 56:
            dirty(DOCS)
        if tick == 57:
            save(DOCS, "+ Holds now expire at exactly their TTL.")
        if tick == 58:
            state["git"]["uncommitted"] = []
            evidence.append("commit created; git working tree clean")
        if tick == 59:
            say("Noor", "Nice, the sweeper finally lets go of expired holds.")
        if tick in NOTES:
            evidence.append(NOTES[tick])
        if not evidence:
            evidence = [f"clock advanced to {now}; cursor at line {state['editor']['cursor_line']}; no relevant event"]
        public = deepcopy(state)
        steps.append({"t": tick, "state": public, "gold": reference(public), "evidence": evidence})
    return {
        "episode_id": "train_debugging_c", "task_family": "live_debugging",
        "scenario_id": "debugging_c", "title": state["session"]["title"], "tick_seconds": 2.0,
        "questions": _questions([TTL, HOLD], [KV_TEAM, FOUNDATION]),
        "decision_spec": {"route_question": "route", "always": ["process", "target_result"],
                          "branches": {"wait": [], "rerun": ["rerun_scope"], "inspect": ["inspect_file"],
                                       "control": ["control_action"], "delegate": ["owner"], "ready": []}},
        "steps": steps,
    }


def scenarios() -> list[dict]:
    """Return the single 60-tick training session of this variant."""
    return [_scenario()]
