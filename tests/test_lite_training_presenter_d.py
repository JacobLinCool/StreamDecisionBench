"""Public-evidence checks for the presenter_d training variant (voice-run gallery tour of a raised oyster smack)."""

from copy import deepcopy
from pathlib import Path
import re

import pytest

from streamdecisionbench.lite.core import compose, encode_scenario, validate_episode
from streamdecisionbench.lite.tasks import presenter as evaluation
from streamdecisionbench.lite.training import presenter_d
from streamdecisionbench.lite.training.audit import MAX_LAYOUT_OVERLAP, layout_overlap, leakage, spec_overlap
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


def _entry(state, turn_id):
    return next(e for e in state["asr"]["log"] if e["turn_id"] == turn_id)


def _phrases(*texts):
    return [{"words": t.removesuffix("?"), "question": t.endswith("?")} for t in texts]


def _finish(state, role, *texts, began=None, ended=None):
    """Append a counterfactual finished turn (it finishes last) and return the reference answers."""
    tick = state["tick"]
    ended = tick if ended is None else ended
    log = state["asr"]["log"]
    log.append({"seq": len(log) + 1, "turn_id": f"cf-{len(log)}", "role": role,
                "began": ended if began is None else began, "ended": ended, "phrases": _phrases(*texts)})
    return reference(state)


def _hear(state, role, words, stable=None, began=None):
    """Put a counterfactual live hypothesis in a role's slot and return the reference answers."""
    tick = state["tick"]
    state["asr"]["live"][role] = {"turn_id": f"cf-{role}", "began": tick if began is None else began,
                                  "revised": tick, "words": words,
                                  "stable": len(words.split()) if stable is None else stable}
    return reference(state)


def _words(text):
    return re.findall(r"[a-z0-9]+", text.lower())


# --- shape, purity, specification ---------------------------------------------------------------


def test_scenario_shape_and_full_gold_reproduction(episode):
    assert episode["episode_id"] == "train_presenter_d" and episode["scenario_id"] == "presenter_d"
    assert episode["task_family"] == "presenter_voice_control" and episode["tick_seconds"] == 2.0
    assert len(episode["steps"]) == 60 and len(episode["questions"]) == 8
    summary = validate_episode(encode_scenario(episode))
    assert summary["decision_transitions"] == 35 and summary["routes_unseen"] == []
    for tick, step in enumerate(episode["steps"]):
        assert step["t"] == tick and step["state"]["tick"] == tick
        assert step["evidence"] and all(isinstance(e, str) and e for e in step["evidence"])
        assert step["state"]["rules"] == presenter_d.RULES
        assert not {"gold", "hidden", "answer"} & set(step["state"])
        state = deepcopy(step["state"])
        assert reference(state) == step["gold"] and state == step["state"]
        for question, value in step["gold"].items():
            assert value in episode["questions"][question]["criteria"]


def test_inactive_branch_answers_are_none_and_active_ones_are_not(episode):
    spec = episode["decision_spec"]
    assert set(spec["branches"]) == set(episode["questions"]["scene"]["criteria"])
    for step in episode["steps"]:
        active = set(compose(spec, step["gold"]))
        for question, value in step["gold"].items():
            assert (value != "none") == (question in active), (step["t"], question)


def test_module_writes_its_own_specification(episode):
    source = Path(presenter_d.__file__).read_text()
    assert "lite.tasks" not in source and "import presenter" not in source
    assert leakage([episode]) == [] and spec_overlap([episode]) == []
    assert layout_overlap(episode) <= MAX_LAYOUT_OVERLAP
    assert all(set(step["state"]) == {"rules", "setting", "tick", "gallery", "asr", "handsets"}
               for step in episode["steps"])
    assert not set(episode["questions"]) & set(evaluation.scenarios()[0]["questions"])
    # Well below the audit's ten-word limit: no run of six words is shared with the evaluation rules or instructions.
    texts = list(evaluation.RULES) + [q["instructions"] for s in evaluation.scenarios() for q in s["questions"].values()]
    runs = {" ".join(w[i:i + 6]) for t in texts for w in [_words(t)] for i in range(len(w) - 5)}
    own = list(presenter_d.RULES) + [q["instructions"] for q in episode["questions"].values()]
    assert not {" ".join(w[i:i + 6]) for t in own for w in [_words(t)] for i in range(len(w) - 5)} & runs


