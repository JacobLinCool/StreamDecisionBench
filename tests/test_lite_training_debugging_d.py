"""Boundary and counterfactual checks for training variant debugging_d (shared family policy)."""

from copy import deepcopy
import json

import pytest

from streamdecisionbench.lite.core import compose
from streamdecisionbench.lite.tasks import debugging
from streamdecisionbench.lite.training import debugging_d
from streamdecisionbench.lite.training.audit import leakage
from streamdecisionbench.lite.training.debugging_d import reference, scenarios

CHECKSUM = "crates/decoder/src/checksum.rs"
GUST = "crates/decoder/src/fields/gust.rs"
UART = "crates/decoder/src/sys/uart_clock.rs"
FRAMING = "crates/decoder/src/framing.rs"
TARGET = "roundtrip::gust_speed_survives_reframing"


@pytest.fixture(scope="module")
def episode():
    (only,) = scenarios()
    return only


def at(episode, tick):
    return deepcopy(episode["steps"][tick]["state"])


def decision(episode, state):
    return compose(episode["decision_spec"], reference(state))


def test_shared_family_rules_are_reused_verbatim(episode):
    assert debugging_d.reference is debugging.reference
    assert episode["questions"] == debugging._questions(
        [CHECKSUM, GUST], ["@serial-io", "@geodesy", "@rust-platform"])
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


KEY_TICKS = {
    0: {"route": "wait", "process": "running", "target_result": "original_error"},
    1: {"route": "wait", "process": "paused", "target_result": "original_error"},
    7: {"route": "wait", "process": "paused", "target_result": "original_error"},
    8: {"route": "control", "process": "paused", "target_result": "original_error", "control_action": "continue"},
    10: {"route": "wait", "process": "running", "target_result": "original_error"},
    13: {"route": "inspect", "process": "idle", "target_result": "different_error", "inspect_file": CHECKSUM},
    15: {"route": "wait", "process": "idle", "target_result": "different_error"},
    17: {"route": "wait", "process": "idle", "target_result": "different_error"},
    18: {"route": "rerun", "process": "idle", "target_result": "different_error", "rerun_scope": "module"},
    21: {"route": "inspect", "process": "idle", "target_result": "different_error", "inspect_file": GUST},
    26: {"route": "rerun", "process": "idle", "target_result": "different_error", "rerun_scope": "target"},
    31: {"route": "wait", "process": "running", "target_result": "different_error"},
    32: {"route": "wait", "process": "stalled", "target_result": "different_error"},
    33: {"route": "wait", "process": "stalled", "target_result": "different_error"},
    34: {"route": "rerun", "process": "idle", "target_result": "not_run", "rerun_scope": "target"},
    38: {"route": "rerun", "process": "idle", "target_result": "passed", "rerun_scope": "module"},
    42: {"route": "rerun", "process": "idle", "target_result": "not_run", "rerun_scope": "target"},
    45: {"route": "rerun", "process": "idle", "target_result": "not_run", "rerun_scope": "full"},
    48: {"route": "delegate", "process": "idle", "target_result": "passed", "owner": "@serial-io"},
    49: {"route": "delegate", "process": "idle", "target_result": "passed", "owner": "@serial-io"},
    50: {"route": "delegate", "process": "idle", "target_result": "passed", "owner": "@serial-io"},
    51: {"route": "wait", "process": "idle", "target_result": "passed"},
    54: {"route": "rerun", "process": "idle", "target_result": "passed", "rerun_scope": "full"},
    56: {"route": "ready", "process": "idle", "target_result": "passed"},
    57: {"route": "ready", "process": "idle", "target_result": "passed"},
    58: {"route": "wait", "process": "idle", "target_result": "passed"},
    59: {"route": "wait", "process": "idle", "target_result": "passed"},
}


@pytest.mark.parametrize("tick", sorted(KEY_TICKS))
def test_story_key_ticks(episode, tick):
    assert compose(episode["decision_spec"], episode["steps"][tick]["gold"]) == KEY_TICKS[tick]


