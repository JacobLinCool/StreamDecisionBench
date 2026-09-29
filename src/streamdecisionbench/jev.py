"""The Jev-compatible System One wire format.

Every benchmark step is one System One request: a ``state`` and a map of typed
``questions`` (choice, score, noul). A model answers with one typed answer per
question, exactly as TypeSafe's ``POST /v1/systemone`` does. Any model can take
part in the benchmark by speaking this format; Jev speaks it natively.
"""

from __future__ import annotations

import math
from typing import Any

QUESTION_TYPES = ("choice", "score", "noul")
MAX_CHOICE_OPTIONS = 255
MIN_SCORE_LEVELS = 2
MAX_SCORE_LEVELS = 10

# The API reports probabilities, confidences and scores rounded to two decimals.
# Consistency checks tolerate exactly that rounding: half a step per term.
REPORTED_STEP = 0.01

INVALID = "<invalid>"


class ContractError(ValueError):
    """A request or response that breaks the System One contract."""


def _is_entry(value: Any) -> bool:
    return isinstance(value, (str, dict, list))


def validate_question(key: str, question: dict[str, Any]) -> None:
    kind = question.get("type")
    if kind not in QUESTION_TYPES:
        raise ContractError(f"question {key!r}: unknown type {kind!r}")
    if "instructions" not in question or not _is_entry(question["instructions"]):
        raise ContractError(f"question {key!r}: instructions must be text, an object or an array")
    criteria = question.get("criteria")
    if kind == "choice":
        if not isinstance(criteria, dict) or not criteria:
            raise ContractError(f"choice {key!r}: criteria must be a non-empty map")
        if len(criteria) > MAX_CHOICE_OPTIONS:
            raise ContractError(f"choice {key!r}: at most {MAX_CHOICE_OPTIONS} options")
        for option, description in criteria.items():
            if not isinstance(option, str) or not option:
                raise ContractError(f"choice {key!r}: option labels must be non-empty strings")
            if description is not None and not _is_entry(description):
                raise ContractError(f"choice {key!r}: option {option!r} has an invalid description")
    elif kind == "score":
        if not isinstance(criteria, list) or not MIN_SCORE_LEVELS <= len(criteria) <= MAX_SCORE_LEVELS:
            raise ContractError(
                f"score {key!r}: criteria must list {MIN_SCORE_LEVELS}-{MAX_SCORE_LEVELS} levels"
            )
        if not all(_is_entry(level) for level in criteria):
            raise ContractError(f"score {key!r}: every level must be text, an object or an array")
    else:
        if criteria is not None:
            if not isinstance(criteria, dict) or set(criteria) - {"true", "false"}:
                raise ContractError(f"noul {key!r}: criteria may only describe 'true' and 'false'")


def validate_request(request: dict[str, Any]) -> None:
    state = request.get("state")
    if not isinstance(state, (str, dict, list)):
        raise ContractError("state must be a string, an object or an array")
    questions = request.get("questions")
    if not isinstance(questions, dict) or not questions:
        raise ContractError("questions must be a non-empty map")
    for key, question in questions.items():
        validate_question(key, question)


