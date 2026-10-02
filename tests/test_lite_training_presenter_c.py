"""Public-evidence checks for the presenter_c training variant (marine-acoustics guest lecture)."""

from copy import deepcopy
import re

import pytest

from streamdecisionbench.lite.core import compose, encode_scenario, validate_episode
from streamdecisionbench.lite.tasks import presenter
from streamdecisionbench.lite.training import presenter_c
from streamdecisionbench.lite.training.audit import check_module, leakage
from streamdecisionbench.lite.training.presenter_c import reference, scenarios


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
    """Add (or replace, by onset) one utterance in a copied state and return the reference answers."""
    now = state["clock"]["now"]
    at = now if at is None else at
    state["transcript"] = [u for u in state["transcript"] if u["at"] != at]
    state["transcript"].append({"utterance_id": "counterfactual", "at": at, "speaker": speaker, "text": text,
                                "final": final, "final_at": (now if final_at is None else final_at) if final else None})
    state["transcript"].sort(key=lambda u: u["at"])
    return reference(state)


def _retext(state, utterance_id, text):
    """Replace the text of one existing utterance in a copied state and return the reference answers."""
    for u in state["transcript"]:
        if u["utterance_id"] == utterance_id:
            u["text"] = text
    return reference(state)


def test_scenario_identity_and_shared_specification(episode):
    assert (episode["episode_id"], episode["scenario_id"], episode["task_family"]) == (
        "train_presenter_c", "presenter_c", "presenter_voice_control")
    assert episode["tick_seconds"] == 2.0 and len(episode["steps"]) == 60
    assert presenter_c.reference is presenter.reference
    deck = episode["steps"][0]["state"]["deck"]
    assert episode["questions"] == presenter._questions(deck)
    assert episode["decision_spec"] == presenter.SPEC
    for step in episode["steps"]:
        assert step["state"]["prepared"]["rules"] == presenter.RULES
    titles = {s["title"] for s in presenter.scenarios()}
    assert episode["title"] not in titles


def test_schema_and_public_reference(episode):
    assert len(episode["questions"]) == 6
    for tick, step in enumerate(episode["steps"]):
        assert step["t"] == tick
        assert step["state"]["clock"]["now"] == tick
        assert {"gold", "hidden", "answer"}.isdisjoint(step["state"])
        assert step["evidence"] and all(isinstance(e, str) and e for e in step["evidence"])
        assert reference(deepcopy(step["state"])) == step["gold"]
        for question, value in step["gold"].items():
            assert value in episode["questions"][question]["criteria"]


def test_encodes_validates_and_passes_the_training_audit(episode):
    summary = validate_episode(encode_scenario(episode))
    assert summary["routes_unseen"] == []
    assert 18 <= summary["decision_transitions"] <= 28
    assert leakage([episode]) == []
    assert check_module(presenter_c)["episodes"][0]["episode_id"] == "train_presenter_c"


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


SMALL = "one two three four five six seven eight nine".split()
LARGE = ("ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty "
         "fifty sixty seventy eighty ninety hundred thousand").split()


def test_finals_write_slide_numbers_and_large_numbers_as_digits(episode):
    lines = episode["steps"][-1]["state"]["transcript"]
    for u in lines:
        words = presenter._words(u["text"])
        if u["final"]:
            assert not set(words) & set(LARGE), u["text"]
            assert not any(a == "slide" and b in SMALL for a, b in zip(words, words[1:])), u["text"]
            assert not re.search(r"\b[0-9]\b", u["text"].replace("slide 6", "").replace("slide 13", "")), u["text"]
    partials = {u["utterance_id"]: u["text"] for s in episode["steps"] for u in s["state"]["transcript"] if not u["final"]}
    assert partials["p0"] == "this tag rode on a sperm whale for fourteen hours"
    assert partials["p15"] == "go to slide six"