def test_reference_is_pure(episode):
    for tick in (0, 16, 33, 38, 46, 59):
        state = _state(episode, tick)
        before = deepcopy(state)
        reference(state)
        assert state == before


# --- stated recogniser conventions ---------------------------------------------------------------


def test_states_are_causal_cumulative_and_follow_the_recogniser_conventions(episode):
    first = episode["steps"][0]["state"]
    previous, overlap, later_began_earlier_finished, never_live = None, False, False, set()
    seen_live = set()
    words = r"[a-z]+(?: [a-z]+)*"
    for step in episode["steps"]:
        state, tick = step["state"], step["t"]
        live, log = state["asr"]["live"], state["asr"]["log"]
        assert state["gallery"] == first["gallery"] and state["setting"] == first["setting"]
        assert set(live) == {"guide", "visitor", "staff", "film"}
        assert [e["seq"] for e in log] == list(range(1, len(log) + 1))
        assert [e["ended"] for e in log] == sorted(e["ended"] for e in log)
        for entry in log:
            assert entry["began"] <= entry["ended"] <= tick
            assert all(re.fullmatch(words, p["words"]) and isinstance(p["question"], bool) for p in entry["phrases"])
        for role, turn in live.items():
            if turn is None:
                continue
            seen_live.add(turn["turn_id"])
            assert turn["began"] <= turn["revised"] <= tick and turn["turn_id"] not in {e["turn_id"] for e in log}
            assert re.fullmatch(words, turn["words"]) and 0 <= turn["stable"] <= len(turn["words"].split())
        overlap |= sum(t is not None for t in live.values()) > 1
        if previous:
            assert log[:len(previous["asr"]["log"])] == previous["asr"]["log"]
            for role, old in previous["asr"]["live"].items():
                if old is None:
                    continue
                kept = old["words"].split()[:old["stable"]]
                new = live[role]
                if new is not None and new["turn_id"] == old["turn_id"]:
                    assert new["stable"] >= old["stable"] and new["words"].split()[:old["stable"]] == kept
                else:
                    done = _entry(state, old["turn_id"])
                    assert " ".join(p["words"] for p in done["phrases"]).split()[:old["stable"]] == kept
        previous = state
    log = episode["steps"][-1]["state"]["asr"]["log"]
    never_live = {e["turn_id"] for e in log} - seen_live
    later_began_earlier_finished = any(a["began"] < b["began"] and a["seq"] > b["seq"] for a in log for b in log)
    assert overlap and later_began_earlier_finished and {"g-11", "g-37", "v-38"} <= never_live
    names = [s["name"].split() for s in first["gallery"]["stops"]]
    assert all(a == b or a[:len(b)] != b for a in names for b in names)
    assert [s["number"] for s in first["gallery"]["stops"]] == list(range(1, 9))


def test_handsets_are_informational(episode):
    assert [_state(episode, t)["handsets"]["working"] for t in (16, 17, 19, 20)] == [18, 17, 17, 18]
    state = _state(episode, 30)
    state["handsets"] = {"caption_language": "Dutch", "issued": 3, "working": 0}
    assert reference(state) == _gold(episode, 30)


# --- the story ------------------------------------------------------------------------------------


def test_story_reaches_every_route_and_most_branch_values(episode):
    values = {q: {_gold(episode, t)[q] for t in range(60)} for q in episode["questions"]}
    assert values["scene"] == {"at_stop", "film", "questions", "paused", "finished"}
    assert values["stop"] == {"estuary", "bell", "hull", "lab", "terrace"}
    assert values["caption_source"] == {"blank", "guide", "visitor", "film"}
    assert values["guide_prompt"] == {"on_time", "move_along", "wrap_up", "none"}
    assert values["screen_warmup"] == {"idle", "bell", "terrace", "hull", "lab", "none"}
    assert values["film_audio"] == {"full", "ducked", "none"}
    assert values["question_queue"] == {"empty", "one", "several", "none"}
    assert values["held_scene"] == {"film", "at_stop", "none"}
    assert [_gold(episode, t)["scene"] for t in (0, 11, 17, 34, 46, 57)] == [
        "at_stop", "film", "paused", "questions", "paused", "finished"]
    assert _decision(episode, 0) == {"scene": "at_stop", "stop": "estuary", "caption_source": "blank",
                                     "guide_prompt": "on_time", "screen_warmup": "idle"}
    assert _decision(episode, 59) == {"scene": "finished", "stop": "terrace", "caption_source": "guide"}


