"""GLiDE wire semantics, explicit retries and CLI provenance."""

import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest

from streamdecisionbench.adapters.base import RetryableHTTPError
from streamdecisionbench.adapters.fastino import MODEL, FastinoAdapter, FastinoAPIError, retry_after_seconds
from streamdecisionbench.jev import ContractError, committed_answer, validate_response

REQUEST = {"state": {"message": "An outage"}, "questions": {
    "team": {"type": "choice", "instructions": "Who handles it?",
             "criteria": {"support": "Outages", "sales": "Plans"}},
    "urgent": {"type": "noul", "instructions": "Is it urgent?"},
    "severity": {"type": "score", "instructions": "Impact?", "criteria": ["Minor", "Major"]},
}}


def payload():
    return {"model": "glide", "answers": {
        "team": {"type": "choice", "choice": "support", "confidence": 0.8,
                 "probabilities": {"support": 0.9, "sales": 0.1}},
        "urgent": {"type": "noul", "noul": 0.9, "confidence": 0.8},
        "severity": {"type": "score", "score": 1, "expected_level": 0.7, "confidence": 0.4,
                     "probabilities": {"0": 0.3, "1": 0.7}, "legend": {"0": "Minor", "1": "Major"}},
    }, "usage": {"input_tokens": 123, "output_tokens": 3}}


def test_native_wire_and_score_mapping():
    def handler(request):
        assert str(request.url) == "https://fastino.test/v1/systemone"
        assert request.headers["x-api-key"] == "test"
        assert "authorization" not in request.headers
        assert json.loads(request.content) == {"model": MODEL, **REQUEST}
        return httpx.Response(200, json=payload(), headers={"x-request-id": "success-id"})
    adapter = FastinoAdapter(api_key="test", base_url="https://fastino.test/",
                            transport=httpx.MockTransport(handler))
    try:
        response = adapter.system_one({**REQUEST, "gold": "never send", "reasoning": "off"})
        validate_response(response, REQUEST["questions"])
        assert response["request_id"] == "success-id"
        answer = response["answers"]["severity"]
        assert answer["native_score"] == 1 and answer["score"] == answer["expected_level"] == 0.7
        assert committed_answer(REQUEST["questions"]["severity"], answer) == 1
        assert response["answers"]["team"] == payload()["answers"]["team"]
    finally:
        adapter.close()
    assert adapter.client.is_closed


@pytest.mark.parametrize("status,header,delay", [(425, None, 60), (425, "90", 90),
    (429, None, None), (429, "2", 2), (503, "3", 3)])
def test_transient_errors_retain_server_delay_without_hidden_retries(status, header, delay):
    calls = []
    def handler(request):
        calls.append(request)
        headers = {"x-request-id": "failed-id"}
        if header is not None:
            headers["Retry-After"] = header
        return httpx.Response(status, text="private body", headers=headers)
    adapter = FastinoAdapter(api_key="test", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(RetryableHTTPError) as caught:
            adapter.system_one(REQUEST)
        assert caught.value.status_code == status
        assert caught.value.request_id == "failed-id"
        assert caught.value.retry_after_s == delay
        assert len(calls) == 1 and "private" not in str(caught.value)
    finally:
        adapter.close()


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 422, 500, 529])
def test_undocumented_or_terminal_errors_are_not_retried(status):
    adapter = FastinoAdapter(api_key="test", transport=httpx.MockTransport(
        lambda request: httpx.Response(status, text="private body")))
    try:
        with pytest.raises(FastinoAPIError) as caught:
            adapter.system_one(REQUEST)
        assert caught.value.status_code == status
        assert "private" not in str(caught.value)
    finally:
        adapter.close()


@pytest.mark.parametrize("field,value", [("score", 0), ("score", True), ("expected_level", None),
    ("expected_level", 0.2), ("probabilities", {"0": 0.5, "1": 0.7})])
def test_invalid_native_scores_are_rejected(field, value):
    result = payload()
    result["answers"]["severity"][field] = value
    adapter = FastinoAdapter(api_key="test", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=result)))
    try:
        with pytest.raises(ContractError):
            adapter.system_one(REQUEST)
    finally:
        adapter.close()


