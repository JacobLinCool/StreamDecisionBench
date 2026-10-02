"""Public-evidence checks and counterfactuals for the training variant support_d (energy account desk)."""

from copy import deepcopy

import pytest

from streamdecisionbench.lite.core import compose, encode_scenario, validate_episode
from streamdecisionbench.lite.training.audit import leakage
from streamdecisionbench.lite.training.support_d import reference, scenarios

SPEAKERS = {"Customer", "Agent", "Background"}
UTTERANCE_KEYS = {"utterance_id", "at", "speaker", "text", "final"}


@pytest.fixture(scope="module")
def episode():
    (only,) = scenarios()
    return only


def _gold(episode, tick):
    return episode["steps"][tick]["gold"]


def _decision(episode, tick):
    return compose(episode["decision_spec"], _gold(episode, tick))


def _state(episode, tick):
    return deepcopy(episode["steps"][tick]["state"])


def _add(state, text, *, speaker="Customer", final=True):
    state["clock"]["now"] += 0.1
    state["transcript"].append({"utterance_id": "counterfactual", "at": state["clock"]["now"],
                                "speaker": speaker, "final": final, "text": text})


def test_schema_and_public_reference(episode):
    assert episode["episode_id"] == "train_support_d"
    assert episode["task_family"] == "support_call_assist"
    assert episode["scenario_id"] == "support_d"
    assert len(episode["questions"]) == 8
    assert len(episode["steps"]) == 60
    assert episode["tick_seconds"] == 2.0
    spec = episode["decision_spec"]
    for tick, step in enumerate(episode["steps"]):
        state = step["state"]
        assert step["t"] == tick
        assert step["evidence"] and all(isinstance(e, str) and e for e in step["evidence"])
        assert state["workflow"] == "energy_account"
        assert state["clock"]["now"] == tick
        assert {"gold", "t", "hidden", "answer"}.isdisjoint(state)
        assert reference(deepcopy(state)) == step["gold"]
        assert state["telephony"]["since"] <= tick
        terms = state["desktop"]["plan"]["terms_read_at"]
        assert terms is None or terms <= tick
        for line in state["transcript"]:
            assert set(line) == UTTERANCE_KEYS
            assert line["speaker"] in SPEAKERS
            assert line["at"] <= tick
        for question, value in step["gold"].items():
            assert value in episode["questions"][question]["criteria"]
        active = {spec["route_question"], *spec["always"], *spec["branches"][step["gold"]["route"]]}
        assert all(value == "none" for key, value in step["gold"].items() if key not in active)


def test_rules_are_published_and_constant(episode):
    first = episode["steps"][0]["state"]["prepared"]
    assert first["hold_check_ticks"] == 4
    assert first["deployment"] and len(first["rules"]) >= 8
    for step in episode["steps"]:
        assert step["state"]["prepared"] == first


def test_transcript_is_cumulative_and_finals_replace_partials(episode):
    previous = {}
    for step in episode["steps"]:
        lines = {u["utterance_id"]: u for u in step["state"]["transcript"]}
        assert len(lines) == len(step["state"]["transcript"])
        for uid, old in previous.items():
            assert uid in lines
            if old["final"]:
                assert lines[uid] == old
            else:
                assert lines[uid]["at"] == old["at"]
        previous = lines
    revised = {u["utterance_id"]: u for u in episode["steps"][59]["state"]["transcript"]}
    assert revised["gas-change"]["final"] and revised["gas-change"]["at"] == 9
    assert revised["count-change"]["final"] and revised["count-change"]["at"] == 25
    assert revised["register-again"]["final"] and revised["register-again"]["at"] == 52
    finals = [u["at"] for u in revised.values() if u["speaker"] == "Customer" and u["final"]]
    assert len(finals) == len(set(finals))


def test_encoded_episode_has_rich_dynamics_and_no_leakage(episode):
    summary = validate_episode(encode_scenario(episode))
    assert summary["decision_transitions"] == 31
    assert summary["routes_unseen"] == []
    assert leakage([episode]) == []


def test_meter_action_follows_tool_not_speech(episode):
    assert [_gold(episode, t)["meter_action"] for t in (0, 2, 3, 4, 5, 7, 8)] == [
        "take_reading", "take_reading", "await_check", "await_check", "confirm_digits", "confirm_digits",
        "confirm_bill"]
    assert _gold(episode, 8)["meter_target"] == "electricity"
    state = _state(episode, 5)
    state["desktop"]["meter_reads"]["gas"]["status"] = "accepted"
    assert reference(state)["meter_action"] == "confirm_digits"


