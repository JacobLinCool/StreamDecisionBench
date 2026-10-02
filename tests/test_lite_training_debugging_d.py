"""Boundary and counterfactual checks for training variant debugging_d (shared family policy)."""

from copy import deepcopy
import json

import pytest

from streamdecisionbench.lite.core import compose
from streamdecisionbench.lite.tasks import debugging
from streamdecisionbench.lite.training import debugging_d
from streamdecisionbench.lite.training.audit import leakage
from streamdecisionbench.lite.training.debugging_d import reference, scenarios

HEADING = "crates/decoder/src/fields/heading.rs"
GUST = "crates/decoder/src/fields/gust.rs"
READER = "crates/decoder/src/reader.rs"
UART = "crates/decoder/src/sys/uart_clock.rs"
FRAMING = "crates/decoder/src/framing.rs"
TARGET = "roundtrip::gust_speed_survives_reframing"
JITTER = "framing::resyncs_after_uart_jitter"


@pytest.fixture(scope="module")
def episode():
    (only,) = scenarios()
    return only


def at(episode, tick):
    return deepcopy(episode["steps"][tick]["state"])


def decision(episode, state):
    return compose(episode["decision_spec"], reference(state))


def run(state, run_id):
    return next(row for row in state["runs"] if row["id"] == run_id)


def test_shared_family_rules_are_reused_verbatim(episode):
    assert debugging_d.reference is debugging.reference
    assert episode["questions"] == debugging._questions(
        [HEADING, GUST], ["@serial-io", "@geodesy", "@rust-platform"])
    assert episode["task_family"] == "live_debugging"
    assert (episode["episode_id"], episode["scenario_id"]) == ("train_debugging_d", "debugging_d")
    assert all(step["state"]["session"]["policy"] == debugging.POLICY for step in episode["steps"])


def test_release_manifest_and_public_only_reproduction(episode):
    assert len(episode["questions"]) == 7
    assert len(episode["steps"]) == 60
    assert episode["tick_seconds"] == 2
    for tick, step in enumerate(episode["steps"]):
        assert step["t"] == tick
        assert step["evidence"] and all(isinstance(item, str) for item in step["evidence"])
        state = json.loads(json.dumps(step["state"]))
        assert state["clock_tick"] == tick
        assert not {"gold", "hidden", "answer", "route"} & state.keys()
        assert reference(state) == step["gold"]
        assert all(row["time"] <= tick for row in state["saves"] + state["terminal"] + state["call"])
        assert all(event["time"] <= tick for event in state["debugger"]["events"])
        assert all(run["started"] <= tick and (run["finished"] is None or run["finished"] <= tick)
                   for run in state["runs"])
        assert set(step["gold"]) == set(episode["questions"])
        for qid, value in step["gold"].items():
            assert value in episode["questions"][qid]["criteria"]


def test_states_are_cumulative_and_runs_consistent(episode):
    previous = None
    for step in episode["steps"]:
        state = step["state"]
        ids = [run["id"] for run in state["runs"]]
        assert len(ids) == len(set(ids))
        active = [run for run in state["runs"] if run["finished"] is None]
        assert len(active) <= 1
        if not active:
            assert state["debugger"]["status"] == "inactive"
        if state["debugger"]["status"] == "paused":
            assert active and any(e["run"] == active[0]["id"] for e in state["debugger"]["events"])
        assert all(row["run"] is None or row["run"] in ids for row in state["terminal"])
        assert all(event["run"] in ids for event in state["debugger"]["events"])
        assert all(row["speaker"] in state["session"]["teammates"] for row in state["call"])
        for run in state["runs"]:
            assert run["started"] in [row["time"] for row in state["terminal"] if row["run"] == run["id"]]
            if run["finished"] is not None:
                assert run["summary"] in [row["text"] for row in state["terminal"] if row["run"] == run["id"]]
        if previous is not None:
            for key in ("saves", "terminal", "call"):
                assert state[key][:len(previous[key])] == previous[key]
            events = previous["debugger"]["events"]
            assert state["debugger"]["events"][:len(events)] == events
            assert state["session"] == previous["session"]
            old = {run["id"]: run for run in previous["runs"]}
            for run in state["runs"]:
                if run["id"] in old and old[run["id"]]["finished"] is not None:
                    assert run == old[run["id"]]  # finished results never change
            assert set(old) <= set(ids)
        previous = state


