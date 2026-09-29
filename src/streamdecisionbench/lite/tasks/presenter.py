"""Two voice-controlled presentations with streaming ASR revisions for the Lite measurement."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

LEAD = r"(?:(?:okay|so|right|now|sure|and) )?"
PLEASE = r"(?: please)?"
NOUN = r"(?:clip|video|demo|animation)"
FORMS = [
    ("close", r"close the " + NOUN + r"|back to the slides"),
    ("next", r"next slide"),
    ("previous", r"previous slide"),
    ("goto", r"(?:go (?:back )?to|back to) (?:slide (?P<n>[0-9]+)|the (?P<name>[a-z ]+?)(?: slide)?)"),
    ("play", r"play(?: it| the " + NOUN + r")?|resume"),
    ("pause", r"(?:pause|hold)(?: it| the " + NOUN + r")?(?: here| there)?"),
    ("open", r"lets take (?:questions|one question)(?: from the floor)?"),
    ("move_on", r"lets move on"),
    ("thank", r"lets thank (?P<who>.+?)"),
]
SLIDE_KINDS = {"next", "previous", "goto"}


def _choice(instructions: str, **criteria: str) -> dict[str, Any]:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def _plain(text: str) -> str:
    return text.lower().replace("'", "").replace("’", "")


def _words(text: str) -> list[str]:
    """A sentence's words: lower-cased, apostrophes deleted, any other non-letter, non-digit a word break."""
    return re.findall(r"[^\W_]+", _plain(text))


def _units(u: dict) -> list[str]:
    """A final splits into sentences, each ending at a run of terminators; a partial is one unit."""
    if not u["final"]:
        return [u["text"]]
    return [s.strip() for s in re.findall(r"[^.?!]+[.?!]*", u["text"]) if s.strip()]


def _asks(unit: str) -> bool:
    return "?" in re.search(r"[.?!]*$", unit).group()


def _command(unit: str, deck: dict, first_name: str = "") -> tuple[str, int | None] | None:
    """The command a sentence (or a whole partial) states under the public command form, if any."""
    if _asks(unit):
        return None
    text = " ".join(re.sub(r"[.!]+$", "", _plain(unit.strip())).replace(",", "").split())
    for kind, form in FORMS:
        m = re.fullmatch(LEAD + "(?:" + form + ")" + PLEASE, text)
        if not m:
            continue
        if kind == "goto":
            if m.group("n"):
                target = int(m.group("n"))
            else:
                target = next((s["n"] for s in deck["slides"] if s["name"] == m.group("name")), None)
            return (kind, target) if target in {s["n"] for s in deck["slides"]} else None
        if kind == "thank":
            return (kind, None) if m.group("who") == _plain(first_name) else None
        return kind, None
    return None


def _replay(state: dict) -> dict:
    """Apply final commands in the order their finals arrived."""
    deck = state["deck"]
    last = len(deck["slides"])
    clips = {s["n"] for s in deck["slides"] if s["clip"]}
    first = state["session"]["presenter"].split()[0]
    slide, mode, clip, opened = deck["start_slide"], "talk", "play", None
    finals = sorted((u for u in state["transcript"] if u["final"]), key=lambda u: (u["final_at"], u["at"]))
    for u in finals:
        for unit in _units(u):
            cmd = _command(unit, deck, first)
            if cmd is None:
                continue
            kind, who = cmd[0], u["speaker"]
            if who == "Presenter":
                if kind in SLIDE_KINDS:
                    slide = (min(slide + 1, last) if kind == "next" else
                             max(slide - 1, 1) if kind == "previous" else cmd[1])
                    if mode == "clip":
                        mode = "talk"
                elif mode == "closed":
                    continue
                elif kind == "play" and (mode == "clip" or (mode == "talk" and slide in clips)):
                    mode, clip = "clip", "play"
                elif kind == "pause" and mode == "clip":
                    clip = "pause"
                elif kind == "close" and mode == "clip":
                    mode = "talk"
                elif kind == "move_on" and mode == "questions":
                    mode = "talk"
            elif who == "Host":
                if kind == "open" and mode in {"talk", "clip"}:
                    mode, opened = "questions", u["at"]
                elif kind == "move_on" and mode == "questions":
                    mode = "talk"
                elif kind == "thank" and mode != "closed":
                    mode = "closed"
    return {"slide": slide, "mode": mode, "clip": clip, "opened": opened}


