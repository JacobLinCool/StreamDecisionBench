"""Training variant presenter_c: a wake-word lecture console driven by confidence-scored ASR segments.

A new-specification variant of the presenter voice-control family. A lecture
console listens to streaming speech recognition on four channels (the
lecturer's headset, the moderator's handheld microphone, the room's ceiling
microphones and the soundtrack of a playing clip). The recogniser publishes
segments with word confidences and a stable flag. Only a STABLE lecturer or
moderator segment that starts with the wake word, says exactly one phrase of
that speaker's closed list and has every word at or above the confidence
threshold is a command; unstable segments change no answer at all. Commands
replay in order of segment end, equal ends in seg_id order. The lecturer
drives the slide (locked outside lecture mode), the pointer effect, the clip
and the recording; the moderator opens and closes the class poll, calls a
break, resumes and ends the lecture. A poll or break called during a clip holds
the clip, and resuming brings it back paused. The capture light pauses for a
break, for the lecturer's recording setting and on a slide listed as
unpublished until the lecturer clears that visit with 'record this slide'. The
countdown cue follows the scheduled end. Every gold answer is computed by
``reference`` from the public state alone; ``controller.rules`` states all of
it.

Story: a marine-acoustics evening lecture. A student tries the wake word from
the seats, a confident slide-number hypothesis turns stable with one word under
the threshold, the lecturer zooms in and out on a recorder, a slide command
during the whale clip is locked out, the moderator runs a class poll over the
clip (the lecturer cannot close it) and the clip comes back paused, the room
booking is extended, a hypothesis that reads as 'zoom in' runs on past the
phrase once stable, a title command passes at exactly the threshold, the
fishers' reef audio is kept off the archive with the recording setting, the
online stream loses its sound and the moderator calls a break in the same tick
as a lecturer slide command, the unpublished harbour slide pauses the capture
until the lecturer clears it (the moderator cannot), the clearance lapses when
she comes back to it after a number-word slide command, and only the moderator
can end the lecture.
"""

from __future__ import annotations

from copy import deepcopy
import re
import zlib
from typing import Any

EPISODE_ID = "train_presenter_c"
TITLE = "Wake-word lecture console: whale clicks, a class poll and a reef recording"

CHANNELS = ("lecturer", "moderator", "room", "media")
COMMANDING = ("lecturer", "moderator")
NUMBER_WORDS = {word: n for n, word in enumerate(
    ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
     "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"], 1)}
CLIP_VERBS = ("play", "pause", "stop")
CLIP_NOUNS = ("video", "audio")
POINTER_PHRASES = {("spotlight",): "spotlight", ("zoom", "in"): "zoom", ("zoom", "out"): "off",
                   ("pointer", "off"): "off"}
RECORDING_PHRASES = {("pause", "recording"): "paused", ("resume", "recording"): "on",
                     ("record", "this", "slide"): "clear"}
MODERATOR_PHRASES = {("open", "the", "poll"): "open_poll", ("close", "the", "poll"): "close_poll",
                     ("take", "a", "break"): "break", ("resume", "the", "lecture"): "resume",
                     ("end", "the", "lecture"): "end"}

