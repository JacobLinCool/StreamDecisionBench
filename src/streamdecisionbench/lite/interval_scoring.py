"""Integrate fixed-response replay metrics over declared environment intervals.

The original scorer still integrates correctness over physical scenario time.
This module adds an outer, normalized integral over evaluation conditions.
No request is issued and no physical recording is modified.
"""

from copy import deepcopy
import math
from statistics import mean

import numpy as np

from streamdecisionbench.lite.retry_scoring import normalized_episode_scores

PARTITION = (
    "current_correct",
    "judgment",
    "stale",
    "compound",
    "outdated_correct",
    "no_decision",
)
METRICS = ("accuracy", "segment_accuracy", "untimed", "oracle", "product", *PARTITION)


def evaluate_interval(
    run: dict, interval_s: float, *, network_s: float = 0.0
) -> list[dict]:
    """Replay on the recorded clock with proportionally scaled delays.

    Equivalent to retiming releases/horizon while preserving measured latency.
    Network removal is in measured seconds, before the equivalent clock change.
    """
    if (
        isinstance(interval_s, bool)
        or not isinstance(interval_s, (int, float))
        or not math.isfinite(interval_s)
        or interval_s <= 0
    ):
        raise ValueError("interval_s must be finite and positive")
    if (
        isinstance(network_s, bool)
        or not isinstance(network_s, (int, float))
        or not math.isfinite(network_s)
        or network_s < 0
    ):
        raise ValueError("network_s must be finite and nonnegative")
    rows = []
    for ep in run["episodes"]:
        eid = ep["episode_id"]
        factor = ep["tick_seconds"] / interval_s
        releases = run["releases"][eid]
        times = {r["t"]: r["release_s"] for r in releases}
        records = deepcopy(run["responses"][eid])
        for record in records:
            origin = times[record["t"]]
            for item in (record, *record["attempts"]):
                for key in (
                    "started_s",
                    "received_s",
                    "completed_s",
                    "actual_recorded_s",
                ):
                    if key in item:
                        item[key] = origin + factor * (item[key] - origin)
        rows.append(
            normalized_episode_scores(
                ep, records, releases, network_s=network_s * factor
            )
        )
    return rows


def _values(rows: list[dict]) -> np.ndarray:
    values = []
    for row in rows:
        part = [
            row["time_partition_seconds"][k] / row["observed_duration_s"]
            for k in PARTITION
        ]
        values.append(
            [
                row["time_accuracy"],
                row["segment_time_accuracy"],
                row["untimed_decision_accuracy"],
                row["current_source_share"],
                row["untimed_decision_accuracy"] * row["current_source_share"],
                *part,
            ]
        )
    result = np.asarray(values)
    if not np.isfinite(result).all():
        raise ValueError("nonfinite replay metric")
    return result


def _trapezoidal_average(values: np.ndarray) -> np.ndarray:
    """Normalized composite trapezoidal rule on an equally spaced axis."""
    return (values[1:-1].sum(axis=0) + (values[0] + values[-1]) / 2) / (len(values) - 1)


def integrate_intervals(
    run: dict,
    min_s: float,
    max_s: float,
    weighting: str = "log",
    *,
    network_s: float = 0.0,
    initial_subintervals: int = 128,
    max_subintervals: int = 4096,
    tolerance: float = 1e-5,
) -> dict:
    """Nested trapezoidal quadrature, refined until every scenario metric converges.

    Tolerance is an absolute score fraction (1e-5 = 0.001 percentage point).
    Successive-grid agreement is a numerical convergence diagnostic, not a
    rigorous error bound or statistical uncertainty. Nonconvergence is an error.
    """
    if any(
        isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
        for x in (min_s, max_s, tolerance)
    ):
        raise ValueError("bounds and tolerance must be finite numbers")
    if not 0 < min_s < max_s or tolerance <= 0 or weighting not in ("linear", "log"):
        raise ValueError(
            "require 0 < min_s < max_s, positive tolerance, and linear or log weighting"
        )
    if (
        any(
            isinstance(n, bool) or not isinstance(n, int) or n < 2
            for n in (initial_subintervals, max_subintervals)
        )
        or max_subintervals < 2 * initial_subintervals
    ):
        raise ValueError("quadrature needs at least one grid doubling")
    start, end = (
        (math.log(min_s), math.log(max_s)) if weighting == "log" else (min_s, max_s)
    )
    n = initial_subintervals

    def sample(t):
        interval = math.exp(t) if weighting == "log" else float(t)
        return _values(evaluate_interval(run, interval, network_s=network_s))

    axis = np.linspace(start, end, n + 1)
    values = np.asarray([sample(t) for t in axis])
    previous = _trapezoidal_average(values)
    while 2 * n <= max_subintervals:
        refined = np.empty((2 * n + 1, *values.shape[1:]))
        refined[::2] = values
        refined[1::2] = [sample(t) for t in (axis[:-1] + axis[1:]) / 2]
        n *= 2
        axis = np.linspace(start, end, n + 1)
        values = refined
        integrated = _trapezoidal_average(values)
        change = float(np.max(np.abs(integrated - previous)))
        if change <= tolerance:
            break
        previous = integrated
    else:
        raise ValueError(
            f"interval quadrature did not converge at {max_subintervals} subintervals"
        )

    rows = [
        {
            "episode_id": ep["episode_id"],
            "task_family": ep["task_family"],
            **dict(zip(METRICS, map(float, val))),
        }
        for ep, val in zip(run["episodes"], integrated, strict=True)
    ]
    families = sorted({r["task_family"] for r in rows})
    by_family = {
        f: {k: mean(r[k] for r in rows if r["task_family"] == f) for k in METRICS}
        for f in families
    }
    overall = {k: mean(row[k] for row in by_family.values()) for k in METRICS}
    for row in [*rows, *by_family.values(), overall]:
        if not math.isclose(sum(row[k] for k in PARTITION), 1, abs_tol=1e-10):
            raise ValueError("integrated partition must sum to one")
        if not math.isclose(
            row["accuracy"],
            row["current_correct"] + row["outdated_correct"],
            abs_tol=1e-10,
        ):
            raise ValueError("integrated correctness identity failed")
    return {
        "min_s": min_s,
        "max_s": max_s,
        "weighting": weighting,
        "network_s": network_s,
        "per_episode": rows,
        "by_family": by_family,
        "overall": overall,
        "quadrature": {
            "subintervals": n,
            "max_successive_change": change,
            "tolerance": tolerance,
        },
        "curve": {
            "intervals_s": (np.exp(axis) if weighting == "log" else axis).tolist(),
            "by_family": {
                f: np.mean(
                    values[
                        :,
                        [
                            i
                            for i, ep in enumerate(run["episodes"])
                            if ep["task_family"] == f
                        ],
                        0,
                    ],
                    axis=1,
                ).tolist()
                for f in families
            },
        },
    }
