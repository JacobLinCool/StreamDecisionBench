"""Google's Gemini Decisions API, normalized to the benchmark's System One contract.

The wire format is nearly System One already: questions go out as a keyed map of
noul, choice and score questions and come back as a keyed map of answers. The
state goes in as JSON text; question text, option descriptions and score levels
go in as text because the API takes text only there. A safety block rejects the
whole request, so every question of a blocked request becomes a refusal that
commits to no option and scores as wrong wherever the decision uses it. Retries
belong to the benchmark runner.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from streamdecisionbench.adapters.base import FatalAdapterError, RetryableHTTPError, StatelessAdapter
from streamdecisionbench.adapters.fastino import retry_after_seconds
from streamdecisionbench.jev import ContractError, validate_request

MODEL = "gemini-decision-1"
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
# Documented error codes of a request blocked by safety filters (HTTP 400).
BLOCK_CODES = frozenset({"safety", "prohibited_content", "blocklist", "image_safety", "content_blocked"})


class GeminiDecisionsAPIError(FatalAdapterError):
    def __init__(self, status_code: int, request_id: str | None):
        self.status_code, self.request_id = status_code, request_id
        super().__init__(f"Gemini Decisions rejected the request (HTTP {status_code})")


def _text(value: Any) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def to_native(request: dict[str, Any]) -> dict[str, Any]:
    questions = {}
    for name, q in request["questions"].items():
        native: dict[str, Any] = {"type": q["type"], "instructions": _text(q["instructions"])}
        criteria = q.get("criteria")
        if q["type"] == "choice":
            native["criteria"] = {option: _text(description) for option, description in criteria.items()}
        elif q["type"] == "score":
            native["criteria"] = [_text(level) for level in criteria]
        elif criteria:
            native["criteria"] = {f"{side}_description": _text(criteria[side])
                                  for side in ("true", "false") if side in criteria}
        questions[name] = native
    return {"model": MODEL, "input": _text(request["state"]), "questions": questions}


def from_native(result: dict[str, Any], questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    native = result.get("answers")
    if not isinstance(native, dict) or set(native) != set(questions):
        raise ContractError("Gemini Decisions must answer exactly the requested questions")
    answers = {}
    for key, question in questions.items():
        answer = native[key]
        if not isinstance(answer, dict) or answer.get("type") != question["type"]:
            raise ContractError(f"answer {key!r}: type does not match its question")
        if question["type"] == "noul":
            answers[key] = {"type": "noul", "noul": answer.get("noul")}
        else:
            probs = answer.get("probabilities")
            if not isinstance(probs, dict):
                raise ContractError(f"answer {key!r}: probabilities must be a map")
            field = "choice" if question["type"] == "choice" else "score"
            answers[key] = {"type": question["type"], field: answer.get(field),
                            "confidence": answer.get("confidence"),
                            "probabilities": {str(k): v for k, v in probs.items()}}
    return answers


def _block_code(response: httpx.Response) -> str | None:
    try:
        error = response.json().get("error")
    except (ValueError, AttributeError):
        return None
    code = error.get("code") if isinstance(error, dict) else None
    return code if code in BLOCK_CODES else None


class GeminiDecisionsAdapter(StatelessAdapter):
    def __init__(self, model: str = MODEL, *, api_key: str | None = None,
                 base_url: str | None = None, timeout: float = 20.0,
                 transport: httpx.BaseTransport | None = None):
        if model != MODEL:
            raise ValueError(f"Gemini Decisions model must be {MODEL}")
        key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY is required")
        endpoint = base_url if base_url is not None else os.environ.get("GEMINI_BASE_URL") or BASE_URL
        self.model, self.name = model, f"gemini-decisions:{model}"
        self.client = httpx.Client(
            base_url=endpoint.rstrip("/"), headers={"x-goog-api-key": key}, timeout=timeout,
            transport=transport if transport is not None else httpx.HTTPTransport(retries=0),
        )

    def system_one(self, request: dict[str, Any]) -> dict[str, Any]:
        validate_request(request)
        try:
            response = self.client.post("/decisions", json=to_native(request))
        except httpx.TimeoutException as error:
            raise TimeoutError("Gemini Decisions request timed out") from error
        except (httpx.NetworkError, httpx.RemoteProtocolError) as error:
            raise ConnectionError("Gemini Decisions connection failed") from error
        request_id = response.headers.get("x-request-id")
        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableHTTPError(response.status_code, retry_after_seconds(response.headers.get("Retry-After")),
                                     request_id)
        if response.status_code == 400 and (code := _block_code(response)):
            # The API blocks the whole request; each question is then declined.
            return {"model": self.model, "request_id": request_id, "blocked": code,
                    "answers": {key: {"type": q["type"], "refusal": True} for key, q in request["questions"].items()},
                    "usage": {"input_tokens": 0, "cached_tokens": 0, "cache_write_tokens": 0,
                              "output_tokens": 0, "reasoning_tokens": 0}}
        if not response.is_success:
            raise GeminiDecisionsAPIError(response.status_code, request_id)
        try:
            result = response.json()
        except ValueError:
            raise ContractError("Gemini Decisions returned invalid JSON") from None
        if not isinstance(result, dict):
            raise ContractError("Gemini Decisions response must be an object")
        usage = result.get("usage")
        counts = {"input_tokens": usage.get("total_input_tokens") if isinstance(usage, dict) else None,
                  "output_tokens": usage.get("total_output_tokens") if isinstance(usage, dict) else None}
        if any(type(v) is not int or v < 0 for v in counts.values()):
            raise ContractError("Gemini Decisions response must include nonnegative token counts")
        # The API echoes no model name; the endpoint serves only the requested model.
        return {"model": self.model, "answers": from_native(result, request["questions"]),
                "usage": {**counts, "cached_tokens": 0, "cache_write_tokens": 0, "reasoning_tokens": 0},
                "request_id": request_id}

    def close(self) -> None:
        self.client.close()
