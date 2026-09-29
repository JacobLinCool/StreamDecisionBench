"""Presentation Navigation: an auto-follow prompter and cue monitor for a live talk (sdb/0.2).

The prompter already knows the talk (script, deck map, rehearsal times) and
follows the presenter live. Every tick it answers two questions: ``position``
(the script unit it highlights and scrolls to) and ``cue`` (the overlay card on
the presenter's display). The state is what a deployed prompter receives, in one
fixed format for both scenarios (``STATE_SCHEMA``): prepared ``talk`` and
``script``; bookkeeping ``clock``, ``slides``, ``channels`` (mixer strips and mic
state), ``mic_log`` and ``media``; live ``voice`` (per-channel VAD and the room's
sound-event detector), ``segments`` (finalized ASR phrases that ended in the
last 90 s) and ``partials``. The speech keys follow REALTIME_FAMILIES.md 3.3;
each mixer channel carries one source, so rows name their ``channel`` (it is
the speaker). Nothing the prompter shows is in the state (4.1).

* ``presentation_a`` (medium, 2 s ticks): a research talk, 07:00-10:18 on the
  talk clock, through a section boundary, a clarification question from the
  floor mic, a lost thread and a section overrun. Six cue rules read voice
  activity, an off-script run and a per-section timer.
* ``presentation_b`` (hard, 1 s ticks): a keynote read from the prompter,
  01:20.5-02:59.5 on the segment clock: a double-click past a must-say
  paragraph, applause, an out-of-order return, a filler stall, a hard out and a
  film that freezes while playback still says "playing". Seven cue rules.

Each scenario is written as timed raw signals: line tables of ``Utterance`` rows
per channel (hidden ``info``: content of which unit, closing, broken off,
filler, aside, reply, sound label), slide clicks, mic changes and playback
events, in two text registers (canonical, paraphrase). ``Show`` holds one
variant's signals and renders them with the declared latencies: ASR finals
0.3 s after speech ends, partials from 0.2 s after it starts, the VAD reporting
silence when the phrase is final, and room sound events reported 0.5 s after
each onset and end. At each read time a ``View`` collects what the rules read;
``facts(view)`` turns it into the latent state and ``policy`` applies the rule
list. ``check`` rebuilds the ``View`` from every rendered state (the windowed
segments, the voice rows, the clock) and requires the same latent, which
proves the renderer guarantees and the evidence timing, then checks the
latencies, threshold margins, read-time coincidences, phrase and mic
consistency and decoy carriers.
"""

from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from streamdecisionbench.authoring import Choice, Question, Scenario, Tick, span_tags
from streamdecisionbench.authoring.stream import (
    EPS,
    Speech,
    Utterance,
    first_tick,
    fmt_mmss,
    margin_problem,
    parse_clock,
    window,
)
from streamdecisionbench.schema import STEPS

FAMILY = "presentation_navigation"
LAG = 0.3  # ASR finalization lag (250 ms endpointing); the VAD reports silence at the same moment
PARTIAL_LAG = 0.2  # the first partial needs 0.2 s of audio
DETECT = 0.5  # the room's sound-event detector reports an onset or an end 0.5 s late
WINDOW = 90.0  # segment and mic-log window in seconds, boundary included
APPLAUSE = ("applause", "cheering")
MIC_STATE = {"on": "live", "unmuted": "live", "off": "off", "muted": "muted"}
BREAK_WORDS = frozenset("um uh er so okay right well the a an and but or of in to".split())

# ---------------------------------------------------------------------------
# The fixed state format (one JSON Schema for both scenarios and all variants)
# ---------------------------------------------------------------------------


def _obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "required": list(properties), "properties": properties}


_TEXT = {"type": "string", "minLength": 1}
_CLOCK = {"type": "string", "pattern": r"^-?\d{2,}:\d{2}\.\d$"}
_MMSS = {"type": "string", "pattern": r"^\d{2}:\d{2}$"}
_CHANNEL = {"enum": ["lapel", "chair", "floor", "host", "room", "program"]}
_OR_DASH = {"anyOf": [_CLOCK, {"const": "-"}]}

# Room states as each register's sound-event detector names them (the paraphrase uses a second vendor's labels).
ROOM_LABELS = {
    "canonical": {"applause": "applause", "cheering": "cheering", "laughter": "laughter", "voices": "voices", "quiet": "quiet"},
    "paraphrase": {"applause": "clapping", "cheering": "cheers", "laughter": "laughs", "voices": "chatter", "quiet": "calm"},
}
ROOM_STATES = sorted({v for labels in ROOM_LABELS.values() for v in labels.values()})


def _tuple(*items: Any) -> dict[str, Any]:
    return {"type": "array", "prefixItems": list(items), "items": False, "minItems": len(items)}


STATE_SCHEMA = _obj({
    "talk": _obj({
        "title": _TEXT, "presenter": _TEXT, "format": _TEXT, "hard_out": _obj({"at": _MMSS, "what": _TEXT}),
        "people": {"type": "array", "items": _TEXT, "minItems": 1, "maxItems": 3}, "notes": _TEXT,
    }),
    "script": {"type": "array", "minItems": 5, "maxItems": 8, "items": _obj({
        "id": {"type": "string", "pattern": r"^[SP]\d$"}, "title": _TEXT,
        "slides": {"type": "string", "pattern": r"^\d+(-\d+)?$"}, "planned_end": _MMSS,
        "must_say": {"type": "boolean"}, "opening": _TEXT,
        "points": {"type": "array", "items": _TEXT, "maxItems": 3}, "closing": _TEXT,
    })},
    "clock": _obj({"now": _CLOCK, "to_hard_out": _CLOCK}),
    "slides": _obj({
        "current": {"type": "integer", "minimum": 1}, "since": _CLOCK,
        "shown": {"type": "string", "pattern": r"^\d+(-\d+)?(,\d+(-\d+)?)*$"},
        "recent_changes": {"type": "array", "maxItems": 4, "items": _tuple(_CLOCK, {"type": "string", "pattern": r"^\d+->\d+$"})},
    }),
    "channels": {"type": "array", "minItems": 4, "maxItems": 4, "items": _obj({
        "channel": _CHANNEL, "who": _TEXT, "mic": {"enum": ["live", "muted", "off"]},
    })},
    "voice": {"type": "array", "minItems": 1, "maxItems": 4, "items": _obj({
        "channel": _CHANNEL, "state": {"enum": ["speaking", "silent", *ROOM_STATES]}, "since": _OR_DASH,
    })},
    "mic_log": {"type": "array", "items": _tuple(_CLOCK, _CHANNEL, {"enum": list(MIC_STATE)})},
    "segments": {"type": "array", "items": _obj({"start": _CLOCK, "end": _CLOCK, "channel": _CHANNEL, "text": _TEXT})},
    "partials": {"type": "array", "maxItems": 2, "items": _obj({"channel": _CHANNEL, "since": _CLOCK, "text": _TEXT})},
    "media": _obj({
        "item": {"type": ["string", "null"]}, "state": {"enum": ["none", "ready", "playing", "paused", "ended"]},
        "position": _OR_DASH, "position_changed_at": _OR_DASH,
    }),
})

# ---------------------------------------------------------------------------
# Timed signals
# ---------------------------------------------------------------------------


def _info(role: str) -> dict[str, Any]:
    """Hidden annotation of one line from its role code.

    ``S3`` / ``P5``: content of that unit; a trailing ``.`` marks its closing,
    ``~`` a phrase that breaks off. ``applause``, ``cheering``, ``laughter``:
    room sound tags. Anything else is a kind: ``filler``, ``aside`` (asides,
    jokes, mentions, ad-libs), ``reply`` (answering a question), ``speech``
    (another person), ``voices`` (audience voices on the room mics), ``program``.
    """
    base = role.rstrip(".~")
    info: dict[str, Any] = {"kind": base, "unit": None, "closing": role.endswith("."), "broke": role.endswith("~")}
    if re.fullmatch(r"[SP]\d", base):
        info.update(kind="content", unit=base)
    elif base in ("applause", "cheering", "laughter"):
        info.update(kind="sound", label=base)
    elif base == "voices":
        info["label"] = "voices"
    return info


Row5 = tuple[float, float, str, str, str, str]  # start, end, channel, role, canonical text, paraphrase text


def _lines(
    rows: list[Row5],
    variant: str,
    revisions: dict[float, tuple[tuple[tuple[float, str], ...], ...]] | None = None,
    decoys: dict[float, str] | None = None,
    edits: dict[float, tuple[str, str] | None] | None = None,
) -> list[Utterance]:
    """Utterances of one variant from a line table (rows are keyed by start time)."""
    starts = [r[0] for r in rows]
    assert len(set(starts)) == len(starts), "line tables are keyed by start time"
    para = variant == "paraphrase"
    out = []
    for start, end, speaker, role, text, alt in rows:
        revs = (revisions or {}).get(start, ((), ()))[1 if para else 0]
        text = alt if para else text
        if variant == "lexical_decoy" and decoys and start in decoys:
            text = decoys[start]
        if variant == "minimal_cf" and edits and start in edits:
            edit = edits[start]
            if edit is None:
                continue
            (role, text), revs = edit, ()
        out.append(Utterance(start, end, speaker, text, tuple(revs), info=_info(role)))
    return out


class Row(NamedTuple):
    """A finalized phrase as the rules read it."""

    start: float
    end: float
    ch: str
    info: dict[str, Any]


@dataclass
class View:
    """Everything the rules read at one read time, from the model or from a rendered state."""

    now: float
    rows: list[Row]  # finalized phrases, oldest first by start
    voice: dict[str, tuple[str | None, float | None]]  # channel -> (speaking/silent, since); (None, None) muted or off
    room: tuple[str, float | None]  # (sound event now, its onset) | ("quiet", end of the last event or None)
    units: dict[str, tuple[float, bool]]  # unit id -> (planned_end, must_say), script order
    to_hard_out: float
    media: tuple[str, float | None]  # playback state, position_changed_at


