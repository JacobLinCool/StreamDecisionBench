"""Decision-13 baselines and family heuristics: copy-human (adapter and audit) and nearest-unit.

The episode is a small synthetic presentation stream whose states carry only
the presentation fields the heuristics read.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from streamdecisionbench.adapters import make_adapter_factory
from streamdecisionbench.audit.heuristics import presentation_copy_human, presentation_nearest_unit
from streamdecisionbench.audit.shortcuts import Audit
from streamdecisionbench.evaluator import evaluate

SCRIPT = [
    {"id": "S1", "title": "Why on-device search", "slides": "1-3", "opening": "Every search goes to a server.",
     "points": ["latency and privacy cost"], "closing": "Can the index live on the phone?"},
    {"id": "S2", "title": "What exists today", "slides": "4-6", "opening": "Two families of retrievers exist.",
     "points": ["dense retrievers are large"], "closing": "Neither fits a phone."},
]
POSITION = {"K2": "S1", "M3": "S2"}
CUE = {"B4": "plain", "D5": "caption", "F6": "hold"}


def state(slide: int, *lapel: str, guest: bool = False, playing: bool = False) -> dict:
    """Lapel phrases oldest first; a floor question sits after them."""
    rows = [{"channel": "lapel", "text": text} for text in lapel] + [{"channel": "floor", "text": "What about dense retrievers?"}]
    return {
        "script": SCRIPT,
        "slides": {"current": slide},
        "channels": [{"channel": "lapel", "mic": "live"}, {"channel": "floor", "mic": "live" if guest else "off"}, {"channel": "room", "mic": "live"}],
        "segments": rows,
        "media": {"state": "playing" if playing else "none"},
    }


STEPS = [  # (state, gold position, gold cue)
    (state(2, "Latency and privacy both cost you."), "S1", "plain"),
    (state(5, "Latency and privacy both cost you."), "S1", "plain"),  # the slide leads the talk
    (state(5, "Two families of retrievers exist today.", guest=True), "S2", "caption"),
    (state(5, "Two families of retrievers exist today.", "Um, sorry.", playing=True), "S2", "plain"),
]


@pytest.fixture()
def episode() -> dict:
    return {
        "schema_version": "sdb/0.2",
        "episode_id": "talk_canonical",
        "task_family": "presentation_navigation",
        "contrast_family": "talk",
        "variant": "canonical",
        "tick_seconds": 2,
        "deadline_seconds": 2,
        "questions": {
            "q1": {"type": "choice", "instructions": "Section?", "criteria": {k: f"{v} section" for k, v in POSITION.items()}},
            "q2": {"type": "choice", "instructions": "Cue?", "criteria": {k: f"{v} card" for k, v in CUE.items()}},
        },
        "hidden": {"question_keys": {"q1": "position", "q2": "cue"}, "option_semantics": {"q1": POSITION, "q2": CUE}},
        "steps": [
            {"t": t, "state": s, "gold": {"q1": pos, "q2": cue}, "event_tags": ["steady"]} for t, (s, pos, cue) in enumerate(STEPS)
        ],
    }


def test_presentation_heuristics():
    options = {"position": {"S1", "S2"}, "cue": {"plain", "caption", "hold"}}
    assert [presentation_copy_human(s, options) for s, _, _ in STEPS] == [
        {"position": "S1", "cue": "plain"},
        {"position": "S2", "cue": "plain"},
        {"position": "S2", "cue": "caption"},
        {"position": "S2", "cue": "hold"},
    ]
    assert presentation_copy_human(state(9, ""), {"cue": {"plain"}}) == {"position": "S2", "cue": "plain"}  # nearest unit's slides
    assert presentation_copy_human(state(1, "", guest=True), {"cue": {"plain", "hold"}})["cue"] == "plain"  # no caption option
    assert [presentation_nearest_unit(s, options) for s, _, _ in STEPS] == [
        {"position": "S1"}, {"position": "S1"}, {"position": "S2"}, {"position": "S2"},  # "Um, sorry." shares nothing: an older phrase decides
    ]
    assert presentation_nearest_unit(state(1, "Thank you."), options) == {}  # no content phrase in the window: no answer


def test_copy_human_adapter(episode):
    records = evaluate(make_adapter_factory("copy-human", [episode]), [episode])["talk_canonical"]
    assert [r["pred"] for r in records] == [
        {"q1": "S1", "q2": "plain"}, {"q1": "S2", "q2": "plain"}, {"q1": "S2", "q2": "caption"}, {"q1": "S2", "q2": "hold"},
    ]
    other = dict(episode, task_family="support_orchestration")
    with pytest.raises(ValueError, match="no human-action map"):
        make_adapter_factory("copy-human", [other])


def test_audit_reports_heuristics_per_question(episode, tmp_path: Path):
    audit = Audit([episode], tmp_path)
    audit.family_heuristics()
    report = audit.report()["methods"]
    copy_human, nearest = report["copy-human"], report["nearest-unit"]
    assert copy_human["coverage"] == 1 and copy_human["by_question"] == {"cue": 0.75, "position": 0.75}
    assert copy_human["decision_accuracy"] == 0.5 and copy_human["sba"] is not None
    assert nearest["coverage"] == 0.5 and nearest["by_question"] == {"position": 1.0}
    assert nearest["decision_accuracy"] is None and nearest["sba"] is None
