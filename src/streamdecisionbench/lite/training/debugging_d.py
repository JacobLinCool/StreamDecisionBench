"""Training variant D of the IDE debugging family: a Rust buoy-telemetry decoder crate.

Shared-rules variant: the family's published policy, question set, run/result
record helpers and public-state reference are reused verbatim from
``streamdecisionbench.lite.tasks.debugging``; only the session (project, people,
files, runs, messages and timeline) is new.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from streamdecisionbench.lite.tasks import debugging
from streamdecisionbench.lite.tasks.debugging import POLICY, _questions, _result, _run

reference = debugging.reference

TARGET = "roundtrip::gust_speed_survives_reframing"
ORIGINAL = "gust_knots: expected 32.4, decoded 12.6"
ROUNDING = "gust_knots: expected 32.4, decoded 32.0"
OWN = "@buoy-ingest"
SERIAL = "@serial-io"
GEODESY = "@geodesy"
PLATFORM = "@rust-platform"

GUST = "crates/decoder/src/fields/gust.rs"
READER = "crates/decoder/src/reader.rs"
FRAMING = "crates/decoder/src/framing.rs"
CHECKSUM = "crates/decoder/src/checksum.rs"
UART = "crates/decoder/src/sys/uart_clock.rs"
CRATE_MANIFEST = "crates/decoder/Cargo.toml"
NOTES_DOC = "docs/gust-encoding.md"

JITTER = "framing::resyncs_after_uart_jitter"
NIBBLE = "checksum::rejects_bad_nibble"
STATION = "station::keeps_leading_zero_ids"
DATUM = "geo::datum_shift_near_antimeridian"

TRACES = {
    JITTER: ["crates/decoder/tests/framing.rs", FRAMING, UART,
             "~/.cargo/registry/src/index.crates.io-6f17d22bba15001f/serialport-4.5.1/src/posix/tty.rs"],
    TARGET: ["crates/decoder/tests/roundtrip.rs", READER, GUST, "vendor/nmea-lite/src/sentence.rs",
             "~/.rustup/toolchains/stable/lib/rustlib/src/rust/library/core/src/panicking.rs"],
    NIBBLE: ["crates/decoder/tests/checksum.rs", FRAMING, CHECKSUM, "vendor/nmea-lite/src/hex.rs"],
}
MESSAGES = {
    JITTER: "resync landed 7 bytes late after UART jitter",
    NIBBLE: "accepted frame with checksum *4F, computed *4E",
}


def _row(test: str, outcome: str, message: str | None = None) -> dict:
    """A runner result row; failed rows carry their fixed message and outermost-first trace."""
    if outcome != "FAILED":
        return _result(test, outcome)
    return _result(test, outcome, message or MESSAGES[test], list(TRACES[test]))


def _module(jitter: str, target: str, nibble: str, station: str, *, message: str = ROUNDING) -> list[dict]:
    """Decoder-crate results in the runner's declaration order."""
    return [_row(JITTER, jitter), _row(TARGET, target, message), _row(NIBBLE, nibble), _row(STATION, station)]


