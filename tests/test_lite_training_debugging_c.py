"""Boundary and counterfactual checks for training variant debugging_c (Go stock-hold session)."""

from copy import deepcopy
import json

import pytest

from streamdecisionbench.lite.core import compose
from streamdecisionbench.lite.tasks import debugging
from streamdecisionbench.lite.training import debugging_c
from streamdecisionbench.lite.training.audit import check_module, leakage
from streamdecisionbench.lite.training.debugging_c import reference, scenarios

HOLD = "internal/reserve/hold.go"
TTL = "internal/reserve/ttl.go"
HOLD_TEST = "internal/reserve/hold_test.go"


@pytest.fixture(scope="module")
def episode():
    (only,) = scenarios()
    return only


def at(episode, tick):
    return deepcopy(episode["steps"][tick]["state"])


def decision(episode, state):
    return compose(episode["decision_spec"], reference(state))


def test_shared_rules_are_reused_verbatim(episode):
    assert debugging_c.reference is debugging.reference
    assert episode["questions"] == debugging._questions([TTL, HOLD], ["@kv-storage", "@svc-foundation"])
    for step in episode["steps"]:
        assert step["state"]["session"]["policy"] == debugging.POLICY


def test_manifest_and_public_only_reproduction(episode):
    assert (episode["episode_id"], episode["scenario_id"]) == ("train_debugging_c", "debugging_c")
    assert episode["task_family"] == "live_debugging"
    assert len(episode["questions"]) == 7
    assert len(episode["steps"]) == 60
    assert episode["tick_seconds"] == 2
    for tick, step in enumerate(episode["steps"]):
        assert step["t"] == tick and step["evidence"]
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


def test_state_schema_matches_the_evaluation_family(episode):
    family = debugging.scenarios()[0]["steps"][0]["state"]
    run_keys = set(family["runs"][0])
    for step in episode["steps"]:
        state = step["state"]
        assert set(state) == set(family)
        for key in ("session", "editor", "debugger", "git"):
            assert set(state[key]) == set(family[key])
        assert all(set(run) == run_keys for run in state["runs"])
        assert all(set(row) == {"time", "file", "diff"} for row in state["saves"])
        assert all(set(row) == {"time", "run", "text"} for row in state["terminal"])
        assert all(set(row) == {"time", "speaker", "text", "final"} for row in state["call"])
        assert all(set(row) == {"test", "outcome", "message", "trace"}
                   for run in state["runs"] for row in run["results"])
        assert all(row["outcome"] in {"PASSED", "FAILED", "SKIPPED"}
                   for run in state["runs"] for row in run["results"])


def test_states_are_causal_and_cumulative(episode):
    previous = None
    for step in episode["steps"]:
        state = step["state"]
        unfinished = [run for run in state["runs"] if run["finished"] is None]
        assert len(unfinished) <= 1
        assert state["debugger"]["status"] == ("running" if unfinished else "inactive")
        runs = {run["id"]: run for run in state["runs"]}
        for row in state["terminal"]:
            if row["run"] is not None:
                run = runs[row["run"]]
                assert run["started"] <= row["time"]
                assert run["finished"] is None or row["time"] <= run["finished"]
        for run in state["runs"]:
            if run["finished"] is not None:
                assert {"time": run["finished"], "run": run["id"], "text": run["summary"]} in state["terminal"]
                assert run["results"] or run["compiler_errors"] or run["interrupted"]
            else:
                assert run["results"] == [] and run["summary"] == "running"
        assert set(state["editor"]["dirty_files"]) <= {HOLD, TTL, "docs/reservations.md", "go.mod", HOLD_TEST}
        if previous is not None:
            assert state["session"] == previous["session"]
            for key in ("saves", "terminal", "call"):
                assert state[key][:len(previous[key])] == previous[key]
            for old, new in zip(previous["runs"], state["runs"]):
                assert old["id"] == new["id"] and old["started"] == new["started"]
                if old["finished"] is not None:
                    assert new == old  # a finished run never changes
        previous = state


