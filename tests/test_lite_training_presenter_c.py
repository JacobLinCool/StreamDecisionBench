"""Public-evidence checks for the presenter_c training variant (wake-word lecture console)."""

from copy import deepcopy
import inspect
import re

import pytest

from streamdecisionbench.lite.core import compose, encode_scenario, validate_episode
from streamdecisionbench.lite.training import presenter_c
from streamdecisionbench.lite.training.audit import (
    MAX_LAYOUT_OVERLAP, check_module, eval_scenarios, layout_overlap, leakage, spec_overlap)
from streamdecisionbench.lite.training.presenter_c import reference, scenarios

CHANNELS = {"lecturer", "moderator", "room", "media"}


@pytest.fixture(scope="module")
def episode():
    (only,) = scenarios()
    return only


def _state(episode, tick):
    return deepcopy(episode["steps"][tick]["state"])


def _gold(episode, tick):
    return episode["steps"][tick]["gold"]


def _decision(episode, tick):
    return compose(episode["decision_spec"], _gold(episode, tick))


def _segment(state, seg_id):
    return next(s for s in state["asr"]["segments"] if s["seg_id"] == seg_id)


def _add(state, text, channel="lecturer", *, stable=True, start=None, end=None, conf=None):
    """Append one new segment (newest seg_id) to a copied state and return the reference answers.

    The appended segment keeps the published conventions: it begins no earlier than any listed segment, it
    ends by now, and its channel has no unstable segment (which would then no longer be that channel's newest).
    """
    segments = state["asr"]["segments"]
    end = state["now"] if end is None else end
    start = end if start is None else start
    assert start <= end <= state["now"]
    assert all(s["start"] <= start for s in segments)
    assert all(s["stable"] for s in segments if s["channel"] == channel)
    words = [{"w": w, "conf": 0.95} for w in text.split(" ")]
    for index, value in (conf or {}).items():
        words[index]["conf"] = value
    seg_id = max((s["seg_id"] for s in segments), default=0) + 1
    segments.append({"seg_id": seg_id, "channel": channel, "start": start, "end": end, "stable": stable,
                     "words": words})
    return reference(state)


def _stabilise(segment, low=None):
    """Turn a hypothesis stable with confident words, except the positions given in low."""
    segment["stable"] = True
    for index, word in enumerate(segment["words"]):
        word["conf"] = (low or {}).get(index, 0.9)


def _reading(word):
    return "".join(ch for ch in word.lower() if ch.isalnum())


# ---------------------------------------------------------------- structure and conventions

def test_schema_causality_and_public_reference(episode):
    assert episode["episode_id"] == "train_presenter_c"
    assert episode["task_family"] == "presenter_voice_control"
    assert episode["scenario_id"] == "presenter_c"
    assert episode["tick_seconds"] == 2.0 and len(episode["steps"]) == 60
    assert set(episode["questions"]) == {"stage_mode", "projected_slide", "recording_light", "timer_cue", "pointer",
                                         "media_state", "poll_panel"}
    first = episode["steps"][0]["state"]
    for tick, step in enumerate(episode["steps"]):
        state = step["state"]
        assert step["t"] == tick and state["now"] == tick
        assert set(state) == {"controller", "session", "slides", "asr", "now"}
        assert state["controller"] == first["controller"] and state["slides"] == first["slides"]
        assert step["evidence"] and all(isinstance(e, str) and e for e in step["evidence"])
        assert reference(deepcopy(state)) == step["gold"]
        for question, value in step["gold"].items():
            assert value in episode["questions"][question]["criteria"]


def test_rules_are_the_only_spec_field_and_the_module_is_self_contained(episode):
    rules = episode["steps"][0]["state"]["controller"]["rules"]
    assert isinstance(rules, list) and all(isinstance(r, str) and r for r in rules)
    source = inspect.getsource(presenter_c)
    assert "lite.tasks" not in source and "import presenter" not in source


