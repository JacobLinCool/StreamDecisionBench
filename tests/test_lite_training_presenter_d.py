"""Public-evidence checks for the presenter_d training variant (museum lecture on a raised wreck)."""

from copy import deepcopy
import re

import pytest

from streamdecisionbench.lite.core import compose
from streamdecisionbench.lite.tasks import presenter
from streamdecisionbench.lite.training import presenter_d
from streamdecisionbench.lite.training.audit import leakage
from streamdecisionbench.lite.training.presenter_d import reference, scenarios


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


def _add(state, text, speaker="Presenter", *, final=True, at=None, final_at=None):
    now = state["clock"]["now"]
    at = now if at is None else at
    state["transcript"] = [u for u in state["transcript"] if u["at"] != at]
    state["transcript"].append({"utterance_id": "counterfactual", "at": at, "speaker": speaker, "text": text,
                                "final": final, "final_at": (now if final_at is None else final_at) if final else None})
    state["transcript"].sort(key=lambda u: u["at"])
    return reference(state)


def _utterance(state, uid):
    return next(u for u in state["transcript"] if u["utterance_id"] == uid)


def test_shared_rules_schema_and_public_reference(episode):
    assert presenter_d.reference is presenter.reference
    assert episode["episode_id"] == "train_presenter_d" and episode["scenario_id"] == "presenter_d"
    assert episode["task_family"] == "presenter_voice_control" and episode["tick_seconds"] == 2.0
    assert episode["decision_spec"] == presenter.SPEC
    deck = episode["steps"][0]["state"]["deck"]
    assert episode["questions"] == presenter._questions(deck) and len(episode["questions"]) == 6
    assert len(episode["steps"]) == 60
    for tick, step in enumerate(episode["steps"]):
        assert step["t"] == tick and step["evidence"]
        assert step["state"]["clock"]["now"] == tick
        assert step["state"]["prepared"]["rules"] == presenter.RULES
        assert step["state"]["deck"] == deck
        assert "gold" not in step["state"]
        assert reference(deepcopy(step["state"])) == step["gold"]
        for question, value in step["gold"].items():
            assert value in episode["questions"][question]["criteria"]


def test_transcript_follows_the_published_asr_conventions(episode):
    finals, identity, overlap = {}, {}, False
    for step in episode["steps"]:
        now, lines = step["state"]["clock"]["now"], step["state"]["transcript"]
        assert [u["at"] for u in lines] == sorted({u["at"] for u in lines})
        for u in lines:
            assert u["at"] <= now
            assert identity.setdefault(u["utterance_id"], (u["at"], u["speaker"])) == (u["at"], u["speaker"])
            if u["final"]:
                assert u["at"] <= u["final_at"] <= now and '"' not in u["text"] and re.search(r"\w", u["text"])
                assert finals.setdefault(u["utterance_id"], u) == u
            else:
                assert u["final_at"] is None and re.fullmatch(r"[a-z ]+", u["text"])
                assert u["utterance_id"] not in finals
        for speaker in {u["speaker"] for u in lines}:
            own = [u for u in lines if u["speaker"] == speaker]
            partials = [u for u in own if not u["final"]]
            assert len(partials) <= 1 and (not partials or partials[0] is own[-1])
        assert set(identity) == {u["utterance_id"] for u in lines}
        overlap |= sum(not u["final"] for u in lines) > 1
    assert overlap
    assert all(u["final"] for u in episode["steps"][-1]["state"]["transcript"])
    assert {u["speaker"] for u in episode["steps"][-1]["state"]["transcript"]} == {"Presenter", "Host", "Audience", "Clip"}


def test_deck_names_are_distinct_plain_and_never_end_in_slide(episode):
    deck = episode["steps"][0]["state"]["deck"]
    names = [s["name"] for s in deck["slides"]]
    assert len(set(names)) == len(names) and 10 <= len(names) <= 15
    assert all(re.fullmatch(r"[a-z ]+", n) and not n.endswith("slide") and not n.startswith("the ") for n in names)
    assert [s["n"] for s in deck["slides"] if s["clip"]] == [3, 6] and deck["start_slide"] == 2