def test_deck_names_are_distinct_plain_new_and_never_end_in_slide(episode):
    deck = episode["steps"][0]["state"]["deck"]
    names = [s["name"] for s in deck["slides"]]
    assert 11 <= len(names) <= 14 and len(set(names)) == len(names)
    assert all(re.fullmatch(r"[a-z ]+", n) and not n.endswith("slide") for n in names)
    assert [s["n"] for s in deck["slides"] if s["clip"]] == [4, 9]
    eval_decks = [s["steps"][0]["state"]["deck"] for s in presenter.scenarios()]
    assert not set(names) & {s["name"] for d in eval_decks for s in d["slides"]}
    assert deck["start_slide"] == 4 and deck["start_slide"] not in {d["start_slide"] for d in eval_decks}
    assert all(step["state"]["deck"] == deck for step in episode["steps"])


KEY_TICKS = {
    0: {"mode": "talk", "slide": "s4", "captions": "presenter", "host_cue": "listen"},
    2: {"mode": "talk", "slide": "s4", "captions": "presenter", "host_cue": "listen"},
    3: {"mode": "clip", "slide": "s4", "captions": "presenter", "clip_state": "play"},
    4: {"mode": "clip", "slide": "s4", "captions": "clip", "clip_state": "play"},
    5: {"mode": "clip", "slide": "s4", "captions": "presenter", "clip_state": "pause"},
    6: {"mode": "clip", "slide": "s4", "captions": "presenter", "clip_state": "play"},
    7: {"mode": "clip", "slide": "s4", "captions": "presenter", "clip_state": "play"},
    8: {"mode": "clip", "slide": "s4", "captions": "presenter", "clip_state": "pause"},
    9: {"mode": "clip", "slide": "s4", "captions": "presenter", "clip_state": "pause"},
    12: {"mode": "clip", "slide": "s4", "captions": "presenter", "clip_state": "play"},
    13: {"mode": "clip", "slide": "s4", "captions": "presenter", "clip_state": "play"},
    14: {"mode": "talk", "slide": "s4", "captions": "presenter", "host_cue": "listen"},
    15: {"mode": "talk", "slide": "s4", "captions": "presenter", "host_cue": "listen"},
    16: {"mode": "talk", "slide": "s6", "captions": "presenter", "host_cue": "listen"},
    19: {"mode": "talk", "slide": "s6", "captions": "presenter", "host_cue": "listen"},
    20: {"mode": "talk", "slide": "s6", "captions": "presenter", "host_cue": "listen"},
    22: {"mode": "talk", "slide": "s9", "captions": "presenter", "host_cue": "listen"},
    23: {"mode": "clip", "slide": "s9", "captions": "presenter", "clip_state": "play"},
    26: {"mode": "talk", "slide": "s10", "captions": "presenter", "host_cue": "listen"},
    29: {"mode": "talk", "slide": "s10", "captions": "host", "host_cue": "listen"},
    30: {"mode": "questions", "slide": "s10", "captions": "host", "question_card": "waiting", "host_cue": "listen"},
    32: {"mode": "questions", "slide": "s10", "captions": "audience", "question_card": "listening", "host_cue": "listen"},
    34: {"mode": "questions", "slide": "s10", "captions": "audience", "question_card": "repeat", "host_cue": "listen"},
    35: {"mode": "questions", "slide": "s10", "captions": "presenter", "question_card": "repeat", "host_cue": "listen"},
    37: {"mode": "questions", "slide": "s9", "captions": "presenter", "question_card": "repeat", "host_cue": "listen"},
    38: {"mode": "questions", "slide": "s9", "captions": "presenter", "question_card": "repeat", "host_cue": "listen"},
    39: {"mode": "questions", "slide": "s9", "captions": "presenter", "question_card": "answer", "host_cue": "listen"},
    42: {"mode": "questions", "slide": "s9", "captions": "audience", "question_card": "answer", "host_cue": "listen"},
    43: {"mode": "talk", "slide": "s9", "captions": "presenter", "host_cue": "listen"},
    45: {"mode": "talk", "slide": "s11", "captions": "presenter", "host_cue": "listen"},
    46: {"mode": "talk", "slide": "s11", "captions": "presenter", "host_cue": "listen"},
    47: {"mode": "talk", "slide": "s11", "captions": "presenter", "host_cue": "stand_by"},
    48: {"mode": "talk", "slide": "s11", "captions": "presenter", "host_cue": "listen"},
    49: {"mode": "talk", "slide": "s11", "captions": "presenter", "host_cue": "stand_by"},
    51: {"mode": "talk", "slide": "s11", "captions": "presenter", "host_cue": "stand_by"},
    52: {"mode": "talk", "slide": "s11", "captions": "host", "host_cue": "listen"},
    53: {"mode": "closed", "slide": "s11", "captions": "host"},
    55: {"mode": "closed", "slide": "s11", "captions": "host"},
    56: {"mode": "closed", "slide": "s13", "captions": "presenter"},
    57: {"mode": "closed", "slide": "s13", "captions": "presenter"},
    59: {"mode": "closed", "slide": "s13", "captions": "presenter"},
}


