"""End-to-end checks of the harness: SDK -> mock Jev server -> evaluator -> metrics."""

from __future__ import annotations

from pathlib import Path

import pytest

from streamdecisionbench.adapters import make_adapter_factory
from streamdecisionbench.adapters.local import OracleAdapter
from streamdecisionbench.evaluator import evaluate
from streamdecisionbench.jev import ContractError, make_answer, validate_response
from streamdecisionbench.metrics import TemporalConfig, aggregate, match_transitions, stable_switches
from streamdecisionbench.mock_server import serve_in_background
from streamdecisionbench.schema import load_episodes

DATA = Path(__file__).resolve().parents[1] / "data" / "legacy" / "v0"


@pytest.fixture(scope="module")
def episodes():
    """A few built episodes of every schema version present (data/legacy/v0 may mix sdb/0.1 and sdb/0.2)."""
    eps = load_episodes(DATA)
    if not eps:
        pytest.skip("no built episodes")
    per_version: dict[str, list] = {}
    for e in eps:
        if len(per_version.setdefault(e["schema_version"], [])) < 2:
            per_version[e["schema_version"]].append(e)
    return [e for group in per_version.values() for e in group]


def test_oracle_through_sdk_and_mock_server(episodes, monkeypatch):
    from streamdecisionbench.adapters.remote import TypeSafeAdapter

    oracle = OracleAdapter(episodes)
    server, url = serve_in_background(lambda: oracle, api_key="test-key")
    try:
        factory = lambda: TypeSafeAdapter(model="jev-latest", base_url=url, api_key="test-key", max_retries=0)
        predictions = evaluate(factory, episodes, concurrency=2)
    finally:
        server.shutdown()
    metrics = aggregate(episodes, predictions)
    assert metrics["secondary"]["invalid_rate"] == 0
    assert metrics["primary"]["sba"] == 1.0
    assert metrics["primary"]["transition_f1"] == 1.0
    assert metrics["primary"]["esr"] == 0
    assert metrics["primary"]["latency_ms_p95"] > 0


def test_mock_server_rejects_bad_requests(episodes):
    from typesafe_sdk import TypeSafeAPIError

    from streamdecisionbench.adapters.remote import TypeSafeAdapter

    server, url = serve_in_background(make_adapter_factory("random"), api_key="test-key")
    try:
        adapter = TypeSafeAdapter(base_url=url, api_key="test-key", max_retries=0)
        with pytest.raises(TypeSafeAPIError):
            adapter.system_one({"state": "x", "questions": {"q": {"type": "score", "instructions": "?", "criteria": ["only"]}}})
        wrong_key = TypeSafeAdapter(base_url=url, api_key="nope", max_retries=0)
        with pytest.raises(TypeSafeAPIError):
            wrong_key.system_one({"state": "x", "questions": {"q": {"type": "noul", "instructions": "?"}}})
    finally:
        server.shutdown()


def test_response_contract():
    q = {"type": "choice", "instructions": "?", "criteria": {"A1": "a", "B2": "b"}}
    good = {"answers": {"q": make_answer(q, {"A1": 3, "B2": 1})}}
    validate_response(good, {"q": q})
    bad = {"answers": {"q": {**good["answers"]["q"], "choice": "B2"}}}
    with pytest.raises(ContractError):
        validate_response(bad, {"q": q})
    s = {"type": "score", "instructions": "?", "criteria": ["lo", "mid", "hi"]}
    validate_response({"answers": {"s": make_answer(s, {"0": 1, "1": 2, "2": 1})}}, {"s": s})
    # A reported near-tie may show the choice one rounding step below another option.
    q3 = {"type": "choice", "instructions": "?", "criteria": {"A": "a", "B": "b", "C": "c"}}
    tie = {"type": "choice", "confidence": 0.3, "choice": "A", "probabilities": {"A": 0.33, "B": 0.34, "C": 0.33}}
    validate_response({"answers": {"q": tie}}, {"q": q3})
    with pytest.raises(ContractError, match="most probable"):
        validate_response({"answers": {"q": {**tie, "probabilities": {"A": 0.32, "B": 0.36, "C": 0.32}}}}, {"q": q3})


def test_transition_matching():
    gold = list("AAAABBBBCCCCAAAA")
    cfg = TemporalConfig(delta=2, hold=2)
    matches, excess = match_transitions(gold, gold, cfg)
    assert all(m.delay == 0 for m in matches) and not excess
    late = list("AAAAABBBBCCCCAAA")  # every switch one tick late
    matches, excess = match_transitions(gold, late, cfg)
    assert [m.delay for m in matches] == [1, 1, 1] and not excess
    flicker = list("AAAABABBCCCCAAAA")  # a one-tick flicker is not a stable switch
    assert (5, "A") not in stable_switches(flicker, 2)
    never = list("A" * 16)
    matches, excess = match_transitions(gold, never, cfg)
    assert all(m.switch is None for m in matches)
    spurious = list("AAAABBBBCCCCAAAD")[:15] + ["D"]
    _, excess = match_transitions(gold, list("AAAABBBBCCZZCAAA"), cfg)
    assert excess  # a held switch to a wrong decision is an excess switch