@dataclass
class Show:
    """One variant of a scenario as timed signals: everything the renderer and ``facts`` read."""

    register: str
    talk: dict[str, Any]
    script: list[dict[str, Any]]
    utterances: list[Utterance]
    channels: list[tuple[str, str]]
    mics: dict[str, str]
    mic_events: list[tuple[float, str, str]]
    slide0: int
    slide_changes: list[tuple[float, int]]
    hard_out: float
    media_item: str | None = None
    media_events: list[tuple[float, float, bool]] = field(default_factory=list)  # (at, position, advancing)

    def __post_init__(self) -> None:
        self.speech = Speech(self.utterances, lag=LAG, window=WINDOW, partial_lag=PARTIAL_LAG, hangover=LAG)
        self.room = [u for u in self.speech.utterances if u.speaker == "room"]
        self.units = {u["id"]: (parse_clock(u["planned_end"]), u["must_say"]) for u in self.script}
        self.info = {(fmt_mmss(u.start), fmt_mmss(u.end), u.speaker): u.info for u in self.utterances}

    def mic_at(self, T: float) -> dict[str, str]:
        mic = dict(self.mics)
        for at, ch, change in self.mic_events:
            if at <= T + EPS:
                mic[ch] = MIC_STATE[change]
        return mic

    def media_at(self, T: float) -> tuple[str, float | None, float | None]:
        """``(state, position, position_changed_at)``; while advancing, the position updates every 0.5 s."""
        if self.media_item is None:
            return "none", None, None
        started = [e for e in self.media_events if e[0] <= T + EPS]
        if not started:
            return "ready", 0.0, None
        at, position, advancing = started[-1]
        step = math.floor((T - at) / 0.5 + EPS) * 0.5 if advancing else 0.0
        return "playing", position + step, round(at + step, 6)

    def room_at(self, T: float) -> tuple[str, float | None]:
        """The room detector's report: an event and its onset, or quiet since the end of the last one (``DETECT`` late)."""
        seen = [u for u in self.room if u.start + DETECT <= T + EPS]
        now = [u for u in seen if T < u.end + DETECT - EPS]
        if now:
            return now[-1].info["label"], now[-1].start
        return "quiet", max((u.end for u in seen), default=None)

    def voice_at(self, T: float) -> dict[str, tuple[str | None, float | None]]:
        """VAD per voice channel (silence is reported once the phrase is final); (None, None) when the mic is not live."""
        mic = self.mic_at(T)
        return {ch: self.speech.activity(T, ch) if mic[ch] == "live" else (None, None) for ch, _ in self.channels if ch != "room"}

    def view(self, T: float) -> View:
        """The model's view: every phrase finalized so far (no window; ``check`` compares with the windowed state)."""
        state, _, changed = self.media_at(T)
        rows = [Row(u.start, u.end, u.speaker, u.info) for u in self.speech.finals(T)]
        return View(T, rows, self.voice_at(T), self.room_at(T), self.units, self.hard_out - T, (state, changed))

    # -- rendering ----------------------------------------------------------

    def render(self, T: float) -> dict[str, Any]:
        clock, labels = fmt_mmss, ROOM_LABELS[self.register]
        mic, voice, (event, heard) = self.mic_at(T), self.voice_at(T), self.room_at(T)
        rows = []
        for ch, _ in self.channels:
            if mic[ch] == "live":
                state, since = (labels[event], heard) if ch == "room" else voice[ch]
                rows.append({"channel": ch, "state": state, "since": "-" if since is None else clock(since)})
        state, position, changed = self.media_at(T)
        return {
            "talk": copy.deepcopy(self.talk),
            "script": copy.deepcopy(self.script),
            "clock": {"now": clock(T), "to_hard_out": clock(self.hard_out - T)},
            "slides": self._slides(T),
            "channels": [{"channel": ch, "who": who, "mic": mic[ch]} for ch, who in self.channels],
            "voice": rows,
            "mic_log": [[clock(at), ch, change] for at, ch, change in window(self.mic_events, T, lambda e: e[0], seconds=WINDOW)],
            "segments": [{"start": clock(u.start), "end": clock(u.end), "channel": u.speaker, "text": u.text} for u in self.speech.segments(T)],
            "partials": [{"channel": p.speaker, "since": clock(p.since), "text": p.text} for p in self.speech.partials(T)],
            "media": {
                "item": self.media_item,
                "state": state,
                "position": "-" if position is None else clock(position),
                "position_changed_at": "-" if changed is None else clock(changed),
            },
        }

    def _slides(self, T: float) -> dict[str, Any]:
        current, since, changes = self.slide0, None, []
        shown = set(range(1, self.slide0 + 1))
        for at, slide in self.slide_changes:
            if at > T + EPS:
                break
            changes.append([fmt_mmss(at), f"{current}->{slide}"])
            current, since = slide, at
            shown.add(slide)
        runs: list[list[int]] = []
        for n in sorted(shown):
            if runs and n == runs[-1][1] + 1:
                runs[-1][1] = n
            else:
                runs.append([n, n])
        text = ",".join(f"{a}-{b}" if b > a else str(a) for a, b in runs)
        return {"current": current, "since": fmt_mmss(since), "shown": text, "recent_changes": changes[-4:]}


def _read_view(state: dict[str, Any], show: Show) -> View:
    """Rebuild the ``View`` from a rendered state alone (plus the hidden line annotations)."""
    rows = [Row(parse_clock(r["start"]), parse_clock(r["end"]), r["channel"], show.info[(r["start"], r["end"], r["channel"])]) for r in state["segments"]]
    labels = {v: k for k, v in ROOM_LABELS[show.register].items()}
    voice: dict[str, tuple[str | None, float | None]] = {c["channel"]: (None, None) for c in state["channels"] if c["channel"] != "room"}
    room: tuple[str, float | None] = ("quiet", None)
    for row in state["voice"]:
        since = None if row["since"] == "-" else parse_clock(row["since"])
        if row["channel"] == "room":
            room = (labels[row["state"]], since)
        elif row["state"] in ("speaking", "silent"):
            voice[row["channel"]] = (row["state"], since)
        else:
            raise ValueError(f"unreadable voice row {row}")
    units = {u["id"]: (parse_clock(u["planned_end"]), u["must_say"]) for u in state["script"]}
    media = state["media"]
    changed = None if media["position_changed_at"] == "-" else parse_clock(media["position_changed_at"])
    return View(parse_clock(state["clock"]["now"]), rows, voice, room, units, parse_clock(state["clock"]["to_hard_out"]), (media["state"], changed))


def _r(x: float) -> float:
    return round(x, 1) + 0.0


def _ends_in_break(text: str) -> bool:
    words = re.sub(r"[^\w\s']", " ", text.lower()).split()
    return bool(words) and (words[-1] in BREAK_WORDS or words[-3:] == ["where", "was", "i"])


# ---------------------------------------------------------------------------
# The family base class
# ---------------------------------------------------------------------------


class Presentation(Scenario):
    """Shared state format, rendering, timeline and checks of both scenarios."""

    family = FAMILY
    schema_id = "presentation_navigation/1"
    state_schema = STATE_SCHEMA
    prepared_keys = ("talk", "script")
    machine_fields = ("clock", "slides", "channels[].mic", "voice", "mic_log", "media")
    deadline_seconds = 2

    UNIT: str  # latent key of the tracked unit ("section" / "paragraph")
    TEXT: dict[str, dict[str, Any]]  # register -> role, tasks, conventions, rules, cue option texts
    TAGS: dict[str, list[tuple[int, int]]]
    CF_TAGS: dict[str, dict[tuple[int, int], list[str]]] = {}
    NOTES: list[tuple[int, int, str]]
    CF_NOTES: dict[str, list[tuple[int, int, str]]] = {}
    DECOY_CARRIERS: frozenset[str] = frozenset()  # channels on which the decoy variant may add lines
    MAX_PHRASE: float | None = None  # ASR phrase-length limit a scenario declares

    def build_show(self, variant: str) -> Show:
        raise NotImplementedError

    def facts(self, view: View) -> dict[str, Any]:
        raise NotImplementedError

    def quantities(self, z: dict[str, Any]) -> list[tuple[str, float, tuple[float, ...]]]:
        """Computed quantities of a latent state with the thresholds they are compared with."""
        raise NotImplementedError

    def show(self, variant: str) -> Show:
        cache = self.__dict__.setdefault("_shows", {})
        if variant not in cache:
            cache[variant] = self.build_show(variant)
        return cache[variant]

    def questions(self, variant: str) -> list[Question]:
        show = self.show(variant)
        text = self.TEXT[show.register]
        positions = {u["id"]: f"{u['id']} · {u['title']}" for u in show.script}
        return [
            Choice("position", {"role": f"{text['role']} {text['position_task']}", "conventions": text["conventions"], "rules": text["position_rules"]}, positions),
            Choice("cue", {
                "role": f"{text['role']} {text['cue_task']}",
                "conventions": text["conventions"],
                text["current_key"]: [text["current"], *text["position_rules"]],
                "rules": text["cue_rules"],
            }, dict(text["cues"])),
        ]

    def timeline(self, variant: str) -> list[Tick]:
        show = self.show(variant)
        tags = span_tags(self.TAGS)
        for (a, b), spec in self.CF_TAGS.get(variant, {}).items():
            for t in range(a, b + 1):
                tags[t] = list(spec)
        if variant == "lexical_decoy":
            canonical = {(u.start, u.speaker, u.text) for u in self.show("canonical").utterances}
            for t in range(STEPS):
                if any((u.start, u.speaker, u.text) not in canonical for u in show.speech.segments(self.read_time(t))):
                    tags[t].append("decoy")
        notes = [""] * STEPS
        for a, b, note in self.NOTES + self.CF_NOTES.get(variant, []):
            for t in range(a, b + 1):
                notes[t] = note
        return [Tick(self.facts(show.view(self.read_time(t))), {}, tags[t], notes[t]) for t in range(STEPS)]

    def render(self, history: list[Tick], variant: str) -> dict[str, Any]:
        return self.show(variant).render(self.read_time(len(history) - 1))

    # -- guarantees -----------------------------------------------------------

    def check(self, variant: str, ticks: list[Tick], golds: list[dict[str, Any]], states: list[dict[str, Any]]) -> list[str]:
        """Renderer guarantees, evidence timing, latencies, threshold margins, line consistency and decoy carriers.

        The latent state re-derived from each rendered state must equal the
        tick's latent state. The model view reads every finalized phrase, the
        state view only the 90-s window, so equality proves that every phrase a
        rule reads is still in the window (the renderer guarantees) and that
        each gold change is visible, finalization lag included, at the tick
        where it happens.
        """
        show = self.show(variant)
        problems = list(show.speech.problems()) + self._check_lines(show) + self._check_timing(show, states)
        start = parse_clock(self.window_start)
        reads = [self.read_time(t) for t in range(STEPS)]
        for t, (tick, state) in enumerate(zip(ticks, states)):
            try:
                seen = self.facts(_read_view(state, show))
            except (KeyError, IndexError, ValueError, AttributeError, StopIteration) as error:
                problems.append(f"t={t}: the state cannot be read back ({type(error).__name__}: {error})")
                continue
            if seen != tick.latent:
                problems.append(f"t={t}: the rendered state gives {seen}, the latent state is {tick.latent}")
            for what, value, thresholds in self.quantities(tick.latent):
                problems += [p for th in thresholds if (p := margin_problem(value, th, 0.1, what=f"t={t} {what}"))]
        for t in range(1, STEPS):
            if ticks[t].latent[self.UNIT]["id"] != ticks[t - 1].latent[self.UNIT]["id"]:
                newest = [u for u in show.speech.finals(reads[t], "lapel") if u.info["kind"] == "content"][-1]
                if first_tick(show.speech.final_at(newest), start, self.tick_seconds) != t:
                    problems.append(f"t={t}: the {self.UNIT} changes but its phrase {newest.text[:40]!r} was final earlier")
        if variant == "lexical_decoy":
            problems += self._check_decoys(show, self.show("canonical"))
        if variant == "paraphrase":
            base = {(u.start, u.end, u.speaker): len(u.text.split()) for u in self.show("canonical").utterances}
            for u in show.utterances:
                n, words = base[(u.start, u.end, u.speaker)], len(u.text.split())
                if not 0.8 * n - EPS <= words <= 1.2 * n + EPS:
                    problems.append(f"paraphrase {u.speaker} {fmt_mmss(u.start)}: {words} words for {n} (keep within 20%)")
        return problems

    def _check_timing(self, show: Show, states: list[dict[str, Any]]) -> list[str]:
        """No signal changes exactly at a read time (3.1), and every state shows the declared latencies."""
        problems = []
        reads = [self.read_time(t) for t in range(STEPS)]
        events: list[tuple[float, str]] = []
        for u in show.utterances:
            where = f"{u.speaker} {fmt_mmss(u.start)} {u.text[:30]!r}:"
            if u.speaker == "room":
                events += [(u.start + DETECT, f"{where} the detector reports its onset"), (u.end + DETECT, f"{where} the detector reports its end")]
            else:
                events += [(u.start, f"{where} starts"), (u.end, f"{where} ends"), (u.start + PARTIAL_LAG, f"{where} its first partial appears")]
                events += [(at, f"{where} a partial revision appears") for at, _ in u.revisions]
            events.append((u.end + LAG, f"{where} finalizes"))
        events += [(at, f"mic {ch} {change}") for at, ch, change in show.mic_events]
        events += [(at, f"slide change to {n}") for at, n in show.slide_changes]
        events += [(e[0], "playback event") for e in show.media_events]
        problems += [f"{what} exactly at a read time" for at, what in events if any(abs(at - T) < EPS for T in reads)]
        for t, state in enumerate(states):
            now = parse_clock(state["clock"]["now"])
            for row in state["voice"]:
                late = DETECT if row["channel"] == "room" else LAG if row["state"] == "silent" else 0.0
                if row["since"] != "-" and parse_clock(row["since"]) > now - late + EPS:
                    problems.append(f"t={t}: {row['channel']} reads {row['state']} since {row['since']}, less than {late:g} s ago")
            problems += [f"t={t}: a {p['channel']} partial since {p['since']} has less than {PARTIAL_LAG:g} s of audio"
                         for p in state["partials"] if parse_clock(p["since"]) > now - PARTIAL_LAG + EPS]
        return problems

    def _check_lines(self, show: Show) -> list[str]:
        problems = []
        for u in show.utterances:
            where = f"{u.speaker} {fmt_mmss(u.start)} {u.text[:30]!r}"
            if u.speaker != "room" and any(show.mic_at(T)[u.speaker] != "live" for T in (u.start, u.end)):
                problems.append(f"{where}: spoken while the mic is not live")
            if self.MAX_PHRASE and u.speaker != "room" and u.end - u.start > self.MAX_PHRASE + EPS:
                problems.append(f"{where}: longer than the declared {self.MAX_PHRASE:g}-s ASR phrase limit")
            if (u.info["broke"] or u.text.rstrip().endswith("...")) and not _ends_in_break(u.text):
                problems.append(f"{where}: a broken-off phrase must end in a filler, article or connector")
            if u.info["broke"] and u.info["closing"]:
                problems.append(f"{where}: a phrase cannot both close a unit and break off")
        return problems

    def _check_decoys(self, decoy: Show, canonical: Show) -> list[str]:
        """Decoys reword lines or add lines only on the scenario's allowed carriers (4.1 Variants)."""
        problems = []
        base = {(u.start, u.end, u.speaker): u for u in canonical.utterances}
        seen = set()
        for u in decoy.utterances:
            key = (u.start, u.end, u.speaker)
            old = base.get(key)
            seen.add(key)
            if old is None:
                if u.speaker not in self.DECOY_CARRIERS or (u.speaker == "room" and u.info["kind"] != "voices"):
                    problems.append(f"decoy adds a line on a forbidden carrier: {u.speaker} {u.text!r}")
            elif old.info != u.info:
                problems.append(f"decoy changes the role of {u.speaker} {fmt_mmss(u.start)}")
            elif old.text != u.text and u.speaker in ("chair", "floor", "host"):
                problems.append(f"decoy rewords a {u.speaker} phrase at {fmt_mmss(u.start)}")
        problems += [f"decoy drops {k[2]} {fmt_mmss(k[0])}" for k in base if k not in seen]
        return problems