def _hands_back(u: dict, host_first: list[str]) -> bool:
    handback = ["back", "to", "you"]
    for unit in _units(u):
        words = _words(unit)
        if words[-3:] == handback or (words[-len(host_first) - 3:] == handback + host_first):
            return True
    return False


def reference(state: dict) -> dict[str, str]:
    """Derive all answers from published state, never a step index or hidden label."""
    deck = state["deck"]
    lines = sorted(state["transcript"], key=lambda u: u["at"])
    run = _replay(state)
    mode = run["mode"]
    presenter = [u for u in lines if u["speaker"] == "Presenter"]
    host = [u for u in lines if u["speaker"] == "Host"]
    mine = presenter[-1] if presenter else None

    clip_state = run["clip"]
    if mine and not mine["final"] and (_command(mine["text"], deck) or ("",))[0] == "pause":
        clip_state = "pause"
    captions = lines[-1]["speaker"].lower() if lines else "off"

    host_first = _words(state["session"]["host"].split()[0])
    handback = bool(mine and _hands_back(mine, host_first) and not any(h["at"] > mine["at"] for h in host))
    host_cue = "stand_by" if handback else "listen"

    card = "none"
    if mode == "questions":
        asked = [u for u in lines if u["speaker"] == "Audience" and u["at"] > run["opened"]]
        questions = [u for u in asked if u["final"] and any(_asks(unit) for unit in _units(u))]
        if any(not u["final"] for u in asked):
            card = "listening"
        elif not asked:
            card = "waiting"
        elif not questions:
            card = "answer"
        else:
            newest = questions[-1]
            repeated = any(
                re.fullmatch(LEAD + r"the question is\b.*", " ".join(_words(unit)))
                for u in presenter if u["final"] and u["at"] > newest["at"] for unit in _units(u))
            card = "answer" if repeated else "repeat"
    return {
        "mode": mode, "slide": f"s{run['slide']}", "captions": captions,
        "clip_state": clip_state if mode == "clip" else "none",
        "question_card": card,
        "host_cue": host_cue if mode in {"talk", "questions"} else "none",
    }


def _build(initial: dict, schedule: dict[int, list[tuple]], *, episode_id: str, title: str,
           questions: dict, decision_spec: dict) -> dict:
    """schedule[t] lists (speaker, start, text, final); a line replaces the same utterance id."""
    live = deepcopy(initial)
    steps = []
    for tick in range(60):
        live["clock"]["now"] = tick
        for speaker, start, text, final in schedule.get(tick, []):
            uid = f"{speaker[0].lower()}{start}"
            line = {"utterance_id": uid, "at": start, "final_at": tick if final else None,
                    "speaker": speaker, "text": text, "final": final}
            kept = [u for u in live["transcript"] if u["utterance_id"] != uid]
            live["transcript"] = sorted(kept + [line], key=lambda u: u["at"])
        state = deepcopy(live)
        newest = state["transcript"][-1] if state["transcript"] else None
        evidence = ["The complete public rules are in prepared.rules."]
        if newest:
            evidence.append(f"{newest['speaker']} {newest['utterance_id']} "
                            f"({'final' if newest['final'] else 'partial'}): {newest['text']}")
        steps.append({"t": tick, "state": state, "gold": reference(state), "evidence": evidence})
    return {"episode_id": episode_id, "task_family": "presenter_voice_control",
            "scenario_id": episode_id.removeprefix("lite_"), "title": title, "tick_seconds": 2.0,
            "questions": questions, "decision_spec": decision_spec, "steps": steps}


