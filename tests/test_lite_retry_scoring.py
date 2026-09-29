"""Artificial timelines independently establish retry-excluded scoring behavior."""

from copy import deepcopy

import pytest

from streamdecisionbench.lite.retry_scoring import TIME_BASIS, normalized_episode_scores, summarize_normalized
from streamdecisionbench.lite.scoring import episode_scores


def episode():
    return {
        "episode_id": "retry_test", "task_family": "test", "scenario_id": "test",
        "tick_seconds": 2.0,
        "questions": {"route": {}, "detail": {}},
        "decision_spec": {"route_question": "route", "always": [], "branches": {"A": ["detail"], "B": []}},
        "steps": [{"t": t, "gold": {"route": route, "detail": "yes"}, "evidence": [f"public event {t}"]}
                  for t, route in enumerate(["A", "A", "B"])],
    }


def releases():
    return [{"t": t, "planned_s": 2.0 * t, "release_s": 2.0 * t} for t in range(3)]


def attempt(index, start, duration, *, ok=True):
    result = {"attempt": index, "started_s": start, "received_s": start + duration * 0.9,
              "completed_s": start + duration, "ok": ok}
    if not ok:
        result.update(error_type="APIConnectionError", retryable=True)
    return result


def record(t, *, duration=0.5, first=None, failed_duration=None, retry_gap=0.0,
           commit_lag=0.0, physical_accepted=True):
    first = 2.0 * t if first is None else first
    attempts = []
    success_start = first
    if failed_duration is not None:
        attempts.append(attempt(1, first, failed_duration, ok=False))
        success_start += failed_duration + retry_gap
    success = attempt(len(attempts) + 1, success_start, duration)
    attempts.append(success)
    check = success["completed_s"] + commit_lag
    result = {"t": t, "ok": True, "pred": episode()["steps"][t]["gold"],
              "started_s": first, "received_s": success["received_s"],
              "completed_s": success["completed_s"], "actual_recorded_s": check,
              "attempts": attempts, "accepted": physical_accepted,
              "discard_reason": None if physical_accepted else "after_horizon"}
    if physical_accepted:
        result["accepted_s"] = check
    return result


def standard_records():
    return [record(t) for t in range(3)]


def test_failure_retry_wait_and_dispatch_are_removed_but_commit_lag_remains():
    records = standard_records()
    records[0] = record(0, first=0.1, duration=0.5, failed_duration=100,
                        retry_gap=9, commit_lag=0.2, physical_accepted=False)
    saved = deepcopy(records)
    score = normalized_episode_scores(episode(), records, releases())
    first = score["normalization"]["records"][0]
    assert first["normalized_ready_s"] == pytest.approx(0.7)
    assert first["first_dispatch_lag_s"] == pytest.approx(0.1)
    assert first["excluded_dispatch_s"] == pytest.approx(0.1)
    assert first["successful_attempt_s"] == pytest.approx(0.5)
    assert first["postprocess_commit_lag_s"] == pytest.approx(0.2)
    assert first["excluded_retry_s"] == pytest.approx(109)
    # No answer for .7 seconds; the A -> B change costs another .5 seconds.
    assert score["time_accuracy"] == pytest.approx(4.8 / 6)
    assert score["untimed_decision_accuracy"] == 1
    reliability = score["retry_reliability"]
    assert reliability["failed_attempts"] == 1
    assert reliability["attempts"] == 4
    assert reliability["attempt_error_rate"] == 0.25
    assert reliability["retried_logical_rate"] == pytest.approx(1 / 3)
    assert reliability["failed_attempt_duration_s"] == 100
    assert records == saved  # Physical evidence remains untouched.


def test_dispatch_queue_from_other_requests_is_excluded_even_without_own_retry():
    records = standard_records()
    # t0 gets a worker only at 5 seconds; its own valid attempt takes .5 seconds.
    # Its queue delay must not survive on the normalized model timeline.
    records[0] = record(0, first=5, duration=0.5, physical_accepted=False)
    score = normalized_episode_scores(episode(), records, releases())
    assert score["normalization"]["records"][0]["normalized_ready_s"] == 0.5
    assert score["normalization"]["records"][0]["accepted"]
    assert score["retry_reliability"]["excluded_dispatch_s"] == 5
    assert score["retry_reliability"]["retried_logical_requests"] == 0
    assert score["max_dispatch_lag_s"] == 0
    assert score["time_accuracy"] == pytest.approx(5 / 6)