# ===========================================================================
# presentation_a: research talk, section cues through a mid-talk question
# ===========================================================================

A_TALK = {
    "canonical": {
        "title": "Learned Sparse Retrieval on the Phone",
        "presenter": "Priya Raman",
        "format": "Conference research talk; slot 12:00, then 3:00 Q&A",
        "hard_out": {"at": "12:00", "what": "talk ends; Q&A follows"},
        "people": ["Session chair Tomás Ortega (chair mic, muted by AV between uses)", "Audience (roaming floor mic, switched on by AV)"],
        "notes": "The chair may take one short clarification question mid-talk; other questions wait for Q&A.",
    },
    "paraphrase": {
        "title": "Trained Sparse Search on a Handset",
        "presenter": "Meera Iyer",
        "format": "Conference research presentation; 12:00 slot, then 3:00 of questions",
        "hard_out": {"at": "12:00", "what": "presentation stops; audience questions begin"},
        "people": ["Moderator Jonas Weber (handheld, muted by the sound desk between uses)", "Attendees (wireless floor mic, enabled by the desk)"],
        "notes": "The moderator may allow one brief clarifying question during the talk; the rest wait for the question period.",
    },
}

# id, slides, planned_end, (title, opening, points, closing) per register
A_SCRIPT = [
    ("S1", "1-3", "01:25",
     ("Why on-device search", "Every search on your phone today goes to a server.", ["latency and privacy cost", "offline use is common"], "Can the index live on the phone?"),
     ("Why search on the handset", "Today every phone search is sent to a server.", ["delays and privacy costs", "people are often offline"], "Could the index sit on the handset?")),
    ("S2", "4-6", "03:28",
     ("What exists today", "Two families of retrievers exist today.", ["dense: accurate but ~400 MB", "classic sparse: small but weak"], "Neither fits a phone well."),
     ("Current approaches", "Retrievers come in two kinds today.", ["dense: precise but around 400 MB", "classic sparse: compact but weak"], "Neither suits a handset.")),
    ("S3", "7-10", "05:52",
     ("Our method: a pruned sparse index", "Our idea: keep it sparse, but learn the weights.", ["term weights learned from real queries", "pruning drops low-weight postings", "8-bit quantized, memory-mapped"], "The whole index ends up at about 40 MB."),
     ("Method: a trimmed sparse index", "Our plan: stay sparse, but train the weights.", ["term weights trained on genuine searches", "trimming removes low-weight entries", "8-bit compressed, mapped into memory"], "In total the index weighs about 40 MB.")),
    ("S4", "11-14", "08:33",
     ("Results on three benchmarks", "Does it work? We tested on three benchmarks.", ["news: +12% recall vs best sparse", "code: matches dense at a tenth of the memory", "multilingual: hardest case, still +4 points"], "Smaller, and at least as accurate on all three."),
     ("Evaluation on three test sets", "Is it any good? We ran three test sets.", ["news: 12% more recall than top sparse", "code: equals dense at a tenth of the memory", "many languages: toughest set, still 4 points up"], "More compact, and no less accurate on any.")),
    ("S5", "15-16", "10:05",
     ("Where it breaks", "Where does it break?", ["queries over ~12 words", "index rebuild takes 20 min on device"], "Both are fixable, and that's our next paper."),
     ("Failure cases", "When does it fail?", ["queries past about 12 words", "a 20-minute index rebuild on the handset"], "Both can be fixed: our next paper.")),
    ("S6", "17-18", "11:40",
     ("Takeaways", "Three things to take home.", ["learned sparse fits on a phone", "no accuracy cost on 3 benchmarks", "code is public"], "Thank you; happy to take questions."),
     ("What to remember", "Three things to remember.", ["trained sparse fits on a handset", "no accuracy loss across 3 test sets", "the code is open"], "Thanks, questions are welcome.")),
]

A_ROWS: list[Row5] = [
    (252.0, 253.4, "room", "laughter", "[laughter]", "[laughter]"),
    (331.0, 335.4, "lapel", "S3", "So the index stores, for every term, a weight we learn from real queries.", "For each term, the index keeps a weight that we train on genuine searches."),
    (336.0, 339.8, "lapel", "S3", "Rare terms that people actually search for get high weights.", "Unusual words that users really type end up weighted heavily."),
    (340.6, 344.2, "lapel", "S3", "Common filler terms end up close to zero.", "Everyday padding words sink to almost nothing."),
    (345.0, 349.6, "lapel", "S3", "And that's where the second trick comes in: pruning.", "Which is where trick number two enters: trimming."),
    (350.4, 355.0, "lapel", "S3", "Anything under a weight threshold, we simply drop.", "Anything below a cutoff weight simply gets discarded."),
    (356.0, 360.2, "lapel", "S3", "On the news corpus that removes about 70% of all postings.", "For the news collection, roughly 70% of the entries disappear."),
    (361.0, 365.8, "lapel", "S3", "You'd expect recall to fall off a cliff when you throw that much away.", "Discarding so much, you would think the hit rate would simply collapse."),
    (366.4, 370.0, "lapel", "S3", "It doesn't, because what we drop only matched low-ranked documents.", "It holds up, since the discarded entries only hit poorly ranked pages."),
    (371.0, 376.2, "lapel", "S3", "Then we quantize the surviving weights to 8 bits.", "After that, the remaining weights get squeezed into 8-bit values."),
    (377.0, 381.6, "lapel", "S3", "That halves it again, and the phone can memory-map it directly.", "Size halves again, and the handset maps the file straight in."),
    (382.4, 386.0, "lapel", "S3", "No decompression at query time, which matters for battery.", "Nothing gets unpacked per search, which saves power."),
    (386.8, 391.4, "lapel", "S3", "The whole lookup path runs in under 4 milliseconds.", "A complete lookup finishes in less than 4 milliseconds."),
    (392.2, 396.6, "lapel", "S3", "Including the tokenizer, which honestly was the slowest part.", "That counts word splitting, frankly the most sluggish step."),
    (397.4, 402.0, "lapel", "S3", "So, putting the three pieces together:", "Combining all three ingredients, then:"),
    (402.8, 407.2, "lapel", "S3", "learned weights, pruning, and 8-bit quantization,", "trained weights, trimming, and 8-bit compression,"),
    (408.0, 412.4, "lapel", "S3", "each one shrinks the index, and none of them costs much recall.", "every one makes the index smaller while barely hurting the hit rate."),
    (413.2, 417.6, "lapel", "S3", "So the memory-mapped index never calls a server to answer a query.", "So the mapped-in index never contacts a server to respond to a search."),
    (418.4, 423.0, "lapel", "S3", "Everything, including the ranking model, sits in local storage.", "All of it, ranker included, lives in on-device storage."),
    (423.9, 428.6, "lapel", "S3", "And the part I'm proudest of, honestly, is the size.", "What I'm most pleased with, frankly, is how small it is."),
    (429.4, 433.8, "lapel", "S3", "Because a pruned index is still useless if it doesn't fit next to your photos.", "A trimmed index is still pointless unless it squeezes in alongside your holiday pictures."),
    (434.6, 438.2, "lapel", "S3", "We were aiming for under 100 megabytes.", "Our target was below 100 megabytes."),
    (438.6, 441.6, "lapel", "S3.", "And the whole index ends up at about 40 megabytes.", "All told, the index comes to roughly 40 megabytes."),
    (450.2, 451.4, "lapel", "S4", "Right. Does it work?", "Okay, is it good?"),
    (452.2, 456.2, "lapel", "S4", "We tested on 3 benchmarks: news, code, and a multilingual set.", "We ran 3 test sets: news, code, and one spanning many languages."),
    (457.0, 461.6, "lapel", "S4", "First, news: 12% better recall than the best sparse baseline.", "News comes first: recall 12% above the strongest sparse competitor."),
    (462.2, 466.4, "lapel", "aside", "There are cases where it breaks, and I'll get to those in a minute.", "It does fail in some cases, and I'll come back to those failures shortly."),
    (467.0, 470.6, "lapel", "S4", "Second, code search, where queries are short and full of identifiers.", "Next is code search, with brief queries packed with variable names."),
    (471.2, 475.4, "lapel", "S4", "Here we match the dense retriever almost exactly, at a tenth of the memory.", "There we are level with the dense model, using a tenth of its memory."),
    (476.2, 479.6, "lapel", "S4", "The dense model needs 400 megabytes; we need 40.", "The dense approach takes 400 megabytes; ours takes just 40."),
    (480.4, 485.4, "lapel", "aside", "Quick confession: I ran every one of these numbers on my own phone,", "Small admission: all of these results came from my personal handset,"),
    (486.2, 490.6, "lapel", "aside", "which is also my alarm clock, which is why I nearly missed this session.", "the same one that wakes me up, so I almost slept through this session."),
    (490.8, 492.8, "room", "laughter", "[laughter]", "[laughter]"),
    (492.2, 494.8, "lapel", "S4", "Anyway: code search, same accuracy, a tenth the size.", "So: code, equal quality at a tenth the footprint."),
    (495.6, 499.4, "chair", "speech", "Sorry to jump in, Priya. A quick clarification question from the floor.", "Apologies for cutting in, Meera. A short clarifying question from the audience."),
    (500.8, 503.6, "floor", "speech", "Thanks. On the news benchmark,", "Thank you. About the news results,"),
    (504.2, 507.8, "floor", "speech", "was the 12% with pruning turned on, or off?", "did the 12% figure use trimming or not?"),
    (508.6, 511.0, "lapel", "reply", "Pruning on. Good question.", "Trimming enabled. Fair point."),
    (511.6, 515.8, "lapel", "reply", "Let me go back to the pruning slide, this one.", "I'll jump back to the trimming slide, here."),
    (516.8, 521.8, "lapel", "reply", "So the 12% is with pruning, dropping low-weight postings at ratio 0.3.", "The 12% uses trimming, which discards low-weight entries, at ratio 0.3."),
    (522.6, 527.8, "lapel", "reply", "Without pruning, recall is about the same, but the index is 3 times bigger.", "Turn trimming off and the hit rate barely moves, yet the index grows 3-fold."),
    (528.6, 533.4, "lapel", "reply", "So pruning costs almost nothing, and it's what makes the phone version possible.", "Trimming is nearly free, and it's the reason a handset build works at all."),
    (534.2, 535.6, "lapel", "reply", "Does that answer it?", "Is that clear enough?"),
    (544.6, 549.6, "floor", "speech", "It does. And is that ratio the same for all 3 benchmarks?", "Yes, thanks. Do all 3 test sets use that same ratio?"),
    (550.2, 552.2, "lapel", "reply", "Same ratio for all 3, yes.", "Yes, identical for all 3."),
    (553.0, 556.8, "lapel", "filler~", "Okay, thanks. So, where... where was I, the, um", "Right, thank you. Now, what... what was I, uh, um"),
    (566.1, 567.6, "lapel", "S4", "Benchmark 3: multilingual, the hardest.", "Set 3: many languages, toughest."),
    (568.4, 572.8, "lapel", "S4", "This is the hard case: 12 languages, lots of short queries.", "That's the tough one: 12 languages and many brief queries."),
    (573.6, 578.2, "lapel", "S4", "We still come out 4 points ahead of the sparse baseline,", "Even there we beat the sparse baseline by 4 points,"),
    (579.0, 583.4, "lapel", "S4", "though the gap to the dense model is bigger here.", "although dense retrieval pulls further ahead on this one."),
    (584.2, 588.2, "lapel", "S4", "Mostly because our tokenizer splits compound words badly.", "Largely since our word splitter mangles compound words."),
    (588.8, 593.6, "lapel", "S4", "And that's the end-to-end latency on the multilingual set: 40 milliseconds.", "And that's the end-to-end delay on the many-language set: 40 milliseconds."),
    (594.4, 598.6, "lapel", "S4.", "So: smaller, and at least as accurate on all 3.", "In short: more compact, and no less accurate on all 3."),
    (600.1, 601.6, "lapel", "S5", "Now: where does it break?", "So: when does it fail?"),
    (602.2, 606.8, "lapel", "S5", "Long queries, first: anything over about 12 words.", "First, lengthy queries: anything past roughly 12 words."),
    (607.6, 611.8, "lapel", "S5", "The learned weights just never saw queries like that in training.", "Our trained weights simply never met such queries during learning."),
    (612.8, 617.2, "lapel", "S5", "And second, rebuilding the index takes 20 minutes on the phone.", "Second, re-creating the index eats 20 minutes on the handset."),
]

