"""Checks that training scenarios are valid and share no instance content with evaluation.

A family's published rules (``rules`` and ``policy`` fields) are the task
specification and may be shared. Everything else in a state is instance
content: names, identifiers, utterances, decks, logs, file paths and messages.
Training content must not repeat an evaluation state, an evaluation sentence,
a six-word run of evaluation text, or an evaluation identifier (paths, @teams,
file names, codes with digits, codes such as ST-A).
"""

from __future__ import annotations

import copy
import re
from typing import Any, Iterable

from streamdecisionbench.lite.core import digest, encode_scenario, validate_episode

FAMILIES = {"live_debugging", "procedural_coaching", "support_call_assist", "presenter_voice_control"}
SPEC_KEYS = {"rules", "policy"}
# Positional record identifiers derived from ticks (u12-Customer, p34, a-7-0), not authored content.
STRUCTURAL_KEYS = {"utterance_id", "event_id"}
SHINGLE = 6
# Output formats of tools shared by a family's scenarios (the test runner's
# summary lines and command), not authored instance content.
TEMPLATES = [
    r"\d+ passed, \d+ failed, \d+ skipped", r"interrupted; no completed result",
    r"compilation failed; 0 tests executed", r"running", r"test-runner --reporter=json",
    r"\$ test-runner; collecting tests",
]
IDENTIFIER = re.compile(r"@[\w-]+|[\w.-]*/[\w./-]+|[A-Za-z][\w-]*\d[\w-]*|[A-Z]{1,4}-[A-Z0-9]+|[\w-]+\.[A-Za-z]{1,5}\b")
GENERIC_IDENTIFIERS = {"J1", "J2", "P1", "P2"}


def eval_scenarios() -> list[dict]:
    from streamdecisionbench.lite.tasks import assembly, debugging, presenter, support

    return [s for m in (debugging, assembly, support, presenter) for s in m.scenarios()]


def _strings(value: Any, spec: bool = False) -> Iterable[tuple[str, bool]]:
    if isinstance(value, str):
        yield value, spec
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key, spec
            if key not in STRUCTURAL_KEYS:
                yield from _strings(item, spec or key in SPEC_KEYS)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item, spec)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _template(text: str) -> bool:
    return any(re.fullmatch(t, text) for t in TEMPLATES)


def _content(scenarios: list[dict]) -> tuple[set[str], set[str]]:
    content, spec = set(), set()
    for scenario in scenarios:
        for step in scenario["steps"]:
            for text, is_spec in _strings(step["state"]):
                (spec if is_spec else content).add(text)
        # Question instructions are specification; criteria name instance options (files, teams, slides) and are not.
        spec.update(question["instructions"] for question in scenario["questions"].values())
    return {t for t in content if not _template(t)}, spec


def leakage(train: list[dict], evaluation: list[dict] | None = None) -> list[str]:
    """Every way the training scenarios repeat evaluation instance content; empty if none."""
    evaluation = eval_scenarios() if evaluation is None else evaluation
    issues = []
    eval_ids = {s["episode_id"] for s in evaluation} | {s["scenario_id"] for s in evaluation}
    eval_titles = {s["title"].lower() for s in evaluation}
    eval_states = {digest(step["state"]) for s in evaluation for step in s["steps"]}
    eval_content, eval_spec = _content(evaluation)
    sentences = {" ".join(_words(t)) for t in eval_content if len(_words(t)) >= 4}
    shingles = {}
    for text in eval_content:
        words = _words(text)
        for i in range(len(words) - SHINGLE + 1):
            shingles.setdefault(" ".join(words[i:i + SHINGLE]), text)
    spec_text = " ".join(eval_spec)
    identifiers = {m.group() for t in eval_content for m in IDENTIFIER.finditer(t)}
    identifiers -= GENERIC_IDENTIFIERS | {i for i in identifiers if i in spec_text}
    for scenario in train:
        eid = scenario["episode_id"]
        if scenario["episode_id"] in eval_ids or scenario["scenario_id"] in eval_ids:
            issues.append(f"{eid}: episode or scenario id is an evaluation id")
        if scenario["title"].lower() in eval_titles:
            issues.append(f"{eid}: title repeats an evaluation title")
        content, _ = _content([scenario])
        for step in scenario["steps"]:
            if digest(step["state"]) in eval_states:
                issues.append(f"{eid} t={step['t']}: state equals an evaluation state")
        for text in sorted(content):
            words = _words(text)
            if " ".join(words) in sentences:
                issues.append(f"{eid}: repeats evaluation text {text!r}")
                continue
            for i in range(len(words) - SHINGLE + 1):
                run = " ".join(words[i:i + SHINGLE])
                if run in shingles:
                    issues.append(f"{eid}: {text!r} shares {run!r} with evaluation text {shingles[run]!r}")
                    break
            for match in IDENTIFIER.finditer(text):
                if match.group() in identifiers:
                    issues.append(f"{eid}: {text!r} uses evaluation identifier {match.group()!r}")
    return sorted(set(issues))


def check_module(module) -> dict:
    """Validate one training module; raise on any structural, reference or leakage failure."""
    scenarios = module.scenarios()
    if not scenarios:
        raise ValueError(f"{module.__name__}: no scenarios")
    summaries = []
    for scenario in scenarios:
        eid = scenario["episode_id"]
        if not eid.startswith("train_"):
            raise ValueError(f"{eid}: training episode ids start with train_")
        if scenario["task_family"] not in FAMILIES:
            raise ValueError(f"{eid}: unknown task family {scenario['task_family']!r}")
        if scenario["tick_seconds"] != 2.0 or len(scenario["steps"]) != 60:
            raise ValueError(f"{eid}: training scenarios have 60 ticks of 2 s")
        for step in scenario["steps"]:
            state = copy.deepcopy(step["state"])
            if module.reference(state) != step["gold"]:
                raise ValueError(f"{eid} t={step['t']}: stored gold differs from the public reference")
            if state != step["state"]:
                raise ValueError(f"{eid} t={step['t']}: reference mutates its input")
            if not {"gold", "hidden", "answer"}.isdisjoint(step["state"]):
                raise ValueError(f"{eid} t={step['t']}: state exposes a private field")
        summary = validate_episode(encode_scenario(scenario))
        summary["task_family"] = scenario["task_family"]
        summary["answer_values"] = {
            q: sorted({s["gold"][q] for s in scenario["steps"]}) for q in scenario["questions"]}
        summaries.append(summary)
    issues = leakage(scenarios)
    if issues:
        raise ValueError("evaluation content leaks into training:\n" + "\n".join(issues))
    return {"module": module.__name__, "episodes": summaries}
