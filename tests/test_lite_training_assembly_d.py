"""Training variant assembly_d (e-bike battery pack): decision consequences of public station records."""

from copy import deepcopy

import pytest

from streamdecisionbench.lite.core import compose, encode_scenario, validate_episode
from streamdecisionbench.lite.tasks.assembly import COMMON_RULES, ROUTES
from streamdecisionbench.lite.training.assembly_d import reference, scenarios
from streamdecisionbench.lite.training.audit import leakage


@pytest.fixture(scope="module")
def episode():
    (only,) = scenarios()
    return only


def decision(episode, t):
    return compose(episode["decision_spec"], episode["steps"][t]["gold"])


def state_at(episode, t):
    return deepcopy(episode["steps"][t]["state"])


def record(state, tick, kind, **match):
    """The unique log record at a tick with the given kind and field values."""
    (found,) = [e for e in state["station_log"]
                if e["tick"] == tick and e["kind"] == kind and all(e.get(k) == v for k, v in match.items())]
    return found


def test_scenario_is_public_causal_and_domain_valid(episode):
    assert episode["episode_id"] == "train_assembly_d"
    assert episode["task_family"] == "procedural_coaching"
    assert episode["tick_seconds"] == 2.0
    assert len(episode["steps"]) == 60
    assert set(episode["questions"]["route"]["criteria"]) == set(ROUTES)
    previous_log = []
    for tick, step in enumerate(episode["steps"]):
        state = step["state"]
        assert step["t"] == tick
        assert set(state) == {"station", "clock", "order", "work_instruction", "station_log"}
        assert state["clock"] == {"tick": tick}
        assert state["work_instruction"]["workflow"] == "battery_pack"
        assert state["work_instruction"]["rules"][:len(COMMON_RULES)] == COMMON_RULES
        assert all(event["tick"] <= tick for event in state["station_log"])
        # Logs are cumulative: every earlier record stays, unchanged and in order.
        assert state["station_log"][:len(previous_log)] == previous_log
        previous_log = state["station_log"]
        assert all({"event_id", "tick", "station", "serial", "kind"} <= set(event) for event in state["station_log"])
        assert step["gold"] == reference(deepcopy(state))
        assert set(step["gold"]) == set(episode["questions"])
        assert all(value in episode["questions"][qid]["criteria"] for qid, value in step["gold"].items())
        ids = {event["event_id"] for event in state["station_log"] if event["tick"] == tick}
        assert ids and step["evidence"] and set(step["evidence"]) <= ids
    event_ids = [event["event_id"] for event in previous_log]
    assert len(event_ids) == len(set(event_ids))
    # Only camera seal-tape counts carry a confidence.
    assert all(event["kind"] == "tape_count" for event in previous_log if "confidence" in event)


def test_encodes_validates_covers_every_route_and_method_and_shares_no_evaluation_content(episode):
    summary = validate_episode(encode_scenario(episode))
    assert summary["routes_unseen"] == []
    assert 20 <= summary["decision_transitions"] <= 28
    methods = {step["gold"]["method"] for step in episode["steps"]}
    assert methods == set(episode["questions"]["method"]["criteria"])
    targets = {step["gold"]["target"] for step in episode["steps"]}
    assert targets == set(episode["questions"]["target"]["criteria"])
    assert leakage([episode]) == []


def test_early_flash_counts_once_the_carrier_is_right(episode):
    # The board is flashed before any carrier scan: intake is a missing earlier stage.
    assert decision(episode, 0) == {"route": "repair", "stage": "firmware", "target": "carrier", "method": "complete_missing"}
    assert episode["steps"][1]["gold"] == episode["steps"][0]["gold"]  # Speech.
    assert decision(episode, 2) == {"route": "repair", "stage": "intake", "target": "carrier", "method": "swap_carrier"}
    # No other record invalidates a flash, so firmware is already complete and weld is next.
    assert decision(episode, 4) == {"route": "advance", "stage": "intake", "next_step": "weld"}