# The interim hypothesis at t85 reads like an ending before it finalizes as a latency point.
A_REVISIONS = {
    588.8: (
        ((589.6, "and that's the end"), (590.6, "and that's the end to end latency"), (591.8, "and that's the end to end latency on the multilingual set forty")),
        ((589.6, "and that's the end"), (590.6, "and that's the end to end delay"), (591.8, "and that's the end to end delay on the many language set forty")),
    ),
}

# Lexical decoys: lapel lines reworded (same role and facts) toward wrong cue options ('captions', 'keyword',
# 'bridge', 'one-line', 'wrap up') or, in an aside and a reply, toward a wrong section (S1, S6). No line is added.
A_DECOYS = {
    386.8: "Even with live captions running, the lookup path takes under 4 milliseconds.",
    392.2: "Including the keyword tokenizer, which honestly was the slowest part.",
    413.2: "So the memory-mapped index never needs a bridge to a server for a query.",
    457.0: "First, news: 12% better recall than the best sparse, keyword-style baseline.",
    462.2: "Some cases do break it; I'll get to those in the next section.",
    471.2: "We match the dense retriever, no bridge needed, at a tenth of the memory.",
    480.4: "Quick confession: every search in these numbers ran on my own phone,",
    486.2: "which is also my alarm clock and captions app, so I nearly missed this session.",
    528.6: "So pruning costs almost nothing; it's why learned sparse fits on a phone at all.",
    568.4: "This is the hard case: 12 languages, lots of one-line queries.",
    607.6: "Queries that long read like captions; the learned weights never saw them in training.",
    612.8: "And second, an index rebuild takes 20 minutes to wrap up on the phone.",
}

# minimal_cf A1-A3 (start -> new role and text)
A_MINIMAL = {
    438.6: ("S3~", "And the whole index ends up at about, um"),
    553.0: ("filler", "Okay, thanks. So, back to the results."),
    600.1: ("aside", "Failure cases in a minute."),
    602.2: ("S4", "But first, one more number on the multilingual set."),
    607.6: ("S4", "Recall at 10 goes from 61 to 65%."),
    612.8: ("S4", "And that holds across all 12 languages."),
}
A_STRUCTURAL_ENDS = {"S4": "08:21", "S5": "09:00"}

A_CUES = {
    "canonical": {
        "plain": "Script view only, no overlay",
        "caption": "Live captions of the other speaker",
        "keyword": "Keyword hint for the part in progress",
        "bridge": "Bridge-back line into the section in progress",
        "next_opening": "Opening line of the next section",
        "wrap_section": "Wrap-up signal for the section in progress",
    },
    "paraphrase": {
        "plain": "Show the script alone, no card",
        "caption": "Running subtitles for whoever else is talking",
        "keyword": "Cue word for the passage under way",
        "bridge": "Return line leading back into the current part",
        "next_opening": "First sentence of the following part",
        "wrap_section": "Signal to finish the current part",
    },
}

A_TEXT = {
    "canonical": {
        "role": ("You run the auto-follow prompter for Priya Raman's research talk. The state is what the prompter receives "
                 "at `clock.now`: the prepared talk and script, the show clock, the slide log from the presentation software, "
                 "the audio mixer's channels, voice activity and mic log, streaming ASR (`segments`, `partials`) and the "
                 "playback server (`media`)."),
        "position_task": "Your answer is the script section the prompter highlights and scrolls to.",
        "cue_task": ("Your answer is the overlay card on the presenter's display. The display fills the card itself, from the "
                     "script (the current section's key points, a line back into it, the next section's opening, a wrap-up "
                     "signal) or with live captions."),
        "conventions": [
            "`segments` lists every finalized phrase from every channel that ended in the last 90 s (boundary included), oldest first by start. A phrase's `channel` is its source: lapel = the presenter, chair = the session chair's handheld, floor = the roaming audience mic, room = audience sound.",
            "A phrase appears in `segments` 0.3 s after it ends. `partials` show speech still in progress (from 0.2 s after it starts) and never count as said: what was said, and every duration, is read from `segments` times and `voice`.",
            "The room channel carries audience sound only (PA audio removed); its tags are [applause], [cheering] and [laughter].",
            "`voice` has one row per channel whose mic is live. A voice channel is 'speaking' (`since` = start of its current speech) or 'silent' (`since` = end of its last phrase, '-' if it has not spoken since its mic went live); silence is reported 0.3 s after speech stops. The room row shows the sound event now ('applause', 'cheering', 'laughter' or 'voices', `since` = its onset) or 'quiet' (`since` = end of the last event, '-' if none); the room detector reports each onset and end 0.5 s late. A muted or off mic has no `voice` row and produces no segments.",
            "`mic_log` lists every mic change in the last 90 s. `slides.shown` lists every slide ever displayed, however briefly; slides change only on the presenter's clicks.",
            "Every list (`script`, `channels`, `voice`, `mic_log`, `segments`, `partials`) is complete: what is not listed did not happen, and an empty list means none. Talk is not state: saying that something will happen ('I'll get to those in a minute') does not make it happen.",
            "`clock.now`, `planned_end` and `hard_out` use the same talk clock; `to_hard_out` goes negative once passed.",
            "The presenter's most recent phrase that delivers script content is always inside the `segments` window.",
            "Nothing in the state comes from this prompter (no overlay, highlight or scroll position): decide as if no card has been shown.",
            "'Or more' includes the threshold; 'under' excludes it.",
        ],
        "position_rules": [
            "1. Decide from finalized lapel phrases in `segments` only; partials, other channels and the slide number never decide.",
            "2. Answer the section of the presenter's most recent phrase that delivers script content: the section's opening, one of its points or an elaboration of one, or its closing, in any wording. A phrase that starts one of its points counts, even if it only names the point ('Third: pricing'). It may be earlier or later than the section you expect.",
            "3. Fillers, thanks, asides, jokes, mentions of a section ('I'll get to that', 'back to the method'), and everything said in reply to a question from the chair or the floor, until the presenter next delivers content, leave the answer unchanged.",
        ],
        "current_key": "current_section",
        "current": "The current section is the prompter position, decided by these rules:",
        "cue_rules": [
            "Apply the first rule that matches.",
            "1. Live captions of the other speaker: the chair or floor channel is speaking now, or the newest speech phrase in `segments` (latest start among lapel, chair and floor phrases) is theirs and the lapel has been silent since it ended.",
            "2. Keyword hint for the part in progress: the presenter's last finalized phrase breaks off mid-sentence and the lapel has been silent for 4 s or more.",
            "3. Bridge-back line into the section in progress: an off-script run of 30 s or more. The run starts at the start of the first lapel phrase after the presenter's most recent content phrase (every lapel phrase since then is a filler, aside, joke, mention or reply); its length is `clock.now` minus that start. Only a presenter content phrase ends the run; other people's speech and silences do not.",
            "4. Opening line of the next section: the presenter's last finalized phrase is the closing of the current section and the lapel has been silent for 3 s or more.",
            "5. Wrap-up signal for the section in progress: `clock.now` is 60 s or more past the current section's `planned_end`.",
            "6. Otherwise: script view only, no overlay.",
        ],
        "cues": A_CUES["canonical"],
    },
    "paraphrase": {
        "role": ("You operate the voice-following teleprompter during Meera Iyer's research presentation. The state is exactly "
                 "what the teleprompter has at `clock.now`: the planned talk and running order, the show timer, the deck "
                 "software's slide record, the sound desk's channels, voice detection and microphone record, live speech "
                 "recognition (`segments`, `partials`) and the video server (`media`)."),
        "position_task": "Your answer is the part of the script the teleprompter marks and scrolls to.",
        "cue_task": ("Your answer is the card laid over the speaker's screen. The screen builds the card by itself, either from "
                     "the script (key points of the current part, a sentence leading back into it, the first sentence of the "
                     "following part, a signal to finish) or as live subtitles."),
        "conventions": [
            "`segments` holds every finished phrase on any channel whose end falls within the past 90 s (the edge counts), earliest start first. A phrase's `channel` names where it came from: lapel is the speaker on stage, chair the moderator's handheld, floor the wireless mic for attendees, room the crowd noise.",
            "A phrase shows up in `segments` 0.3 s after its end. `partials` hold speech that is still going (from 0.2 s after it begins) and are never treated as spoken: read what was said, and every time span, from `segments` times and `voice`.",
            "The room channel picks up crowd noise only (the PA is filtered out) and tags it [applause], [cheering] or [laughter].",
            "`voice` carries a row for each channel whose microphone is live. A voice channel reads 'speaking' (`since` = when its current speech began) or 'silent' (`since` = when its latest phrase ended, '-' if nothing has been said since the mic went live); silence shows up 0.3 s after the speech stops. The room row gives the crowd sound at this moment ('clapping', 'cheers', 'laughs' or 'chatter', `since` = when it began) or 'calm' (`since` = when the latest sound stopped, '-' if there has been none); the crowd detector reports every start and stop 0.5 s late. A muted or switched-off mic has no `voice` row and yields no segments.",
            "`mic_log` records each microphone change of the past 90 s. `slides.shown` records every slide that has been on screen, even for a moment; only the speaker's clicker moves the slides.",
            "Each list (`script`, `channels`, `voice`, `mic_log`, `segments`, `partials`) is exhaustive: anything absent did not happen, and an empty list means there is none. Words are not events: announcing something ('I'll get to those in a minute') does not make it happen.",
            "`clock.now`, `planned_end` and `hard_out` share one talk timer; `to_hard_out` turns negative after the hard out.",
            "The speaker's latest phrase that carries script material never drops out of the `segments` window.",
            "The state holds nothing this teleprompter produced (no card, marking or scroll point); judge as though no card has appeared yet.",
            "'At least' counts the threshold itself; 'below' does not.",
        ],
        "position_rules": [
            "1. Judge only from the finished lapel phrases in `segments`; partials, the other channels and the slide number never settle it.",
            "2. Pick the part to which the speaker's latest material-carrying phrase belongs: its first sentence, one of its key points or something expanding on one, or its final sentence, however it is worded. A phrase that begins one of its key points counts even when it only names that point ('Third: pricing'). That part may come before or after the one you would expect.",
            "3. Hesitations, thanks, side remarks, jokes, references to a part ('I'll get to that', 'back to the method'), and anything said while answering a question from the moderator or the audience, up to the moment the speaker delivers material again, do not change the answer.",
        ],
        "current_key": "current_part",
        "current": "The current part is the teleprompter's marked part, chosen by these rules:",
        "cue_rules": [
            "Use the first rule that applies.",
            "1. Running subtitles for whoever else is talking: the chair or floor channel has voice at this moment, or the latest speech phrase in `segments` (latest start among lapel, chair and floor phrases) belongs to one of them and the lapel has had no voice since that phrase ended.",
            "2. Cue word for the passage under way: the speaker's latest finished phrase stops partway through a sentence and the lapel has had no voice for at least 4 s.",
            "3. Return line leading back into the current part: an unscripted stretch of at least 30 s. The stretch begins at the start of the first lapel phrase after the speaker's latest material-carrying phrase (every lapel phrase since then being a hesitation, side remark, joke, reference or answer); its length is `clock.now` minus that start. Only a speaker phrase with script material ends it; other people talking and pauses do not.",
            "4. First sentence of the following part: the speaker's latest finished phrase is the final sentence of the current part and the lapel has had no voice for at least 3 s.",
            "5. Signal to finish the current part: `clock.now` is at least 60 s beyond the current part's `planned_end`.",
            "6. In every other case: show the script alone, no card.",
        ],
        "cues": A_CUES["paraphrase"],
    },
}