RULES = [
    "Clock and segment list. Every time value (now, session.ends_at, each segment's start and end) counts "
    "ticks of two seconds. The snapshot with now = t is the one released at tick t, and nothing in it changes "
    "before the next release. asr.segments is the complete list of segments since tick 0, sorted by seg_id; "
    "seg_id follows onset, so start is non-decreasing down the list, and two segments may share a start. "
    "Fields: channel names the source (lecturer = the lecturer's headset; moderator = the moderator's "
    "handheld; room = ceiling microphones above the seats; media = a playing clip's soundtrack); start = the "
    "first tick with speech; end = the last tick with speech so far; start <= end <= now always holds.",
    "Settled and working segments. stable = true marks a settled segment: from then on nothing in it changes "
    "(it stays settled, with the same words, confidences and end), and some segments are already settled when "
    "they first appear. stable = false marks a working (unstable) segment: the recogniser publishes only its "
    "latest hypothesis, and a later snapshot may change, add or remove any of its words and change their "
    "confidences or its end. Text form: a working segment uses lower-case letters only, no punctuation, "
    "numbers as words; a settled one may add capitals and attached punctuation and may use digits. seg_id, "
    "channel and start never change. Only a channel's newest segment can be working, so no channel ever has "
    "two; segments on different channels may overlap in time. In this recording every segment ends up "
    "settled and no segment disappears. No answer depends on a working segment, even one that already reads "
    "as a complete command with confident words: its settled form may continue past the phrase or include a "
    "word below the threshold.",
    "Reading words. Each entry of words is one recognised word w with its confidence conf, a number from 0 to "
    "1. A word reads as w in lower case with anything other than a letter or digit dropped: "
    "'Console,' reads console and '6.' reads 6. No word reads as empty. Capitals and punctuation therefore "
    "never matter, and a segment's reading is the list of its word readings in order.",
    "Commands. A command is a stable segment on the lecturer or moderator channel whose reading is the wake "
    "word (controller.wake_word), then exactly one phrase from that speaker's list, then at most a closing "
    "'please', and nothing else; in addition every one of its words, the wake word and please included, must "
    "have conf of at least controller.min_confidence (a conf equal to the threshold passes; a single word below "
    "it voids the whole segment). The wake word must be the first word: 'So, console, next slide' is ordinary "
    "speech, and so is a segment with a second phrase, a please anywhere but last, or any other extra word. "
    "Room and media segments never command, whatever they say, and a phrase from one speaker's list said on "
    "the other speaker's channel is ordinary speech.",
    "Lecturer phrases. Slides: 'next slide'; 'previous slide'; 'slide N' or 'go to slide N', where N is written "
    "in the digits 0 to 9 (read as a decimal number) or as one number word from one to twenty; 'show TITLE' or "
    "'show the TITLE', where TITLE is a slide title from slides.titles, word for word. Clip: 'play', 'pause' or "
    "'stop', followed by 'video', 'the video', 'audio' or 'the audio'; both nouns work on every slide listed in "
    "slides.media. Pointer: 'spotlight'; 'zoom in'; 'zoom out' or 'pointer off' (both set the pointer off). "
    "Recording: 'pause recording'; 'resume recording'; 'record this slide' (no other article or word: 'pause "
    "the recording' and 'record the slide' are ordinary speech). Moderator phrases, exactly as written: 'open "
    "the poll'; 'close the poll'; 'take a break'; 'resume the lecture'; 'end the lecture'.",
    "Deck. slides.count is the number of slides, and slides.titles maps each slide number from 1 to count, "
    "written as a string, to its title. Titles are distinct, made of lower-case letters and single spaces, and "
    "none begins with 'the' or ends with 'please'. slides.media lists the numbers of the slides that carry a "
    "video or audio clip, and slides.unpublished the numbers of the slides that show results not yet published. "
    "A slide command naming a number outside 1 to count, or a title that is not in the deck, has no effect.",
    "Replay. At tick 0 the console is in lecture mode on slide 1 with the pointer off, the recording setting "
    "on, no clip held and no slide cleared. Commands take effect one at a time in order of their segment's end, "
    "and for equal ends in seg_id order; the current answers are what replaying every command from tick 0 in "
    "that order gives. So a command whose segment turns stable late still takes effect at its end, ahead of "
    "commands that ended later, even if those were already applied. A command that does not apply in the "
    "current mode has no effect, and once the lecture has ended no command has any effect.",
    "Lecture mode: slide commands move the slide (next adds 1 but stays at count on the last slide; previous "
    "subtracts 1 but stays at 1; slide N, go to slide N and show TITLE select that slide); pointer commands set "
    "the pointer; play on a slide listed in slides.media opens that slide's clip in media mode, playing, while "
    "play on any other slide, and pause or stop in lecture mode, have no effect. Media mode: play sets the clip "
    "playing, pause sets it paused, and stop closes the clip and returns to lecture mode on the same slide; "
    "slide and pointer commands have no effect until the clip is stopped. Poll and break modes: slide, pointer "
    "and clip commands have no effect. Apart from the end of the lecture, stop is the only command that "
    "closes a clip.",
    "Moderator commands: open the poll, in lecture or media mode, gives poll mode with the panel collecting "
    "votes; close the poll, in poll mode, turns the panel to results; take a break, in lecture, media or poll "
    "mode, gives break mode; end the lecture, in any mode, gives ended. A poll or break called in media mode "
    "holds the clip instead of closing it, and the clip stays held through a break called during that poll. "
    "resume the lecture, in poll or break mode, gives media mode with the held clip paused when a clip is held, "
    "whether it was playing or paused before, and otherwise lecture mode; either way on the slide already "
    "selected, and the clip is no longer held. The pointer returns to off whenever the slide number changes "
    "and whenever the mode changes; a slide command that leaves the number as it is (next on the last slide, "
    "previous on slide 1, or naming the current slide) keeps the pointer.",
    "Recording. The recording setting is changed by the lecturer's pause recording (to paused) and resume "
    "recording (to on), in every mode until the end. record this slide, also in every mode until the end, "
    "clears the selected slide for the archive and leaves the setting as it is; a clearance covers only the "
    "current visit and lapses as soon as the slide number changes, so coming back to a slide needs a new "
    "record this slide. Recording light: off once the lecture has ended; otherwise paused in break mode; "
    "otherwise paused while the setting is paused; otherwise, in lecture or media mode, paused while the "
    "selected slide is listed in slides.unpublished and is not cleared; otherwise on. In poll mode the "
    "projector shows the poll panel, so an unpublished slide behind it does not pause the light.",
    "Timer cue, from session.ends_at, the currently scheduled end (the moderator's tablet may move it; only "
    "this field counts, never remarks about time): none once the lecture has ended; otherwise overtime when "
    "now >= ends_at; otherwise wrap_up when now >= ends_at - controller.warning_ticks; otherwise none. Both "
    "comparisons count equality.",
    "Decision. stage_mode is the route; projected_slide, recording_light and timer_cue apply in every mode; "
    "lecture adds pointer, media adds media_state, poll adds poll_panel, and break and ended add nothing. Every "
    "answer outside the active branch is none.",
]

