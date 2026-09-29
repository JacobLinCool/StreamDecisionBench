"""Blind semantic validation: export requests without gold, score answers after.

A shuffled batch mixes ticks from one or more episodes in random order, so a
solver must decide each tick from its own state (which is what "complete state"
promises) and cannot lean on neighbouring ticks. An ordered batch instead gives
each episode as one stream: its questions once, then its states in tick order,
so a solver follows the stream live as SPEC 3.1's expert does. Either way the
key that maps items back to episodes and ticks is written to a separate file
the solver never needs, and ``score_batch`` scores both.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from streamdecisionbench.authoring import seeded
from streamdecisionbench.schema import build_request, composite, question_keys, to_semantic

SOLVER_BRIEF = (
    "Each item is one moment of a live decision task. Answer every question of the item's task "
    "using only that item's `state` and the task's instructions. Choice: give the option label "
    "(e.g. \"K4\"). Score: give the level index (0-based integer). Noul (legacy tasks): give true or false. "
    "Items are shuffled and independent; do not use other items."
)


def export_batch(
    episodes: Sequence[dict[str, Any]],
    ticks: dict[str, Sequence[int]],
    seed: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns (batch, key). ``ticks`` maps episode_id -> tick indices."""
    rng = seeded("blind", seed)
    tasks: dict[str, Any] = {}
    task_of: dict[str, str] = {}
    items = []
    for n, episode in enumerate(episodes, start=1):
        eid = episode["episode_id"]
        if eid not in ticks:
            continue
        task_id = f"T{n}"
        task_of[eid] = task_id
        first = build_request(episode, episode["steps"][0])
        tasks[task_id] = {"questions": first["questions"]}
        for t in ticks[eid]:
            request = build_request(episode, episode["steps"][t])
            items.append({"task": task_id, "state": request["state"], "_eid": eid, "_t": t})
    rng.shuffle(items)
    key = {}
    for i, item in enumerate(items, start=1):
        item_id = f"i{i:03d}"
        key[item_id] = {"episode_id": item.pop("_eid"), "t": item.pop("_t")}
        item["id"] = item_id
    batch = {"brief": SOLVER_BRIEF, "tasks": tasks, "items": [{"id": it["id"], "task": it["task"], "state": it["state"]} for it in items]}
    return batch, key


ORDERED_BRIEF = (
    "Each stream is one live decision task observed tick by tick. Read its questions once, then "
    "follow its states in order and answer every question at every tick, as if the states arrived "
    "live: use the current state, the instructions and what you have seen earlier in the same "
    "stream, never later states. Choice: give the option label (e.g. \"K4\"). Score: give the level "
    "index (0-based integer). Noul (legacy tasks): give true or false. Answer as "
    "{item id: {question key: answer}}."
)


def export_ordered(
    episodes: Sequence[dict[str, Any]], ticks: dict[str, Sequence[int]], seed: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns (batch, key): one stream per episode, streams in shuffled order, states in tick order.

    A stream carries only its questions and gold-free states; the episode id,
    variant, gold, latent state, tags, notes and option semantics stay in the key
    or out of the export.
    """
    chosen = [e for e in episodes if e["episode_id"] in ticks]
    seeded("ordered", seed).shuffle(chosen)
    streams = []
    key = {}
    for n, episode in enumerate(chosen, start=1):
        stream_id = f"S{n}"
        items = []
        for t in sorted(ticks[episode["episode_id"]]):
            item_id = f"{stream_id}.{t:03d}"
            key[item_id] = {"episode_id": episode["episode_id"], "t": t}
            items.append({"id": item_id, "t": t, "state": build_request(episode, episode["steps"][t])["state"]})
        questions = build_request(episode, episode["steps"][0])["questions"]
        streams.append({"id": stream_id, "questions": questions, "ticks": items})
    return {"brief": ORDERED_BRIEF, "streams": streams}, key


def _coerce(question: dict[str, Any], value: Any) -> Any:
    if value is None:
        return None
    if question["type"] == "score":
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if question["type"] == "noul":
        if isinstance(value, str):
            return value.strip().lower() in ("true", "yes", "1")
        return bool(value)
    return value


def score_batch(
    episodes: dict[str, dict[str, Any]], key: dict[str, Any], answers: dict[str, Any]
) -> dict[str, Any]:
    rows = []
    per_question: dict[str, list[bool]] = {}
    for item_id, where in key.items():
        episode = episodes[where["episode_id"]]
        step = episode["steps"][where["t"]]
        keys = question_keys(episode)
        given = answers.get(item_id) or {}
        if not isinstance(given, dict):
            # A bare value is accepted for single-question tasks.
            given = {keys[0]: given} if len(keys) == 1 else {}
        pred = {}
        for k in keys:
            q = episode["questions"][k]
            value = _coerce(q, given.get(k))
            pred[k] = to_semantic(episode, k, value) if q["type"] == "choice" else value
            per_question.setdefault(f"{episode['contrast_family']}:{k}", []).append(pred[k] == step["gold"][k])
        ok = composite(pred, keys) == composite(step["gold"], keys)
        rows.append(
            {
                "item": item_id,
                "episode_id": where["episode_id"],
                "t": where["t"],
                "correct": ok,
                "answer": pred,
                "gold": step["gold"],
                "tags": step["event_tags"],
                "note": step["note"],
            }
        )
    wrong = [r for r in rows if not r["correct"]]
    return {
        "items": len(rows),
        "correct": len(rows) - len(wrong),
        "accuracy": (len(rows) - len(wrong)) / len(rows) if rows else None,
        "per_question": {k: sum(v) / len(v) for k, v in sorted(per_question.items())},
        "disagreements": wrong,
    }


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n")