def test_weld_escalation_is_withdrawn_by_a_passing_remeasurement(episode):
    steps = episode["steps"]
    assert decision(episode, 6) == {"route": "wait", "stage": "weld"}  # Probe moves the stage only.
    assert decision(episode, 7) == {"route": "repair", "stage": "weld", "target": "W1", "method": "inspect_weld"}
    assert decision(episode, 9) == {"route": "escalate", "stage": "weld", "target": "W1", "destination": "battery_lead"}
    assert decision(episode, 12) == {"route": "handoff", "stage": "weld", "destination": "battery_lead"}
    assert all(steps[t]["gold"] == steps[12]["gold"] for t in range(13, 17))  # The present lead dominates.
    # W1's two older failures remain, but its latest reading passes; W2 passes at 0.30.
    assert decision(episode, 17) == {"route": "advance", "stage": "weld", "next_step": "isolation"}


def test_lower_endpoint_and_lead_presence_counterfactuals(episode):
    state = state_at(episode, 17)
    record(state, 16, "tab_resistance", target="W2")["value"] = 0.29
    result = reference(state)  # With the t15 failure, 0.29 would be W2's second miss.
    assert (result["route"], result["target"], result["destination"]) == ("escalate", "W2", "battery_lead")
    state = state_at(episode, 16)
    state["station_log"] = [e for e in state["station_log"] if e["kind"] != "badge"]
    assert reference(state)["route"] == "advance"  # Without the lead, no escalation survives W1=0.28.


def test_repeated_isolation_failures_stay_repairs_under_a_ticket(episode):
    steps = episode["steps"]
    assert decision(episode, 19) == {"route": "repair", "stage": "isolation", "target": "isolation", "method": "replace_insulator"}
    # A second isolation failure is still a repair: only W1 and W2 can escalate.
    assert steps[21]["gold"] == steps[19]["gold"]
    # The ticket opens while no lead is badged in.
    assert decision(episode, 22) == {"route": "hold", "stage": "isolation", "destination": "quality_desk"}
    assert steps[24]["gold"] == steps[22]["gold"]  # A passing reading cannot lift the hold.
    assert decision(episode, 26) == {"route": "advance", "stage": "isolation", "next_step": "pack"}


def test_pack_check_reopened_ticket_and_other_station_badge(episode):
    steps = episode["steps"]
    assert steps[28]["gold"] == steps[27]["gold"]  # Camera count at 0.57 has no effect.
    state = state_at(episode, 28)
    record(state, 28, "tape_count")["confidence"] = 0.8
    assert (reference(state)["route"], reference(state)["method"]) == ("repair", "correct_tape")
    assert decision(episode, 29) == {"route": "wait", "stage": "pack"}
    assert decision(episode, 31) == {"route": "repair", "stage": "pack", "target": "label", "method": "relabel"}
    assert decision(episode, 33) == {"route": "release", "stage": "pack", "destination": "aging_rack"}
    assert steps[34]["gold"] == steps[33]["gold"]  # Speech about reopening is not a ticket record.
    # The latest record of the same ticket identifier reopens it.
    assert decision(episode, 35) == {"route": "hold", "stage": "pack", "destination": "quality_desk"}
    assert steps[37]["gold"] == steps[33]["gold"]
    assert steps[38]["gold"] == steps[37]["gold"]  # Badge at another station, for another pack.
    state = state_at(episode, 38)
    badge = record(state, 38, "badge")
    badge.update(station=state["station"], serial=state["order"]["serial"])
    assert reference(state)["route"] == "handoff"


def test_no_read_after_a_correct_scan_neither_counts_nor_erases(episode):
    steps = episode["steps"]
    assert steps[39]["gold"] == steps[40]["gold"] == steps[37]["gold"]
    state = state_at(episode, 40)
    record(state, 40, "scan", target="carrier")["code"] = "HC-00X"  # As if it were a readable wrong carrier.
    result = reference(state)
    assert (result["stage"], result["target"], result["method"]) == ("intake", "carrier", "swap_carrier")


