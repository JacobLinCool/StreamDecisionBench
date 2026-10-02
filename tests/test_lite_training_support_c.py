"""Public-evidence checks for the travel-change training variant support_c."""

from copy import deepcopy

import pytest

from streamdecisionbench.lite.core import compose, encode_scenario, validate_episode
from streamdecisionbench.lite.training.audit import leakage
from streamdecisionbench.lite.training.support_c import reference, scenarios


@pytest.fixture(scope="module")
def episode():
    (only,) = scenarios()
    return only


def _state(episode, tick):
    return deepcopy(episode["steps"][tick]["state"])


def _gold(episode, tick):
    return episode["steps"][tick]["gold"]


def _add(state, text, *, speaker="Customer", final=True):
    state["transcript"].append({"utterance_id": "counterfactual", "at": state["clock"]["now"] + 0.1,
                                "speaker": speaker, "final": final, "text": text})
    state["clock"]["now"] += 0.1


def _line(state, utterance_id):
    return next(u for u in state["transcript"] if u["utterance_id"] == utterance_id)


def test_schema_causality_and_public_reference(episode):
    assert episode["episode_id"] == "train_support_c"
    assert episode["task_family"] == "support_call_assist"
    assert episode["scenario_id"] == "support_c"
    assert len(episode["questions"]) == 7
    assert len(episode["steps"]) == 60
    assert episode["tick_seconds"] == 2.0
    rules = episode["steps"][0]["state"]["prepared"]
    previous = set()
    for tick, step in enumerate(episode["steps"]):
        state = step["state"]
        assert step["t"] == tick
        assert state["clock"]["now"] == tick
        assert state["workflow"] == "travel_change"
        assert state["prepared"] == rules
        assert not {"gold", "t", "hidden", "answer"} & set(state)
        assert step["evidence"] and all(isinstance(e, str) and e for e in step["evidence"])
        assert reference(deepcopy(state)) == step["gold"]
        transcript = state["transcript"]
        assert all(u["at"] <= tick for u in transcript)
        assert [u["at"] for u in transcript] == sorted(u["at"] for u in transcript)
        assert len({u["utterance_id"] for u in transcript}) == len(transcript)
        assert all(u["speaker"] in {"Customer", "Agent", "Background"} for u in transcript)
        assert state["telephony"]["since"] <= tick
        for question, value in step["gold"].items():
            assert value in episode["questions"][question]["criteria"]
        # History is kept: every earlier utterance id survives (a final only replaces its partial).
        ids = {u["utterance_id"] for u in transcript}
        assert previous <= ids
        previous = ids


def test_final_replaces_partial_and_keeps_its_time(episode):
    partial = _line(_state(episode, 13), "u13-turn")
    final = _line(_state(episode, 14), "u13-turn")
    assert not partial["final"] and final["final"]
    assert partial["at"] == final["at"] == 13
    assert sum(u["utterance_id"] == "u13-turn" for u in _state(episode, 14)["transcript"]) == 1


def test_encoded_episode_is_valid_and_has_no_leakage(episode):
    summary = validate_episode(encode_scenario(episode))
    assert summary["decision_transitions"] == 22
    assert summary["routes_unseen"] == []
    assert leakage([episode]) == []


def test_every_branch_value_is_exercised(episode):
    for question, spec in episode["questions"].items():
        seen = {step["gold"][question] for step in episode["steps"]}
        assert seen == set(spec["criteria"]), question


def test_inactive_branch_answers_are_none(episode):
    spec = episode["decision_spec"]
    for step in episode["steps"]:
        gold = step["gold"]
        active = set(compose(spec, gold))
        for question, value in gold.items():
            if question not in active:
                assert value == "none", (step["t"], question)


