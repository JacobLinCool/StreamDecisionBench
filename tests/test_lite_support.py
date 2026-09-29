"""Public-evidence counterfactuals for the two support workflows."""

from copy import deepcopy

import pytest

from streamdecisionbench.lite.tasks.support import reference, scenarios


@pytest.fixture(scope="module")
def episodes():
    return scenarios()


def _state(episodes, scenario, tick):
    return deepcopy(episodes[scenario]["steps"][tick]["state"])


def _add(state, text, *, speaker="Customer", final=True):
    state["transcript"].append({"utterance_id": "counterfactual", "at": state["clock"]["now"] + 0.1,
                                "speaker": speaker, "final": final, "text": text})
    state["clock"]["now"] += 0.1


def test_support_schema_and_public_reference(episodes):
    assert len(episodes) == 2
    for episode in episodes:
        assert len(episode["questions"]) == 7
        assert len(episode["steps"]) == 60
        assert episode["tick_seconds"] == 2.0
        for tick, step in enumerate(episode["steps"]):
            assert step["t"] == tick
            assert step["state"]["clock"]["now"] == tick
            assert "gold" not in step["state"]
            assert "t" not in step["state"]
            assert reference(deepcopy(step["state"])) == step["gold"]
            assert all(u["at"] <= tick for u in step["state"]["transcript"])
            for question, value in step["gold"].items():
                assert value in episode["questions"][question]["criteria"]


def test_payment_partial_card_correction_requires_final(episodes):
    assert episodes[0]["steps"][38]["gold"]["instrument"] == "debit"
    assert episodes[0]["steps"][40]["gold"]["instrument"] == "credit"
    assert episodes[0]["steps"][40]["gold"]["payment_stage"] == "collect"
    state = _state(episodes, 0, 48)
    assert reference(state)["payment_stage"] == "submit"
    state["desktop"]["payment"]["fields_for_card"] = "debit"
    assert reference(state)["payment_stage"] == "collect"


def test_payment_authorisation_withdrawal_and_regrant(episodes):
    assert episodes[0]["steps"][44]["gold"]["payment_stage"] == "ask_consent"
    assert episodes[0]["steps"][46]["gold"]["payment_stage"] == "collect"
    assert episodes[0]["steps"][0]["state"]["desktop"]["payment"]["statement_read_at"] is None
    state = _state(episodes, 0, 0)
    _add(state, "I authorise this one-off payment.")
    assert reference(state)["payment_stage"] == "ask_consent"


def test_payment_recorder_is_global_and_old_card_text_is_not_live(episodes):
    at_side_question = episodes[0]["steps"][20]["gold"]
    assert at_side_question["route"] == "service"
    assert at_side_question["recorder"] == "pause"
    assert episodes[0]["steps"][22]["gold"]["recorder"] == "record"
    assert episodes[0]["steps"][50]["gold"]["recorder"] == "record"
    assert episodes[0]["steps"][51]["gold"]["recorder"] == "pause"
    assert episodes[0]["steps"][52]["gold"]["recorder"] == "record"
    assert episodes[0]["steps"][10]["gold"]["recorder"] == "record"
    assert episodes[0]["steps"][58]["gold"]["recorder"] == "stop"


def test_card_ending_digits_alone_do_not_pause_but_expiry_still_does(episodes):
    state = _state(episodes, 0, 52)
    _add(state, "My card number ends in four two.", final=False)
    assert reference(state)["recorder"] == "record"
    state["transcript"][-1]["text"] = "My card number ends in four two; the expiry is zero nine."
    assert reference(state)["recorder"] == "pause"


@pytest.mark.parametrize("speaker", ["Agent", "Background"])
def test_other_speaker_cannot_choose_card_or_workflow(episodes, speaker):
    state = _state(episodes, 0, 8)
    expected = reference(state)
    _add(state, "Check my router. Use my credit card.", speaker=speaker)
    assert reference(state) == expected


def test_hold_threshold_uses_clock_including_equality(episodes):
    state = _state(episodes, 0, 29)
    state["clock"]["now"] = 32.999
    assert reference(state)["hold_action"] == "wait"
    state["clock"]["now"] = 33
    assert reference(state)["hold_action"] == "return_customer"
    assert episodes[0]["steps"][34]["gold"]["route"] == "service"
    assert episodes[1]["steps"][47]["gold"]["route"] == "hold_wait"
    assert episodes[1]["steps"][48]["gold"]["route"] == "hold_return"


def test_cancellation_requires_final_request_and_callback(episodes):
    assert episodes[1]["steps"][10]["gold"]["route"] == "delivery"
    assert episodes[1]["steps"][12]["gold"]["route"] == "cancel"
    assert episodes[1]["steps"][14]["gold"]["cancellation_action"] == "cancel_request"
    assert episodes[1]["steps"][16]["gold"]["cancellation_action"] == "confirm_cancelled"
    state = _state(episodes, 1, 12)
    state["desktop"]["shipments"]["replacement"]["status"] = "in_transit"
    assert reference(state)["cancellation_action"] == "explain_locked"


def test_parcel_deadline_and_target_overrule_agent_estimate(episodes):
    assert episodes[1]["steps"][19]["gold"]["delivery_action"] == "wait"
    assert episodes[1]["steps"][20]["gold"]["delivery_action"] == "open_case"
    assert episodes[1]["steps"][20]["gold"]["delivery_target"] == "original"
    assert episodes[1]["steps"][22]["gold"]["delivery_action"] == "confirm_delivery"
    state = _state(episodes, 1, 8)
    state["desktop"]["shipments"]["replacement"]["promised_at"] = 1
    assert reference(state)["delivery_action"] == "correct_address"


def test_device_correction_and_spares_are_target_specific(episodes):
    assert episodes[1]["steps"][26]["gold"]["repair_target"] == "base"
    assert episodes[1]["steps"][28]["gold"]["repair_target"] == "handset"
    assert episodes[1]["steps"][34]["gold"]["repair_action"] == "book_visit"
    assert episodes[1]["steps"][38]["gold"]["repair_action"] == "send_part"
    assert episodes[1]["steps"][40]["gold"]["repair_target"] == "base"
    assert episodes[1]["steps"][40]["gold"]["repair_action"] == "diagnose"


def test_contact_withdrawal_does_not_revoke_remote_permission(episodes):
    gold = episodes[1]["steps"][53]["gold"]
    assert gold["contact_channel"] == "none"
    assert gold["repair_action"] == "remote_check"
    state = _state(episodes, 1, 53)
    _add(state, "I withdraw remote access; do not connect remotely.")
    changed = reference(state)
    assert changed["repair_action"] == "request_access"
    assert changed["contact_channel"] == "none"


def test_quoted_or_negated_request_does_not_select_cancel(episodes):
    state = _state(episodes, 1, 6)
    expected = reference(state)
    _add(state, 'I heard "cancel the original parcel" on the television. Do not cancel the replacement parcel.')
    assert reference(state) == expected


def test_reference_is_pure_and_unknown_workflow_fails(episodes):
    state = _state(episodes, 0, 36)
    before = deepcopy(state)
    reference(state)
    assert state == before
    state["workflow"] = "unknown"
    with pytest.raises(ValueError, match="Unknown support workflow"):
        reference(state)
