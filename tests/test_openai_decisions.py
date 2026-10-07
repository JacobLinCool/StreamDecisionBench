"""OpenAI Decisions wire mapping, error handling and CLI provenance."""

import json
import sys

import httpx
import pytest

from streamdecisionbench.adapters.base import RetryableHTTPError
from streamdecisionbench.adapters.openai_decisions import MODEL, OpenAIDecisionsAdapter, OpenAIDecisionsAPIError
from streamdecisionbench.jev import ContractError, validate_response

REQUEST = {"state": {"message": "An outage"}, "questions": {
    "team": {"type": "choice", "instructions": "Who handles it?",
             "criteria": {"K2": "support: Outages", "K1": "sales: Plans"}},
    "urgent": {"type": "noul", "instructions": "Is it urgent?"},
    "severity": {"type": "score", "instructions": "Impact?", "criteria": ["Minor", "Major"]},
}}

NATIVE_QUESTIONS = [
    {"name": "team", "instructions": "Who handles it?", "type": "choice",
     "choices": [{"value": "K2", "description": "support: Outages"}, {"value": "K1", "description": "sales: Plans"}]},
    {"name": "urgent", "instructions": "Is it urgent?", "type": "predicate"},
    {"name": "severity", "instructions": "Impact?", "type": "score", "levels": [{"label": "Minor"}, {"label": "Major"}]},
]


def result(model=MODEL):
    return {"model": model, "answers": [
        {"type": "score", "name": "severity", "score": 0.3, "confidence": 0.12,
         "probabilities": [{"value": 0, "label": "Minor", "probability": 0.7},
                           {"value": 1, "label": "Major", "probability": 0.3}]},
        {"type": "choice", "name": "team", "choice": "K2", "confidence": 0.53,
         "probabilities": [{"value": "K2", "probability": 0.9}, {"value": "K1", "probability": 0.1}]},
        {"type": "predicate", "name": "urgent", "probability": 0.92},
    ], "usage": {"input_tokens": 120, "input_tokens_details": {"cached_tokens": 64, "cache_write_tokens": 0},
                 "output_tokens": 0, "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": 120}}


def adapter_for(handler):
    return OpenAIDecisionsAdapter(api_key="test", base_url="https://oai.test/v1/",
                                  transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("model", [MODEL, MODEL + "-2026-10-01"])
def test_native_wire_maps_questions_and_answers(model):
    def handler(request):
        assert str(request.url) == "https://oai.test/v1/decisions"
        assert request.headers["authorization"] == "Bearer test"
        assert json.loads(request.content) == {"model": MODEL, "input": json.dumps(REQUEST["state"]),
                                               "questions": NATIVE_QUESTIONS}
        return httpx.Response(200, json=result(model), headers={"x-request-id": "req_1"})
    adapter = adapter_for(handler)
    try:
        response = adapter.system_one({**REQUEST, "gold": "never send"})
    finally:
        adapter.close()
    validate_response(response, REQUEST["questions"])
    assert response["model"] == model and response["request_id"] == "req_1"
    assert response["answers"]["team"] == {"type": "choice", "choice": "K2", "confidence": 0.53,
                                           "probabilities": {"K2": 0.9, "K1": 0.1}}
    assert response["answers"]["urgent"] == {"type": "noul", "noul": 0.92}
    assert response["answers"]["severity"]["probabilities"] == {"0": 0.7, "1": 0.3}
    assert response["usage"] == {"input_tokens": 120, "cached_tokens": 64, "cache_write_tokens": 0,
                                 "output_tokens": 0, "reasoning_tokens": 0}


@pytest.mark.parametrize("status,retryable", [(400, False), (401, False), (404, False),
                                              (429, True), (500, True), (503, True)])
def test_http_errors_are_classified_without_leaking_body(status, retryable):
    adapter = adapter_for(lambda request: httpx.Response(status, text="private body",
                                                         headers={"x-request-id": "err", "Retry-After": "2"}))
    try:
        with pytest.raises(RetryableHTTPError if retryable else OpenAIDecisionsAPIError) as caught:
            adapter.system_one(REQUEST)
    finally:
        adapter.close()
    assert caught.value.status_code == status and caught.value.request_id == "err"
    assert "private" not in str(caught.value)
    if retryable:
        assert caught.value.retry_after_s == 2


def missing_answer():
    payload = result()
    payload["answers"] = payload["answers"][:2]
    return payload


@pytest.mark.parametrize("payload", [[], result("gpt-6-terra"), missing_answer(),
                                     {**result(), "usage": {"input_tokens": 1}}])
def test_malformed_responses_are_rejected(payload):
    adapter = adapter_for(lambda request: httpx.Response(200, json=payload))
    try:
        with pytest.raises(ContractError):
            adapter.system_one(REQUEST)
    finally:
        adapter.close()


def test_cli_records_native_settings(monkeypatch, tmp_path):
    import streamdecisionbench.adapters.openai_decisions as decisions
    import streamdecisionbench.cli as cli
    import streamdecisionbench.lite.runtime as runtime
    from streamdecisionbench.lite import __main__ as lite_cli
    captured = {}
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(lite_cli, "load_dataset", lambda path: ([], {}))
    monkeypatch.setattr(decisions, "OpenAIDecisionsAdapter", lambda **kwargs: kwargs)
    def run(episodes, manifest, factory, output, config):
        captured.update(config, adapter=factory())
        return {}
    monkeypatch.setattr(runtime, "run_dataset", run)
    monkeypatch.setattr(sys, "argv", ["lite", "run", "--data", str(tmp_path), "--out", str(tmp_path / "out"),
                                    "--provider", "openai-decisions", "--model", MODEL])
    lite_cli.main()
    assert captured["provider"] == "openai-decisions" and captured["reasoning_effort"] is None
    assert captured["request_timeout_s"] == 20 and not captured["custom_endpoint"]
    assert captured["rate_limit_policy"] == "http429_5xx_retry_after_shared_cooldown_v1"
    assert captured["adapter"] == {"model": MODEL, "timeout": 20}


def test_refused_question_commits_to_no_option_and_fails_only_where_used():
    from streamdecisionbench.jev import INVALID, committed_answer
    from streamdecisionbench.lite.core import compose, decode

    payload = result()
    payload["answers"][1] = {"type": "refusal", "name": "team"}
    adapter = adapter_for(lambda request: httpx.Response(200, json=payload))
    try:
        response = adapter.system_one(REQUEST)
    finally:
        adapter.close()
    validate_response(response, REQUEST["questions"])
    assert response["answers"]["team"] == {"type": "choice", "refusal": True}
    assert committed_answer(REQUEST["questions"]["team"], response["answers"]["team"]) == INVALID

    episode = {"questions": {"route": {}, "card": {}, "cue": {}},
               "option_semantics": {"route": {"K1": "talk", "K2": "questions"}, "card": {"K1": "none"},
                                    "cue": {"K1": "listen"}}}
    spec = {"route_question": "route", "always": ["cue"], "branches": {"talk": [], "questions": ["card"]}}
    pred = decode(episode, {"route": "K1", "card": INVALID, "cue": "K1"})
    assert compose(spec, pred) == {"route": "talk", "cue": "listen"}
    assert compose(spec, {**pred, "route": "questions"})["card"] == INVALID
    assert compose(spec, decode(episode, {"route": INVALID, "card": "K1", "cue": "K1"})) == {
        "route": INVALID, "cue": "listen"}