def test_key_ticks(episode):
    expected = {
        0: {"route": "rebook", "segment": "island", "rebook_action": "change_free", "recorder": "record"},
        1: {"route": "rebook", "segment": "island", "rebook_action": "change_free"},
        3: {"route": "rebook", "rebook_action": "collect_difference"},
        4: {"route": "rebook", "rebook_action": "collect_difference"},
        6: {"route": "refund", "segment": "island", "refund_action": "offer_credit"},
        8: {"refund_action": "offer_credit"},
        9: {"refund_action": "submit_refund"},
        11: {"route": "refund", "segment": "return", "refund_action": "explain_nonrefundable"},
        13: {"route": "refund", "segment": "return", "refund_action": "explain_nonrefundable"},
        14: {"route": "baggage", "bag": "suitcase", "bag_action": "keep_tracing", "segment": "none"},
        16: {"bag": "suitcase", "bag_action": "arrange_delivery"},
        17: {"bag_action": "arrange_delivery"},
        18: {"bag": "guitar_case", "bag_action": "share_eta"},
        19: {"bag": "guitar_case", "bag_action": "share_eta"},
        20: {"bag": "guitar_case", "bag_action": "share_eta"},
        21: {"bag": "suitcase", "bag_action": "share_eta"},
        23: {"bag_action": "share_eta", "recorder": "record"},
        24: {"bag": "suitcase", "bag_action": "open_claim", "recorder": "record"},
        25: {"route": "baggage", "bag_action": "open_claim", "recorder": "pause"},
        26: {"route": "baggage", "bag_action": "open_claim", "recorder": "pause"},
        27: {"route": "hold_wait", "bag": "none", "bag_action": "none", "recorder": "pause"},
        31: {"route": "hold_wait", "recorder": "pause"},
        32: {"route": "hold_return", "recorder": "pause"},
        34: {"route": "baggage", "bag": "suitcase", "bag_action": "confirm_delivery", "recorder": "pause"},
        36: {"route": "rebook", "segment": "return", "rebook_action": "offer_waitlist", "recorder": "pause"},
        37: {"route": "rebook", "rebook_action": "offer_waitlist", "recorder": "record"},
        39: {"route": "rebook", "rebook_action": "offer_waitlist"},
        40: {"rebook_action": "offer_waitlist"},
        41: {"rebook_action": "await_waitlist", "recorder": "record"},
        42: {"recorder": "record"},
        45: {"recorder": "record"},
        46: {"recorder": "pause"},
        47: {"recorder": "record"},
        48: {"rebook_action": "await_waitlist"},
        49: {"rebook_action": "confirm_change"},
        51: {"route": "refund", "segment": "island", "refund_action": "await_refund"},
        50: {"route": "rebook", "segment": "return", "rebook_action": "confirm_change"},
        53: {"refund_action": "confirm_refund"},
        54: {"route": "refund", "segment": "island", "refund_action": "confirm_refund"},
        55: {"recorder": "record"},
        57: {"route": "closed", "recorder": "stop", "segment": "none"},
        59: {"route": "closed", "recorder": "stop"},
    }
    for tick, fields in expected.items():
        gold = _gold(episode, tick)
        for key, value in fields.items():
            assert gold[key] == value, (tick, key, gold[key])


@pytest.mark.parametrize("speaker", ["Agent", "Background"])
def test_other_speakers_cannot_request_or_choose(episode, speaker):
    state = _state(episode, 8)
    expected = reference(state)
    _add(state, "Trace my guitar case, please.", speaker=speaker)
    assert reference(state) == expected
    _add(state, "Rebook my return flight to Tuesday.", speaker=speaker)
    assert reference(state) == expected


def test_background_request_would_count_if_spoken_by_customer(episode):
    state = _state(episode, 10)
    assert reference(state)["route"] == "refund"
    _line(state, "u10-Background")["speaker"] = "Customer"
    changed = reference(state)
    assert changed["route"] == "baggage"
    assert changed["bag"] == "guitar_case"
    assert changed["bag_action"] == "share_eta"


def test_partial_request_needs_finality_and_final_wording_decides(episode):
    state = _state(episode, 13)
    assert reference(state)["route"] == "refund"
    _line(state, "u13-turn")["final"] = True
    changed = reference(state)
    assert changed["route"] == "rebook"
    assert changed["segment"] == "return"
    assert changed["rebook_action"] == "offer_waitlist"


def test_tool_records_overrule_agent_claims(episode):
    state = _state(episode, 8)
    assert reference(state)["refund_action"] == "offer_credit"
    state["desktop"]["booking"]["segments"]["island"]["fare_type"] = "flex"
    assert reference(state)["refund_action"] == "submit_refund"
    state = _state(episode, 38)
    assert reference(state)["rebook_action"] == "offer_waitlist"
    state["desktop"]["booking"]["segments"]["return"]["change_option"]["seats_left"] = 3
    assert reference(state)["rebook_action"] == "collect_difference"
    state["desktop"]["booking"]["segments"]["return"]["change_option"]["fare_difference"] = 0
    assert reference(state)["rebook_action"] == "change_free"


