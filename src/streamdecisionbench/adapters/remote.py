"""Remote System One models: TypeSafe Jev and any Jev-compatible endpoint.

``TypeSafeAdapter`` goes through the official ``typesafe_sdk`` client, so the
exact code path used against real Jev can be exercised against the local mock
server (``sdb serve-mock``) by pointing ``base_url`` at it.
``HTTPAdapter`` is a dependency-light client for any server that implements
``POST /v1/systemone``.
"""

from __future__ import annotations

import os
from typing import Any

import httpx


def _builtins(obj: Any) -> Any:
    """SDK answer/usage objects (pydantic in typesafe-sdk>=0.7, msgspec before) to plain JSON data."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    try:
        import msgspec

        return msgspec.to_builtins(obj)
    except ImportError:  # pragma: no cover
        return dict(obj)


def _normalise(answer: dict[str, Any]) -> dict[str, Any]:
    out = dict(answer)
    for field in ("probabilities", "legend"):
        if isinstance(out.get(field), dict):
            out[field] = {str(k): v for k, v in out[field].items()}
    return out


class TypeSafeAdapter:
    """TypeSafe's Jev (or the mock server) through the official Python SDK."""

    def __init__(
        self,
        model: str = "jev-latest",
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
        max_retries: int | None = None,
    ):
        from typesafe_sdk import RetryPolicy, TypeSafeClient

        retry = RetryPolicy(max_retries=max_retries) if max_retries is not None else None
        self.client = TypeSafeClient(
            model=model,
            base_url=base_url,
            api_key=api_key or os.environ.get("TYPESAFE_API_KEY"),
            timeout=timeout,
            retry=retry,
        )
        self.name = f"typesafe:{model}"

    def start_episode(self, session: str) -> None:
        return None

    def system_one(self, request: dict[str, Any]) -> dict[str, Any]:
        response = self.client.system_one(state=request["state"], questions=request["questions"])
        answers = {k: _normalise(_builtins(v)) for k, v in response.answers.items()}
        usage = _builtins(response.usage)
        return {"model": response.model, "answers": answers, "usage": usage}

    def close(self) -> None:
        self.client.close()


class HTTPAdapter:
    """Any Jev-compatible ``POST /v1/systemone`` endpoint."""

    def __init__(self, base_url: str, model: str = "jev-latest", api_key: str | None = None, timeout: float = 30.0):
        headers = {"Content-Type": "application/json"}
        key = api_key or os.environ.get("TYPESAFE_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        self.client = httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=timeout)
        self.model = model
        self.name = f"http:{model}"

    def start_episode(self, session: str) -> None:
        return None

    def system_one(self, request: dict[str, Any]) -> dict[str, Any]:
        body = {"state": request["state"], "questions": request["questions"], "model": self.model}
        response = self.client.post("/v1/systemone", json=body)
        response.raise_for_status()
        data = response.json()
        data["answers"] = {k: _normalise(v) for k, v in data.get("answers", {}).items()}
        return data

    def close(self) -> None:
        self.client.close()
