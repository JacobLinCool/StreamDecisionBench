"""Gemini Decisions wire mapping, safety blocks, error handling and CLI provenance."""

import json
import sys

import httpx
import pytest

from streamdecisionbench.adapters.base import RetryableHTTPError
from streamdecisionbench.adapters.gemini_decisions import MODEL, GeminiDecisionsAdapter, GeminiDecisionsAPIError
from streamdecisionbench.jev import INVALID, ContractError, committed_answer, validate_response

REQUEST = {"state": {"message": "An outage"}, "questions": {
    "team": {"type": "choice", "instructions": "Who handles it?",
             "criteria": {"K2": "support: Outages", "K1": None}},
    "urgent": {"type": "noul", "instructions": {"ask": "Is it urgent?"}, "criteria": {"true": "act now"}},
    "severity": {"type": "score", "instructions": "Impact?", "criteria": ["Minor", {"level": "Major"}]},
}}

NATIVE_QUESTIONS = {
    "team": {"type": "choice", "instructions": "Who handles it?", "criteria": {"K2": "support: Outages", "K1": ""}},
    "urgent": {"type": "noul", "instructions": '{"ask": "Is it urgent?"}', "criteria": {"true_description": "act now"}},
    "severity": {"type": "score", "instructions": "Impact?", "criteria": ["Minor", '{"level": "Major"}']},
}


def result():
    return {"answers": {
        "severity": {"type": "score", "score": 0.3, "confidence": 0.7, "probabilities": {"1": 0.3, "0": 0.7},
                     "legend": {"0": "Minor", "1": "Major"}},
        "team": {"type": "choice", "choice": "K2", "confidence": 0.9, "probabilities": {"K2": 0.9, "K1": 0.1}},
        "urgent": {"type": "noul", "noul": 0.92, "confidence": 0.92},
    }, "usage": {"total_tokens": 120, "total_input_tokens": 120, "total_output_tokens": 0,
                 "input_tokens_by_modality": [{"modality": "text", "tokens": 120}]}}


def adapter_for(handler):
    return GeminiDecisionsAdapter(api_key="test", base_url="https://gem.test/v1beta/",
                                  transport=httpx.MockTransport(handler))


def call(handler, request=REQUEST):
    adapter = adapter_for(handler)
    try:
        return adapter.system_one(request)
    finally:
        adapter.close()


def test_native_wire_maps_questions_and_answers():
    def handler(request):
        assert str(request.url) == "https://gem.test/v1beta/decisions"
        assert request.headers["x-goog-api-key"] == "test"
        assert json.loads(request.content) == {"model": MODEL, "input": json.dumps(REQUEST["state"]),
                                               "questions": NATIVE_QUESTIONS}
        return httpx.Response(200, json=result())
    response = call(handler, {**REQUEST, "gold": "never send"})
    validate_response(response, REQUEST["questions"])
    assert response["model"] == MODEL
    assert response["answers"]["team"] == {"type": "choice", "choice": "K2", "confidence": 0.9,
                                           "probabilities": {"K2": 0.9, "K1": 0.1}}
    assert response["answers"]["urgent"] == {"type": "noul", "noul": 0.92}
    assert response["answers"]["severity"]["probabilities"] == {"1": 0.3, "0": 0.7}
    assert response["usage"] == {"input_tokens": 120, "output_tokens": 0, "cached_tokens": 0,
                                 "cache_write_tokens": 0, "reasoning_tokens": 0}


def test_safety_block_declines_every_question():
    blocked = {"error": {"code": "safety", "message": "Request blocked due to safety violations."}}
    response = call(lambda request: httpx.Response(400, json=blocked))
    validate_response(response, REQUEST["questions"])
    assert all(committed_answer(REQUEST["questions"][k], a) == INVALID for k, a in response["answers"].items())


@pytest.mark.parametrize("status,body,retryable", [
    (400, {"error": {"code": "invalid_argument", "message": "private body"}}, False), (400, "private body", False),
    (401, "private body", False), (404, "private body", False),
    (429, "private body", True), (500, "private body", True), (503, "private body", True)])
def test_http_errors_are_classified_without_leaking_body(status, body, retryable):
    kwargs = {"json": body} if isinstance(body, dict) else {"text": body}
    with pytest.raises(RetryableHTTPError if retryable else GeminiDecisionsAPIError) as caught:
        call(lambda request: httpx.Response(status, headers={"Retry-After": "2"}, **kwargs))
    assert caught.value.status_code == status and "private" not in str(caught.value)
    if retryable:
        assert caught.value.retry_after_s == 2


def missing_answer():
    payload = result()
    del payload["answers"]["team"]
    return payload


@pytest.mark.parametrize("payload", [[], missing_answer(), {**result(), "usage": {"total_input_tokens": 1}}])
def test_malformed_responses_are_rejected(payload):
    with pytest.raises(ContractError):
        call(lambda request: httpx.Response(200, json=payload))


def test_cli_records_native_settings(monkeypatch, tmp_path):
    import streamdecisionbench.adapters.gemini_decisions as decisions
    import streamdecisionbench.cli as cli
    import streamdecisionbench.lite.runtime as runtime
    from streamdecisionbench.lite import __main__ as lite_cli
    captured = {}
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.delenv("GEMINI_BASE_URL", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(lite_cli, "load_dataset", lambda path: ([], {}))
    monkeypatch.setattr(decisions, "GeminiDecisionsAdapter", lambda **kwargs: kwargs)
    def run(episodes, manifest, factory, output, config):
        captured.update(config, adapter=factory())
        return {}
    monkeypatch.setattr(runtime, "run_dataset", run)
    monkeypatch.setattr(sys, "argv", ["lite", "run", "--data", str(tmp_path), "--out", str(tmp_path / "out"),
                                    "--provider", "gemini-decisions", "--model", MODEL])
    lite_cli.main()
    assert captured["provider"] == "gemini-decisions" and captured["reasoning_effort"] is None
    assert captured["request_timeout_s"] == 20 and not captured["custom_endpoint"]
    assert captured["rate_limit_policy"] == "http429_5xx_retry_after_shared_cooldown_v1"
    assert captured["adapter"] == {"model": MODEL, "timeout": 20}