def test_key_ticks(episode):
    assert _decision(episode, 5) == {"scene": "at_stop", "stop": "estuary", "caption_source": "guide",
                                     "guide_prompt": "on_time", "screen_warmup": "bell"}
    assert _decision(episode, 14) == {"scene": "film", "stop": "bell", "caption_source": "visitor",
                                      "film_audio": "full"}
    assert _decision(episode, 15) == {"scene": "film", "stop": "bell", "caption_source": "guide",
                                      "film_audio": "ducked"}
    assert _decision(episode, 17) == {"scene": "paused", "stop": "bell", "caption_source": "film",
                                      "held_scene": "film"}
    assert _decision(episode, 23) == {"scene": "at_stop", "stop": "bell", "caption_source": "guide",
                                      "guide_prompt": "move_along", "screen_warmup": "idle"}
    assert _decision(episode, 38) == {"scene": "questions", "stop": "hull", "caption_source": "visitor",
                                      "question_queue": "several", "guide_prompt": "on_time",
                                      "screen_warmup": "idle"}
    assert _decision(episode, 46) == {"scene": "paused", "stop": "lab", "caption_source": "guide",
                                      "held_scene": "at_stop"}
    assert _decision(episode, 52) == {"scene": "questions", "stop": "lab", "caption_source": "visitor",
                                      "question_queue": "empty", "guide_prompt": "wrap_up",
                                      "screen_warmup": "idle"}
    assert _decision(episode, 55) == {"scene": "at_stop", "stop": "terrace", "caption_source": "guide",
                                      "guide_prompt": "wrap_up", "screen_warmup": "idle"}


# --- caption strip --------------------------------------------------------------------------------


def test_staff_radio_is_never_shown(episode):
    assert _entry(_state(episode, 0), "s-00")["role"] == "staff" and _gold(episode, 0)["caption_source"] == "blank"
    state = _state(episode, 0)
    _entry(state, "s-00")["role"] = "visitor"
    assert reference(state)["caption_source"] == "visitor"
    # At 20 the staff resume is the latest log entry; the strip keeps the guide's entry before it.
    state = _state(episode, 20)
    assert state["asr"]["log"][-1]["role"] == "staff" and _gold(episode, 20)["caption_source"] == "guide"
    # A live staff turn (43-45) never takes the strip.
    assert _state(episode, 44)["asr"]["live"]["staff"] and _gold(episode, 44)["caption_source"] == "guide"


def test_live_turns_have_priority_guide_then_visitor_then_film(episode):
    assert [_gold(episode, t)["caption_source"] for t in range(11, 24)] == [
        "guide", "film", "film", "visitor", "guide", "film", "film", "guide", "guide", "guide", "film", "film",
        "guide"]
    # At 33 the visitor began after the guide, yet the live guide keeps the strip.
    state = _state(episode, 33)
    assert state["asr"]["live"]["visitor"]["began"] > state["asr"]["live"]["guide"]["began"]
    assert reference(state)["caption_source"] == "guide"
    state["asr"]["live"]["guide"] = None
    assert reference(state)["caption_source"] == "visitor"
    # At 14 the visitor outranks the older live film turn; without the visitor the film shows.
    state = _state(episode, 14)
    state["asr"]["live"]["visitor"] = None
    assert reference(state)["caption_source"] == "film"


def test_with_nothing_live_the_strip_keeps_the_highest_seq(episode):
    # At 17 the staff pause and then the cut-off film turn finish: the film entry has the higher seq.
    state = _state(episode, 17)
    assert [e["role"] for e in state["asr"]["log"][-2:]] == ["staff", "film"]
    assert reference(state)["caption_source"] == "film"
    # At 37 the visitor question and the guide's 'good questions' finish in one tick, the guide's last.
    state = _state(episode, 37)
    v, g = _entry(state, "v-36"), _entry(state, "g-37")
    assert v["ended"] == g["ended"] == 37 and g["seq"] == v["seq"] + 1
    assert reference(state)["caption_source"] == "guide"
    v["seq"], g["seq"] = g["seq"], v["seq"]
    assert reference(state)["caption_source"] == "visitor"


# --- commands -------------------------------------------------------------------------------------