RULES = [
    "Time and transcript. clock.now, at and final_at are ticks; snapshot t is published at tick t, and nothing changes between ticks. The transcript lists every utterance since tick 0 once, by utterance_id, in the order they began; at is the tick at which its first hypothesis appeared, and no two utterances share an at; final_at is the tick at which its final appeared. An utterance keeps its utterance_id, at and speaker, and every utterance ends in a final with at least one word. A partial (final false, final_at null) holds the recogniser's current hypothesis: lower-case words only, with no punctuation or apostrophes and numbers spelled out. Each newer hypothesis replaces it under the same utterance_id; words may be added or changed, and earlier hypotheses are not kept. The final (final true, final_at set) adds capitals, punctuation and apostrophes, writes slide numbers and numbers from 10 up as digits, has no quotation marks, can still change words, and never changes again; a short utterance can appear already final. Each speaker has at most one partial, and it is that speaker's newest utterance; different speakers can overlap. The recogniser is biased toward slide names and command phrases, so a hypothesis can show a command that a later hypothesis or the final corrects. Nothing the controller shows is in the state.",
    "Evidence tiers. ONSET: that an utterance exists, with its speaker and at, known from its first hypothesis. CURRENT TEXT: the text shown now, partial or final; an answer that uses it follows every revision, including back. FINAL TEXT: final utterances only; a partial never counts, however complete it looks. Every start or move the room sees or hears (the slide, playing or closing the clip, the mode) waits for FINAL TEXT, and so do the repeat and answer cards, which need the finished question. CURRENT TEXT is used only where a late answer loses its value and a wrong one is cheap and undone by the next hypothesis: the early pause, which only stops the looping clip, and the chair's private stand-by. Captions, the listening card and the end of a stand-by use ONSET.",
    "Speakers: Presenter (lapel microphone), Host (the session chair), Audience (floor microphone) and Clip (the clip's soundtrack, recognised for captions). Only the Presenter's commands move slides or control the clip. Only the Host opens questions, and only the Host closes the session, with the thanks command; the Presenter or the Host can end questions. Audience and Clip speech never commands, and a request made or relayed by another speaker changes nothing.",
    "Sentences and commands. A final splits into sentences, each ending at a run of '.', '?' and '!' (trailing text without one is also a sentence); a sentence ends in '?' if its run contains '?'. A command is one whole sentence of a final utterance, or, for the early pause only, the whole text of a Presenter partial. Lower-case it, delete commas, apostrophes and a closing run of '.' and '!', and collapse spaces; it must then be, in this order, an optional lead-in word (okay, so, right, now, sure or and), exactly one command phrase and an optional 'please'. A sentence with any other word or character, or ending in '?', is not a command: 'Next slide shows the demo.' and 'Go back to slide 3?' are talk. Word tests ('the question is', 'back to you', first names) read words: lower-cased, apostrophes deleted, and every other character that is not a letter or digit a word break.",
    "Command phrases (NOUN is clip, video, demo or animation). Slide: 'next slide'; 'previous slide'; 'go to slide N', 'go back to slide N' or 'back to slide N', with N a slide number of the deck in digits; 'go to the NAME', 'go back to the NAME' or 'back to the NAME', optionally followed by 'slide', with NAME exactly one slide name in the deck (slide names are distinct, use lower-case letters and spaces only, and none ends in 'slide'). Play: 'play', 'play it', 'play the NOUN' or 'resume'. Pause: 'pause' or 'hold', optionally followed by 'it' or 'the NOUN', then optionally by 'here' or 'there'. Close: 'close the NOUN' or 'back to the slides'. Session: 'lets take questions' or 'lets take one question', optionally followed by 'from the floor'; 'lets move on'; the thanks command, 'lets thank' followed by the presenter's first name.",
    "Replay. Final commands take effect in the order their finals arrived (final_at, then at, then sentence order), starting from deck.start_slide in talk mode. Slide commands apply in every mode: next adds 1 and previous subtracts 1 within the deck, go-to selects its slide, and in clip mode a slide command also closes the clip (talk). Play gives clip mode with the clip playing if the mode is already clip, or if the mode is talk and the current slide has a clip; otherwise nothing. In clip mode, pause pauses the clip and close returns to talk; a clip loops until paused or closed. The Host's open-questions command gives questions from talk or clip mode, and its utterance is the opening. 'lets move on' in questions gives talk. The Host's thanks command gives closed, after which only slide commands apply. Commands with no effect in the current mode are ignored.",
    "Clip state, in clip mode: pause while the Presenter's newest utterance is a partial whose whole text is a pause command (the early pause, which lapses as soon as that hypothesis is revised or finalised into anything else); otherwise the state set by the latest final Presenter play or pause command that took effect. Captions, by ONSET: the speaker of the newest utterance (largest at), partial or final, on any channel; off before anyone has spoken.",
    "Question card, in questions mode, over Audience utterances whose at is greater than the opening's at: listening while one of them is partial; otherwise waiting if there are none; otherwise answer if none has a sentence ending in '?'; otherwise repeat until a final Presenter utterance whose at is greater than that of the newest Audience utterance with such a sentence has a sentence whose words start, after an optional lead-in word from the command lead-in list, with 'the question is'; then answer.",
    "Host cue, in talk and questions modes, by CURRENT TEXT: stand_by while a sentence of the Presenter's newest utterance (its whole text, if partial) ends with the words 'back to you', optionally followed by the Host's first name, and no Host utterance has a greater at; otherwise listen. The applied decision is mode, slide and captions plus the active branch: talk adds host_cue; questions adds question_card and host_cue; clip adds clip_state; closed adds nothing. Answers outside the active branch are none.",
]


