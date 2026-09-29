"""presentation_navigation (sdb/0.2) against its design (legacy real-time family design, section 4.1; kept locally).

The canonical gold timelines and the counterfactual flips are pinned to the
design tables; ``check()`` must pass on every built variant and must catch a
threshold tie, a finalization on a read time, a renderer that drops the window
guarantee and a state that reports sound or silence faster than the declared
latencies.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from streamdecisionbench.authoring import build_episode, gold_track
from streamdecisionbench.authoring.stream import parse_clock
from streamdecisionbench.families.presentation_navigation import SCENARIOS, KeynotePrompter, ResearchTalk, Show
from streamdecisionbench.metrics import segments
from streamdecisionbench.schema import VARIANTS, gold_sequence
from streamdecisionbench.validate import Report, check_episode

# Transition ticks (REALTIME_FAMILIES.md 4.1, "Transitions") and counterfactual flip runs (variant table).
TRANSITIONS = {
    "presentation_a": [13, 16, 38, 45, 60, 63, 66, 71, 74, 77, 91],
    "presentation_b": [4, 12, 16, 19, 26, 32, 40, 45, 53, 60, 65, 68, 74, 81],
}
FLIPS = {
    ("presentation_a", "minimal_cf"): [(13, 15), (71, 73), (91, 99)],
    ("presentation_a", "structural_cf"): [(74, 76), (91, 99)],
    ("presentation_b", "minimal_cf"): [(19, 25), (53, 59), (74, 80)],
    ("presentation_b", "structural_cf"): [(16, 18), (26, 31)],
}


@pytest.fixture(scope="module")
def built() -> dict[str, dict[str, dict[str, Any]]]:
    return {cls.scenario_id: {v: build_episode(cls(), v) for v in VARIANTS} for cls in SCENARIOS}


def test_episodes_pass_structural_checks(built):
    report = Report()
    for episodes in built.values():
        for episode in episodes.values():
            check_episode(episode, report)
    assert report.errors == [] and report.warnings == []


def test_canonical_timelines_match_the_design(built):
    for sid, ticks in TRANSITIONS.items():
        gold = gold_sequence(built[sid]["canonical"])
        assert [a for a, _, _ in segments(gold)][1:] == ticks
        assert min(b - a for a, b, _ in segments(gold)) >= 3


def test_counterfactual_flips_match_the_design(built):
    for (sid, variant), runs in FLIPS.items():
        base, gold = gold_sequence(built[sid]["canonical"]), gold_sequence(built[sid][variant])
        diff = segments(["d" if x != y else "s" for x, y in zip(base, gold)])
        assert [(a, b - 1) for a, b, v in diff if v == "d"] == runs


def test_check_passes_on_every_variant(built):
    for cls in SCENARIOS:
        scenario = cls()
        for variant, episode in built[cls.scenario_id].items():
            _, ticks, golds = gold_track(scenario, variant)
            assert scenario.check(variant, ticks, golds, [s["state"] for s in episode["steps"]]) == []


def test_check_catches_a_threshold_tie():
    class Tie(ResearchTalk):
        def build_show(self, variant: str) -> Show:
            show = super().build_show(variant)
            lines = copy.deepcopy(show.utterances)
            for u in lines:
                if u.start == 534.2:
                    u.end = 536.0  # 'Does that answer it?' ends 4.0 s before t60
                if u.start == 550.2:
                    u.end = 551.7  # final at 552.0, t66's read time
            fields = ("register", "talk", "script", "channels", "mics", "mic_events", "slide0", "slide_changes", "hard_out", "media_item", "media_events")
            return Show(utterances=lines, **{k: getattr(show, k) for k in fields})

    scenario = Tie()
    _, ticks, golds = gold_track(scenario, "canonical")
    states = [scenario.render(ticks[: t + 1], "canonical") for t in range(100)]
    problems = scenario.check("canonical", ticks, golds, states)
    assert any("t=60 silence 4 sits exactly on the threshold 4" in p for p in problems)
    assert any("finalizes exactly at a read time" in p for p in problems)


def test_check_catches_a_short_transcript_window(built):
    scenario = KeynotePrompter()
    _, ticks, golds = gold_track(scenario, "canonical")
    states = [copy.deepcopy(s["state"]) for s in built["presentation_b"]["canonical"]["steps"]]
    for state in states:
        now = parse_clock(state["clock"]["now"])
        state["segments"] = [r for r in state["segments"] if parse_clock(r["end"]) >= now - 30]
    problems = scenario.check("canonical", ticks, golds, states)
    assert any(p.startswith("t=49: the rendered state gives") and "'skipped': ['P5']" in p for p in problems)


def test_check_catches_instant_detection(built):
    scenario = KeynotePrompter()
    _, ticks, golds = gold_track(scenario, "canonical")
    states = [copy.deepcopy(s["state"]) for s in built["presentation_b"]["canonical"]["steps"]]
    room = next(r for r in states[12]["voice"] if r["channel"] == "room")
    room["since"] = "01:32.4"  # applause 'ended' 0.1 s before t12's read, faster than the 0.5-s detector
    lapel = next(r for r in states[40]["voice"] if r["channel"] == "lapel")
    lapel.update(state="silent", since="02:00.4")  # silence 0.1 s old, faster than the 0.3-s endpointing
    problems = scenario.check("canonical", ticks, golds, states)
    assert any(p.startswith("t=12: room reads quiet since 01:32.4, less than 0.5 s ago") for p in problems)
    assert any(p.startswith("t=40: lapel reads silent since 02:00.4, less than 0.3 s ago") for p in problems)