def test_story_routes_and_transitions(episode):
    decisions = [_decision(episode, t) for t in range(60)]
    changes = [t for t in range(1, 60) if decisions[t] != decisions[t - 1]]
    assert len(changes) == 39
    assert {d["mode"] for d in decisions} == {"talk", "clip", "questions", "closed"}
    assert {_gold(episode, t)["captions"] for t in range(60)} == {"presenter", "clip", "host", "audience"}
    assert {_gold(episode, t)["host_cue"] for t in range(60) if decisions[t]["mode"] == "questions"} == {
        "listen", "stand_by"}
    assert decisions[0] == {"mode": "talk", "slide": "s2", "captions": "presenter", "host_cue": "listen"}
    assert decisions[59] == {"mode": "closed", "slide": "s3", "captions": "presenter"}


def test_partial_commands_never_move_the_slide_or_change_the_mode(episode):
    assert [_gold(episode, t)["slide"] for t in (2, 3)] == ["s2", "s3"]
    assert [_gold(episode, t)["mode"] for t in (4, 5)] == ["talk", "clip"]
    assert [(_gold(episode, t)["mode"], _gold(episode, t)["slide"]) for t in (18, 19, 20)] == [
        ("clip", "s3"), ("clip", "s3"), ("talk", "s4")]
    # The partial names the lifting frame (slide 5); only the final's target, the lift animation, counts.
    assert _utterance(episode["steps"][21]["state"], "p21")["text"] == "go to the lifting frame"
    assert [_gold(episode, t)["slide"] for t in (21, 22)] == ["s4", "s6"]
    assert all(_gold(episode, t)["slide"] != "s5" for t in range(60))
    assert [_gold(episode, t)["mode"] for t in (40, 41, 42)] == ["talk", "talk", "questions"]
    assert _utterance(episode["steps"][41]["state"], "h40")["text"] == "wonderful odile lets take"
    assert [_gold(episode, t)["slide"] for t in (58, 59)] == ["s4", "s3"]
    assert _add(_state(episode, 37), "next slide", final=False)["slide"] == "s6"
    assert _add(_state(episode, 37), "play the video", final=False)["mode"] == "talk"
    assert _add(_state(episode, 37), "Play the video.")["mode"] == "clip"


def test_command_in_question_form_is_talk(episode):
    assert [(_gold(episode, t)["mode"], _gold(episode, t)["clip_state"]) for t in (15, 16, 17)] == [
        ("clip", "play")] * 3
    assert _utterance(episode["steps"][16]["state"], "p15")["text"] == "Close the video?"
    state = _state(episode, 16)
    _utterance(state, "p15")["text"] = "Close the video."
    assert (reference(state)["mode"], reference(state)["slide"]) == ("talk", "s3")
    # The chair's go-ahead is not a command, and the Host cannot close the clip anyway.
    assert _add(_state(episode, 17), "Close the video.", "Host", at=17)["mode"] == "clip"


def test_slide_command_in_clip_mode_closes_the_clip(episode):
    assert _decision(episode, 19) == {"mode": "clip", "slide": "s3", "captions": "presenter", "clip_state": "play"}
    assert _decision(episode, 20) == {"mode": "talk", "slide": "s4", "captions": "presenter", "host_cue": "listen"}
    state = _state(episode, 20)
    _utterance(state, "p18")["text"] = "Next slide? The stern post is solid oak and still sound."
    assert (reference(state)["mode"], reference(state)["slide"]) == ("clip", "s3")


def test_clip_playback_pause_and_resume(episode):
    assert [(_gold(episode, t)["mode"], _gold(episode, t)["clip_state"]) for t in (4, 5, 8)] == [
        ("talk", "none"), ("clip", "play"), ("clip", "play")]
    assert [_gold(episode, t)["clip_state"] for t in (9, 10, 11, 12, 13, 14)] == [
        "pause", "play", "pause", "pause", "pause", "play"]
    # The Clip's own "Hold it." changes nothing; the same words from the Presenter pause the clip.
    state = _state(episode, 8)
    assert reference(state)["clip_state"] == "play"
    _utterance(state, "c8")["speaker"] = "Presenter"
    assert reference(state)["clip_state"] == "pause"