@pytest.mark.parametrize("texts,stop", [
    (["okay folks on to stop three"], "hull"),
    (["on to stop three"], "hull"),
    (["right everyone on to stop three please"], "hull"),
    (["on to stop three?"], "hull"),
    (["follow me to the hull"], "hull"),
    (["follow me now to the hull folks"], "hull"),
    (["that was the bell", "on to stop four"], "figurehead"),
    (["on to stop four", "on to stop three"], "hull"),
    (["follow me to the chart room"], "charts"),
    (["sorry on to stop three"], "bell"),
    (["on to stop three at last"], "bell"),
    (["follow me to the hull model"], "bell"),
    (["follow me to hull"], "bell"),
    (["lets go on to stop three"], "bell"),
    (["on to stop nine"], "bell"),
    (["on to stop two"], "bell"),
    (["follow me to the chart"], "bell"),
])
def test_command_form(episode, texts, stop):
    state = _state(episode, 29)
    _entry(state, "g-28")["phrases"] = _phrases(*texts)
    answers = reference(state)
    assert (answers["scene"], answers["stop"]) == ("at_stop", stop)
    assert answers["guide_prompt"] == ("on_time" if stop != "bell" else "move_along")


def test_live_hypotheses_never_command(episode):
    assert [(_gold(episode, t)["stop"], _gold(episode, t)["scene"]) for t in (28, 29)] == [
        ("bell", "at_stop"), ("hull", "at_stop")]
    assert [_gold(episode, t)["scene"] for t in (32, 33, 34)] == ["at_stop", "at_stop", "questions"]
    assert [_gold(episode, t)["scene"] for t in (16, 17)] == ["film", "paused"]
    assert [_gold(episode, t)["scene"] for t in (56, 57)] == ["at_stop", "finished"]
    assert _hear(_state(episode, 31), "guide", "that concludes our tour")["scene"] == "at_stop"
    assert _hear(_state(episode, 31), "staff", "pause the tour")["scene"] == "at_stop"


def test_the_question_flag_plays_no_part_in_commands(episode):
    assert _entry(_state(episode, 34), "g-32")["phrases"] == _phrases("any questions?")
    assert _gold(episode, 34)["scene"] == "questions"
    assert _finish(_state(episode, 31), "guide", "on to stop four?")["stop"] == "figurehead"


def test_roles_restrict_commands(episode):
    # Visitor and film phrases never command, whatever they say; the same words from the guide would.
    state = _state(episode, 10)
    _entry(state, "v-09")["phrases"] = _phrases("start the film please")
    assert reference(state)["scene"] == "at_stop"
    _entry(state, "v-09")["role"] = "guide"
    assert reference(state)["scene"] == "film"
    state = _state(episode, 22)
    _entry(state, "f-21")["phrases"] = _phrases("stop the film")
    assert reference(state)["scene"] == "film"
    _entry(state, "f-21")["role"] = "guide"
    assert reference(state)["scene"] == "at_stop"
    # Only staff pause and resume; staff phrases from other roles and guide phrases from staff are speech.
    assert _finish(_state(episode, 31), "guide", "pause the tour")["scene"] == "at_stop"
    assert _finish(_state(episode, 31), "visitor", "pause the tour please")["scene"] == "at_stop"
    assert _finish(_state(episode, 31), "staff", "pause the tour")["scene"] == "paused"
    assert _finish(_state(episode, 48), "guide", "okay resume the tour")["scene"] == "paused"
    assert _finish(_state(episode, 36), "staff", "thank you for your questions")["scene"] == "questions"
    assert _finish(_state(episode, 36), "guide", "thank you for your questions")["scene"] == "at_stop"


def test_film_needs_a_film_stop_and_accepts_only_stop_the_film(episode):
    state = _state(episode, 31)
    assert _finish(state, "guide", "start the film")["scene"] == "at_stop"
    state = _state(episode, 31)
    state["gallery"]["stops"][2]["film"] = True
    assert _finish(state, "guide", "start the film")["scene"] == "film"
    for texts, scene in [(["follow me to the hull"], "film"), (["any questions?"], "film"),
                         (["that concludes our tour"], "film"), (["start the film"], "film"),
                         (["stop the film?"], "at_stop")]:
        state = _state(episode, 16)
        _entry(state, "g-15")["phrases"] = _phrases(*texts)
        assert reference(state)["scene"] == scene, texts
    # Without the film the same move acts and its ended tick is the arrival.
    state = _state(episode, 16)
    _entry(state, "g-11")["phrases"] = _phrases("theyre all in the film")
    answers = reference(state)
    assert (answers["scene"], answers["stop"], answers["guide_prompt"]) == ("at_stop", "hull", "on_time")
    # The move dropped at 16 never acts later: the stop is still the diving bell once the film stops.
    assert (_gold(episode, 23)["stop"], _gold(episode, 23)["scene"]) == ("bell", "at_stop")


