"""OpenAI's native Decisions API, normalized to the benchmark's System One contract.

The state goes in as JSON text and every question keeps its instructions and
option descriptions; answers come back as a list keyed by question name and are
mapped back to the System One answer map. A refused question commits to no
option and scores as wrong wherever the decision uses it. Retries belong to the
benchmark runner.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from streamdecisionbench.adapters.base import FatalAdapterError, RetryableHTTPError, StatelessAdapter
from streamdecisionbench.adapters.fastino import retry_after_seconds
from streamdecisionbench.jev import ContractError, validate_request

MODEL = "gpt-6-luna"
BASE_URL = "https://api.openai.com/v1"


class OpenAIDecisionsAPIError(FatalAdapterError):
    def __init__(self, status_code: int, request_id: str | None):
        self.status_code, self.request_id = status_code, request_id
        super().__init__(f"OpenAI Decisions rejected the request (HTTP {status_code})")


def to_native(request: dict[str, Any]) -> dict[str, Any]:
    questions = []
    for name, q in request["questions"].items():
        native: dict[str, Any] = {"name": name, "instructions": q["instructions"]}
        if q["type"] == "choice":
            native.update(type="choice", choices=[{"value": value, "description": description}
                                                  for value, description in q["criteria"].items()])
        elif q["type"] == "score":
            native.update(type="score", levels=[{"label": level} if isinstance(level, str) else level
                                                for level in q["criteria"]])
        else:
            native["type"] = "predicate"
        questions.append(native)
    state = request["state"]
    text = state if isinstance(state, str) else json.dumps(state, ensure_ascii=False)
    return {"model": MODEL, "input": text, "questions": questions}


def _distribution(entries: Any, key: str, field: str) -> dict[str, float]:
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        raise ContractError(f"answer {key!r}: probabilities must be a list of objects")
    probs = {str(e.get(field)): e.get("probability") for e in entries}
    if len(probs) != len(entries):
        raise ContractError(f"answer {key!r}: probabilities repeat an option")
    return probs


def from_native(result: dict[str, Any], questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    native = result.get("answers")
    if not isinstance(native, list) or not all(isinstance(a, dict) for a in native):
        raise ContractError("OpenAI Decisions answers must be a list of objects")
    by_name = {a.get("name"): a for a in native}
    if len(by_name) != len(native) or set(by_name) != set(questions):
        raise ContractError("OpenAI Decisions must answer exactly the requested questions")
    answers = {}
    for key, question in questions.items():
        answer = by_name[key]
        kind = {"choice": "choice", "score": "score", "noul": "predicate"}[question["type"]]
        if answer.get("type") == "refusal":
            # Undocumented but observed: the model declines one question and answers the rest.
            answers[key] = {"type": question["type"], "refusal": True}
            continue
        if answer.get("type") != kind:
            raise ContractError(f"answer {key!r}: type does not match its question")
        if kind == "predicate":
            answers[key] = {"type": "noul", "noul": answer.get("probability")}
        elif kind == "choice":
            answers[key] = {"type": "choice", "choice": answer.get("choice"), "confidence": answer.get("confidence"),
                            "probabilities": _distribution(answer.get("probabilities"), key, "value")}
        else:
            answers[key] = {"type": "score", "score": answer.get("score"), "confidence": answer.get("confidence"),
                            "probabilities": _distribution(answer.get("probabilities"), key, "value")}
    return answers


class OpenAIDecisionsAdapter(StatelessAdapter):
    def __init__(self, model: str = MODEL, *, api_key: str | None = None,
                 base_url: str | None = None, timeout: float = 20.0,
                 transport: httpx.BaseTransport | None = None):
        if model != MODEL:
            raise ValueError(f"OpenAI Decisions model must be {MODEL}")
        key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY is required")
        endpoint = base_url if base_url is not None else os.environ.get("OPENAI_BASE_URL") or BASE_URL
        self.model, self.name = model, f"openai-decisions:{model}"
        self.client = httpx.Client(
            base_url=endpoint.rstrip("/"), headers={"Authorization": f"Bearer {key}"}, timeout=timeout,
            transport=transport if transport is not None else httpx.HTTPTransport(retries=0),
        )

    def system_one(self, request: dict[str, Any]) -> dict[str, Any]:
        validate_request(request)
        try:
            response = self.client.post("/decisions", json=to_native(request))
        except httpx.TimeoutException as error:
            raise TimeoutError("OpenAI Decisions request timed out") from error
        except (httpx.NetworkError, httpx.RemoteProtocolError) as error:
            raise ConnectionError("OpenAI Decisions connection failed") from error
        request_id = response.headers.get("x-request-id")
        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableHTTPError(response.status_code, retry_after_seconds(response.headers.get("Retry-After")),
                                     request_id)
        if not response.is_success:
            raise OpenAIDecisionsAPIError(response.status_code, request_id)
        try:
            result = response.json()
        except ValueError:
            raise ContractError("OpenAI Decisions returned invalid JSON") from None
        served = result.get("model") if isinstance(result, dict) else None
        # A dated snapshot of the requested model is still the requested model.
        if not isinstance(served, str) or not (served == self.model or served.startswith(self.model + "-")):
            raise ContractError("OpenAI Decisions response must echo the requested model")
        usage = result.get("usage")
        details = usage.get("input_tokens_details") if isinstance(usage, dict) else None
        counts = {"input_tokens": usage.get("input_tokens") if isinstance(usage, dict) else None,
                  "cached_tokens": details.get("cached_tokens") if isinstance(details, dict) else None,
                  "cache_write_tokens": details.get("cache_write_tokens") if isinstance(details, dict) else None,
                  "output_tokens": usage.get("output_tokens") if isinstance(usage, dict) else None}
        if any(type(v) is not int or v < 0 for v in counts.values()):
            raise ContractError("OpenAI Decisions response must include nonnegative token counts")
        return {"model": result["model"], "answers": from_native(result, request["questions"]),
                "usage": {**counts, "reasoning_tokens": 0}, "request_id": request_id}

    def close(self) -> None:
        self.client.close()