def test_story_is_internally_consistent(episode):
    final = episode["steps"][-1]["state"]
    # Every locally saved file is uncommitted; the pulled files arrive committed and say so in the terminal.
    pulled = {"Cargo.lock", UART}
    local = {row["file"] for row in final["saves"]} - pulled
    assert set(final["git"]["uncommitted"]) == local
    pull = next(row for row in final["terminal"] if row["text"].startswith("$ git pull"))
    assert pull["run"] is None and all(path in pull["text"] for path in pulled)
    assert {row["time"] for row in final["saves"] if row["file"] in pulled} == {pull["time"]}
    # The serialport version in pre-pull traces is the one the lock bump replaces.
    lock = next(row for row in final["saves"] if row["file"] == "Cargo.lock")
    assert lock["diff"].startswith("- serialport 4.5.1\n")
    frames = [frame for r in final["runs"] for row in r["results"] for frame in row["trace"] if "serialport" in frame]
    assert frames and all("serialport-4.5.1/" in frame for frame in frames)
    # The compile errors name the call sites of the changed reader signature.
    errors = run(final, "W41")["compiler_errors"]
    assert [row["file"] for row in errors] == [HEADING, GUST]
    assert all(row["file"] in row["message"] for row in errors)


KEY_TICKS = {
    0: {"route": "wait", "process": "running", "target_result": "original_error"},
    1: {"route": "wait", "process": "stalled", "target_result": "original_error"},
    2: {"route": "wait", "process": "running", "target_result": "original_error"},
    4: {"route": "inspect", "process": "idle", "target_result": "not_run", "inspect_file": HEADING},
    5: {"route": "inspect", "process": "idle", "target_result": "not_run", "inspect_file": HEADING},
    6: {"route": "wait", "process": "idle", "target_result": "not_run"},
    9: {"route": "wait", "process": "idle", "target_result": "not_run"},
    10: {"route": "rerun", "process": "idle", "target_result": "not_run", "rerun_scope": "module"},
    14: {"route": "inspect", "process": "idle", "target_result": "different_error", "inspect_file": GUST},
    15: {"route": "inspect", "process": "idle", "target_result": "different_error", "inspect_file": GUST},
    17: {"route": "wait", "process": "paused", "target_result": "different_error"},
    26: {"route": "wait", "process": "paused", "target_result": "different_error"},
    27: {"route": "control", "process": "paused", "target_result": "different_error", "control_action": "continue"},
    28: {"route": "control", "process": "paused", "target_result": "different_error", "control_action": "continue"},
    29: {"route": "wait", "process": "running", "target_result": "different_error"},
    33: {"route": "wait", "process": "running", "target_result": "different_error"},
    34: {"route": "wait", "process": "stalled", "target_result": "different_error"},
    35: {"route": "wait", "process": "stalled", "target_result": "different_error"},
    36: {"route": "control", "process": "stalled", "target_result": "different_error", "control_action": "stop"},
    37: {"route": "control", "process": "stalled", "target_result": "different_error", "control_action": "stop"},
    38: {"route": "rerun", "process": "idle", "target_result": "not_run", "rerun_scope": "target"},
    41: {"route": "rerun", "process": "idle", "target_result": "passed", "rerun_scope": "module"},
    42: {"route": "rerun", "process": "idle", "target_result": "passed", "rerun_scope": "module"},
    43: {"route": "wait", "process": "running", "target_result": "passed"},
    46: {"route": "delegate", "process": "idle", "target_result": "passed", "owner": "@serial-io"},
    47: {"route": "delegate", "process": "idle", "target_result": "passed", "owner": "@serial-io"},
    48: {"route": "delegate", "process": "idle", "target_result": "passed", "owner": "@serial-io"},
    49: {"route": "delegate", "process": "idle", "target_result": "passed", "owner": "@serial-io"},
    50: {"route": "wait", "process": "idle", "target_result": "passed"},
    52: {"route": "wait", "process": "idle", "target_result": "passed"},
    53: {"route": "rerun", "process": "idle", "target_result": "passed", "rerun_scope": "full"},
    56: {"route": "ready", "process": "idle", "target_result": "passed"},
    57: {"route": "wait", "process": "idle", "target_result": "passed"},
    58: {"route": "wait", "process": "idle", "target_result": "passed"},
    59: {"route": "ready", "process": "idle", "target_result": "passed"},
}