def _questions(deck: dict) -> dict:
    slides = {f"s{s['n']}": f"Slide {s['n']}: {s['name']}" + (" (has a clip)" if s["clip"] else "")
              for s in deck["slides"]}
    return {
        "mode": _choice("Which mode is the stage controller in now? FINAL TEXT: replay final commands in the order their finals arrived, starting in talk; partial speech never changes the mode.",
                        talk="Presenting slides", clip="Showing the current slide's clip",
                        questions="Taking questions from the floor", closed="Session closed by the Host"),
        "slide": _choice("Which deck slide should the projector show (behind the clip while one is showing)? FINAL TEXT: start from deck.start_slide and apply final Presenter slide commands in every mode; partial hypotheses, other speakers, mentions and questions never move it.", **slides),
        "captions": _choice("Whose speech does the caption bar in the hall and on the stream show now? ONSET: the speaker of the newest utterance (largest at), partial or final, on any channel; off before anyone has spoken.",
                            presenter="Captions of the Presenter", host="Captions of the Host",
                            audience="Captions of the Audience microphone", clip="Captions of the clip's soundtrack",
                            off="No one has spoken yet"),
        "clip_state": _choice("In clip mode, is the clip playing or paused now? CURRENT TEXT for the early pause: paused while the Presenter's newest utterance is a partial whose whole text is a pause command; otherwise FINAL TEXT: the state set by the latest final Presenter play or pause command that took effect. Otherwise none.",
                              play="Playing", pause="Paused", none="Clip mode inactive"),
        "question_card": _choice("In questions mode, which card does the presenter's confidence monitor show? Over Audience utterances that began after the opening: ONSET: listening while one is partial, waiting if there are none; FINAL TEXT: repeat after the newest one with a sentence ending in '?' until a final Presenter utterance that began after it has a sentence whose words start, after an optional lead-in word (okay, so, right, now, sure or and), with 'the question is'; otherwise answer. Otherwise none.",
                                 waiting="Floor open, no Audience utterance yet",
                                 listening="A question is being asked",
                                 repeat="Repeat the question for the stream before answering",
                                 answer="Answer; nothing left to repeat",
                                 none="Questions mode inactive"),
        "host_cue": _choice("In talk or questions mode, what does the session chair's tablet show? CURRENT TEXT: stand_by while a sentence of the Presenter's newest utterance (its whole text, if partial) ends with the words 'back to you', optionally followed by the Host's first name, and no Host utterance began after it; otherwise listen. Otherwise none.",
                            listen="Nothing for the chair to do", stand_by="Stand by: the presenter may be handing the floor to you",
                            none="Talk and questions modes inactive"),
    }


SPEC = {"route_question": "mode", "always": ["slide", "captions"],
        "branches": {"talk": ["host_cue"], "questions": ["question_card", "host_cue"],
                     "clip": ["clip_state"], "closed": []}}


def _deck(names: list[str], clips: set[int], start: int) -> dict:
    return {"start_slide": start,
            "slides": [{"n": i, "name": n, "clip": i in clips} for i, n in enumerate(names, 1)]}


P, H, A, C = "Presenter", "Host", "Audience", "Clip"


