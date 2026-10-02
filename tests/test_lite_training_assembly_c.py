"""Training variant assembly_c (pump cartridge): decision consequences of observed station events."""

import re
from copy import deepcopy

import pytest

from streamdecisionbench.lite.tasks import assembly as eval_assembly
from streamdecisionbench.lite.tasks.assembly import COMMON_RULES, ROUTES
from streamdecisionbench.lite.training import assembly_c
from streamdecisionbench.lite.training.assembly_c import reference, scenarios
from streamdecisionbench.lite.training.audit import check_module


@pytest.fixture(scope="module")
def episode():
    (only,) = scenarios()
    return only


@pytest.fixture(scope="module")
def steps(episode):
    return episode["steps"]


def gold(steps, tick):
    return steps[tick]["gold"]


def test_scenario_is_public_causal_and_domain_valid(episode):
    assert episode["episode_id"] == "train_assembly_c"
    assert episode["task_family"] == "procedural_coaching"
    assert episode["scenario_id"] == "assembly_c"
    assert episode["tick_seconds"] == 2.0
    assert len(episode["steps"]) == 60
    assert episode["questions"]["route"]["criteria"] == ROUTES
    eval_state = eval_assembly.scenarios()[0]["steps"][0]["state"]
    previous_log = []
    for tick, step in enumerate(episode["steps"]):
        state = step["state"]
        assert step["t"] == tick
        assert set(state) == set(eval_state)
        assert state["clock"] == {"tick": tick}
        assert state["work_instruction"]["rules"][:len(COMMON_RULES)] == COMMON_RULES
        assert state["work_instruction"]["workflow"] == "pump_cartridge"
        log = state["station_log"]
        assert all(event["tick"] <= tick for event in log)
        assert all({"event_id", "tick", "station", "serial", "kind"} <= set(event) for event in log)
        assert log[:len(previous_log)] == previous_log  # cumulative history, never rewritten
        assert [e["tick"] for e in log] == sorted(e["tick"] for e in log)
        assert len({e["event_id"] for e in log}) == len(log)
        previous_log = log
        assert step["gold"] == reference(deepcopy(state))
        assert set(step["gold"]) == set(episode["questions"])
        assert all(value in episode["questions"][qid]["criteria"] for qid, value in step["gold"].items())
        ids = {event["event_id"] for event in log if event["tick"] == tick}
        assert step["evidence"] and set(step["evidence"]) <= ids
        assert not {"gold", "hidden", "answer"} & set(state)


def test_training_check_and_leakage_audit_pass():
    summary = check_module(assembly_c)["episodes"][0]
    assert summary["routes_unseen"] == []
    assert 18 <= summary["decision_transitions"] <= 32  # 23 at present; a loose band so edits stay cheap.
    assert set(summary["answer_values"]["method"]) == {
        "none", "complete_missing", "swap_body", "repress", "replace_bearing", "refit_seal", "locate_leak", "bleed_retest"}


def _runs(text, size=4):
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {" ".join(words[i:i + size]) for i in range(len(words) - size + 1)}


def test_heartbeat_wording_is_new_and_fills_quiet_ticks(steps):
    log = steps[-1]["state"]["station_log"]
    heartbeats = [e for e in log if e["kind"] == "heartbeat"]
    assert heartbeats and {e["message"] for e in heartbeats} == {assembly_c.HEARTBEAT}
    assert {e["tick"] for e in log} == set(range(60))
    eval_heartbeats = {e["message"] for scenario in eval_assembly.scenarios()
                       for e in scenario["steps"][-1]["state"]["station_log"] if e["kind"] == "heartbeat"}
    assert eval_heartbeats
    for message in eval_heartbeats:
        assert not _runs(assembly_c.HEARTBEAT) & _runs(message)


def test_press_before_body_scan_then_transposed_body(steps):
    assert gold(steps, 0)["route"] == "wait"  # No record yet: intake, incomplete, no defect.
    assert gold(steps, 0)["stage"] == "intake"
    # A press before any body scan: intake is a missing earlier stage.
    assert (gold(steps, 1)["route"], gold(steps, 1)["stage"]) == ("repair", "bearing")
    assert (gold(steps, 1)["target"], gold(steps, 1)["method"]) == ("body", "complete_missing")
    assert gold(steps, 2) == gold(steps, 1)  # Speech about skipping the scan does not decide.
    assert (gold(steps, 3)["stage"], gold(steps, 3)["target"], gold(steps, 3)["method"]) == ("intake", "body", "swap_body")
    # The correct body makes the t=1 press obsolete, so the bearing stage is still to do.
    assert (gold(steps, 5)["route"], gold(steps, 5)["next_step"]) == ("advance", "bearing")


