"""Episode files: the public System One requests plus hidden construction data.

An episode is one continuous situation observed over ``STEPS`` ticks. Each tick
carries a complete state; the questions (and therefore the decision policy and
candidate decisions) are fixed for the whole episode. Gold answers, latent
states, option semantics and event tags are hidden metadata and never reach the
evaluated model.

Two schema versions exist. ``sdb/0.2`` (real-time families) adds the episode's
timing (``tick_seconds``, ``window_start``, ``deadline_seconds``) and its
family's state format (``schema_id``); the state is always a JSON object, and
each choice question's option order is fixed for the episode as the insertion
order of its ``criteria``. Legacy ``sdb/0.1`` (v0 pilot families not yet
rewritten) reshuffles option order every tick through ``criteria_order``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, Iterator

SCHEMA_VERSION = "sdb/0.2"
LEGACY_SCHEMA_VERSION = "sdb/0.1"
SCHEMA_VERSIONS = (LEGACY_SCHEMA_VERSION, SCHEMA_VERSION)
STEPS = 100
TICK_SECONDS = (0.5, 1, 2, 3, 5)
CHOICE_OPTIONS = (2, 10)  # sdb/0.2 choice option count (binary decisions are 2-option choices)
SCORE_LEVELS = (3, 5)  # sdb/0.2 score level count
QUESTION_COUNT = (1, 3)  # sdb/0.2 questions per decision
VARIANTS = ("canonical", "paraphrase", "lexical_decoy", "minimal_cf", "structural_cf")
COUNTERFACTUAL_VARIANTS = ("minimal_cf", "structural_cf")
INVARIANT_VARIANTS = ("paraphrase", "lexical_decoy")

TASK_FAMILIES = (
    "presentation_navigation",
    "interview_navigation",
    "dialogue_intervention",
    "meeting_facilitation",
    "procedural_coaching",
    "incident_response",
    "live_debugging",
    "support_orchestration",
    "monitoring_alerting",
    "workflow_handoff",
)

DECISION_STRUCTURES = (
    "maintain",
    "advance",
    "wait",
    "recover",
    "rollback",
    "reroute",
    "escalate",
    "handoff",
    "terminate",
    "resolve-conflict",
)

# Event tags authors attach to steps. ``transition`` and ``cf_flip`` are derived
# from gold labels by the builder; the rest describe why a step exists.
EVENT_TAGS = (
    "steady",
    "transition",
    "distractor",
    "minimal_change",
    "recovery",
    "hold_under_activity",
    "boundary",
    "priority_conflict",
    "arithmetic",
    "implicit",
    "decoy",
    "cf_flip",
)

TIERS = ("easy", "medium", "hard")  # sdb/0.1
RT_TIERS = ("medium", "hard")  # sdb/0.2 has no easy tier (decision 3)

# An id-like token shown to the model (script unit ``S4``, paragraph ``P10``,
# product ``H4``). sdb/0.2 option labels never start with the letter of one.
ID_TOKEN = re.compile(r"\b([A-Z])\d+\b")


def deadline_steps_for(deadline_seconds: float, tick_seconds: float) -> int:
    """The DSR deadline in ticks for a deadline in seconds (sdb/0.2)."""
    return max(1, round(deadline_seconds / tick_seconds))


def is_realtime(episode: dict[str, Any]) -> bool:
    return episode.get("schema_version") == SCHEMA_VERSION


def composite(gold_or_pred: dict[str, Any], keys: Iterable[str]) -> str:
    """One comparable token for a multi-question decision."""
    return "|".join(json.dumps(gold_or_pred[k]) for k in keys)


def question_keys(episode: dict[str, Any]) -> list[str]:
    return sorted(episode["questions"], key=lambda k: int(k[1:]) if k[1:].isdigit() else k)


def gold_sequence(episode: dict[str, Any]) -> list[str]:
    keys = question_keys(episode)
    return [composite(step["gold"], keys) for step in episode["steps"]]


def build_request(episode: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    """The exact System One request the model sees at one tick.

    Choice options appear in the step's ``criteria_order`` (sdb/0.1) or, when
    the step has none (sdb/0.2), in the question's own fixed order.
    """
    orders = step.get("criteria_order") or {}
    questions: dict[str, Any] = {}
    for key in question_keys(episode):
        question = episode["questions"][key]
        wire = {"type": question["type"], "instructions": question["instructions"]}
        if question["type"] == "choice" and key in orders:
            wire["criteria"] = {option: question["criteria"][option] for option in orders[key]}
        elif "criteria" in question:
            wire["criteria"] = question["criteria"]
        questions[key] = wire
    return {"state": step["state"], "questions": questions}


def to_semantic(episode: dict[str, Any], key: str, committed: Any) -> Any:
    """Map a committed answer (option label, level, bool) to its hidden semantic value."""
    question = episode["questions"][key]
    if question["type"] == "choice":
        return episode["hidden"]["option_semantics"][key].get(committed, None)
    return committed


def state_text(state: Any) -> str:
    """A flat text view of a state, for lexical baselines and similarity checks."""
    if isinstance(state, str):
        return state
    if isinstance(state, dict):
        return "\n".join(f"{k}: {state_text(v)}" for k, v in state.items())
    if isinstance(state, list):
        return "\n".join(state_text(v) for v in state)
    return str(state)


def entry_text(entry: Any) -> str:
    return state_text(entry) if entry is not None else ""


def id_tokens(*entries: Any) -> dict[str, str]:
    """Letter -> first id-like token (``ID_TOKEN``) that starts with it, over the text of ``entries``."""
    out: dict[str, str] = {}
    for entry in entries:
        for match in ID_TOKEN.finditer(entry_text(entry)):
            out.setdefault(match.group(1), match.group(0))
    return out


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()


def load_episode(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def iter_episodes(root: Path) -> Iterator[dict[str, Any]]:
    for path in sorted((root / "episodes").glob("*.json")):
        yield load_episode(path)


def load_episodes(root: Path, ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
    wanted = set(ids) if ids else None
    return [e for e in iter_episodes(root) if wanted is None or e["episode_id"] in wanted]


def save_episode(root: Path, episode: dict[str, Any]) -> Path:
    path = root / "episodes" / f"{episode['episode_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".json.tmp{os.getpid()}")
    tmp.write_text(json.dumps(episode, ensure_ascii=False, indent=1) + "\n")
    os.replace(tmp, path)  # atomic: concurrent readers never see a partial file
    return path