KEY_TICKS = {
    0: {"route": "wait", "process": "idle", "target_result": "original_error"},
    1: {"route": "rerun", "process": "idle", "target_result": "original_error", "rerun_scope": "target"},
    2: {"route": "wait", "process": "running", "target_result": "original_error"},
    4: {"route": "inspect", "process": "idle", "target_result": "different_error", "inspect_file": TTL},
    5: {"route": "inspect", "process": "idle", "target_result": "different_error", "inspect_file": TTL},
    6: {"route": "wait", "process": "idle", "target_result": "different_error"},
    8: {"route": "wait", "process": "idle", "target_result": "different_error"},
    9: {"route": "rerun", "process": "idle", "target_result": "different_error", "rerun_scope": "module"},
    12: {"route": "inspect", "process": "idle", "target_result": "not_run", "inspect_file": HOLD},
    13: {"route": "inspect", "process": "idle", "target_result": "not_run", "inspect_file": HOLD},
    17: {"route": "wait", "process": "idle", "target_result": "not_run"},
    18: {"route": "rerun", "process": "idle", "target_result": "not_run", "rerun_scope": "module"},
    21: {"route": "wait", "process": "running", "target_result": "not_run"},
    24: {"route": "wait", "process": "running", "target_result": "not_run"},
    25: {"route": "wait", "process": "stalled", "target_result": "not_run"},
    26: {"route": "wait", "process": "running", "target_result": "not_run"},
    29: {"route": "wait", "process": "running", "target_result": "not_run"},
    30: {"route": "wait", "process": "stalled", "target_result": "not_run"},
    31: {"route": "wait", "process": "stalled", "target_result": "not_run"},
    32: {"route": "control", "process": "stalled", "target_result": "not_run", "control_action": "stop"},
    33: {"route": "control", "process": "stalled", "target_result": "not_run", "control_action": "stop"},
    34: {"route": "wait", "process": "idle", "target_result": "not_run"},
    35: {"route": "rerun", "process": "idle", "target_result": "not_run", "rerun_scope": "target"},
    38: {"route": "rerun", "process": "idle", "target_result": "passed", "rerun_scope": "module"},
    39: {"route": "rerun", "process": "idle", "target_result": "passed", "rerun_scope": "module"},
    40: {"route": "wait", "process": "running", "target_result": "passed"},
    42: {"route": "delegate", "process": "idle", "target_result": "passed", "owner": "@kv-storage"},
    47: {"route": "delegate", "process": "idle", "target_result": "passed", "owner": "@kv-storage"},
    48: {"route": "wait", "process": "idle", "target_result": "passed"},
    51: {"route": "wait", "process": "idle", "target_result": "passed"},
    52: {"route": "rerun", "process": "idle", "target_result": "passed", "rerun_scope": "full"},
    55: {"route": "ready", "process": "idle", "target_result": "passed"},
    57: {"route": "ready", "process": "idle", "target_result": "passed"},
    58: {"route": "wait", "process": "idle", "target_result": "passed"},
    59: {"route": "wait", "process": "idle", "target_result": "passed"},
}


@pytest.mark.parametrize("tick", sorted(KEY_TICKS))
def test_key_ticks_of_the_story(episode, tick):
    assert compose(episode["decision_spec"], episode["steps"][tick]["gold"]) == KEY_TICKS[tick]


def test_rich_dynamics_and_value_coverage(episode):
    answers = [step["gold"] for step in episode["steps"]]
    decisions = [compose(episode["decision_spec"], a) for a in answers]
    changes = sum(a != b for a, b in zip(decisions, decisions[1:]))
    assert 18 <= changes <= 26
    assert {a["route"] for a in answers} == {"wait", "rerun", "inspect", "control", "delegate", "ready"}
    assert {a["process"] for a in answers} == {"idle", "running", "stalled"}
    assert {a["target_result"] for a in answers} == {"not_run", "passed", "original_error", "different_error"}
    assert {a["rerun_scope"] for a in answers} == {"none", "target", "module", "full"}
    assert {a["control_action"] for a in answers} == {"none", "stop"}
    assert {a["owner"] for a in answers} == {"none", "@kv-storage"}
    assert {a["inspect_file"] for a in answers} == {"none", TTL, HOLD}
    assert {a["inspect_file"] for a in answers} == set(episode["questions"]["inspect_file"]["criteria"])
    # @svc-foundation is offered only as the owner a reader gets by stopping at the internal/* rule.
    assert set(episode["questions"]["owner"]["criteria"]) == {"none", "@kv-storage", "@svc-foundation"}


def test_save_grace_boundary_and_earlier_writes(episode):
    state = at(episode, 1)
    assert decision(episode, state)["route"] == "rerun"  # exactly two ticks after the save
    state["clock_tick"] -= 0.01
    assert decision(episode, state)["route"] == "wait"
    # The ttl.go write predates G40's start; moved after it, it widens the rerun to module.
    state = at(episode, 1)
    assert reference(state)["rerun_scope"] == "target"
    state["saves"][0]["time"] = -5
    assert reference(state)["rerun_scope"] == "module"