class ResearchTalk(Presentation):
    scenario_id = "presentation_a"
    title = "Prompter and cue monitor: research talk through a mid-talk question"
    tier = "medium"
    difficulty_features = [
        "streaming ASR aligned to paraphrased script sections",
        "floor handoff read from separate mic channels",
        "near-threshold silence, off-script run and overrun arithmetic",
        "per-section timer while the talk as a whole runs late",
        "slides and replies that point at another section",
        "three priority conflicts",
    ]
    decision_structures = ["maintain", "advance", "recover", "handoff", "terminate", "resolve-conflict"]
    tick_seconds = 2
    window_start = "07:00.0"
    UNIT = "section"
    TEXT = A_TEXT

    TAGS = {
        "arithmetic": [(0, 12), (17, 23), (57, 62), (66, 70), (74, 84)],
        "hold_under_activity": [(0, 10), (30, 36), (46, 58), (78, 89)],
        "distractor": [(11, 12), (14, 15), (17, 23), (24, 25), (33, 37), (39, 44), (46, 50), (57, 59), (60, 62), (69, 70), (74, 76), (85, 85), (90, 90)],
        "minimal_change": [(13, 13), (60, 60), (77, 77)],
        "priority_conflict": [(13, 15), (63, 65), (71, 73)],
        "recovery": [(16, 16), (45, 45), (66, 66), (74, 74)],
        "boundary": [(16, 16), (38, 38), (91, 91)],
        "implicit": [(71, 73)],
    }
    CF_TAGS = {
        "minimal_cf": {(13, 15): ["minimal_change", "priority_conflict", "implicit"], (71, 73): ["minimal_change", "arithmetic"], (91, 99): ["distractor", "arithmetic"]},
        "structural_cf": {(74, 76): ["priority_conflict", "arithmetic"], (77, 77): ["arithmetic"], (91, 99): ["boundary", "arithmetic"]},
    }
    NOTES = [
        (0, 12, "S3 runs 68-92 s past its 05:52 planned end; its closing is said 07:18.6-07:21.6, then a pause"),
        (13, 15, "The pause after S3's closing passes 3 s; slide clicked to 11 at 07:27.4 with nothing said"),
        (16, 37, "S4 opens with 'Does it work?'; a promise to cover failures later, an alarm-clock aside, laughter"),
        (38, 44, "The chair cuts in (unmuted 08:15.2); a clarification question on the floor mic"),
        (45, 59, "Reply to the question on the S3 pruning slide; the off-script run grows to 29.4 s"),
        (60, 62, "The run passes 30 s while the presenter waits after 'Does that answer it?'"),
        (63, 65, "A follow-up question on the floor mic outranks the bridge"),
        (66, 70, "A one-line reply, then a broken-off 'where was I'; run 43-51 s"),
        (71, 73, "Silent 5.2-9.2 s after the broken-off phrase"),
        (74, 76, "'Benchmark 3: multilingual, the hardest.' starts S4's third point and ends the run; S4 overrun 55-59 s"),
        (77, 90, "S4 60 s or more past 08:33; its closing is said 09:54.4-09:58.6"),
        (91, 99, "S5 opens with 'Now: where does it break?'"),
    ]
    CF_NOTES = {
        "minimal_cf": [
            (0, 12, "S3 runs 68-92 s past 05:52; its last phrase breaks off at 07:21.6"),
            (13, 15, "A1: S3's last phrase broke off ('about, um'); silent 4.4-8.4 s"),
            (66, 70, "A one-line reply, then a complete 'So, back to the results.'; run 43-51 s"),
            (71, 73, "A2: the 09:13.0 phrase is complete ('back to the results'); the run goes on"),
            (91, 99, "A3: S5 is only mentioned; S4 content continues past its planned end"),
        ],
        "structural_cf": [
            (74, 76, "S4 re-timed to end 08:21: 67-71 s over"),
            (77, 90, "S4 re-timed to end 08:21: 73-99 s over; its closing is said 09:54.4-09:58.6"),
            (91, 99, "S5 re-timed to end 09:00: 62-78 s over"),
        ],
    }

    def build_show(self, variant: str) -> Show:
        register = "paraphrase" if variant == "paraphrase" else "canonical"
        para = register == "paraphrase"
        script = []
        for uid, slides, end, canon, alt in A_SCRIPT:
            title, opening, points, closing = alt if para else canon
            if variant == "structural_cf":
                end = A_STRUCTURAL_ENDS.get(uid, end)
            script.append({"id": uid, "title": title, "slides": slides, "planned_end": end, "must_say": False,
                           "opening": opening, "points": list(points), "closing": closing})
        talk = copy.deepcopy(A_TALK[register])
        if variant == "structural_cf":
            talk["notes"] += " Sections S4 and S5 were re-timed after the dress rehearsal."
        who = {
            "canonical": ["presenter (Priya Raman)", "session chair (Tomás Ortega)", "roaming audience mic", "ambient room mics (audience sound, PA removed)"],
            "paraphrase": ["speaker on stage (Meera Iyer)", "moderator (Jonas Weber)", "wireless mic for attendees", "hall microphones (crowd noise only, PA filtered out)"],
        }[register]
        return Show(
            register=register,
            talk=talk,
            script=script,
            utterances=_lines(A_ROWS, variant, A_REVISIONS, A_DECOYS, A_MINIMAL),
            channels=list(zip(("lapel", "chair", "floor", "room"), who)),
            mics={"lapel": "live", "chair": "muted", "floor": "off", "room": "live"},
            mic_events=[(495.2, "chair", "unmuted"), (499.6, "floor", "on"), (500.2, "chair", "muted"), (552.4, "floor", "off")],
            slide0=6,
            slide_changes=[(232.4, 7), (300.0, 8), (371.0, 9), (397.4, 10), (447.4, 11), (466.8, 12), (510.2, 9), (566.8, 13), (579.0, 14), (599.4, 15)],
            hard_out=720.0,
        )

    def facts(self, v: View) -> dict[str, Any]:
        lapel = [r for r in v.rows if r.ch == "lapel"]
        content = [r for r in lapel if r.info["kind"] == "content"]
        newest_content, last = content[-1], lapel[-1]
        after = [r for r in lapel if r.start > newest_content.start]
        state, since = v.voice["lapel"]
        speech = [r for r in v.rows if r.ch in ("lapel", "chair", "floor")]
        newest = speech[-1]
        floor = any(v.voice[ch][0] == "speaking" for ch in ("chair", "floor")) or (
            newest.ch != "lapel" and state == "silent" and since <= newest.end + EPS
        )
        unit = newest_content.info["unit"]
        return {
            "section": {"id": unit, "overrun": _r(v.now - v.units[unit][0])},
            "floor": floor,
            "lapel": {
                "silence": 0.0 if state == "speaking" else _r(v.now - since),
                "broke_off": last.info["broke"],
                "after_closing": last is newest_content and last.info["closing"],
                "run": _r(v.now - after[0].start) if after else 0.0,
            },
        }

    def policy(self, z: dict[str, Any]) -> dict[str, Any]:
        lapel = z["lapel"]
        if z["floor"]:
            cue = "caption"
        elif lapel["broke_off"] and lapel["silence"] >= 4:
            cue = "keyword"
        elif lapel["run"] >= 30:
            cue = "bridge"
        elif lapel["after_closing"] and lapel["silence"] >= 3:
            cue = "next_opening"
        elif z["section"]["overrun"] >= 60:
            cue = "wrap_section"
        else:
            cue = "plain"
        return {"position": z["section"]["id"], "cue": cue}

    def quantities(self, z: dict[str, Any]) -> list[tuple[str, float, tuple[float, ...]]]:
        return [("silence", z["lapel"]["silence"], (3, 4)), ("run", z["lapel"]["run"], (30,)), ("overrun", z["section"]["overrun"], (60,))]

    def construction(self, variant: str) -> dict[str, Any]:
        return {
            "canonical": {"summary": "Research talk 07:00-10:18: S3 overrun and closing pause, S4 results, a chair-led clarification question with a follow-up, a lost thread, S4 overrun, S5 start."},
            "paraphrase": {"summary": "Every free-text value reworded (talk, script, speech, names, channel labels, the room detector's labels, instructions, options); keys, times, numbers and IDs kept; each reworded phrase keeps its start, end and role."},
            "lexical_decoy": {"summary": f"{len(A_DECOYS)} lapel phrases reworded, same role and facts, toward wrong cue options or (an aside and a reply) toward S1 and S6: "
                              + " | ".join(A_DECOYS.values()) + " No chair or floor phrase, no applause, no lapel phrase added."},
            "minimal_cf": {"summary": "A1: S3's closing phrase breaks off ('about, um'), t13-15 next_opening -> keyword. A2: the 09:13.0 phrase is complete ('So, back to the results.'), t71-73 keyword -> bridge. A3: S5's opening becomes a mention ('Failure cases in a minute.') and S4 content continues, t91-99 S5/plain -> S4/wrap_section."},
            "structural_cf": {"summary": "Plan re-timed: S4 ends 08:21 and S5 09:00, so t74-76 and t91-99 become wrap_section."},
        }[variant]


