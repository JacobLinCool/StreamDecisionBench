"""Decision consequences of observed assembly events, independent of model output."""

from copy import deepcopy

import pytest

from streamdecisionbench.lite.tasks.assembly import reference, scenarios


@pytest.fixture(scope="module")
def episodes():
    return scenarios()


def test_scenarios_are_public_causal_and_domain_valid(episodes):
    assert len(episodes) == 2
    for episode in episodes:
        assert len(episode["steps"]) == 60
        assert episode["tick_seconds"] == 2.0
        for tick, step in enumerate(episode["steps"]):
            assert step["t"] == tick
            assert step["state"]["clock"] == {"tick": tick}
            assert all(event["tick"] <= tick for event in step["state"]["station_log"])
            assert step["gold"] == reference(deepcopy(step["state"]))
            assert set(step["gold"]) == set(episode["questions"])
            assert all(value in episode["questions"][qid]["criteria"] for qid, value in step["gold"].items())
            ids = {event["event_id"] for event in step["state"]["station_log"] if event["tick"] == tick}
            assert set(step["evidence"]) <= ids


def test_second_failure_handoff_and_two_ticket_precedence(episodes):
    steps = episodes[0]["steps"]
    assert steps[10]["gold"]["method"] == "retorque"
    assert steps[16]["gold"]["route"] == "escalate"
    assert steps[16]["gold"]["target"] == "J2"
    assert steps[18]["gold"] == steps[16]["gold"]  # Speech is not a badge.
    assert steps[19]["gold"]["route"] == "handoff"
    assert steps[21]["gold"]["route"] == "hold"
    assert steps[24]["gold"]["route"] == "hold"  # Q72 remains open.
    assert steps[25]["gold"]["route"] == "handoff"
    assert steps[31]["gold"]["route"] == "advance"
    assert steps[31]["gold"]["next_step"] == "inspection"


def test_inclusive_bounds_replacement_and_reinspection(episodes):
    steps = episodes[0]["steps"]
    assert steps[8]["gold"]["route"] == "wait"  # J1=9.2 passes; J2 absent.
    assert steps[33]["gold"]["route"] == "release"  # J2=26.0 passes.
    assert steps[45]["gold"]["method"] == "replace_fastener"
    assert steps[47]["gold"]["route"] == "wait"  # Old result no longer counts.
    assert steps[49]["gold"]["next_step"] == "inspection"  # J1=10.8 passes.
    assert steps[51]["gold"]["method"] == "reinspect"
    assert steps[53]["gold"]["route"] == "release"


def test_unreliable_observation_other_units_and_no_read_do_not_erase(episodes):
    steps = episodes[0]["steps"]
    assert steps[35]["gold"] == steps[33]["gold"]
    assert steps[37]["gold"]["target"] == "gasket"
    assert steps[37]["gold"]["stage"] == "seal"
    assert steps[43]["gold"] == steps[41]["gold"]
    assert steps[55]["gold"] == steps[53]["gold"]
    assert steps[57]["gold"] == steps[53]["gold"]


def test_rework_invalidates_downstream_evidence_without_erasing_records(episodes):
    steps = episodes[1]["steps"]
    assert steps[36]["gold"]["route"] == "release"
    assert steps[38]["gold"]["next_step"] == "electrical"
    assert steps[40]["gold"]["route"] == "repair"
    assert steps[40]["gold"]["target"] == "continuity"
    assert steps[40]["gold"]["method"] == "complete_missing"
    assert steps[42]["gold"]["route"] == "wait"  # Insulation still obsolete.
    assert steps[44]["gold"]["target"] == "insulation"
    assert steps[46]["gold"]["next_step"] == "label"  # Exactly 20 MOhm passes.
    assert steps[48]["gold"]["route"] == "wait"  # Old kit count must be refreshed.
    assert steps[50]["gold"]["destination"] == "validation_rack"


def test_minimal_current_measurement_withdraws_repeated_failure(episodes):
    state = deepcopy(episodes[0]["steps"][16]["state"])
    # Change only the newest numeric reading: earlier failure persists, but the
    # latest passing measurement removes both the fault and its escalation.
    state["station_log"][-1]["value"] = 24.0
    result = reference(state)
    assert result["route"] == "advance"
    assert result["next_step"] == "inspection"
    assert result["target"] == "none"


def test_changing_public_order_changes_reference_without_gold_or_private_state(episodes):
    state = deepcopy(episodes[1]["steps"][2]["state"])
    assert reference(state)["method"] == "reseat"
    state["order"]["key_position"] = "north"
    assert reference(state)["route"] == "advance"
    state["gold"] = {"route": "repair"}
    state["hidden"] = {"desired_route": "repair"}
    assert reference(state)["route"] == "advance"


def test_simultaneous_failures_select_earliest_target(episodes):
    state = deepcopy(episodes[0]["steps"][10]["state"])
    first_joint = next(e for e in state["station_log"] if e["kind"] == "rundown" and e["target"] == "J1")
    first_joint["value"] = 11.5
    result = reference(state)
    assert result["route"] == "repair"
    assert (result["target"], result["method"]) == ("J1", "replace_fastener")


def test_fan_out_excludes_unused_fields_but_retains_wrong_route(episodes):
    specification = episodes[0]["decision_spec"]

    def application(answer):
        route = answer["route"]
        names = ["route", *specification["always"], *specification["branches"][route]]
        return tuple((name, answer[name]) for name in names)

    answer = deepcopy(episodes[0]["steps"][21]["gold"])
    changed = {**answer, "method": "retorque", "target": "J1", "next_step": "seal"}
    assert application(changed) == application(answer)
    changed["route"] = "handoff"
    assert application(changed) != application(answer)