def test_bearing_repress_wait_no_read_and_withdrawn_escalation(steps):
    assert (gold(steps, 7)["target"], gold(steps, 7)["method"]) == ("rear_bearing", "repress")
    assert gold(steps, 9)["route"] == "wait"  # Rear passes; front's only reading predates the body scan.
    assert gold(steps, 10) == gold(steps, 9)  # NO_READ is not a scan: nothing becomes obsolete.
    assert (gold(steps, 12)["target"], gold(steps, 12)["method"]) == ("front_bearing", "replace_bearing")
    assert gold(steps, 13) == gold(steps, 12)  # "seated fine, ship it" is speech.
    assert gold(steps, 14)["route"] == "escalate"
    assert (gold(steps, 14)["target"], gold(steps, 14)["destination"]) == ("front_bearing", "hydraulics_lead")
    # A passing press withdraws escalation before any specialist arrives.
    assert (gold(steps, 16)["route"], gold(steps, 16)["next_step"]) == ("advance", "seal")
    assert all(gold(steps, t)["stage"] == "bearing" for t in range(7, 27))


def test_two_tickets_close_in_reverse_order_during_advance(steps):
    assert gold(steps, 18)["route"] == "hold"
    assert gold(steps, 18)["destination"] == "quality_desk"
    assert gold(steps, 22)["route"] == "hold"  # QN-5509 closed, QN-5506 still open.
    assert gold(steps, 23) == gold(steps, 22)  # "carry on" speech does not close a ticket.
    assert gold(steps, 25) == gold(steps, 16)  # Both closed: back to the advance.


def test_accepted_seal_then_ignored_low_confidence_contradiction(steps):
    assert (gold(steps, 27)["stage"], gold(steps, 27)["next_step"]) == ("seal", "pressure")
    assert gold(steps, 29) == gold(steps, 27)  # 0.79 is below the 0.8 threshold.
    assert gold(steps, 30) == gold(steps, 27)


def test_leak_lead_visit_and_ticket_outranking_and_outlasting_badge(steps):
    assert (gold(steps, 32)["target"], gold(steps, 32)["method"]) == ("pressure_decay", "locate_leak")
    assert (gold(steps, 34)["route"], gold(steps, 34)["destination"]) == ("handoff", "hydraulics_lead")
    assert gold(steps, 36) == gold(steps, 34)  # Passing retest while the lead is present.
    assert gold(steps, 38)["route"] == "hold"  # An open ticket outranks the present specialist.
    assert gold(steps, 40)["route"] == "hold"  # The lead leaves; the ticket stays open.
    assert (gold(steps, 41)["route"], gold(steps, 41)["next_step"]) == ("advance", "functional")  # 1.5 kPa endpoint.
    assert all(gold(steps, t)["stage"] == "pressure" for t in range(32, 43))


def test_flow_retest_and_neighbouring_unit_reading(steps):
    assert (gold(steps, 43)["target"], gold(steps, 43)["method"]) == ("flow", "bleed_retest")
    assert gold(steps, 44) == gold(steps, 43)  # A passing flow from another serial does not count.
    assert (gold(steps, 45)["route"], gold(steps, 45)["destination"]) == ("release", "spares_crate")  # 18.5 endpoint.
    assert gold(steps, 46) == gold(steps, 45)  # The recall is speech until a record follows.


def test_post_release_recall_swap_missing_rear_press_and_flipped_seal(steps):
    assert (gold(steps, 48)["route"], gold(steps, 48)["stage"]) == ("wait", "bearing")
    # The swap clears the rear reading; the seal record moves past bearing, so rear is missing.
    assert (gold(steps, 50)["route"], gold(steps, 50)["stage"]) == ("repair", "seal")
    assert (gold(steps, 50)["target"], gold(steps, 50)["method"]) == ("rear_bearing", "complete_missing")
    # Rear passes at its 6.5 kN endpoint; the known seal defect is repaired even from the bearing stage.
    assert (gold(steps, 52)["stage"], gold(steps, 52)["target"], gold(steps, 52)["method"]) == ("bearing", "seal", "refit_seal")
    assert (gold(steps, 54)["route"], gold(steps, 54)["next_step"]) == ("advance", "pressure")  # Old leak test obsolete.
    assert gold(steps, 55) == gold(steps, 54)  # Another station's leak test.
    assert gold(steps, 57)["next_step"] == "functional"  # The t=45 flow test is now obsolete.
    assert gold(steps, 59)["route"] == "release"