def test_pause_timer_counts_debugger_events_not_saves_or_messages(episode):
    # Step at t4; the docs save at t5 and the message at t6 do not restart the pause timer.
    assert [reference(at(episode, t))["route"] for t in range(1, 8)] == ["wait"] * 7
    state = at(episode, 8)
    state["saves"].append({"time": 8, "file": "crates/decoder/src/reader.rs", "diff": "+ trace"})
    state["call"].append({"time": 8, "speaker": "Ilse", "text": "Still waiting on it.", "final": True})
    assert reference(state)["control_action"] == "continue"  # also overrides a fresh relevant write
    state["editor"]["dirty_files"] = [GUST]
    assert reference(state)["control_action"] == "continue"  # and an unsaved relevant buffer
    state = at(episode, 8)
    state["debugger"]["events"].append({"time": 8, "run": "W41", "kind": "evaluate", "file": "x.rs"})
    assert (reference(state)["route"], reference(state)["process"]) == ("wait", "paused")
    state = at(episode, 7)
    state["debugger"]["events"][-1]["time"] = 3  # step one tick earlier -> four ticks by t7
    assert reference(state)["control_action"] == "continue"


def test_continued_event_resets_run_silence(episode):
    state = at(episode, 11)
    assert reference(state)["process"] == "running"
    # Without the continued event the run would have been silent since t-1.
    state["debugger"]["events"][-1]["kind"] = "evaluate"
    state["debugger"]["status"] = "running"
    answer = reference(state)
    assert (answer["process"], answer["route"], answer["control_action"]) == ("stalled", "control", "stop")


def test_unrelated_terminal_output_does_not_reset_silence(episode):
    state = at(episode, 32)
    assert reference(state)["process"] == "stalled"
    line = next(row for row in state["terminal"] if row["time"] == 31)
    assert line["run"] is None
    line["run"] = "W43"
    assert reference(state)["process"] == "running"
    state = at(episode, 33)
    state["clock_tick"] = 34  # had the run not been interrupted, six silent ticks enable stop
    assert reference(state)["control_action"] == "stop"


def test_new_failure_beats_target_and_first_listed_failure(episode):
    state = at(episode, 13)
    failed = [row["test"] for row in state["runs"][-1]["results"] if row["outcome"] == "FAILED"]
    assert failed[0] != TARGET and failed[1] == TARGET and failed[2] == "checksum::rejects_bad_nibble"
    assert reference(state)["inspect_file"] == CHECKSUM
    # Had the checksum test already failed in W40, nothing is new and the pinned target wins.
    previous = next(run for run in state["runs"] if run["id"] == "W40")
    previous["results"][2] = deepcopy(state["runs"][-1]["results"][2])
    assert reference(state)["inspect_file"] == GUST


def test_without_new_failures_the_target_beats_the_first_listed_failure(episode):
    state = at(episode, 21)
    assert reference(state)["inspect_file"] == GUST
    # If the pinned target had passed, the first failing test (UART-owned) would be selected.
    state["runs"][-1]["results"][1] = {"test": TARGET, "outcome": "PASSED", "message": "", "trace": []}
    answer = reference(state)
    assert (answer["route"], answer["owner"], answer["target_result"]) == ("delegate", "@serial-io", "passed")


def test_vendor_frames_are_ignored_and_original_message_is_exact(episode):
    state = at(episode, 21)
    trace = state["runs"][-1]["results"][1]["trace"]
    assert trace[-1].startswith("~/") and trace[-2].startswith("vendor/") and trace[-3] == GUST
    state["runs"][-1]["results"][1]["trace"] = trace[:2] + trace[3:]
    assert reference(state)["inspect_file"] == "crates/decoder/src/reader.rs"
    state = at(episode, 13)
    assert reference(state)["target_result"] == "different_error"
    state["runs"][-1]["results"][1]["message"] = state["session"]["original_failure"]
    assert reference(state)["target_result"] == "original_error"


def test_save_grace_and_write_at_run_start(episode):
    assert reference(at(episode, 17))["route"] == "wait"
    state = at(episode, 18)
    assert reference(state)["rerun_scope"] == "module"
    state["clock_tick"] = 17.99
    assert reference(state)["route"] == "wait"
    # The checksum save at t19 coincides with W42's start, so W42 already loaded it.
    state = at(episode, 21)
    assert reference(state)["route"] == "inspect"  # exactly two ticks after that save
    late = at(episode, 22)
    late["saves"][-1]["time"] = 19.5
    assert late["saves"][-1]["file"] == CHECKSUM
    assert (reference(late)["route"], reference(late)["rerun_scope"]) == ("rerun", "module")
    # At t26 only the gust write is after W42's start: target, not module.
    assert reference(at(episode, 26))["rerun_scope"] == "target"