def _talk_scenario() -> dict:
    deck = _deck(["title", "agenda", "wake word", "streaming decoder", "partial results", "latency chart",
                  "demo", "error cases", "battery", "privacy", "cost table", "thank you"], {7}, 5)
    initial = {
        "prepared": {"deployment": "Fictional session at the Northgate Speech Systems Forum, held in a hall and streamed; Tomas Ruud chairs it. The deck runs on the show computer at the AV desk, and the presenter asks for slides by voice ('Next slide, please') as she would ask a slide operator. The stage controller follows those requests from streaming ASR and drives the projector, the clip player, the caption bar in the hall and on the stream, the presenter's confidence monitor and the chair's tablet. Shadow-mode recording: a human operator ran the deck, the controller's decisions describe what it should show, and nobody reacts to them.",
                     "rules": RULES},
        "clock": {"now": 0},
        "session": {"talk": "Voice control on a three-watt budget", "presenter": "Mira Castell", "host": "Tomas Ruud"},
        "deck": deck, "transcript": [],
    }
    S = {
        0: [(P, 0, "so the decoder keeps one", False)],
        1: [(P, 0, "so the decoder keeps one running hypothesis", False)],
        2: [(P, 0, "So the decoder keeps one running hypothesis and revises it as audio arrives.", True)],
        3: [(P, 3, "next slide", False)],
        4: [(P, 3, "Next slide, please.", True)],
        5: [(P, 5, "next slide", False)],
        6: [(P, 5, "next slide shows the demo", False)],
        7: [(P, 5, "Next slide shows the demo, but first one more number.", True)],
        8: [(P, 8, "go to slide seven", False)],
        9: [(P, 8, "Go to slide 11.", True)],
        11: [(P, 11, "the cost table is what finance", False)],
        12: [(P, 11, "The cost table is what finance asked about, 40 cents per device per year.", True)],
        13: [(P, 13, "go back to the", False)],
        14: [(P, 13, "go back to the demo", False)],
        15: [(P, 13, "Go back to the demo.", True)],
        16: [(P, 16, "play the video", False)],
        17: [(P, 16, "Play the video.", True)],
        19: [(C, 19, "watch the top line", False)],
        20: [(C, 19, "Watch the top line as the user speaks.", True)],
        21: [(C, 21, "Next slide.", True)],
        22: [(P, 22, "hold it", False)],
        23: [(P, 22, "Hold it there.", True)],
        24: [(A, 24, "can you play it again", False)],
        25: [(A, 24, "Can you play it again?", True)],
        26: [(P, 26, "sure play it", False)],
        27: [(P, 26, "Sure, play it.", True)],
        28: [(C, 28, "watch the", False)],
        29: [(C, 28, "watch the top line as the", False), (P, 29, "pause the demo", False)],
        30: [(P, 29, "because the demo runs on", False), (C, 28, "Watch the top line as the user speaks.", True)],
        31: [(P, 29, "Because the demo runs on battery, the decoder is slower here.", True)],
        32: [(P, 32, "back to the slides", False)],
        33: [(P, 32, "Back to the slides.", True)],
        34: [(P, 34, "users mostly say next slide", False)],
        35: [(P, 34, "Users mostly say next slide, so that phrase gets extra training data.", True)],
        36: [(P, 36, "and the watch sends it back to you", False)],
        37: [(P, 36, "and the watch sends it back to your phone", False)],
        38: [(P, 36, "And the watch sends it back to your phone in under a second.", True)],
        39: [(P, 39, "go to the thank you slide", False)],
        40: [(P, 39, "Go to the thank you slide.", True)],
        42: [(P, 42, "thats all from me back to you", False)],
        43: [(P, 42, "That's all from me. Back to you, Tomas.", True)],
        45: [(H, 45, "thank you mira lets take questions", False)],
        46: [(H, 45, "Thank you, Mira. Let's take questions.", True)],
        48: [(A, 48, "does the decoder", False)],
        49: [(A, 48, "does the decoder work offline", False)],
        50: [(A, 48, "Does the decoder work offline?", True)],
        52: [(P, 52, "the question is whether", False)],
        53: [(P, 52, "The question is whether it works offline.", True)],
        54: [(P, 54, "yes everything stays on the", False)],
        55: [(P, 54, "Yes. Everything stays on the device, including the partials.", True)],
        57: [(H, 57, "Let's thank Mira.", True)],
    }
    return _build(initial, S, episode_id="lite_presenter_a", title="Conference talk with a demo clip and floor questions",
                  questions=_questions(deck), decision_spec=SPEC)