def test_early_pause_follows_the_current_hypothesis_and_lapses(episode):
    assert _utterance(episode["steps"][9]["state"], "p9") == {
        "utterance_id": "p9", "at": 9, "final_at": None, "speaker": "Presenter", "text": "pause", "final": False}
    assert _utterance(episode["steps"][10]["state"], "p9")["text"] == "Pores in the oak are still full of mud."
    state = _state(episode, 9)
    answers = [_add(state, text, final=False, at=9)["clip_state"] for text in ("pause", "pores in the", "pause it")]
    assert answers == ["pause", "play", "pause"]
    assert _add(_state(episode, 9), "pause", "Audience", final=False, at=9)["clip_state"] == "play"
    assert _add(_state(episode, 9), "pause", "Clip", final=False, at=9)["clip_state"] == "play"


def test_play_needs_a_clip_on_the_current_slide(episode):
    assert [(_gold(episode, t)["mode"], _gold(episode, t)["slide"]) for t in (22, 23, 24)] == [
        ("talk", "s6"), ("talk", "s6"), ("clip", "s6")]
    state = _state(episode, 21)
    assert _add(state, "Play the video.")["mode"] == "talk"
    state["deck"]["slides"][3]["clip"] = True
    assert reference(state)["mode"] == "clip"


def test_questions_open_from_clip_mode_and_clip_commands_are_ignored_there(episode):
    assert _decision(episode, 27) == {"mode": "clip", "slide": "s6", "captions": "host", "clip_state": "play"}
    assert _decision(episode, 28) == {"mode": "questions", "slide": "s6", "captions": "host",
                                      "question_card": "waiting", "host_cue": "listen"}
    assert _gold(episode, 28)["clip_state"] == "none"
    assert [_decision(episode, t)["mode"] for t in (29, 30)] == ["questions", "questions"]
    assert _utterance(episode["steps"][30]["state"], "p29")["text"] == "Sure, close the animation."
    state = _state(episode, 30)
    _utterance(state, "p29")["text"] = "Sure, play the animation."
    assert reference(state)["mode"] == "questions"
    early = _add(_state(episode, 29), "pause", final=False, at=29)
    assert (early["mode"], early["clip_state"]) == ("questions", "none")
    # Only the Host opens questions.
    assert _add(_state(episode, 26), "Let's take one question.", "Presenter", at=26)["mode"] == "clip"


def test_a_comment_needs_no_repeat(episode):
    assert [_gold(episode, t)["question_card"] for t in (30, 31, 32, 33)] == [
        "waiting", "listening", "answer", "answer"]
    assert _gold(episode, 32)["captions"] == "audience"
    assert _decision(episode, 34) == {"mode": "talk", "slide": "s6", "captions": "presenter", "host_cue": "listen"}
    state = _state(episode, 32)
    _utterance(state, "a31")["text"] = "Did my grandad sail on her?"
    assert reference(state)["question_card"] == "repeat"


def test_stand_by_follows_current_text_until_the_host_speaks(episode):
    assert [_gold(episode, t)["host_cue"] for t in range(34, 43)] == [
        "listen", "stand_by", "listen", "listen", "stand_by", "stand_by", "listen", "listen", "listen"]
    state = _state(episode, 36)
    _utterance(state, "p35")["text"] = "every plank traces back to you"
    assert reference(state)["host_cue"] == "stand_by"
    state = _state(episode, 41)
    state["transcript"] = [u for u in state["transcript"] if u["speaker"] != "Host" or u["at"] < 38]
    assert reference(state)["host_cue"] == "stand_by"
    assert _add(_state(episode, 39), "Back to you, Kwame.", at=38)["host_cue"] == "stand_by"
    assert _add(_state(episode, 39), "Back to you, Odile.", at=38)["host_cue"] == "listen"
    assert _add(_state(episode, 39), "mm", "Audience", final=False)["host_cue"] == "stand_by"


def test_stand_by_in_questions_mode(episode):
    assert _decision(episode, 56) == {"mode": "questions", "slide": "s4", "captions": "presenter",
                                      "question_card": "repeat", "host_cue": "stand_by"}
    assert _gold(episode, 55)["host_cue"] == "listen"
    state = _state(episode, 56)
    _utterance(state, "p55")["text"] = "Not yet, she opens in the autumn. Back to you, Odile."
    assert reference(state)["host_cue"] == "listen"


