"""Replay frozen responses at declared evaluation intervals.

The environment clock changes; successful-attempt latency in seconds does not.
These are counterfactual scores, not measurements of service at a new request rate.
The input run and all physical records remain untouched.
"""

from __future__ import annotations

from copy import deepcopy
import math
from statistics import mean

from streamdecisionbench.lite.retry_scoring import normalized_episode_scores, summarize_normalized
from streamdecisionbench.lite.scoring import SCORE_KEYS


def family_mean(rows: list[dict], value) -> float:
    """Equal episode weights within families, equal weights across families."""
    families = sorted({row["task_family"] for row in rows})
    if not families:
        raise ValueError("family mean requires at least one episode")
    return mean(mean(value(row) for row in rows if row["task_family"] == family) for family in families)


def summarize_reference(rows: list[dict]) -> dict:
    summary = summarize_normalized(rows)
    summary["overall"] = {key: family_mean(rows, lambda row: row[key]) for key in SCORE_KEYS}
    summary["aggregation"] = "equal episodes within family, then equal families"
    return summary


def retime(verified: dict, intervals: dict[str, float]) -> dict:
    """Copy a verified run onto new release clocks, preserving all request delays.

    Scale release and planned timestamps by new/recorded interval. Shift request
    and attempt timestamps by the change in their own release. The retry scorer
    then removes dispatch/retry waits and recomputes acceptance at the new horizon.
    Tick-valued evidence and policy thresholds remain unchanged.
    """
    families = {episode["task_family"] for episode in verified["episodes"]}
    if set(intervals) != families:
        raise ValueError("evaluation intervals must name exactly the run's families")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0
           for v in intervals.values()):
        raise ValueError("evaluation intervals must be finite positive seconds")
    result = deepcopy(verified)
    for episode in result["episodes"]:
        eid = episode["episode_id"]
        interval = intervals[episode["task_family"]]
        scale = interval / episode["tick_seconds"]
        episode["tick_seconds"] = interval
        shifts = {}
        for release in result["releases"][eid]:
            old = release["release_s"]
            release["release_s"] = old * scale
            release["planned_s"] *= scale
            shifts[release["t"]] = release["release_s"] - old
        for record in result["responses"][eid]:
            shift = shifts[record["t"]]
            if "release_s" in record:
                record["release_s"] += shift
            for item in [record, *record["attempts"]]:
                for key in ("started_s", "received_s", "completed_s", "actual_recorded_s", "accepted_s"):
                    if key in item:
                        item[key] += shift
    result["scores"] = score_reference(result)
    result["evaluation_intervals_s"] = dict(intervals)
    return result


def score_reference(run: dict, *, network_s: float = 0.0) -> dict:
    return summarize_reference([
        normalized_episode_scores(episode, run["responses"][episode["episode_id"]],
                                  run["releases"][episode["episode_id"]], network_s=network_s)
        for episode in run["episodes"]
    ])