def test_reconstructed_order_replaces_physical_acceptance():
    records = [record(0, duration=3), record(1, duration=0.1, failed_duration=1), record(2)]
    # Physical: t0 arrives at 3, then t1 at 3.1. Reconstructed: t1 at 2.1
    # precedes t0 at 3, so t0 must now be discarded despite physical acceptance.
    score = normalized_episode_scores(episode(), records, releases())
    assert score["normalization"]["arrival_order"] == [1, 0, 2]
    assert score["normalization"]["records"][0]["discard_reason"] == "older_than_active"
    assert score["accepted_updates"] == 2
    assert score["error_seconds"]["no_decision"] == pytest.approx(2.1)


def test_simultaneous_normalized_arrivals_take_newest_source_first_deterministically():
    records = [record(0, duration=3), record(1, duration=1), record(2)]
    forward = normalized_episode_scores(episode(), records, releases())
    reverse = normalized_episode_scores(episode(), list(reversed(records)), releases())
    assert forward == reverse
    assert forward["normalization"]["arrival_order"] == [1, 0, 2]
    assert forward["normalization"]["records"][0]["discard_reason"] == "older_than_active"
    assert forward["normalization"]["records"][1]["accepted"]


def test_without_retries_normalized_scores_match_physical_scores():
    records = [record(t, duration=0.5 + 0.1 * t, commit_lag=0.05) for t in range(3)]
    actual = episode_scores(episode(), records, releases())
    normalized = normalized_episode_scores(episode(), records, releases())
    assert {key: normalized[key] for key in actual} == actual
    assert normalized["retry_reliability"]["attempt_error_rate"] == 0
    assert normalized["retry_reliability"]["retried_logical_rate"] == 0


def test_success_physically_after_horizon_is_still_an_untimed_answer_and_may_normalize_inside():
    records = standard_records()
    records[2] = record(2, duration=0.5, failed_duration=20, retry_gap=1, physical_accepted=False)
    score = normalized_episode_scores(episode(), records, releases())
    assert score["untimed_decision_accuracy"] == 1
    assert score["normalization"]["records"][2]["accepted"]
    assert score["normalization"]["records"][2]["normalized_ready_s"] == 4.5
    assert score["accepted_updates"] == 3


def test_normalized_delivery_at_horizon_is_not_accepted():
    records = standard_records()
    records[2] = record(2, duration=2, failed_duration=20, physical_accepted=False)
    score = normalized_episode_scores(episode(), records, releases())
    assert score["untimed_decision_accuracy"] == 1
    assert score["normalization"]["records"][2]["discard_reason"] == "after_horizon"
    assert score["time_accuracy"] == pytest.approx(3.5 / 6)


def test_final_valid_but_wrong_answer_is_scored_without_cherry_picking():
    records = standard_records()
    records[2]["pred"] = {"route": "A", "detail": "no"}
    score = normalized_episode_scores(episode(), records, releases())
    assert score["untimed_decision_accuracy"] == pytest.approx(2 / 3)
    assert score["retry_reliability"]["attempts"] == 3
    assert score["error_seconds"]["source_incorrect"] == pytest.approx(1.5)


def test_retry_after_success_is_rejected_even_if_last_prediction_would_be_correct():
    records = standard_records()
    r = records[0]
    r["attempts"].append(attempt(2, 1, 0.5))
    r.update(received_s=1.45, completed_s=1.5, actual_recorded_s=1.5)
    with pytest.raises(ValueError, match="stop after its first successful"):
        normalized_episode_scores(episode(), records, releases())


@pytest.mark.parametrize("mutation", ["missing_record", "empty_attempts", "unsuccessful_final", "logical_not_ok"])
def test_incomplete_logical_success_refuses_a_full_model_score(mutation):
    records = standard_records()
    if mutation == "missing_record":
        records.pop()
    elif mutation == "empty_attempts":
        records[-1]["attempts"] = []
    elif mutation == "unsuccessful_final":
        records[-1]["attempts"][-1]["ok"] = False
    else:
        records[-1]["ok"] = False
    with pytest.raises(ValueError):
        normalized_episode_scores(episode(), records, releases())