def _briefing_scenario() -> dict:
    deck = _deck(["title", "river basin", "flood footage", "rain gauges", "rainfall chart", "barrier design",
                  "barrier animation", "costs", "timeline", "zone map", "evacuation routes", "contact"], {3, 7}, 6)
    initial = {
        "prepared": {"deployment": "Fictional public briefing by the Kestrel Valley Water Board in the Aldern council hall, streamed online; Paulo Mendes chairs it and relays online requests. The deck runs on the show computer at the AV desk, and the presenter asks for slides by voice ('Next slide, please') as she would ask a slide operator. The stage controller follows those requests from streaming ASR and drives the projector, the clip player, the caption bar in the hall and on the stream, the presenter's confidence monitor and the chair's tablet. The barrier animation has no soundtrack. Shadow-mode recording: a human operator ran the deck, the controller's decisions describe what it should show, and nobody reacts to them.",
                     "rules": RULES},
        "clock": {"now": 0},
        "session": {"talk": "The Aldern flood barrier: design, cost and closures", "presenter": "Ines Harrow", "host": "Paulo Mendes"},
        "deck": deck, "transcript": [],
    }
    S = {
        0: [(P, 0, "the gates sit under the", False)],
        1: [(P, 0, "The gates sit under the old bridge and rise in 20 minutes.", True)],
        2: [(P, 2, "ill come back to the zone map", False)],
        3: [(P, 2, "I'll come back to the zone map later.", True)],
        4: [(P, 4, "play the animation", False)],
        5: [(P, 4, "Play the animation.", True)],
        6: [(P, 6, "oh its on the next one", False)],
        7: [(P, 6, "Oh, it's on the next one. Next slide, please.", True)],
        8: [(P, 8, "play the animation", False)],
        9: [(P, 8, "Play the animation.", True)],
        11: [(P, 11, "hold", False)],
        12: [(P, 11, "Hold on to your seats.", True)],
        15: [(P, 15, "pause it", False)],
        16: [(P, 15, "Pause it.", True)],
        17: [(P, 17, "the second gate rises only", False)],
        18: [(P, 17, "The second gate rises only when the first is sealed.", True)],
        19: [(P, 19, "next slide", False)],
        20: [(P, 19, "Next slide.", True)],
        21: [(P, 21, "the barrier costs", False)],
        22: [(P, 21, "the barrier costs forty one million", False), (H, 22, "sorry ines", False)],
        23: [(P, 21, "The barrier costs 41 million, shared with the rail company.", True),
             (H, 22, "sorry ines lets take one", False)],
        24: [(H, 22, "Sorry, Ines. Let's take one question from the floor.", True)],
        26: [(A, 26, "will the", False)],
        27: [(A, 26, "will the barrier close the river path", False)],
        28: [(A, 26, "Will the barrier close the river path?", True)],
        30: [(P, 30, "yes for about four hours", False)],
        31: [(P, 30, "Yes, for about four hours during a closure.", True)],
        32: [(P, 32, "sorry the question is", False)],
        33: [(P, 32, "Sorry. The question is whether the river path closes.", True)],
        34: [(P, 34, "go to the zone", False)],
        35: [(P, 34, "go to the zone map", False)],
        36: [(P, 34, "Go to the zone map.", True)],
        38: [(P, 38, "the path back to you", False)],
        39: [(P, 38, "the path back to union street", False)],
        40: [(P, 38, "The path back to Union Street closes only in zone B.", True)],
        41: [(P, 41, "lets move on", False)],
        42: [(P, 41, "Let's move on.", True)],
        44: [(H, 44, "a request from jun online", False)],
        45: [(H, 44, "A request from Jun online. Go back to slide 3, please.", True)],
        46: [(P, 46, "go back to slide three", False)],
        47: [(P, 46, "Go back to slide 3? Not today. The footage is in the handout.", True)],
        48: [(P, 48, "Previous slide.", True)],
        50: [(P, 50, "the timeline has both", False)],
        51: [(P, 50, "The timeline has both gates working by next spring.", True)],
        52: [(P, 52, "thats the timeline back to you", False)],
        53: [(P, 52, "That's the timeline. Back to you, Paulo.", True)],
        55: [(H, 55, "were out of time", False)],
        56: [(H, 55, "We're out of time. Let's thank Ines.", True)],
    }
    return _build(initial, S, episode_id="lite_presenter_b", title="Flood-barrier briefing with a clip and a mid-talk question",
                  questions=_questions(deck), decision_spec=SPEC)


def scenarios() -> list[dict]:
    """Return two independent 60-tick observation trajectories."""
    return [_talk_scenario(), _briefing_scenario()]