def test_asr_segments_follow_the_published_conventions(episode):
    identity, frozen, previous, overlap, same_start = {}, {}, [], False, False
    for step in episode["steps"]:
        now, segments = step["state"]["now"], step["state"]["asr"]["segments"]
        ids = [s["seg_id"] for s in segments]
        assert ids == sorted(set(ids))
        starts = [s["start"] for s in segments]
        assert starts == sorted(starts)
        same_start |= len(set(starts)) < len(starts)
        assert set(previous) <= set(ids)  # history is kept: no segment is withdrawn
        previous = ids
        for s in segments:
            assert s["channel"] in CHANNELS
            assert s["start"] <= s["end"] <= now
            assert identity.setdefault(s["seg_id"], (s["channel"], s["start"])) == (s["channel"], s["start"])
            assert s["words"] and all(0 <= w["conf"] <= 1 and _reading(w["w"]) for w in s["words"])
            # At most three words a second: a segment's span of ticks (two seconds each) bounds its length.
            assert len(s["words"]) <= 6 * (s["end"] - s["start"] + 1), s
            if s["stable"]:
                assert frozen.setdefault(s["seg_id"], s) == s  # a stable segment never changes again
            else:
                assert s["seg_id"] not in frozen
                assert all(re.fullmatch(r"[a-z]+", w["w"]) for w in s["words"])
        for channel in CHANNELS:
            own = [s for s in segments if s["channel"] == channel]
            unstable = [s for s in own if not s["stable"]]
            assert len(unstable) <= 1 and (not unstable or unstable[0] is own[-1])
        overlap |= sum(not s["stable"] for s in segments) > 1
    assert overlap and same_start
    assert all(s["stable"] for s in episode["steps"][-1]["state"]["asr"]["segments"])


def test_stable_words_clear_the_threshold_unless_set_low_on_purpose(episode):
    state = episode["steps"][-1]["state"]
    threshold = state["controller"]["min_confidence"]
    low = {(s["seg_id"], i, w["conf"]) for s in state["asr"]["segments"] for i, w in enumerate(s["words"])
           if w["conf"] < threshold}
    assert low == {(6, 4, 0.84)}
    exact = {(s["seg_id"], i) for s in state["asr"]["segments"] for i, w in enumerate(s["words"])
             if w["conf"] == threshold}
    assert exact == {(30, 4)}


def test_deck_follows_the_published_conventions(episode):
    slides = episode["steps"][0]["state"]["slides"]
    titles = slides["titles"]
    assert list(titles) == [str(n) for n in range(1, slides["count"] + 1)]
    assert len(set(titles.values())) == len(titles)
    for title in titles.values():
        assert re.fullmatch(r"[a-z]+( [a-z]+)*", title)
        assert not title.startswith("the ") and not title.endswith(" please") and title != "please"
    assert set(slides["media"]) <= set(range(1, slides["count"] + 1))
    assert set(slides["unpublished"]) <= set(range(1, slides["count"] + 1))
    criteria = episode["questions"]["projected_slide"]["criteria"]
    assert set(criteria) == {f"slide_{n}" for n in range(1, slides["count"] + 1)}


def test_encoded_episode_is_valid_with_no_leakage_and_its_own_specification(episode):
    summary = validate_episode(encode_scenario(episode))
    assert summary["decision_transitions"] == 30
    assert summary["routes_seen"] == ["break", "ended", "lecture", "media", "poll"]
    assert summary["routes_unseen"] == []
    assert leakage([episode]) == []
    assert spec_overlap([episode]) == []
    assert layout_overlap(episode) <= MAX_LAYOUT_OVERLAP
    check_module(presenter_c)


def test_questions_and_option_sets_are_the_variants_own(episode):
    family = [s for s in eval_scenarios() if s["task_family"] == episode["task_family"]]
    assert family
    for scenario in family:
        assert not set(scenario["questions"]) & set(episode["questions"])
        for question in scenario["questions"].values():
            labels = set(question["criteria"].values())
            for ours in episode["questions"].values():
                assert labels != set(ours["criteria"].values())
                assert not any(label.endswith("mode inactive") for label in ours["criteria"].values())


def test_every_non_slide_value_is_reached_as_gold(episode):
    for question, spec in episode["questions"].items():
        seen = {step["gold"][question] for step in episode["steps"]}
        if question == "projected_slide":
            assert seen == {f"slide_{n}" for n in (1, 2, 3, 4, 6, 8, 9, 10)}
        else:
            assert seen == set(spec["criteria"]), question


def test_inactive_branch_answers_are_none_and_every_question_is_used(episode):
    spec = episode["decision_spec"]
    used = {spec["route_question"], *spec["always"], *(q for b in spec["branches"].values() for q in b)}
    assert used == set(episode["questions"])
    for step in episode["steps"]:
        active = set(compose(spec, step["gold"]))
        for question, value in step["gold"].items():
            if question not in active:
                assert value == "none", (step["t"], question)


def test_no_answer_depends_on_an_unstable_segment(episode):
    for step in episode["steps"]:
        state = deepcopy(step["state"])
        state["asr"]["segments"] = [s for s in state["asr"]["segments"] if s["stable"]]
        assert reference(state) == step["gold"], step["t"]


# ---------------------------------------------------------------- the story

