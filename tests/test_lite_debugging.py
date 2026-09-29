"""Boundary and counterfactual checks for the public debugging policy."""

from copy import deepcopy
import json

import pytest

from streamdecisionbench.lite.tasks.debugging import reference, scenarios


@pytest.fixture(scope="module")
def episodes():
    return scenarios()


def at(episodes, scenario, tick):
    return deepcopy(episodes[scenario]["steps"][tick]["state"])


def test_release_manifest_and_public_only_reproduction(episodes):
    assert len(episodes) == 2
    for episode in episodes:
        assert len(episode["questions"]) == 7
        assert len(episode["steps"]) == 60
        assert episode["tick_seconds"] == 2
        for tick, step in enumerate(episode["steps"]):
            assert step["t"] == tick
            state = json.loads(json.dumps(step["state"]))
            assert state["clock_tick"] == tick
            assert not {"gold", "hidden", "answer", "route"} & state.keys()
            assert reference(state) == step["gold"]
            assert all(row["time"] <= tick for row in state["saves"] + state["terminal"] + state["call"])
            assert all(event["time"] <= tick for event in state["debugger"]["events"])
            assert all(run["started"] <= tick and
                       (run["finished"] is None or run["finished"] <= tick)
                       for run in state["runs"])
            assert set(step["gold"]) == set(episode["questions"])
            for qid, value in step["gold"].items():
                assert value in episode["questions"][qid]["criteria"]


def test_new_failure_wins_over_target_still_failing(episodes):
    state = at(episodes, 0, 14)
    assert reference(state)["inspect_file"] == "src/refunds/fees.ts"
    assert reference(state)["target_result"] == "different_error"
    # If the earlier run already had that failure, it is no longer new.
    previous = state["runs"][-2]
    previous["results"].append(deepcopy(state["runs"][-1]["results"][1]))
    assert reference(state)["inspect_file"] == "src/refunds/grace.ts"


def test_compile_failure_is_not_green_or_missing_test_rerun(episodes):
    result = reference(at(episodes, 0, 23))
    assert result["target_result"] == "not_run"
    assert (result["route"], result["inspect_file"]) == ("inspect", "src/refunds/grace.ts")


def test_unrelated_write_and_unsaved_notes_do_not_reset_policy(episodes):
    state = at(episodes, 0, 41)
    assert reference(state)["route"] == "ready"
    state["editor"]["dirty_files"] = ["notes.md"]
    state["saves"].append({"time": state["clock_tick"], "file": "README.md", "diff": "+ note"})
    assert reference(state)["route"] == "ready"
    state["editor"]["dirty_files"] = ["src/refunds/grace.ts"]
    assert reference(state)["route"] == "wait"


def test_save_grace_and_start_boundary(episodes):
    state = at(episodes, 0, 9)
    assert reference(state)["route"] == "rerun"  # two ticks after save
    state["clock_tick"] -= 0.01
    assert reference(state)["route"] == "wait"
    state = at(episodes, 0, 39)
    latest = state["runs"][-1]
    state["saves"].append({"time": latest["started"], "file": "src/refunds/grace.ts", "diff": "+ fix"})
    assert reference(state)["route"] == "ready"
    state["saves"][-1]["time"] += 0.01
    assert reference(state)["route"] == "rerun"


def test_result_during_active_run_does_not_replace_finished_badge(episodes):
    state = at(episodes, 1, 28)
    active = state["runs"][-1]
    active["results"] = [{"test": state["session"]["target_test"], "outcome": "PASSED", "message": "", "trace": []}]
    answer = reference(state)
    assert answer["route"] == "wait"
    assert answer["target_result"] == "not_run"


def test_pause_evaluation_timer_and_dirty_priority(episodes):
    assert reference(at(episodes, 1, 6))["route"] == "wait"
    answer = reference(at(episodes, 1, 7))
    assert (answer["route"], answer["control_action"], answer["process"]) == ("control", "continue", "paused")
    assert reference(at(episodes, 1, 8))["control_action"] == "continue"
    state = at(episodes, 1, 8)
    state["debugger"]["events"].append({"time": state["clock_tick"], "run": "D7", "kind": "evaluate", "file": "ledger/settlement/batch.py"})
    assert reference(state)["route"] == "wait"
    assert reference(state)["process"] == "paused"


def test_continue_resets_silence_and_background_output_does_not(episodes):
    assert reference(at(episodes, 1, 9))["process"] == "running"
    assert reference(at(episodes, 1, 17))["process"] == "running"
    at_eight = reference(at(episodes, 1, 18))
    assert (at_eight["process"], at_eight["route"]) == ("stalled", "wait")
    at_twelve = reference(at(episodes, 1, 20))
    assert (at_twelve["process"], at_twelve["control_action"]) == ("stalled", "stop")
    assert reference(at(episodes, 1, 21))["control_action"] == "stop"


@pytest.mark.parametrize("tick", [31, 32, 33, 34])
def test_wrong_team_partial_and_question_do_not_accept_handoff(episodes, tick):
    answer = reference(at(episodes, 1, tick))
    assert (answer["route"], answer["owner"]) == ("delegate", "@fx-platform")


def test_positive_handoff_requires_matching_run_and_can_be_revoked(episodes):
    state = at(episodes, 1, 35)
    assert reference(state)["route"] == "wait"
    state["call"][-1]["text"] = "I will not contact @fx-platform about D9."
    assert reference(state)["route"] == "delegate"
    assert reference(at(episodes, 1, 45))["owner"] == "@platform-core"
    assert reference(at(episodes, 1, 46))["route"] == "wait"


def test_last_matching_owner_rule_and_innermost_project_frame(episodes):
    state = at(episodes, 1, 31)
    assert reference(state)["owner"] == "@fx-platform"
    state["runs"][-1]["results"][1]["trace"] = ["tests/fx_test.py", "ledger/settlement/batch.py", ".venv/sql/engine.py"]
    answer = reference(state)
    assert (answer["route"], answer["inspect_file"]) == ("inspect", "ledger/settlement/batch.py")


def test_all_route_scope_badge_and_control_values_reached(episodes):
    answers = [step["gold"] for episode in episodes for step in episode["steps"]]
    assert {a["route"] for a in answers} == {"wait", "rerun", "inspect", "control", "delegate", "ready"}
    assert {a["process"] for a in answers} == {"idle", "running", "paused", "stalled"}
    assert {a["target_result"] for a in answers} == {"not_run", "passed", "original_error", "different_error"}
    assert {a["rerun_scope"] for a in answers} == {"none", "target", "module", "full"}
    assert {a["control_action"] for a in answers} == {"none", "continue", "stop"}
    assert {a["owner"] for a in answers} == {"none", "@runtime", "@fx-platform", "@platform-core"}
    for episode in episodes:
        used = {s["gold"]["inspect_file"] for s in episode["steps"]}
        assert used == set(episode["questions"]["inspect_file"]["criteria"])


def test_scenarios_are_fresh_and_deterministic(episodes):
    other = scenarios()
    assert other == episodes
    other[0]["steps"][0]["state"]["runs"][0]["results"].clear()
    assert episodes[0]["steps"][0]["state"]["runs"][0]["results"]