@pytest.mark.parametrize("tick", sorted(KEY_TICKS))
def test_story_key_ticks(episode, tick):
    assert compose(episode["decision_spec"], episode["steps"][tick]["gold"]) == KEY_TICKS[tick]


def test_build_silence_counts_only_the_runs_own_lines(episode):
    # W41's last line was at -3: four silent ticks at t1, then its own compiler line resets it.
    assert reference(at(episode, 1))["process"] == "stalled"
    state = at(episode, 1)
    state["clock_tick"] = 3  # without the t2/t3 compiler lines, six silent ticks enable stop
    answer = reference(state)
    assert (answer["route"], answer["control_action"]) == ("control", "stop")


def test_first_compiler_file_beats_editor_diagnostics_and_teammate(episode):
    state = at(episode, 5)
    assert [row["file"] for row in state["diagnostics"] if "argument" in row["message"]] == [GUST]
    assert "gust.rs" in state["call"][-1]["text"]
    assert reference(state)["inspect_file"] == HEADING
    latest = run(state, "W41")
    latest["compiler_errors"].reverse()
    assert reference(state)["inspect_file"] == GUST
    # Compile failure outranks the pre-existing reader write, which predates W41's start.
    state = at(episode, 4)
    reader = next(row for row in state["saves"] if row["file"] == READER)
    assert reader["time"] < run(state, "W41")["started"]
    reader["time"] = run(state, "W41")["started"] + 1
    assert (reference(state)["route"], reference(state)["rerun_scope"]) == ("rerun", "module")


def test_save_grace_and_widest_scope(episode):
    assert reference(at(episode, 9))["route"] == "wait"
    state = at(episode, 10)
    assert reference(state)["rerun_scope"] == "module"
    state["clock_tick"] = 9.99
    assert reference(state)["route"] == "wait"
    # Only the gust.rs write would map to target.
    state = at(episode, 10)
    state["saves"] = [row for row in state["saves"] if row["file"] != HEADING]
    assert reference(state)["rerun_scope"] == "target"
    # Last matching scope rule: a gust.rs write maps to target although crates/* says module.
    state["session"]["scope_rules"] = [rule for rule in state["session"]["scope_rules"] if rule[0] != GUST]
    assert reference(state)["rerun_scope"] == "module"


def test_new_failure_beats_target_and_first_listed_failure(episode):
    # W41 compiled nothing, so the target failure in W42 is new and selects gust.rs.
    state = at(episode, 14)
    assert run(state, "W41")["results"] == []
    assert reference(state)["inspect_file"] == GUST
    # In W45 the jitter test is new (skipped in W44); a newly failing target after it would not win.
    state = at(episode, 46)
    assert [row["outcome"] for row in run(state, "W44")["results"]][0] == "SKIPPED"
    latest = run(state, "W45")["results"]
    template = deepcopy(at(episode, 14)["runs"][-1]["results"][1])
    latest[1] = template
    assert (reference(state)["route"], reference(state)["owner"]) == ("delegate", "@serial-io")
    # Had the jitter test already failed in W44, the newly failing target is selected instead.
    run(state, "W44")["results"][0] = deepcopy(latest[0])
    assert (reference(state)["route"], reference(state)["inspect_file"]) == ("inspect", GUST)
    # And with nothing new at all, the pinned target still beats the first listed failure.
    run(state, "W44")["results"][1] = deepcopy(template)
    assert (reference(state)["route"], reference(state)["inspect_file"]) == ("inspect", GUST)


def test_vendor_frames_are_ignored_and_original_message_is_exact(episode):
    state = at(episode, 14)
    trace = state["runs"][-1]["results"][1]["trace"]
    assert trace[-1].startswith("~/") and trace[-2].startswith("vendor/") and trace[-3] == GUST
    state["runs"][-1]["results"][1]["trace"] = trace[:3] + trace[4:]
    assert reference(state)["inspect_file"] == READER
    state = at(episode, 14)
    assert reference(state)["target_result"] == "different_error"
    state["runs"][-1]["results"][1]["message"] = state["session"]["original_failure"]
    assert reference(state)["target_result"] == "original_error"
    state["runs"][-1]["results"][1]["message"] += " "
    assert reference(state)["target_result"] == "different_error"