def test_gas_request_switches_meter_and_uses_only_the_gas_record(episode):
    assert [_gold(episode, t)["meter_target"] for t in (0, 10, 11, 12, 13)] == [
        "electricity", "electricity", "gas", "gas", "gas"]
    assert _decision(episode, 11) == {"route": "meter", "priority_register": "none",
                                      "meter_target": "gas", "meter_action": "take_reading"}
    assert episode["steps"][11]["state"]["desktop"]["meter_reads"]["electricity"]["status"] == "accepted"
    assert _decision(episode, 13) == {"route": "meter", "priority_register": "register",
                                      "meter_target": "gas", "meter_action": "await_check"}
    state = _state(episode, 13)
    state["desktop"]["meter_reads"]["electricity"]["status"] = "implausible"
    assert reference(state)["meter_action"] == "await_check"
    _add(state, "Sorry, submit my electricity reading again instead.")
    assert reference(state)["meter_target"] == "electricity"
    assert reference(state)["meter_action"] == "confirm_digits"


def test_partial_gas_request_finalised_as_refusal(episode):
    assert _decision(episode, 9) == _decision(episode, 8)
    assert _decision(episode, 10) == _decision(episode, 8)
    assert _decision(episode, 11)["meter_target"] == "gas"
    state = _state(episode, 9)
    partial = next(u for u in state["transcript"] if u["utterance_id"] == "gas-change")
    partial["final"] = True
    changed = reference(state)
    assert changed["meter_target"] == "gas"
    assert changed["meter_action"] == "take_reading"


def test_plan_stages_in_priority_order(episode):
    stages = {t: (_gold(episode, t)["plan_stage"], _gold(episode, t)["instalments"])
              for t in (14, 15, 16, 17, 19, 20, 21, 23, 25, 26, 27)}
    assert stages == {14: ("await_eligibility", "unknown"), 15: ("await_eligibility", "unknown"),
                      16: ("explain_ineligible", "unknown"), 17: ("read_terms", "unknown"),
                      19: ("ask_consent", "unknown"), 20: ("ask_consent", "unknown"),
                      21: ("ask_count", "unknown"), 23: ("set_up", "six"), 25: ("set_up", "six"),
                      26: ("set_up", "twelve"), 27: ("ask_consent", "twelve")}
    state = _state(episode, 25)
    next(u for u in state["transcript"] if u["utterance_id"] == "count-change")["final"] = True
    assert (reference(state)["plan_stage"], reference(state)["instalments"]) == ("set_up", "three")
    state = _state(episode, 23)
    state["desktop"]["account"]["plan_eligibility"] = "ineligible"
    assert reference(state)["plan_stage"] == "explain_ineligible"
    state["desktop"]["plan"]["status"] = "active"
    assert reference(state)["plan_stage"] == "confirm_active"


def test_agreement_must_follow_latest_terms_reading(episode):
    state = _state(episode, 17)
    _add(state, "I agree to the plan terms.")
    assert reference(state)["plan_stage"] == "read_terms"
    state["desktop"]["plan"]["terms_read_at"] = 18
    assert reference(state)["plan_stage"] == "ask_consent"
    state["desktop"]["plan"]["terms_read_at"] = state["clock"]["now"]
    assert reference(state)["plan_stage"] == "ask_count"
    state = _state(episode, 26)
    state["desktop"]["plan"]["terms_read_at"] = 26
    assert reference(state)["plan_stage"] == "ask_consent"


def test_revised_agreement_keeps_its_at_and_can_be_stale(episode):
    state = _state(episode, 18)
    state["transcript"].append({"utterance_id": "early-yes", "at": 18, "speaker": "Customer", "final": False,
                                "text": "I agree to the plan terms"})
    assert reference(state)["plan_stage"] == "read_terms"
    state = _state(episode, 19)
    state["transcript"].append({"utterance_id": "early-yes", "at": 18, "speaker": "Customer", "final": True,
                                "text": "I agree to the plan terms."})
    assert state["desktop"]["plan"]["terms_read_at"] == 19
    assert reference(state)["plan_stage"] == "ask_consent"
    state["transcript"][-1]["at"] = 19
    assert reference(state)["plan_stage"] == "ask_count"


def test_agreement_withdrawn_and_regranted(episode):
    assert _gold(episode, 42)["plan_stage"] == "ask_consent"
    assert _gold(episode, 44)["plan_stage"] == "set_up"
    assert _gold(episode, 45)["plan_stage"] == "ask_consent"
    assert _decision(episode, 51) == {"route": "plan", "priority_register": "none",
                                      "plan_stage": "ask_consent", "instalments": "twelve"}
    assert _gold(episode, 54)["plan_stage"] == "set_up"
    assert _gold(episode, 55)["plan_stage"] == "set_up"
    assert _gold(episode, 56)["plan_stage"] == "confirm_active"


def test_outage_estimate_equality_and_site_specific_map(episode):
    assert _decision(episode, 28) == {"route": "outage", "priority_register": "register",
                                      "outage_site": "cottage", "outage_action": "log_report"}
    assert [_gold(episode, t)["outage_action"] for t in (34, 36, 37, 38, 39, 40)] == [
        "share_estimate", "share_estimate", "share_estimate", "escalate_overdue", "escalate_overdue",
        "confirm_restored"]
    assert _gold(episode, 36)["outage_site"] == "cottage"
    state = _state(episode, 37)
    state["desktop"]["outage_map"]["cottage"]["estimated_restore_at"] = 37
    assert reference(state)["outage_action"] == "escalate_overdue"
    state = _state(episode, 38)
    state["desktop"]["outage_map"]["home"]["status"] = "restored"
    state["desktop"]["area_notices"].append("Cottage lane: supply restored.")
    assert reference(state)["outage_action"] == "escalate_overdue"