def test_key_ticks(episode):
    expected = {
        0: {"stage_mode": "lecture", "projected_slide": "slide_1", "recording_light": "on", "timer_cue": "none",
            "pointer": "off"},
        2: {"projected_slide": "slide_1"},
        3: {"projected_slide": "slide_2"},
        6: {"projected_slide": "slide_2"},
        7: {"projected_slide": "slide_2"},
        8: {"projected_slide": "slide_2"},
        9: {"projected_slide": "slide_3"},
        12: {"pointer": "zoom"},
        14: {"projected_slide": "slide_3", "pointer": "off"},
        15: {"projected_slide": "slide_3"},
        16: {"projected_slide": "slide_3"},
        17: {"projected_slide": "slide_4", "pointer": "off"},
        18: {"stage_mode": "media", "media_state": "playing", "pointer": "none"},
        20: {"stage_mode": "media", "projected_slide": "slide_4"},
        23: {"stage_mode": "poll", "poll_panel": "collecting", "media_state": "none", "projected_slide": "slide_4"},
        25: {"poll_panel": "collecting"},
        26: {"poll_panel": "results"},
        27: {"stage_mode": "media", "media_state": "paused", "poll_panel": "none"},
        28: {"media_state": "playing"},
        30: {"stage_mode": "lecture", "projected_slide": "slide_4", "pointer": "off", "media_state": "none"},
        31: {"projected_slide": "slide_6"},
        32: {"pointer": "off"},
        33: {"pointer": "off"},
        34: {"pointer": "spotlight", "timer_cue": "none"},
        35: {"timer_cue": "wrap_up"},
        36: {"timer_cue": "wrap_up"},
        37: {"timer_cue": "none"},
        38: {"projected_slide": "slide_6", "pointer": "spotlight"},
        39: {"projected_slide": "slide_8", "pointer": "off"},
        42: {"stage_mode": "lecture", "recording_light": "paused"},
        43: {"stage_mode": "media", "media_state": "playing", "recording_light": "paused"},
        45: {"timer_cue": "none"},
        46: {"timer_cue": "wrap_up", "stage_mode": "media"},
        47: {"media_state": "paused"},
        48: {"stage_mode": "lecture", "projected_slide": "slide_8", "recording_light": "paused"},
        49: {"recording_light": "on"},
        50: {"stage_mode": "break", "projected_slide": "slide_8", "recording_light": "paused", "pointer": "none"},
        51: {"stage_mode": "break", "projected_slide": "slide_9", "recording_light": "paused"},
        52: {"stage_mode": "lecture", "projected_slide": "slide_9", "recording_light": "paused", "pointer": "off"},
        53: {"recording_light": "paused", "timer_cue": "wrap_up"},
        54: {"recording_light": "paused", "timer_cue": "overtime"},
        55: {"projected_slide": "slide_9", "recording_light": "on"},
        56: {"projected_slide": "slide_10", "recording_light": "on", "pointer": "off"},
        57: {"projected_slide": "slide_9", "recording_light": "paused", "timer_cue": "overtime"},
        58: {"stage_mode": "ended", "recording_light": "off", "timer_cue": "none", "projected_slide": "slide_9"},
        59: {"stage_mode": "ended", "projected_slide": "slide_9", "recording_light": "off", "pointer": "none"},
    }
    for tick, fields in expected.items():
        gold = _gold(episode, tick)
        for key, value in fields.items():
            assert gold[key] == value, (tick, key, gold[key])


def test_decision_holds_on_distractor_ticks(episode):
    # Unstable command, room command, confident unstable command, low-confidence command, wake word not first,
    # locked slide, the zoom request that runs past its phrase, the stream remark, the lecturer's moderator
    # phrase, the moderator's lecturer phrase and a command after the end change nothing.
    for tick in (2, 6, 7, 8, 15, 20, 32, 33, 45, 53, 59):
        assert _decision(episode, tick) == _decision(episode, tick - 1), tick


# ---------------------------------------------------------------- confidence threshold

def test_confidence_threshold_equality_counts(episode):
    state = _state(episode, 8)
    assert state["controller"]["min_confidence"] == 0.85
    word = _segment(state, 6)["words"][4]
    assert (word["w"], word["conf"]) == ("three.", 0.84)
    word["conf"] = 0.85
    assert reference(state)["projected_slide"] == "slide_3"
    state = _state(episode, 8)
    state["controller"]["min_confidence"] = 0.84
    assert reference(state)["projected_slide"] == "slide_3"
    state = _state(episode, 39)
    word = _segment(state, 30)["words"][4]
    assert (word["w"], word["conf"]) == ("chorus.", 0.85)
    assert reference(state)["projected_slide"] == "slide_8"
    word["conf"] = 0.84
    assert reference(state)["projected_slide"] == "slide_6"
    state = _state(episode, 39)
    state["controller"]["min_confidence"] = 0.86
    assert reference(state)["projected_slide"] == "slide_6"