@pytest.mark.parametrize("tick", sorted(KEY_TICKS))
def test_key_ticks_of_the_lecture(episode, tick):
    assert _decision(episode, tick) == KEY_TICKS[tick]


def test_inactive_branch_answers_are_none(episode):
    for step in episode["steps"]:
        gold = step["gold"]
        if gold["mode"] != "clip":
            assert gold["clip_state"] == "none"
        if gold["mode"] != "questions":
            assert gold["question_card"] == "none"
        if gold["mode"] not in {"talk", "questions"}:
            assert gold["host_cue"] == "none"


def test_partial_commands_wait_for_the_final(episode):
    transcript = lambda t: {u["utterance_id"]: u for u in episode["steps"][t]["state"]["transcript"]}
    assert transcript(2)["p2"]["text"] == "play the video" and _gold(episode, 2)["mode"] == "talk"
    assert transcript(15)["p15"]["text"] == "go to slide six" and _gold(episode, 15)["slide"] == "s4"
    assert transcript(13)["p13"]["text"] == "close the video" and _gold(episode, 13)["mode"] == "clip"
    assert transcript(29)["h29"]["text"] == "lets take questions" and _gold(episode, 29)["mode"] == "talk"
    # The Host's partial is already a whole thanks command (lead-in, phrase, first name); only its final closes.
    deck = episode["steps"][0]["state"]["deck"]
    assert transcript(52)["h52"]["text"] == "right lets thank tamsin"
    assert presenter._command(transcript(52)["h52"]["text"], deck, "Tamsin") == ("thank", None)
    assert [_gold(episode, t)["mode"] for t in (52, 53)] == ["talk", "closed"]
    # A whole-command partial finalised as talk never moves the slide.
    assert transcript(19)["p19"]["text"] == "go to the spectrogram reading"
    assert [_gold(episode, t)["slide"] for t in (19, 20, 21)] == ["s6", "s6", "s6"]
    # A '?' echo of a command form is talk; the later sentence of the same final moves the slide.
    assert transcript(35)["p35"]["text"] == "back to the reef chorus"
    assert [_gold(episode, t)["slide"] for t in (35, 36, 37)] == ["s10", "s10", "s9"]


def test_early_pause_needs_the_presenters_newest_partial(episode):
    # The clip narrator's partial "pause" is not the Presenter's speech.
    assert _gold(episode, 4)["clip_state"] == "play"
    assert _add(_state(episode, 4), "pause", final=False, at=4)["clip_state"] == "pause"
    # Early pause on a Presenter partial, lapsing when the hypothesis grows into talk.
    assert [_gold(episode, t)["clip_state"] for t in (4, 5, 6, 7)] == ["play", "pause", "play", "play"]
    assert _retext(_state(episode, 7), "p5", "Pause the video.")["clip_state"] == "pause"
    # The final pause holds while she talks over the paused frame, until the final resume.
    assert [_gold(episode, t)["clip_state"] for t in (8, 9, 10, 11, 12)] == ["pause"] * 4 + ["play"]
    assert _retext(_state(episode, 12), "p12", "Okay, resume?")["clip_state"] == "pause"
    # An Audience or Clip partial in pause form never pauses the clip.
    assert _add(_state(episode, 7), "hold it", "Audience", final=False, at=7)["clip_state"] == "play"
    assert _add(_state(episode, 7), "pause it there", "Clip", final=False, at=7)["clip_state"] == "play"


