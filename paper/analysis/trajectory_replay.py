"""Exact replay of two independently recorded components under explicit arbitration.

Acceptance sees only source indices, component identity and arrival times. The
reference is consulted after arbitration, exclusively to evaluate the held path.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
import math
from statistics import mean

from streamdecisionbench.lite.core import compose

PARTITION = (
    "current_correct", "judgment", "stale", "compound",
    "outdated_correct", "no_decision",
)
METRICS = ("accuracy", "oracle", "terminal_product", "slow_share", *PARTITION)
POLICIES = ("freshest", "lag_one", "arrival")


@dataclass(frozen=True)
class Component:
    predictions: tuple[dict, ...]
    delays_s: tuple[float, ...]


@dataclass(frozen=True)
class Scenario:
    episode_id: str
    family: str
    tick_s: float
    releases_s: tuple[float, ...]
    gold: tuple[dict, ...]
    components: dict[str, Component]


def prepare(runs: dict[str, dict]) -> list[Scenario]:
    """Require the same frozen episodes, releases and complete successful logs."""
    first = next(iter(runs.values()))
    scenarios = []
    for run in runs.values():
        if run["episodes"] != first["episodes"]:
            raise ValueError("composition requires identical frozen episodes")
    for ep in first["episodes"]:
        eid = ep["episode_id"]
        releases = tuple(r["release_s"] for r in first["releases"][eid])
        components = {}
        for name, run in runs.items():
            row = next(r for r in run["scores"]["per_episode"] if r["episode_id"] == eid)
            own_times = {r["t"]: r["release_s"] for r in run["releases"][eid]}
            delays = {r["t"]: r["successful_attempt_s"] + r["postprocess_commit_lag_s"]
                      for r in row["normalization"]["records"]}
            predictions = {r["t"]: compose(ep["decision_spec"], r["pred"])
                           for r in run["responses"][eid]}
            n = len(ep["steps"])
            if set(own_times) != set(range(n)) or set(predictions) != set(range(n)):
                raise ValueError("composition requires complete state coverage")
            if any(not math.isfinite(d) or d < 0 for d in delays.values()):
                raise ValueError("invalid normalized delay")
            components[name] = Component(
                tuple(predictions[t] for t in range(n)),
                tuple(delays[t] for t in range(n)),
            )
        # Common nominal releases avoid importing different client scheduling
        # jitter into a joint application. This is a declared counterfactual.
        scenarios.append(Scenario(
            eid, ep["task_family"], ep["tick_seconds"],
            tuple(t * ep["tick_seconds"] for t in range(len(releases))),
            tuple(compose(ep["decision_spec"], s["gold"]) for s in ep["steps"]),
            components,
        ))
    return scenarios


def arbitrate(events: list[tuple[float, int, int, dict]], horizon: float,
              policy: str) -> tuple[list[tuple[float, int, int, dict]], Counter]:
    """0 = fast, 1 = slow. Slow wins source ties; arrivals at H are excluded.

    Each component's arrivals must advance its own high-water source index,
    including responses rejected by cross-component arbitration. Fast output
    never regresses the active source; slow output may regress it by 0, 1 or
    arbitrarily many ticks, for freshest, lag_one and arrival respectively.
    At simultaneous arrivals, newest source is processed first, then slow.
    """
    if policy not in POLICIES:
        raise ValueError(f"unknown arbitration policy: {policy}")
    lag = {"freshest": 0, "lag_one": 1, "arrival": math.inf}[policy]
    active_t, active_component = -1, -1
    seen = [-1, -1]
    accepted, counts = [], Counter()
    for event in sorted(events, key=lambda r: (r[0], -r[1], -r[2])):
        ready, t, component, _ = event
        if ready >= horizon:
            counts["after_horizon"] += 1
            continue
        if t <= seen[component]:
            counts["older_within_component"] += 1
            continue
        seen[component] = t
        if component == 0 and (t < active_t or (t == active_t and active_component == 1)):
            counts["fast_not_newer"] += 1
            continue
        if component == 1 and t < active_t - lag:
            counts["slow_exceeds_lag"] += 1
            continue
        counts["source_regressions"] += t < active_t
        counts["slow_accepted" if component else "fast_accepted"] += 1
        if component == 1 and t == active_t and active_component == 0:
            counts["same_state_corrections"] += 1
        active_t, active_component = t, component
        accepted.append(event)
    return accepted, counts


def evaluate(scenario: Scenario, fast: str, slow: str | None, interval_s: float,
             policy: str = "freshest", *, trace: bool = False) -> dict:
    """Integrate the decision in force at all release/accepted-arrival boundaries."""
    if isinstance(interval_s, bool) or not math.isfinite(interval_s) or interval_s <= 0:
        raise ValueError("interval must be finite and positive")
    times = [r * interval_s / scenario.tick_s for r in scenario.releases_s]
    horizon = len(scenario.gold) * interval_s
    events = []
    for component, name in enumerate([fast] if slow is None else [fast, slow]):
        data = scenario.components[name]
        events.extend((times[t] + delay, t, component, data.predictions[t])
                      for t, delay in enumerate(data.delays_s))
    accepted, counts = arbitrate(events, horizon, policy)
    points = sorted({times[0], horizon, *times, *(r[0] for r in accepted)})
    partition = dict.fromkeys(PARTITION, 0.0)
    slow_s, cursor, current = 0.0, 0, None
    spans = []
    for start, end in zip(points, points[1:]):
        while cursor < len(accepted) and accepted[cursor][0] <= start:
            current = accepted[cursor]
            cursor += 1
        reference_t = bisect_right(times, start) - 1
        reference = scenario.gold[reference_t]
        if current is None:
            kind = "no_decision"
        else:
            _, source, component, pred = current
            if scenario.gold[source] == reference:
                kind = "current_correct" if pred == reference else "judgment"
            elif pred == scenario.gold[source]:
                kind = "stale"
            else:
                kind = "outdated_correct" if pred == reference else "compound"
            slow_s += (end - start) * (component == 1)
        partition[kind] += end - start
        if trace:
            spans.append({
                "start_s": start, "end_s": end, "reference_t": reference_t,
                "source_t": None if current is None else current[1],
                "component": None if current is None else (slow if current[2] else fast),
                "kind": kind,
            })
    duration = horizon - times[0]
    part = {k: v / duration for k, v in partition.items()}
    if not math.isclose(sum(part.values()), 1.0, abs_tol=1e-12):
        raise AssertionError("trajectory partition does not cover the horizon")
    oracle = part["current_correct"] + part["judgment"]
    terminal = scenario.components[fast if slow is None else slow]
    untimed = mean(p == g for p, g in zip(terminal.predictions, scenario.gold, strict=True))
    result = {
        "episode_id": scenario.episode_id, "task_family": scenario.family,
        "accuracy": part["current_correct"] + part["outdated_correct"],
        "oracle": oracle, "terminal_untimed": untimed,
        "terminal_product": untimed * oracle, "slow_share": slow_s / duration,
        **part, "counts": dict(counts),
    }
    if trace:
        result["spans"] = spans
        result["accepted"] = [
            {"arrival_s": a, "source_t": t, "component": slow if c else fast}
            for a, t, c, _ in accepted
        ]
    return result


def aggregate(rows: list[dict]) -> dict:
    families = sorted({r["task_family"] for r in rows})
    by_family = {f: {k: mean(r[k] for r in rows if r["task_family"] == f)
                     for k in METRICS} for f in families}
    return {"per_episode": rows, "by_family": by_family,
            "overall": {k: mean(row[k] for row in by_family.values()) for k in METRICS}}