def test_airline_cancellation_refunds_any_fare(episode):
    state = _state(episode, 11)
    assert reference(state)["refund_action"] == "explain_nonrefundable"
    state["desktop"]["booking"]["segments"]["return"]["flight_status"] = "cancelled"
    assert reference(state)["refund_action"] == "submit_refund"


def test_waitlist_status_wins_over_reopened_seats(episode):
    state = _state(episode, 48)
    option = state["desktop"]["booking"]["segments"]["return"]["change_option"]
    assert option["seats_left"] == 2 and option["status"] == "waitlisted"
    assert reference(state)["rebook_action"] == "await_waitlist"
    option["status"] = "none"
    assert reference(state)["rebook_action"] == "collect_difference"


def test_refund_record_is_segment_specific(episode):
    state = _state(episode, 13)
    assert state["desktop"]["refunds"]["island"] == "pending"
    assert reference(state)["refund_action"] == "explain_nonrefundable"
    state["desktop"]["refunds"]["return"] = "issued"
    assert reference(state)["refund_action"] == "confirm_refund"


def test_bag_deadline_equality_and_other_bag_record(episode):
    state = _state(episode, 23)
    state["clock"]["now"] = 23.999
    assert reference(state)["bag_action"] == "share_eta"
    state["clock"]["now"] = 24
    assert reference(state)["bag_action"] == "open_claim"
    state = _state(episode, 24)
    state["desktop"]["tracer"]["suitcase"]["promised_at"] = 25
    assert reference(state)["bag_action"] == "share_eta"
    state = _state(episode, 20)
    assert reference(state)["bag"] == "guitar_case"
    state["desktop"]["tracer"]["suitcase"]["status"] = "delivered"
    assert reference(state)["bag_action"] == "share_eta"
    state["desktop"]["tracer"]["guitar_case"]["status"] = "located"
    assert reference(state)["bag_action"] == "arrange_delivery"


def test_scan_note_does_not_override_status(episode):
    state = _state(episode, 19)
    assert "neighbour" in state["desktop"]["tracer"]["guitar_case"]["last_scan"]
    assert reference(state)["bag_action"] == "share_eta"


def test_hold_threshold_equality_and_resume(episode):
    state = _state(episode, 31)
    state["clock"]["now"] = 31.999
    assert reference(state)["route"] == "hold_wait"
    state["clock"]["now"] = 32
    assert reference(state)["route"] == "hold_return"
    assert _gold(episode, 26)["bag"] == _gold(episode, 34)["bag"] == "suitcase"
    state = _state(episode, 33)
    state["prepared"]["hold_check_ticks"] = 7
    assert reference(state)["route"] == "hold_wait"


def test_recorder_capture_and_live_passport_digits(episode):
    state = _state(episode, 37)
    assert reference(state)["recorder"] == "record"
    state["transcript"] = [u for u in state["transcript"] if u["utterance_id"] != "u37-Agent"]
    assert reference(state)["recorder"] == "pause"
    state = _state(episode, 46)
    assert reference(state)["recorder"] == "pause"
    _line(state, "u46-fix")["text"] = "Sorry, the booking number ends four"
    assert reference(state)["recorder"] == "record"
    state = _state(episode, 46)
    _line(state, "u46-fix")["speaker"] = "Background"
    assert reference(state)["recorder"] == "record"
    state = _state(episode, 55)
    assert not _line(state, "u55-receipt")["final"]
    assert reference(state)["recorder"] == "record"
    _line(state, "u55-receipt")["text"] = "The passport on the booking ends five nine"
    assert reference(state)["recorder"] == "pause"


def test_newer_customer_speech_ends_the_live_digit_pause(episode):
    state = _state(episode, 46)
    _add(state, "Hang on a second.", final=True)
    assert reference(state)["recorder"] == "record"


def test_call_end_stops_recorder_even_during_capture(episode):
    state = _state(episode, 30)
    assert reference(state)["recorder"] == "pause"
    state["telephony"] = {"status": "ended", "since": 30}
    changed = reference(state)
    assert changed["recorder"] == "stop"
    assert changed["route"] == "closed"


