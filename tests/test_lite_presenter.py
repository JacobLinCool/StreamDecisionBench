"""Public-evidence counterfactuals for the two voice-controlled presentations."""

from copy import deepcopy
import re

import pytest

from streamdecisionbench.lite.tasks.presenter import reference, scenarios


@pytest.fixture(scope="module")
def episodes():
    return scenarios()


def _state(episodes, scenario, tick):
    return deepcopy(episodes[scenario]["steps"][tick]["state"])


def _gold(episodes, scenario, tick):
    return episodes[scenario]["steps"][tick]["gold"]


def _add(state, text, speaker="Presenter", *, final=True, at=None, final_at=None):
    now = state["clock"]["now"]
    at = now if at is None else at
    state["transcript"] = [u for u in state["transcript"] if u["at"] != at]
    state["transcript"].append({"utterance_id": "counterfactual", "at": at, "speaker": speaker, "text": text,
                                "final": final, "final_at": (now if final_at is None else final_at) if final else None})
    state["transcript"].sort(key=lambda u: u["at"])
    return reference(state)


def test_presenter_schema_and_public_reference(episodes):
    assert len(episodes) == 2
    for episode in episodes:
        assert len(episode["questions"]) == 6
        assert len(episode["steps"]) == 60
        assert episode["tick_seconds"] == 2.0
        for tick, step in enumerate(episode["steps"]):
            assert step["t"] == tick
            assert step["state"]["clock"]["now"] == tick
            assert "gold" not in step["state"]
            assert reference(deepcopy(step["state"])) == step["gold"]
            for question, value in step["gold"].items():
                assert value in episode["questions"][question]["criteria"]


def test_transcript_follows_the_published_asr_conventions(episodes):
    for episode in episodes:
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


@pytest.mark.parametrize("text,speaker,slide", [
    ("Next slide.", "Host", "s11"), ("Next slide.", "Audience", "s11"), ("Next slide?", "Presenter", "s11"),
    ("Don't go to the next slide yet.", "Presenter", "s11"), ("Go to the budget slide.", "Presenter", "s11"),
    ("Go to slide 30.", "Presenter", "s11"), ("Go to slide ².", "Presenter", "s11"),
    ("Okay, previous slide, please.", "Presenter", "s10"), ("That is the budget. Next slide.", "Presenter", "s12"),
    ("Next slide , please.", "Presenter", "s12"), ("Please, next slide.", "Presenter", "s11"),
    ("Okay: next slide.", "Presenter", "s11"), ("Next slide!?", "Presenter", "s11"),
])
def test_only_whole_final_presenter_commands_move_the_slide(episodes, text, speaker, slide):
    assert _add(_state(episodes, 0, 12), text, speaker)["slide"] == slide


def test_partial_commands_never_move_the_slide_or_start_the_clip(episodes):
    assert _add(_state(episodes, 0, 12), "next slide", final=False)["slide"] == "s11"
    assert [_gold(episodes, 0, t)["slide"] for t in (8, 9)] == ["s6", "s11"]
    assert episodes[0]["steps"][8]["state"]["transcript"][-1]["text"] == "go to slide seven"
    assert _add(_state(episodes, 0, 15), "play it", final=False)["mode"] == "talk"
    assert _gold(episodes, 0, 26)["clip_state"] == "pause" and _gold(episodes, 0, 27)["clip_state"] == "play"
    assert _gold(episodes, 1, 46)["slide"] == _gold(episodes, 1, 47)["slide"] == "s10"


def test_early_pause_follows_the_current_hypothesis_and_lapses(episodes):
    assert _gold(episodes, 0, 22)["clip_state"] == "pause"
    assert [_gold(episodes, 0, t)["clip_state"] for t in (28, 29, 30)] == ["play", "pause", "play"]
    assert [_gold(episodes, 1, t)["clip_state"] for t in (10, 11, 12)] == ["play", "pause", "play"]
    assert episodes[1]["steps"][12]["state"]["transcript"][-1]["final"]
    assert _gold(episodes, 1, 17)["clip_state"] == "pause"
    assert _add(_state(episodes, 0, 20), "pause it", "Clip", final=False)["clip_state"] == "play"
    assert _add(_state(episodes, 0, 28), "pause it", "Audience", final=False)["clip_state"] == "play"
    state = _state(episodes, 0, 28)
    answers = []
    for text in ("pause it", "pause is", "pause it"):
        answers.append(_add(state, text, final=False, at=28)["clip_state"])
    assert answers == ["pause", "play", "pause"]
    assert _add(state, "watch the top", "Clip", final=False, at=29)["clip_state"] == "pause"


def test_deck_names_are_distinct_plain_and_never_end_in_slide(episodes):
    for episode in episodes:
        names = [s["name"] for s in episode["steps"][0]["state"]["deck"]["slides"]]
        assert len(set(names)) == len(names)
        assert all(re.fullmatch(r"[a-z ]+", n) and not n.endswith("slide") for n in names)