SETTING = (
    "Fictional final evening of the Ocean Sound and Society lecture series in the Corran lecture theatre of "
    "the Saltmarsh Institute of Ocean Science, open to the public, streamed online and captured for the "
    "institute's archive. "
    "A lecture console listens to four recogniser channels and, when addressed by its wake word, drives the "
    "projector, a pointer effect on the projected slide, the clip player, the class poll panel, the capture "
    "light on the archive camera and the countdown on the lectern screen. That evening the console was under "
    "evaluation and connected to nothing: the booth technician carried out the lecturer's and the moderator's "
    "spoken orders by hand, and the console's outputs were saved to a file to be compared with the "
    "technician's afterwards."
)

TITLES = ["welcome", "sound in seawater", "hydrophone moorings", "sperm whale dive", "shipping lanes",
          "noise budget", "spectrogram reading", "reef chorus", "quiet harbour trial", "open recordings",
          "further reading", "acknowledgements"]
MEDIA_SLIDES = [4, 8]
UNPUBLISHED_SLIDES = [9]


# ---------------------------------------------------------------- reference

def _reading(word: str) -> str:
    """A word's reading: lower case, every character that is not a letter or digit removed."""
    return "".join(ch for ch in word.lower() if ch.isalnum())


def _readings(segment: dict) -> list[str]:
    return [_reading(item["w"]) for item in segment["words"]]


def _number(token: str) -> int | None:
    if re.fullmatch(r"[0-9]+", token):
        return int(token)
    return NUMBER_WORDS.get(token)


def _lecturer_phrase(body: tuple[str, ...], titles: dict[str, str]) -> tuple[str, Any] | None:
    if body == ("next", "slide"):
        return "slide", "next"
    if body == ("previous", "slide"):
        return "slide", "previous"
    if (len(body) == 2 and body[0] == "slide") or (len(body) == 4 and body[:3] == ("go", "to", "slide")):
        n = _number(body[-1])
        return ("slide", n) if n is not None else None
    if body[:1] == ("show",) and len(body) > 1:
        rest = body[2:] if body[1] == "the" else body[1:]
        name = " ".join(rest)
        return "slide", next((int(k) for k, title in titles.items() if title == name), None)
    if len(body) in (2, 3) and body[0] in CLIP_VERBS and body[-1] in CLIP_NOUNS and (
            len(body) == 2 or body[1] == "the"):
        return "clip", body[0]
    if body in POINTER_PHRASES:
        return "pointer", POINTER_PHRASES[body]
    if body in RECORDING_PHRASES:
        return "recording", RECORDING_PHRASES[body]
    return None


