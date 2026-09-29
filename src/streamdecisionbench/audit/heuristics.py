"""Family heuristics behind the human-action and content baselines (SPEC section 4).

Each heuristic reads one state in its family's fixed format (what the model
sees, nothing hidden) and returns hidden semantic answers keyed by the family's
internal question keys; a question it has no view on is left out. ``options``
gives the semantic ids each internal question offers in the scenario at hand.

* ``copy-human``: "copy the latest human action" (decision 13): the decision
  the humans' own bookkeeping implies (a slide click, a mic switched on, a film
  fired), mapped to an option, and the idle option otherwise. It runs as the
  ``copy-human`` adapter (``sdb eval``) and in ``sdb audit``.
* ``nearest-unit``: presentation's "latest content phrase -> nearest unit"
  (REALTIME_FAMILIES.md 4.1, Risks): the script unit sharing the most content
  words with the presenter's newest finalized phrase that shares any. It
  answers ``position`` only; ``sdb audit`` reports it per question.

Families without an entry have no heuristic of that kind yet.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from streamdecisionbench.adapters.local import content_words

Heuristic = Callable[[dict[str, Any], dict[str, set[str]]], dict[str, Any]]


def _channel(row: dict[str, Any]) -> str:
    """A channel row's or segment's channel (``channel``; ``ch`` / ``speaker`` in the first presentation format)."""
    return row.get("channel", row.get("ch", row.get("speaker", "")))


def _slides(spec: str) -> set[int]:
    """Slide numbers of a script unit's ``slides`` ("7-10", "12")."""
    numbers = [int(x) for x in re.findall(r"\d+", spec)]
    return set(range(numbers[0], numbers[-1] + 1)) if "-" in spec else set(numbers)


def presentation_copy_human(state: dict[str, Any], options: dict[str, set[str]]) -> dict[str, Any]:
    """The presenter's slide -> its script unit (the nearest one if none lists it); the operator's film playing ->
    hold; a mic the AV crew opened for another speaker (chair, floor, host) live -> captions; otherwise plain."""
    current = state["slides"]["current"]
    units = state["script"]
    position = min(units, key=lambda u: (current not in _slides(u["slides"]), min(abs(current - k) for k in _slides(u["slides"]))))["id"]
    guest_mic = any(c["mic"] == "live" and _channel(c) not in ("lapel", "room", "program") for c in state["channels"])
    cue = "hold" if state["media"]["state"] == "playing" else "caption" if guest_mic else "plain"
    return {"position": position, "cue": cue if cue in options.get("cue", ()) else "plain"}


def presentation_nearest_unit(state: dict[str, Any], options: dict[str, set[str]]) -> dict[str, Any]:
    """The unit (title, opening, points, closing) sharing most content words with the newest lapel phrase that shares any."""
    units = {
        u["id"]: set(content_words(" ".join([u.get("title", ""), u.get("opening", ""), *u.get("points", []), u.get("closing", "")])))
        for u in state["script"]
    }
    for row in reversed(state.get("segments", state.get("transcript", []))):
        if _channel(row) != "lapel":
            continue
        words = set(content_words(row["text"]))
        best = max(units, key=lambda uid: len(words & units[uid]))
        if words & units[best]:
            return {"position": best}
    return {}


HEURISTICS: dict[str, dict[str, Heuristic]] = {
    "copy-human": {"presentation_navigation": presentation_copy_human},
    "nearest-unit": {"presentation_navigation": presentation_nearest_unit},
}


def semantic_options(episode: dict[str, Any]) -> dict[str, set[str]]:
    """Internal question key -> the semantic ids its choice offers (empty for scores)."""
    keys = episode["hidden"].get("question_keys", {})
    semantics = episode["hidden"].get("option_semantics", {})
    return {keys.get(qid, qid): set(semantics.get(qid, {}).values()) for qid in episode["questions"]}