def test_film_audio_ducks_only_for_a_live_guide_turn(episode):
    assert [_gold(episode, t)["film_audio"] for t in range(11, 24)] == [
        "full", "full", "full", "full", "ducked", "full", "none", "none", "none", "full", "full", "full", "none"]
    state = _state(episode, 14)
    assert state["asr"]["live"]["visitor"] and state["asr"]["live"]["film"]
    assert _hear(_state(episode, 14), "guide", "look")["film_audio"] == "ducked"
    assert _hear(_state(episode, 13), "staff", "front desk to the bell")["film_audio"] == "full"
    assert _finish(_state(episode, 13), "guide", "look")["film_audio"] == "full"


# --- screen warm-up -------------------------------------------------------------------------------


def test_screen_warmup_reads_only_the_stable_words(episode):
    assert [_gold(episode, t)["screen_warmup"] for t in range(3, 8)] == ["idle", "idle", "bell", "idle", "idle"]
    state = _state(episode, 4)
    assert state["asr"]["live"]["guide"]["words"] == "on to stop two" and state["asr"]["live"]["guide"]["stable"] == 3
    state["asr"]["live"]["guide"]["stable"] = 4
    assert reference(state)["screen_warmup"] == "bell"
    # The roof terrace: not yet named (24), named (25), named with stable words after it (26), finished (27).
    assert [_gold(episode, t)["screen_warmup"] for t in range(23, 30)] == [
        "idle", "idle", "terrace", "terrace", "idle", "hull", "idle"]
    assert _entry(_state(episode, 27), "g-24")["phrases"] == _phrases(
        "follow me to the roof terrace for drinks at the end")
    assert _gold(episode, 27)["stop"] == "bell"
    # Fillers are removed from the stable words, also mid-phrase; a name of the current stop wakes nothing.
    assert _gold(episode, 44)["screen_warmup"] == "lab"
    assert _state(episode, 44)["asr"]["live"]["guide"]["words"] == "follow me now to the conservation lab"
    assert _gold(episode, 42)["screen_warmup"] == "idle" and _gold(episode, 42)["stop"] == "hull"
    assert _gold(episode, 15)["screen_warmup"] == "none"


@pytest.mark.parametrize("words,stable,warm", [
    ("on to stop three", 4, "hull"),
    ("on to stop three", 3, "idle"),
    ("okay on to stop eight and drinks", 5, "terrace"),
    ("okay on to stop eight and drinks", 4, "idle"),
    ("now follow me to the chart room where", 7, "charts"),
    ("follow me to the chart room", 5, "idle"),
    ("follow me to the chart", 5, "idle"),
    ("so on to stop three", 5, "idle"),
    ("right now on to stop three", 6, "hull"),
    ("on to stop two", 4, "idle"),
    ("follow me to the diving bell", 6, "idle"),
    ("on to stop nine", 4, "idle"),
    ("on to stop", 3, "idle"),
    ("lets go on to stop three", 6, "idle"),
    ("follow me everyone to the figurehead", 6, "figurehead"),
])
def test_screen_warmup_reading(episode, words, stable, warm):
    state = _state(episode, 24)
    state["asr"]["live"]["guide"].update(words=words, stable=stable)
    answers = reference(state)
    assert (answers["stop"], answers["screen_warmup"]) == ("bell", warm)


def test_screen_warmup_runs_in_questions(episode):
    assert _hear(_state(episode, 36), "guide", "on to stop four and", began=36)["screen_warmup"] == "figurehead"
    assert _hear(_state(episode, 36), "guide", "on to stop four and", stable=3, began=36)["screen_warmup"] == "idle"


# --- guide prompt thresholds ---------------------------------------------------------------------