@pytest.mark.parametrize("mutation", ["nan", "negative_commit", "overlapping_retry", "received_before_start", "nonretryable", "wrong_sequence", "wrong_logical_start", "wrong_logical_end"])
def test_nonfinite_noncausal_and_invalid_attempt_metadata_is_rejected(mutation):
    records = standard_records()
    records[0] = record(0, failed_duration=2, retry_gap=1)
    r = records[0]
    if mutation == "nan":
        r["actual_recorded_s"] = float("nan")
    elif mutation == "negative_commit":
        r["actual_recorded_s"] = r["completed_s"] - 0.01
    elif mutation == "overlapping_retry":
        r["attempts"][-1]["started_s"] = 1
    elif mutation == "received_before_start":
        r["attempts"][-1]["received_s"] = 0
    elif mutation == "nonretryable":
        r["attempts"][0]["retryable"] = False
    elif mutation == "wrong_sequence":
        r["attempts"][-1]["attempt"] = 3
    elif mutation == "wrong_logical_start":
        r["started_s"] = 0.1
    else:
        r["completed_s"] += 0.1
    with pytest.raises(ValueError):
        normalized_episode_scores(episode(), records, releases())


def test_summary_uses_summed_attempt_denominators_and_preserves_time_basis():
    first = normalized_episode_scores(episode(), standard_records(), releases())
    retry_records = standard_records()
    retry_records[0] = record(0, failed_duration=1)
    retry_records[1] = record(1, failed_duration=1)
    second = normalized_episode_scores(episode(), retry_records, releases())
    summary = summarize_normalized([first, second])
    assert summary["time_basis"] == TIME_BASIS
    reliability = summary["retry_reliability"]
    assert reliability["logical_requests"] == 6
    assert reliability["successful_logical_requests"] == 6
    assert reliability["attempts"] == 8
    assert reliability["failed_attempts"] == 2
    assert reliability["attempt_error_rate"] == 0.25  # Not mean(0/3, 2/5).
    assert reliability["retried_logical_rate"] == pytest.approx(2 / 6)
    assert reliability["attempt_errors_by_type"] == {"APIConnectionError": 2}
    assert summary["overall"]["untimed_decision_accuracy"] == 1


def test_summary_rejects_raw_or_mixed_time_bases():
    normalized = normalized_episode_scores(episode(), standard_records(), releases())
    raw = episode_scores(episode(), standard_records(), releases())
    with pytest.raises(ValueError, match="same time basis"):
        summarize_normalized([normalized, raw])
    with pytest.raises(ValueError):
        summarize_normalized([])


def test_network_removal_defaults_to_the_primary_replay_and_never_goes_below_receipt():
    records = standard_records()
    assert normalized_episode_scores(episode(), records, releases(), network_s=0.0) == \
        normalized_episode_scores(episode(), records, releases())
    # duration 0.5, received at 0.45, commit lag 0.2: removing 0.3 s keeps receipt-to-completion and commit lag.
    lagged = [record(t, commit_lag=0.2) for t in range(3)]
    detail = normalized_episode_scores(episode(), lagged, releases(), network_s=0.3)["normalization"]["records"][0]
    assert detail["normalized_ready_s"] == pytest.approx(0.0 + 0.2 + 0.2)
    assert detail["removed_network_s"] == pytest.approx(0.3) and not detail["network_clamped"]
    clamped = normalized_episode_scores(episode(), lagged, releases(), network_s=1.0)
    assert clamped["normalization"]["records"][0]["normalized_ready_s"] == pytest.approx(0.05 + 0.2)
    assert clamped["normalization"]["network_clamped_requests"] == 3


def test_network_removal_recomputes_acceptance_against_the_horizon():
    late = standard_records()
    late[2] = record(2, duration=2.1)
    assert normalized_episode_scores(episode(), late, releases())["normalization"]["records"][2]["discard_reason"] == "after_horizon"
    rescued = normalized_episode_scores(episode(), late, releases(), network_s=0.5)
    assert rescued["normalization"]["records"][2]["accepted"] is True


@pytest.mark.parametrize("bad", [-0.1, float("nan"), float("inf"), True])
def test_invalid_network_removal_is_rejected(bad):
    with pytest.raises(ValueError, match="network_s"):
        normalized_episode_scores(episode(), standard_records(), releases(), network_s=bad)