@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_one_low_word_voids_the_whole_command_including_wake_word_and_please(episode, index):
    state = _state(episode, 17)
    seg = _segment(state, 13)
    assert [w["w"] for w in seg["words"]] == ["Console,", "next", "slide,", "please."]
    assert reference(state)["projected_slide"] == "slide_4"
    seg["words"][index]["conf"] = 0.5
    assert reference(state)["projected_slide"] == "slide_3"


# ---------------------------------------------------------------- who may command, and stability

def test_room_and_media_channels_never_command(episode):
    state = _state(episode, 6)
    assert reference(state)["projected_slide"] == "slide_2"
    _segment(state, 4)["channel"] = "lecturer"
    assert reference(state)["projected_slide"] == "slide_3"
    state = _state(episode, 22)
    assert _add(state, "Console, stop the video.", "media")["stage_mode"] == "media"
    assert _add(state, "Console, take a break.", "room")["stage_mode"] == "media"
    assert _add(state, "Console, stop the video.", "lecturer")["stage_mode"] == "lecture"


def test_each_speaker_has_its_own_phrases(episode):
    state = _state(episode, 25)
    assert reference(state)["poll_panel"] == "collecting"
    _segment(state, 20)["channel"] = "moderator"
    assert reference(state)["poll_panel"] == "results"
    state = _state(episode, 53)
    assert reference(state)["recording_light"] == "paused"
    _segment(state, 43)["channel"] = "lecturer"
    assert reference(state)["recording_light"] == "on"
    state = _state(episode, 49)
    assert _add(state, "Console, end the lecture.", "lecturer")["stage_mode"] == "lecture"
    assert _add(state, "Console, pause recording.", "moderator")["recording_light"] == "on"
    assert _add(state, "Console, end the lecture.", "moderator")["stage_mode"] == "ended"
    state = _state(episode, 11)
    assert _add(state, "Console, next slide.", "moderator")["projected_slide"] == "slide_3"
    assert _add(state, "Console, open the poll.", "lecturer")["stage_mode"] == "lecture"


def test_unstable_segments_never_command_until_stable(episode):
    state = _state(episode, 2)
    assert not _segment(state, 2)["stable"] and reference(state)["projected_slide"] == "slide_1"
    _stabilise(_segment(state, 2))
    assert reference(state)["projected_slide"] == "slide_2"
    state = _state(episode, 50)
    assert not _segment(state, 39)["stable"] and reference(state)["projected_slide"] == "slide_8"
    _stabilise(_segment(state, 39))
    assert reference(state)["projected_slide"] == "slide_9"


@pytest.mark.parametrize("tick,seg_id,lure,field,before,acted", [
    (7, 6, ["console", "go", "to", "slide", "three"], "projected_slide", "slide_2", "slide_3"),
    (32, 27, ["console", "zoom", "in"], "pointer", "off", "zoom"),
])
def test_confident_hypotheses_that_never_become_commands(episode, tick, seg_id, lure, field, before, acted):
    # The hypothesis reads as a complete command with every word above the threshold; acting on it would be
    # wrong, because the stable segment of the next tick is void (a word under the threshold) or longer speech.
    state = _state(episode, tick)
    seg = _segment(state, seg_id)
    threshold = state["controller"]["min_confidence"]
    assert not seg["stable"] and [_reading(w["w"]) for w in seg["words"]] == lure
    assert all(w["conf"] >= threshold for w in seg["words"])
    assert _gold(episode, tick)[field] == before
    seg["stable"] = True
    assert reference(state)[field] == acted
    stable = _segment(_state(episode, tick + 1), seg_id)
    assert stable["stable"] and _gold(episode, tick + 1)[field] == before
    assert ([_reading(w["w"]) for w in stable["words"]] != lure
            or any(w["conf"] < threshold for w in stable["words"]))


def test_the_break_is_called_for_the_stream_and_closed_by_its_return(episode):
    remark = _segment(_state(episode, 46), 35)
    assert remark["channel"] == "moderator" and "break." in [w["w"] for w in remark["words"]]
    assert [_gold(episode, t)["stage_mode"] for t in (46, 49, 50, 51, 52)] == [
        "media", "lecture", "break", "break", "lecture"]
    back = _segment(_state(episode, 51), 41)
    assert (back["channel"], back["stable"], back["start"]) == ("moderator", True, 51)
    assert _decision(episode, 51)["stage_mode"] == "break"


def test_a_number_word_slide_command_passes(episode):
    seg = _segment(_state(episode, 56), 46)
    assert [_reading(w["w"]) for w in seg["words"]] == ["console", "slide", "ten"]
    assert _gold(episode, 55)["projected_slide"] == "slide_9" and _gold(episode, 56)["projected_slide"] == "slide_10"
    state = _state(episode, 56)
    seg = _segment(state, 46)
    seg["words"][2]["w"] = "tenth."
    assert reference(state)["projected_slide"] == "slide_9"


