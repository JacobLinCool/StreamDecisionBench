"""Shared real-time stream conventions (docs/legacy/REALTIME_FAMILIES.md 3.1-3.4, 3.8).

Times are float seconds on the scenario's own clock: a talk or call clock
(``mm:ss.s``, seconds since the talk started) or a wall clock (``hh:mm:ss``,
seconds since midnight). The state of tick ``t`` is read at
``window_start + t * tick_seconds``. Comparisons tolerate ``EPS`` of float noise,
so ``end + lag <= T`` holds for 441.6 + 0.3 against 441.9.

* Clocks: ``fmt_mmss``, ``fmt_hms``, ``parse_clock``, ``fmt_like``, ``first_tick``.
* Speech: ``Utterance`` and ``Speech`` model timed ASR for one or more speakers
  and render it at a read time into finalized segments, current partials and
  voice activity, with one declared finalization lag and rolling window.
* Event logs: ``window`` keeps the items of a rolling window ("newest 8",
  "last 90 s").
* Thresholds: ``margin_problem`` / ``assert_margin`` implement the 3.8 rule that
  a computed quantity sits at least one display unit from each threshold it is
  compared with, unless exact hits are allowed.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence, TypeVar

EPS = 1e-6

T_ = TypeVar("T_")


# ---------------------------------------------------------------------------
# Clocks
# ---------------------------------------------------------------------------


def _split(seconds: float, decimals: int) -> tuple[str, int, int]:
    """Sign and the magnitude in whole seconds and 10^-decimals fractions.

    The value must already lie on the display grid (float noise aside): a clock
    never rounds silently, because a margin checked on the unrounded value
    could flip once two displayed times are subtracted (3.8).
    """
    scale = 10**decimals
    exact = abs(seconds) * scale
    units = round(exact)
    if abs(exact - units) > EPS:
        raise ValueError(f"{seconds!r} s is not on the {10**-decimals:g} s display grid; round it before display and margin checks")
    sign = "-" if seconds < 0 and units else ""
    return sign, units // scale, units % scale


def _frac(frac: int, decimals: int) -> str:
    return f".{frac:0{decimals}d}" if decimals else ""


def fmt_mmss(seconds: float, decimals: int = 1, signed: bool = False) -> str:
    """Talk/call clock or signed duration: ``07:22.0``, ``-00:12.5``, ``+02:38.0``.

    Minutes are not wrapped into hours (``75:10.0``). ``signed`` adds ``+`` to
    non-negative values, for countdowns such as ``to_hard_out``.
    """
    sign, whole, frac = _split(seconds, decimals)
    if signed and not sign:
        sign = "+"
    return f"{sign}{whole // 60:02d}:{whole % 60:02d}{_frac(frac, decimals)}"


def fmt_hms(seconds: float, decimals: int = 0) -> str:
    """Wall clock from seconds since midnight: ``10:32:05`` or ``10:32:05.4``."""
    sign, whole, frac = _split(seconds, decimals)
    return f"{sign}{whole // 3600:02d}:{whole // 60 % 60:02d}:{whole % 60:02d}{_frac(frac, decimals)}"


_CLOCK = re.compile(r"^([+-]?)(\d+):(\d{2})(?::(\d{2}))?(?:\.(\d+))?$")


def parse_clock(text: str) -> float:
    """Seconds from ``mm:ss``, ``mm:ss.s``, ``hh:mm:ss`` or ``hh:mm:ss.s`` (optional sign).

    The leading field may be any size (``75:10.0``); the fields after it are below 60.
    """
    match = _CLOCK.match(text.strip())
    if not match:
        raise ValueError(f"not a clock: {text!r}")
    sign, a, b, c, frac = match.groups()
    if int(b) >= 60 or (c is not None and int(c) >= 60):
        raise ValueError(f"not a clock: {text!r} (minutes and seconds after the leading field are below 60)")
    whole = int(a) * 3600 + int(b) * 60 + int(c) if c is not None else int(a) * 60 + int(b)
    value = whole + (int(frac) / 10 ** len(frac) if frac else 0.0)
    return -value if sign == "-" else value


def fmt_like(seconds: float, template: str) -> str:
    """Format ``seconds`` in the style of ``template`` (same fields and decimals)."""
    match = _CLOCK.match(template.strip())
    if not match:
        raise ValueError(f"not a clock: {template!r}")
    decimals = len(match.group(5) or "")
    if match.group(4) is not None:
        return fmt_hms(seconds, decimals)
    return fmt_mmss(seconds, decimals, signed=match.group(1) == "+")


def first_tick(at: float, start: float, tick_seconds: float) -> int:
    """The first tick whose read time ``start + t * tick_seconds`` is at or after ``at``.

    Evidence timing (3.4): a gold change caused by a fact that becomes visible
    at ``at`` (for speech, ``end + lag``) must happen exactly at this tick.
    """
    return max(0, math.ceil((at - start) / tick_seconds - EPS))


# ---------------------------------------------------------------------------
# Rolling windows
# ---------------------------------------------------------------------------


def window(
    items: Iterable[T_],
    now: float,
    at: Callable[[T_], float],
    seconds: float | None = None,
    last: int | None = None,
    inclusive: bool = True,
) -> list[T_]:
    """Items of a rolling window at read time ``now``, oldest first.

    Only items with ``at(item) <= now`` exist yet. ``seconds`` keeps those with
    ``at >= now - seconds`` (``>`` when ``inclusive`` is false); ``last`` then
    keeps the newest ``last`` of them. Items are ordered by ``at`` (stable).
    """
    kept = sorted((x for x in items if at(x) <= now + EPS), key=at)
    if seconds is not None:
        edge = now - seconds
        kept = [x for x in kept if (at(x) >= edge - EPS if inclusive else at(x) > edge + EPS)]
    if last is not None:
        kept = kept[-last:] if last > 0 else []
    return kept


# ---------------------------------------------------------------------------
# Spoken form of partials
# ---------------------------------------------------------------------------

_ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen"
).split()
_TENS = "- - twenty thirty forty fifty sixty seventy eighty ninety".split()
_SCALES = ((10**9, "billion"), (10**6, "million"), (1000, "thousand"))
_ORDINAL = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth",
            "nine": "ninth", "twelve": "twelfth"}


def number_words(n: int) -> str:
    """Spoken English for a non-negative integer: 41900 -> 'forty one thousand nine hundred'."""
    if n < 0:
        return "minus " + number_words(-n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("" if n % 10 == 0 else " " + _ONES[n % 10])
    if n < 1000:
        return _ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + number_words(n % 100))
    for size, name in _SCALES:
        if n >= size:
            return number_words(n // size) + " " + name + ("" if n % size == 0 else " " + number_words(n % size))
    raise AssertionError("unreachable")


def _ordinal(words: str) -> str:
    *head, last = words.split()
    if last in _ORDINAL:
        last = _ORDINAL[last]
    elif last.endswith("y"):
        last = last[:-1] + "ieth"
    else:
        last += "th"
    return " ".join([*head, last])


_NUMBER = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(st|nd|rd|th)?(%)?", re.I)
_PUNCT = re.compile(r"[^\w\s']|_|(?<!\w)'|'(?!\w)")


def _number(match: re.Match[str]) -> str:
    whole, frac, suffix, percent = match.groups()
    words = number_words(int(whole.replace(",", "")))
    if frac:
        words += " point " + " ".join(_ONES[int(d)] for d in frac)
    elif suffix:
        words = _ordinal(words)
    return f" {words}{' percent' if percent else ''} "


def spoken(text: str) -> str:
    """ASR interim style: lower case, no punctuation, numbers as words.

    Apostrophes inside words stay ("don't"); hyphens and other marks become
    spaces; ``41,900`` -> "forty one thousand nine hundred", ``0.3`` -> "zero
    point three", ``12%`` -> "twelve percent", ``3rd`` -> "third". Anything more
    exotic (card numbers read digit by digit, currencies) is written by the
    author as an explicit partial revision.
    """
    text = _NUMBER.sub(_number, text)
    return " ".join(_PUNCT.sub(" ", text.lower()).split())


# ---------------------------------------------------------------------------
# Speech
# ---------------------------------------------------------------------------

_SOUND_TAG = re.compile(r"^(\s*\[[^\]]*\]\s*)+$")


@dataclass
class Utterance:
    """One stretch of speech (or one sound event) as the ASR will finalize it.

    ``text`` is the final: punctuated, digits for numbers. ``revisions`` are
    optional explicit partial hypotheses ``(from_time, text)``, oldest first;
    each is shown from its time until the next one or finalization, and before
    the first one the default partial (the words spoken so far) is shown. A
    text made only of sound tags (``[laughter]``) never produces a partial.
    ``info`` carries hidden per-utterance facts for the policy (kind, unit,
    closing, ...); it is never rendered.
    """

    start: float
    end: float
    speaker: str
    text: str
    revisions: tuple[tuple[float, str], ...] = ()
    channel: str | None = None
    info: dict[str, Any] = field(default_factory=dict)

    @property
    def sound(self) -> bool:
        return bool(_SOUND_TAG.match(self.text))


@dataclass
class Partial:
    speaker: str
    since: float
    text: str
    utterance: Utterance


@dataclass
class Speech:
    """Timed ASR for one stream, rendered at read time ``T``.

    * **Finals.** An utterance is final once ``end + lag <= T``. ``segments(T)``
      keeps the finals inside the rolling window: ``window_by`` ("end" or
      "start") must be ``>= T - window`` (``>`` when ``inclusive`` is false);
      ``window=None`` keeps everything. Ordered oldest first by ``order``
      ("start" or "end").
    * **Partials.** Speech that started but is not final yet: ``start +
      partial_lag <= T < end + lag``. At most one per speaker, always that
      speaker's newest utterance, in ``spoken()`` form. The default text is the
      words spoken by ``T - partial_lag`` (in proportion to elapsed time, at
      least one word; all of them once speech has ended).
    * **Voice activity.** A speaker is speaking while ``start <= T < end +
      hangover`` for one of their utterances; "speaking since" is the start of
      the current run (utterances whose hangover intervals touch chain), and
      "silent since" is the end of the last utterance (not end + hangover).

    Families state ``lag``, ``window``, the boundary and the ordering in their
    instructions (3.3, 3.4); this class is the single implementation of them.
    """

    utterances: Sequence[Utterance]
    lag: float = 0.3
    window: float | None = 90.0
    window_by: str = "end"
    inclusive: bool = True
    order: str = "start"
    partial_lag: float = 0.0
    hangover: float = 0.0

    def __post_init__(self) -> None:
        if self.window_by not in ("start", "end") or self.order not in ("start", "end"):
            raise ValueError("window_by and order must be 'start' or 'end'")
        self.utterances = sorted(self.utterances, key=lambda u: (u.start, u.end))

    def is_final(self, u: Utterance, T: float) -> bool:
        return u.end + self.lag <= T + EPS

    def final_at(self, u: Utterance) -> float:
        """When ``u``'s final segment first appears (evidence time, 3.4)."""
        return u.end + self.lag

    def finals(self, T: float, speaker: str | None = None) -> list[Utterance]:
        """Every finalized utterance so far (no window), oldest first by start."""
        return [u for u in self.utterances if self.is_final(u, T) and (speaker is None or u.speaker == speaker)]

    def segments(self, T: float) -> list[Utterance]:
        """Finalized utterances inside the rolling window, in the declared order."""
        at = (lambda u: u.end) if self.window_by == "end" else (lambda u: u.start)
        kept = window(self.finals(T), T, at, seconds=self.window, inclusive=self.inclusive)
        return sorted(kept, key=(lambda u: (u.end, u.start)) if self.order == "end" else (lambda u: (u.start, u.end)))

    def _partial_text(self, u: Utterance, T: float) -> str:
        shown = [text for at, text in u.revisions if at <= T + EPS]
        if shown:
            return spoken(shown[-1])
        words = spoken(u.text).split()
        heard = T - self.partial_lag
        fraction = 1.0 if heard >= u.end else (heard - u.start) / max(u.end - u.start, 0.1)
        return " ".join(words[: max(1, int(len(words) * fraction + EPS))])

    def partials(self, T: float) -> list[Partial]:
        """Current partials, at most one per speaker, oldest first by start."""
        newest: dict[str, Utterance] = {}
        for u in self.utterances:
            if u.sound or not (u.start + self.partial_lag <= T + EPS and T < u.end + self.lag - EPS):
                continue
            if u.speaker not in newest or u.start >= newest[u.speaker].start:
                newest[u.speaker] = u
        out = [Partial(u.speaker, u.start, self._partial_text(u, T), u) for u in newest.values()]
        return sorted((p for p in out if p.text), key=lambda p: p.since)

    def activity(self, T: float, speaker: str) -> tuple[str, float | None]:
        """``("speaking", since)`` or ``("silent", since)``; since is None if never spoken."""
        own = [u for u in self.utterances if u.speaker == speaker and u.start <= T + EPS]
        if not own:
            return "silent", None
        since = None
        run_end = -math.inf
        for u in own:
            if since is None or u.start > run_end + EPS:
                since = u.start
            run_end = max(run_end, u.end + self.hangover)
        if T < run_end - EPS:
            return "speaking", since
        return "silent", max(u.end for u in own)

    def silence(self, T: float, speaker: str) -> float | None:
        """Seconds since the speaker went silent (0 while speaking, None if never spoken)."""
        state, since = self.activity(T, speaker)
        if since is None:
            return None
        return 0.0 if state == "speaking" else T - since

    def problems(self) -> list[str]:
        """Authoring errors: bad intervals, overlapping or unfinalized same-speaker speech, stray revisions.

        Sound-tag utterances never produce partials, so back-to-back room events
        are not held to the one-partial-per-speaker rule.
        """
        out: list[str] = []
        last: dict[str, Utterance] = {}
        for u in self.utterances:
            where = f"{u.speaker} {u.start:g}-{u.end:g} {u.text[:30]!r}"
            if u.end <= u.start:
                out.append(f"{where}: ends before it starts")
            times = [at for at, _ in u.revisions]
            if times != sorted(times) or any(not u.start <= at < u.end + self.lag for at in times):
                out.append(f"{where}: partial revisions must be ordered and fall in [start, end + lag)")
            if u.sound:
                continue
            prev = last.get(u.speaker)
            if prev is not None and u.start < prev.end + self.lag - EPS:
                out.append(f"{where}: starts before the speaker's previous utterance is final (one partial per speaker)")
            last[u.speaker] = u
        return out

    def segment_rows(self, T: float, clock: Callable[[float], str]) -> list[dict[str, Any]]:
        """Segments in the shared shape ``{start, end, speaker[, channel], text}``."""
        rows = []
        for u in self.segments(T):
            row: dict[str, Any] = {"start": clock(u.start), "end": clock(u.end), "speaker": u.speaker}
            if u.channel is not None:
                row["channel"] = u.channel
            row["text"] = u.text
            rows.append(row)
        return rows

    def partial_rows(self, T: float, clock: Callable[[float], str]) -> list[dict[str, Any]]:
        """Partials in the shared shape ``{speaker, since, text}``."""
        return [{"speaker": p.speaker, "since": clock(p.since), "text": p.text} for p in self.partials(T)]


