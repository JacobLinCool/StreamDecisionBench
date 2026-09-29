"""Generative LLMs behind the System One interface.

The LLM receives the request (state + questions) as JSON, answers with a JSON
object of committed answers, and the adapter wraps them as contract-valid
System One answers. Generative models expose no calibrated probabilities, so
answers are one-hot (confidence 1.0); calibration metrics are not meaningful
for these rows.

* ``claude-cli:<model>`` runs the local Claude Code CLI (``claude -p``) with all
  tools disabled; convenient for small reference runs, not for latency.
* ``anthropic:<model>`` calls the Anthropic Messages API (needs ``anthropic``
  installed and ``ANTHROPIC_API_KEY``).
* ``openai:<model>[@<effort>]`` calls the OpenAI Responses API with
  ``OPENAI_API_KEY`` (``OPENAI_BASE_URL`` points it at another compatible
  endpoint). Structured Outputs constrain the reply to the request's own option
  labels and level indices, and ``effort`` sets the reasoning effort
  (``none``, ``minimal``, ``low``, ...; the model's default when omitted).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any

from streamdecisionbench.adapters.base import FatalAdapterError, StatelessAdapter
from streamdecisionbench.jev import make_answer

SYSTEM = (
    "You are a real-time decision model. You receive one moment of a live task as JSON: "
    "`state` is everything observable now, `questions` are typed questions whose instructions "
    "hold the decision policy. Answer every question. Choice -> the option label (a key of its "
    "criteria). Score -> the 0-based index of a level in its criteria list. Noul -> true or false. "
    "Reply with ONLY a JSON object mapping question ids to answers, e.g. "
    '{"q1": "K4", "q2": 1, "q3": false}. No prose.'
)

_JSON = re.compile(r"\{.*\}", re.S)


def _parse(text: str) -> dict[str, Any]:
    match = _JSON.search(text)
    if not match:
        raise ValueError(f"no JSON object in model output: {text[:200]!r}")
    return json.loads(match.group(0))


def to_answers(request: dict[str, Any], committed: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for key, q in request["questions"].items():
        value = committed.get(key)
        if q["type"] == "choice":
            if value not in q["criteria"]:
                raise ValueError(f"{key}: {value!r} is not an option label")
            out[key] = make_answer(q, {k: (1.0 if k == value else 0.0) for k in q["criteria"]})
        elif q["type"] == "score":
            level = int(value)
            if not 0 <= level < len(q["criteria"]):
                raise ValueError(f"{key}: level {level} out of range")
            out[key] = make_answer(q, {str(i): (1.0 if i == level else 0.0) for i in range(len(q["criteria"]))})
        else:
            if isinstance(value, str):
                value = value.strip().lower() in ("true", "yes")
            out[key] = make_answer(q, 1.0 if value else 0.0)
    return out


class ClaudeCLIAdapter(StatelessAdapter):
    def __init__(self, model: str = "haiku", effort: str | None = None, timeout: float = 120.0):
        self.model = model
        self.effort = effort
        self.timeout = timeout
        self.name = f"claude-cli:{model}"

    def answer(self, request: dict[str, Any]) -> dict[str, Any]:
        cmd = [
            "claude", "-p", "--model", self.model, "--output-format", "json", "--tools", "",
            "--no-session-persistence", "--strict-mcp-config", "--setting-sources", "", "--system-prompt", SYSTEM,
        ]
        if self.effort:
            cmd += ["--effort", self.effort]
        proc = subprocess.run(
            cmd, input=json.dumps(request, ensure_ascii=False), capture_output=True, text=True, timeout=self.timeout
        )
        if proc.returncode != 0:
            raise RuntimeError(f"claude CLI failed: {proc.stderr.strip()[:300]}")
        envelope = json.loads(proc.stdout)
        return to_answers(request, _parse(envelope.get("result", "")))


class AnthropicAdapter(StatelessAdapter):
    def __init__(self, model: str, max_tokens: int = 256):
        import anthropic

        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        self.model = model
        self.max_tokens = max_tokens
        self.name = f"anthropic:{model}"

    def answer(self, request: dict[str, Any]) -> dict[str, Any]:
        message = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(request, ensure_ascii=False)}],
        )
        text = "".join(block.text for block in message.content if getattr(block, "type", "") == "text")
        return to_answers(request, _parse(text))


def answer_schema(request: dict[str, Any]) -> dict[str, Any]:
    """A strict JSON Schema admitting exactly the well-formed answers to ``request``.

    Labels are sorted, so the schema never depends on the displayed option
    order: that order is fixed per episode in sdb/0.2 and reshuffled every tick
    in legacy sdb/0.1. Labels are opaque, so sorting reveals nothing.
    """
    properties: dict[str, Any] = {}
    for key, q in request["questions"].items():
        if q["type"] == "choice":
            properties[key] = {"type": "string", "enum": sorted(q["criteria"])}
        elif q["type"] == "score":
            properties[key] = {"type": "integer", "enum": list(range(len(q["criteria"])))}
        else:
            properties[key] = {"type": "boolean"}
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


class OpenAIAdapter:
    """OpenAI models through the Responses API.

    The request goes in as JSON with ``questions`` before ``state``: the same
    content the other adapters send, ordered so the policy text that repeats
    at every tick forms a cacheable prefix. Responses are not stored
    (``store=False``); the episode's opaque session token is the prompt cache key.
    """

    def __init__(
        self,
        model: str,
        effort: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 300.0,
        max_retries: int = 8,
        client: Any = None,
    ):
        import openai

        self.client = client or openai.OpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=base_url or os.environ.get("OPENAI_BASE_URL") or None,
            timeout=timeout,
            max_retries=max_retries,
        )
        self.model = model
        self.effort = effort
        self.session: str | None = None
        self.name = f"openai:{model}" + (f"@{effort}" if effort else "")

    def start_episode(self, session: str) -> None:
        self.session = session

    def system_one(self, request: dict[str, Any]) -> dict[str, Any]:
        import openai

        params: dict[str, Any] = {
            "model": self.model,
            "instructions": SYSTEM,
            "input": json.dumps({"questions": request["questions"], "state": request["state"]}, ensure_ascii=False),
            "text": {"format": {"type": "json_schema", "name": "decision", "schema": answer_schema(request), "strict": True}},
            "store": False,
        }
        if self.effort:
            params["reasoning"] = {"effort": self.effort}
        if self.session:
            params["prompt_cache_key"] = self.session
        try:
            response = self.client.responses.create(**params)
        except (
            openai.AuthenticationError,
            openai.PermissionDeniedError,
            openai.NotFoundError,
            openai.BadRequestError,
            openai.UnprocessableEntityError,
        ) as error:
            raise FatalAdapterError(f"OpenAI rejected the request ({type(error).__name__}): {error}") from error
        if response.status not in (None, "completed"):
            reason = getattr(response.incomplete_details, "reason", None) or getattr(response.error, "message", None)
            raise RuntimeError(f"response {response.status}: {reason}")
        answers = to_answers(request, json.loads(response.output_text))
        usage = response.usage
        return {
            "model": response.model,
            "answers": answers,
            "usage": {
                "input_tokens": usage.input_tokens,
                "cached_tokens": usage.input_tokens_details.cached_tokens,
                "output_tokens": usage.output_tokens,
                "reasoning_tokens": usage.output_tokens_details.reasoning_tokens,
            }
            if usage
            else None,
        }

    def close(self) -> None:
        self.client.close()