def _command(segment: dict, controller: dict, titles: dict[str, str]) -> tuple[str, Any] | None:
    """The command a segment states under the published form, or None for ordinary speech."""
    if not segment["stable"] or segment["channel"] not in COMMANDING:
        return None
    if any(item["conf"] < controller["min_confidence"] for item in segment["words"]):
        return None
    tokens = _readings(segment)
    if not tokens or tokens[0] != _reading(controller["wake_word"]):
        return None
    body = tuple(tokens[1:-1] if len(tokens) > 1 and tokens[-1] == "please" else tokens[1:])
    if segment["channel"] == "moderator":
        return ("moderator", MODERATOR_PHRASES[body]) if body in MODERATOR_PHRASES else None
    return _lecturer_phrase(body, titles)


def _replay(state: dict) -> dict[str, Any]:
    controller, slides = state["controller"], state["slides"]
    count, clips = slides["count"], set(slides["media"])
    run = {"mode": "lecture", "slide": 1, "pointer": "off", "clip": "playing", "held": False,
           "panel": "collecting", "recording": "on", "cleared": False}
    for segment in sorted(state["asr"]["segments"], key=lambda s: (s["end"], s["seg_id"])):
        command = _command(segment, controller, slides["titles"])
        if command is None or run["mode"] == "ended":
            continue
        kind, arg = command
        mode, slide = run["mode"], run["slide"]
        if kind == "recording":
            if arg == "clear":
                run["cleared"] = True
            else:
                run["recording"] = arg
        elif kind == "moderator":
            if arg == "open_poll" and mode in ("lecture", "media"):
                run.update(mode="poll", panel="collecting", held=run["held"] or mode == "media")
            elif arg == "close_poll" and mode == "poll":
                run["panel"] = "results"
            elif arg == "break" and mode in ("lecture", "media", "poll"):
                run.update(mode="break", held=run["held"] or mode == "media")
            elif arg == "resume" and mode in ("poll", "break"):
                if run["held"]:
                    run.update(mode="media", clip="paused", held=False)
                else:
                    run["mode"] = "lecture"
            elif arg == "end":
                run["mode"] = "ended"
        elif mode == "lecture":
            if kind == "slide":
                target = slide + 1 if arg == "next" else slide - 1 if arg == "previous" else arg
                if target is not None and 1 <= target <= count:
                    run["slide"] = target
            elif kind == "pointer":
                run["pointer"] = arg
            elif kind == "clip" and arg == "play" and slide in clips:
                run.update(mode="media", clip="playing")
        elif mode == "media" and kind == "clip":
            if arg == "stop":
                run["mode"] = "lecture"
            else:
                run["clip"] = "playing" if arg == "play" else "paused"
        if run["slide"] != slide:
            run["cleared"] = False
        if (run["mode"], run["slide"]) != (mode, slide):
            run["pointer"] = "off"
    return run


def reference(state: dict) -> dict[str, str]:
    """Derive every answer from the public state alone (no tick index, gold or hidden field)."""
    run = _replay(state)
    mode = run["mode"]
    now, ends_at = state["now"], state["session"]["ends_at"]
    if mode == "ended":
        light = "off"
    elif mode == "break" or run["recording"] == "paused":
        light = "paused"
    elif mode in ("lecture", "media") and run["slide"] in state["slides"]["unpublished"] and not run["cleared"]:
        light = "paused"
    else:
        light = "on"
    if mode == "ended":
        timer = "none"
    elif now >= ends_at:
        timer = "overtime"
    elif now >= ends_at - state["controller"]["warning_ticks"]:
        timer = "wrap_up"
    else:
        timer = "none"
    return {
        "stage_mode": mode,
        "projected_slide": f"slide_{run['slide']}",
        "recording_light": light,
        "timer_cue": timer,
        "pointer": run["pointer"] if mode == "lecture" else "none",
        "media_state": run["clip"] if mode == "media" else "none",
        "poll_panel": run["panel"] if mode == "poll" else "none",
    }


# ---------------------------------------------------------------- questions and decision

