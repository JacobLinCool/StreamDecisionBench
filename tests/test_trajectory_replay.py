"""Independently derived timelines verify provisional answers and source regression."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "paper/analysis"))
from trajectory_replay import Component, Scenario, arbitrate, evaluate
from lite_trajectory_value import integrate, regression_example, transition_errors
from streamdecisionbench.lite.core import compose
from streamdecisionbench.lite.retry_scoring import normalized_episode_scores
from test_lite_retry_scoring import episode, record, releases


def scenario(gold=("A",), fast=("B",), slow=("A",), fast_delay=(0.1,), slow_delay=(0.5,)):
    decision = lambda values: tuple({"route": v} for v in values)
    return Scenario("test", "test", 2.0, tuple(2.0 * t for t in range(len(gold))),
                    decision(gold), {"fast": Component(decision(fast), fast_delay),
                                     "slow": Component(decision(slow), slow_delay)})


def test_slow_corrects_same_state_but_provisional_error_has_duration():
    # No decision [0,.1), wrong fast [.1,.5), correct slow [.5,2).
    row = evaluate(scenario(), "fast", "slow", 2, trace=True)
    assert row["accuracy"] == pytest.approx(0.75)
    assert row["oracle"] == pytest.approx(0.95)
    assert row["judgment"] == pytest.approx(0.2)
    assert row["terminal_product"] == pytest.approx(0.95)
    assert row["counts"]["same_state_corrections"] == 1
    assert [r["component"] for r in row["accepted"]] == ["fast", "slow"]


def test_late_old_correction_regresses_source_and_creates_stale_time():
    sc = scenario(("A", "B"), ("A", "B"), ("A", "B"), (0.1, 0.1), (2.5, 2.5))
    # Fresh: none .1 + stale .1 = .2 s error out of 4.
    fresh = evaluate(sc, "fast", "slow", 2, "freshest", trace=True)
    # Override adds stale A [2.5,4); slow B arrives beyond the horizon.
    late = evaluate(sc, "fast", "slow", 2, "arrival", trace=True)
    assert fresh["accuracy"] == pytest.approx(0.95)
    assert late["accuracy"] == pytest.approx(0.575)
    assert late["counts"]["source_regressions"] == 1
    assert [r["source_t"] for r in late["accepted"]] == [0, 1, 0]
    assert late["stale"] == pytest.approx(0.4)


def test_one_tick_guard_admits_one_tick_regression_but_blocks_two():
    events = [(0.1, 0, 0, {}), (2.1, 1, 0, {}), (4.1, 2, 0, {}),
              (4.2, 0, 1, {}), (4.3, 1, 1, {})]
    accepted, counts = arbitrate(events, 6, "lag_one")
    assert [(t, c) for _, t, c, _ in accepted] == [(0, 0), (1, 0), (2, 0), (1, 1)]
    assert counts["slow_exceeds_lag"] == 1
    assert counts["source_regressions"] == 1


def test_rejected_component_delivery_still_updates_its_high_water_mark():
    events = [(0.1, 4, 0, {}), (0.2, 3, 1, {}), (0.3, 2, 1, {})]
    accepted, counts = arbitrate(events, 2, "freshest")
    assert len(accepted) == 1
    assert counts["slow_exceeds_lag"] == 1
    assert counts["older_within_component"] == 1


def test_source_ties_slow_priority_and_horizon_exclusion():
    events = [(0.5, 0, 0, {}), (0.5, 0, 1, {}), (2.0, 1, 1, {})]
    accepted, counts = arbitrate(events, 2, "freshest")
    assert accepted == [(0.5, 0, 1, {})]
    assert counts["after_horizon"] == 1
    assert counts["fast_not_newer"] == 1


@pytest.mark.parametrize("policy", ["freshest", "lag_one", "arrival"])
def test_oracle_identity_and_selection_do_not_depend_on_predictions(policy):
    sc = scenario(("A", "B", "A"), ("B", "B", "B"), ("A", "A", "A"),
                  (0.1, 0.1, 0.1), (2.5, 2.5, 0.5))
    before = deepcopy(sc)
    row = evaluate(sc, "fast", "slow", 2, policy, trace=True)
    oracle_sc = replace(sc, components={k: replace(v, predictions=sc.gold) for k, v in sc.components.items()})
    oracle = evaluate(oracle_sc, "fast", "slow", 2, policy, trace=True)
    assert row["accepted"] == oracle["accepted"]
    assert row["oracle"] == pytest.approx(oracle["accuracy"])
    assert row["accuracy"] == pytest.approx(row["current_correct"] + row["outdated_correct"])
    assert sc == before


@pytest.mark.parametrize("durations", [(0, 0, 0), (2.5, 0.1, 0.5), (0.5, 0.5, 2), (9, 9, 9)])
def test_single_component_matches_existing_exact_scorer(durations):
    ep = episode()
    records = [record(t, duration=d) for t, d in enumerate(durations)]
    gold = tuple(compose(ep["decision_spec"], s["gold"]) for s in ep["steps"])
    sc = Scenario("retry_test", "test", 2, (0, 2, 4), gold, {"fast": Component(gold, durations)})
    actual = evaluate(sc, "fast", None, 2)
    expected = normalized_episode_scores(ep, records, releases())
    assert actual["accuracy"] == pytest.approx(expected["time_accuracy"], abs=1e-12)
    for k, seconds in expected["time_partition_seconds"].items():
        assert actual[k] == pytest.approx(seconds / 6, abs=1e-12)


@pytest.mark.parametrize("lo,hi", [(1, 5), (.5, 8), (1, 4)])
def test_outer_integral_has_known_closed_form(lo, hi):
    # Wrong provisional output lasts until .5 after each release: A(delta)=1-.5/delta.
    actual = integrate([scenario()], "fast", "slow", "freshest",
                       {"min_s": lo, "max_s": hi, "weighting": "log"})
    import math
    assert actual["overall"]["accuracy"] == pytest.approx(1 - .5 * (1 / lo - 1 / hi) / math.log(hi / lo), abs=1e-12)


def test_log_integral_splits_at_discontinuous_acceptance_crossing():
    # Slow t0 at 2.5 is accepted just after fast t1 for delta<2.4,
    # but fast t1 replaces it for delta>2.4, giving a jump in held accuracy.
    sc = scenario(("A", "B"), ("A", "B"), ("A", "B"), (0.1, 0.1), (2.5, 2.5))
    actual = integrate([sc], "fast", "slow", "arrival",
                       {"min_s": 2, "max_s": 3, "weighting": "log"})
    import math
    expected = (1.15 * (1/2 - 1/2.4) + math.log(3/2.4) - 0.1 * (1/2.4 - 1/3)) / math.log(3/2)
    assert actual["overall"]["accuracy"] == pytest.approx(expected, abs=1e-12)


def test_signed_transition_bins_count_states_once_and_ties_use_earlier_change():
    sc = scenario(("A", "B", "B", "A", "A"), ("B", "B", "A", "A", "B"),
                  ("A", "B", "B", "A", "A"), (0,) * 5, (0,) * 5)
    row = transition_errors([sc], "fast", 0)
    assert [r["offset"] for r in row["states"]] == [-1, 0, 1, 0, 1]
    assert row["near"]["states"] == 2
    assert row["far"]["states"] == 3
    assert sum(r["states"] for r in row["by_offset"].values()) == 5


def test_representative_override_loss_joins_contiguous_release_partitions():
    sc = replace(scenario(("A", "B"), ("A", "B"), ("A", "B"), (0.1, 0.1), (2.5, 2.5)),
                 episode_id="lite_support_a")
    fresh = evaluate(sc, "fast", "slow", 2, "freshest", trace=True)
    late = evaluate(sc, "fast", "slow", 2, "arrival", trace=True)
    for row in (fresh, late):
        for span in row["spans"]:
            span["component"] = {"fast": "Jev", "slow": "Terra", None: None}[span["component"]]
        for rec in row["accepted"]:
            rec["component"] = {"fast": "Jev", "slow": "Terra"}[rec["component"]]
    stale = late["spans"][-1]
    late["spans"][-1:] = [{**stale, "end_s": 3}, {**stale, "start_s": 3}]
    example = regression_example({"traces": {"freshest": [fresh], "arrival": [late]}}, [sc])
    assert example["duration_s"] == pytest.approx(1.5)
    assert example["fast_arrival_s"] == pytest.approx(2.1)
    assert example["old_reference"] == {"route": "A"}
    assert example["new_reference"] == {"route": "B"}


@pytest.mark.parametrize("interval", [0, -1, True, float("inf"), float("nan")])
def test_invalid_interval_rejected(interval):
    with pytest.raises(ValueError):
        evaluate(scenario(), "fast", "slow", interval)
