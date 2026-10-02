"""Training variant presenter_d: a guided after-hours gallery tour driven by the guide's voice.

New-specification variant of the presenter voice-control family. A tour
controller follows a streaming recogniser on four roles (guide headset, roving
visitor microphone, staff radio, film soundtrack) and drives the stop screens,
the films, the visitors' handsets, a caption strip and the guide's wrist
display. Its own rules (``state["rules"]``), questions and state layout
(tick / gallery / asr.live / asr.log / handsets) are written for this variant;
no rule, question, builder or reference is imported from the evaluation module.

Evidence representation: the recogniser publishes one live slot per role (the
current hypothesis with a count of committed ``stable`` leading words) and a
log of finished turns in finishing order (``seq``), each already cut into
phrases with a question flag. All words are normalised lower-case words with
numbers spelled out, so there is no sentence or word splitting.

Design: commands are log phrases that equal one command phrase of their role
once filler words are removed wherever they stand. The scene replays the log
in seq order: a film accepts only 'stop the film'; a staff pause drops the
guide's commands for good and resumes the remembered scene unchanged; the end
of the tour is final. The caption strip gives live turns priority (guide, then
visitor, then film), else keeps the latest finished one. The guide prompt uses
the dwell time since arrival and a wrap-up tick (reaching counts). The screen
warm-up reads only the stable words of the guide's live turn, film ducking
follows whether the guide is live, and the question queue counts finished
visitor questions begun since the opening that no later guide onset has
answered. Every gold answer is computed by ``reference`` from the public state.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

EPISODE_ID = "train_presenter_d"
TITLE = "After-hours gallery tour of a raised oyster smack, run by the guide's voice"

ROLES = ("guide", "visitor", "staff", "film")
CAPTION_PRIORITY = ("guide", "visitor", "film")
FILLERS = {"okay", "right", "now", "then", "please", "everyone", "folks"}
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
GUIDE_PHRASES = {
    ("start", "the", "film"): "start_film",
    ("stop", "the", "film"): "stop_film",
    ("any", "questions"): "open_questions",
    ("thank", "you", "for", "your", "questions"): "close_questions",
    ("that", "concludes", "our", "tour"): "finish",
}
STAFF_PHRASES = {("pause", "the", "tour"): "pause", ("resume", "the", "tour"): "resume"}
FOLLOW = ["follow", "me", "to", "the"]
ON_TO = ["on", "to", "stop"]
INTERRUPTIBLE = {"at_stop", "film", "questions"}

RULES = [
    "Snapshot and gallery. tick is the number of this snapshot: snapshot t arrives at tick t and stays valid "
    "until the next one, two seconds later. Every began, revised, ended, dwell_ticks and gallery.wrap_up_at is a "
    "count of ticks. gallery.stops gives the stops in walking order, each with stop_id, number (1 upward), name "
    "(lower-case words; no stop's name forms the opening words of another's), film (true if the stop has a film "
    "the guide can start) and dwell_ticks (the time planned there). handsets only reports equipment and never "
    "changes an answer.",
    "Live turns. The recogniser hears four roles: guide (the guide's headset, relayed to the visitors' handsets), "
    "visitor (one roving microphone the visitors pass around), staff (the staff radio channel) and film (the "
    "soundtrack of a film playing at a stop). asr.live has one slot per role, holding null or the turn the "
    "recogniser is still hearing on it: turn_id, began (tick of its first hypothesis), revised (tick of its "
    "newest hypothesis), words (that hypothesis) and stable. stable counts the leading words the recogniser has "
    "committed to: later hypotheses of the turn keep them unchanged and may rewrite, add or remove only the words "
    "after them, and stable never decreases.",
    "Finished turns. When the recogniser finishes a turn, the turn leaves asr.live and is appended to asr.log, so "
    "the log lists finished turns in the order they finished; seq numbers them 1, 2, 3 and so on, and ended is "
    "the tick of finishing. A turn that began earlier can finish later than another one, and several turns can "
    "finish in one tick, in seq order. A log entry has seq, turn_id, role, began, ended and phrases, and is never "
    "altered afterwards. phrases is the turn cut where the speaker paused; each phrase has words and question "
    "(true when it was spoken as a question). The finished words start with the stable words of the turn's last "
    "hypothesis; the rest can differ from it. A short turn can enter the log without ever having been live.",
    "Words. Every words field holds lower-case words made of the letters a to z, one space apart: no punctuation "
    "and no capitals, apostrophes dropped (youngs, theyre) and numbers written as words (stop three, nineteen ninety "
    "eight). The filler words are okay, right, now, then, please, everyone and folks.",
    "Commands. Only phrases in asr.log can command; a live hypothesis never does, however it reads. Remove every "
    "filler word from a phrase, wherever it stands: the phrase is a command when the words left equal one of the "
    "command phrases of the turn's role, and question plays no part. Guide command phrases: 'follow me to the "
    "NAME' and 'on to stop N', moves to the stop whose full name is NAME or whose number is the word N (a NAME or "
    "N that fits no stop leaves the phrase ordinary speech); 'start the film'; 'stop the film'; 'any questions'; "
    "'thank you for your questions'; 'that concludes our tour'. Staff command phrases: 'pause the tour' and "
    "'resume the tour'. Visitor and film phrases never command. So 'right everyone on to stop three please' is a "
    "move, while 'sorry on to stop three', 'on to stop three at last' and 'follow me to the hull model' are "
    "ordinary speech.",
    "Scenes. The tour starts in the at_stop scene at the stop numbered 1, with arrival tick 0 and no questions "
    "opening. Go through asr.log in seq order and through each entry's phrases in order; every command acts on "
    "the scene of that moment or is dropped. In at_stop, a move to another stop makes it the current stop and "
    "the move's ended tick the arrival tick; 'start the film' gives film when the current stop's film is true; "
    "'any questions' gives questions and makes its ended tick the questions opening; 'that concludes our tour' "
    "gives finished. In questions, a move to another stop works as in at_stop and gives at_stop; 'thank you for "
    "your questions' gives at_stop; 'that concludes our tour' gives finished. In film only 'stop the film' acts, "
    "giving at_stop. The staff's 'pause the tour' in at_stop, film or questions gives paused and remembers that "
    "scene; 'resume the tour' in paused brings the remembered scene back with the same stop, arrival tick and "
    "questions opening. In paused the guide's commands are dropped, and in finished every command is. Any other "
    "command is dropped as well, including a move to the current stop (the arrival tick stays). A dropped "
    "command is gone for good and never acts later.",
    "Stop and caption strip, in every scene. stop is the current stop's stop_id. caption_source is the role the "
    "strip above the gallery shows. A live turn has priority: the guide's if she is live, else the visitor's, "
    "else the film's; the staff radio is never shown. With none of those three live, the strip keeps the role of "
    "the guide, visitor or film entry with the highest seq in asr.log, and it is blank while the log has no such "
    "entry.",
    "Guide prompt, the guide's wrist display, in at_stop and questions: wrap_up once tick has reached "
    "gallery.wrap_up_at; else move_along once tick minus the arrival tick has reached the current stop's "
    "dwell_ticks; else on_time. Reaching means equal or greater, and the clock at a stop keeps running through "
    "films, questions and pauses.",
    "Screen warm-up, in at_stop and questions, from stable words only. Take the committed leading words of the "
    "guide's live turn (as many as its stable count) and remove the filler words. If what remains begins with 'follow me to the' and a stop's "
    "full name, or with 'on to stop' and a stop's number word, that stop's screen wakes early (the answer is its "
    "stop_id), whatever stable words come after, unless it is the current stop. Otherwise idle: the guide has no "
    "live turn, the name or number is not yet among the stable words, or the stable words begin any other way.",
    "Film audio, in film: ducked while the guide has a live turn, so the handsets carry her voice over the "
    "soundtrack; otherwise full. Live visitor, staff or film turns never duck it.",
    "Question queue, in questions. A visitor entry in asr.log with at least one phrase whose question is true "
    "waits for an answer when it began at or after the current questions opening (the ended tick of the latest "
    "'any questions' that acted) and no guide turn, live or in the log, began after the visitor entry's ended "
    "tick. A guide turn that began in that very tick started before she could hear the question out and answers "
    "nothing. A live visitor turn never waits. The answer is empty when nothing waits, one for a single waiting "
    "entry and several for two or more.",
    "Held scene, in paused: the scene the pause remembered, which a resume brings back. Composition: the "
    "decision applied is scene, stop and caption_source plus the fields of the active scene: at_stop adds "
    "guide_prompt and screen_warmup; questions adds question_queue, guide_prompt and screen_warmup; film adds "
    "film_audio; paused adds held_scene; finished adds nothing. Every field of an inactive scene is answered "
    "none.",
]


def _stop_by_number(word: str, stops: list[dict]) -> dict | None:
    return next((s for s in stops if s["number"] == NUMBER_WORDS.get(word)), None)


def _content(words: list[str]) -> list[str]:
    """The words of a phrase or hypothesis with every filler word removed."""
    return [w for w in words if w not in FILLERS]


def _command(phrase: dict, role: str, stops: list[dict]) -> tuple[str, dict | None] | None:
    """The command a finished phrase states for its role, if any."""
    core = _content(phrase["words"].split())
    if role == "staff":
        kind = STAFF_PHRASES.get(tuple(core))
        return (kind, None) if kind else None
    if role != "guide":
        return None
    if tuple(core) in GUIDE_PHRASES:
        return GUIDE_PHRASES[tuple(core)], None
    if core[:4] == FOLLOW:
        target = next((s for s in stops if s["name"].split() == core[4:]), None)
        return ("move", target) if target else None
    if core[:3] == ON_TO and len(core) == 4:
        target = _stop_by_number(core[3], stops)
        return ("move", target) if target else None
    return None


def _leading_move(words: list[str], stops: list[dict]) -> dict | None:
    """The stop a word list begins to name with a move phrase, whatever words follow."""
    if words[:4] == FOLLOW:
        return next((s for s in stops if words[4:4 + len(s["name"].split())] == s["name"].split()), None)
    if words[:3] == ON_TO and len(words) > 3:
        return _stop_by_number(words[3], stops)
    return None


def _replay(log: list[dict], stops: list[dict]) -> dict:
    """Apply the commands of finished phrases in seq order."""
    scene, stop = "at_stop", next(s for s in stops if s["number"] == 1)
    arrived, held, opening = 0, None, None
    for entry in sorted(log, key=lambda e: e["seq"]):
        for phrase in entry["phrases"]:
            command = _command(phrase, entry["role"], stops)
            if command is None:
                continue
            kind, target = command
            if kind == "pause":
                if scene in INTERRUPTIBLE:
                    held, scene = scene, "paused"
            elif kind == "resume":
                if scene == "paused":
                    scene, held = held, None
            elif kind == "move":
                if scene in {"at_stop", "questions"} and target["stop_id"] != stop["stop_id"]:
                    stop, arrived, scene = target, entry["ended"], "at_stop"
            elif kind == "start_film":
                if scene == "at_stop" and stop["film"]:
                    scene = "film"
            elif kind == "stop_film":
                if scene == "film":
                    scene = "at_stop"
            elif kind == "open_questions":
                if scene == "at_stop":
                    scene, opening = "questions", entry["ended"]
            elif kind == "close_questions":
                if scene == "questions":
                    scene = "at_stop"
            elif kind == "finish":
                if scene in {"at_stop", "questions"}:
                    scene = "finished"
    return {"scene": scene, "stop": stop, "arrived": arrived, "held": held, "opening": opening}


def reference(state: dict) -> dict[str, str]:
    """Derive every answer from the published state alone (no tick index, gold or hidden field)."""
    tick, gallery = state["tick"], state["gallery"]
    stops, live, log = gallery["stops"], state["asr"]["live"], state["asr"]["log"]
    run = _replay(log, stops)
    scene, stop = run["scene"], run["stop"]

    speaking = [role for role in CAPTION_PRIORITY if live.get(role)]
    if speaking:
        caption = speaking[0]
    else:
        shown = [e for e in log if e["role"] in CAPTION_PRIORITY]
        caption = max(shown, key=lambda e: e["seq"])["role"] if shown else "blank"

    if tick >= gallery["wrap_up_at"]:
        prompt = "wrap_up"
    elif tick - run["arrived"] >= stop["dwell_ticks"]:
        prompt = "move_along"
    else:
        prompt = "on_time"

    guide_live = live.get("guide")
    warmup = "idle"
    if guide_live:
        committed = guide_live["words"].split()[:guide_live["stable"]]
        target = _leading_move(_content(committed), stops)
        if target and target["stop_id"] != stop["stop_id"]:
            warmup = target["stop_id"]

    audio = "ducked" if guide_live else "full"

    queue = "none"
    if scene == "questions":
        onsets = [e["began"] for e in log if e["role"] == "guide"] + ([guide_live["began"]] if guide_live else [])
        waiting = sum(
            1 for v in log
            if v["role"] == "visitor" and any(p["question"] for p in v["phrases"]) and v["began"] >= run["opening"]
            and not any(b > v["ended"] for b in onsets))
        queue = "empty" if waiting == 0 else "one" if waiting == 1 else "several"

    walking = scene in {"at_stop", "questions"}
    return {
        "scene": scene,
        "stop": stop["stop_id"],
        "caption_source": caption,
        "guide_prompt": prompt if walking else "none",
        "screen_warmup": warmup if walking else "none",
        "film_audio": audio if scene == "film" else "none",
        "question_queue": queue,
        "held_scene": run["held"] if scene == "paused" else "none",
    }


def _choice(instructions: str, **criteria: str) -> dict[str, Any]:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def _questions(stops: list[dict]) -> dict[str, Any]:
    stop_options = {s["stop_id"]: f"Stop {s['number']}, {s['name']}" + (" (has a film)" if s["film"] else "")
                    for s in stops}
    warm_options = {s["stop_id"]: f"Wake the screen at stop {s['number']}, {s['name']}" for s in stops}
    return {
        "scene": _choice(
            "Which scene is the tour in? Replay the command phrases of asr.log in seq order, starting from at_stop "
            "at stop 1; live hypotheses never count. A film accepts only 'stop the film', a staff pause drops the "
            "guide's commands until the staff resume the tour, and after finished nothing acts.",
            at_stop="Guide presenting at the current stop", film="Film running at the current stop",
            questions="Visitors' questions open", paused="Tour halted by staff", finished="Tour over"),
        "stop": _choice(
            "Which stop do the screens and handsets serve? The stop of the latest guide move that acted in the "
            "replay (stop 1 at the start). Moves act only in at_stop and questions; a move to the current stop, a "
            "live hypothesis or another role's phrase never moves the tour.",
            **stop_options),
        "caption_source": _choice(
            "Which role does the caption strip above the gallery show? A live guide turn first, then a live "
            "visitor turn, then a live film turn; with none of them live, the role of the guide, visitor or film "
            "entry with the highest seq in asr.log; blank before any. Staff radio turns are never shown.",
            guide="Guide's headset", visitor="Roving visitor microphone", film="Film soundtrack",
            blank="Nothing to show yet"),
        "guide_prompt": _choice(
            "In at_stop or questions, what does the guide's wrist display show? wrap_up when tick has reached "
            "gallery.wrap_up_at; else move_along when the ticks since the arrival tick have reached the current "
            "stop's dwell_ticks; else on_time. Reaching includes equality. Otherwise none.",
            on_time="On schedule", move_along="Planned time at this stop reached: move the group along",
            wrap_up="Tour time is up: wrap up", none="Not in at_stop or questions"),
        "screen_warmup": _choice(
            "In at_stop or questions, which stop's screen should wake early? Read only the stable words of the "
            "guide's live turn, fillers removed: if they begin with 'follow me to the' plus a stop's name or 'on "
            "to stop' plus a stop's number word, that stop unless it is the current one; otherwise idle, also "
            "when the guide has no live turn. Otherwise none.",
            idle="No screen to wake", **warm_options, none="Not in at_stop or questions"),
        "film_audio": _choice(
            "In film, how loud do the handsets play the soundtrack? ducked while the guide has a live turn; "
            "otherwise full. Otherwise none.",
            full="Soundtrack at full level", ducked="Soundtrack lowered under the guide's voice",
            none="Not in the film scene (a paused film included)"),
        "question_queue": _choice(
            "In questions, how many visitor questions wait? Count the visitor entries of asr.log with a question "
            "phrase that began at or after the questions opening and after whose ended tick no guide turn has "
            "begun (a guide turn beginning in that same tick does not count): empty for none, one for one, "
            "several for two or more. Otherwise none.",
            empty="No question waiting", one="One question waiting", several="Two or more questions waiting",
            none="Not in the questions scene (paused questions included)"),
        "held_scene": _choice(
            "In paused, which scene will the staff's resume bring back? The scene the pause interrupted. "
            "Otherwise none.",
            at_stop="Back to presenting the stop", film="Back to the running film",
            questions="Back to the open questions", none="The tour is not paused"),
    }


DECISION_SPEC = {
    "route_question": "scene", "always": ["stop", "caption_source"],
    "branches": {"at_stop": ["guide_prompt", "screen_warmup"],
                 "questions": ["question_queue", "guide_prompt", "screen_warmup"],
                 "film": ["film_audio"], "paused": ["held_scene"], "finished": []},
}

STOPS = [
    {"stop_id": "estuary", "number": 1, "name": "estuary gallery", "film": False, "dwell_ticks": 8},
    {"stop_id": "bell", "number": 2, "name": "diving bell", "film": True, "dwell_ticks": 12},
    {"stop_id": "hull", "number": 3, "name": "hull", "film": False, "dwell_ticks": 10},
    {"stop_id": "figurehead", "number": 4, "name": "figurehead", "film": False, "dwell_ticks": 6},
    {"stop_id": "lab", "number": 5, "name": "conservation lab", "film": True, "dwell_ticks": 10},
    {"stop_id": "charts", "number": 6, "name": "chart room", "film": False, "dwell_ticks": 8},
    {"stop_id": "ropewalk", "number": 7, "name": "ropewalk", "film": False, "dwell_ticks": 6},
    {"stop_id": "terrace", "number": 8, "name": "roof terrace", "film": False, "dwell_ticks": 8},
]

SETTING = (
    "Fictional after-hours members' tour of the Linnet gallery at the Gullhaven Maritime Museum, where an oyster "
    "smack raised from the estuary mud is shown in eight stops a few steps apart, ending on the roof terrace. "
    "Odile Brennan, the curator, guides the group on foot; every stop has its own screen, and two stops can show "
    "a short film. Visitors wear handsets that relay the guide's headset or a film's soundtrack, a caption strip "
    "above the gallery carries the speech, and one roving microphone is passed around the group. Kwame Osei, the "
    "duty manager, and the front desk share the staff radio, and the duty manager can halt the walk over it. The "
    "tour controller reads the recogniser's output for all four roles and drives the screens, films, handsets, "
    "caption strip and the guide's wrist display."
)

G, V, S, F = "guide", "visitor", "staff", "film"

# schedule[t] lists events in order: ("hear", role, began, words, stable) sets that role's live hypothesis;
# ("end", role, began, phrases) finishes the turn (a phrase ending in '?' was spoken as a question).
SCHEDULE: dict[int, list[tuple]] = {
    0: [("end", S, 0, ["front desk to odile", "all eighteen handsets are out"])],
    1: [("hear", G, 1, "good evening everyone", 2)],
    2: [("hear", G, 1, "good evening everyone the linnets story", 5)],
    3: [("end", G, 1, ["good evening everyone", "the linnets story starts here in the estuary"])],
    4: [("hear", G, 4, "on to stop two", 3)],
    5: [("hear", G, 4, "on to stop two everyone", 5)],
    6: [("end", G, 4, ["on to stop two everyone"])],
    7: [("hear", G, 7, "this bell took two divers", 4)],
    8: [("end", G, 7, ["this bell took two divers down to the wreck every morning"])],
    9: [("hear", V, 9, "can we see them", 2)],
    10: [("end", V, 9, ["can we see them working?"])],
    11: [("end", G, 11, ["theyre all in the film", "start the film please"])],
    12: [("hear", F, 12, "down we go", 2)],
    13: [("hear", F, 12, "down we go here is the linnet", 5)],
    14: [("hear", V, 14, "its so dark", 2)],
    15: [("end", V, 14, ["its so dark down there"]), ("hear", F, 12, "down we go here is the linnet just as the divers", 7),
         ("hear", G, 15, "follow me to the", 4)],
    16: [("end", G, 15, ["follow me to the hull"]), ("hear", S, 16, "pause the tour", 2)],
    17: [("end", S, 16, ["pause the tour please", "a handset has fallen behind the bell rail"]),
         ("end", F, 12, ["down we go", "here is the linnet just as the divers"])],
    18: [("hear", G, 18, "while we wait", 3)],
    19: [("end", G, 18, ["while we wait", "the bell still has its original glass ports"])],
    20: [("end", S, 20, ["got it", "resume the tour"])],
    21: [("hear", F, 21, "the divers worked by", 3)],
    22: [("end", F, 21, ["the divers worked by lamplight on the riverbed"])],
    23: [("end", G, 23, ["right stop the film"])],
    24: [("hear", G, 24, "follow me to the roof", 4)],
    25: [("hear", G, 24, "follow me to the roof terrace for", 6)],
    26: [("hear", G, 24, "follow me to the roof terrace for drinks at the", 9)],
    27: [("end", G, 24, ["follow me to the roof terrace for drinks at the end"])],
    28: [("hear", G, 28, "okay folks on to stop three", 6)],
    29: [("end", G, 28, ["okay folks on to stop three"])],
    30: [("hear", G, 30, "she came up in", 3)],
    31: [("end", G, 30, ["she came up in nineteen ninety eight", "full of estuary silt"])],
    32: [("hear", G, 32, "any questions", 2)],
    33: [("hear", V, 33, "how did they", 3)],
    34: [("end", G, 32, ["any questions?"]), ("hear", V, 33, "how did they lift her without", 5)],
    35: [("end", V, 33, ["how did they lift her without breaking her back?"])],
    36: [("hear", V, 36, "and where was", 2)],
    37: [("end", V, 36, ["and where was she built?"]), ("end", G, 37, ["good questions"])],
    38: [("end", V, 38, ["is the mast the original?"])],
    39: [("hear", G, 39, "a steel cradle went under", 3)],
    40: [("end", G, 39, ["a steel cradle went under her", "she was built at youngs yard", "and the mast is new"])],
    41: [("end", G, 41, ["thank you for your questions"])],
    42: [("hear", G, 42, "follow me to the hull the rest", 5)],
    43: [("end", G, 42, ["follow me to the hull", "the rest of you too"]), ("hear", S, 43, "pause the", 1)],
    44: [("hear", S, 43, "pause the tour please the", 4), ("hear", G, 44, "follow me now to the conservation lab", 7)],
    45: [("end", G, 44, ["follow me now to the conservation lab"])],
    46: [("end", S, 43, ["pause the tour please", "the fire door on the landing is open"])],
    47: [("end", G, 47, ["okay start the film"])],
    48: [("hear", G, 48, "the wax tanks", 2)],
    49: [("end", G, 48, ["the wax tanks are on your left"]), ("end", S, 49, ["door is shut", "resume the tour"])],
    50: [("hear", G, 50, "were short of time so", 4)],
    51: [("end", G, 50, ["were short of time", "so no film here", "any questions?"])],
    52: [("hear", V, 52, "is the wax", 2)],
    53: [("end", V, 52, ["is the wax still soft?"])],
    54: [("hear", G, 54, "no it sets", 2)],
    55: [("end", G, 54, ["no it sets as hard as candles", "on to stop eight everyone"])],
    56: [("hear", G, 56, "any questions", 2)],
    57: [("end", G, 56, ["any questions?", "no?", "then that concludes our tour"])],
    58: [("end", V, 58, ["thank you odile"])],
    59: [("end", G, 59, ["follow me to the chart room", "if you want to see the old charts"])],
}

HANDSETS = {17: {"working": 17}, 20: {"working": 18}}

NOTES = {
    0: "Only the staff radio has spoken, and it is never shown: the strip is blank.",
    4: "Live 'on to stop two' with stable 3: the number is not yet committed, so no screen wakes.",
    5: "Stable words 'on to stop two everyone' (filler dropped) name stop 2: the diving bell screen wakes; the "
       "stop waits for the finished turn.",
    6: "Finished move to stop 2: the diving bell, arrival tick 6.",
    11: "'start the film please' at a stop with a film: film scene.",
    14: "A live visitor turn during the film: the strip shows the visitor (over the film), and the soundtrack "
        "stays full because only the guide ducks it.",
    15: "A live guide turn during the film: soundtrack ducked; the guide has strip priority.",
    16: "A move during the film is dropped; with the guide finished, the strip returns to the live film turn.",
    17: "Staff pause during the film: paused, remembering film. The soundtrack stops, so the film turn finishes "
        "with its last hypothesis. One handset is out of use.",
    20: "Staff resume: the film scene comes back at the diving bell.",
    23: "Film stopped; 17 ticks since arriving at the diving bell reach its 12 dwell ticks: move_along. The "
        "move dropped at tick 16 never acts.",
    24: "Stable words 'follow me to the' do not yet name a stop: idle.",
    25: "Stable words 'follow me to the roof terrace': the roof terrace screen wakes.",
    26: "Stable words go on past the name ('for drinks at'): the screen still wakes, whatever follows.",
    27: "The finished phrase has extra words and is ordinary speech; with no live guide turn the warm-up is idle.",
    28: "Stable 'okay folks on to stop three' with both fillers dropped wakes the hull screen.",
    29: "Finished move to stop 3: the hull, arrival tick 29.",
    33: "Guide and visitor both live: the guide has strip priority although the visitor began later.",
    34: "'any questions?' opens questions at tick 34; the live visitor turn does not wait.",
    35: "The visitor question began at tick 33, before the opening at 34, so it never waits: empty.",
    37: "One question waits: the guide's 'good questions' began in the tick the question finished and answers "
        "nothing.",
    38: "A second visitor question finishes before any later guide onset: several.",
    39: "A guide turn begins after both questions: empty. 10 ticks at the hull equal its dwell_ticks: move_along.",
    41: "'thank you for your questions' closes questions: at_stop at the hull.",
    42: "Stable words name the current stop: no screen wakes.",
    43: "A move to the current stop is dropped and the arrival tick stays 29: still move_along.",
    44: "The staff turn began at 43 and is still live; the guide's stable 'follow me now to the conservation lab' "
        "(filler dropped mid-phrase) wakes the lab screen.",
    45: "The guide's move finishes first: the conservation lab, arrival tick 45.",
    46: "The staff pause finishes after the move: paused at the lab, remembering at_stop.",
    47: "'okay start the film' while paused is dropped for good.",
    49: "Staff resume: at_stop at the lab; the dropped film command does not act now.",
    51: "'any questions?' after the guide's remarks opens questions at tick 51.",
    52: "tick equals gallery.wrap_up_at: wrap_up.",
    53: "One visitor question waits.",
    54: "A guide onset answers it: empty.",
    55: "A move out of questions: at_stop at the roof terrace.",
    57: "'any questions' opens questions and 'then that concludes our tour' ends the tour from questions.",
    59: "A move after the end of the tour is dropped.",
}


def _initial() -> dict[str, Any]:
    return {
        "rules": RULES,
        "setting": SETTING,
        "tick": 0,
        "gallery": {"museum": "Gullhaven Maritime Museum", "guide": "Odile Brennan", "duty_manager": "Kwame Osei",
                    "wrap_up_at": 52, "stops": deepcopy(STOPS)},
        "asr": {"live": {role: None for role in ROLES}, "log": []},
        "handsets": {"caption_language": "English", "issued": 18, "working": 18},
    }


WORDS = re.compile(r"[a-z]+(?: [a-z]+)*")


def _check_conventions(state: dict, previous: dict | None) -> None:
    """Raise if a snapshot breaks the stated recogniser conventions."""
    tick, live, log = state["tick"], state["asr"]["live"], state["asr"]["log"]
    if set(live) != set(ROLES):
        raise ValueError(f"tick {tick}: asr.live needs one slot per role")
    logged = {e["turn_id"] for e in log}
    if len(logged) != len(log):
        raise ValueError(f"tick {tick}: a turn finished twice")
    for index, entry in enumerate(log):
        if entry["seq"] != index + 1 or not entry["began"] <= entry["ended"] <= tick:
            raise ValueError(f"tick {tick}: log entry {entry['turn_id']} is out of order")
        if index and entry["ended"] < log[index - 1]["ended"]:
            raise ValueError(f"tick {tick}: log is not in finishing order")
        if not entry["phrases"] or not all(WORDS.fullmatch(p["words"]) for p in entry["phrases"]):
            raise ValueError(f"tick {tick}: bad phrases in {entry['turn_id']}")
    for role, turn in live.items():
        if turn is None:
            continue
        if turn["turn_id"] in logged or not turn["began"] <= turn["revised"] <= tick:
            raise ValueError(f"tick {tick}: live {role} turn is inconsistent")
        if not WORDS.fullmatch(turn["words"]) or not 0 <= turn["stable"] <= len(turn["words"].split()):
            raise ValueError(f"tick {tick}: live {role} words or stable count is invalid")
        own = [e for e in log if e["role"] == role]
        if own and turn["began"] < own[-1]["ended"]:
            raise ValueError(f"tick {tick}: live {role} turn began before the role's previous turn finished")
    if previous is None:
        return
    old_log = previous["asr"]["log"]
    if log[:len(old_log)] != old_log:
        raise ValueError(f"tick {tick}: a log entry changed")
    for role, old in previous["asr"]["live"].items():
        if old is None:
            continue
        new = live[role]
        if new is not None and new["turn_id"] == old["turn_id"]:
            kept = old["words"].split()[:old["stable"]]
            if new["began"] != old["began"] or new["stable"] < old["stable"] or \
                    new["words"].split()[:old["stable"]] != kept:
                raise ValueError(f"tick {tick}: live {role} turn changed its committed words")
            continue
        finished = next((e for e in log[len(old_log):] if e["turn_id"] == old["turn_id"]), None)
        if finished is None:
            raise ValueError(f"tick {tick}: live {role} turn vanished without finishing")
        words = " ".join(p["words"] for p in finished["phrases"]).split()
        if words[:old["stable"]] != old["words"].split()[:old["stable"]]:
            raise ValueError(f"tick {tick}: {finished['turn_id']} does not start with its stable words")


def _phrase(text: str) -> dict[str, Any]:
    return {"words": text.removesuffix("?"), "question": text.endswith("?")}


def _build() -> dict[str, Any]:
    live = _initial()
    steps, previous = [], None
    for tick in range(60):
        live["tick"] = tick
        live["handsets"].update(HANDSETS.get(tick, {}))
        lines = []
        for event in SCHEDULE.get(tick, []):
            kind, role, began = event[:3]
            turn_id = f"{role[0]}-{began:02d}"
            slot = live["asr"]["live"][role]
            if kind == "hear":
                if slot is not None and slot["turn_id"] != turn_id:
                    raise ValueError(f"tick {tick}: {role} already has a live turn")
                live["asr"]["live"][role] = {"turn_id": turn_id, "began": began, "revised": tick,
                                             "words": event[3], "stable": event[4]}
                lines.append(f"live {role} {turn_id} (stable {event[4]}): {event[3]}")
            else:
                if slot is not None and slot["turn_id"] != turn_id:
                    raise ValueError(f"tick {tick}: {role} finishes a turn that is not its live one")
                live["asr"]["live"][role] = None
                phrases = [_phrase(p) for p in event[3]]
                live["asr"]["log"].append({"seq": len(live["asr"]["log"]) + 1, "turn_id": turn_id, "role": role,
                                           "began": began, "ended": tick, "phrases": phrases})
                lines.append(f"finished {role} {turn_id}: " + " / ".join(event[3]))
        state = deepcopy(live)
        _check_conventions(state, previous)
        previous = deepcopy(state)
        evidence = ["The complete public tour rules are in state.rules."] + lines
        if tick in NOTES:
            evidence.append(NOTES[tick])
        steps.append({"t": tick, "state": state, "gold": reference(state), "evidence": evidence})
    return {"episode_id": EPISODE_ID, "task_family": "presenter_voice_control", "scenario_id": "presenter_d",
            "title": TITLE, "tick_seconds": 2.0, "questions": _questions(STOPS),
            "decision_spec": deepcopy(DECISION_SPEC), "steps": steps}


def scenarios() -> list[dict[str, Any]]:
    """One 60-tick guided tour."""
    return [_build()]
