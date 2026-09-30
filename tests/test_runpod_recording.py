"""Open-weight transport boundaries and refusal to report incomplete runs."""
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from streamdecisionbench.adapters.base import FatalAdapterError

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/runpod" / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_djev_preserves_native_answers_and_declared_sampling(monkeypatch):
    record = module("record")
    captured = []
    native = {"model": "dgemma", "answers": {"q": {"type": "noul", "noul": 0.25}},
              "usage": {"input_tokens": 10, "output_tokens": 0}, "diagnostics": {"steps": 1}}

    def handler(request):
        captured.append((json.loads(request.content), request.headers))
        return httpx.Response(200, json=native)

    client = httpx.Client(base_url="http://local", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "Client", lambda **_: client)
    monkeypatch.setenv("TYPESAFE_API_KEY", "must-never-leak")
    adapter = record.DJevAdapter("http://local", "dgemma")
    request = {"state": {"tick": 1}, "questions": {"q": {"type": "noul", "instructions": "Ready?"}}}
    response = adapter.system_one(request)
    assert response["answers"] == native["answers"]
    assert response["usage"]["djev_diagnostics"] == native["diagnostics"]
    body, headers = captured[0]
    assert body["state"] == request["state"] and body["questions"] == request["questions"]
    assert (body["steps"], body["think"], body["samples"], body["auto_max"], body["seed"]) == (1, 0, "auto", 4, 42)
    assert "authorization" not in headers
    adapter.close()


@pytest.mark.parametrize("failure", ["network", "status", "malformed"])
def test_only_transport_failures_can_be_retried(monkeypatch, failure):
    record = module("record")

    def handler(request):
        if failure == "network":
            raise httpx.ReadTimeout("timed out", request=request)
        if failure == "status":
            return httpx.Response(400, json={"error": "schema rejected"})
        return httpx.Response(200, content="not json")

    client = httpx.Client(base_url="http://local", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "Client", lambda **_: client)
    adapter = record.DJevAdapter("http://local", "dgemma")
    expected = {"network": ConnectionError, "status": FatalAdapterError, "malformed": json.JSONDecodeError}[failure]
    with pytest.raises(expected):
        adapter.system_one({"state": {}, "questions": {}})
    adapter.close()


def test_summary_never_scores_incomplete_recordings(tmp_path, monkeypatch):
    summary = module("summarize")
    monkeypatch.setattr(summary, "ROOT", tmp_path)
    run = tmp_path / "raw/runs/laya-english"
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"status": "incomplete"}))
    result = summary.summarize(tmp_path / "raw", tmp_path / "reports")
    assert result["complete_settings"] == 0
    assert result["results"] == []
    assert len(result["failures"]) == 4
    assert not (tmp_path / "reports/results.csv").exists()


def test_summary_rejects_corrupt_event_hash_before_analysis(tmp_path):
    summary = module("summarize")
    run = tmp_path / "raw/runs/laya-english"
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"status": "complete", "events_sha256": "incorrect"}))
    (run / "events.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="event hash mismatch"):
        summary.summarize(tmp_path / "raw", tmp_path / "reports")
