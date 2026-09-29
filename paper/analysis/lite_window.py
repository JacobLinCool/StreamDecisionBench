"""Choose the Figure 1 window by an explicit rule over every candidate window.

Used by lite_figures.py (to draw the window) and lite_numbers.py (to state how it
was chosen). Needs no plotting library and makes no network request.

Candidates: every WINDOW_S-second window that starts at a time step and ends within
the horizon, in the scenarios passed in ``order`` (51 starts per 60-step scenario).
The paper passes only presenter A at the 2 s recording cadence.

Rule, applied to the scored in-force intervals of the primary replay timeline:
the displayed window is the most representative one, minimizing the largest
absolute difference between a model's correct share in the window and its overall
in-force accuracy; ties go to the earlier scenario, then the earlier start.
"""

from __future__ import annotations

WINDOW_S = 20.0
KINDS = ("correct", "source_correct", "source_incorrect", "no_decision")


def _seconds(intervals: list[dict], start: float, end: float) -> dict:
    out = dict.fromkeys(KINDS, 0.0)
    for iv in intervals:
        a, b = max(iv["start_s"], start), min(iv["end_s"], end)
        if b > a:
            out[iv["kind"]] += b - a
    return out


def scan(intervals: dict, overall: dict, order: list[str], tick: float, horizon: float) -> dict:
    """intervals[model][episode_id] -> scored intervals; overall[model] -> in-force accuracy (fraction)."""
    models = list(overall)
    candidates = []
    starts = [k * tick for k in range(int(round((horizon - WINDOW_S) / tick)) + 1)]
    for eid in order:
        for start in starts:
            end = start + WINDOW_S
            seconds = {m: _seconds(intervals[m][eid], start, end) for m in models}
            share = {m: seconds[m]["correct"] / WINDOW_S for m in models}
            deviation = max(abs(share[m] - overall[m]) for m in models)
            candidates.append({"episode": eid, "start": start, "end": end,
                               "share": share, "seconds": seconds, "max_deviation": deviation})
    chosen = min(candidates, key=lambda c: (c["max_deviation"], order.index(c["episode"]), c["start"]))
    return {"window_s": WINDOW_S, "candidates": len(candidates), "chosen": chosen,
            "rule": __doc__.split("Rule, applied")[1].strip()}