def test_question_card_resets_for_each_question(episode):
    assert [_gold(episode, t)["question_card"] for t in range(42, 57)] == [
        "waiting", "waiting", "listening", "listening", "repeat", "repeat", "answer", "listening", "answer",
        "answer", "answer", "listening", "repeat", "repeat", "repeat"]
    state = _state(episode, 48)
    _utterance(state, "p47")["text"] = "Well, the question is where she was found. Back to the estuary map slide."
    assert reference(state)["question_card"] == "repeat"
    state = _state(episode, 56)
    _utterance(state, "p55")["text"] = "The question is whether she is on show. Not yet."
    assert reference(state)["question_card"] == "answer"


def test_a_floor_request_never_moves_the_slide(episode):
    assert [_gold(episode, t)["slide"] for t in (47, 48, 49, 50, 51, 52)] == ["s6", "s2", "s2", "s2", "s2", "s4"]
    assert _utterance(episode["steps"][50]["state"], "a49")["text"] == "Back to the hull survey, please."
    state = _state(episode, 50)
    _utterance(state, "a49")["speaker"] = "Presenter"
    assert reference(state)["slide"] == "s4"
    assert _add(_state(episode, 50), "Back to the hull survey, please.", "Host")["slide"] == "s2"
    assert _add(_state(episode, 50), "Go back to slide 4.", "Clip")["slide"] == "s2"


def test_session_closes_only_on_the_hosts_thanks(episode):
    assert [_gold(episode, t)["mode"] for t in (56, 57)] == ["questions", "closed"]
    assert _add(_state(episode, 56), "Let's thank Odile.")["mode"] == "questions"
    assert _add(_state(episode, 56), "Let's thank Kwame.", "Host")["mode"] == "questions"
    assert _add(_state(episode, 56), "Let's thank Odile, please.", "Host")["mode"] == "closed"


def test_after_closing_only_slide_commands_apply(episode):
    assert [_decision(episode, t) for t in (57, 59)] == [
        {"mode": "closed", "slide": "s4", "captions": "host"},
        {"mode": "closed", "slide": "s3", "captions": "presenter"}]
    # Slide 3 has a clip, but play is ignored once the session is closed, as is reopening questions.
    assert _add(_state(episode, 59), "Play the video.", at=59)["mode"] == "closed"
    assert _add(_state(episode, 59), "Let's take questions from the floor.", "Host", at=59)["mode"] == "closed"


def test_captions_follow_the_newest_onset(episode):
    assert [_gold(episode, t)["captions"] for t in (5, 6, 8, 9)] == ["presenter", "clip", "clip", "presenter"]
    assert [_gold(episode, t)["captions"] for t in (16, 17, 18)] == ["presenter", "host", "presenter"]
    assert [_gold(episode, t)["captions"] for t in (39, 40, 41)] == ["presenter", "host", "host"]
    assert episode["steps"][41]["state"]["transcript"][-2]["final_at"] == 41
    state = _state(episode, 0)
    state["transcript"] = []
    assert reference(state)["captions"] == "off"


def _plain_words(text):
    return " " + " ".join(re.findall(r"[a-z0-9]+", text.lower().replace("'", ""))) + " "


def _instance_text(scenario):
    texts = []

    def walk(value, key=None):
        if key in {"rules", "policy"}:
            return
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, dict):
            for k, v in value.items():
                walk(v, k)
        elif isinstance(value, list):
            for v in value:
                walk(v, key)

    for step in scenario["steps"]:
        walk(step["state"])
    return _plain_words(" ".join(texts))


def test_no_evaluation_content_leaks(episode):
    assert leakage([episode]) == []
    mine = _instance_text(episode)
    names = {"jun", "northgate", "kestrel valley", "aldern", "union street", "water board"}
    for scenario in presenter.scenarios():
        first = scenario["steps"][0]["state"]
        names |= {w for person in (first["session"]["presenter"], first["session"]["host"]) for w in person.split()}
        names |= {s["name"] for s in first["deck"]["slides"]}
        names.add(first["session"]["talk"])
    leaked = sorted(n for n in names if _plain_words(n) in mine)
    assert leaked == []
    # The chair never relays requests, and no one corrects a command with an "Oh, ..." afterthought.
    assert " online " not in mine and " relay" not in mine
    finals = [u for u in episode["steps"][-1]["state"]["transcript"] if u["final"]]
    assert not any(u["text"].startswith("Oh") for u in finals)


def test_reference_is_pure(episode):
    state = _state(episode, 48)
    before = deepcopy(state)
    reference(state)
    assert state == before
