"""Perplexity native decisions; retries belong to the benchmark runner."""

from __future__ import annotations

import math
import os
from typing import Any

import httpx

from streamdecisionbench.adapters.base import FatalAdapterError, RateLimitError, StatelessAdapter
from streamdecisionbench.jev import ContractError

MODEL = "pplx-decider-v1-27b"
BASE_URL = "https://api.perplexity.ai"


class PerplexityAPIError(FatalAdapterError):
    def __init__(self, status_code: int, request_id: str | None):
        self.status_code, self.request_id = status_code, request_id
        super().__init__(f"Perplexity rejected the request (HTTP {status_code})")


class PerplexityServiceError(ConnectionError):
    def __init__(self, status_code: int, request_id: str | None):
        self.status_code, self.request_id = status_code, request_id
        super().__init__(f"Perplexity service failed (HTTP {status_code})")


class PerplexityAdapter(StatelessAdapter):
    def __init__(self, model: str = MODEL, *, api_key: str | None = None,
                 base_url: str | None = None, timeout: float = 30.0,
                 transport: httpx.BaseTransport | None = None):
        if model != MODEL:
            raise ValueError(f"Perplexity Decisions model must be {MODEL}")
        key = api_key if api_key is not None else os.environ.get("PERPLEXITY_API_KEY")
        if not key:
            raise ValueError("PERPLEXITY_API_KEY is required")
        endpoint = base_url if base_url is not None else os.environ.get("PERPLEXITY_BASE_URL", BASE_URL)
        self.model, self.name = model, f"perplexity:{model}"
        self.client = httpx.Client(
            base_url=endpoint.rstrip("/"), headers={"Authorization": f"Bearer {key}"},
            timeout=timeout,
            transport=transport if transport is not None else httpx.HTTPTransport(retries=0),
        )

    def system_one(self, request: dict[str, Any]) -> dict[str, Any]:
        body = {"model": self.model, "state": request["state"], "questions": request["questions"]}
        try:
            response = self.client.post("/v1/decisions", json=body)
        except httpx.TimeoutException as error:
            raise TimeoutError("Perplexity request timed out") from error
        except (httpx.NetworkError, httpx.RemoteProtocolError) as error:
            raise ConnectionError("Perplexity connection failed") from error
        request_id = response.headers.get("x-request-id")
        if response.status_code == 429:
            header = response.headers.get("Retry-After")
            delay = None
            if header is not None:
                if not header.strip().isascii() or not header.strip().isdigit():
                    raise ContractError("Perplexity Retry-After must be integer seconds")
                try:
                    delay = float(header)
                except (ValueError, OverflowError):
                    raise ContractError("Perplexity Retry-After must be finite") from None
                if not math.isfinite(delay):
                    raise ContractError("Perplexity Retry-After must be finite")
            error = RateLimitError(delay)
            error.request_id = request_id
            raise error
        if response.status_code >= 500:
            raise PerplexityServiceError(response.status_code, request_id)
        if not response.is_success:
            raise PerplexityAPIError(response.status_code, request_id)
        try:
            result = response.json()
        except ValueError:
            raise ContractError("Perplexity returned invalid JSON") from None
        if not isinstance(result, dict) or result.get("model") != self.model:
            raise ContractError("Perplexity response must echo the requested model")
        if not isinstance(result.get("answers"), dict):
            raise ContractError("Perplexity response must include answers")
        usage = result.get("usage")
        if not isinstance(usage, dict) or any(
            type(usage.get(key)) is not int or usage[key] < 0 for key in ("input_tokens", "output_tokens")
        ):
            raise ContractError("Perplexity response must include nonnegative token counts")
        result["request_id"] = request_id
        return result

    def close(self) -> None:
        self.client.close()
