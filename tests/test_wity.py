"""Verify the native Wity wire contract and benchmark CLI without paid API calls."""

import json
import sys

import httpx
import pytest

from streamdecisionbench.adapters.wity import WityAdapter, WityAPIError
from streamdecisionbench.jev import ContractError, make_answer, validate_response
from streamdecisionbench.lite import __main__ as lite_cli
from streamdecisionbench.lite.runtime import is_transport_error

REQUEST = {"state": {"message": "An outage"}, "questions": {
    "team": {"type": "choice", "instructions": "Who handles it?",
             "criteria": {"support": "Outages", "sales": "Plans"}},
    "urgent": {"type": "noul", "instructions": "Is it urgent?"},
    "severity": {"type": "score", "instructions": "Impact?", "criteria": ["Minor", "Major"]},
}}


@pytest.mark.parametrize("reasoning", ["auto", "off", "always"])
def test_native_request_and_response_preserve_probabilities_and_reasoning(reasoning):
    answers = {key: make_answer(q, 0.9 if q["type"] == "noul" else
                               {label: 0.5 for label in (q["criteria"] if q["type"] == "choice" else ["0", "1"])})
               for key, q in REQUEST["questions"].items()}
    answers["team"]["reasoning"] = {"mode": reasoning, "thought": True}
    result = {"model": "wity-1", "answers": answers, "usage": {"input_tokens": 123, "output_tokens": 0},
              "metadata": {"reasoning": reasoning, "elapsed_ms": 94.1}}

    def handler(request):
        assert str(request.url) == "https://wity.test/v1/systemone"
        assert request.headers["authorization"] == "Bearer test-wity-key"
        assert json.loads(request.content) == {**REQUEST, "reasoning": reasoning}
        return httpx.Response(200, json=result)

    client = WityAdapter(api_key="test-wity-key", base_url="https://wity.test/", reasoning=reasoning,
                         transport=httpx.MockTransport(handler))
    try:
        response = client.system_one({**REQUEST, "gold": "never send", "reasoning": "always"})
        validate_response(response, REQUEST["questions"])
        assert response == result
    finally:
        client.close()
    assert client.client.is_closed


@pytest.mark.parametrize("status", [400, 401, 403, 500])
def test_api_rejections_are_not_transport_retries_or_secret_leaks(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": "private input or key"})

    client = WityAdapter(api_key="test", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(WityAPIError) as caught:
            client.system_one(REQUEST)
        assert caught.value.status_code == status
        assert not is_transport_error(caught.value)
        assert "private" not in str(caught.value)
        assert len(calls) == 1
    finally:
        client.close()


@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError])
def test_network_failures_are_owned_by_the_runner(failure):
    def handler(request):
        raise failure("private details", request=request)

    client = WityAdapter(api_key="test", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises((ConnectionError, TimeoutError)) as caught:
            client.system_one(REQUEST)
        assert is_transport_error(caught.value)
        assert "private" not in str(caught.value)
    finally:
        client.close()


@pytest.mark.parametrize("result", [
    [], {"answers": {}, "usage": {"input_tokens": 1, "output_tokens": 0}},
    {"model": "wity-1", "answers": None, "usage": {"input_tokens": 1, "output_tokens": 0}},
    {"model": "wity-1", "answers": {}, "usage": {"input_tokens": True, "output_tokens": 0}},
    {"model": "wity-1", "answers": {}, "usage": {"input_tokens": 1}},
])
def test_missing_response_provenance_is_rejected(result):
    client = WityAdapter(api_key="test", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=result)))
    try:
        with pytest.raises(ContractError):
            client.system_one(REQUEST)
    finally:
        client.close()