def _choice(instructions: str, **criteria: str) -> dict[str, Any]:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def _questions() -> dict[str, Any]:
    def label(n: int, title: str) -> str:
        notes = [note for note, listed in (("clip attached", MEDIA_SLIDES), ("results unpublished",
                                                                            UNPUBLISHED_SLIDES)) if n in listed]
        return f"{title.capitalize()} (number {n} of {len(TITLES)}" + "".join(f"; {note}" for note in notes) + ")"

    slides = {f"slide_{n}": label(n, title) for n, title in enumerate(TITLES, 1)}
    return {
        "stage_mode": _choice(
            "Which mode is the lecture console in? Replay the stable wake-word commands of the lecturer and the "
            "moderator in order of segment end (equal ends in seg_id order), from lecture mode at tick 0; "
            "resuming after a poll or break that was called during a clip goes back to media mode. Unstable "
            "hypotheses, room and media speech and segments with any word below the confidence threshold never "
            "change it.",
            lecture="The lecturer talks over the projected slide",
            media="A video or audio clip from the slide is up in the player",
            poll="The class poll panel covers the projector", **{"break": "Intermission called by the moderator"},
            ended="Lecture over; the console ignores every further command"),
        "projected_slide": _choice(
            "Which slide does the projector hold? Replay commands in order of segment end from slide 1: only "
            "stable lecturer slide commands that meet lecture mode at their place in that order move it; in "
            "media, poll and break mode and after the end they have no effect.", **slides),
        "recording_light": _choice(
            "What does the capture light on the archive camera show? off after the end; paused in break mode or "
            "while the lecturer's last pause recording or resume recording command (in replay order) left the "
            "setting paused; paused in lecture or media mode on a slide from slides.unpublished unless the "
            "lecturer said record this slide since the projector last arrived on that slide; otherwise on.",
            on="Capturing", paused="Capture paused", off="Capture finished: the lecture has ended"),
        "timer_cue": _choice(
            "Which cue does the lectern countdown show? Compare now with session.ends_at: overtime from ends_at "
            "on, wrap_up from ends_at minus controller.warning_ticks on (both bounds inclusive), else none; none "
            "after the end.",
            none="No timing cue", wrap_up="Within the warning window: start wrapping up",
            overtime="The scheduled end has been reached or passed"),
        "pointer": _choice(
            "In lecture mode, which pointer effect is on the projected slide? Stable lecturer pointer commands set "
            "it in lecture mode, and it goes back to off whenever the slide number or the mode changes. none in "
            "every other mode.",
            off="No pointer effect", spotlight="Spotlight on the slide", zoom="Zoomed in on the slide",
            none="Pointer effects are unavailable right now"),
        "media_state": _choice(
            "In media mode, is the slide's clip playing or paused? A clip opens playing and stable lecturer play "
            "and pause commands change it; a clip held through a poll or break comes back paused. none in every "
            "other mode.",
            playing="The clip runs with its sound", paused="The clip waits, frozen where it was left",
            none="No clip in the foreground"),
        "poll_panel": _choice(
            "In poll mode, what does the poll panel show? collecting from the moderator's open command until the "
            "moderator's close command, then results. none in every other mode.",
            collecting="Collecting votes", results="Showing the results", none="The poll panel is hidden"),
    }


DECISION_SPEC = {
    "route_question": "stage_mode", "always": ["projected_slide", "recording_light", "timer_cue"],
    "branches": {"lecture": ["pointer"], "media": ["media_state"], "poll": ["poll_panel"], "break": [],
                 "ended": []},
}


# ---------------------------------------------------------------- story

MIN_CONFIDENCE = 0.85


def _conf(seg_id: int, index: int, word: str, stable: bool) -> float:
    """Deterministic word confidences: stable words 0.86 to 0.99, hypothesis words 0.64 to 0.93."""
    h = zlib.crc32(f"{seg_id}:{index}:{word}".encode())
    return round(0.86 + (h % 14) / 100, 2) if stable else round(0.64 + (h % 30) / 100, 2)


