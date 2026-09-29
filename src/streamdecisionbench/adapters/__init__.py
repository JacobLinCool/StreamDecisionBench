"""Adapter registry. Specs are strings such as ``random``, ``oracle-noisy:0.1``,
``oracle-lag:2``, ``lagged-sticky:3``, ``copy-human``, ``jev:jev-latest``,
``jev:jev-latest@http://127.0.0.1:8787``, ``http:http://host:port`` or
``openai:gpt-5.6-luna@low``."""

from __future__ import annotations

import os
from typing import Any, Callable, Sequence

from streamdecisionbench.adapters.base import Adapter, FatalAdapterError, StatelessAdapter
from streamdecisionbench.adapters.local import (
    CopyHumanAdapter,
    FirstOptionAdapter,
    LexicalAdapter,
    OracleAdapter,
    RandomAdapter,
    StickyAdapter,
)

__all__ = ["Adapter", "FatalAdapterError", "StatelessAdapter", "make_adapter_factory"]


def make_adapter_factory(spec: str, episodes: Sequence[dict[str, Any]] = ()) -> Callable[[], Adapter]:
    """A zero-argument factory; the evaluator builds one adapter per worker."""
    name, _, arg = spec.partition(":")
    if name == "random":
        return lambda: RandomAdapter(seed=int(arg or 0))
    if name == "first":
        return FirstOptionAdapter
    if name == "sticky":
        return lambda: StickyAdapter(seed=int(arg or 0))
    if name == "lexical":
        return LexicalAdapter
    if name == "oracle":
        return OracleAdapter(episodes).fork
    if name == "oracle-noisy":
        return OracleAdapter(episodes, noise=float(arg or 0.1)).fork
    if name in ("oracle-lag", "oracle-lead", "lagged-sticky"):
        k = int(arg or (3 if name == "lagged-sticky" else 1))
        if k < 0:
            raise ValueError(f"{name} needs a tick count >= 0, e.g. {name}:2")
        oracle = OracleAdapter(episodes, shift=k if name == "oracle-lead" else -k)
        if name == "lagged-sticky":
            oracle.name = f"lagged-sticky:{k}"
        return oracle.fork
    if name == "copy-human":
        adapter = CopyHumanAdapter(episodes)
        return lambda: adapter
    if name == "jev":
        from streamdecisionbench.adapters.remote import TypeSafeAdapter

        model, _, base_url = arg.partition("@")
        return lambda: TypeSafeAdapter(model=model or "jev-latest", base_url=base_url or None)
    if name == "http":
        from streamdecisionbench.adapters.remote import HTTPAdapter

        return lambda: HTTPAdapter(base_url=arg)
    if name == "claude-cli":
        from streamdecisionbench.adapters.llm import ClaudeCLIAdapter

        model, _, effort = arg.partition("@")
        return lambda: ClaudeCLIAdapter(model=model or "haiku", effort=effort or None)
    if name == "anthropic":
        from streamdecisionbench.adapters.llm import AnthropicAdapter

        return lambda: AnthropicAdapter(model=arg)
    if name == "openai":
        from streamdecisionbench.adapters.llm import OpenAIAdapter

        model, _, effort = arg.partition("@")
        if not model:
            raise ValueError("openai needs a model, e.g. openai:gpt-5.6-luna or openai:gpt-5.6-luna@low")
        if not os.environ.get("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY is not set: add it to .env (see .env.example) or export it")
        return lambda: OpenAIAdapter(model=model, effort=effort or None)
    raise ValueError(f"unknown adapter spec {spec!r}")
