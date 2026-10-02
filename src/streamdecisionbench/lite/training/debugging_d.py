"""Training variant D of the IDE debugging family: a Rust buoy-telemetry decoder crate.

Shared-rules variant: the family's published policy, question set, run/result
record helpers and public-state reference are reused verbatim from
``streamdecisionbench.lite.tasks.debugging``; only the session (project, people,
files, runs, messages and timeline) is new.

Story: a byte-order change to the decoder's ``read_u16`` helper is still
building when the session opens; the build goes quiet long enough to read
stalled until its own compiler output resumes, then fails with two call-site
errors. The first compiler file (heading.rs) must be opened although
rust-analyzer and a teammate point at gust.rs. Fixing both call sites (a module
and a target write) asks for the wider module rerun, which now fails with a
different gust value whose innermost project frame is gust.rs; a teammate's
"revert the reader" advice does not change that. A debugger run pauses in
gust.rs and is stepped every three ticks, so the continue card appears only
four ticks after the last step, overriding the scale fix saved one tick earlier
and a request to stay paused. After continuing, the run prints one harness line
and then goes silent; editor-tool output does not reset its silence, so it
stalls and reaches the stop card before it is interrupted. The interrupted run
needs a target rerun; the green target-only run skips too many tests, so the
module is rerun (with a write exactly at its start, already loaded). That run
exposes a newly failing UART jitter test whose innermost project frame belongs
to the serial team by the last matching owners rule; a negation, a question
and a wrong-team commitment leave delegation active until a teammate says they
have messaged the right team about that run. The serial team's fix arrives by
``git pull`` together with a lock-file bump, which forces the full suite; it
passes, so the change is ready; an unsaved edit to gust.rs turns the card back
to wait until it is reverted, which restores ready.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from streamdecisionbench.lite.tasks import debugging
from streamdecisionbench.lite.tasks.debugging import POLICY, _questions, _result, _run

# Shared family rules: the evaluation reference, never reimplemented here.
reference = debugging.reference

TARGET = "roundtrip::gust_speed_survives_reframing"
ORIGINAL = "gust_knots: expected 32.4, decoded 174.1"
SCALED = "gust_knots: expected 32.4, decoded 3.2"
OWN = "@buoy-ingest"
SERIAL = "@serial-io"
GEODESY = "@geodesy"
PLATFORM = "@rust-platform"
TEAMMATES = ["Ilse", "Ruairi"]

GUST = "crates/decoder/src/fields/gust.rs"
HEADING = "crates/decoder/src/fields/heading.rs"
READER = "crates/decoder/src/reader.rs"
FRAMING = "crates/decoder/src/framing.rs"
UART = "crates/decoder/src/sys/uart_clock.rs"
LOCKFILE = "Cargo.lock"

JITTER = "framing::resyncs_after_uart_jitter"
NIBBLE = "checksum::rejects_bad_nibble"
STATION = "station::keeps_leading_zero_ids"
DATUM = "geo::datum_shift_near_antimeridian"

ROUNDTRIP_TEST = "crates/decoder/tests/roundtrip.rs"
NMEA = "vendor/nmea-lite/src/sentence.rs"
PANICKING = "~/.rustup/toolchains/stable/lib/rustlib/src/rust/library/core/src/panicking.rs"
SERIALPORT = "~/.cargo/registry/src/index.crates.io-6f17d22bba15001f/serialport-4.5.1/src/posix/tty.rs"
TRACES = {
    ORIGINAL: [ROUNDTRIP_TEST, FRAMING, READER, NMEA, PANICKING],
    SCALED: [ROUNDTRIP_TEST, FRAMING, READER, GUST, NMEA, PANICKING],
    JITTER: ["crates/decoder/tests/framing.rs", FRAMING, UART, SERIALPORT],
}
JITTER_MESSAGE = "resync landed 7 bytes late after UART jitter"
ARITY = "error[E0061]: this function takes 2 arguments but 1 argument was supplied"
COMPILE_ERRORS = [{"file": HEADING, "message": ARITY + " --> " + HEADING + ":31:19"},
                  {"file": GUST, "message": ARITY + " --> " + GUST + ":47:15"}]

# Authoring witnesses for ticks whose decision changes only because a timer or an ordering rule decides.
NOTES = {
    1: "W41 silent for 4 ticks since its own line at -3: stalled, not yet stoppable",
    9: "gust.rs write (8) is one tick old: save grace still applies",
    10: "writes after W41's start (-4): heading.rs (module) and gust.rs (target); the widest is module",
    14: "W41 compiled nothing, so the target is newly failing; innermost project frame is gust.rs",
    27: "four ticks since the step at 23; the gust.rs write at 26 is one tick old but control outranks it",
    34: "W43 silent for 4 ticks since its own line at 30; the rust-analyzer line at 32 is not W43 output",
    36: "W43 silent for 6 ticks: stop",
    46: "jitter test newly failing (skipped in W44); innermost project frame uart_clock.rs; last owners match @serial-io",
    50: "final first-person message names @serial-io and W45",
    53: "pulled writes after W45's start: Cargo.lock (full) and uart_clock.rs (module); the widest is full",
}


def _target(outcome: str, message: str = "") -> dict:
    """The pinned roundtrip test; failed rows carry the trace recorded for their message."""
    if outcome != "FAILED":
        return _result(TARGET, outcome)
    return _result(TARGET, outcome, message, list(TRACES[message]))


def _jitter(outcome: str) -> dict:
    if outcome != "FAILED":
        return _result(JITTER, outcome)
    return _result(JITTER, outcome, JITTER_MESSAGE, list(TRACES[JITTER]))


def _module(jitter: str, target: dict, nibble: str, station: str) -> list[dict]:
    """Decoder-crate results in the runner's declaration order."""
    return [_jitter(jitter), target, _result(NIBBLE, nibble), _result(STATION, station)]