def _seg(seg_id: int, channel: str, start: int, end: int, text: str, *, stable: bool = True,
         confident: bool = False, conf: dict[int, float] | None = None) -> dict[str, Any]:
    """One segment snapshot; confident scores a hypothesis like stable words (all above the threshold), and conf
    overrides individual word confidences by position."""
    words = text.split(" ")
    if not stable and not all(re.fullmatch(r"[a-z]+", w) for w in words):
        raise ValueError(f"unstable words must be lower-case letters: {text!r}")
    if len(words) > 6 * (end - start + 1):
        raise ValueError(f"segment {seg_id} speaks faster than three words a second: {text!r}")
    items = [{"w": w, "conf": _conf(seg_id, i, w, stable or confident)} for i, w in enumerate(words)]
    for index, value in (conf or {}).items():
        items[index]["conf"] = value
    return {"seg_id": seg_id, "channel": channel, "start": start, "end": end, "stable": stable, "words": items}


L, M, R, X = "lecturer", "moderator", "room", "media"


def _schedule() -> dict[int, dict[str, Any]]:
    """Tick -> segment snapshots, session updates and an authoring note (kept out of the state)."""
    s = _seg
    return {
        0: {"segments": [s(1, L, 0, 0, "good evening everyone", stable=False)],
            "note": "No command yet: lecture mode on slide 1, pointer off, capture on."},
        1: {"segments": [s(1, L, 0, 1, "Good evening, everyone, and welcome to the last lecture of the series.")]},
        2: {"segments": [s(2, L, 2, 2, "console next slide", stable=False)],
            "note": "An unstable command hypothesis is not a command yet."},
        3: {"segments": [s(2, L, 2, 2, "Console, next slide.")],
            "note": "The segment turns stable with every word above threshold: slide 2."},
        4: {"segments": [s(3, L, 4, 4, "sound moves more than four times", stable=False)]},
        5: {"segments": [s(3, L, 4, 5, "Sound moves more than four times faster in seawater than in air."),
                         s(4, R, 5, 5, "console next slide", stable=False)]},
        6: {"segments": [s(4, R, 5, 6, "Console, next slide!"),
                         s(5, L, 6, 6, "Nice try. Not from the seats.")],
            "note": "A student says the full command on the room channel: room speech never commands."},
        7: {"segments": [s(6, L, 7, 7, "console go to slide three", stable=False, confident=True)],
            "note": "The hypothesis reads as a complete command with every word confident, but it is not stable."},
        8: {"segments": [s(6, L, 7, 8, "Console, go to slide three.", conf={4: 0.84})],
            "note": "Once stable, one word sits at 0.84, below min_confidence 0.85: the whole segment is void, so "
                    "the hypothesis of tick 7 never takes effect."},
        9: {"segments": [s(7, L, 9, 9, "Console, go to slide 3.")],
            "note": "The repeated command passes, with the number in digits: slide 3."},
        10: {"segments": [s(8, L, 10, 10, "these moorings sit on the", stable=False)]},
        11: {"segments": [s(8, L, 10, 11, "These moorings sit on the shelf edge, two hundred metres down.")]},
        12: {"segments": [s(9, L, 12, 12, "Console, zoom in.")],
             "note": "Pointer zoom in lecture mode."},
        13: {"segments": [s(10, L, 13, 13, "That grey box is the recorder.")]},
        14: {"segments": [s(11, L, 14, 14, "Console, zoom out.")],
             "note": "Zoom out sets the pointer off on the same slide."},
        15: {"segments": [s(12, L, 15, 15, "So, console, next slide.")],
             "note": "The wake word is not the first word: ordinary speech."},
        16: {"segments": [s(13, L, 16, 16, "console next slide please", stable=False)]},
        17: {"segments": [s(13, L, 16, 16, "Console, next slide, please.")],
             "note": "Closing please is allowed: slide 4."},
        18: {"segments": [s(14, L, 18, 18, "Console, play the video.")],
             "note": "Slide 4 carries a clip: media mode, playing."},
        19: {"segments": [s(15, X, 19, 19, "at four hundred metres she", stable=False),
                          s(16, L, 19, 19, "console next slide", stable=False)]},
        20: {"segments": [s(15, X, 19, 20, "At four hundred metres she begins to click faster."),
                          s(16, L, 19, 19, "Console, next slide.")],
             "note": "Slide commands have no effect in media mode."},
        21: {"segments": [s(17, L, 21, 21, "before she dives guess how", stable=False)]},
        22: {"segments": [s(17, L, 21, 22, "Before she dives, guess how deep she goes.")]},
        23: {"segments": [s(18, M, 23, 23, "Console, open the poll.")],
             "note": "Poll opened during the playing clip: poll mode, collecting, and the clip is held."},
        24: {"segments": [s(19, R, 24, 24, "she cant go two", stable=False)]},
        25: {"segments": [s(19, R, 24, 25, "She can't go two kilometres down!"),
                          s(20, L, 25, 25, "Console, close the poll.")],
             "note": "Close the poll is a moderator phrase: from the lecturer it is ordinary speech."},
        26: {"segments": [s(21, M, 26, 26, "Console, close the poll, please.")],
             "note": "Moderator closes the poll: results."},
        27: {"segments": [s(22, M, 27, 27, "Console, resume the lecture.")],
             "note": "The held clip comes back in media mode, paused, although it was playing when the poll "
                     "opened."},
        28: {"segments": [s(23, L, 28, 28, "Console, play video.")],
             "note": "Play without the article: the clip plays again."},
        29: {"segments": [s(24, X, 29, 29, "There. That buzz is the strike.")]},
        30: {"segments": [s(25, L, 30, 30, "Console, stop the video.")],
             "note": "Stop closes the clip: lecture mode on slide 4."},
        31: {"segments": [s(26, L, 31, 31, "Console, show noise budget.")],
             "note": "Show TITLE without the article: slide 6."},
        32: {"segments": [s(27, L, 32, 32, "console zoom in", stable=False, confident=True)],
             "note": "A confident hypothesis that reads as zoom in, still unstable."},
        33: {"segments": [s(27, L, 32, 33, "Console, zoom in on the red band.")],
             "note": "The stable segment runs on past the phrase: ordinary speech, and the pointer stays off."},
        34: {"segments": [s(28, L, 34, 34, "Console, spotlight.")],
             "note": "The lecturer settles for the spotlight: pointer spotlight."},
        35: {"segments": [s(29, M, 35, 35, "good news the next booking", stable=False)],
             "note": "now 35 = ends_at 43 - warning_ticks 8: wrap_up (equality counts)."},
        36: {"segments": [s(29, M, 35, 36, "good news the next booking was cancelled so", stable=False)]},
        37: {"segments": [s(29, M, 35, 37, "Good news: the room's next booking was cancelled, so we can run a "
                                           "little longer.")],
             "session": {"ends_at": 54},
             "note": "The moderator's tablet moves ends_at to 54: no timing cue until tick 46."},
        38: {"segments": [s(30, L, 38, 38, "console show the reef", stable=False)]},
        39: {"segments": [s(30, L, 38, 39, "Console, show the reef chorus.", conf={4: 0.85})],
             "note": "A word exactly at the threshold passes: slide 8 by title, and the slide change resets the "
                     "spotlight."},
        40: {"segments": [s(31, L, 40, 40, "the fishers asked us not", stable=False)]},
        41: {"segments": [s(31, L, 40, 41, "The fishers asked us not to archive this one.")]},
        42: {"segments": [s(32, L, 42, 42, "Console, pause recording.")],
             "note": "Recording setting paused."},
        43: {"segments": [s(33, L, 43, 43, "Console, play audio.")],
             "note": "Media mode, playing; the paused setting keeps the capture paused across the mode change."},
        44: {"segments": [s(34, L, 44, 44, "that crackle is snapping", stable=False),
                          s(35, M, 44, 44, "sorry tamsin", stable=False)]},
        45: {"segments": [s(34, L, 44, 45, "That crackle is snapping shrimp, thousands of them on a single reef."),
                          s(35, M, 44, 45, "sorry tamsin the online stream has lost", stable=False)]},
        46: {"segments": [s(35, M, 44, 46, "Sorry, Tamsin, the online stream has lost its sound; we need a "
                                           "short break.")],
             "note": "now 46 = ends_at 54 - 8: wrap_up again. The moderator's remark is ordinary speech."},
        47: {"segments": [s(36, L, 47, 47, "Console, pause the audio.")],
             "note": "Clip paused."},
        48: {"segments": [s(37, L, 48, 48, "Console, stop the audio.")],
             "note": "Clip closed: lecture mode on slide 8, capture still paused by the setting."},
        49: {"segments": [s(38, L, 49, 49, "Console, resume recording.")],
             "note": "Capture on again."},
        50: {"segments": [s(39, L, 50, 50, "console next slide", stable=False),
                          s(40, M, 50, 50, "Console, take a break.")],
             "note": "The moderator calls the break for the stream; the lecturer's slide command, begun in the "
                     "same tick, is still unstable."},
        51: {"segments": [s(39, L, 50, 50, "Console, next slide."),
                          s(41, M, 51, 51, "The stream sound is back.")],
             "note": "Both commands ended at tick 50; the lecturer's began first (lower seg_id), so it moves to "
                     "slide 9 in lecture mode before the break applies. The moderator's remark is not a command."},
        52: {"segments": [s(42, M, 52, 52, "Console, resume the lecture.")],
             "note": "Lecture mode on slide 9, which is unpublished and not cleared: capture paused."},
        53: {"segments": [s(43, M, 53, 53, "Console, record this slide."),
                          s(44, L, 53, 53, "the harbour paper came out", stable=False)],
             "note": "Record this slide is a lecturer phrase: from the moderator it is ordinary speech."},
        54: {"segments": [s(44, L, 53, 54, "The harbour paper came out on Monday, so we can archive this.")],
             "note": "now 54 = ends_at: overtime."},
        55: {"segments": [s(45, L, 55, 55, "Console, record this slide.")],
             "note": "The lecturer clears slide 9 for this visit: capture on."},
        56: {"segments": [s(46, L, 56, 56, "Console, slide ten.")],
             "note": "A number word selects slide 10, which is published: capture on."},
        57: {"segments": [s(47, L, 57, 57, "Console, previous slide.")],
             "note": "Back on slide 9: the clearance lapsed when the slide changed, so capture is paused again."},
        58: {"segments": [s(48, M, 58, 58, "Console, end the lecture.")],
             "note": "Moderator ends the lecture: capture off, no timing cue."},
        59: {"segments": [s(49, L, 59, 59, "Console, record this slide.")],
             "note": "No command has any effect after the end."},
    }


