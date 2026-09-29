"""The model interface: one Jev-compatible System One call per tick.

An adapter receives exactly what the evaluated model is allowed to see (the
request's ``state`` and ``questions``) and returns a System One response. It may
keep any private memory it likes between calls of the same episode; the
evaluator signals episode boundaries with ``start_episode``.
"""

from __future__ import annotations

from typing import Any, Protocol


class FatalAdapterError(RuntimeError):
    """A failure that would repeat on every tick (bad key, unknown model, rejected
    parameters). The evaluator stops the run instead of scoring it as wrong answers."""


class Adapter(Protocol):
    name: str

    def start_episode(self, session: str) -> None:
        """A new, unrelated stream begins. ``session`` is an opaque token."""

    def system_one(self, request: dict[str, Any]) -> dict[str, Any]:
        """Answer every question in ``request``; return a System One response body."""

    def close(self) -> None: ...


class StatelessAdapter:
    """Convenience base for adapters that keep no memory between ticks."""

    name = "stateless"

    def start_episode(self, session: str) -> None:
        return None

    def close(self) -> None:
        return None

    def answer(self, request: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def system_one(self, request: dict[str, Any]) -> dict[str, Any]:
        return {"model": self.name, "answers": self.answer(request), "usage": {"input_tokens": 0, "output_tokens": 0}}
