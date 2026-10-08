"""Claude models through the Anthropic Messages API, normalized to the System One contract.

The request goes in as two text blocks, ``questions`` then ``state``, with a
cache breakpoint after the questions: the policy text that repeats at every
tick forms a cacheable prefix. Structured outputs constrain the reply to the
request's own option labels and level indices (the same schema as the OpenAI
adapter). ``effort`` sets ``output_config.effort`` (the model's default when
omitted) and ``thinking`` is ``adaptive`` (the API default, sent by omission)
or ``disabled``.

A safeguard decline (``stop_reason: "refusal"``) is a valid response that
refuses every question: it commits to no option and scores as wrong wherever
the decision uses it. Retries belong to the benchmark runner; SDK retries are off.
"""

from __future__ import annotations

import json
import os
from typing import Any

from streamdecisionbench.adapters.base import FatalAdapterError, RetryableHTTPError
from streamdecisionbench.adapters.fastino import retry_after_seconds
from streamdecisionbench.adapters.llm import SYSTEM, answer_schema, to_answers
from streamdecisionbench.jev import ContractError, validate_request

EFFORTS = ("low", "medium", "high", "xhigh", "max")
THINKING = ("adaptive", "disabled")


class AnthropicAdapter:
    def __init__(self, model: str, *, effort: str | None = None, thinking: str = "adaptive",
                 api_key: str | None = None, base_url: str | None = None, timeout: float = 20.0,
                 max_tokens: int = 16000, client: Any = None):
        import anthropic

        if effort is not None and effort not in EFFORTS:
            raise ValueError(f"effort must be one of {', '.join(EFFORTS)}")
        if thinking not in THINKING:
            raise ValueError(f"thinking must be one of {', '.join(THINKING)}")
        if thinking == "disabled" and effort in ("xhigh", "max"):
            raise ValueError("thinking cannot be disabled at xhigh or max effort")
        self.client = client or anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"),
            base_url=base_url or os.environ.get("ANTHROPIC_BASE_URL") or None,
            timeout=timeout,
            max_retries=0,
        )
        self.model, self.effort, self.thinking, self.max_tokens = model, effort, thinking, max_tokens
        self.name = f"anthropic:{model}" + (f"@{effort}" if effort else "") + ("+nothink" if thinking == "disabled" else "")

    def start_episode(self, session: str) -> None:
        return None

    def params(self, request: dict[str, Any]) -> dict[str, Any]:
        output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": answer_schema(request)}}
        if self.effort:
            output_config["effort"] = self.effort
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": SYSTEM,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": json.dumps({"questions": request["questions"]}, ensure_ascii=False),
                 "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": json.dumps({"state": request["state"]}, ensure_ascii=False)},
            ]}],
            "output_config": output_config,
        }
        if self.thinking == "disabled":
            params["thinking"] = {"type": "disabled"}
        return params

    def system_one(self, request: dict[str, Any]) -> dict[str, Any]:
        import anthropic

        validate_request(request)
        try:
            message = self.client.messages.create(**self.params(request))
        except anthropic.APITimeoutError as error:
            raise TimeoutError("Anthropic request timed out") from error
        except anthropic.APIConnectionError as error:
            raise ConnectionError("Anthropic connection failed") from error
        except anthropic.APIStatusError as error:
            request_id = error.response.headers.get("request-id")
            # 429 rate limit, 529 overloaded and other 5xx are transient.
            if error.status_code == 429 or error.status_code >= 500:
                raise RetryableHTTPError(error.status_code,
                                         retry_after_seconds(error.response.headers.get("retry-after")),
                                         request_id) from error
            raise FatalAdapterError(f"Anthropic rejected the request (HTTP {error.status_code})") from error
        if message.stop_reason == "refusal":
            answers = {key: {"type": q["type"], "refusal": True} for key, q in request["questions"].items()}
        elif message.stop_reason != "end_turn":
            raise ContractError(f"Anthropic response stopped early: {message.stop_reason}")
        else:
            text = "".join(block.text for block in message.content if block.type == "text")
            try:
                answers = to_answers(request, json.loads(text))
            except (ValueError, TypeError) as error:
                raise ContractError(f"Anthropic answer does not fit the request: {error}") from None
        usage = message.usage
        return {
            "model": message.model,
            "answers": answers,
            # Thinking tokens are billed as output and not reported separately.
            "usage": {"input_tokens": usage.input_tokens,
                      "cached_tokens": usage.cache_read_input_tokens or 0,
                      "cache_write_tokens": usage.cache_creation_input_tokens or 0,
                      "output_tokens": usage.output_tokens},
            "request_id": message._request_id,
        }

    def close(self) -> None:
        self.client.close()