def test_pause_timer_counts_debugger_events_not_saves_or_messages(episode):
    # Paused at 17, evaluate 18, steps at 20 and 23: the card appears only four ticks after the last step.
    assert [reference(at(episode, t))["route"] for t in range(17, 27)] == ["wait"] * 10
    state = at(episode, 27)
    assert state["editor"]["dirty_files"] == []
    assert max(row["time"] for row in state["saves"]) == 26  # a relevant write one tick old
    assert reference(state)["control_action"] == "continue"
    state["editor"]["dirty_files"] = [GUST]
    assert reference(state)["control_action"] == "continue"  # also overrides an unsaved relevant buffer
    state = at(episode, 27)
    state["debugger"]["events"].append({"time": 27, "run": "W43", "kind": "evaluate", "file": GUST})
    assert (reference(state)["route"], reference(state)["process"]) == ("wait", "paused")
    state = at(episode, 27)
    state["debugger"]["events"][-1]["time"] = 24  # last step one tick later -> still wait at t27
    assert reference(state)["route"] == "wait"


def test_continued_event_resets_run_silence(episode):
    state = at(episode, 29)
    assert reference(state)["process"] == "running"
    # Without the continued event W43 would have been silent since its start at 16.
    state["debugger"]["events"][-1]["kind"] = "step"
    state["debugger"]["status"] = "running"
    answer = reference(state)
    assert (answer["process"], answer["route"], answer["control_action"]) == ("stalled", "control", "stop")


def test_unrelated_terminal_output_does_not_reset_silence(episode):
    state = at(episode, 34)
    assert reference(state)["process"] == "stalled"
    line = next(row for row in state["terminal"] if row["time"] == 32)
    assert line["run"] is None
    line["run"] = "W43"
    assert reference(state)["process"] == "running"
    state = at(episode, 36)
    line = next(row for row in state["terminal"] if row["time"] == 32)
    line["run"] = "W43"
    assert (reference(state)["route"], reference(state)["process"]) == ("wait", "stalled")


def test_stop_overrides_dirty_buffers_and_fresh_writes(episode):
    state = at(episode, 36)
    state["editor"]["dirty_files"] = [GUST]
    state["saves"].append({"time": 36, "file": GUST, "diff": "+ // probe"})
    answer = reference(state)
    assert (answer["route"], answer["control_action"]) == ("control", "stop")


def test_interrupted_or_skipped_target_reruns_target_before_failures(episode):
    answer = reference(at(episode, 38))
    assert (answer["route"], answer["rerun_scope"], answer["target_result"]) == ("rerun", "target", "not_run")
    # Even without the gust.rs write after W43's start, the interruption alone asks for a target rerun.
    state = at(episode, 38)
    state["saves"] = [row for row in state["saves"] if row["time"] <= 16]
    assert (reference(state)["route"], reference(state)["rerun_scope"]) == ("rerun", "target")
    state = at(episode, 46)
    state["runs"][-1]["results"][1]["outcome"] = "SKIPPED"
    answer = reference(state)
    assert (answer["route"], answer["rerun_scope"], answer["target_result"]) == ("rerun", "target", "not_run")
    state = at(episode, 46)
    state["runs"][-1]["results"].pop(1)  # an absent target is also not run
    assert (reference(state)["rerun_scope"], reference(state)["target_result"]) == ("target", "not_run")


def test_skips_above_allowance_rerun_module(episode):
    state = at(episode, 41)
    assert state["session"]["allowed_skips"] == 0
    assert (reference(state)["route"], reference(state)["rerun_scope"]) == ("rerun", "module")
    state["session"]["allowed_skips"] = 3
    assert reference(state)["route"] == "ready"


def test_write_exactly_at_run_start_is_already_loaded(episode):
    state = at(episode, 46)
    save = state["saves"][-1]
    assert (save["file"], save["time"]) == (READER, run(state, "W45")["started"])
    assert reference(state)["route"] == "delegate"
    save["time"] = 43.5
    assert (reference(state)["route"], reference(state)["rerun_scope"]) == ("rerun", "module")


def test_lock_file_bump_maps_to_full_by_scope_rule(episode):
    assert [reference(at(episode, t))["route"] for t in (51, 52)] == ["wait", "wait"]
    state = at(episode, 53)
    assert reference(state)["rerun_scope"] == "full"
    state["session"]["scope_rules"] = [rule for rule in state["session"]["scope_rules"] if rule[0] != "Cargo.lock"]
    assert reference(state)["rerun_scope"] == "module"  # only the pulled uart_clock.rs remains


