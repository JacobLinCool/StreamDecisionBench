"""Validate, freeze and compose application decisions without consulting gold."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any

from streamdecisionbench.jev import validate_request
from streamdecisionbench.lite import SCHEMA_VERSION


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def request_for(episode: dict, step: dict) -> dict:
    """Only these two fields cross the model boundary."""
    return {"state": step["state"], "questions": episode["questions"]}


def compose(spec: dict, answers: dict) -> dict:
    """Keep the predicted route, its active fields, and globally used fields."""
    route_key = spec["route_question"]
    route = answers[route_key]
    if route not in spec["branches"]:
        raise ValueError(f"unknown route: {route!r}")
    keys = [route_key, *spec["always"], *spec["branches"][route]]
    return {key: answers[key] for key in keys}


def decode(episode: dict, wire_answers: dict) -> dict:
    if set(wire_answers) != set(episode["questions"]):
        raise ValueError("answers must cover every question exactly once")
    return {key: episode["option_semantics"][key][value] for key, value in wire_answers.items()}


def encode_scenario(scenario: dict) -> dict:
    """Freeze stable opaque option labels; semantic gold stays outside requests."""
    episode = copy.deepcopy(scenario)
    episode["schema_version"] = SCHEMA_VERSION
    mappings = {}
    for key, q in episode["questions"].items():
        if q["type"] != "choice":
            raise ValueError("the first Lite pilot uses choice questions only")
        rng = random.Random(f"sdb-lite-v1:{episode['episode_id']}:{key}")
        labels = [f"K{i:02d}" for i in range(1, len(q["criteria"]) + 1)]
        rng.shuffle(labels)
        pairs = list(zip(labels, q["criteria"].items()))
        rng.shuffle(pairs)
        mappings[key] = {label: semantic for label, (semantic, _) in pairs}
        q["criteria"] = {label: f"{semantic}: {description}" for label, (semantic, description) in pairs}
    episode["option_semantics"] = mappings
    validate_episode(episode)
    return episode


def validate_episode(episode: dict) -> dict:
    if episode.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("not a Lite episode")
    tick = episode["tick_seconds"]
    if not isinstance(tick, (int, float)) or not math.isfinite(tick) or tick <= 0:
        raise ValueError("tick_seconds must be positive and finite")
    questions, spec = episode["questions"], episode["decision_spec"]
    route = spec["route_question"]
    if route not in questions or route in spec["always"]:
        raise ValueError("route question must exist and not repeat in always")
    if set(spec["branches"]) != set(episode["option_semantics"][route].values()):
        raise ValueError("every route must have a declared branch")
    used = {route, *spec["always"]}
    for branch in spec["branches"].values():
        keys = [route, *spec["always"], *branch]
        if len(keys) != len(set(keys)) or not set(keys) <= set(questions):
            raise ValueError("decision fields must be unique defined questions")
        used.update(branch)
    if used != set(questions):
        raise ValueError("each question must serve at least one application decision")
    steps = episode["steps"]
    if len(steps) < 2 or [s["t"] for s in steps] != list(range(len(steps))):
        raise ValueError("steps must be consecutive from zero")
    decisions, routes = [], set()
    for step in steps:
        validate_request(request_for(episode, step))
        if set(step["gold"]) != set(questions):
            raise ValueError("gold must cover exactly the questions")
        for key, value in step["gold"].items():
            if value not in episode["option_semantics"][key].values():
                raise ValueError(f"invalid gold for {key}")
        if not step.get("evidence"):
            raise ValueError("every state requires an authoring evidence witness")
        decisions.append(compose(spec, step["gold"]))
        routes.add(step["gold"][route])
    changes = [i for i in range(1, len(steps)) if decisions[i] != decisions[i - 1]]
    if not changes or len(changes) == len(steps) - 1:
        raise ValueError("episode must contain both transitions and holds")
    return {
        "episode_id": episode["episode_id"], "questions": len(questions), "steps": len(steps),
        "duration_s": len(steps) * tick, "decision_transitions": len(changes),
        "routes_seen": sorted(routes), "routes_unseen": sorted(set(spec["branches"]) - routes),
        "public_hash": digest([request_for(episode, s) for s in steps]),
    }


def sources() -> dict[str, str]:
    package = Path(__file__).parent
    paths = [*package.rglob("*.py"), *(package.parent / "adapters").glob("*.py"), package.parent / "jev.py"]
    return {str(p.relative_to(package.parent)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def build_dataset(destination: Path) -> dict:
    from streamdecisionbench.lite.tasks import assembly, debugging, presenter, support

    episodes = []
    for module in (debugging, assembly, support, presenter):
        for scenario in module.scenarios():
            for step in scenario["steps"]:
                if module.reference(copy.deepcopy(step["state"])) != step["gold"]:
                    raise ValueError(f"public reference mismatch: {scenario['episode_id']} t={step['t']}")
            episodes.append(encode_scenario(scenario))
    ids = [e["episode_id"] for e in episodes]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate episode ids")
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError("dataset directory must be empty; freeze each revision separately")
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "episodes": [validate_episode(e) for e in episodes],
        "hashes": {e["episode_id"]: digest(e) for e in episodes},
        "generator_sources": sources(),
        "reference_validation": "public-only executable reference agreement; not independent human adjudication",
    }
    manifest["dataset_hash"] = digest(manifest["hashes"])
    for e in episodes:
        (destination / f"{e['episode_id']}.json").write_text(json.dumps(e, ensure_ascii=False, indent=2) + "\n")
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def select_episodes(episodes: list[dict], *, families: list[str] | None = None,
                    episode_ids: list[str] | None = None) -> list[dict]:
    """The requested families or episodes, in dataset order; unknown names are errors."""
    if families and episode_ids:
        raise ValueError("select either families or episodes, not both")
    if families:
        unknown = set(families) - {e["task_family"] for e in episodes}
        chosen = [e for e in episodes if e["task_family"] in families]
    elif episode_ids:
        unknown = set(episode_ids) - {e["episode_id"] for e in episodes}
        chosen = [e for e in episodes if e["episode_id"] in episode_ids]
    else:
        return episodes
    if unknown:
        raise ValueError(f"not in the dataset: {', '.join(sorted(unknown))}")
    return chosen


def load_dataset(path: Path) -> tuple[list[dict], dict]:
    manifest = json.loads((path / "manifest.json").read_text())
    if digest(manifest["hashes"]) != manifest["dataset_hash"]:
        raise ValueError("manifest dataset hash mismatch")
    episodes = []
    for eid, expected in manifest["hashes"].items():
        e = json.loads((path / f"{eid}.json").read_text())
        if digest(e) != expected:
            raise ValueError(f"episode hash mismatch: {eid}")
        validate_episode(e)
        episodes.append(e)
    return episodes, manifest