def test_dwell_threshold_counts_equality(episode):
    assert [_gold(episode, t)["guide_prompt"] for t in (38, 39)] == ["on_time", "move_along"]
    state = _state(episode, 39)
    assert state["tick"] - 29 == state["gallery"]["stops"][2]["dwell_ticks"]
    state["gallery"]["stops"][2]["dwell_ticks"] = 11
    assert reference(state)["guide_prompt"] == "on_time"


def test_wrap_up_threshold_counts_equality_and_outranks_dwell(episode):
    assert [_gold(episode, t)["guide_prompt"] for t in (51, 52)] == ["on_time", "wrap_up"]
    state = _state(episode, 52)
    state["gallery"]["wrap_up_at"] = 53
    assert reference(state)["guide_prompt"] == "on_time"
    # At the terrace the dwell clock restarts at 55, but the tour time is already up.
    assert [_gold(episode, t)["guide_prompt"] for t in (55, 56)] == ["wrap_up", "wrap_up"]
    state = _state(episode, 44)
    state["gallery"]["wrap_up_at"] = 44
    assert reference(state)["guide_prompt"] == "wrap_up"


def test_dwell_time_runs_through_films_and_pauses(episode):
    # Arrived at the diving bell at 6; the film and the pause (11-22) do not stop the clock: 17 ticks at 23.
    assert _gold(episode, 23)["guide_prompt"] == "move_along"
    state = _state(episode, 23)
    state["gallery"]["stops"][1]["dwell_ticks"] = 18
    assert reference(state)["guide_prompt"] == "on_time"
    # Resumed at 49 at the lab with the arrival tick 45 unchanged.
    assert _gold(episode, 49)["guide_prompt"] == "on_time"
    state = _state(episode, 49)
    state["gallery"]["stops"][4]["dwell_ticks"] = 4
    assert reference(state)["guide_prompt"] == "move_along"


def test_a_move_to_the_current_stop_keeps_the_arrival_tick(episode):
    assert _entry(_state(episode, 43), "g-42")["phrases"][0]["words"] == "follow me to the hull"
    assert [_gold(episode, t)["guide_prompt"] for t in (42, 43, 44)] == ["move_along"] * 3
    state = _state(episode, 43)
    _entry(state, "g-42")["phrases"][0]["words"] = "follow me to the figurehead"
    answers = reference(state)
    assert (answers["stop"], answers["guide_prompt"]) == ("figurehead", "on_time")


# --- questions ------------------------------------------------------------------------------------


def test_question_queue_story(episode):
    assert [_gold(episode, t)["question_queue"] for t in range(33, 42)] == [
        "none", "empty", "empty", "empty", "one", "several", "empty", "empty", "none"]
    assert [_gold(episode, t)["question_queue"] for t in range(51, 56)] == [
        "empty", "empty", "one", "empty", "none"]


def test_a_question_begun_before_the_opening_never_waits(episode):
    state = _state(episode, 35)
    v33, g32 = _entry(state, "v-33"), _entry(state, "g-32")
    assert v33["began"] == 33 < g32["ended"] == 34 and v33["phrases"][0]["question"]
    assert reference(state)["question_queue"] == "empty"
    v33["began"] = 34
    assert reference(state)["question_queue"] == "one"
    # Turns without a question phrase never wait.
    _entry(state, "v-33")["phrases"] = _phrases("how they lifted her is a mystery")
    assert reference(state)["question_queue"] == "empty"


def test_a_guide_onset_in_the_same_tick_answers_nothing(episode):
    state = _state(episode, 37)
    assert _entry(state, "g-37")["began"] == _entry(state, "v-36")["ended"] == 37
    assert reference(state)["question_queue"] == "one"
    _entry(state, "v-36")["ended"] = 36
    assert reference(state)["question_queue"] == "empty"
    # Two waiting entries give several; without the second question phrase only one waits.
    state = _state(episode, 38)
    assert reference(state)["question_queue"] == "several"
    _entry(state, "v-38")["phrases"] = _phrases("the mast looks new")
    assert reference(state)["question_queue"] == "one"
    # A live guide turn answers as soon as it begins.
    assert _gold(episode, 39)["question_queue"] == "empty" and _state(episode, 39)["asr"]["live"]["guide"]


def test_a_live_visitor_turn_never_waits(episode):
    assert _state(episode, 52)["asr"]["live"]["visitor"] and _gold(episode, 52)["question_queue"] == "empty"
    assert _gold(episode, 53)["question_queue"] == "one"