def _initial() -> dict[str, Any]:
    return {
        "controller": {"wake_word": "console", "min_confidence": MIN_CONFIDENCE, "warning_ticks": 8,
                       "rules": RULES},
        "session": {"course": "Ocean Sound and Society, evening lecture series",
                    "lecturer": "Tamsin Valdez", "moderator": "Elliot Fairbanks",
                    "setting": SETTING, "ends_at": 43},
        "slides": {"count": len(TITLES), "titles": {str(n): t for n, t in enumerate(TITLES, 1)},
                   "media": list(MEDIA_SLIDES), "unpublished": list(UNPUBLISHED_SLIDES)},
        "asr": {"segments": []},
        "now": 0,
    }


def _build() -> dict[str, Any]:
    live = _initial()
    schedule = _schedule()
    steps = []
    for tick in range(60):
        live["now"] = tick
        update = deepcopy(schedule.get(tick, {}))
        live["session"].update(update.get("session", {}))
        segments = live["asr"]["segments"]
        changed = []
        for snapshot in update.get("segments", []):
            if snapshot["end"] > tick:
                raise ValueError(f"segment from the future at tick {tick}")
            index = next((i for i, seg in enumerate(segments) if seg["seg_id"] == snapshot["seg_id"]), None)
            if index is None:
                segments.append(snapshot)
            else:
                if segments[index]["stable"]:
                    raise ValueError(f"stable segment {snapshot['seg_id']} revised at tick {tick}")
                segments[index] = snapshot
            changed.append(snapshot)
        state = deepcopy(live)
        evidence = ["controller.rules holds the complete console rules."]
        for seg in changed:
            text = " ".join(item["w"] for item in seg["words"])
            evidence.append(f"segment {seg['seg_id']} on {seg['channel']} "
                            f"({'stable' if seg['stable'] else 'unstable'}): {text}")
        if update.get("note"):
            evidence.append(update["note"])
        steps.append({"t": tick, "state": state, "gold": reference(state), "evidence": evidence})
    return {"episode_id": EPISODE_ID, "task_family": "presenter_voice_control", "scenario_id": "presenter_c",
            "title": TITLE, "tick_seconds": 2.0, "questions": _questions(),
            "decision_spec": deepcopy(DECISION_SPEC), "steps": steps}


def scenarios() -> list[dict[str, Any]]:
    """One 60-tick wake-word lecture console episode."""
    return [_build()]
