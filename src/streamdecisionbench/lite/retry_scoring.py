"""Score a replay that excludes transport failures and retry waits.

This is a reconstructed delivery timeline, not the physical wall-clock trace.
Each logical request contributes its final successful attempt duration and its
actual postprocessing/commit-check lag, anchored at evidence release. Predictions,
reference releases and the horizon are unchanged. Acceptance is recomputed on
the reconstructed timeline without consulting reference answers.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import math
from typing import Any

from streamdecisionbench.lite.scoring import episode_scores, summarize


TIME_BASIS = "release_anchored_successful_attempt_replay"
PROTOCOL = "retry_excluded_successful_attempt_v1"


def _time(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite nonnegative timestamp")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{label} must be a finite nonnegative timestamp")
    return float(value)


def _prepare_record(record: dict, release_s: float, network_s: float = 0.0) -> tuple[dict, dict]:
    """Validate one completed logical request and reconstruct its timestamps.

    ``network_s`` removes an estimated network delay from the time before the
    response was received, never more than that time.
    """
    attempts = record.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise ValueError("every logical request needs a successful attempt and its attempt log")
    if record.get("ok") is not True or attempts[-1].get("ok") is not True:
        raise ValueError("cannot score a complete model run without success for every logical request")
    previous_end = release_s
    for index, attempt in enumerate(attempts, 1):
        if attempt.get("attempt") != index or isinstance(attempt.get("attempt"), bool):
            raise ValueError("attempt identifiers must be consecutive from one")
        if not isinstance(attempt.get("ok"), bool):
            raise ValueError("attempt ok must be boolean")
        start = _time(attempt.get("started_s"), "attempt started_s")
        end = _time(attempt.get("completed_s"), "attempt completed_s")
        received = _time(attempt.get("received_s", end), "attempt received_s")
        if not previous_end <= start <= received <= end:
            raise ValueError("attempt timestamps violate release/retry causality")
        if index < len(attempts):
            if attempt["ok"]:
                raise ValueError("a logical request must stop after its first successful response")
            if attempt.get("retryable") is not True:
                raise ValueError("only retryable failed attempts may precede success")
            if not isinstance(attempt.get("error_type"), str) or not attempt["error_type"]:
                raise ValueError("failed attempts require a nonempty error_type")
        previous_end = end

    first, success = attempts[0], attempts[-1]
    first_start = _time(record.get("started_s"), "record started_s")
    completed = _time(record.get("completed_s"), "record completed_s")
    actual_ready = _time(record.get("actual_recorded_s"), "record actual_recorded_s")
    if first_start != first["started_s"] or completed != success["completed_s"]:
        raise ValueError("logical timestamps must match first dispatch and final successful completion")
    if "received_s" in record:
        received = _time(record["received_s"], "record received_s")
        if not success["started_s"] <= received <= completed:
            raise ValueError("logical received_s must belong to the final successful attempt")
        if "received_s" in success and received != success["received_s"]:
            raise ValueError("logical received_s must match the successful attempt")
    if actual_ready < completed:
        raise ValueError("actual commit check must follow successful completion")

    received_offset = success.get("received_s", success["completed_s"]) - success["started_s"]
    removed_network_s = min(network_s, received_offset)
    successful_attempt_s = completed - success["started_s"] - removed_network_s
    commit_lag_s = actual_ready - completed
    normalized_completed_s = release_s + successful_attempt_s
    ready_s = normalized_completed_s + commit_lag_s
    if not math.isfinite(ready_s):
        raise ValueError("normalized delivery timestamp must be finite")
    normalized = deepcopy(record)
    normalized.update(started_s=release_s, completed_s=normalized_completed_s,
                      accepted=False, discard_reason=None, normalized_ready_s=ready_s)
    normalized.pop("accepted_s", None)
    if "received_s" in success:
        normalized["received_s"] = release_s + received_offset - removed_network_s
    else:
        # The receive timestamp is optional; do not leave a physical timestamp in
        # the reconstructed record when its final attempt did not record one.
        normalized.pop("received_s", None)
    details = {
        "t": record["t"], "first_started_s": first_start,
        "first_dispatch_lag_s": first_start - release_s,
        "excluded_dispatch_s": first_start - release_s,
        "successful_attempt_s": successful_attempt_s,
        "postprocess_commit_lag_s": commit_lag_s,
        "actual_recorded_s": actual_ready,
        "normalized_ready_s": ready_s,
        "excluded_retry_s": success["started_s"] - first_start,
        "attempt_count": len(attempts),
    }
    if network_s:
        details.update(removed_network_s=removed_network_s, network_clamped=removed_network_s < network_s)
    return normalized, details


def normalized_episode_scores(episode: dict, records: list[dict], releases: list[dict], *,
                              network_s: float = 0.0) -> dict:
    """Return effective-decision scores and separately counted retry reliability.

    All logical requests must have exactly one final successful response. A
    response can be incorrect relative to gold and still be a successful API
    response; no correctness-dependent selection is performed. Physical
    ``accepted`` flags are ignored and may differ from reconstructed acceptance.
    Simultaneous arrivals use descending source index so the newest source wins.
    A positive ``network_s`` replays every response with that estimated network
    delay removed (a secondary, network-removed view; see PROTOCOL.md).
    """
    if isinstance(network_s, bool) or not isinstance(network_s, (int, float)) \
            or not math.isfinite(network_s) or network_s < 0:
        raise ValueError("network_s must be a finite nonnegative number")
    n = len(episode["steps"])
    if len(releases) != n or [r["t"] for r in releases] != list(range(n)):
        raise ValueError("scoring requires every scheduled release")
    by_t = {r["t"]: r for r in records}
    if len(by_t) != len(records) or set(by_t) != set(range(n)):
        raise ValueError("scoring requires exactly one record per released state")
    times = [_time(r["release_s"], "release_s") for r in releases]
    horizon = n * episode["tick_seconds"]
    if not math.isfinite(horizon) or horizon <= 0:
        raise ValueError("episode horizon must be finite and positive")
    if times[-1] >= horizon or any(a >= b for a, b in zip(times, times[1:])):
        raise ValueError("invalid evidence release times")
    for release, release_s in zip(releases, times):
        planned_s = _time(release["planned_s"], "planned_s")
        if planned_s > release_s:
            raise ValueError("evidence must not be released before its scheduled time")

    normalized, details = [], []
    for t in range(n):
        record, metadata = _prepare_record(by_t[t], times[t], network_s)
        normalized.append(record)
        details.append(metadata)
    arrival_order = sorted(normalized, key=lambda r: (r["normalized_ready_s"], -r["t"]))
    latest = -1
    for record in arrival_order:
        ready = record["normalized_ready_s"]
        if ready >= horizon:
            record["discard_reason"] = "after_horizon"
        elif record["t"] <= latest:
            record["discard_reason"] = "older_than_active"
        else:
            latest = record["t"]
            record.update(accepted=True, accepted_s=ready)
        details[record["t"]].update(accepted=record["accepted"], discard_reason=record["discard_reason"])

    score = episode_scores(episode, normalized, releases)
    attempts = [attempt for record in records for attempt in record["attempts"]]
    failed = [attempt for attempt in attempts if not attempt["ok"]]
    retried = sum(len(record["attempts"]) > 1 for record in records)
    score.update(
        time_basis=TIME_BASIS,
        retry_reliability={
            "logical_requests": n,
            "successful_logical_requests": n,
            "attempts": len(attempts),
            "failed_attempts": len(failed),
            "attempt_error_rate": len(failed) / len(attempts),
            "attempt_error_rate_denominator": "all physical attempts, including final successes",
            "retried_logical_requests": retried,
            "retried_logical_rate": retried / n,
            "retried_logical_rate_denominator": "all released logical requests",
            "attempt_errors_by_type": dict(Counter(attempt["error_type"] for attempt in failed)),
            "failed_attempt_duration_s": sum(a["completed_s"] - a["started_s"] for a in failed),
            "excluded_retry_s": sum(detail["excluded_retry_s"] for detail in details),
        },
        normalization={
            "definition": "actual evidence release + successful attempt duration + actual postprocess/commit-check lag",
            "tie_break": "newest source index first at an exactly equal reconstructed arrival time",
            "acceptance": "recomputed against source order and original horizon; physical acceptance ignored",
            "latency_basis": "successful attempt completion minus its start; excludes dispatch queue, failed attempts and retry waits",
            "arrival_order": [r["t"] for r in arrival_order],
            "records": details,
        },
    )
    score["retry_reliability"]["excluded_dispatch_s"] = sum(detail["excluded_dispatch_s"] for detail in details)
    if network_s:
        score["normalization"].update(removed_network_s=network_s,
                                      network_clamped_requests=sum(d["network_clamped"] for d in details))
    return score


def summarize_normalized(results: list[dict]) -> dict:
    """Aggregate normalized scores with attempt- and request-level denominators.

    Rates are formed from summed counters, not from the mean of episode rates.
    Raw physical scores belong in a separate artifact and are not accepted here.
    """
    if not results or any(row.get("time_basis") != TIME_BASIS for row in results):
        raise ValueError("summarize_normalized requires nonempty normalized results of the same time basis")
    aggregate = summarize(results)
    reliability = [row["retry_reliability"] for row in results]
    totals = {key: sum(row[key] for row in reliability) for key in (
        "logical_requests", "successful_logical_requests", "attempts", "failed_attempts",
        "retried_logical_requests", "failed_attempt_duration_s", "excluded_retry_s", "excluded_dispatch_s",
    )}
    errors: Counter = Counter()
    for row in reliability:
        errors.update(row["attempt_errors_by_type"])
    totals.update(
        attempt_error_rate=totals["failed_attempts"] / totals["attempts"],
        attempt_error_rate_denominator="all physical attempts, including final successes",
        retried_logical_rate=totals["retried_logical_requests"] / totals["logical_requests"],
        retried_logical_rate_denominator="all released logical requests",
        attempt_errors_by_type=dict(errors),
    )
    aggregate.update(
        time_basis=TIME_BASIS,
        retry_reliability=totals,
        interpretation=("One run per independent scenario; no repeated-run or population confidence claim. "
                        "Untimed metrics use final successful responses. Time metrics replay each successful "
                        "attempt at its evidence release, preserving its duration and commit-check lag while "
                        "excluding dispatch queues, failed attempts and retry waits; these are not physical "
                        "wall-clock deployment scores."),
    )
    return aggregate