# ---------------------------------------------------------------------------
# Threshold margins (3.8)
# ---------------------------------------------------------------------------


class MarginError(AssertionError):
    """A computed quantity sits too close to a threshold it is compared with."""


def margin_problem(
    value: float, threshold: float, unit: float, exact_allowed: bool = False, what: str = "value"
) -> str | None:
    """None if ``value`` respects the 3.8 margin rule for ``threshold``, else a message.

    A value exactly on the threshold is allowed only with ``exact_allowed`` (the
    rule states whether the line counts and the display shows the threshold's
    precision); any other value must be at least one display ``unit`` away.
    Presentation uses ``exact_allowed=False`` (no ties at all).

    Compute ``value`` from the operands as displayed (on the display grid, as
    the ``fmt_*`` clocks require), never from finer latent times: the model
    subtracts what it sees.
    """
    steps = (value - threshold) / unit
    if abs(steps) < EPS:
        return None if exact_allowed else f"{what} {value:g} sits exactly on the threshold {threshold:g}"
    if abs(steps) < 1 - EPS:
        return f"{what} {value:g} is less than one unit ({unit:g}) from the threshold {threshold:g}"
    return None


def assert_margin(value: float, threshold: float, unit: float, exact_allowed: bool = False, what: str = "value") -> None:
    """Raise ``MarginError`` where ``margin_problem`` reports one."""
    problem = margin_problem(value, threshold, unit, exact_allowed, what)
    if problem:
        raise MarginError(problem)