@pytest.mark.parametrize("reasoning,timeout", [(None, None), ("off", "90"), ("always", None)])
def test_cli_freezes_mode_timeout_and_uses_wity_credentials(monkeypatch, tmp_path, reasoning, timeout):
    import streamdecisionbench.adapters.wity as wity
    import streamdecisionbench.cli as cli
    import streamdecisionbench.lite.runtime as runtime

    captured = {}
    monkeypatch.setenv("WITY_API_KEY", "test")
    monkeypatch.delenv("WITY_BASE_URL", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(lite_cli, "load_dataset", lambda path: ([], {}))
    monkeypatch.setattr(wity, "WityAdapter", lambda **kwargs: kwargs)

    def run(episodes, manifest, factory, output, config):
        captured.update(config, adapter=factory())
        return {}

    monkeypatch.setattr(runtime, "run_dataset", run)
    argv = ["lite", "run", "--data", str(tmp_path), "--out", str(tmp_path / "out"),
            "--provider", "wity", "--model", "wity-1"]
    if reasoning:
        argv += ["--reasoning", reasoning]
    if timeout:
        argv += ["--timeout", timeout]
    monkeypatch.setattr(sys, "argv", argv)
    lite_cli.main()
    mode = reasoning or "auto"
    assert captured["provider"] == "wity" and captured["reasoning"] == mode
    assert captured["workers"] == 16
    assert captured["rate_limit_policy"] == "http429_retry_after_shared_cooldown_v1"
    assert captured["sdk_retries"] == 0 and not captured["custom_endpoint"]
    assert captured["request_timeout_s"] == (float(timeout) if timeout else 60.0)
    assert captured["adapter"] == {"model": "wity-1", "reasoning": mode,
                                   "timeout": captured["request_timeout_s"]}


@pytest.mark.parametrize("args,error", [
    (["--model", "other"], "Wity model"),
    (["--effort", "low"], "--effort"),
    (["--provider", "typesafe", "--reasoning", "off"], "--reasoning"),
])
def test_cli_rejects_misleading_settings_before_loading_data(monkeypatch, tmp_path, capsys, args, error):
    import streamdecisionbench.cli as cli

    monkeypatch.setenv("WITY_API_KEY", "test")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test")
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(sys, "argv", ["lite", "run", "--data", str(tmp_path), "--out", str(tmp_path / "out"),
                                    "--provider", "wity", "--model", "wity-1", *args])
    with pytest.raises(SystemExit) as caught:
        lite_cli.main()
    assert caught.value.code == 2 and error in capsys.readouterr().err


@pytest.mark.parametrize("provider,model,module,adapter,credentials", [
    ("openai", "test-model", "llm", "OpenAIAdapter", {"OPENAI_API_KEY": "test"}),
    ("typesafe", "jev-latest", "remote", "TypeSafeAdapter", {"TYPESAFE_API_KEY": "test"}),
    ("cloudflare", "clef", "cloudflare", "CloudflareAdapter",
     {"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_AUTH_TOKEN": "test"}),
])
def test_wity_worker_limit_does_not_change_other_providers(monkeypatch, tmp_path, provider, model,
                                                         module, adapter, credentials):
    import importlib
    import streamdecisionbench.cli as cli
    import streamdecisionbench.lite.runtime as runtime

    captured = {}
    for key, value in credentials.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(lite_cli, "load_dataset", lambda path: ([], {}))
    monkeypatch.setattr(importlib.import_module(f"streamdecisionbench.adapters.{module}"),
                        adapter, lambda **kwargs: kwargs)

    def run(episodes, manifest, factory, output, config):
        captured.update(config, adapter=factory())
        return {}

    monkeypatch.setattr(runtime, "run_dataset", run)
    monkeypatch.setattr(sys, "argv", ["lite", "run", "--data", str(tmp_path), "--out", str(tmp_path / "out"),
                                    "--provider", provider, "--model", model])
    lite_cli.main()
    assert captured["workers"] == 32
    assert captured["request_timeout_s"] == 20.0
    assert "reasoning" not in captured
    assert "rate_limit_policy" not in captured


@pytest.mark.parametrize('header', ['0', '2', '120'])
def test_retry_after_seconds(header):
    from streamdecisionbench.adapters.wity import retry_after_seconds
    assert retry_after_seconds(header) == float(header)


def test_retry_after_http_date_and_invalid_headers():
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime
    from streamdecisionbench.adapters.wity import retry_after_seconds
    assert 58 <= retry_after_seconds(format_datetime(datetime.now(timezone.utc) + timedelta(seconds=60))) <= 60
    assert retry_after_seconds('Wed, 21 Oct 2015 07:28:00 GMT') == 0
    assert retry_after_seconds(None) is None
    for value in ['private invalid header', '-1', 'nan', '1.5']:
        with pytest.raises(ValueError, match='Retry-After'):
            retry_after_seconds(value)


def test_rate_limit_recovery_is_logged_and_excluded_from_model_timing():
    import time
    from collections import Counter
    from streamdecisionbench.lite.runtime import run_episode
    from test_lite_core import example

    ep = example(0.01)
    calls, times, events = [], [], []
    counts = Counter()

    def handler(request):
        body = json.loads(request.content)
        t = body['state']['event']
        calls.append(body)
        times.append(time.monotonic())
        counts[t] += 1
        if t == 0 and counts[t] == 1:
            return httpx.Response(429, headers={'Retry-After': '1'}, json={'error': 'secret'})
        answers = {}
        for key, question in body['questions'].items():
            correct = next(label for label, meaning in ep['option_semantics'][key].items()
                           if meaning == ep['steps'][t]['gold'][key])
            answers[key] = make_answer(question, {label: float(label == correct) for label in question['criteria']})
        return httpx.Response(200, json={'model': 'wity-1', 'answers': answers,
                                      'usage': {'input_tokens': 10, 'output_tokens': 0}})

    records, releases = run_episode(ep, lambda: WityAdapter(api_key='test', transport=httpx.MockTransport(handler)),
                                    events.append, workers=1, max_attempts=2, retry_delay_s=0)
    assert times[1] - times[0] >= 1
    assert calls[0] == calls[1]
    assert all(r['ok'] for r in records)
    assert records[0]['attempts'][0]['retry_after_s'] == 1
    assert records[0]['attempts'][0]['http_status'] == 429
    assert records[0]['attempts'][0]['retryable']
    assert len(records[0]['attempts']) == 2
    assert 'secret' not in json.dumps(events)
    from streamdecisionbench.lite.retry_scoring import normalized_episode_scores
    assert normalized_episode_scores(ep, records, releases)['untimed_decision_accuracy'] == 1
