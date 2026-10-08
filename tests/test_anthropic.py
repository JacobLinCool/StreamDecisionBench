"""Anthropic Messages wire format, refusals, error handling and CLI provenance."""

import json
import sys

import httpx2
import pytest

anthropic = pytest.importorskip("anthropic")

from streamdecisionbench.adapters.anthropic_messages import AnthropicAdapter
from streamdecisionbench.adapters.base import FatalAdapterError, RetryableHTTPError
from streamdecisionbench.adapters.llm import SYSTEM, answer_schema
from streamdecisionbench.jev import INVALID, ContractError, committed_answer, validate_response

MODEL = "claude-haiku-5-5"
REQUEST = {"state": {"message": "An outage"}, "questions": {
    "team": {"type": "choice", "instructions": "Who handles it?",
             "criteria": {"K2": "support: Outages", "K1": "sales: Plans"}},
    "urgent": {"type": "noul", "instructions": "Is it urgent?"},
    "severity": {"type": "score", "instructions": "Impact?", "criteria": ["Minor", "Major"]},
}}


def message(text=None, stop_reason="end_turn", **extra):
    content = [{"type": "thinking", "thinking": "", "signature": "sig"}]
    if text is not None:
        content.append({"type": "text", "text": text})
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": MODEL, "content": content,
            "stop_reason": stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": 300, "cache_read_input_tokens": 900, "cache_creation_input_tokens": 0,
                      "output_tokens": 40}, **extra}


def adapter_for(handler, **kwargs):
    client = anthropic.Anthropic(api_key="test", base_url="https://anthropic.test", max_retries=0,
                                 http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    return AnthropicAdapter(MODEL, client=client, **kwargs)


def call(handler, **kwargs):
    adapter = adapter_for(handler, **kwargs)
    try:
        return adapter.system_one(REQUEST)
    finally:
        adapter.close()


def test_structured_request_and_answers():
    sent = []

    def handler(request):
        assert request.url.path == "/v1/messages"
        sent.append(json.loads(request.content))
        return httpx2.Response(200, json=message('{"team": "K2", "urgent": true, "severity": 1}'),
                               headers={"request-id": "req_1"})

    response = call(handler, effort="low", thinking="disabled")
    validate_response(response, REQUEST["questions"])
    body = sent[0]
    assert body["model"] == MODEL and body["system"] == SYSTEM
    assert body["output_config"] == {"format": {"type": "json_schema", "schema": answer_schema(REQUEST)},
                                     "effort": "low"}
    assert body["thinking"] == {"type": "disabled"}
    assert "temperature" not in body and "top_p" not in body
    questions, state = body["messages"][0]["content"]
    assert questions["cache_control"] == {"type": "ephemeral"} and "cache_control" not in state
    assert json.loads(questions["text"]) == {"questions": REQUEST["questions"]}
    assert json.loads(state["text"]) == {"state": REQUEST["state"]}
    assert {k: committed_answer(REQUEST["questions"][k], a) for k, a in response["answers"].items()} == {
        "team": "K2", "urgent": True, "severity": 1}
    assert response["model"] == MODEL and response["request_id"] == "req_1"
    assert response["usage"] == {"input_tokens": 300, "cached_tokens": 900, "cache_write_tokens": 0,
                                 "output_tokens": 40}


def test_default_settings_leave_thinking_and_effort_to_the_model():
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx2.Response(200, json=message('{"team": "K1", "urgent": false, "severity": 0}'))

    call(handler)
    assert "thinking" not in sent[0] and "effort" not in sent[0]["output_config"]


def test_safeguard_refusal_refuses_every_question():
    def handler(request):
        return httpx2.Response(200, json=message(stop_reason="refusal",
                                                 stop_details={"type": "refusal", "category": "general_harms",
                                                               "explanation": None}))

    response = call(handler)
    validate_response(response, REQUEST["questions"])
    assert {k: committed_answer(REQUEST["questions"][k], a) for k, a in response["answers"].items()} == {
        k: INVALID for k in REQUEST["questions"]}


@pytest.mark.parametrize("payload", [
    message('{"team": "K9", "urgent": true, "severity": 1}'),
    message('{"team": "K2", "urgent": true, "severity": 5}'),
    message("not json"),
    message('{"team": "K2"', stop_reason="max_tokens"),
])
def test_malformed_or_truncated_answers_are_contract_errors(payload):
    with pytest.raises(ContractError):
        call(lambda request: httpx2.Response(200, json=payload))


@pytest.mark.parametrize("status,retryable", [(429, True), (500, True), (529, True), (400, False), (401, False),
                                              (404, False)])
def test_http_errors_are_classified(status, retryable):
    def handler(request):
        return httpx2.Response(status, json={"type": "error", "error": {"type": "x", "message": "secret body"}},
                               headers={"retry-after": "3", "request-id": "req_9"})

    with pytest.raises(RetryableHTTPError if retryable else FatalAdapterError) as caught:
        call(handler)
    assert "secret body" not in str(caught.value)
    if retryable:
        assert caught.value.status_code == status and caught.value.retry_after_s == 3
        assert caught.value.request_id == "req_9"


def test_connection_failures_are_transport_errors():
    from streamdecisionbench.lite.runtime import is_transport_error

    def handler(request):
        raise httpx2.ConnectError("down")

    with pytest.raises(ConnectionError) as caught:
        call(handler)
    assert is_transport_error(caught.value)


def test_thinking_cannot_be_disabled_at_high_effort_levels():
    with pytest.raises(ValueError):
        AnthropicAdapter(MODEL, effort="xhigh", thinking="disabled", api_key="test")


def run_cli(monkeypatch, tmp_path, *flags):
    import streamdecisionbench.adapters.anthropic_messages as messages
    import streamdecisionbench.cli as cli
    import streamdecisionbench.lite.runtime as runtime
    from streamdecisionbench.lite import __main__ as lite_cli

    captured = {}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(lite_cli, "load_dataset", lambda path: ([], {}))
    monkeypatch.setattr(messages, "AnthropicAdapter", lambda **kwargs: kwargs)

    def run(episodes, manifest, factory, output, config):
        captured.update(config, adapter=factory())
        return {}

    monkeypatch.setattr(runtime, "run_dataset", run)
    monkeypatch.setattr(sys, "argv", ["lite", "run", "--data", str(tmp_path), "--out", str(tmp_path / "out"),
                                      "--provider", "anthropic", "--model", MODEL, *flags])
    lite_cli.main()
    return captured


def test_cli_records_claude_settings(monkeypatch, tmp_path):
    captured = run_cli(monkeypatch, tmp_path, "--effort", "low", "--thinking", "disabled")
    assert captured["provider"] == "anthropic" and captured["reasoning_effort"] == "low"
    assert captured["thinking"] == "disabled" and captured["workers"] == 32
    assert captured["rate_limit_policy"] == "http429_5xx_retry_after_shared_cooldown_v1"
    assert captured["adapter"] == {"model": MODEL, "effort": "low", "thinking": "disabled", "timeout": 20}
    assert run_cli(monkeypatch, tmp_path)["thinking"] == "adaptive"


@pytest.mark.parametrize("flags", [["--effort", "max", "--thinking", "disabled"], ["--effort", "none"]])
def test_cli_rejects_invalid_claude_settings(monkeypatch, tmp_path, flags):
    with pytest.raises(SystemExit):
        run_cli(monkeypatch, tmp_path, *flags)