# ===========================================================================
# presentation_b: keynote prompter with a skipped must-say paragraph, a hard out and a frozen film
# ===========================================================================

B_TALK = {
    "canonical": {
        "title": "Halvard H4 launch keynote, segment 3: Range",
        "presenter": "Ines Duarte",
        "format": "Scripted keynote segment read from an auto-follow prompter",
        "hard_out": {"at": "02:40", "what": "test-drive film must be rolling (live-stream break)"},
        "people": ["Show host (handheld mic)", "Show caller (fires the film from the control room)"],
        "notes": "Paragraphs marked must_say are legal or commercial lines that have to be spoken on stage.",
    },
    "paraphrase": {
        "title": "Nordvik H4 launch event, part 3: Range",
        "presenter": "Clara Moreau",
        "format": "Fully scripted keynote section delivered from a voice-following teleprompter",
        "hard_out": {"at": "02:40", "what": "the test-drive video must be playing (stream cuts away)"},
        "people": ["Evening's emcee (handheld microphone)", "Show director (starts the video from the gallery)"],
        "notes": "A must_say paragraph holds legal or sales wording that must be read aloud on stage.",
    },
}

B_SCRIPT = [
    ("P1", "12", "00:30", False,
     ("The question", "Last year we asked thousands of you one question:", ["why haven't you gone electric yet?"], "And the answer, over and over, was range."),
     ("What we asked", "A year ago we surveyed thousands of you on one thing:", ["what's stopping you from switching to electric?"], "Again and again, you told us: it's range.")),
    ("P2", "13", "00:55", False,
     ("The number", "So we went back to the battery.", ["H4 goes 610 km on a single charge."], "Six hundred and ten. [hold for applause]"),
     ("The headline figure", "So we started over with the cells.", ["H4 drives 610 km on one full battery."], "That's 610. [pause for applause]")),
    ("P3", "13", "01:15", False,
     ("Charging", "And when you do stop:", ["ten minutes on a fast charger"], "adds 300 km."),
     ("Fast charging", "And whenever you need to pause:", ["a 10-minute fast-charge stop"], "gains 300 km.")),
    ("P4", "14", "01:25", True,
     ("Range note", "A quick note on those numbers:", ["all range and charging figures are WLTP estimates;"], "real-world range depends on speed, temperature and load."),
     ("Fine print on range", "A brief word about those figures:", ["every range or charging value is a WLTP estimate;"], "actual range varies with speed, weather and cargo.")),
    ("P5", "15", "01:40", True,
     ("Price", "So what does it cost?", ["H4 Long Range starts at 41,900 euros,"], "home charger included."),
     ("Cost", "So what's the price?", ["H4 Long Range begins at 41,900 euros,"], "wallbox thrown in.")),
    ("P6", "16", "01:55", False,
     ("Availability", "Orders open tonight at eight.", ["First deliveries in March,"], "in twelve countries."),
     ("When and where", "You can order from eight tonight.", ["Deliveries begin in March,"], "across twelve markets.")),
    ("P7", "17", "02:05", False,
     ("Hand to film", "But don't take my word for it.", [], "Here's what our test drivers said. [roll film]"),
     ("Over to the video", "But you needn't just believe me.", [], "Listen to the people who drove it. [start film]")),
]

B_ROWS: list[Row5] = [
    (5.0, 6.8, "host", "speech", "Please welcome back Ines Duarte!", "Once more, here's Clara Moreau!"),
    (32.0, 34.0, "lapel", "P1", "Last year we asked thousands of you", "We surveyed thousands of you last year"),
    (34.4, 35.6, "lapel", "P1", "one question:", "one thing:"),
    (36.2, 38.2, "lapel", "P1", "why haven't you gone electric yet?", "what's stopping you from switching to electric?"),
    (38.6, 40.4, "lapel", "P1", "And the answer, over and over,", "And time after time, you said"),
    (40.8, 42.0, "lapel", "P1.", "was range.", "It's range."),
    (43.0, 45.0, "lapel", "P2", "So we went back to the battery.", "So we started over with the cells."),
    (46.0, 48.0, "lapel", "P2", "H4 goes 610 kilometres", "H4 drives 610 kilometres"),
    (48.4, 50.0, "lapel", "P2", "on a single charge.", "on one full battery."),
    (51.2, 52.8, "lapel", "P2.", "610.", "610."),
    (53.4, 63.0, "room", "applause", "[applause] [cheering]", "[applause] [cheering]"),
    (63.6, 64.4, "lapel", "filler", "Thank you.", "Thank you."),
    (66.4, 68.2, "lapel", "P3", "And when you do stop:", "And whenever you need to pause:"),
    (68.6, 70.4, "lapel", "aside", "hands up if you've ever waited", "who here has ever sat"),
    (70.8, 72.2, "lapel", "aside", "40 minutes at a charger?", "40 minutes by a plug?"),
    (72.4, 74.0, "room", "laughter", "[laughter]", "[laughter]"),
    (74.4, 75.4, "lapel", "aside", "Yeah. Me too.", "Yes. Same here."),
    (76.0, 78.0, "lapel", "P3", "With H4, 10 minutes fast-charging", "H4: 10 minutes of rapid charging"),
    (78.8, 80.0, "lapel", "P3.", "adds 300 kilometres.", "gains 300 kilometres."),
    (81.0, 82.6, "lapel", "P3", "300. In 10 minutes.", "300. Within 10 minutes."),
    (83.9, 91.9, "room", "applause", "[applause]", "[applause]"),
    (89.6, 90.3, "lapel", "filler", "Thank you.", "Thank you."),
    (90.6, 92.1, "lapel", "P5", "So what does it cost?", "So what's the price?"),
    (92.6, 94.4, "lapel", "P5", "H4 Long Range starts at", "H4 Long Range begins at"),
    (94.8, 96.8, "lapel", "P5", "41,900 euros,", "41,900 euros,"),
    (97.4, 98.8, "lapel", "P5.", "home charger included.", "wallbox thrown in."),
    (98.9, 105.6, "room", "cheering", "[cheering]", "[cheering]"),
    (106.0, 106.8, "lapel", "filler", "Thank you.", "Thank you."),
    (107.2, 108.6, "lapel", "aside", "Oh, before I forget.", "Oh, one more thing."),
    (110.2, 111.8, "lapel", "P4", "The small print on those:", "One footnote on those:"),
    (112.4, 114.1, "lapel", "P4", "they're all WLTP lab results;", "each comes from WLTP testing;"),
    (114.4, 116.1, "lapel", "P4", "real-world range depends on speed,", "actual range varies with speed,"),
    (116.4, 117.4, "lapel", "P4.", "temperature and load.", "weather and cargo."),
    (119.2, 119.6, "lapel", "filler", "So...", "Um..."),
    (121.0, 121.4, "lapel", "filler", "okay.", "right."),
    (123.2, 125.0, "lapel", "P6", "Order yours from 8 tonight.", "Ordering opens at 8 tonight."),
    (125.6, 127.4, "lapel", "P6", "First deliveries in March,", "Deliveries begin in March,"),
    (127.8, 128.8, "lapel", "P6~", "in, um...", "across, uh..."),
    (127.9, 129.1, "room", "voices", "What about the UK?", "How about the UK?"),
    (129.2, 130.1, "lapel", "aside", "UK's coming too!", "UK as well!"),
    (130.4, 131.8, "room", "laughter", "[laughter]", "[laughter]"),
    (132.4, 133.9, "lapel", "filler", "So, um...", "Um, so..."),
    (134.2, 135.9, "lapel", "filler", "where was I, uh...", "uh, where was I..."),
    (136.2, 137.9, "lapel", "filler", "okay, the... the...", "the... okay, the..."),
    (138.2, 140.1, "lapel", "filler", "um, so, right, er...", "er, right, so, um..."),
    (142.4, 144.4, "lapel", "P7", "But don't take my word for it.", "But you needn't just believe me."),
    (144.8, 146.8, "lapel", "P7.", "Here's what our test drivers said.", "Listen to the people who drove it."),
    (154.6, 155.3, "lapel", "filler", "Well.", "Well."),
    (155.6, 157.1, "lapel", "aside", "That's live events for you.", "Gotta love live shows."),
    (157.4, 159.4, "lapel", "aside", "Glad it didn't freeze on the price.", "Lucky it didn't stop on the price."),
    (159.7, 161.7, "lapel", "aside", "The crew's on it, one second.", "Our team is fixing it, one moment."),
]

# The film soundtrack on the program channel, in seconds from the top of the film.
B_FILM = [
    (0.8, 2.4, "Day one. Lisbon. Battery full.", "First day. Lisbon. Fully charged."),
    (3.8, 5.8, "I kept waiting for the range warning.", "I was expecting the low-range alert."),
    (6.4, 7.4, "It never came.", "It never showed."),
    (8.4, 10.4, "Honestly, I forgot where I was going,", "Truly, I lost track of my destination,"),
    (10.8, 12.6, "and never thought of the cost.", "and never minded the price."),
    (13.4, 15.2, "Madrid. Still 40% left.", "Madrid, with 40% remaining."),
    (16.0, 17.8, "I'd drive it again tomorrow.", "I'd happily do it again."),
    (18.4, 20.2, "Porto to Seville, one stop.", "Porto, then Seville, one pause."),
    (21.0, 22.8, "The kids slept the whole way.", "The children dozed all the way."),
    (23.4, 25.2, "Quiet, comfortable, easy.", "Calm, comfy, effortless."),
    (26.0, 27.8, "No planning around chargers.", "No route planning needed."),
    (28.4, 30.2, "That's the range we wanted.", "Exactly the range we hoped for."),
]
B_FILM_DECOYS = {
    3.8: "I kept waiting for a warning flag.",
    10.8: "and the home charger was included.",
    13.4: "Madrid: skipped charging, 40% left.",
    16.0: "Real-world range, even fully loaded.",
}
B_MEDIA = [(148.2, 0.0, True), (150.8, 2.6, False), (161.2, 0.0, True)]  # rolls, freezes at 00:02.6, restarted