def _probability(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= 1


def _distribution(probabilities: Any, expected: set[str], key: str) -> dict[str, float]:
    if not isinstance(probabilities, dict):
        raise ContractError(f"answer {key!r}: probabilities must be a map")
    probs = {str(k): v for k, v in probabilities.items()}
    if set(probs) != expected:
        raise ContractError(f"answer {key!r}: probabilities must cover exactly the defined options")
    if not all(_probability(p) for p in probs.values()):
        raise ContractError(f"answer {key!r}: probabilities must lie in [0, 1]")
    tolerance = REPORTED_STEP / 2 * len(expected) + 1e-9
    if not math.isclose(sum(probs.values()), 1.0, abs_tol=tolerance):
        raise ContractError(f"answer {key!r}: probabilities must sum to 1")
    return probs


def validate_response(response: dict[str, Any], questions: dict[str, dict[str, Any]]) -> None:
    """Check a response against the full decision contract of its request.

    Mirrors the checks a careful Jev client applies before letting an answer into
    a benchmark: exactly one answer per question, of the right type, with a
    well-formed probability distribution whose argmax is the reported choice.
    """
    answers = response.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise ContractError("response must answer exactly the requested questions")
    for key, question in questions.items():
        answer = answers[key]
        if not isinstance(answer, dict) or answer.get("type") != question["type"]:
            raise ContractError(f"answer {key!r}: type does not match its question")
        if question["type"] == "noul":
            if not _probability(answer.get("noul")):
                raise ContractError(f"answer {key!r}: noul must be a probability")
            continue
        if not _probability(answer.get("confidence")):
            raise ContractError(f"answer {key!r}: confidence must be a probability")
        if question["type"] == "choice":
            expected = set(question["criteria"])
            probs = _distribution(answer.get("probabilities"), expected, key)
            choice = answer.get("choice")
            if choice not in expected:
                raise ContractError(f"answer {key!r}: choice is not a defined option")
            # Rounded (and renormalised) reports can show a near-tie choice one
            # step below another option; allow exactly that much.
            if probs[choice] < max(probs.values()) - REPORTED_STEP - 1e-9:
                raise ContractError(f"answer {key!r}: choice is not the most probable option")
        else:
            levels = len(question["criteria"])
            expected = {str(i) for i in range(levels)}
            probs = _distribution(answer.get("probabilities"), expected, key)
            score = answer.get("score")
            if not isinstance(score, (int, float)) or not math.isfinite(score):
                raise ContractError(f"answer {key!r}: score must be a number")
            expectation = sum(int(i) * p for i, p in probs.items())
            tolerance = REPORTED_STEP / 2 * (1 + sum(range(levels))) + 1e-9
            if not math.isclose(score, expectation, abs_tol=tolerance):
                raise ContractError(f"answer {key!r}: score is not the expected level")


def score_level(answer: dict[str, Any]) -> int:
    """The level a score answer commits to: the most probable one (lowest on ties)."""
    probs = {int(k): v for k, v in answer["probabilities"].items()}
    best = max(probs.values())
    return min(level for level, p in probs.items() if p == best)


def committed_answer(question: dict[str, Any], answer: dict[str, Any]) -> str | int | bool:
    """The discrete decision an answer commits to, in the question's own terms."""
    if question["type"] == "choice":
        return answer["choice"]
    if question["type"] == "score":
        return score_level(answer)
    return answer["noul"] >= 0.5


# ---------------------------------------------------------------------------
# Answer construction, used by local baselines and the mock server.
# ---------------------------------------------------------------------------


def _round_distribution(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0 or not math.isfinite(total):
        weights = {k: 1.0 for k in weights}
        total = float(len(weights))
    probs = {k: max(v, 0.0) / total for k, v in weights.items()}
    # Round to the reported precision while keeping the sum within tolerance.
    rounded = {k: round(p, 2) for k, p in probs.items()}
    drift = round(1.0 - sum(rounded.values()), 2)
    if drift:
        top = max(rounded, key=lambda k: probs[k])
        rounded[top] = round(min(max(rounded[top] + drift, 0.0), 1.0), 2)
    return rounded


def _confidence(probs: dict[str, float]) -> float:
    """A peakedness summary in [0, 1]: 1 - normalised entropy."""
    n = len(probs)
    if n <= 1:
        return 1.0
    entropy = -sum(p * math.log(p) for p in probs.values() if p > 0)
    return round(max(0.0, 1.0 - entropy / math.log(n)), 2)


def make_answer(question: dict[str, Any], weights: dict[str, float] | float) -> dict[str, Any]:
    """Build a contract-valid answer from unnormalised weights.

    ``weights`` maps option labels (choice) or level indices as strings (score)
    to non-negative weights; for a noul it is the probability of yes.
    """
    kind = question["type"]
    if kind == "noul":
        assert isinstance(weights, (int, float))
        return {"type": "noul", "noul": round(min(max(float(weights), 0.0), 1.0), 2)}
    assert isinstance(weights, dict)
    probs = _round_distribution(weights)
    if kind == "choice":
        choice = max(probs, key=lambda k: (probs[k], -list(probs).index(k)))
        return {"type": "choice", "choice": choice, "probabilities": probs, "confidence": _confidence(probs)}
    levels = len(question["criteria"])
    probs = {str(i): probs.get(str(i), 0.0) for i in range(levels)}
    score = round(sum(int(i) * p for i, p in probs.items()), 2)
    return {
        "type": "score",
        "score": score,
        "legend": {str(i): level for i, level in enumerate(question["criteria"])},
        "probabilities": probs,
        "confidence": _confidence(probs),
    }
