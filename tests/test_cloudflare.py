"""Native Clef responses and CLI routing against a local fake Workers AI API."""

from copy import deepcopy
import json
import sys

import httpx
import pytest

from streamdecisionbench.adapters.cloudflare import CloudflareAdapter, CloudflareAPIError
from streamdecisionbench.jev import ContractError, make_answer, validate_response
from streamdecisionbench.lite import __main__ as lite_cli
from streamdecisionbench.lite.core import request_for, sources
from streamdecisionbench.lite.runtime import IncompleteRunError, is_transport_error, run_episode
from test_lite_core import example

ACCOUNT_ID = "a" * 32
TOKEN = "local-test-token"
REQUEST = {
    "state": "Checkout has been failing for every customer for the last hour.",
    "questions": {
        "urgent": {"type": "noul", "instructions": "Is this support request urgent?"},
        "team": {"type": "choice", "instructions": "Which team should handle this request?",
                 "criteria": {"billing": "Payments", "technical": "Outages", "sales": "Plans"}},
        "severity": {"type": "score", "instructions": "How severe is the customer impact?",
                     "criteria": ["No impact", "Minor", "Major", "Critical"]},
    },
}
RESULT = {
    "model": "clef",
    "answers": {
        "urgent": {"type": "noul", "noul": 0.9906},
        "team": {"type": "choice", "choice": "technical",
                 "probabilities": {"billing": 0.1762, "technical": 0.8088, "sales": 0.015},
                 "confidence": 0.5281},
        "severity": {"type": "score", "score": 2.9573,
                     "legend": {"0": "No impact", "1": "Minor", "2": "Major", "3": "Critical"},
                     "probabilities": {"0": 0.0042, "1": 0.0043, "2": 0.0215, "3": 0.97},
                     "confidence": 0.922},
    },
    "usage": {"input_tokens": 346, "output_tokens": 0},
}


def adapter(handler, **kwargs):
    return CloudflareAdapter(account_id=ACCOUNT_ID, auth_token=TOKEN,
                             transport=httpx.MockTransport(handler), **kwargs)


@pytest.mark.parametrize("model", ["clef", "clef-flash"])
def test_native_answers_are_preserved_and_only_public_inputs_are_sent(model):
    result = {**deepcopy(RESULT), "model": model}
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "POST"
        assert str(request.url) == f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/@cf/cloudflare/{model}"
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        assert json.loads(request.content) == {"model": model, **REQUEST}
        return httpx.Response(200, json={"success": True, "result": result, "errors": [], "messages": []})

    client = adapter(handler, model=model)
    try:
        client.start_episode("test-session")
        response = client.system_one({**deepcopy(REQUEST), "gold": "private authoring data"})
        validate_response(response, REQUEST["questions"])
        assert response == result
        assert len(calls) == 1
    finally:
        client.close()
    assert client.client.is_closed


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500])
def test_api_rejections_are_not_retried_or_echoed(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"success": False, "errors": [{"message": "private input or token"}]})

    client = adapter(handler)
    try:
        with pytest.raises(CloudflareAPIError) as caught:
            client.system_one(REQUEST)
        assert caught.value.status_code == status
        assert not is_transport_error(caught.value)
        assert "private" not in str(caught.value)
        assert len(calls) == 1
    finally:
        client.close()


def test_unsuccessful_envelope_cannot_be_used_as_an_answer():
    client = adapter(lambda request: httpx.Response(200, json={"success": False, "result": RESULT}))
    try:
        with pytest.raises(CloudflareAPIError):
            client.system_one(REQUEST)
    finally:
        client.close()


@pytest.mark.parametrize("field,value", [
    ("model", None), ("model", ""), ("answers", None), ("usage", None),
    ("usage", {"input_tokens": 10}),
    ("usage", {"input_tokens": -1, "output_tokens": 0}),
    ("usage", {"input_tokens": True, "output_tokens": 0}),
])
def test_missing_or_invalid_result_metadata_is_rejected(field, value):
    result = {**deepcopy(RESULT), field: value}
    client = adapter(lambda request: httpx.Response(200, json={"success": True, "result": result}))
    try:
        with pytest.raises(ContractError):
            client.system_one(REQUEST)
    finally:
        client.close()


@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError])
def test_runner_records_each_network_attempt_and_retries_the_same_public_input(failure):
    ep = example(0.01)
    calls = []
    events = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        if len(calls) == 1:
            raise failure("private exception text", request=request)
        t = body["state"]["event"]
        answers = {}
        for key, question in body["questions"].items():
            label = next(label for label, semantic in ep["option_semantics"][key].items()
                         if semantic == ep["steps"][t]["gold"][key])
            answers[key] = make_answer(question, {option: float(option == label) for option in question["criteria"]})
        return httpx.Response(200, json={"success": True,
                                        "result": {"model": "clef", "answers": answers,
                                                   "usage": {"input_tokens": 10, "output_tokens": 0}}})

    records, releases = run_episode(ep, lambda: adapter(handler), events.append, workers=1,
                                    max_attempts=2, retry_delay_s=0)
    assert len(calls) == 4
    assert calls[0] == calls[1] == {"model": "clef", **request_for(ep, ep["steps"][0])}
    assert len(records[0]["attempts"]) == 2
    assert records[0]["attempts"][0]["retryable"]
    assert all(record["ok"] for record in records)
    assert sum(event["kind"] == "attempt" for event in events) == 4
    assert "private exception text" not in json.dumps(events)
    assert len(releases) == 3


