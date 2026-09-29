"""Exact correctness of the delivered application decision over wall-clock time."""

from __future__ import annotations

from collections import Counter, defaultdict
import math
from statistics import mean

import numpy as np

from streamdecisionbench.lite.core import compose


def episode_scores(episode: dict, records: list[dict], releases: list[dict]) -> dict:
    steps, spec = episode["steps"], episode["decision_spec"]
    n, tick = len(steps), episode["tick_seconds"]
    horizon = n * tick
    if len(releases) != n or [r["t"] for r in releases] != list(range(n)):
        raise ValueError("scoring requires every scheduled release")
    times = [r["release_s"] for r in releases]
    if (not all(math.isfinite(t) for t in times) or times != sorted(times)
            or times[0] < 0 or times[-1] >= horizon
            or any(a >= b for a, b in zip(times, times[1:]))):
        raise ValueError("invalid evidence release times")
    by_t = {r["t"]: r for r in records}
    if len(by_t) != len(records) or set(by_t) != set(range(n)):
        raise ValueError("scoring requires exactly one record per released state")
    for t, r in by_t.items():
        timestamps = [times[t], r["started_s"]]
        if "received_s" in r:
            timestamps.append(r["received_s"])
        timestamps.append(r["completed_s"])
        if r["accepted"]:
            if not r["ok"]:
                raise ValueError("failed response cannot be accepted")
            timestamps.append(r["accepted_s"])
        if not all(math.isfinite(x) for x in timestamps) or timestamps != sorted(timestamps):
            raise ValueError("response timestamps violate causality")
    gold = [compose(spec, s["gold"]) for s in steps]
    untimed = [bool(by_t[t]["ok"] and compose(spec, by_t[t]["pred"]) == gold[t]) for t in range(n)]
    raw_exact = [bool(by_t[t]["ok"] and by_t[t]["pred"] == steps[t]["gold"]) for t in range(n)]
    boundaries = [0] + [t for t in range(1, n) if gold[t] != gold[t - 1]] + [n]
    changes = sorted((r["accepted_s"], r["t"], compose(spec, r["pred"]))
                     for r in records if r["accepted"])
    if any(not 0 <= a < horizon for a, _, _ in changes):
        raise ValueError("accepted decision outside horizon")
    if any(t1 >= t2 for (_, t1, _), (_, t2, _) in zip(changes, changes[1:])):
        raise ValueError("accepted decisions must have increasing source indices")
    points = sorted({0.0, horizon, *times, *(c[0] for c in changes)})
    correct_s = [0.0] * n
    kinds = {"no_decision": 0.0, "source_correct": 0.0, "source_incorrect": 0.0}
    # Every observed instant by two conditions of the decision in force: is its source state still
    # current (same reference decision as now; timing), and was it correct for its source (judgment)?
    partition = {"current_correct": 0.0, "judgment": 0.0, "stale": 0.0, "compound": 0.0,
                 "outdated_correct": 0.0, "no_decision": 0.0}
    intervals = []
    gi, ci, current = -1, 0, None
    for a, b in zip(points, points[1:]):
        while gi + 1 < n and times[gi + 1] <= a:
            gi += 1
        while ci < len(changes) and changes[ci][0] <= a:
            current = changes[ci]
            ci += 1
        if gi < 0:  # The episode becomes observable at its first release.
            continue
        correct = current is not None and current[2] == gold[gi]
        if current is None:
            partition["no_decision"] += b - a
        elif gold[current[1]] == gold[gi]:
            partition["current_correct" if correct else "judgment"] += b - a
        elif current[2] == gold[current[1]]:
            partition["stale"] += b - a
        else:
            partition["outdated_correct" if correct else "compound"] += b - a
        if correct:
            correct_s[gi] += b - a
            kind = "correct"
        else:
            kind = "no_decision" if current is None else (
                "source_correct" if current[2] == gold[current[1]] else "source_incorrect")
            kinds[kind] += b - a
        intervals.append({"start_s": a, "end_s": b, "reference_t": gi,
                          "source_t": None if current is None else current[1], "kind": kind})
    durations = [b - a for a, b in zip(times, [*times[1:], horizon])]
    observed_horizon = horizon - times[0]
    segment_scores = [sum(correct_s[a:b]) / sum(durations[a:b]) for a, b in zip(boundaries, boundaries[1:])]
    per_question = {}
    for key in episode["questions"]:
        relevant = [t for t in range(n) if key in gold[t]]
        per_question[key] = {
            "all_states_accuracy": mean(bool(by_t[t]["ok"] and by_t[t]["pred"][key] == steps[t]["gold"][key]) for t in range(n)),
            "active_states": len(relevant),
            "active_accuracy": mean(bool(by_t[t]["ok"] and by_t[t]["pred"][key] == steps[t]["gold"][key]) for t in relevant) if relevant else None,
        }
    mistakes = []
    for t in range(n):
        if untimed[t]:
            continue
        r = by_t[t]
        mistakes.append({"t": t, "reference_decision": gold[t],
                         "predicted_decision": compose(spec, r["pred"]) if r["ok"] else None,
                         "wrong_active_questions": [q for q in gold[t] if not r["ok"] or r["pred"][q] != steps[t]["gold"][q]],
                         "reference_evidence": steps[t]["evidence"]})
    latencies = [r["completed_s"] - r["started_s"] for r in records]
    result = {
        "episode_id": episode["episode_id"], "task_family": episode["task_family"],
        "scenario_id": episode["scenario_id"], "states": n, "questions": len(episode["questions"]),
        "reference_transitions": len(boundaries) - 2,
        "untimed_decision_accuracy": mean(untimed),
        "untimed_segment_accuracy": mean(mean(untimed[a:b]) for a, b in zip(boundaries, boundaries[1:])),
        "all_questions_exact_accuracy": mean(raw_exact),
        "inactive_only_error_states": sum(u and not r for u, r in zip(untimed, raw_exact)),
        "time_accuracy": sum(correct_s) / observed_horizon,
        "segment_time_accuracy": mean(segment_scores),
        "observed_duration_s": observed_horizon,
        "error_seconds": kinds,
        "time_partition_seconds": partition,
        # Share of observed time whose decision in force answered a state with the current reference
        # decision; equals the in-force accuracy of reference answers at the same arrival times.
        "current_source_share": (partition["current_correct"] + partition["judgment"]) / observed_horizon,
        "latency_s_p50": float(np.percentile(latencies, 50)),
        "latency_s_p95": float(np.percentile(latencies, 95)),
        "failed_requests": sum(not r["ok"] for r in records),
        "accepted_updates": len(changes),
        "discarded_updates": dict(Counter(r["discard_reason"] for r in records if r["ok"] and not r["accepted"])),
        "max_release_lag_s": max(r["release_s"] - r["planned_s"] for r in releases),
        "max_dispatch_lag_s": max(r["started_s"] - times[r["t"]] for r in records),
        "per_question": per_question, "mistakes": mistakes, "intervals": intervals,
    }
    if abs(sum(correct_s) + sum(kinds.values()) - observed_horizon) > 1e-7:
        raise AssertionError("duration partition does not cover observation horizon")
    if (abs(sum(partition.values()) - observed_horizon) > 1e-7
            or abs(partition["stale"] - kinds["source_correct"]) > 1e-7
            or abs(partition["judgment"] + partition["compound"] - kinds["source_incorrect"]) > 1e-7
            or abs(partition["current_correct"] + partition["outdated_correct"] - sum(correct_s)) > 1e-7):
        raise AssertionError("timing-by-judgment partition disagrees with the error classes")
    return result


SCORE_KEYS = ("untimed_decision_accuracy", "untimed_segment_accuracy", "all_questions_exact_accuracy",
              "time_accuracy", "segment_time_accuracy")


def summarize(results: list[dict]) -> dict:
    families = defaultdict(list)
    for r in results:
        families[r["task_family"]].append(r)
    average = lambda rows: {k: mean(r[k] for r in rows) for k in SCORE_KEYS}
    return {
        "episodes": len(results), "states": sum(r["states"] for r in results),
        "overall": average(results),
        "by_family": {f: {"episodes": len(rows), **average(rows)} for f, rows in families.items()},
        "failed_requests": sum(r["failed_requests"] for r in results),
        "inactive_only_error_states": sum(r["inactive_only_error_states"] for r in results),
        "per_episode": results,
        "interpretation": "One run per independent scenario; no repeated-run or population confidence claim. Untimed metrics use the same responses, disregarding delivery time.",
    }