@pytest.mark.parametrize("text,channel,tick", [
    ("console next slide", "lecturer", 11),
    ("console spotlight", "lecturer", 11),
    ("console play the video", "lecturer", 17),
    ("console pause recording", "lecturer", 11),
    ("console pause recording please", "lecturer", 11),
    ("console stop the video", "lecturer", 22),
    ("console pause the video", "lecturer", 22),
    ("console record this slide", "lecturer", 52),
    ("console end the lecture", "moderator", 11),
    ("console take a break", "moderator", 22),
    ("console resume the lecture", "moderator", 51),
])
def test_unstable_command_readings_change_no_answer(episode, text, channel, tick):
    state = _state(episode, tick)
    assert _add(state, text, channel, stable=False) == _gold(episode, tick)


def test_wake_word_must_come_first(episode):
    state = _state(episode, 15)
    assert reference(state)["projected_slide"] == "slide_3"
    _segment(state, 12)["words"].pop(0)
    assert reference(state)["projected_slide"] == "slide_4"
    state = _state(episode, 15)
    state["controller"]["wake_word"] = "lectern"
    assert reference(state)["projected_slide"] == "slide_1"


# ---------------------------------------------------------------- grammar

@pytest.mark.parametrize("text,field,value", [
    ("Console, next slide.", "projected_slide", "slide_4"),
    ("CONSOLE NEXT SLIDE!", "projected_slide", "slide_4"),
    ("console next slide", "projected_slide", "slide_4"),
    ("Console... next slide?!", "projected_slide", "slide_4"),
    ("Console, previous slide, please.", "projected_slide", "slide_2"),
    ("Console, slide 12.", "projected_slide", "slide_12"),
    ("Console, slide 09.", "projected_slide", "slide_9"),
    ("Console, go to slide nine.", "projected_slide", "slide_9"),
    ("Console, slide twelve.", "projected_slide", "slide_12"),
    ("Console, slide 13.", "projected_slide", "slide_3"),
    ("Console, slide 0.", "projected_slide", "slide_3"),
    ("Console, slide twenty.", "projected_slide", "slide_3"),
    ("Console, slide twenty one.", "projected_slide", "slide_3"),
    ("Console, go slide 5.", "projected_slide", "slide_3"),
    ("Console, show quiet harbour trial.", "projected_slide", "slide_9"),
    ("Console, show the noise budget, please.", "projected_slide", "slide_6"),
    ("Console, show the coral reef.", "projected_slide", "slide_3"),
    ("Console, show noise.", "projected_slide", "slide_3"),
    ("Console, please next slide.", "projected_slide", "slide_3"),
    ("Console, next slide, please, please.", "projected_slide", "slide_3"),
    ("Console, next slide and zoom in.", "projected_slide", "slide_3"),
    ("Okay console, next slide.", "projected_slide", "slide_3"),
    ("Consoles, next slide.", "projected_slide", "slide_3"),
    ("Console, next.", "projected_slide", "slide_3"),
    ("Console, pause recording.", "recording_light", "paused"),
    ("Console, pause recording, please.", "recording_light", "paused"),
    ("Console, pause the recording.", "recording_light", "on"),
    ("Console, stop recording.", "recording_light", "on"),
    ("Console, zoom in.", "pointer", "zoom"),
    ("Console, spotlight, please.", "pointer", "spotlight"),
    ("Console, spotlight on.", "pointer", "off"),
    ("Console, play the video.", "stage_mode", "lecture"),
    ("Console, open the poll.", "stage_mode", "lecture"),
])
def test_command_grammar_on_a_lecture_slide_without_clip(episode, text, field, value):
    state = _state(episode, 11)
    gold = reference(state)
    assert (gold["projected_slide"], gold["pointer"], gold["recording_light"]) == ("slide_3", "off", "on")
    assert _add(state, text)[field] == value


@pytest.mark.parametrize("text,light", [
    ("Console, record this slide.", "on"),
    ("Console, record this slide, please.", "on"),
    ("console record this slide", "on"),
    ("Console, record the slide.", "paused"),
    ("Console, record slide 9.", "paused"),
    ("Console, record this.", "paused"),
    ("Console, record this slide now.", "paused"),
    ("Console, resume recording.", "paused"),
])
def test_record_this_slide_grammar_on_the_unpublished_slide(episode, text, light):
    state = _state(episode, 52)
    gold = reference(state)
    assert (gold["stage_mode"], gold["projected_slide"], gold["recording_light"]) == ("lecture", "slide_9", "paused")
    assert _add(state, text)["recording_light"] == light


