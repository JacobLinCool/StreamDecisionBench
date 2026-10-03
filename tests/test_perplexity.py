"""Native Decisions wire contract, error handling and CLI provenance."""

import json
import sys

import httpx
import pytest

from streamdecisionbench.adapters.base import RateLimitError
from streamdecisionbench.adapters.perplexity import (
    MODEL, PerplexityAdapter, PerplexityAPIError, PerplexityServiceError,
)
from streamdecisionbench.jev import ContractError, make_answer, validate_response
from streamdecisionbench.lite.runtime import is_transport_error

REQUEST = {"state": {"message": "An outage"}, "questions": {
    "team": {"type": "choice", "instructions": "Who handles it?",
             "criteria": {"support": "Outages", "sales": "Plans"}},
    "urgent": {"type": "noul", "instructions": "Is it urgent?"},
    "severity": {"type": "score", "instructions": "Impact?", "criteria": ["Minor", "Major"]},
}}


def result():
    return {"model": MODEL, "answers": {
        key: make_answer(q, 0.91 if q["type"] == "noul" else
                         {label: 0.5 for label in (q["criteria"] if q["type"] == "choice" else ["0", "1"])})
        for key, q in REQUEST["questions"].items()
    }, "usage": {"input_tokens": 123, "output_tokens": 3}}


def test_native_wire_preserves_answers_and_records_request_id():
    payload = result()
    def handler(request):
        assert str(request.url) == "https://pplx.test/v1/decisions"
        assert request.headers["authorization"] == "Bearer test"
        assert json.loads(request.content) == {"model": MODEL, **REQUEST}
        return httpx.Response(200, json=payload, headers={"x-request-id": "test-request"})
    adapter = PerplexityAdapter(api_key="test", base_url="https://pplx.test/",
                                transport=httpx.MockTransport(handler))
    try:
        response = adapter.system_one({**REQUEST, "gold": "never send", "reasoning": "off"})
        validate_response(response, REQUEST["questions"])
        assert response == {**payload, "request_id": "test-request"}
    finally:
        adapter.close()
    assert adapter.client.is_closed


@pytest.mark.parametrize("status", [400, 401, 403, 404, 413, 500, 503, 504])
def test_http_errors_do_not_parse_html_or_leak_body(status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="private body", headers={"x-request-id": "error-id"})
    adapter = PerplexityAdapter(api_key="test", transport=httpx.MockTransport(handler))
    try:
        error_class = PerplexityServiceError if status >= 500 else PerplexityAPIError
        with pytest.raises(error_class) as caught:
            adapter.system_one(REQUEST)
        assert caught.value.status_code == status
        assert caught.value.request_id == "error-id"
        assert is_transport_error(caught.value) == (status >= 500)
        assert "private" not in str(caught.value)
        assert len(calls) == 1
    finally:
        adapter.close()


@pytest.mark.parametrize("header,delay", [(None, None), ("0", 0), ("2", 2)])
def test_rate_limit_is_owned_by_runner(header, delay):
    headers = {"x-request-id": "limit-id"}
    if header is not None:
        headers["Retry-After"] = header
    adapter = PerplexityAdapter(api_key="test", transport=httpx.MockTransport(
        lambda request: httpx.Response(429, headers=headers)))
    try:
        with pytest.raises(RateLimitError) as caught:
            adapter.system_one(REQUEST)
        assert caught.value.retry_after_s == delay
        assert caught.value.request_id == "limit-id"
    finally:
        adapter.close()


@pytest.mark.parametrize("payload", [[], {**result(), "model": "other"},
    {**result(), "answers": None}, {**result(), "usage": {"input_tokens": True, "output_tokens": 0}}])
def test_malformed_provenance_is_rejected(payload):
    adapter = PerplexityAdapter(api_key="test", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=payload)))
    try:
        with pytest.raises(ContractError):
            adapter.system_one(REQUEST)
    finally:
        adapter.close()


def test_cli_records_native_settings(monkeypatch, tmp_path):
    import streamdecisionbench.adapters.perplexity as perplexity
    import streamdecisionbench.cli as cli
    import streamdecisionbench.lite.runtime as runtime
    from streamdecisionbench.lite import __main__ as lite_cli
    captured = {}
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test")
    monkeypatch.delenv("PERPLEXITY_BASE_URL", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(lite_cli, "load_dataset", lambda path: ([], {}))
    monkeypatch.setattr(perplexity, "PerplexityAdapter", lambda **kwargs: kwargs)
    def run(episodes, manifest, factory, output, config):
        captured.update(config, adapter=factory())
        return {}
    monkeypatch.setattr(runtime, "run_dataset", run)
    monkeypatch.setattr(sys, "argv", ["lite", "run", "--data", str(tmp_path), "--out", str(tmp_path / "out"),
                                    "--provider", "perplexity", "--model", MODEL])
    lite_cli.main()
    assert captured["workers"] == 32
    assert captured["request_timeout_s"] == 30
    assert captured["sdk_retries"] == 0 and not captured["custom_endpoint"]
    assert captured["rate_limit_policy"] == "http429_retry_after_shared_cooldown_v1"
    assert captured["adapter"] == {"model": MODEL, "timeout": 30}


@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError])
def test_transport_failure_is_retryable_without_hidden_retries(failure):
    calls = []
    def handler(request):
        calls.append(request)
        raise failure("private details", request=request)
    adapter = PerplexityAdapter(api_key="test", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises((ConnectionError, TimeoutError)) as caught:
            adapter.system_one(REQUEST)
        assert is_transport_error(caught.value)
        assert len(calls) == 1 and "private" not in str(caught.value)
    finally:
        adapter.close()


@pytest.mark.parametrize("header", ["-1", "1.5", "nan", "9" * 400])
def test_invalid_retry_after_is_not_silently_replaced(header):
    adapter = PerplexityAdapter(api_key="test", transport=httpx.MockTransport(
        lambda request: httpx.Response(429, headers={"Retry-After": header})))
    try:
        with pytest.raises(ContractError):
            adapter.system_one(REQUEST)
    finally:
        adapter.close()


def test_runner_retains_request_ids_for_failed_and_successful_attempts():
    from streamdecisionbench.lite.runtime import run_episode
    from test_lite_core import example
    episode = example(0.01)
    counts = {}
    def handler(request):
        body = json.loads(request.content)
        t = body['state']['event']
        counts[t] = counts.get(t, 0) + 1
        if t == 0 and counts[t] == 1:
            return httpx.Response(503, text="private details", headers={"x-request-id": "failed-id"})
        answers = {key: make_answer(q, {label: 1 for label in q['criteria']})
                   for key, q in body['questions'].items()}
        return httpx.Response(200, json={"model": MODEL, "answers": answers,
                                        "usage": {"input_tokens": 10, "output_tokens": 2}},
                              headers={"x-request-id": f"success-{t}"})
    events = []
    records, _ = run_episode(episode, lambda: PerplexityAdapter(api_key="test", transport=httpx.MockTransport(handler)),
                             events.append, workers=1, max_attempts=2, retry_delay_s=0)
    first = next(r for r in records if r['t'] == 0)
    assert first['attempts'][0]['request_id'] == 'failed-id'
    assert first['attempts'][0]['http_status'] == 503
    assert first['attempts'][1]['request_id'] == 'success-0'
    assert all(r['ok'] for r in records)
    assert 'private details' not in json.dumps(events)