def test_clip_rules_use_the_deck_and_mode(episodes):
    assert (_gold(episodes, 0, 21)["mode"], _gold(episodes, 0, 21)["slide"]) == ("clip", "s7")
    assert _gold(episodes, 1, 5)["mode"] == "talk"
    assert (_gold(episodes, 1, 20)["mode"], _gold(episodes, 1, 20)["slide"]) == ("talk", "s8")
    state = _state(episodes, 0, 47)
    _add(state, "Go back to the demo.", at=47)
    state["clock"]["now"] = 48
    assert _add(state, "Play the video.", at=48)["mode"] == "questions"


def test_session_commands_need_the_host_and_the_final(episodes):
    assert _gold(episodes, 0, 45)["mode"] == "talk" and _gold(episodes, 0, 46)["mode"] == "questions"
    assert _add(_state(episodes, 0, 55), "Let's thank Mira.")["mode"] == "questions"
    assert _add(_state(episodes, 0, 55), "Let's thank our volunteers.", "Host")["mode"] == "questions"
    assert _add(_state(episodes, 0, 41), "Let's take questions after the break.", "Host")["mode"] == "talk"
    assert _gold(episodes, 1, 45)["slide"] == "s10"
    assert _add(_state(episodes, 0, 59), "Let's take questions.", "Host")["mode"] == "closed"
    state = _state(episodes, 1, 55)
    state["session"]["presenter"] = "Inés Harrow"
    assert _add(state, "Let's thank Inés.", "Host", at=56)["mode"] == "closed"
    assert _add(_state(episodes, 0, 55), "Let's thank Mira, please.", "Host")["mode"] == "closed"
    assert _gold(episodes, 0, 57)["mode"] == "closed" and episodes[0]["steps"][57]["state"]["transcript"][-1]["final"]


def test_replay_orders_commands_by_final_arrival(episodes):
    state = _state(episodes, 0, 41)
    state["clock"]["now"] = 46
    state["transcript"] += [
        {"utterance_id": "h44", "at": 44, "final_at": 46, "speaker": "Host", "text": "Let's take questions.", "final": True},
        {"utterance_id": "p45", "at": 45, "final_at": 45, "speaker": "Presenter", "text": "Let's move on.", "final": True}]
    assert reference(state)["mode"] == "questions"


def test_question_card_needs_final_question_and_final_repetition(episodes):
    assert [_gold(episodes, 0, t)["question_card"] for t in (46, 48, 50, 52, 53)] == [
        "waiting", "listening", "repeat", "repeat", "answer"]
    assert _gold(episodes, 1, 31)["question_card"] == "repeat"
    state = _state(episodes, 0, 50)
    state["transcript"][-1]["text"] = "Nice demo."
    assert reference(state)["question_card"] == "answer"
    assert _add(_state(episodes, 0, 47), "Any questions?", "Host")["question_card"] == "waiting"
    assert _add(_state(episodes, 0, 51), "Thanks.", "Audience")["question_card"] == "repeat"
    state = _state(episodes, 0, 50)
    state["transcript"][-1]["text"] = "Does the decoder work offline? I ask for privacy."
    assert reference(state)["question_card"] == "repeat"
    assert _add(_state(episodes, 0, 51), "Let's take one question.", "Host")["question_card"] == "repeat"


def test_stand_by_follows_current_text_until_the_host_speaks(episodes):
    assert [_gold(episodes, 0, t)["host_cue"] for t in (36, 37, 42, 44, 45)] == [
        "stand_by", "listen", "stand_by", "stand_by", "listen"]
    assert [_gold(episodes, 1, t)["host_cue"] for t in (38, 39, 40)] == ["stand_by", "listen", "listen"]
    assert _add(_state(episodes, 0, 41), "Finance will get back to you by email.")["host_cue"] == "listen"
    assert _add(_state(episodes, 0, 41), "We never went back. To you, it may look slow.")["host_cue"] == "listen"
    for host in ("Tomás Ruud", "Jean-Luc Ruud"):
        state = _state(episodes, 0, 41)
        state["session"]["host"] = host
        assert _add(state, f"That's all. Back to you, {host.split()[0]}.")["host_cue"] == "stand_by"
    assert _add(_state(episodes, 0, 44), "wow", "Audience", final=False)["host_cue"] == "stand_by"
    assert _add(_state(episodes, 0, 41), "Back to you, Mira.", "Host")["host_cue"] == "listen"
    assert _add(_state(episodes, 0, 44), "one more thing", final=False)["host_cue"] == "listen"


def test_captions_follow_the_newest_onset(episodes):
    assert _gold(episodes, 0, 0)["captions"] == "presenter"
    assert _gold(episodes, 0, 19)["captions"] == "clip"
    assert [_gold(episodes, 0, t)["captions"] for t in (28, 29, 30)] == ["clip", "presenter", "presenter"]
    assert [_gold(episodes, 1, t)["captions"] for t in (21, 22, 23, 24)] == ["presenter", "host", "host", "host"]
    assert _gold(episodes, 0, 30)["clip_state"] == "play" and _gold(episodes, 1, 24)["mode"] == "questions"
    state = _state(episodes, 0, 0)
    state["transcript"] = []
    assert reference(state)["captions"] == "off"


def test_reference_is_pure(episodes):
    state = _state(episodes, 0, 30)
    before = deepcopy(state)
    reference(state)
    assert state == before