# --- pause, resume, ordering, end ---------------------------------------------------------------------


def test_the_log_replays_in_finishing_order(episode):
    # The staff pause began at 43, before the guide's move (44), but finished after it (46).
    state = _state(episode, 46)
    staff, guide = _entry(state, "s-43"), _entry(state, "g-44")
    assert staff["began"] < guide["began"] and staff["seq"] > guide["seq"]
    assert (reference(state)["stop"], reference(state)["held_scene"]) == ("lab", "at_stop")
    # Had the pause finished first, the move would have been dropped while paused.
    staff["seq"], guide["seq"] = guide["seq"], staff["seq"]
    staff["ended"], guide["ended"] = 45, 46
    answers = reference(state)
    assert (answers["scene"], answers["stop"], answers["held_scene"]) == ("paused", "hull", "at_stop")


def test_staff_pause_remembers_the_scene_and_drops_guide_commands_for_good(episode):
    assert [_gold(episode, t)["scene"] for t in range(16, 24)] == [
        "film", "paused", "paused", "paused", "film", "film", "film", "at_stop"]
    assert [_gold(episode, t)["scene"] for t in range(45, 52)] == [
        "at_stop", "paused", "paused", "paused", "at_stop", "at_stop", "questions"]
    # 'okay start the film' at 47 was dropped while paused and does not act after the resume at 49.
    assert _entry(_state(episode, 49), "g-47")["phrases"] == _phrases("okay start the film")
    state = _state(episode, 49)
    state["asr"]["log"] = [e for e in state["asr"]["log"] if e["turn_id"] != "s-43"]
    assert reference(state)["scene"] == "film"
    # A pause during questions remembers questions; the resume keeps the opening, so the queue is unchanged.
    state = _state(episode, 38)
    answers = _finish(state, "staff", "pause the tour")
    assert (answers["scene"], answers["held_scene"], answers["question_queue"]) == ("paused", "questions", "none")
    answers = _finish(state, "staff", "resume the tour")
    assert (answers["scene"], answers["question_queue"]) == ("questions", "several")
    # A second pause while paused changes nothing; a resume when not paused does nothing.
    state = _state(episode, 47)
    assert _finish(state, "staff", "pause the tour")["held_scene"] == "at_stop"
    assert _finish(_state(episode, 31), "staff", "resume the tour")["scene"] == "at_stop"


def test_resume_keeps_the_arrival_tick(episode):
    # Resumed into the film at 20; the arrival at the diving bell is still 6 when the film stops at 23.
    assert _gold(episode, 20)["scene"] == "film" and _gold(episode, 23)["guide_prompt"] == "move_along"


def test_questions_end_by_thanks_by_a_move_or_by_the_end_of_the_tour(episode):
    assert [_gold(episode, t)["scene"] for t in (40, 41)] == ["questions", "at_stop"]
    assert [(_gold(episode, t)["scene"], _gold(episode, t)["stop"]) for t in (54, 55)] == [
        ("questions", "lab"), ("at_stop", "terrace")]
    # 'any questions?', 'no?' and 'then that concludes our tour' act in phrase order within one turn.
    state = _state(episode, 57)
    assert _entry(state, "g-56")["phrases"] == _phrases("any questions?", "no?", "then that concludes our tour")
    assert reference(state)["scene"] == "finished"
    _entry(state, "g-56")["phrases"] = _phrases("then that concludes our tour", "any questions?")
    assert reference(state)["scene"] == "finished"
    _entry(state, "g-56")["phrases"] = _phrases("any questions?", "no?")
    assert reference(state)["scene"] == "questions"


def test_the_end_of_the_tour_is_final(episode):
    assert [_gold(episode, t)["scene"] for t in (56, 57, 58, 59)] == ["at_stop", "finished", "finished", "finished"]
    assert _entry(_state(episode, 59), "g-59")["phrases"][0]["words"] == "follow me to the chart room"
    assert _gold(episode, 59)["stop"] == "terrace"
    assert _finish(_state(episode, 59), "staff", "pause the tour")["scene"] == "finished"
    state = _state(episode, 59)
    _entry(state, "g-56")["phrases"] = _phrases("any questions?", "no?", "then that concludes the tour")
    answers = reference(state)
    assert (answers["scene"], answers["stop"]) == ("at_stop", "charts")