# Lexical decoys: lapel asides reworded toward wrong cue options or the price paragraph (same role and facts),
# room voices and film lines borrowing option and paragraph vocabulary. No lapel or host line is added.
B_DECOYS = {107.2: "Before I jump ahead.", 155.6: "Live events: that's the keyword.", 157.4: "Could've frozen on 'Long Range starts at'."}
B_DECOY_ROWS: list[Row5] = [
    (20.0, 21.4, "room", "voices", "Stream's stalled again.", "Stream's stalled again."),
    (95.7, 96.6, "room", "voices", "Hold my coffee.", "Hold my coffee."),
    (117.6, 118.9, "room", "voices", "Talking points so far.", "Talking points so far."),
    (146.8, 147.7, "room", "voices", "Winter range, though?", "Winter range, though?"),
]

# minimal_cf B1-B3: the price draws laughter; P6's closing is said; the film never freezes (no ad-libs, no restart).
B_MINIMAL: dict[float, tuple[str, str] | None] = {
    98.9: ("laughter", "[laughter]"),
    127.8: ("P6.", "in 12 countries."),
    154.6: None, 155.6: None, 157.4: None, 159.7: None,
}

B_CUES = {
    "canonical": {
        "plain": "Plain prompter text, no overlay",
        "hold": "Hold card: wait before speaking",
        "flag_skipped": "Flag for the skipped must-say paragraph",
        "cut_to_close": "Jump marker to the closing paragraph",
        "keyword": "Keyword hint for the part in progress",
        "next_opening": "Opening line of the next paragraph",
        "ad_lib": "Ad-lib talking points while the film is stalled",
    },
    "paraphrase": {
        "plain": "Bare script, no card on top",
        "hold": "Wait card: do not start talking",
        "flag_skipped": "Marker for the obligatory paragraph that was passed over",
        "cut_to_close": "Skip-ahead pointer to the final paragraph",
        "keyword": "Cue word for the passage under way",
        "next_opening": "First sentence of the following paragraph",
        "ad_lib": "Filler talking points while the video is frozen",
    },
}

B_TEXT = {
    "canonical": {
        "role": ("You run the auto-follow prompter that Ines Duarte reads from during a live keynote segment. The state is what "
                 "the prompter receives at `clock.now`: the prepared talk and script, the show clock, the slide log, the audio "
                 "mixer's channels, voice activity and mic log, streaming ASR (`segments`, `partials`) and the playback server "
                 "(`media`)."),
        "position_task": "Your answer is the script paragraph the prompter highlights and scrolls to.",
        "cue_task": ("Your answer is the overlay card on the prompter screen. The screen fills the card itself from the script "
                     "(a keyword of the current paragraph, the next paragraph's opening, the skipped must-say paragraph, the "
                     "closing paragraph, ad-lib points) or shows a hold card."),
        "conventions": [
            "`segments` lists every finalized phrase from every channel that ended in the last 90 s (boundary included), oldest first by start. A phrase's `channel` is its source: lapel = the presenter, host = the show host's handheld, room = audience sound, program = the film soundtrack (never the presenter).",
            "A phrase appears in `segments` 0.3 s after it ends, and the ASR cuts continuous speech into phrases of at most 2 s. `partials` show speech still in progress (from 0.2 s after it starts) and never count as said: what was said, and every duration, is read from `segments` times and `voice`.",
            "The room channel carries audience sound only (PA audio removed): the tags [applause], [cheering] and [laughter], and words called out from the audience.",
            "`voice` has one row per channel whose mic is live. A voice channel is 'speaking' (`since` = start of its current speech) or 'silent' (`since` = end of its last phrase, '-' if it has not spoken since its mic went live); silence is reported 0.3 s after speech stops. The room row shows the sound event now ('applause', 'cheering', 'laughter' or 'voices', `since` = its onset) or 'quiet' (`since` = end of the last event, '-' if none); the room detector reports each onset and end 0.5 s late. A muted or off mic has no `voice` row and produces no segments.",
            "`mic_log` lists every mic change in the last 90 s. `slides.shown` lists every slide ever displayed, however briefly; slides change only on the presenter's clicks.",
            "`media` is the playback server for the segment's film: during normal playback `position` and `position_changed_at` change every 0.5 s.",
            "Every list (`script`, `channels`, `voice`, `mic_log`, `segments`, `partials`) is complete: what is not listed did not happen, and an empty list means none. Talk is not state: saying that something will happen ('The crew's on it, one second') does not make it happen.",
            "`clock.now`, `planned_end` and `hard_out` use the same segment clock; `to_hard_out` goes negative once passed.",
            "Guarantees: the presenter's most recent phrase that delivers script content is always inside the `segments` window, and so is every phrase of a must-say paragraph said in this segment. A must-say paragraph with no phrase in `segments` has not been said.",
            "Nothing in the state comes from this prompter (no overlay, highlight or scroll position): decide as if no card has been shown.",
            "'Or more' includes the threshold; 'under' excludes it. 'In the last 3 s' means less than 3 s before `clock.now`.",
        ],
        "position_rules": [
            "1. Decide from finalized lapel phrases in `segments` only; partials, other channels (host, room, program) and the slide number never decide.",
            "2. Answer the paragraph of the presenter's most recent phrase that delivers script content: the paragraph's opening, its point or its closing, in any wording. It may be earlier or later than the paragraph you expect.",
            "3. Fillers, thanks, asides, jokes, ad-libs, mentions of a paragraph and replies to the audience leave the answer unchanged.",
        ],
        "current_key": "current_paragraph",
        "current": "The current paragraph is the prompter position, decided by these rules:",
        "cue_rules": [
            "Fillers are um, uh, er, so, okay, right, well, 'the...', 'where was I' and 'thank you'; a filler phrase contains nothing else. A paragraph's first phrase is its earliest phrase in `segments`; its closing is said once the phrase that finishes it is in `segments` (a closing split over several phrases counts from its last one; a phrase that breaks off partway through the closing does not finish it). Apply the first rule that matches.",
            "1. Ad-lib talking points while the film is stalled: `media.state` is 'playing' but `media.position_changed_at` is 3 s or more before `clock.now`.",
            "2. Hold card: the room's `voice` row shows applause or cheering, or `media.state` is 'playing'.",
            "3. Flag for the skipped must-say paragraph: a must-say paragraph earlier in the script than the current one has no phrase in `segments`, and the current paragraph's first phrase started 5 s or more before `clock.now`.",
            "4. Jump marker to the closing paragraph: `clock.to_hard_out` is under 20 s and no P7 phrase is in `segments`.",
            "5. Keyword hint for the part in progress: the current paragraph's closing is unsaid, no non-filler lapel phrase ended in the last 3 s, and no applause or cheering ended in the last 3 s.",
            "6. Opening line of the next paragraph: the current paragraph's closing is said, a paragraph later in the script has no phrase in `segments`, no non-filler lapel phrase ended in the last 3 s, and no applause or cheering ended in the last 3 s.",
            "7. Otherwise: plain prompter text, no overlay.",
        ],
        "cues": B_CUES["canonical"],
    },
    "paraphrase": {
        "role": ("You operate the voice-following teleprompter Clara Moreau reads from during a live keynote section. The state "
                 "is exactly what the teleprompter has at `clock.now`: the planned talk and running order, the show timer, the "
                 "slide record, the sound desk's channels, voice detection and microphone record, live speech recognition "
                 "(`segments`, `partials`) and the video server (`media`)."),
        "position_task": "Your answer is the script paragraph the teleprompter marks and scrolls to.",
        "cue_task": ("Your answer is the card laid over the teleprompter text. The screen builds it by itself from the script (a "
                     "cue word for the current paragraph, the following paragraph's first sentence, the obligatory paragraph "
                     "that was passed over, the final paragraph, filler talking points) or shows a wait card."),
        "conventions": [
            "`segments` holds every finished phrase on any channel whose end falls within the past 90 s (the edge counts), earliest start first. A phrase's `channel` names where it came from: lapel is the speaker on stage, host the emcee's handheld, room the crowd noise, program the video soundtrack (never the speaker).",
            "A phrase shows up in `segments` 0.3 s after its end, and speech recognition splits unbroken speech into phrases no longer than 2 s. `partials` hold speech that is still going (from 0.2 s after it begins) and are never treated as spoken: read what was said, and every time span, from `segments` times and `voice`.",
            "The room channel picks up crowd noise only (the PA is filtered out): the tags [applause], [cheering] and [laughter], plus words shouted from the seats.",
            "`voice` carries a row for each channel whose microphone is live. A voice channel reads 'speaking' (`since` = when its current speech began) or 'silent' (`since` = when its latest phrase ended, '-' if nothing has been said since the mic went live); silence shows up 0.3 s after the speech stops. The room row gives the crowd sound at this moment ('clapping', 'cheers', 'laughs' or 'chatter', `since` = when it began) or 'calm' (`since` = when the latest sound stopped, '-' if there has been none); the crowd detector reports every start and stop 0.5 s late. A muted or switched-off mic has no `voice` row and yields no segments.",
            "`mic_log` records each microphone change of the past 90 s. `slides.shown` records every slide that has been on screen, even for a moment; only the speaker's clicker moves the slides.",
            "`media` is the video server for this section's clip: while it plays normally, `position` and `position_changed_at` move on every 0.5 s.",
            "Each list (`script`, `channels`, `voice`, `mic_log`, `segments`, `partials`) is exhaustive: anything absent did not happen, and an empty list means there is none. Words are not events: announcing something ('Our team is fixing it, one moment') does not make it happen.",
            "`clock.now`, `planned_end` and `hard_out` share one section timer; `to_hard_out` turns negative after the hard out.",
            "Guarantees: the speaker's latest phrase that carries script material never drops out of the `segments` window, and neither does any phrase of a must_say paragraph spoken in this section. A must_say paragraph without a phrase in `segments` has not been spoken.",
            "The state holds nothing this teleprompter produced (no card, marking or scroll point); judge as though no card has appeared yet.",
            "'At least' counts the threshold itself; 'below' does not. 'Within the past 3 s' means less than 3 s before `clock.now`.",
        ],
        "position_rules": [
            "1. Judge only from the finished lapel phrases in `segments`; partials, the other channels (host, room, program) and the slide number never settle it.",
            "2. Pick the paragraph to which the speaker's latest material-carrying phrase belongs: its first sentence, its point or its final sentence, however it is worded. That paragraph may come before or after the one you would expect.",
            "3. Hesitations, thanks, side remarks, jokes, improvised lines, references to a paragraph and answers to the audience do not change the answer.",
        ],
        "current_key": "current_paragraph",
        "current": "The current paragraph is the teleprompter's marked paragraph, chosen by these rules:",
        "cue_rules": [
            "Hesitation words are um, uh, er, so, okay, right, well, 'the...', 'where was I' and 'thank you'; a hesitation phrase has nothing else in it. A paragraph's first phrase is its earliest phrase in `segments`; its final sentence counts as spoken once the phrase that completes it is in `segments` (a final sentence spread over several phrases counts from the last of them; a phrase that stops partway through it does not complete it). Use the first rule that applies.",
            "1. Filler talking points while the video is frozen: `media.state` reads 'playing' yet `media.position_changed_at` lies at least 3 s before `clock.now`.",
            "2. Wait card: the room's `voice` row shows clapping or cheers, or `media.state` reads 'playing'.",
            "3. Marker for the obligatory paragraph that was passed over: a must_say paragraph placed before the current one in the script has no phrase in `segments`, and the current paragraph's first phrase began at least 5 s before `clock.now`.",
            "4. Skip-ahead pointer to the final paragraph: `clock.to_hard_out` is below 20 s and `segments` holds no P7 phrase.",
            "5. Cue word for the passage under way: the current paragraph's final sentence has not been spoken, no lapel phrase other than a hesitation phrase ended within the past 3 s, and no clapping or cheers ended within the past 3 s.",
            "6. First sentence of the following paragraph: the current paragraph's final sentence has been spoken, some paragraph later in the script has no phrase in `segments`, no lapel phrase other than a hesitation phrase ended within the past 3 s, and no clapping or cheers ended within the past 3 s.",
            "7. In every other case: bare script, no card on top.",
        ],
        "cues": B_CUES["paraphrase"],
    },
}