def _build() -> dict:
    history = _module("FAILED", "FAILED", "PASSED", "PASSED", message=ORIGINAL)
    state: dict[str, Any] = {
        "session": {
            "title": "Buoy telemetry decoder session",
            "policy": POLICY,
            "target_test": TARGET, "original_failure": ORIGINAL, "own_team": OWN,
            "teammates": ["Ilse", "Ruairi"], "allowed_skips": 0,
            "project_roots": ["crates/", "xtask/"],
            "scope_rules": [["crates/*", "module"], [GUST, "target"], ["Cargo.toml", "full"],
                            ["Cargo.lock", "full"], ["crates/*/Cargo.toml", "full"]],
            "owners": [["*", OWN], ["crates/*", PLATFORM], ["crates/decoder/*", OWN],
                       ["crates/geo/*", GEODESY], ["crates/*/src/sys/*", SERIAL]],
        },
        "clock_tick": 0,
        "editor": {"active_file": READER, "cursor_line": 52, "dirty_files": []},
        "saves": [{"time": -4, "file": READER,
                   "diff": "- let raw = u16::from_le_bytes(pair);\n+ let raw = u16::from_be_bytes(pair);"}],
        "runs": [_run("W39", -16, -12, deepcopy(history)), _run("W40", -10, -6, deepcopy(history)),
                 _run("W41", -2, None, [])],
        "terminal": [{"time": -12, "run": "W39", "text": "2 passed, 2 failed, 0 skipped"},
                     {"time": -10, "run": "W40", "text": "$ test-runner; collecting tests"},
                     {"time": -6, "run": "W40", "text": "2 passed, 2 failed, 0 skipped"},
                     {"time": -2, "run": "W41", "text": "$ test-runner; collecting tests"},
                     {"time": -1, "run": "W41", "text": "running 4 tests; debugger attached"}],
        "debugger": {"status": "running", "events": []},
        "call": [],
        "git": {"uncommitted": [READER]},
        "diagnostics": [{"file": "crates/decoder/src/station.rs",
                         "message": "warning: unused import: `core::fmt::Write`"}],
    }
    now = 0
    evidence: list[str] = []

    def say(speaker: str, text: str, *, final: bool = True) -> None:
        state["call"].append({"time": now, "speaker": speaker, "text": text, "final": final})
        evidence.append(f"call {speaker}: {text}" + ("" if final else " [partial]"))

    def dirty(path: str) -> None:
        state["editor"]["dirty_files"] = [path]
        state["editor"]["active_file"] = path
        evidence.append("buffer edited, unsaved: " + path)

    def save(path: str, diff: str, *, pulled: bool = False) -> None:
        state["saves"].append({"time": now, "file": path, "diff": diff})
        state["editor"]["dirty_files"] = [p for p in state["editor"]["dirty_files"] if p != path]
        if not pulled and path not in state["git"]["uncommitted"]:
            state["git"]["uncommitted"].append(path)
        evidence.append(("pulled " if pulled else "saved ") + f"{path} at {now}")

    def line(run_id: str | None, text: str) -> None:
        state["terminal"].append({"time": now, "run": run_id, "text": text})
        evidence.append(f"terminal [{run_id or 'no run'}]: {text}")

    def start(run_id: str, scope: str) -> None:
        state["runs"].append(_run(run_id, now, None, []))
        state["terminal"].append({"time": now, "run": run_id, "text": "$ test-runner; collecting tests"})
        state["debugger"]["status"] = "running"
        evidence.append(f"run started: {run_id} ({scope} scope)")

    def finish(results: list[dict], *, interrupted: bool = False) -> None:
        current = next(run for run in state["runs"] if run["finished"] is None)
        current.update(_run(current["id"], current["started"], now, results, interrupted=interrupted))
        state["terminal"].append({"time": now, "run": current["id"], "text": current["summary"]})
        state["debugger"]["status"] = "inactive"
        evidence.append(f"run finished: {current['id']}; {current['summary']}")

    def dap(kind: str) -> None:
        current = next(run for run in state["runs"] if run["finished"] is None)
        state["debugger"]["events"].append({"time": now, "run": current["id"], "kind": kind, "file": READER})
        if kind in ("paused", "continued"):
            state["debugger"]["status"] = "paused" if kind == "paused" else "running"
        evidence.append(f"debugger {kind} in {current['id']}")

    steps = []
    for tick in range(60):
        now = tick
        evidence = []
        state["clock_tick"] = now
        state["editor"]["cursor_line"] = 52 + (tick * 7) % 23
        if tick == 1: dap("paused")  # breakpoint in the byte reader
        if tick == 2: dap("evaluate")
        if tick == 3: say("Ilse", "It has been sitting on that line for a while. Should we kill it?")
        if tick == 4: dap("step")
        if tick == 5: save(NOTES_DOC, "+ Gust bytes arrive big-endian from the mast unit.")
        if tick == 6: say("Ruairi", "Is that the reader breakpoint, or is the decoder hung?")
        # t8: four ticks after the step at t4 -> continue, despite the save and the message.
        if tick == 10: dap("continued")
        if tick == 12: line("W41", "test checksum::rejects_bad_nibble ... FAILED")
        if tick == 13: finish(_module("FAILED", "FAILED", "FAILED", "PASSED"))
        if tick == 14: say("Ruairi", "The jitter test is still red. Shouldn't we start with that one?")
        if tick == 15: dirty(CHECKSUM)
        if tick == 16:
            save(CHECKSUM, "- if nibble > 0xF {\n+ if !nibble.is_ascii_hexdigit() {")
        if tick == 19:
            start("W42", "module")
            save(CHECKSUM, "- fold(0, |a, b| a ^ b)\n+ fold(0u8, |acc, byte| acc ^ byte)")  # same tick as start
        if tick == 20: line("W42", "running 4 tests")
        if tick == 21: finish(_module("FAILED", "FAILED", "PASSED", "PASSED"))
        if tick == 22: say("Ilse", "The gust value is within half a knot now, so that is basically a pass.")
        if tick == 23:
            dirty(GUST)
            state["diagnostics"].append({"file": GUST, "message": "warning: unused variable: `tenths`"})
            evidence.append("rust-analyzer warning in the unsaved gust buffer")
        if tick == 24:
            save(GUST, "+ #[cfg(feature = \"gust-tenths\")]\n- knots.round()\n+ (knots * 10.0).round() / 10.0")
            state["diagnostics"] = [row for row in state["diagnostics"] if row["file"] != GUST]
        if tick == 27: start("W43", "target")
        if tick == 28: line("W43", "running 1 test")
        if tick == 31: line(None, "rust-analyzer: cache priming finished")  # not W43 output
        if tick == 34: finish([], interrupted=True)
        if tick == 35: say("Ruairi", "Nothing failed in that run, so the fix works.")
        if tick == 36: start("W44", "target")
        if tick == 37: line("W44", "running 1 test")
        if tick == 38: finish(_module("SKIPPED", "PASSED", "SKIPPED", "SKIPPED"))
        if tick == 39: say("Ilse", "Target is green. Let's commit it and move on.")
        if tick == 40: start("W45", "module")
        if tick == 41: line("W45", "test roundtrip::gust_speed_survives_reframing ... ignored")
        if tick == 42: finish(_module("FAILED", "SKIPPED", "PASSED", "PASSED"))
        if tick == 43:
            state["editor"]["active_file"] = CRATE_MANIFEST
            save(CRATE_MANIFEST, "- default = []\n+ default = [\"gust-tenths\"]")
        if tick == 46: start("W46", "full")
        if tick == 47: line("W46", "running 5 tests")
        if tick == 48: finish(_module("FAILED", "PASSED", "PASSED", "PASSED") + [_row(DATUM, "PASSED")])
        if tick == 49: say("Ruairi", "I'll contact @serial-io about W45.")
        if tick == 50: say("Ruairi", "I have contacted @serial-io about W46.", final=False)
        if tick == 51: say("Ruairi", "I have contacted @serial-io about W46.")
        if tick == 52:
            save(UART, "- const RESYNC_WINDOW: usize = 4;\n+ const RESYNC_WINDOW: usize = 12;", pulled=True)
            save("Cargo.lock", "- serialport 4.5.0\n+ serialport 4.5.1", pulled=True)
        if tick == 55: start("W47", "full")
        if tick == 56: finish(_module("PASSED", "PASSED", "PASSED", "PASSED") + [_row(DATUM, "PASSED")])
        if tick == 57: save(NOTES_DOC, "+ Tenths stay behind the gust-tenths feature flag.")
        if tick == 58:
            state["git"]["uncommitted"] = []
            evidence.append("committed; working tree clean")
        if tick == 59:
            state["editor"]["dirty_files"] = ["notes.md"]
            evidence.append("untracked scratch notes buffer edited")
        if not evidence:
            evidence = [f"clock advanced to {now}; cursor at line {state['editor']['cursor_line']}; no new event"]
        public = deepcopy(state)
        steps.append({"t": tick, "state": public, "gold": reference(public), "evidence": evidence})
    return {
        "episode_id": "train_debugging_d", "task_family": "live_debugging",
        "scenario_id": "debugging_d", "title": state["session"]["title"], "tick_seconds": 2.0,
        "questions": _questions([CHECKSUM, GUST], [SERIAL, GEODESY, PLATFORM]),
        "decision_spec": {"route_question": "route", "always": ["process", "target_result"],
                          "branches": {"wait": [], "rerun": ["rerun_scope"], "inspect": ["inspect_file"],
                                       "control": ["control_action"], "delegate": ["owner"], "ready": []}},
        "steps": steps,
    }


def scenarios() -> list[dict]:
    """One 60-tick scripted session of the training split."""
    return [_build()]