@pytest.mark.parametrize("text,media", [
    ("Console, pause video.", "paused"), ("Console, pause the audio.", "paused"),
    ("Console, pause audio, please.", "paused"), ("Console, pause a video.", "playing"),
    ("Console, pause the clip.", "playing"), ("Console, hold the video.", "playing"),
])
def test_clip_nouns_are_interchangeable(episode, text, media):
    state = _state(episode, 22)
    assert reference(state)["media_state"] == "playing"
    assert _add(state, text)["media_state"] == media


def test_pointer_zoom_out_and_pointer_off(episode):
    for text in ("Console, zoom out.", "Console, pointer off."):
        state = _state(episode, 13)
        assert reference(state)["pointer"] == "zoom"
        assert _add(state, text)["pointer"] == "off"
    state = _state(episode, 37)
    assert reference(state)["pointer"] == "spotlight"
    assert _add(state, "Console, pointer off.")["pointer"] == "off"


# ---------------------------------------------------------------- modes

def test_slides_are_locked_outside_lecture_mode(episode):
    state = _state(episode, 20)
    assert reference(state)["projected_slide"] == "slide_4"
    _segment(state, 14)["channel"] = "room"  # without the play command, the next slide command applies
    changed = reference(state)
    assert (changed["stage_mode"], changed["projected_slide"]) == ("lecture", "slide_5")
    for tick in (24, 51):
        state = _state(episode, tick)
        before = reference(state)
        assert _add(state, "Console, next slide.") == before
        assert _add(state, "Console, spotlight.") == before
    state = _state(episode, 22)
    assert _add(state, "Console, zoom in.")["stage_mode"] == "media"
    assert _add(state, "Console, stop the video.")["pointer"] == "off"


def test_play_needs_a_media_slide_and_pause_or_stop_need_media_mode(episode):
    state = _state(episode, 11)
    assert _add(state, "Console, play the video.")["stage_mode"] == "lecture"
    state = _state(episode, 17)
    assert _add(state, "Console, pause the video.")["stage_mode"] == "lecture"
    assert _add(state, "Console, stop the video.")["stage_mode"] == "lecture"
    answers = _add(state, "Console, play the audio.")
    assert (answers["stage_mode"], answers["media_state"]) == ("media", "playing")
    state = _state(episode, 27)
    assert _add(state, "Console, play the video.")["media_state"] == "playing"


def test_pointer_resets_only_when_slide_or_mode_changes(episode):
    state = _state(episode, 13)
    assert reference(state)["pointer"] == "zoom"
    assert _add(state, "Console, slide three.")["pointer"] == "zoom"
    assert _add(state, "Console, show hydrophone moorings.")["pointer"] == "zoom"
    assert _add(state, "Console, previous slide.")["pointer"] == "off"
    state = _state(episode, 11)
    _add(state, "Console, slide 12.")
    _add(state, "Console, zoom in.")
    answers = _add(state, "Console, next slide.")
    assert (answers["projected_slide"], answers["pointer"]) == ("slide_12", "zoom")
    state = _state(episode, 11)
    _add(state, "Console, slide one.")
    _add(state, "Console, spotlight.")
    answers = _add(state, "Console, previous slide.")
    assert (answers["projected_slide"], answers["pointer"]) == ("slide_1", "spotlight")
    state = _state(episode, 13)
    _add(state, "Console, open the poll.", "moderator")
    answers = _add(state, "Console, resume the lecture.", "moderator")
    assert (answers["stage_mode"], answers["projected_slide"], answers["pointer"]) == ("lecture", "slide_3", "off")


def test_moderator_mode_commands_apply_only_in_their_modes(episode):
    state = _state(episode, 30)
    answers = _add(state, "Console, open the poll.", "moderator")
    assert (answers["stage_mode"], answers["poll_panel"]) == ("poll", "collecting")
    assert _add(state, "Console, take a break.", "moderator")["stage_mode"] == "break"
    assert _add(state, "Console, close the poll.", "moderator")["stage_mode"] == "break"
    assert _add(state, "Console, open the poll.", "moderator")["stage_mode"] == "break"
    assert _add(state, "Console, take a break.", "moderator")["stage_mode"] == "break"
    answers = _add(state, "Console, resume the lecture.", "moderator")
    assert (answers["stage_mode"], answers["projected_slide"], answers["media_state"]) == ("lecture", "slide_4", "none")
    assert _add(state, "Console, resume the lecture.", "moderator")["stage_mode"] == "lecture"
    assert _add(state, "Console, close the poll.", "moderator")["stage_mode"] == "lecture"
    state = _state(episode, 26)
    answers = _add(state, "Console, open the poll.", "moderator")
    assert (answers["stage_mode"], answers["poll_panel"]) == ("poll", "results")
    state = _state(episode, 24)
    assert _add(state, "Console, open the poll, please.", "moderator")["poll_panel"] == "collecting"
    assert _add(state, "Console, close poll.", "moderator")["poll_panel"] == "collecting"
    state = _state(episode, 38)
    answers = _add(state, "Console, open the poll.", "moderator")
    assert (answers["stage_mode"], answers["poll_panel"]) == ("poll", "collecting")