def test_home_report_uses_only_the_home_map_entry(episode):
    assert [_gold(episode, t)["outage_site"] for t in (28, 36, 40, 41, 42)] == [
        "cottage", "cottage", "cottage", "home", "none"]
    assert _decision(episode, 41) == {"route": "outage", "priority_register": "register",
                                      "outage_site": "home", "outage_action": "log_report"}
    state = _state(episode, 41)
    assert state["desktop"]["outage_map"]["cottage"]["status"] == "restored"
    state["desktop"]["outage_map"]["home"] = {"status": "outage", "estimated_restore_at": 45}
    assert reference(state)["outage_action"] == "share_estimate"
    state["desktop"]["outage_map"]["home"]["estimated_restore_at"] = 41
    assert reference(state)["outage_action"] == "escalate_overdue"


def test_holds_use_clock_including_equality_and_resume_request(episode):
    assert [_gold(episode, t)["route"] for t in (29, 30, 33, 34)] == ["outage", "hold_wait", "hold_wait", "outage"]
    assert [_gold(episode, t)["route"] for t in (45, 46, 49, 50, 51)] == [
        "plan", "hold_wait", "hold_wait", "hold_return", "plan"]
    state = _state(episode, 49)
    state["clock"]["now"] = 49.999
    assert reference(state)["route"] == "hold_wait"
    state["clock"]["now"] = 50
    assert reference(state)["route"] == "hold_return"
    state = _state(episode, 33)
    _add(state, "Please set up an instalment plan instead.")
    assert reference(state)["route"] == "hold_wait"
    state["telephony"] = {"status": "connected", "since": state["clock"]["now"]}
    assert reference(state)["route"] == "plan"


def test_register_changes_during_hold_without_changing_route(episode):
    state = _state(episode, 47)
    assert reference(state)["route"] == "hold_wait"
    assert reference(state)["priority_register"] == "none"
    _add(state, "While I wait, add me to the priority services register.")
    assert reference(state) == {**_gold(episode, 47), "priority_register": "register"}


def test_register_toggles_and_persists_after_call_ends(episode):
    assert [_gold(episode, t)["priority_register"] for t in (11, 12, 24, 42, 43, 52, 53, 57, 59)] == [
        "none", "register", "register", "register", "none", "none", "register", "register", "register"]
    assert _decision(episode, 59) == {"route": "closed", "priority_register": "register"}
    state = _state(episode, 59)
    _add(state, "Take me off the priority services register.", speaker="Background")
    assert reference(state)["priority_register"] == "register"
    _add(state, "Please take me off the priority services register.")
    assert reference(state)["priority_register"] == "none"


@pytest.mark.parametrize("speaker", ["Agent", "Background"])
def test_other_speakers_cannot_request_agree_or_register(episode, speaker):
    for tick in (8, 19, 38, 42, 47):
        state = _state(episode, tick)
        expected = reference(state)
        _add(state, "Report a power cut at home. I agree to the plan terms. "
                    "Take me off the priority services register.", speaker=speaker)
        assert reference(state) == expected


def test_quoted_and_refused_phrases_do_not_count(episode):
    state = _state(episode, 34)
    expected = reference(state)
    _add(state, 'The leaflet says "report a power cut at home" in big letters. '
                "Do not report a power cut at home; it is only the cottage.")
    assert reference(state) == expected
    state = _state(episode, 20)
    _add(state, "Please don't take me off the priority services register.")
    assert reference(state)["priority_register"] == "register"


def test_only_published_refusal_words_refuse(episode):
    state = _state(episode, 8)
    _add(state, 'Why not "officially" submit my gas reading today?')
    assert reference(state)["meter_target"] == "gas"
    state = _state(episode, 8)
    _add(state, "I won't submit my gas reading until the key turns up.")
    assert reference(state)["meter_target"] == "gas"
    state = _state(episode, 8)
    _add(state, "Never submit my gas reading without me.")
    assert reference(state) == _gold(episode, 8)


def test_last_phrase_in_one_utterance_counts(episode):
    state = _state(episode, 12)
    _add(state, "Submit my gas reading later; first set up an instalment plan.")
    changed = reference(state)
    assert changed["route"] == "plan"
    _add(state, "Back to the instalment plan, then submit my electricity reading.")
    changed = reference(state)
    assert changed["route"] == "meter"
    assert changed["meter_target"] == "electricity"
    assert changed["meter_action"] == "confirm_bill"


def test_reference_is_pure_and_unknown_workflow_fails(episode):
    state = _state(episode, 41)
    before = deepcopy(state)
    reference(state)
    assert state == before
    state["workflow"] = "payment_support"
    with pytest.raises(ValueError, match="Unknown support workflow"):
        reference(state)