def test_last_matching_owner_rule_with_nested_patterns(episode):
    state = at(episode, 46)
    assert reference(state)["owner"] == "@serial-io"
    owners = state["session"]["owners"]
    sys_rule = owners.pop()
    assert sys_rule == ["crates/*/src/sys/*", "@serial-io"]
    owners.insert(2, sys_rule)  # now crates/decoder/* comes later and wins
    answer = reference(state)
    assert (answer["route"], answer["inspect_file"]) == ("inspect", UART)
    state = at(episode, 46)
    state["runs"][-1]["results"][0]["trace"].remove(UART)
    answer = reference(state)
    assert (answer["route"], answer["inspect_file"]) == ("inspect", FRAMING)
    state = at(episode, 46)
    state["runs"][-1]["results"][0]["trace"][2] = "crates/geo/src/datum.rs"
    assert reference(state)["owner"] == "@geodesy"
    state["runs"][-1]["results"][0]["trace"][2] = "crates/telemetry/src/frame.rs"
    assert reference(state)["owner"] == "@rust-platform"


def test_timeline_distractors_keep_delegation_active(episode):
    texts = [row["text"] for row in at(episode, 49)["call"] if row["time"] in (47, 48, 49)]
    assert texts == ["I won't message @serial-io about W45 until the bench rig has rerun it.",
                     "Has anyone messaged @serial-io about W45?",
                     "I'm going to message @rust-platform about W45."]
    assert all(reference(at(episode, t))["route"] == "delegate" for t in (47, 48, 49))


@pytest.mark.parametrize("text, final, speaker, route", [
    ("I've messaged @serial-io about W45.", True, "Ilse", "wait"),
    ("I'm going to message @serial-io about W45.", True, "Ruairi", "wait"),
    ("I will contact @serial-io about W45!", True, "Ruairi", "wait"),
    ("I've messaged @serial-io about W45.", False, "Ilse", "delegate"),
    ("I've messaged @serial-io about W44.", True, "Ilse", "delegate"),
    ("I've messaged @geodesy about W45.", True, "Ilse", "delegate"),
    ("Could you message @serial-io about W45?", True, "Ilse", "delegate"),
    ("I haven't messaged @serial-io about W45.", True, "Ilse", "delegate"),
    ("I've messaged @serial-io about W45.", True, "Oona", "delegate"),
])
def test_handoff_requires_final_teammate_commitment_for_team_and_run(episode, text, final, speaker, route):
    state = at(episode, 50)
    state["call"][-1].update({"text": text, "final": final, "speaker": speaker})
    assert reference(state)["route"] == route


def test_ready_needs_uncommitted_files_and_ignores_irrelevant_edits(episode):
    state = at(episode, 56)
    assert reference(state)["route"] == "ready"
    state["editor"]["dirty_files"] = ["docs/gust-encoding.md"]
    assert reference(state)["route"] == "ready"
    state["editor"]["dirty_files"] = [GUST]
    assert reference(state)["route"] == "wait"
    state = at(episode, 59)
    assert reference(state)["route"] == "ready"
    state["git"]["uncommitted"] = []
    assert reference(state)["route"] == "wait"


def test_all_routes_badges_and_branch_values_reached(episode):
    answers = [step["gold"] for step in episode["steps"]]
    assert {a["route"] for a in answers} == {"wait", "rerun", "inspect", "control", "delegate", "ready"}
    assert {a["process"] for a in answers} == {"idle", "running", "paused", "stalled"}
    assert {a["target_result"] for a in answers} == {"not_run", "passed", "original_error", "different_error"}
    assert {a["rerun_scope"] for a in answers} == {"none", "target", "module", "full"}
    assert {a["control_action"] for a in answers} == {"none", "continue", "stop"}
    assert {a["owner"] for a in answers} == {"none", "@serial-io"}
    assert {a["inspect_file"] for a in answers} == set(episode["questions"]["inspect_file"]["criteria"])
    changes = sum(decision(episode, a["state"]) != decision(episode, b["state"])
                  for a, b in zip(episode["steps"], episode["steps"][1:]))
    assert 18 <= changes <= 26


def test_no_evaluation_leakage_and_fresh_deterministic_generation(episode):
    assert leakage([episode]) == []
    other = scenarios()[0]
    assert other == episode
    other["steps"][0]["state"]["runs"][0]["results"].clear()
    assert episode["steps"][0]["state"]["runs"][0]["results"]