# ---------------------------------------------------------------- held clips

def test_a_poll_called_during_a_clip_holds_it_and_resuming_brings_it_back_paused(episode):
    assert [_gold(episode, t)["media_state"] for t in (22, 23, 26, 27, 28)] == [
        "playing", "none", "none", "paused", "playing"]
    assert [_gold(episode, t)["stage_mode"] for t in (22, 23, 26, 27, 30)] == [
        "media", "poll", "poll", "media", "lecture"]
    state = _state(episode, 27)
    _segment(state, 14)["channel"] = "room"  # no clip was open when the poll opened: resume gives lecture mode
    answers = reference(state)  # (and the lecturer's next slide at tick 19 then applies: slide 5)
    assert (answers["stage_mode"], answers["projected_slide"], answers["media_state"]) == ("lecture", "slide_5", "none")


def test_a_break_holds_the_clip_too_and_only_stop_closes_it(episode):
    state = _state(episode, 22)
    assert _add(state, "Console, take a break.", "moderator")["stage_mode"] == "break"
    answers = _add(state, "Console, resume the lecture.", "moderator")
    assert (answers["stage_mode"], answers["projected_slide"], answers["media_state"]) == ("media", "slide_4", "paused")
    assert _add(state, "Console, resume the lecture.", "moderator")["stage_mode"] == "media"
    assert _add(state, "Console, stop the video.")["stage_mode"] == "lecture"
    assert _add(state, "Console, take a break.", "moderator")["stage_mode"] == "break"
    assert _add(state, "Console, resume the lecture.", "moderator")["stage_mode"] == "lecture"


def test_a_clip_stays_held_through_a_break_called_during_the_poll(episode):
    state = _state(episode, 26)
    assert _add(state, "Console, take a break.", "moderator")["stage_mode"] == "break"
    answers = _add(state, "Console, resume the lecture.", "moderator")
    assert (answers["stage_mode"], answers["media_state"]) == ("media", "paused")
    state = _state(episode, 22)
    _add(state, "Console, pause the video.")
    _add(state, "Console, open the poll.", "moderator")
    assert _add(state, "Console, play the video.")["stage_mode"] == "poll"  # clip commands do nothing in a poll
    answers = _add(state, "Console, resume the lecture.", "moderator")
    assert (answers["stage_mode"], answers["media_state"]) == ("media", "paused")
    state = _state(episode, 26)
    assert _add(state, "Console, end the lecture.", "moderator")["stage_mode"] == "ended"
    assert _add(state, "Console, resume the lecture.", "moderator")["stage_mode"] == "ended"


def test_end_is_final(episode):
    state = _state(episode, 59)
    before = reference(state)
    for text, channel in [("Console, resume the lecture.", "moderator"), ("Console, open the poll.", "moderator"),
                          ("Console, resume recording.", "lecturer"), ("Console, slide 2.", "lecturer")]:
        assert _add(state, text, channel) == before
    state = _state(episode, 13)
    answers = _add(state, "Console, end the lecture.", "moderator")
    assert (answers["stage_mode"], answers["recording_light"], answers["timer_cue"]) == ("ended", "off", "none")


# ---------------------------------------------------------------- replay order

def test_a_late_stable_command_takes_effect_at_its_end(episode):
    state = _state(episode, 51)
    seg39, seg40 = _segment(state, 39), _segment(state, 40)
    assert (seg39["channel"], seg39["start"], seg39["end"]) == ("lecturer", 50, 50)
    assert (seg40["channel"], seg40["start"], seg40["end"]) == ("moderator", 50, 50)
    assert reference(state)["projected_slide"] == "slide_9"
    seg39["end"] = 51  # the lecturer was still speaking after the break began: the slide stays locked
    assert reference(state)["projected_slide"] == "slide_8"


@pytest.mark.parametrize("first,second,slide", [
    (("Console, next slide.", "lecturer"), ("Console, take a break.", "moderator"), "slide_9"),
    (("Console, take a break.", "moderator"), ("Console, next slide.", "lecturer"), "slide_8"),
])
def test_equal_ends_replay_in_seg_id_order(episode, first, second, slide):
    state = _state(episode, 49)
    state["now"] = 51
    _add(state, *first, start=50, end=50)
    answers = _add(state, *second, start=50, end=50)
    assert (answers["stage_mode"], answers["projected_slide"]) == ("break", slide)


# ---------------------------------------------------------------- recording

