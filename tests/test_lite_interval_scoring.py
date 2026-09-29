"""AUC checked against closed-form timelines and an independent clock transform."""
from copy import deepcopy
import math

import pytest

from streamdecisionbench.lite.interval_scoring import (
    evaluate_interval,
    integrate_intervals,
)
from streamdecisionbench.lite.reference_scoring import retime, score_reference
from test_lite_reference_scoring import frozen
from test_lite_retry_scoring import record


@pytest.mark.parametrize("weighting", ["log", "linear"])
def test_perfect_answers_constant_delay_have_known_area(weighting):
    # A,A,B with .5 s delay loses .5 s at the start and at A->B:
    # A(delta) = 1 - 1/(3 delta), throughout [1,5].
    result = integrate_intervals(frozen(), 1, 5, weighting)
    penalty = (
        (1 - 1 / 5) / (3 * math.log(5)) if weighting == "log" else math.log(5) / 12
    )
    assert result["overall"]["accuracy"] == pytest.approx(1 - penalty, abs=1e-5)
    assert result["overall"]["oracle"] == pytest.approx(1 - penalty, abs=1e-5)
    assert result["overall"]["untimed"] == 1


@pytest.mark.parametrize("interval", [0.5, 1, 2, 5])
@pytest.mark.parametrize("network", [0, 0.2, 3])
def test_scaled_delay_matches_retimed_clock_including_reordering_and_clamping(
    interval, network
):
    run = frozen()
    run["responses"]["retry_test"] = [
        record(0, duration=2),
        record(1, duration=0.1),
        record(2, duration=1),
    ]
    original = deepcopy(run)
    actual = evaluate_interval(run, interval, network_s=network)[0]
    expected = score_reference(retime(run, {"test": interval}), network_s=network)[
        "per_episode"
    ][0]
    for key in ("time_accuracy", "segment_time_accuracy", "current_source_share"):
        assert actual[key] == pytest.approx(expected[key], abs=1e-12)
    assert actual["discarded_updates"] == expected["discarded_updates"]
    assert run == original


def test_aggregation_weights_families_equally_with_unequal_scenario_counts():
    run = frozen()
    for eid, family, wrong in [("same", "test", False), ("other", "second", True)]:
        ep = deepcopy(run["episodes"][0])
        ep.update(episode_id=eid, task_family=family)
        run["episodes"].append(ep)
        run["releases"][eid] = deepcopy(run["releases"]["retry_test"])
        run["responses"][eid] = [record(t, duration=0) for t in range(3)]
        if wrong:
            for rec in run["responses"][eid]:
                rec["pred"] = {"route": "B" if rec["t"] < 2 else "A", "detail": "yes"}
    result = integrate_intervals(run, 1, 5)
    assert result["overall"]["accuracy"] == pytest.approx(
        sum(r["accuracy"] for r in result["by_family"].values()) / 2
    )
    assert result["overall"]["accuracy"] != pytest.approx(
        sum(r["accuracy"] for r in result["per_episode"]) / 3
    )


@pytest.mark.parametrize(
    "lo,hi,weight",
    [
        (0, 5, "log"),
        (2, 1, "log"),
        (1, 1, "linear"),
        (1, 5, "sqrt"),
        (1, float("inf"), "log"),
    ],
)
def test_bad_domains_rejected(lo, hi, weight):
    with pytest.raises(ValueError):
        integrate_intervals(frozen(), lo, hi, weight)


def test_nonconvergence_is_not_silently_accepted():
    with pytest.raises(ValueError, match="did not converge"):
        integrate_intervals(
            frozen(), 1, 5, initial_subintervals=4, max_subintervals=8, tolerance=1e-12
        )