def test_clip_rules_use_the_deck_mode_and_slide_commands(episode):
    state = _state(episode, 3)
    state["deck"]["start_slide"] = 5
    assert (reference(state)["mode"], reference(state)["slide"]) == ("talk", "s5")
    # Play only acts from talk on a clip slide or in clip mode: not in questions mode.
    assert _add(_state(episode, 41), "Play it.")["mode"] == "questions"
    assert _add(_state(episode, 44), "Play it.", at=44)["mode"] == "clip"
    # A slide command in clip mode closes the clip.
    assert (_gold(episode, 25)["mode"], _gold(episode, 26)["mode"], _gold(episode, 26)["slide"]) == ("clip", "talk", "s10")
    assert _retext(_state(episode, 14), "p13", "Close the video?")["mode"] == "clip"


@pytest.mark.parametrize("text,speaker,slide", [
    ("Go to the spectrogram reading.", "Presenter", "s7"),
    ("Go to the spectrogram reading slide, please.", "Presenter", "s7"),
    ("Go to the spectrogram reading.", "Host", "s6"),
    ("Go to the spectrogram reading.", "Audience", "s6"),
    ("Go to the spectrograms.", "Presenter", "s6"),
    ("Go to slide 14.", "Presenter", "s6"),
    ("So, previous slide.", "Presenter", "s5"),
    ("Sorry, previous slide.", "Presenter", "s6"),
])
def test_only_whole_final_presenter_commands_move_the_slide(episode, text, speaker, slide):
    state = _state(episode, 20)
    if speaker == "Presenter":
        answers = _retext(state, "p19", text)
    else:
        answers = _add(state, text, speaker, at=20)
    assert answers["slide"] == slide


def test_sentence_order_and_question_marks_in_one_final(episode):
    assert _gold(episode, 37)["slide"] == "s9"
    assert _retext(_state(episode, 37), "p35", "Back to the reef chorus. Of course. Previous slide.")["slide"] == "s8"
    assert _retext(_state(episode, 37), "p35", "Back to the reef chorus? Of course.")["slide"] == "s10"


def test_slide_commands_apply_in_closed_mode_within_the_deck(episode):
    assert _gold(episode, 55)["slide"] == "s11"
    assert _gold(episode, 56)["slide"] == _gold(episode, 57)["slide"] == "s13"
    state = _state(episode, 57)
    assert _add(state, "Previous slide.", at=57)["slide"] == "s12"
    assert _add(_state(episode, 59), "Play it.", at=59)["mode"] == "closed"
    assert _add(_state(episode, 55), "Go to the acknowledgements.", "Host", at=55)["slide"] == "s11"


def test_session_commands_need_the_host_the_final_and_the_first_name(episode):
    assert [_gold(episode, t)["mode"] for t in (29, 30)] == ["talk", "questions"]
    assert _retext(_state(episode, 53), "h52", "Right, let's thank Elliot.")["mode"] == "talk"
    assert _retext(_state(episode, 53), "h52", "Right, let's thank Tamsin Valdez.")["mode"] == "talk"
    assert _retext(_state(episode, 53), "h52", "Right. Let's thank Tamsin.")["mode"] == "closed"
    assert _add(_state(episode, 51), "Let's thank Tamsin.", at=51)["mode"] == "talk"
    assert _add(_state(episode, 28), "Let's take questions from the floor.", "Audience", at=28)["mode"] == "talk"
    # Either the Presenter or the Host can end questions; the Audience cannot.
    assert _add(_state(episode, 42), "Okay, let's move on.", "Host", at=42)["mode"] == "talk"
    assert _add(_state(episode, 42), "Okay, let's move on.", "Audience", at=42)["mode"] == "questions"


def _final_at(state, utterance_id, tick):
    for u in state["transcript"]:
        if u["utterance_id"] == utterance_id:
            u["final_at"] = tick
    return reference(state)["mode"]


