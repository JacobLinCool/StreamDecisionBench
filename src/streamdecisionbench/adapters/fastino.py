"""GLiDE's native decisions, normalized to the benchmark's System One contract."""

from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from streamdecisionbench.adapters.base import FatalAdapterError, RetryableHTTPError, StatelessAdapter
from streamdecisionbench.jev import ContractError, validate_request, validate_response

MODEL = "fastino/GLiDE"
BASE_URL = "https://api.fastino.ai"


def retry_after_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    try:
        if value.isascii() and value.isdigit():
            seconds = float(value)
        else:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                raise ValueError
            seconds = max(0.0, (date - datetime.now(timezone.utc)).total_seconds())
        if not math.isfinite(seconds):
            raise ValueError
        return seconds
    except (ValueError, TypeError, OverflowError):
        raise ContractError("Fastino returned an invalid Retry-After header") from None


class FastinoAPIError(FatalAdapterError):
    def __init__(self, status_code: int, request_id: str | None):
        self.status_code, self.request_id = status_code, request_id
        super().__init__(f"Fastino rejected the request (HTTP {status_code})")


class FastinoAdapter(StatelessAdapter):
    def __init__(self, model: str = MODEL, *, api_key: str | None = None,
                 base_url: str | None = None, timeout: float = 300.0,
                 transport: httpx.BaseTransport | None = None):
        if model != MODEL:
            raise ValueError(f"Fastino decision model must be {MODEL}")
        key = api_key if api_key is not None else os.environ.get("FASTINO_API_KEY")
        if not key:
            raise ValueError("FASTINO_API_KEY is required")
        endpoint = base_url if base_url is not None else os.environ.get("FASTINO_BASE_URL", BASE_URL)
        self.model, self.name = model, f"fastino:{model}"
        self.client = httpx.Client(
            base_url=endpoint.rstrip("/"), headers={"X-API-Key": key}, timeout=timeout,
            transport=transport if transport is not None else httpx.HTTPTransport(retries=0),
        )

    def system_one(self, request: dict[str, Any]) -> dict[str, Any]:
        validate_request(request)
        if not request["state"]:
            raise ContractError("Fastino requires a non-empty state")
        for question in request["questions"].values():
            if not isinstance(question["instructions"], str) or not question["instructions"].strip():
                raise ContractError("Fastino requires non-empty text instructions")
            criteria = question.get("criteria")
            descriptions = criteria.values() if isinstance(criteria, dict) else criteria or []
            if any(not isinstance(description, str) for description in descriptions):
                raise ContractError("Fastino criteria descriptions must be strings")
        body = {"model": self.model, "state": request["state"], "questions": request["questions"]}
        try:
            response = self.client.post("/v1/systemone", json=body)
        except httpx.TimeoutException as error:
            raise TimeoutError("Fastino request timed out") from error
        except (httpx.NetworkError, httpx.RemoteProtocolError) as error:
            raise ConnectionError("Fastino connection failed") from error
        request_id = response.headers.get("x-request-id")
        if response.status_code in {425, 429, 503}:
            delay = retry_after_seconds(response.headers.get("Retry-After"))
            if response.status_code == 425:
                delay = max(60.0, delay or 0.0)
            raise RetryableHTTPError(response.status_code, delay, request_id)
        if not response.is_success:
            raise FastinoAPIError(response.status_code, request_id)
        try:
            result = response.json()
        except ValueError:
            raise ContractError("Fastino returned invalid JSON") from None
        if not isinstance(result, dict) or result.get("model") != "glide":
            raise ContractError("Fastino response must identify the served model as glide")
        answers = result.get("answers")
        if not isinstance(answers, dict) or set(answers) != set(request["questions"]):
            raise ContractError("Fastino response must answer exactly the requested questions")
        usage = result.get("usage")
        if not isinstance(usage, dict) or any(
            type(usage.get(key)) is not int or usage[key] < 0 for key in ("input_tokens", "output_tokens")
        ):
            raise ContractError("Fastino response must include nonnegative token counts")
        for key, question in request["questions"].items():
            answer = answers[key]
            if not isinstance(answer, dict):
                raise ContractError("Fastino answers must be objects")
            if question["type"] == "score":
                winner = answer.get("score")
                probabilities = answer.get("probabilities")
                if (type(winner) is not int or not 0 <= winner < len(question["criteria"])
                        or not isinstance(probabilities, dict)):
                    raise ContractError("Fastino score must be a valid winning level index")
                expected = answer.get("expected_level")
                if type(expected) not in {int, float} or not math.isfinite(expected):
                    raise ContractError("Fastino score requires a finite expected_level")
                # Preserve the native winner and expectation alongside the shared score field.
                answers[key] = {**answer, "native_score": winner, "score": expected}
        validate_response(result, request["questions"])
        for key, question in request["questions"].items():
            if question["type"] == "score":
                answer = answers[key]
                probs = answer["probabilities"]
                if probs[str(answer["native_score"])] < max(probs.values()) - 1e-9:
                    raise ContractError("Fastino native score must be a most probable level")
        result["request_id"] = request_id
        return result

    def close(self) -> None:
        self.client.close()