def test_last_matching_scope_rule_decides(episode):
    state = at(episode, 1)
    rules = state["session"]["scope_rules"]
    rules[0], rules[1] = rules[1], rules[0]  # the broad internal/* rule now matches hold.go last
    assert reference(state)["rerun_scope"] == "module"


def test_widest_scope_over_all_writes_after_the_start(episode):
    assert reference(at(episode, 17))["route"] == "wait"  # newest relevant write is one tick old
    state = at(episode, 18)
    assert reference(state)["rerun_scope"] == "module"
    state["saves"] = [row for row in state["saves"] if not (row["file"] == TTL and row["time"] == 15)]
    assert reference(state)["rerun_scope"] == "target"  # only hold.go was written after G42 started
    state = at(episode, 52)
    assert reference(state)["rerun_scope"] == "full"
    state["saves"] = [row for row in state["saves"] if row["file"] != "go.mod"]
    assert reference(state)["rerun_scope"] == "target"
    # The re-vendoring write matches no scope rule: it neither widens the rerun nor restarts save grace.
    state = at(episode, 52)
    vendor = next(row for row in state["saves"] if row["file"] == "vendor/modules.txt")
    assert vendor["time"] == 49
    vendor["time"] = 52
    assert (reference(state)["route"], reference(state)["rerun_scope"]) == ("rerun", "full")


def test_target_failing_again_selects_its_own_frame_not_skips(episode):
    state = at(episode, 4)
    answer = reference(state)
    assert (answer["route"], answer["inspect_file"], answer["target_result"]) == ("inspect", TTL, "different_error")
    # A newly failing retry test would win over the still-failing target and go to the storage team.
    retry = state["runs"][-1]["results"][1]
    retry.update(outcome="FAILED", message="conflict", trace=episode["steps"][42]["state"]["runs"][-1]["results"][1]["trace"])
    assert (reference(state)["route"], reference(state)["owner"]) == ("delegate", "@kv-storage")
    # If it had already failed in G40 it is not new, and the pinned target is selected again.
    state["runs"][0]["results"][1] = deepcopy(retry)
    assert (reference(state)["route"], reference(state)["inspect_file"]) == ("inspect", TTL)


def test_first_compiler_file_not_editor_diagnostics(episode):
    # The language server flags both files right after the ttl.go save; the rerun still comes first.
    assert [row["file"] for row in at(episode, 7)["diagnostics"]] == [TTL, HOLD]
    assert reference(at(episode, 9))["route"] == "rerun"
    state = at(episode, 12)
    assert state["diagnostics"][0]["file"] == TTL
    answer = reference(state)
    assert (answer["route"], answer["inspect_file"], answer["target_result"]) == ("inspect", HOLD, "not_run")
    errors = state["runs"][-1]["compiler_errors"]
    errors.reverse()
    assert reference(state)["inspect_file"] == TTL


def test_only_the_runs_own_output_resets_silence(episode):
    state = at(episode, 25)
    assert reference(state)["process"] == "stalled"
    gopls = next(row for row in state["terminal"] if row["time"] == 23)
    gopls["run"] = "G43"
    assert reference(state)["process"] == "running"
    # Output tagged with another run does not reset silence either.
    state = at(episode, 32)
    state["terminal"].append({"time": 31, "run": "G42", "text": "late log flush"})
    assert reference(state)["control_action"] == "stop"
    state["terminal"][-1]["run"] = "G43"
    answer = reference(state)
    assert (answer["route"], answer["process"]) == ("wait", "running")


def test_stop_outranks_dirty_buffer_and_recent_write(episode):
    state = at(episode, 32)
    assert state["editor"]["dirty_files"] == [HOLD]
    state["saves"].append({"time": 32, "file": HOLD, "diff": "+ // retry"})
    answer = reference(state)
    assert (answer["route"], answer["control_action"]) == ("control", "stop")
    assert reference(at(episode, 31))["route"] == "wait"  # five silent ticks are not enough


def test_interrupted_run_reruns_target_unless_a_write_followed_its_start(episode):
    state = at(episode, 34)
    assert reference(state)["route"] == "wait"  # the unsaved hold.go buffer blocks
    state = at(episode, 35)
    assert (reference(state)["route"], reference(state)["rerun_scope"]) == ("rerun", "target")
    state["saves"].append({"time": 27, "file": HOLD_TEST, "diff": "+ t.Parallel()"})
    assert (reference(state)["route"], reference(state)["rerun_scope"]) == ("rerun", "module")