def test_replay_orders_commands_by_final_arrival(episode):
    state = _state(episode, 31)
    state["transcript"].append({"utterance_id": "p30", "at": 30, "final_at": 30, "speaker": "Presenter",
                                "text": "Okay, let's move on.", "final": True})
    state["transcript"].sort(key=lambda u: u["at"])
    # Opening final at 30, move-on final at 30: same arrival, the earlier onset (the opening) applies first.
    assert reference(state)["mode"] == "talk"
    # Opening final only at 31: the move-on arrived first, while still in talk, and is ignored.
    assert _final_at(state, "h29", 31) == "questions"
    # Both at 31: tie broken by onset again, so the opening then the move-on.
    assert _final_at(state, "p30", 31) == "talk"


def test_question_card_needs_a_final_question_and_a_final_repetition(episode):
    assert [_gold(episode, t)["question_card"] for t in (30, 31, 32, 33, 34, 37, 38, 39, 42)] == [
        "waiting", "waiting", "listening", "listening", "repeat", "repeat", "repeat", "answer", "answer"]
    assert _retext(_state(episode, 34), "a32", "Lovely recording.")["question_card"] == "answer"
    assert _retext(_state(episode, 39), "p38", "Also, the question is where the fish calls are.")["question_card"] == "repeat"
    assert _retext(_state(episode, 39), "p38", "Now the question is where the fish calls are.")["question_card"] == "answer"
    assert _retext(_state(episode, 42), "a42", "Thanks, is the data online?")["question_card"] == "repeat"
    assert _add(_state(episode, 42), "Any more questions?", "Host", at=42)["question_card"] == "answer"
    assert _add(_state(episode, 31), "Anyone?", "Host", at=31)["question_card"] == "waiting"


def test_stand_by_follows_current_text_until_the_host_speaks(episode):
    assert [_gold(episode, t)["host_cue"] for t in (45, 46, 47, 48, 49, 50, 51, 52)] == [
        "listen", "listen", "stand_by", "listen", "stand_by", "stand_by", "stand_by", "listen"]
    # The partial's 'back to you' is a mishearing of a name; the final's 'back to Hugh' is not the hand-back words.
    lines = {u["utterance_id"]: u for u in episode["steps"][47]["state"]["transcript"]}
    assert lines["p46"]["text"].endswith("go back to you") and not lines["p46"]["final"]
    assert _retext(_state(episode, 48), "p46",
                   "The harbour master lent us his pier, so the first copies go back to you.")["host_cue"] == "stand_by"
    state = _state(episode, 50)
    state["session"]["host"] = "Elliott Fairbanks"
    assert reference(state)["host_cue"] == "listen"
    assert _retext(_state(episode, 50), "p49", "Back to you in a minute, Elliot.")["host_cue"] == "listen"
    assert _add(_state(episode, 51), "mm", "Audience", final=False, at=51)["host_cue"] == "stand_by"
    assert _add(_state(episode, 51), "Back to you, Tamsin.", "Host", at=51)["host_cue"] == "listen"
    assert _add(_state(episode, 41), "That's all. Back to you, Elliot.", at=41)["host_cue"] == "stand_by"


def test_captions_follow_the_newest_onset(episode):
    assert [_gold(episode, t)["captions"] for t in (3, 4, 5, 6)] == ["presenter", "clip", "presenter", "presenter"]
    lines = {u["utterance_id"]: u for u in episode["steps"][6]["state"]["transcript"]}
    assert lines["c4"]["final_at"] == 6 and not lines["p5"]["final"]
    assert [_gold(episode, t)["captions"] for t in (28, 29, 31, 32, 35, 42, 43, 52, 56)] == [
        "presenter", "host", "host", "audience", "presenter", "audience", "presenter", "host", "presenter"]
    state = _state(episode, 0)
    state["transcript"] = []
    assert reference(state)["captions"] == "off"


def test_reference_is_pure(episode):
    for tick in (5, 37, 50):
        state = _state(episode, tick)
        before = deepcopy(state)
        reference(state)
        assert state == before