def _film(events: list[tuple[float, float, bool]], variant: str) -> list[Utterance]:
    """Program-channel lines as the film plays: each advancing run plays the soundtrack from its position."""
    out = []
    stops = [e[0] for e in events[1:]] + [math.inf]
    for (at, position, advancing), stop in zip(events, stops):
        if not advancing:
            continue
        for start, end, text, alt in B_FILM:
            if start >= position - EPS and at + end - position <= stop + EPS:
                if variant == "paraphrase":
                    text = alt
                elif variant == "lexical_decoy":
                    text = B_FILM_DECOYS.get(start, text)
                out.append(Utterance(round(at + start - position, 1), round(at + end - position, 1), "program", text, info=_info("program")))
    return out


class KeynotePrompter(Presentation):
    scenario_id = "presentation_b"
    title = "Prompter and cue monitor: keynote with a skipped must-say line, a hard out and a frozen film"
    tier = "hard"
    difficulty_features = [
        "one-second budget with states that differ by one phrase",
        "closed-world must-say check against a 90-s window",
        "fillers versus content while the VAD reads speaking",
        "applause versus laughter and audience voices",
        "a stall visible only as a stale playback timestamp",
        "four near-threshold quantities",
        "three priority conflicts",
    ]
    decision_structures = ["maintain", "advance", "wait", "recover", "rollback", "handoff", "terminate", "resolve-conflict"]
    tick_seconds = 1
    window_start = "01:20.5"
    UNIT = "paragraph"
    TEXT = B_TEXT
    DECOY_CARRIERS = frozenset({"room", "program"})
    MAX_PHRASE = 2.0

    TAGS = {
        "hold_under_activity": [(4, 11), (48, 52), (74, 80), (82, 99)],
        "distractor": [(10, 11), (30, 31), (42, 44), (48, 52), (63, 64), (71, 73), (77, 80), (84, 99)],
        "arithmetic": [(12, 18), (36, 40), (53, 64), (71, 74)],
        "minimal_change": [(16, 16), (60, 60), (74, 74)],
        "priority_conflict": [(19, 25), (60, 64), (74, 80)],
        "recovery": [(26, 26), (32, 32), (81, 81)],
        "boundary": [(65, 65), (68, 68)],
        "implicit": [(53, 59), (74, 80)],
    }
    CF_TAGS = {
        "minimal_cf": {
            (19, 25): ["minimal_change", "distractor"], (53, 59): ["minimal_change", "arithmetic"], (71, 73): ["hold_under_activity"],
            (74, 80): ["minimal_change", "hold_under_activity"], (81, 81): ["hold_under_activity"],
        },
        "structural_cf": {(16, 18): ["distractor"], (19, 25): ["hold_under_activity"], (26, 31): ["distractor"]},
    }
    NOTES = [
        (0, 3, "P3's closing, then '300. In 10 minutes.'"),
        (4, 11, "Applause from 01:23.9 (reported 0.5 s later); double-click 13->14->15; 'So what does it cost?' spoken into the applause"),
        (12, 15, "P5 under way with must-say P4 skipped; P5 began 1.9-4.9 s ago"),
        (16, 18, "5.9-7.9 s into P5 with P4 unsaid"),
        (19, 25, "Cheering for the price outranks the flag"),
        (26, 31, "The flag returns; 'Oh, before I forget.'; slide back to 14"),
        (32, 39, "The range note, out of order, its opening and point in her own words; then fillers"),
        (40, 44, "Only fillers for 3.1-7.1 s after P4's closing; P6 is next because P5 was said"),
        (45, 52, "Availability; an audience voice asks about the UK, an ad-lib, laughter"),
        (53, 59, "Continuous fillers keep the VAD at speaking; no non-filler phrase for 3.4-9.4 s"),
        (60, 64, "Under 20 s to the hard out with no P7 phrase"),
        (65, 67, "P7's opening and closing"),
        (68, 73, "The film rolls from 02:28.2; its position is stuck at 00:02.6 from 02:30.8"),
        (74, 80, "Film stalled 3.7-9.7 s while playback says playing; ad-libs"),
        (81, 99, "Film restarted at 02:41.2 and playing"),
    ]
    CF_NOTES = {
        "minimal_cf": [
            (19, 25, "B1: the price draws laughter, not cheering"), (53, 59, "B2: P6's closing 'in 12 countries.' is said"),
            (68, 73, "The film rolls from 02:28.2 and keeps advancing"), (74, 80, "B3: the film never freezes"), (81, 99, "Film still playing normally"),
        ],
        "structural_cf": [
            (12, 15, "P5 under way; P4 is not must-say"), (16, 18, "P4 is not must-say: nothing is skipped"),
            (19, 25, "Cheering for the price: hold"), (26, 31, "P4 is not must-say: no flag"),
        ],
    }

    def build_show(self, variant: str) -> Show:
        register = "paraphrase" if variant == "paraphrase" else "canonical"
        para = register == "paraphrase"
        script = []
        for uid, slides, end, must, canon, alt in B_SCRIPT:
            title, opening, points, closing = alt if para else canon
            if variant == "structural_cf" and uid == "P4":
                must = False
            script.append({"id": uid, "title": title, "slides": slides, "planned_end": end, "must_say": must,
                           "opening": opening, "points": list(points), "closing": closing})
        talk = copy.deepcopy(B_TALK[register])
        if variant == "structural_cf":
            talk["notes"] += " The WLTP note (P4) now runs as on-screen text, so it is no longer must-say."
        media = B_MEDIA if variant != "minimal_cf" else B_MEDIA[:1]
        rows = B_ROWS + (B_DECOY_ROWS if variant == "lexical_decoy" else [])
        who = {
            "canonical": ["presenter (Ines Duarte)", "host handheld", "audience mics (PA removed)", "film playback audio"],
            "paraphrase": ["on-stage speaker (Clara Moreau)", "emcee's handheld", "hall mics (crowd noise, PA filtered)", "video soundtrack feed"],
        }[register]
        return Show(
            register=register,
            talk=talk,
            script=script,
            utterances=_lines(rows, variant, decoys=B_DECOYS, edits=B_MINIMAL) + _film(media, variant),
            channels=list(zip(("lapel", "host", "room", "program"), who)),
            mics={"lapel": "live", "host": "live", "room": "live", "program": "off"},
            mic_events=[(10.0, "host", "muted"), (148.2, "program", "on")],
            slide0=11,
            slide_changes=[(32.0, 12), (43.4, 13), (91.0, 14), (91.4, 15), (109.8, 14), (122.6, 16), (142.2, 17)],
            hard_out=160.0,
            media_item="Video: What the drivers said (1:05)" if para else "Film: Test drivers (1:05)",
            media_events=list(media),
        )

    def facts(self, v: View) -> dict[str, Any]:
        lapel = [r for r in v.rows if r.ch == "lapel"]
        content = [r for r in lapel if r.info["kind"] == "content"]
        order = list(v.units)
        pid = content[-1].info["unit"]
        said = {r.info["unit"] for r in content}
        first = next(r for r in content if r.info["unit"] == pid)
        skipped = [p for p in order[: order.index(pid)] if v.units[p][1] and p not in said]
        clapping = v.room[0] in APPLAUSE
        ends = [r.end for r in v.rows if r.ch == "room" and r.info.get("label") in APPLAUSE]
        state, changed = v.media
        return {
            "paragraph": {
                "id": pid,
                "closed": any(r.info["closing"] and r.info["unit"] == pid for r in content),
                "later_unsaid": any(p not in said for p in order[order.index(pid) + 1:]),
                "grace": _r(v.now - first.start) if skipped else None,
            },
            "skipped": skipped,
            "sound": {
                "lapel_gap": _r(v.now - max(r.end for r in lapel if r.info["kind"] != "filler")),
                "applause_now": clapping,
                "since_applause": 0.0 if clapping else _r(v.now - max(ends)),
            },
            "to_hard_out": _r(v.to_hard_out),
            "p7_said": "P7" in said,
            "media": {"state": state, "stall": _r(v.now - changed) if state == "playing" else 0.0},
        }

    def policy(self, z: dict[str, Any]) -> dict[str, Any]:
        media, sound, paragraph = z["media"], z["sound"], z["paragraph"]
        quiet = sound["lapel_gap"] >= 3 and not sound["applause_now"] and sound["since_applause"] >= 3
        if media["state"] == "playing" and media["stall"] >= 3:
            cue = "ad_lib"
        elif sound["applause_now"] or media["state"] == "playing":
            cue = "hold"
        elif z["skipped"] and paragraph["grace"] >= 5:
            cue = "flag_skipped"
        elif z["to_hard_out"] < 20 and not z["p7_said"]:
            cue = "cut_to_close"
        elif not paragraph["closed"] and quiet:
            cue = "keyword"
        elif paragraph["closed"] and paragraph["later_unsaid"] and quiet:
            cue = "next_opening"
        else:
            cue = "plain"
        return {"position": paragraph["id"], "cue": cue}

    def quantities(self, z: dict[str, Any]) -> list[tuple[str, float, tuple[float, ...]]]:
        sound = z["sound"]
        out = [("lapel_gap", sound["lapel_gap"], (3,)), ("to_hard_out", z["to_hard_out"], (20,))]
        if not sound["applause_now"]:
            out.append(("since_applause", sound["since_applause"], (3,)))
        if z["paragraph"]["grace"] is not None:
            out.append(("grace", z["paragraph"]["grace"], (5,)))
        if z["media"]["state"] == "playing":
            out.append(("stall", z["media"]["stall"], (3,)))
        return out

    def construction(self, variant: str) -> dict[str, Any]:
        return {
            "canonical": {"summary": "Keynote segment 01:20.5-02:59.5: applause, a double-click past must-say P4 into P5, the flag and its interruption by cheering, P4 out of order in her own words, a heckle and a filler stall, the hard-out cut, the film handoff, a freeze while playback says playing, a restart."},
            "paraphrase": {"summary": "Every free-text value reworded (talk, script, speech, film soundtrack, names, channel labels, the room detector's labels, media item, instructions, options); keys, times, numbers and IDs kept; the filler words and the 2-s phrase limit kept."},
            "lexical_decoy": {"summary": "Room voices added: " + ", ".join(f"{r[4]!r} ({fmt_mmss(r[0])})" for r in B_DECOY_ROWS)
                              + "; lapel asides reworded: " + ", ".join(map(repr, B_DECOYS.values()))
                              + "; film lines reworded: " + ", ".join(map(repr, B_FILM_DECOYS.values()))
                              + ". No host phrase, no applause or cheering, no lapel phrase added."},
            "minimal_cf": {"summary": "B1: the price draws [laughter], t19-25 hold -> flag_skipped. B2: 'in, um...' becomes 'in 12 countries.', t53-59 keyword -> next_opening. B3: the film never freezes (no ad-libs, no restart), t74-80 ad_lib -> hold."},
            "structural_cf": {"summary": "P4 is not must-say (moved to on-screen text), so t16-18 and t26-31 become plain."},
        }[variant]


SCENARIOS = [ResearchTalk, KeynotePrompter]