def _build() -> dict:
    state: dict[str, Any] = {
        "session": {
            "title": "Buoy telemetry decoder session",
            "policy": POLICY,
            "target_test": TARGET, "original_failure": ORIGINAL, "own_team": OWN,
            "teammates": list(TEAMMATES), "allowed_skips": 0,
            "project_roots": ["crates/", "xtask/"],
            "scope_rules": [["crates/*", "module"], [GUST, "target"], ["Cargo.toml", "full"],
                            [LOCKFILE, "full"], ["crates/*/Cargo.toml", "full"]],
            "owners": [["*", OWN], ["crates/*", PLATFORM], ["crates/decoder/*", OWN],
                       ["crates/geo/*", GEODESY], ["crates/*/src/sys/*", SERIAL]],
        },
        "clock_tick": 0,
        "editor": {"active_file": READER, "cursor_line": 18, "dirty_files": []},
        "saves": [{"time": -6, "file": READER,
                   "diff": "- pub fn read_u16(pair: [u8; 2]) -> u16 {\n-     u16::from_le_bytes(pair)\n"
                           "+ pub fn read_u16(pair: [u8; 2], order: ByteOrder) -> u16 {\n+     order.decode(pair)"}],
        "runs": [_run("W40", -14, -10, _module("PASSED", _target("FAILED", ORIGINAL), "PASSED", "PASSED")),
                 _run("W41", -4, None, [])],
        "terminal": [],
        "debugger": {"status": "running", "events": []},
        "call": [],
        "git": {"uncommitted": [READER]},
        "diagnostics": [{"file": "crates/decoder/src/station.rs",
                         "message": "warning: unused import: `core::fmt::Write`"}],
    }
    state["terminal"] = [
        {"time": -14, "run": "W40", "text": "$ test-runner; collecting tests"},
        {"time": -10, "run": "W40", "text": state["runs"][0]["summary"]},
        {"time": -4, "run": "W41", "text": "$ test-runner; collecting tests"},
        {"time": -3, "run": "W41", "text": "Compiling decoder v0.4.0 (crates/decoder)"},
    ]
    now = 0
    evidence: list[str] = []

    def say(speaker: str, text: str, *, final: bool = True) -> None:
        state["call"].append({"time": now, "speaker": speaker, "text": text, "final": final})
        evidence.append(f"call {speaker}: {text}" + ("" if final else " [partial]"))

    def dirty(path: str) -> None:
        state["editor"]["dirty_files"] = [path]
        state["editor"]["active_file"] = path
        evidence.append("buffer edited, unsaved: " + path)

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

    def pull(changes: list[tuple[str, str]]) -> None:
        """A fast-forward pull: files change on disk but arrive committed, so git stays as it was."""
        for path, diff in changes:
            state["saves"].append({"time": now, "file": path, "diff": diff})
        text = "$ git pull --ff-only; updated " + ", ".join(path for path, _ in changes)
        state["terminal"].append({"time": now, "run": None, "text": text})
        evidence.append(f"terminal [no run]: {text} (already committed upstream)")

    def line(run_id: str | None, text: str) -> None:
        state["terminal"].append({"time": now, "run": run_id, "text": text})
        evidence.append(f"terminal [{run_id or 'no run'}]: {text}")

    def start(run_id: str, scope: str) -> None:
        state["runs"].append(_run(run_id, now, None, []))
        state["terminal"].append({"time": now, "run": run_id, "text": "$ test-runner; collecting tests"})
        state["debugger"]["status"] = "running"
        evidence.append(f"run started: {run_id} ({scope} scope)")

    def finish(results: list[dict], *, errors: list[dict] | None = None, interrupted: bool = False) -> None:
        current = next(run for run in state["runs"] if run["finished"] is None)
        current.update(_run(current["id"], current["started"], now, results,
                            errors=errors, interrupted=interrupted))
        state["terminal"].append({"time": now, "run": current["id"], "text": current["summary"]})
        state["debugger"]["status"] = "inactive"
        evidence.append(f"run finished: {current['id']}; {current['summary']}")

    def dap(kind: str) -> None:
        current = next(run for run in state["runs"] if run["finished"] is None)
        state["debugger"]["events"].append({"time": now, "run": current["id"], "kind": kind, "file": GUST})
        if kind in ("paused", "continued"):
            state["debugger"]["status"] = "paused" if kind == "paused" else "running"
        evidence.append(f"debugger {kind} in {current['id']} at {GUST}")

    steps = []
    for tick in range(60):
        now = tick
        evidence = []
        state["clock_tick"] = now
        state["editor"]["cursor_line"] = 18 + (tick * 7) % 41
        # Act 1: the signature change is still compiling, then fails at two call sites.
        if tick == 2: line("W41", ARITY)
        if tick == 3: line("W41", "error: could not compile `decoder` (lib) due to 2 previous errors")
        if tick == 4:
            finish([], errors=deepcopy(COMPILE_ERRORS))
            state["diagnostics"].append({"file": GUST, "message": "expected 2 arguments, found 1"})
            evidence.append("rust-analyzer shows the gust.rs error only")
        if tick == 5: say("Ilse", "rust-analyzer only shows an error in gust.rs, so open that one first.")
        if tick == 6: dirty(HEADING)
        if tick == 7:
            save(HEADING, "- let deg = read_u16(pair);\n+ let deg = read_u16(pair, ByteOrder::Big);")
            dirty(GUST)
        if tick == 8:
            save(GUST, "- let raw = read_u16(pair);\n+ let raw = read_u16(pair, ByteOrder::Big);")
            state["diagnostics"] = [row for row in state["diagnostics"] if row["file"] != GUST]
        # Act 2: it builds; the gust value is now wrong in a different way.
        if tick == 11: start("W42", "module")
        if tick == 12: line("W42", "running 4 tests")
        if tick == 14: finish(_module("PASSED", _target("FAILED", SCALED), "PASSED", "PASSED"))
        if tick == 15: say("Ruairi", "A new number means the reader change broke it. Revert reader.rs.")
        # Act 3: a debugger run in gust.rs, stepped every three ticks.
        if tick == 16:
            start("W43", "target")
            evidence.append("debugger attached to W43; breakpoint set in " + GUST)
        if tick == 17: dap("paused")  # breakpoint on the gust scale factor
        if tick == 18: dap("evaluate")
        if tick == 20: dap("step")
        if tick == 23: dap("step")
        if tick == 25: dirty(GUST)
        if tick == 26: save(GUST, "- let knots = f32::from(raw) / 100.0;\n+ let knots = f32::from(raw) / 10.0;")
        if tick == 27: say("Ilse", "Leave it paused, I'm still reading the scale factor.")
        if tick == 29: dap("continued")
        if tick == 30: line("W43", f"{TARGET}: waiting for a loopback frame")
        if tick == 32: line(None, "rust-analyzer: flycheck finished, 0 errors")
        if tick == 35: say("Ruairi", "Something printed a moment ago, so it is still moving.")
        if tick == 38: finish([], interrupted=True)
        # Act 4: target, then module, then the serial team's failure.
        if tick == 39: start("W44", "target")
        if tick == 40: line("W44", "running 1 test")
        if tick == 41: finish(_module("SKIPPED", _target("PASSED"), "SKIPPED", "SKIPPED"))
        if tick == 42: say("Ruairi", "Skipped just means those tests were green last time.")
        if tick == 43:
            # The write and the module run start share tick 43, so W45 already loads it.
            save(READER, "- // FIXME: confirm the mast unit's byte order")
            start("W45", "module")
        if tick == 44: line("W45", "running 4 tests")
        if tick == 46: finish(_module("FAILED", _target("PASSED"), "PASSED", "PASSED"))
        if tick == 47: say("Ilse", f"I won't message {SERIAL} about W45 until the bench rig has rerun it.")
        if tick == 48: say("Ruairi", f"Has anyone messaged {SERIAL} about W45?")
        if tick == 49: say("Ruairi", f"I'm going to message {PLATFORM} about W45.")
        if tick == 50: say("Ilse", f"I've messaged {SERIAL} about W45.")
        # Act 5: the serial fix arrives by pull with a lock bump; full suite; ready.
        if tick == 51:
            pull([(LOCKFILE, "- serialport 4.5.1\n+ serialport 4.5.2"),
                  (UART, "- const RESYNC_WINDOW: usize = 4;\n+ const RESYNC_WINDOW: usize = 12;")])
        if tick == 54: start("W46", "full")
        if tick == 55: line("W46", "running 5 tests")
        if tick == 56:
            finish(_module("PASSED", _target("PASSED"), "PASSED", "PASSED") + [_result(DATUM, "PASSED")])
        if tick == 57: dirty(GUST)
        if tick == 58: say("Ruairi", "That is only a typo in a doc comment; I'll throw it away.")
        if tick == 59: revert()
        if tick in NOTES:
            evidence.append(NOTES[tick])
        if not evidence:
            evidence = [f"clock advanced to {now}; cursor at line {state['editor']['cursor_line']}; no new event"]
        public = deepcopy(state)
        steps.append({"t": tick, "state": public, "gold": reference(public), "evidence": evidence})
    return {
        "episode_id": "train_debugging_d", "task_family": "live_debugging",
        "scenario_id": "debugging_d", "title": state["session"]["title"], "tick_seconds": 2.0,
        "questions": _questions([HEADING, GUST], [SERIAL, GEODESY, PLATFORM]),
        "decision_spec": {"route_question": "route", "always": ["process", "target_result"],
                          "branches": {"wait": [], "rerun": ["rerun_scope"], "inspect": ["inspect_file"],
                                       "control": ["control_action"], "delegate": ["owner"], "ready": []}},
        "steps": steps,
    }


def scenarios() -> list[dict]:
    """One 60-tick scripted session of the training split."""
    return [_build()]
