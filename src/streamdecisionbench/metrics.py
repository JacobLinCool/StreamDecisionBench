"""Leaderboard metrics over decision trajectories.

A step's decision is the tuple of answers to all of its questions; a step is
correct only when every answer matches gold. Gold trajectories are split into
maximal constant segments, and a true transition is any tick whose gold
decision differs from the previous tick's.

Primary columns (no single overall score in v0):
SBA, Transition F1@delta, Reaction Delay, ESR, DSR, latency p95, CSA.

Every run is scored twice (REALTIME_FAMILIES.md 3.1). The **untimed** run
scores the answer to every tick's own state, ignoring latency. The
**real-time** replays (``replay``) put the same per-tick answers and their
measured latencies on a virtual clock per timed (``sdb/0.2``) episode and
score, at every tick, the decision in force when the tick ends; the gap
between the two is the cost of latency (plus the effect of failed responses,
which the untimed run scores wrong and a replay bridges with the previous
decision). In a replay, reaction delay in seconds and the DSR deadline are
wall-clock: from the release of the transition tick's state to the arrival of
the answer that put the new decision in force.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass
from statistics import mean, median, stdev
from typing import Any, Iterable, Sequence

from streamdecisionbench.jev import INVALID
from streamdecisionbench.schema import (
    COUNTERFACTUAL_VARIANTS,
    INVARIANT_VARIANTS,
    composite,
    deadline_steps_for,
    is_realtime,
    question_keys,
)


@dataclass(frozen=True)
class TemporalConfig:
    delta: int = 2  # tolerance, in ticks, for matching a switch to a true transition
    hold: int = 2  # a predicted switch counts only if held for this many ticks


def segments(seq: Sequence[str]) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    start = 0
    for t in range(1, len(seq) + 1):
        if t == len(seq) or seq[t] != seq[start]:
            out.append((start, t, seq[start]))
            start = t
    return out


def true_transitions(gold: Sequence[str]) -> list[tuple[int, str]]:
    return [(t, gold[t]) for t in range(1, len(gold)) if gold[t] != gold[t - 1]]


def stable_switches(pred: Sequence[str], hold: int) -> list[tuple[int, str]]:
    """Changes of the settled (debounced) decision.

    The settled decision starts as the first valid prediction and moves to a
    new value at tick s only if the prediction takes that value at s and keeps
    it for ``hold`` ticks (or until the episode ends). Flicker that never holds
    leaves the settled decision, and therefore the switch count, untouched.
    Ticks before the first valid prediction (in a real-time replay, before the
    first answer arrives) are wrong but are not a switch.
    """
    out: list[tuple[int, str]] = []
    n = len(pred)
    first = next((s for s, p in enumerate(pred) if p != INVALID), n)
    if first == n:
        return out
    settled = pred[first]
    for s in range(first + 1, n):
        if pred[s] == settled:
            continue
        end = min(n, s + hold)
        if all(pred[k] == pred[s] for k in range(s, end)):
            settled = pred[s]
            out.append((s, settled))
    return out


@dataclass
class TransitionMatch:
    tau: int
    decision: str
    switch: int | None  # matched stable switch tick, None if missed

    @property
    def delay(self) -> int | None:
        return None if self.switch is None else self.switch - self.tau


def match_transitions(
    gold: Sequence[str], pred: Sequence[str], cfg: TemporalConfig
) -> tuple[list[TransitionMatch], list[tuple[int, str]]]:
    """One-to-one matching of true transitions to predicted stable switches.

    A switch matches a transition when it moves to the transition's new
    decision within ``delta`` ticks of it. Returns the per-transition matches
    and the unmatched (excess) switches.
    """
    switches = stable_switches(pred, cfg.hold)
    used: set[int] = set()
    matches = []
    for tau, decision in true_transitions(gold):
        candidates = [
            (abs(s - tau), s < tau, s)
            for s, value in switches
            if s not in used and value == decision and abs(s - tau) <= cfg.delta
        ]
        if candidates:
            _, _, s = min(candidates)  # closest; on ties prefer the non-early switch
            used.add(s)
            matches.append(TransitionMatch(tau, decision, s))
        else:
            matches.append(TransitionMatch(tau, decision, None))
    excess = [(s, v) for s, v in switches if s not in used]
    return matches, excess


def _pct(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    # nearest-rank percentile
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return float(ordered[rank - 1])


def _mean(values: Iterable[float]) -> float | None:
    values = list(values)
    return sum(values) / len(values) if values else None


def episode_tick(episode: dict[str, Any]) -> float | None:
    """Seconds per tick of a timed (sdb/0.2) episode; None for untimed sdb/0.1 ticks."""
    return episode["tick_seconds"] if is_realtime(episode) else None


def episode_sequences(episode: dict[str, Any], records: Sequence[dict[str, Any]]) -> tuple[list[str], list[str]]:
    keys = question_keys(episode)
    gold = [composite(step["gold"], keys) for step in episode["steps"]]
    by_t = {r["t"]: r for r in records}
    pred = []
    for step in episode["steps"]:
        r = by_t.get(step["t"])
        if r is None or not r.get("ok"):
            pred.append(INVALID)
        else:
            pred.append(composite(r["pred"], keys))
    return gold, pred


def _f1(tp: int, fp: int, fn: int) -> float:
    return 2 * tp / (2 * tp + fp + fn) if (tp + fp + fn) else 1.0


def episode_metrics(
    episode: dict[str, Any], records: Sequence[dict[str, Any]], cfg: TemporalConfig
) -> dict[str, Any]:
    """Metrics of one episode. ``records`` are untimed-run responses or, from a
    replay, the decisions in force (rows with ``received_s``); for the latter,
    reaction delay in seconds and the DSR deadline are wall-clock."""
    gold, pred = episode_sequences(episode, records)
    n = len(gold)
    correct = [g == p for g, p in zip(gold, pred)]
    segs = segments(gold)
    sba = sum(sum(correct[a:b]) / (b - a) for a, b, _ in segs) / len(segs)
    matches, excess = match_transitions(gold, pred, cfg)
    tp = [m for m in matches if m.switch is not None]
    fn = len(matches) - len(tp)
    fp = len(excess)
    exact, exact_excess = match_transitions(gold, pred, TemporalConfig(delta=0, hold=cfg.hold))
    exact_tp = sum(m.switch is not None for m in exact)
    exact_counts = (exact_tp, len(exact_excess), len(exact) - exact_tp)
    late_enough = [m for m in tp if m.delay is not None and m.delay >= 0]  # early switches anticipate the evidence
    early = [m for m in tp if m.delay is not None and m.delay < 0]
    by_t = {r["t"]: r for r in records}
    tick = episode_tick(episode)
    replayed = any("received_s" in r for r in records)

    def seconds(m: TransitionMatch) -> float:
        """Reaction delay in seconds: wall-clock in a replay, whole ticks in the untimed run."""
        if replayed:
            return by_t[m.switch]["received_s"] - m.tau * tick
        return m.delay * tick

    deadline = deadline_steps_for(episode["deadline_seconds"], tick) if tick else episode["deadline_steps"]
    if tick and replayed:
        on_time = [m for m in late_enough if seconds(m) <= episode["deadline_seconds"] + 1e-9]
    else:
        on_time = [m for m in late_enough if m.delay <= deadline]
    raw_switches = sum(1 for t in range(1, n) if pred[t] != pred[t - 1])

    keys = question_keys(episode)
    roles = episode["hidden"].get("question_keys", {})
    per_question = {}
    for key in keys:
        hits = []
        for step in episode["steps"]:
            r = by_t.get(step["t"])
            hits.append(bool(r and r.get("ok") and r["pred"][key] == step["gold"][key]))
        per_question[key] = sum(hits) / n
    # Share of the most frequent gold answer: what always giving that answer would score.
    prior = {}
    for key in keys:
        counts: dict[str, int] = defaultdict(int)
        for step in episode["steps"]:
            counts[str(step["gold"][key])] += 1
        prior[key] = max(counts.values()) / n

    return {
        "episode_id": episode["episode_id"],
        "task_family": episode["task_family"],
        "contrast_family": episode["contrast_family"],
        "variant": episode["variant"],
        "tier": episode["difficulty"]["tier"],
        "steps": n,
        "accuracy": sum(correct) / n,
        "sba": sba,
        "segments": len(segs),
        "transitions": len(matches),
        "tp": len(tp),
        "fp": fp,
        "fn": fn,
        "transition_f1": _f1(len(tp), fp, fn),
        "transition_f1_exact": _f1(*exact_counts),
        "reaction_delays": [m.delay for m in late_enough],
        "reaction_delays_s": [round(seconds(m), 6) for m in late_enough] if tick else [],
        "deadline_steps": deadline,
        "early_switches": len(early),
        "esr": fp / n,
        "raw_switch_rate": raw_switches / n,
        "dsr": len(on_time) / len(matches) if matches else 1.0,
        "invalid": sum(1 for p in pred if p == INVALID),
        "per_question_accuracy": per_question,
        "per_question_prior": prior,
        "questions": {k: {"role": roles.get(k, k), "type": episode["questions"][k].get("type")} for k in keys},
        "correct": correct,
        "exact_counts": exact_counts,
    }


PRIVATE_FIELDS = ("correct", "exact_counts")  # per-episode fields kept out of metrics.json


def contrast_probes(family: dict[str, dict[str, Any]]) -> list[list[tuple[str, int]]]:
    """Probes for one contrast family (variant -> episode).

    For each counterfactual variant, every maximal run of ticks whose gold
    decision differs from the canonical one is a probe. The probe covers those
    ticks in the counterfactual, the canonical, and both invariant variants: a
    model solves it only by flipping where the facts flip and holding where
    only the wording changes.
    """
    canonical = family.get("canonical")
    if canonical is None:
        return []
    keys = question_keys(canonical)
    base = [composite(s["gold"], keys) for s in canonical["steps"]]
    probes = []
    for variant in COUNTERFACTUAL_VARIANTS:
        episode = family.get(variant)
        if episode is None:
            continue
        seq = [composite(s["gold"], keys) for s in episode["steps"]]
        t = 0
        while t < len(seq):
            if seq[t] == base[t]:
                t += 1
                continue
            start = t
            while t < len(seq) and seq[t] != base[t]:
                t += 1
            members = []
            for k in range(start, t):
                members.append((variant, k))
                members.append(("canonical", k))
                for inv in INVARIANT_VARIANTS:
                    if inv in family:
                        members.append((inv, k))
            probes.append(members)
    return probes


def _one_hot(probs: Any) -> bool:
    values = list(probs.values()) if isinstance(probs, dict) else [float(probs)]
    return all(p in (0.0, 1.0) for p in values)


def _calibration(
    episodes: dict[str, dict[str, Any]], predictions: dict[str, list[dict[str, Any]]]
) -> dict[str, Any] | None:
    """NLL, Brier and ECE of the reported probabilities against gold.

    None when no answer carries probabilities or every answer is one-hot
    (generative adapters wrap a committed answer as probability 1): such a run
    reports no uncertainty to calibrate.
    """
    nll, brier, conf_hits, one_hot = [], [], [], True
    for eid, records in predictions.items():
        episode = episodes.get(eid)
        if episode is None:
            continue
        steps = {s["t"]: s for s in episode["steps"]}
        for r in records:
            if not r.get("ok") or not r.get("probs"):
                continue
            gold = steps[r["t"]]["gold"]
            for key, probs in r["probs"].items():
                one_hot = one_hot and _one_hot(probs)
                g = gold[key]
                if isinstance(probs, dict):
                    p_gold = probs.get(str(g) if not isinstance(g, str) else g, 0.0)
                    nll.append(-math.log(max(p_gold, 1e-6)))
                    brier.append(sum((p - (1.0 if k == (str(g) if not isinstance(g, str) else g) else 0.0)) ** 2 for k, p in probs.items()))
                    top = max(probs.values())
                    conf_hits.append((top, r["pred"][key] == g))
                else:
                    p_yes = float(probs)
                    target = 1.0 if g else 0.0
                    brier.append((p_yes - target) ** 2)
                    nll.append(-math.log(max(p_yes if g else 1 - p_yes, 1e-6)))
                    conf_hits.append((max(p_yes, 1 - p_yes), r["pred"][key] == g))
    if not conf_hits or one_hot:
        return None
    bins: dict[int, list[tuple[float, bool]]] = defaultdict(list)
    for conf, hit in conf_hits:
        bins[min(int(conf * 10), 9)].append((conf, hit))
    ece = sum(
        len(items) / len(conf_hits) * abs(_mean(c for c, _ in items) - _mean(float(h) for _, h in items))
        for items in bins.values()
    )
    return {"nll": _mean(nll), "brier": _mean(brier), "ece": ece, "answers": len(conf_hits)}


def aggregate(
    episodes: Sequence[dict[str, Any]],
    predictions: dict[str, list[dict[str, Any]]],
    cfg: TemporalConfig = TemporalConfig(),
    requests: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """The metric suite over per-tick records (``episode_id -> records``).

    ``predictions`` holds the decision scored at each tick. Latency, the late
    rate and the failed-request rate come from ``requests``, the requests
    actually made (by default the same records); a real-time replay passes the
    requests it sent. They cover every sent request with a measured latency,
    failed or not, so a slow failure stays in the tail.
    """
    by_id = {e["episode_id"]: e for e in episodes}
    per_episode = [episode_metrics(e, predictions.get(e["episode_id"], []), cfg) for e in episodes]

    delays = [d for m in per_episode for d in m["reaction_delays"]]
    delays_s = [d for m in per_episode for d in m["reaction_delays_s"]]
    transitions = sum(m["transitions"] for m in per_episode)
    tp = sum(m["tp"] for m in per_episode)
    fp = sum(m["fp"] for m in per_episode)
    fn = sum(m["fn"] for m in per_episode)
    steps = sum(m["steps"] for m in per_episode)
    sent = [(by_id[eid], r) for eid, rs in (predictions if requests is None else requests).items() if eid in by_id for r in rs]
    timed_sent = [(e, r) for e, r in sent if r.get("latency_ms") is not None]
    latencies = [r["latency_ms"] for _, r in timed_sent]
    # A request is late when its answer cannot be in force within its own tick: latency >= tick (in replay microseconds).
    late = [round(r["latency_ms"] * 1000) >= round(episode_tick(e) * 1_000_000) for e, r in timed_sent if episode_tick(e)]
    exact = [sum(m["exact_counts"][i] for m in per_episode) for i in range(3)]

    # Contrast-set accuracy.
    families: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for e in episodes:
        families[e["contrast_family"]][e["variant"]] = e
    correct_at = {m["episode_id"]: m["correct"] for m in per_episode}
    family_solved = {}
    probe_scores = []
    for name, fam in sorted(families.items()):
        probes = contrast_probes(fam)
        solved = [all(correct_at[fam[v]["episode_id"]][t] for v, t in probe) for probe in probes]
        probe_scores.extend(solved)
        family_solved[name] = {"probes": len(probes), "solved": sum(solved), "all": bool(probes) and all(solved)}
    scored_families = [f for f in family_solved.values() if f["probes"]]

    def breakdown(field: str) -> dict[str, Any]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for m in per_episode:
            groups[m[field]].append(m)
        return {
            k: {
                "episodes": len(v),
                "sba": _mean(x["sba"] for x in v),
                "accuracy": _mean(x["accuracy"] for x in v),
                "transition_f1": _pct_f1(v),
                "esr": _mean(x["esr"] for x in v),
            }
            for k, v in sorted(groups.items())
        }

    tag_hits: dict[str, list[bool]] = defaultdict(list)
    for e in episodes:
        c = correct_at[e["episode_id"]]
        for step in e["steps"]:
            for tag in step["event_tags"]:
                tag_hits[tag].append(c[step["t"]])

    # Per-question accuracy, weighted by steps: by wire key (q1..), answer type and semantic role.
    question_hits: dict[str, dict[str, list[tuple[float, int]]]] = {"key": defaultdict(list), "type": defaultdict(list), "role": defaultdict(list)}
    for m in per_episode:
        for key, acc in m["per_question_accuracy"].items():
            info = m["questions"][key]
            for field, group in (("key", key), ("type", info["type"]), ("role", info["role"])):
                question_hits[field][group].append((acc, m["steps"]))

    def question_breakdown(groups: dict[str, list[tuple[float, int]]]) -> dict[str, Any]:
        return {
            k: {"episodes": len(v), "steps": sum(n for _, n in v), "accuracy": sum(a * n for a, n in v) / sum(n for _, n in v)}
            for k, v in sorted(groups.items())
        }

    structure_hits: dict[str, list[float]] = defaultdict(list)
    for m, e in zip(per_episode, episodes):
        for s in e["decision_structures"]:
            structure_hits[s].append(m["sba"])

    return {
        "config": {"delta": cfg.delta, "hold": cfg.hold},
        "episodes": len(per_episode),
        "steps": steps,
        "primary": {
            "sba": _mean(m["sba"] for m in per_episode),
            "transition_f1": _f1(tp, fp, fn),
            "reaction_delay_median": median(delays) if delays else None,
            "reaction_delay_p90": _pct(delays, 90),
            "reaction_delay_s_median": median(delays_s) if delays_s else None,
            "reaction_delay_s_p90": _pct(delays_s, 90),
            "esr": fp / steps if steps else None,
            "dsr": sum(m["dsr"] * m["transitions"] for m in per_episode) / transitions if transitions else None,
            "latency_ms_p95": _pct(latencies, 95),
            "csa": (sum(f["all"] for f in scored_families) / len(scored_families)) if scored_families else None,
        },
        "secondary": {
            "accuracy": sum(m["accuracy"] * m["steps"] for m in per_episode) / steps if steps else None,
            "early_switch_rate": sum(m["early_switches"] for m in per_episode) / transitions if transitions else None,
            "transition_f1_exact": _f1(*exact),
            "raw_switch_rate": _mean(m["raw_switch_rate"] for m in per_episode),
            "latency_ms_p50": _pct(latencies, 50),
            "latency_ms_p99": _pct(latencies, 99),
            "late_rate": _mean(float(x) for x in late),
            "failed_request_rate": _mean(float(not r.get("ok")) for _, r in sent),
            "csa_probe": _mean(float(x) for x in probe_scores),
            "invalid_rate": sum(m["invalid"] for m in per_episode) / steps if steps else None,
            "transitions": transitions,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "calibration": _calibration(by_id, predictions),
        },
        "by_family": breakdown("task_family"),
        "by_variant": breakdown("variant"),
        "by_tier": breakdown("tier"),
        "by_event_tag": {k: {"steps": len(v), "accuracy": sum(v) / len(v)} for k, v in sorted(tag_hits.items())},
        "by_decision_structure": {k: {"episodes": len(v), "sba": _mean(v)} for k, v in sorted(structure_hits.items())},
        "by_question": {f"by_{field}": question_breakdown(groups) for field, groups in question_hits.items()},
        "contrast_families": family_solved,
        "per_episode": [{k: v for k, v in m.items() if k not in PRIVATE_FIELDS} for m in per_episode],
    }


def _pct_f1(ms: Sequence[dict[str, Any]]) -> float:
    return _f1(sum(m["tp"] for m in ms), sum(m["fp"] for m in ms), sum(m["fn"] for m in ms))


# ---------------------------------------------------------------------------
# Real-time replay (REALTIME_FAMILIES.md 3.1)
# ---------------------------------------------------------------------------

REPLAY_MODES = ("single", "pipelined")
TIMEOUT_TICKS = 3  # client timeout: max(3 ticks, the DSR deadline)
RESAMPLES = 20  # latency redraws behind the replay blocks' mean and sd
RESAMPLED = ("sba", "transition_f1", "dsr", "esr", "accuracy")


def client_timeout(episode: dict[str, Any]) -> float:
    """Seconds after which a replay abandons a request (SPEC 2.3): ``max(3 ticks, deadline_seconds)``."""
    return max(TIMEOUT_TICKS * episode["tick_seconds"], episode["deadline_seconds"])


def replay(
    episode: dict[str, Any], records: Sequence[dict[str, Any]], mode: str = "single"
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Replay an untimed run of one timed episode on a virtual clock; no sleeping.

    Tick t's state is released at ``t * tick_seconds``. Each request takes the
    latency recorded for the state it carries (the untimed run answered every
    tick). ``single``: one request in flight; when the model is idle it gets the
    newest released state (or waits for the next release), so states released
    while a request is in flight are skipped. ``pipelined``: every state is
    sent at its release. A request whose latency exceeds ``client_timeout`` is
    abandoned at the timeout: its answer never arrives, it counts as a failed
    (and late) request, and in single mode the newest state is sent at once.
    The decision in force at tick t is the answer of the newest state among the
    valid answers received strictly before ``(t + 1) * tick_seconds``; in
    single mode that is simply the latest one. A failed or invalid response
    occupies its latency and leaves the previous decision in force; ticks
    before the first valid answer have no decision (scored wrong). A tick
    without a record counts as a failure with no latency. The clock runs in
    integer microseconds, so ties are exact: an answer that arrives exactly at a
    tick boundary is in force from the next tick on.

    Returns ``(in_force, sent)``: one record per tick with the decision in force
    (``source_t`` is the tick whose state it answered, ``received_s`` the
    virtual arrival time; ``ok`` is False when no decision is in force), and
    the recorded responses of the requests the replay sent, in sending order;
    an abandoned one is marked ``abandoned`` and not ``ok``.
    """
    if mode not in REPLAY_MODES:
        raise ValueError(f"unknown replay mode {mode!r}; expected one of {REPLAY_MODES}")
    tick = round(episode["tick_seconds"] * 1_000_000)
    limit = round(client_timeout(episode) * 1_000_000)
    n = len(episode["steps"])
    by_t = {r["t"]: r for r in records}

    def latency(s: int) -> int:
        r = by_t.get(s)
        return round(r["latency_ms"] * 1000) if r and r.get("latency_ms") is not None else 0

    order: list[int] = []  # state ticks, in sending order
    arrivals: list[tuple[int, int]] = []  # (received, state tick) of the answers that arrive
    if mode == "pipelined":
        order = list(range(n))
        arrivals = [(s * tick + latency(s), s) for s in order if latency(s) <= limit]
    else:
        now, s = 0, 0
        while s < n:
            order.append(s)
            start = max(now, s * tick)
            now = start + min(latency(s), limit)
            if latency(s) <= limit:
                arrivals.append((now, s))
            s = max(s + 1, now // tick)  # the newest state released by the time the answer arrives (or is abandoned)

    ordered = sorted(arrivals)
    in_force: list[dict[str, Any]] = []
    best: tuple[int, int] | None = None  # (received, state tick) of the decision in force
    i = 0
    for t in range(n):
        while i < len(ordered) and ordered[i][0] < (t + 1) * tick:
            received, s = ordered[i]
            i += 1
            if by_t.get(s, {}).get("ok") and (best is None or s > best[1]):
                best = (received, s)
        row: dict[str, Any] = {"episode_id": episode["episode_id"], "t": t}
        if best is None:
            row.update(ok=False, source_t=None, error="no decision in force")
        else:
            source = by_t[best[1]]
            row.update(ok=True, source_t=best[1], received_s=best[0] / 1e6, pred=source["pred"], probs=source.get("probs"))
        in_force.append(row)
    sent = []
    for s in order:
        if s in by_t:
            abandoned = latency(s) > limit
            sent.append({**by_t[s], "ok": False, "abandoned": True, "error": "client timeout"} if abandoned else by_t[s])
    return in_force, sent


REALTIME_BLOCKS = {
    "realtime": ("single", ("primary", "secondary", "by_family", "by_variant", "by_tier")),
    "realtime_pipelined": ("pipelined", ("primary", "secondary")),
}


def _replay_all(
    timed: Sequence[dict[str, Any]], predictions: dict[str, list[dict[str, Any]]], mode: str
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    in_force, sent = {}, {}
    for e in timed:
        eid = e["episode_id"]
        in_force[eid], sent[eid] = replay(e, predictions.get(eid, []), mode)
    return in_force, sent


def latency_resamples(
    timed: Sequence[dict[str, Any]],
    predictions: dict[str, list[dict[str, Any]]],
    cfg: TemporalConfig,
    mode: str,
    k: int = RESAMPLES,
) -> dict[str, Any]:
    """Mean and sd of a replay's headline numbers over ``k`` latency redraws.

    Each redraw keeps every answer and gives each tick a latency drawn with
    replacement from its own episode's recorded latencies, so a few tail
    latencies show up as spread instead of deciding the point value. Seeded,
    so a run's metrics.json is reproducible.
    """
    rng = random.Random(f"sdb-latency-resample:{mode}")
    draws: dict[str, list[float]] = defaultdict(list)
    for _ in range(k):
        redrawn = {}
        for e in timed:
            records = predictions.get(e["episode_id"], [])
            pool = [r["latency_ms"] for r in records if r.get("latency_ms") is not None]
            redrawn[e["episode_id"]] = [{**r, "latency_ms": rng.choice(pool)} for r in records] if pool else records
        in_force, sent = _replay_all(timed, redrawn, mode)
        m = aggregate(timed, in_force, cfg, requests=sent)
        for key in RESAMPLED:
            value = m["primary"][key] if key in m["primary"] else m["secondary"][key]
            if value is not None:
                draws[key].append(value)
    out: dict[str, Any] = {"resamples": k}
    for key, values in draws.items():
        out[key] = {"mean": mean(values), "sd": stdev(values) if len(values) > 1 else 0.0}
    return out


def score_run(
    episodes: Sequence[dict[str, Any]],
    predictions: dict[str, list[dict[str, Any]]],
    cfg: TemporalConfig = TemporalConfig(),
    resamples: int = RESAMPLES,
) -> dict[str, Any]:
    """The contents of ``metrics.json`` for one run.

    The top-level blocks are the untimed run, as before. ``realtime`` (single
    request in flight, the primary protocol) and ``realtime_pipelined`` (a
    request per tick, secondary) replay the timed (sdb/0.2) episodes only; both
    are omitted when the run has none. Their ``stale_rate`` is the share of
    ticks whose decision in force answered an earlier tick's state and their
    ``timeout_rate`` the share of sent requests abandoned at the client
    timeout. The replay of the recorded latencies is the point value;
    ``resampled`` gives mean and sd over ``resamples`` latency redraws
    (``latency_resamples``; 0 turns it off).
    """
    out = aggregate(episodes, predictions, cfg)
    timed = [e for e in episodes if episode_tick(e)]
    if not timed:
        return out
    for block, (mode, fields) in REALTIME_BLOCKS.items():
        in_force, sent = _replay_all(timed, predictions, mode)
        m = aggregate(timed, in_force, cfg, requests=sent)
        rows = [r for rs in in_force.values() for r in rs]
        requests = [r for rs in sent.values() for r in rs]
        m["secondary"]["stale_rate"] = sum(1 for r in rows if r["ok"] and r["source_t"] < r["t"]) / len(rows)
        m["secondary"]["timeout_rate"] = sum(1 for r in requests if r.get("abandoned")) / len(requests) if requests else None
        out[block] = {"protocol": mode, "episodes": m["episodes"], "steps": m["steps"], **{k: m[k] for k in fields}}
        if resamples:
            out[block]["resampled"] = latency_resamples(timed, predictions, cfg, mode, resamples)
    return out
