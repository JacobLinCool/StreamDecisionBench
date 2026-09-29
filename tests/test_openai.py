"""The OpenAI adapter, end to end through the official SDK against a fake Responses API."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from streamdecisionbench.adapters import FatalAdapterError, make_adapter_factory
from streamdecisionbench.adapters.llm import OpenAIAdapter, answer_schema
from streamdecisionbench.adapters.local import OracleAdapter
from streamdecisionbench.evaluator import evaluate
from streamdecisionbench.jev import committed_answer
from streamdecisionbench.metrics import aggregate
from streamdecisionbench.schema import build_request, load_episodes

openai = pytest.importorskip("openai")

DATA = Path(__file__).resolve().parents[1] / "data" / "legacy" / "v0"
# Between them: choice, score and noul questions.
EPISODES = ["incident_b_canonical", "dialogue_b_minimal_cf"]


@pytest.fixture(scope="module")
def episodes():
    eps = load_episodes(DATA, EPISODES)
    if len(eps) != len(EPISODES):
        pytest.skip("episodes not built")
    return eps


def response_body(model: str, text: str, status: str = "completed") -> dict:
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 0,
        "status": status,
        "model": f"{model}-2026-09-01",
        "output": [
            {
                "type": "message",
                "id": "msg_test",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
        "usage": {
            "input_tokens": 1200,
            "input_tokens_details": {"cached_tokens": 1024},
            "output_tokens": 20,
            "output_tokens_details": {"reasoning_tokens": 8},
            "total_tokens": 1220,
        },
        "incomplete_details": None if status == "completed" else {"reason": "max_output_tokens"},
        "error": None,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
    }


def fake_client(handler) -> "openai.OpenAI":
    return openai.OpenAI(
        api_key="test",
        base_url="https://openai.test/v1",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def oracle_handler(episodes, calls: list, status: str = "completed"):
    oracle = OracleAdapter(episodes)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/responses"
        body = json.loads(request.content)
        calls.append(body)
        payload = json.loads(body["input"])
        wire = {"state": payload["state"], "questions": payload["questions"]}
        answers = oracle.answer(wire)
        committed = {k: committed_answer(q, answers[k]) for k, q in wire["questions"].items()}
        return httpx.Response(200, json=response_body(body["model"], json.dumps(committed), status))

    return handler


def test_oracle_through_openai_sdk(episodes):
    calls: list = []
    handler = oracle_handler(episodes, calls)
    factory = lambda: OpenAIAdapter(model="gpt-test", effort="low", client=fake_client(handler))
    predictions = evaluate(factory, episodes, concurrency=2)
    metrics = aggregate(episodes, predictions)
    assert metrics["secondary"]["invalid_rate"] == 0
    assert metrics["primary"]["sba"] == 1.0

    assert len(calls) == sum(len(e["steps"]) for e in episodes)
    body = calls[0]
    assert body["store"] is False
    assert body["reasoning"] == {"effort": "low"}
    assert body["text"]["format"]["strict"] is True
    assert body["input"].startswith('{"questions"')
    # One prompt cache key per episode stream.
    assert len({c["prompt_cache_key"] for c in calls}) == len(episodes)

    record = next(iter(predictions.values()))[0]
    assert record["model"] == "gpt-test-2026-09-01"
    assert record["usage"] == {"input_tokens": 1200, "cached_tokens": 1024, "output_tokens": 20, "reasoning_tokens": 8}


def test_answer_schema_admits_only_defined_answers(episodes):
    episode = episodes[0]
    request = build_request(episode, episode["steps"][0])
    schema = answer_schema(request)
    assert schema["required"] == list(request["questions"])
    assert schema["additionalProperties"] is False
    for key, q in request["questions"].items():
        prop = schema["properties"][key]
        if q["type"] == "choice":
            assert prop == {"type": "string", "enum": sorted(q["criteria"])}
        elif q["type"] == "score":
            assert prop == {"type": "integer", "enum": list(range(len(q["criteria"])))}
        else:
            assert prop == {"type": "boolean"}
    # Stable across ticks although the option order is shuffled per tick.
    later = build_request(episode, episode["steps"][50])
    assert answer_schema(later) == schema


def test_incomplete_response_is_a_failed_tick(episodes):
    handler = oracle_handler(episodes, [], status="incomplete")
    factory = lambda: OpenAIAdapter(model="gpt-test", client=fake_client(handler))
    predictions = evaluate(factory, episodes[:1])
    records = predictions[episodes[0]["episode_id"]]
    assert not any(r["ok"] for r in records)
    assert "incomplete" in records[0]["error"]


def test_rejected_key_stops_the_run(episodes, tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Incorrect API key", "type": "invalid_request_error"}})

    factory = lambda: OpenAIAdapter(model="gpt-test", client=fake_client(handler))
    with pytest.raises(FatalAdapterError):
        evaluate(factory, episodes, out=tmp_path, concurrency=2)
    predictions = tmp_path / "predictions.jsonl"
    assert not predictions.exists() or not predictions.read_text().strip()


def test_factory_needs_model_and_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        make_adapter_factory("openai:gpt-test")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    with pytest.raises(ValueError, match="needs a model"):
        make_adapter_factory("openai:")
    adapter = make_adapter_factory("openai:gpt-test@minimal")()
    assert (adapter.model, adapter.effort, adapter.name) == ("gpt-test", "minimal", "openai:gpt-test@minimal")
    adapter.close()