def test_carrier_reseat_voids_welds_and_missing_targets_are_taken_in_order(episode):
    assert decision(episode, 41) == {"route": "advance", "stage": "intake", "next_step": "weld"}
    # A fresh isolation reading cannot stand in for the voided welds: W1 comes first.
    assert decision(episode, 43) == {"route": "repair", "stage": "isolation", "target": "W1", "method": "complete_missing"}
    # Weld is now the current stage, so W2 still missing is not a defect.
    assert decision(episode, 45) == {"route": "wait", "stage": "weld"}
    # Missing W2 (weld) outranks the known firmware defect from the wrong-version flash.
    assert decision(episode, 46) == {"route": "repair", "stage": "firmware", "target": "W2", "method": "complete_missing"}
    # Only one W2 failure since the reseat: repair, not escalate.
    assert decision(episode, 48) == {"route": "repair", "stage": "weld", "target": "W2", "method": "reweld"}
    # The tab replacement removes the failing W2 reading, leaving the firmware defect first.
    assert decision(episode, 50) == {"route": "repair", "stage": "weld", "target": "bms", "method": "reflash"}
    assert episode["steps"][52]["gold"] == episode["steps"][50]["gold"]  # W2 = 0.45 passes at the upper endpoint.
    assert decision(episode, 54) == {"route": "advance", "stage": "firmware", "next_step": "isolation"}
    assert decision(episode, 55) == {"route": "advance", "stage": "isolation", "next_step": "pack"}  # 50.0 passes.
    # A probe contact moves the stage back but does not outdate isolation.
    assert decision(episode, 56) == {"route": "advance", "stage": "weld", "next_step": "pack"}


def test_without_the_reseat_old_readings_and_failures_still_count(episode):
    state = state_at(episode, 43)
    state["station_log"] = [e for e in state["station_log"] if not (e["tick"] == 41 and e["kind"] == "scan")]
    assert compose(episode["decision_spec"], reference(state)) == {"route": "advance", "stage": "isolation", "next_step": "pack"}
    state = state_at(episode, 48)
    state["station_log"] = [e for e in state["station_log"] if not (e["tick"] == 41 and e["kind"] == "scan")]
    result = reference(state)  # The t15 failure would count again with the t48 failure.
    assert (result["route"], result["target"], result["destination"]) == ("escalate", "W2", "battery_lead")


def test_endpoint_and_probe_counterfactuals(episode):
    state = state_at(episode, 52)
    record(state, 52, "tab_resistance", target="W2")["value"] = 0.46
    assert (reference(state)["target"], reference(state)["method"]) == ("W2", "reweld")
    state = state_at(episode, 55)
    record(state, 55, "isolation")["value"] = 49.9
    assert (reference(state)["target"], reference(state)["method"]) == ("isolation", "replace_insulator")
    state = state_at(episode, 56)
    record(state, 56, "probe").update(kind="tab_resistance", value=0.40)  # A real reading does outdate isolation.
    result = reference(state)
    assert (result["route"], result["next_step"]) == ("advance", "isolation")


def test_stale_pack_records_are_missing_not_incorrect(episode):
    state = state_at(episode, 55)
    record(state, 33, "scan", target="label")["code"] = "EB-6042"
    record(state, 29, "tape_count")["value"] = 5
    assert compose(episode["decision_spec"], reference(state)) == {"route": "advance", "stage": "isolation", "next_step": "pack"}


def test_final_pack_check_boundary_confidence_and_neighbour_count(episode):
    steps = episode["steps"]
    # Confidence exactly 0.80 is not below the cut-off, so the wrong count applies.
    assert decision(episode, 57) == {"route": "repair", "stage": "pack", "target": "seal_tape", "method": "correct_tape"}
    assert steps[58]["gold"] == steps[57]["gold"]  # The neighbouring pack's count.
    state = state_at(episode, 58)
    record(state, 58, "tape_count")["serial"] = state["order"]["serial"]
    assert reference(state)["route"] == "release"
    assert decision(episode, 59) == {"route": "release", "stage": "pack", "destination": "aging_rack"}


def test_public_order_and_private_fields(episode):
    state = state_at(episode, 50)
    state["order"]["firmware_version"] = "2.3.9"
    assert compose(episode["decision_spec"], reference(state)) == {"route": "wait", "stage": "weld"}
    state = state_at(episode, 33)
    state["gold"] = {"route": "hold"}
    state["hidden"] = {"desired_route": "hold"}
    assert reference(state)["route"] == "release"


def test_fan_out_excludes_unused_fields_but_retains_wrong_route(episode):
    specification = episode["decision_spec"]
    answer = deepcopy(episode["steps"][22]["gold"])
    changed = {**answer, "method": "replace_insulator", "target": "isolation", "next_step": "pack"}
    assert compose(specification, changed) == compose(specification, answer)
    changed["route"] = "repair"
    assert compose(specification, changed) != compose(specification, answer)
