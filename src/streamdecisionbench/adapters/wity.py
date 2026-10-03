"""Wity's native System One API; the benchmark runner owns retries."""

from __future__ import annotations

import math
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from streamdecisionbench.adapters.base import FatalAdapterError, RateLimitError
from streamdecisionbench.jev import ContractError

BASE_URL = "https://wity-proxy-production-2c33.up.railway.app"


def retry_after_seconds(value: str | None) -> float | None:
    """Parse Retry-After's delay-seconds or HTTP-date, without retaining headers."""
    if value is None:
        return None
    value = value.strip()
    if re.fullmatch(r"[0-9]+", value):
        seconds = float(value)
        if not math.isfinite(seconds):
            raise ValueError("Wity Retry-After must be finite")
        return seconds
    try:
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            raise ValueError
        return max(0.0, (date - datetime.now(timezone.utc)).total_seconds())
    except (ValueError, TypeError, OverflowError):
        raise ValueError("Wity returned an invalid Retry-After header") from None


class WityAPIError(FatalAdapterError):
    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"Wity rejected the request (HTTP {status_code})")


class WityAdapter:
    def __init__(self, model: str = "wity-1", *, reasoning: str = "auto",
                 api_key: str | None = None, base_url: str | None = None,
                 timeout: float = 60.0, transport: httpx.BaseTransport | None = None):
        if model != "wity-1":
            raise ValueError("Wity model must be wity-1; the API does not select models")
        if reasoning not in {"auto", "off", "always"}:
            raise ValueError("Wity reasoning must be auto, off or always")
        key = api_key if api_key is not None else os.environ.get("WITY_API_KEY")
        if not key:
            raise ValueError("WITY_API_KEY is required")
        endpoint = base_url if base_url is not None else os.environ.get("WITY_BASE_URL", BASE_URL)
        self.name = f"wity:{model}"
        self.reasoning = reasoning
        self.client = httpx.Client(
            base_url=endpoint.rstrip("/"), headers={"Authorization": f"Bearer {key}"},
            timeout=timeout,
            transport=transport if transport is not None else httpx.HTTPTransport(retries=0),
        )

    def start_episode(self, session: str) -> None:
        return None

    def system_one(self, request: dict[str, Any]) -> dict[str, Any]:
        body = {"state": request["state"], "questions": request["questions"], "reasoning": self.reasoning}
        try:
            response = self.client.post("/v1/systemone", json=body)
        except httpx.TimeoutException as error:
            raise TimeoutError("Wity request timed out") from error
        except (httpx.NetworkError, httpx.RemoteProtocolError) as error:
            raise ConnectionError("Wity connection failed") from error
        if response.status_code == 429:
            raise RateLimitError(retry_after_seconds(response.headers.get("Retry-After")))
        if not response.is_success:
            raise WityAPIError(response.status_code)
        result = response.json()
        if not isinstance(result, dict) or not isinstance(result.get("model"), str) or not result["model"]:
            raise ContractError("Wity response must include a served model")
        if not isinstance(result.get("answers"), dict):
            raise ContractError("Wity response must include answers")
        usage = result.get("usage")
        if not isinstance(usage, dict) or any(
            type(usage.get(key)) is not int or usage[key] < 0 for key in ("input_tokens", "output_tokens")
        ):
            raise ContractError("Wity response must include nonnegative input and output token counts")
        return result

    def close(self) -> None:
        self.client.close()