@pytest.mark.parametrize("header", ["-1", "1.5", "nan", "9" * 400])
def test_invalid_server_delay_is_rejected(header):
    with pytest.raises(ContractError):
        retry_after_seconds(header)


def test_http_date_delay():
    value = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=10), usegmt=True)
    assert 8 <= retry_after_seconds(value) <= 10


@pytest.mark.parametrize("instructions", [None, {}, "", " "])
def test_unsupported_questions_fail_before_dispatch(instructions):
    request = copy.deepcopy(REQUEST)
    request["questions"]["team"]["instructions"] = instructions
    def handler(request):
        pytest.fail("invalid request dispatched")
    adapter = FastinoAdapter(api_key="test", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ContractError):
            adapter.system_one(request)
    finally:
        adapter.close()


def test_cli_records_native_settings(monkeypatch, tmp_path):
    import streamdecisionbench.adapters.fastino as fastino
    import streamdecisionbench.cli as cli
    import streamdecisionbench.lite.runtime as runtime
    from streamdecisionbench.lite import __main__ as lite_cli
    captured = {}
    monkeypatch.setenv("FASTINO_API_KEY", "test")
    monkeypatch.delenv("FASTINO_BASE_URL", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(lite_cli, "load_dataset", lambda path: ([], {}))
    monkeypatch.setattr(fastino, "FastinoAdapter", lambda **kwargs: kwargs)
    def run(episodes, manifest, factory, output, config):
        captured.update(config, adapter=factory())
        return {}
    monkeypatch.setattr(runtime, "run_dataset", run)
    monkeypatch.setattr(sys, "argv", ["lite", "run", "--data", str(tmp_path), "--out", str(tmp_path / "out"),
                                    "--provider", "fastino", "--model", MODEL])
    lite_cli.main()
    assert captured["workers"] == 32 and captured["request_timeout_s"] == 300
    assert captured["sdk_retries"] == 0 and not captured["custom_endpoint"]
    assert captured["rate_limit_policy"] == "http425_429_503_retry_after_shared_cooldown_v1"
    assert captured["score_mapping"] == "expected_level_to_score_v1"
    assert captured["adapter"] == {"model": MODEL, "timeout": 300}


def test_runner_honors_transient_http_delay_and_records_each_attempt():
    from streamdecisionbench.lite.runtime import run_episode
    from streamdecisionbench.jev import make_answer
    from test_lite_core import example
    calls = {}
    def handler(request):
        body = json.loads(request.content)
        tick = body["state"]["event"]
        calls[tick] = calls.get(tick, 0) + 1
        if tick == 0 and calls[tick] == 1:
            return httpx.Response(503, headers={"Retry-After": "1", "x-request-id": "failed-id"})
        answers = {key: make_answer(q, {label: 1 for label in q["criteria"]})
                   for key, q in body["questions"].items()}
        return httpx.Response(200, json={"model": "glide", "answers": answers,
            "usage": {"input_tokens": 10, "output_tokens": 2}}, headers={"x-request-id": "success-id"})
    records, _ = run_episode(example(0.01), lambda: FastinoAdapter(api_key="test",
        transport=httpx.MockTransport(handler)), lambda event: None, workers=1, max_attempts=2, retry_delay_s=0)
    assert all(record["ok"] for record in records)
    attempts = next(record for record in records if record["t"] == 0)["attempts"]
    assert attempts[0]["http_status"] == 503 and attempts[0]["retry_after_s"] == 1
    assert attempts[0]["request_id"] == "failed-id"
    assert attempts[1]["started_s"] - attempts[0]["started_s"] >= 1
    assert attempts[1]["request_id"] == "success-id"


def test_report_describes_fastino_retry_policy(tmp_path):
    from test_lite_reports import _write_recording, lite_report
    run = tmp_path / "run"
    _write_recording(run)
    data = lite_report.analyze(run)
    data["config"]["rate_limit_policy"] = "http425_429_503_retry_after_shared_cooldown_v1"
    lines = "\n".join(lite_report._retry_report_lines(data))
    assert "HTTP 425, 429, and 503" in lines
    assert "Retry-After" in lines and "shared episode cooldown" in lines
    assert "at least 60 s" in lines