def test_counterfactual_without_rear_swap_old_reading_still_counts(steps):
    state = deepcopy(steps[50]["state"])
    state["station_log"] = [e for e in state["station_log"] if e["kind"] != "bearing_swap"]
    result = reference(state)
    assert (result["route"], result["target"], result["method"]) == ("repair", "seal", "refit_seal")


def test_counterfactual_current_failing_rear_press_is_a_defect_not_missing(steps):
    state = deepcopy(steps[50]["state"])
    seal = state["station_log"].pop()
    state["station_log"].append({**seal, "event_id": "cf-49", "tick": 49, "kind": "press",
                                 "target": "rear_bearing", "value": 5.2, "confidence": 1.0})
    state["station_log"].append(seal)
    result = reference(state)
    assert (result["route"], result["target"], result["method"]) == ("repair", "rear_bearing", "repress")


@pytest.mark.parametrize("value", [3.55, 4.45])
def test_counterfactual_failing_latest_press_keeps_escalation(steps, value):
    state = deepcopy(steps[16]["state"])
    state["station_log"][-1]["value"] = value
    result = reference(state)
    assert (result["route"], result["target"]) == ("escalate", "front_bearing")


def test_counterfactual_confidence_threshold_is_inclusive(steps):
    state = deepcopy(steps[29]["state"])
    state["station_log"][-1]["confidence"] = 0.8
    result = reference(state)
    assert (result["route"], result["stage"], result["target"], result["method"]) == ("repair", "seal", "seal", "refit_seal")


def test_counterfactual_without_lead_retest_leak_failure_returns(steps):
    state = deepcopy(steps[41]["state"])
    state["station_log"] = [e for e in state["station_log"] if not (e["kind"] == "pressure_decay" and e["tick"] == 36)]
    result = reference(state)
    assert (result["route"], result["target"], result["method"]) == ("repair", "pressure_decay", "locate_leak")


def test_counterfactual_readable_body_scan_obsoletes_bearing_readings(steps):
    state = deepcopy(steps[10]["state"])
    state["station_log"][-1]["code"] = "PB-46S"
    result = reference(state)
    assert (result["route"], result["stage"], result["next_step"]) == ("advance", "intake", "bearing")


def test_counterfactual_simultaneous_failures_follow_target_order(steps):
    state = deepcopy(steps[14]["state"])
    press = {e["tick"]: e for e in state["station_log"] if e["kind"] == "press"}
    press[9]["value"] = 6.9
    result = reference(state)  # Both bearings now have two current failures: front comes first.
    assert (result["route"], result["target"]) == ("escalate", "front_bearing")
    press[12]["value"] = 4.2
    result = reference(state)  # Only rear fails twice (5.3, 6.9): its escalation outranks front's repair.
    assert (result["route"], result["target"]) == ("escalate", "rear_bearing")
    press[7]["value"] = 6.0
    result = reference(state)  # One failure each: both are defects, front comes first in target order.
    assert (result["route"], result["target"], result["method"]) == ("repair", "front_bearing", "replace_bearing")


def test_public_order_changes_reference_but_private_fields_and_clock_do_not(steps):
    state = deepcopy(steps[3]["state"])
    assert reference(state)["method"] == "swap_body"
    state["order"]["body_code"] = "PB-64S"
    assert reference(state)["route"] == "advance"
    state["gold"] = {"route": "repair"}
    state["hidden"] = {"desired_route": "repair"}
    state["clock"] = {"tick": 59}
    assert reference(state)["route"] == "advance"


def test_fan_out_excludes_unused_fields_but_retains_wrong_route(episode):
    specification = episode["decision_spec"]

    def application(answer):
        names = ["route", *specification["always"], *specification["branches"][answer["route"]]]
        return tuple((name, answer[name]) for name in names)

    answer = deepcopy(episode["steps"][38]["gold"])
    changed = {**answer, "method": "locate_leak", "target": "pressure_decay", "next_step": "functional"}
    assert application(changed) == application(answer)
    changed["route"] = "handoff"
    assert application(changed) != application(answer)