def test_skips_above_allowance_but_not_at_it(episode):
    state = at(episode, 38)
    assert (reference(state)["route"], reference(state)["rerun_scope"]) == ("rerun", "module")
    state = at(episode, 55)
    assert reference(state)["route"] == "ready"  # one skip equals allowed_skips
    state["runs"][-1]["results"][-1]["outcome"] = "SKIPPED"
    assert (reference(state)["route"], reference(state)["rerun_scope"]) == ("rerun", "module")


def test_write_at_run_start_belongs_to_that_run(episode):
    state = at(episode, 44)
    assert reference(state)["route"] == "delegate"
    save = next(row for row in state["saves"] if row["file"] == HOLD_TEST)
    assert save["time"] == state["runs"][-1]["started"] == 40
    save["time"] = 40.01
    assert (reference(state)["route"], reference(state)["rerun_scope"]) == ("rerun", "module")


def test_owner_is_last_matching_rule_on_last_project_frame(episode):
    state = at(episode, 42)
    assert reference(state)["owner"] == "@kv-storage"
    owners = state["session"]["owners"]
    state["session"]["owners"] = [rule for rule in owners if rule[1] != "@kv-storage"]
    assert reference(state)["owner"] == "@svc-foundation"  # internal/* now matches last
    state = at(episode, 42)
    trace = state["runs"][-1]["results"][1]["trace"]
    state["runs"][-1]["results"][1]["trace"] = [path for path in trace if "kvclient" not in path]
    answer = reference(state)  # vendor and GOROOT frames are skipped; hold.go is our own
    assert (answer["route"], answer["inspect_file"]) == ("inspect", HOLD)


@pytest.mark.parametrize("tick", [42, 43, 44, 45, 46, 47])
def test_non_commitments_leave_delegation_active(episode, tick):
    answer = reference(at(episode, tick))
    assert (answer["route"], answer["owner"]) == ("delegate", "@kv-storage")


def test_every_partial_is_finalized_by_its_speaker(episode):
    call = episode["steps"][-1]["state"]["call"]
    partials = [i for i, row in enumerate(call) if not row["final"]]
    assert partials
    for i in partials:
        final = call[i + 1]
        assert final["final"] and (final["speaker"], final["text"]) == (call[i]["speaker"], call[i]["text"])
        assert final["time"] == call[i]["time"] + 1
    state = at(episode, 47)
    assert state["call"][-1]["final"] is False
    state["call"][-1]["final"] = True  # the same words, once final, end delegation
    assert reference(state)["route"] == "wait"


def test_positive_commitment_must_match_team_run_speaker_and_finality(episode):
    state = at(episode, 48)
    assert reference(state)["route"] == "wait"
    for edit in ({"text": "I have messaged @kv-storage about G44."},
                 {"text": "I have not messaged @kv-storage about G45."},
                 {"text": "I have messaged @svc-foundation about G45."},
                 {"final": False}, {"speaker": "Esme"}):
        changed = deepcopy(state)
        changed["call"][-1].update(edit)
        assert (reference(changed)["route"], reference(changed)["owner"]) == ("delegate", "@kv-storage")


def test_ready_relevance_and_commit(episode):
    state = at(episode, 57)
    assert reference(state)["route"] == "ready"
    state["editor"]["dirty_files"] = ["docs/reservations.md"]
    assert reference(state)["route"] == "ready"
    state["editor"]["dirty_files"] = [TTL]
    assert reference(state)["route"] == "wait"
    state = at(episode, 58)
    assert state["git"]["uncommitted"] == [] and reference(state)["route"] == "wait"
    state["git"]["uncommitted"] = ["go.mod"]
    assert reference(state)["route"] == "ready"


def test_unfinished_results_do_not_replace_finished_badge(episode):
    state = at(episode, 41)
    state["runs"][-1]["results"] = [{"test": "TestHoldExpiresAfterTTL", "outcome": "FAILED",
                                     "message": "reserved after TTL = 12, want 9", "trace": []}]
    answer = reference(state)
    assert (answer["route"], answer["target_result"]) == ("wait", "passed")
    # The streamed PASS line of an interrupted run is not a result either.
    assert reference(at(episode, 21))["target_result"] == "not_run"


def test_module_passes_check_and_leakage_audit(episode):
    assert leakage([episode]) == []
    (summary,) = check_module(debugging_c)["episodes"]
    assert summary["routes_unseen"] == []


def test_scenarios_are_fresh_and_deterministic(episode):
    other = scenarios()
    assert other == [episode]
    other[0]["steps"][0]["state"]["runs"][0]["results"].clear()
    assert episode["steps"][0]["state"]["runs"][0]["results"]