def test_quoted_and_negated_phrases_are_not_requests(episode):
    state = _state(episode, 50)
    assert reference(state)["route"] == "rebook"
    line = _line(state, "u50-Customer")
    line["text"] = line["text"].replace('"', "\u201c", 1).replace('"', "\u201d", 1)
    assert reference(state)["route"] == "rebook"
    line["text"] = line["text"].replace("\u201c", "").replace("\u201d", "")
    changed = reference(state)
    assert changed["route"] == "refund" and changed["segment"] == "return"
    state = _state(episode, 54)
    assert reference(state)["segment"] == "island"
    line = _line(state, "u54-Customer")
    line["text"] = line["text"].replace("Please don't refund", "Please refund")
    changed = reference(state)
    assert changed["segment"] == "return"
    assert changed["refund_action"] == "explain_nonrefundable"


def test_two_requests_in_one_utterance_are_rejected(episode):
    state = _state(episode, 10)
    _add(state, "Trace my suitcase and rebook my return flight.")
    with pytest.raises(ValueError, match="more than one request"):
        reference(state)


def test_reference_is_pure_and_unknown_workflow_fails(episode):
    state = _state(episode, 47)
    before = deepcopy(state)
    reference(state)
    assert state == before
    state["workflow"] = "payment_support"
    with pytest.raises(ValueError, match="Unknown support workflow"):
        reference(state)


@pytest.mark.parametrize("text", [
    "DON'T refund the return ticket, please.",
    "Please do not rebook my return flight.",
    "You should never trace my guitar case without telling me.",
    "The sticker on it says \u201ctrace my suitcase\u201d in red.",
])
def test_negated_and_quoted_variants_change_nothing(episode, text):
    state = _state(episode, 8)
    expected = reference(state)
    _add(state, text)
    assert reference(state) == expected


def test_defaults_before_any_request(episode):
    state = _state(episode, 0)
    assert all(u["speaker"] == "Customer" and u["final"] for u in state["transcript"])
    gold = _gold(episode, 0)
    assert (gold["route"], gold["segment"], gold["rebook_action"]) == ("rebook", "island", "change_free")
    state["desktop"]["booking"]["segments"]["island"]["change_option"]["seats_left"] = 0
    assert reference(state)["rebook_action"] == "offer_waitlist"


def test_other_segment_change_option_never_substitutes(episode):
    state = _state(episode, 4)
    assert reference(state)["rebook_action"] == "collect_difference"
    state["desktop"]["booking"]["segments"]["return"]["change_option"].update(
        status="confirmed", fare_difference=0)
    assert reference(state)["rebook_action"] == "collect_difference"


def test_capture_phrases_are_case_insensitive_and_agent_final_only(episode):
    state = _state(episode, 37)
    _line(state, "u37-Agent")["text"] = "Noted. PASSPORT CAPTURE IS COMPLETE."
    assert reference(state)["recorder"] == "record"
    state = _state(episode, 24)
    assert reference(state)["recorder"] == "record"
    _add(state, "please READ YOUR PASSPORT NUMBER now.", speaker="Agent")
    assert reference(state)["recorder"] == "pause"
    for speaker, final in [("Background", True), ("Customer", True), ("Agent", False)]:
        state = _state(episode, 40)
        _add(state, "Please read your passport number.", speaker=speaker, final=final)
        assert reference(state)["recorder"] == "record", (speaker, final)
    state = _state(episode, 30)
    _add(state, "Passport capture is complete.", speaker="Background")
    assert reference(state)["recorder"] == "pause"


def test_capture_stays_open_across_hold_and_route_change(episode):
    recorders = [_gold(episode, t)["recorder"] for t in range(25, 37)]
    assert recorders == ["pause"] * 12
    routes = {_gold(episode, t)["route"] for t in range(25, 37)}
    assert routes == {"baggage", "hold_wait", "hold_return", "rebook"}


def test_live_passport_digit_words_include_hyphenated_numbers(episode):
    state = _state(episode, 46)
    _line(state, "u46-fix")["text"] = "The passport fee was thirty-five"
    assert reference(state)["recorder"] == "pause"
    _line(state, "u46-fix")["text"] = "The PASSPORT ends 4"
    assert reference(state)["recorder"] == "pause"
    _line(state, "u46-fix")["text"] = "My passport is in the van somewhere"
    assert reference(state)["recorder"] == "record"
    _line(state, "u46-fix")["text"] = "Four two, that was my passport"
    assert reference(state)["recorder"] == "record"