def test_invalid_probabilities_stop_the_run_without_repair_or_retry():
    ep = example(0.01)
    events, calls = [], []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        answers = {key: {"type": "choice", "choice": next(iter(q["criteria"])),
                         "probabilities": {label: 0 for label in q["criteria"]}, "confidence": 0.0}
                   for key, q in body["questions"].items()}
        return httpx.Response(200, json={"success": True,
                                        "result": {"model": "clef", "answers": answers,
                                                   "usage": {"input_tokens": 10, "output_tokens": 0}}})

    with pytest.raises(IncompleteRunError):
        run_episode(ep, lambda: adapter(handler), events.append, max_attempts=5)
    assert len(calls) == 1
    attempt = next(event for event in events if event["kind"] == "attempt")
    assert attempt["error_type"] == "ContractError" and not attempt["retryable"]


def test_credentials_and_model_are_validated_before_any_request(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_AUTH_TOKEN", raising=False)
    with pytest.raises(ValueError, match="ACCOUNT_ID"):
        CloudflareAdapter()
    with pytest.raises(ValueError, match="AUTH_TOKEN"):
        CloudflareAdapter(account_id=ACCOUNT_ID)
    with pytest.raises(ValueError, match="ACCOUNT_ID"):
        CloudflareAdapter(account_id="../other-account", auth_token=TOKEN)
    with pytest.raises(ValueError, match="model"):
        CloudflareAdapter(model="unknown", account_id=ACCOUNT_ID, auth_token=TOKEN)


def test_cloudflare_cli_records_native_provider_settings_and_provenance(monkeypatch, tmp_path):
    import streamdecisionbench.adapters.cloudflare
    import streamdecisionbench.cli
    import streamdecisionbench.lite.runtime

    captured = {}
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACCOUNT_ID)
    monkeypatch.setenv("CLOUDFLARE_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://unrelated-provider.test/v1")
    monkeypatch.setattr(streamdecisionbench.cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(lite_cli, "load_dataset", lambda path: ([], {}))
    monkeypatch.setattr(streamdecisionbench.adapters.cloudflare, "CloudflareAdapter", lambda **kwargs: kwargs)

    def fake_run(episodes, manifest, factory, output, config):
        captured.update(config, adapter=factory())
        return {"result": "no API invoked"}

    monkeypatch.setattr(streamdecisionbench.lite.runtime, "run_dataset", fake_run)
    monkeypatch.setattr(sys, "argv", ["sdb-lite", "run", "--data", str(tmp_path), "--out", str(tmp_path / "out"),
                                    "--provider", "cloudflare", "--model", "clef", "--timeout", "30"])
    lite_cli.main()
    assert captured["provider"] == "cloudflare" and captured["model"] == "clef"
    assert captured["reasoning_effort"] is None and not captured["custom_endpoint"]
    assert captured["protocol"] == lite_cli.RETRY_PROTOCOL and captured["sdk_retries"] == 0
    assert captured["adapter"] == {"model": "clef", "timeout": 30.0}
    assert TOKEN not in json.dumps(captured) and ACCOUNT_ID not in json.dumps(captured)
    recorded = sources()
    assert "adapters/cloudflare.py" in recorded and "adapters/remote.py" in recorded
    assert len(recorded["adapters/cloudflare.py"]) == 64


@pytest.mark.parametrize("case", ["missing_account", "missing_token", "effort", "unknown_model"])
def test_cloudflare_cli_rejects_invalid_configuration(monkeypatch, tmp_path, case):
    import streamdecisionbench.cli

    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACCOUNT_ID)
    monkeypatch.setenv("CLOUDFLARE_AUTH_TOKEN", TOKEN)
    monkeypatch.setattr(streamdecisionbench.cli, "load_dotenv", lambda: None)
    argv = ["sdb-lite", "run", "--data", str(tmp_path), "--out", str(tmp_path / "out"),
            "--provider", "cloudflare", "--model", "clef"]
    if case == "missing_account":
        monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID")
    elif case == "missing_token":
        monkeypatch.delenv("CLOUDFLARE_AUTH_TOKEN")
    elif case == "effort":
        argv.extend(["--effort", "low"])
    else:
        argv[-1] = "unknown"
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as caught:
        lite_cli.main()
    assert caught.value.code == 2
    assert not (tmp_path / "out").exists()
