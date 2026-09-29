"""Metric definitions on hand-made trajectories."""

from __future__ import annotations

import copy

from streamdecisionbench.jev import INVALID
from streamdecisionbench.metrics import (
    TemporalConfig,
    aggregate,
    contrast_probes,
    episode_metrics,
    stable_switches,
)


def make_episode(gold: str, variant: str = "canonical", family: str = "fam_a", deadline: int = 2) -> dict:
    return {
        "episode_id": f"{family}_{variant}",
        "task_family": "presentation_navigation",
        "contrast_family": family,
        "variant": variant,
        "difficulty": {"tier": "easy"},
        "decision_structures": ["maintain"],
        "deadline_steps": deadline,
        "questions": {"q1": {"type": "choice"}},
        "hidden": {"option_semantics": {"q1": {}}},
        "steps": [{"t": t, "gold": {"q1": g}, "event_tags": ["steady"]} for t, g in enumerate(gold)],
    }


def records(pred: str) -> list[dict]:
    return [{"t": t, "ok": p != "?", "pred": {"q1": p}, "latency_ms": 1.0} for t, p in enumerate(pred)]


CFG = TemporalConfig(delta=2, hold=2)


def test_perfect_and_constant():
    ep = make_episode("AAAABBBBAAAACCCC")
    m = episode_metrics(ep, records("AAAABBBBAAAACCCC"), CFG)
    assert m["sba"] == 1 and m["transition_f1"] == 1 and m["esr"] == 0 and m["dsr"] == 1
    m = episode_metrics(ep, records("AAAAAAAAAAAAAAAA"), CFG)
    # A-segments fully right, B and C segments fully wrong: SBA = 2/4
    assert m["sba"] == 0.5
    assert m["tp"] == 0 and m["fn"] == 3 and m["transition_f1"] == 0 and m["dsr"] == 0


def test_delay_deadline_and_early():
    ep = make_episode("AAAAAABBBBBBBB", deadline=1)
    late = episode_metrics(ep, records("AAAAAAAABBBBBB"), CFG)  # two ticks late
    assert late["tp"] == 1 and late["reaction_delays"] == [2] and late["dsr"] == 0.0
    early = episode_metrics(ep, records("AAAAABBBBBBBBB"), CFG)  # one tick early
    assert early["tp"] == 1 and early["early_switches"] == 1 and early["reaction_delays"] == []
    too_late = episode_metrics(ep, records("AAAAAAAAABBBBB"), CFG)  # three ticks late: outside delta
    assert too_late["tp"] == 0 and too_late["fp"] == 1 and too_late["fn"] == 1


def test_flicker_is_not_a_stable_switch_but_counts_as_raw():
    ep = make_episode("AAAAAAAAAA")
    m = episode_metrics(ep, records("AABABAAAAA"), CFG)
    assert m["fp"] == 0 and m["esr"] == 0
    assert m["raw_switch_rate"] == 0.4


def test_invalid_answers_are_wrong():
    ep = make_episode("AAAABBBB")
    m = episode_metrics(ep, records("AA??BBBB"), CFG)
    assert m["accuracy"] == 0.75 and m["invalid"] == 2


def test_settled_decision_starts_at_the_first_valid_answer():
    ep = make_episode("AAAABBBBAAAA")
    m = episode_metrics(ep, records("??AABBBBAAAA"), CFG)  # e.g. no answer in force yet
    assert m["accuracy"] == 10 / 12 and m["fp"] == 0 and m["tp"] == 2 and m["esr"] == 0
    assert stable_switches([INVALID, INVALID, "A", "A", "B", "B"], 2) == [(4, "B")]
    assert stable_switches([INVALID] * 4, 2) == []
    m = episode_metrics(ep, records("AA??BBBBAAAA"), CFG)  # a held invalid stretch later on is still a switch
    assert m["raw_switch_rate"] == 3 / 12 and m["fp"] == 1


def test_deadline_and_delays_in_seconds_for_timed_episodes():
    ep = make_episode("AAAAAABBBBBBBB", deadline=5)
    ep.update(schema_version="sdb/0.2", tick_seconds=2, deadline_seconds=2)  # 1 tick; the stored 5 is ignored
    m = episode_metrics(ep, records("AAAAAAAABBBBBB"), CFG)  # two ticks late
    assert m["reaction_delays"] == [2] and m["reaction_delays_s"] == [4] and m["dsr"] == 0 and m["deadline_steps"] == 1
    assert episode_metrics(make_episode("AAAAAABBBBBBBB"), records("AAAAAAAABBBBBB"), CFG)["reaction_delays_s"] == []


def test_contrast_probes_and_csa():
    canonical = make_episode("AAAABBBBAAAA")
    minimal = make_episode("AAAAAAAAAAAA", "minimal_cf")  # flip at t4..7
    structural = make_episode("AAAABBBBCCCC", "structural_cf")  # flip at t8..11
    para = make_episode("AAAABBBBAAAA", "paraphrase")
    decoy = make_episode("AAAABBBBAAAA", "lexical_decoy")
    fam = {e["variant"]: e for e in (canonical, minimal, structural, para, decoy)}
    probes = contrast_probes(fam)
    assert len(probes) == 2
    assert ("minimal_cf", 4) in probes[0] and ("canonical", 7) in probes[0] and ("paraphrase", 5) in probes[0]
    episodes = list(fam.values())
    preds = {e["episode_id"]: records("".join(s["gold"]["q1"] for s in e["steps"])) for e in episodes}
    agg = aggregate(episodes, preds, CFG)
    assert agg["primary"]["csa"] == 1.0 and agg["secondary"]["csa_probe"] == 1.0
    # One wrong tick inside a probe in the decoy variant breaks the family.
    broken = copy.deepcopy(preds)
    broken[decoy["episode_id"]][9]["pred"]["q1"] = "B"
    agg = aggregate(episodes, broken, CFG)
    assert agg["primary"]["csa"] == 0.0 and agg["secondary"]["csa_probe"] == 0.5


def test_multi_question_composite():
    ep = make_episode("AAAABBBB")
    ep["questions"]["q2"] = {"type": "noul"}
    for s in ep["steps"]:
        s["gold"]["q2"] = s["t"] >= 6
    recs = records("AAAABBBB")
    for r in recs:
        r["pred"]["q2"] = r["t"] >= 6
    m = episode_metrics(ep, recs, CFG)
    assert m["transitions"] == 2 and m["tp"] == 2 and m["accuracy"] == 1
    recs[6]["pred"]["q2"] = False  # q2 one tick late: composite wrong at t6
    m = episode_metrics(ep, recs, CFG)
    assert m["accuracy"] == 7 / 8 and m["per_question_accuracy"]["q1"] == 1.0
    assert m["reaction_delays"] == [0, 1]