def test_interrupted_or_skipped_target_reruns_target_before_failures(episode):
    answer = reference(at(episode, 34))
    assert (answer["route"], answer["rerun_scope"], answer["target_result"]) == ("rerun", "target", "not_run")
    state = at(episode, 42)
    latest = state["runs"][-1]
    assert [row["outcome"] for row in latest["results"][:2]] == ["FAILED", "SKIPPED"]
    assert reference(state)["rerun_scope"] == "target"
    latest["results"][1] = {"test": TARGET, "outcome": "PASSED", "message": "", "trace": []}
    assert (reference(state)["route"], reference(state)["owner"]) == ("delegate", "@serial-io")
    state = at(episode, 42)
    state["runs"][-1]["results"].pop(1)  # an absent target is also not run
    assert (reference(state)["rerun_scope"], reference(state)["target_result"]) == ("target", "not_run")


def test_skips_above_allowance_rerun_module(episode):
    state = at(episode, 38)
    assert state["session"]["allowed_skips"] == 0
    assert (reference(state)["route"], reference(state)["rerun_scope"]) == ("rerun", "module")
    state["session"]["allowed_skips"] = 3
    assert reference(state)["route"] == "ready"


def test_manifest_write_maps_to_full_by_last_scope_rule(episode):
    assert reference(at(episode, 43))["route"] == "wait"
    state = at(episode, 45)
    assert reference(state)["rerun_scope"] == "full"
    state["session"]["scope_rules"] = [rule for rule in state["session"]["scope_rules"]
                                       if rule[0] != "crates/*/Cargo.toml"]
    assert reference(state)["rerun_scope"] == "module"


def test_last_matching_owner_rule_with_nested_patterns(episode):
    state = at(episode, 48)
    assert reference(state)["owner"] == "@serial-io"
    owners = state["session"]["owners"]
    sys_rule = owners.pop()
    assert sys_rule == ["crates/*/src/sys/*", "@serial-io"]
    owners.insert(2, sys_rule)  # now crates/decoder/* comes later and wins
    answer = reference(state)
    assert (answer["route"], answer["inspect_file"]) == ("inspect", UART)
    state = at(episode, 48)
    state["runs"][-1]["results"][0]["trace"].remove(UART)
    answer = reference(state)
    assert (answer["route"], answer["inspect_file"]) == ("inspect", FRAMING)


@pytest.mark.parametrize("text, final, speaker, route", [
    ("I have contacted @serial-io about W46.", True, "Ruairi", "wait"),
    ("I'm going to contact @serial-io about W46.", True, "Ilse", "wait"),
    ("I have contacted @serial-io about W46.", False, "Ruairi", "delegate"),
    ("I have contacted @serial-io about W45.", True, "Ruairi", "delegate"),
    ("I have contacted @geodesy about W46.", True, "Ruairi", "delegate"),
    ("Should I contact @serial-io about W46?", True, "Ruairi", "delegate"),
    ("I will not contact @serial-io about W46.", True, "Ruairi", "delegate"),
    ("I have contacted @serial-io about W46.", True, "Odile", "delegate"),
])
def test_handoff_requires_final_teammate_commitment_for_team_and_run(episode, text, final, speaker, route):
    state = at(episode, 51)
    state["call"][-1].update({"text": text, "final": final, "speaker": speaker})
    assert reference(state)["route"] == route


def test_ready_needs_uncommitted_files_and_ignores_irrelevant_edits(episode):
    state = at(episode, 57)
    assert reference(state)["route"] == "ready"
    state["editor"]["dirty_files"] = ["notes.md"]
    assert reference(state)["route"] == "ready"
    state["editor"]["dirty_files"] = [GUST]
    assert reference(state)["route"] == "wait"
    state = at(episode, 58)
    assert state["git"]["uncommitted"] == [] and reference(state)["route"] == "wait"
    state["git"]["uncommitted"] = ["crates/decoder/src/reader.rs"]
    assert reference(state)["route"] == "ready"


def test_all_routes_badges_and_branch_values_reached(episode):
    answers = [step["gold"] for step in episode["steps"]]
    assert {a["route"] for a in answers} == {"wait", "rerun", "inspect", "control", "delegate", "ready"}
    assert {a["process"] for a in answers} == {"idle", "running", "paused", "stalled"}
    assert {a["target_result"] for a in answers} == {"not_run", "passed", "original_error", "different_error"}
    assert {a["rerun_scope"] for a in answers} == {"none", "target", "module", "full"}
    assert {a["control_action"] for a in answers} == {"none", "continue"}
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
