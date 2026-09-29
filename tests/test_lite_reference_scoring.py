"""Reference cadence changes the environment clock, never measured service time."""

from copy import deepcopy

import pytest

from streamdecisionbench.lite.reference_scoring import family_mean, retime, summarize_reference
from test_lite_retry_scoring import episode, releases, record


def frozen():
    return {"episodes": [episode()], "releases": {"retry_test": releases()},
            "responses": {"retry_test": [record(t) for t in range(3)]}}


def test_new_interval_preserves_latency_and_raw_input():
    run = frozen()
    run["responses"]["retry_test"][0] = record(0, failed_duration=10, retry_gap=1, commit_lag=0.2)
    before = deepcopy(run)
    replay = retime(run, {"test": 1.0})
    row = replay["scores"]["per_episode"][0]
    # At 1 s cadence: no decision for .7 s; A -> B at 2 costs another .5 s.
    assert row["time_accuracy"] == pytest.approx(1.8 / 3)
    assert row["normalization"]["records"][2]["normalized_ready_s"] == pytest.approx(2.5)
    assert row["retry_reliability"]["excluded_retry_s"] == 11
    assert row["untimed_decision_accuracy"] == 1
    assert replay["episodes"][0]["steps"] == before["episodes"][0]["steps"]
    assert run == before


def test_new_horizon_and_arrival_order_are_recomputed():
    run = frozen()
    run["responses"]["retry_test"] = [record(0, duration=1.5), record(1, duration=0.1), record(2, duration=1.0)]
    replay = retime(run, {"test": 1.0})
    rows = replay["scores"]["per_episode"][0]["normalization"]["records"]
    assert rows[0]["discard_reason"] == "older_than_active"
    assert rows[2]["discard_reason"] == "after_horizon"


def test_equal_family_weights_do_not_pool_seconds_or_episode_counts():
    first = retime(frozen(), {"test": 1.0})["scores"]["per_episode"][0]
    other = deepcopy(first)
    other.update(task_family="other", time_accuracy=0.0)
    rows = [first, deepcopy(first), other]
    assert summarize_reference(rows)["overall"]["time_accuracy"] == pytest.approx(first["time_accuracy"] / 2)
    assert family_mean(rows, lambda r: r["time_accuracy"]) != pytest.approx(first["time_accuracy"] * 2 / 3)


@pytest.mark.parametrize("intervals", [{}, {"wrong": 1}, {"test": 0}, {"test": -1},
                                        {"test": float("nan")}, {"test": True}])
def test_invalid_or_incomplete_interval_map_is_rejected(intervals):
    with pytest.raises(ValueError):
        retime(frozen(), intervals)