def test_recording_setting_persists_across_mode_changes(episode):
    assert [_gold(episode, t)["recording_light"] for t in range(41, 50)] == [
        "on", "paused", "paused", "paused", "paused", "paused", "paused", "paused", "on"]
    state = _state(episode, 44)
    _segment(state, 32)["words"][2]["w"] = "the"  # 'Console, pause the.' is ordinary speech
    assert reference(state)["recording_light"] == "on"


def test_recording_setting_changes_during_a_break_and_shows_after_it(episode):
    state = _state(episode, 30)
    assert reference(state)["recording_light"] == "on"
    _add(state, "Console, take a break.", "moderator")
    assert _add(state, "Console, pause recording.")["recording_light"] == "paused"
    answers = _add(state, "Console, resume the lecture.", "moderator")
    assert (answers["stage_mode"], answers["recording_light"]) == ("lecture", "paused")


def test_unpublished_slide_pauses_until_cleared_for_this_visit(episode):
    assert [_gold(episode, t)["recording_light"] for t in range(52, 60)] == [
        "paused", "paused", "paused", "on", "on", "paused", "off", "off"]
    state = _state(episode, 52)
    state["slides"]["unpublished"] = []
    assert reference(state)["recording_light"] == "on"
    state = _state(episode, 57)
    state["slides"]["unpublished"] = [10]
    assert reference(state)["recording_light"] == "on"
    state = _state(episode, 56)
    assert _add(state, "Console, record this slide.")["recording_light"] == "on"
    assert _add(state, "Console, previous slide.")["recording_light"] == "paused"  # cleared slide 10, not 9
    state = _state(episode, 49)
    _add(state, "Console, record this slide.")
    answers = _add(state, "Console, next slide.")
    assert (answers["projected_slide"], answers["recording_light"]) == ("slide_9", "paused")
    state = _state(episode, 55)
    assert _add(state, "Console, show quiet harbour trial.")["recording_light"] == "on"  # same slide: kept


def test_record_this_slide_leaves_the_setting_alone(episode):
    state = _state(episode, 52)
    _add(state, "Console, pause recording.")
    assert _add(state, "Console, record this slide.")["recording_light"] == "paused"
    assert _add(state, "Console, resume recording.")["recording_light"] == "on"
    state = _state(episode, 52)
    _add(state, "Console, record this slide.")
    assert _add(state, "Console, pause recording.")["recording_light"] == "paused"


def test_unpublished_slide_counts_in_lecture_and_media_mode_only(episode):
    state = _state(episode, 52)
    answers = _add(state, "Console, open the poll.", "moderator")
    assert (answers["stage_mode"], answers["recording_light"]) == ("poll", "on")
    assert _add(state, "Console, record this slide.")["recording_light"] == "on"
    assert _add(state, "Console, resume the lecture.", "moderator")["recording_light"] == "on"
    state = _state(episode, 52)
    _add(state, "Console, open the poll.", "moderator")
    assert _add(state, "Console, resume the lecture.", "moderator")["recording_light"] == "paused"
    state = _state(episode, 22)
    state["slides"]["unpublished"] = [4]
    assert reference(state)["recording_light"] == "paused"
    state = _state(episode, 24)
    state["slides"]["unpublished"] = [4]
    assert reference(state)["recording_light"] == "on"


# ---------------------------------------------------------------- timer

def test_timer_thresholds_count_equality(episode):
    state = _state(episode, 34)
    assert reference(state)["timer_cue"] == "none"
    state["now"] = 35
    assert reference(state)["timer_cue"] == "wrap_up"
    state = _state(episode, 35)
    state["session"]["ends_at"] = 44
    assert reference(state)["timer_cue"] == "none"
    state = _state(episode, 35)
    state["controller"]["warning_ticks"] = 7
    assert reference(state)["timer_cue"] == "none"
    state = _state(episode, 53)
    assert reference(state)["timer_cue"] == "wrap_up"
    state["now"] = 54
    assert reference(state)["timer_cue"] == "overtime"
    state = _state(episode, 54)
    state["session"]["ends_at"] = 55
    assert reference(state)["timer_cue"] == "wrap_up"


def test_only_the_ends_at_field_moves_the_schedule(episode):
    assert episode["steps"][36]["state"]["session"]["ends_at"] == 43
    assert episode["steps"][37]["state"]["session"]["ends_at"] == 54
    state = _state(episode, 37)
    state["session"]["ends_at"] = 43
    assert reference(state)["timer_cue"] == "wrap_up"
    state = _state(episode, 38)
    assert _add(state, "We are nearly out of time, so let's be quick.", "moderator")["timer_cue"] == "none"
    state = _state(episode, 34)
    assert _add(state, "We have run over.", "moderator")["timer_cue"] == "none"


def test_reference_is_pure(episode):
    state = _state(episode, 51)
    before = deepcopy(state)
    reference(state)
    assert state == before
