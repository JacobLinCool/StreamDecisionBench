"""Clef's native System One interface through the Workers AI REST API."""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

from streamdecisionbench.adapters.base import FatalAdapterError
from streamdecisionbench.jev import ContractError


class CloudflareAPIError(FatalAdapterError):
    """An API rejection, which the benchmark does not retry as a network failure."""

    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"Cloudflare Workers AI rejected the request (HTTP {status_code})")


class CloudflareAdapter:
    """Preserve Clef's probabilities and usage; let the runner own all retries."""

    def __init__(
        self,
        model: str = "clef",
        *,
        account_id: str | None = None,
        auth_token: str | None = None,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ):
        if model not in {"clef", "clef-flash"}:
            raise ValueError("Cloudflare model must be clef or clef-flash")
        account_id = account_id if account_id is not None else os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        auth_token = auth_token if auth_token is not None else os.environ.get("CLOUDFLARE_AUTH_TOKEN")
        if not account_id or not re.fullmatch(r"[0-9a-fA-F]{32}", account_id):
            raise ValueError("CLOUDFLARE_ACCOUNT_ID must be a 32-character hexadecimal account ID")
        if not auth_token:
            raise ValueError("CLOUDFLARE_AUTH_TOKEN is required")
        self.model = model
        self.name = f"cloudflare:{model}"
        self.url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/cloudflare/{model}"
        self.client = httpx.Client(
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=timeout,
            transport=transport if transport is not None else httpx.HTTPTransport(retries=0),
        )

    def start_episode(self, session: str) -> None:
        return None

    def system_one(self, request: dict[str, Any]) -> dict[str, Any]:
        body = {"model": self.model, "state": request["state"], "questions": request["questions"]}
        try:
            response = self.client.post(self.url, json=body)
        except httpx.TimeoutException as error:
            raise TimeoutError("Cloudflare Workers AI request timed out") from error
        except (httpx.NetworkError, httpx.RemoteProtocolError) as error:
            raise ConnectionError("Cloudflare Workers AI connection failed") from error
        if not response.is_success:
            raise CloudflareAPIError(response.status_code)
        envelope = response.json()
        if not isinstance(envelope, dict) or envelope.get("success") is not True:
            raise CloudflareAPIError(response.status_code)
        result = envelope.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("model"), str) or not result["model"]:
            raise ContractError("Cloudflare response must include a served model")
        if not isinstance(result.get("answers"), dict):
            raise ContractError("Cloudflare response must include answers")
        usage = result.get("usage")
        if not isinstance(usage, dict) or any(
            type(usage.get(key)) is not int or usage[key] < 0 for key in ("input_tokens", "output_tokens")
        ):
            raise ContractError("Cloudflare response must include nonnegative input and output token counts")
        return result

    def close(self) -> None:
        self.client.close()
