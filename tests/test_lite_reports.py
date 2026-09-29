"""Frozen report verification across physical and retry-excluded time bases."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

from streamdecisionbench.lite import __main__ as lite_cli
from streamdecisionbench.lite.core import compose, digest, encode_scenario, request_for, sources
from streamdecisionbench.lite.retry_scoring import normalized_episode_scores, summarize_normalized
from streamdecisionbench.lite.scoring import episode_scores, summarize

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "lite"))
import lite_compare
import lite_report


def _write_recording(path, *, normalized=True):
    question = lambda values: {"type": "choice", "instructions": "Choose the specified value.", "criteria": {v: v for v in values}}
    episode = encode_scenario({
        "episode_id": "test", "task_family": "test", "scenario_id": "test", "title": "Report fixture", "tick_seconds": 2.0,
        "questions": {"route": question(["A", "B"]), "a": question(["yes", "no"]), "b": question(["yes", "no"])},
        "decision_spec": {"route_question": "route", "always": [], "branches": {"A": ["a"], "B": ["b"]}},
        "steps": [
            {"t": 0, "state": {"event": 0}, "gold": {"route": "A", "a": "yes", "b": "no"}, "evidence": ["initial"]},
            {"t": 1, "state": {"event": 1}, "gold": {"route": "A", "a": "yes", "b": "yes"}, "evidence": ["inactive"]},
            {"t": 2, "state": {"event": 2}, "gold": {"route": "B", "a": "yes", "b": "yes"}, "evidence": ["new route"]},
        ],
    })
    releases = [{"episode_id": "test", "t": t, "planned_s": 2.0 * t, "release_s": 2.0 * t} for t in range(3)]
    histories = [
        [{"attempt": 1, "started_s": 0.05, "completed_s": 0.55, "ok": False, "retryable": True, "error_type": "APIConnectionError"},
         {"attempt": 2, "started_s": 1.05, "received_s": 1.43, "completed_s": 1.45, "ok": True, "retryable": False}],
        [{"attempt": 1, "started_s": 2.1, "received_s": 2.58, "completed_s": 2.6, "ok": True, "retryable": False}],
        [{"attempt": 1, "started_s": 4.2, "received_s": 4.58, "completed_s": 4.6, "ok": True, "retryable": False}],
    ]
    records, events = [], [{"kind": "release", **r} for r in releases]
    for step, attempts in zip(episode["steps"], histories):
        success = attempts[-1]
        record = {"episode_id": "test", "t": step["t"], "request_hash": digest(request_for(episode, step)),
                  "ok": True, "pred": step["gold"], "decision": compose(episode["decision_spec"], step["gold"]),
                  "wire_answers": {q: next(label for label, value in episode["option_semantics"][q].items() if value == answer)
                                   for q, answer in step["gold"].items()},
                  "started_s": attempts[0]["started_s"], "received_s": success["received_s"], "completed_s": success["completed_s"],
                  "accepted": True, "accepted_s": success["completed_s"] + 0.05, "discard_reason": None,
                  "release_s": 2.0 * step["t"], "model": "test-model", "usage": {"input_tokens": 0, "output_tokens": 0}}
        if normalized:
            record.update(attempts=attempts, actual_recorded_s=record["accepted_s"])
            events.extend({"kind": "attempt", "episode_id": "test", "t": step["t"], "request_hash": record["request_hash"], **a} for a in attempts)
        records.append(record)
        events.append({"kind": "response", **record})
    events.sort(key=lambda e: e["release_s"] if e["kind"] == "release" else e["completed_s"])
    raw = summarize([episode_scores(episode, records, releases)])
    primary = summarize_normalized([normalized_episode_scores(episode, records, releases)]) if normalized else raw
    config = {"model": "test-model", "reasoning_effort": "low", "workers": 32, "episode_concurrency": 1,
              "protocol": lite_cli.RETRY_PROTOCOL if normalized else lite_cli.PHYSICAL_PROTOCOL,
              "request_timeout_s": 20.0, "sdk_retries": 0, "custom_endpoint": False, "untimed": "fixture"}
    if normalized:
        config.update(max_attempts=5, retry_delay_s=0.5)
    path.mkdir()
    event_bytes = ("\n".join(json.dumps(e) for e in events) + "\n").encode()
    hashes = {"test": digest(episode)}
    frozen = {"status": "complete", "config": config, "dataset_manifest": {"hashes": hashes, "dataset_hash": digest(hashes)},
              "run_sources": sources(), "events_sha256": hashlib.sha256(event_bytes).hexdigest(),
              "started_at_utc": "2026-01-01T00:00:00Z", "finished_at_utc": "2026-01-01T00:00:06Z"}
    (path / "run.json").write_text(json.dumps(frozen))
    (path / "episodes.json").write_text(json.dumps([episode]))
    (path / "events.jsonl").write_bytes(event_bytes)
    (path / "metrics.json").write_text(json.dumps(primary))
    if normalized:
        (path / "raw_wallclock_metrics.json").write_text(json.dumps(raw))
    return frozen


def test_retry_report_uses_successful_attempts_and_separates_raw_time(tmp_path):
    run = tmp_path / "run"
    _write_recording(run)
    data = lite_report.analyze(run)
    assert data["latency_s"]["p50"] == pytest.approx(0.4)
    assert data["raw_wallclock_latency_s"]["p50"] == pytest.approx(0.5)
    assert data["scores"]["overall"]["time_accuracy"] > data["raw_wallclock_scores"]["overall"]["time_accuracy"]
    assert data["retry_reliability"]["attempts"] == 4
    assert data["retry_reliability"]["failed_attempts"] == 1
    assert data["retry_reliability"]["attempt_error_rate"] == 0.25
    assert data["retry_reliability"]["retried_logical_rate"] == 1 / 3
    output = tmp_path / "report"
    lite_report.report(data, output)
    text = (output / "REPORT.md").read_text()
    assert "成功 attempt" in text and "原始時鐘診斷" in text
    assert "1 個失敗 attempts／全部 4 個 attempts" in text
    assert "1 個曾重試 requests／全部 3 個 logical requests" in text
    assert data["analysis_sources"] and data["run_sources"]


def test_historical_raw_run_survives_runtime_changes_without_reinterpreting_scores(tmp_path):
    run = tmp_path / "raw"
    frozen = _write_recording(run, normalized=False)
    frozen["run_sources"]["lite/runtime.py"] = "historical-runtime-version"
    frozen["run_sources"]["lite/scoring.py"] = "historical-scorer-version"
    (run / "run.json").write_text(json.dumps(frozen))
    data = lite_report.analyze(run)
    assert data["time_basis"] == lite_cli.PHYSICAL_PROTOCOL
    assert data["raw_wallclock_scores"] is None
    assert data["scores"] == json.loads((run / "metrics.json").read_text())
    assert data["run_sources"]["lite/runtime.py"] == "historical-runtime-version"
    assert data["analysis_sources"]["lite/runtime.py"] != "historical-runtime-version"


def test_compare_rejects_mixed_time_basis_and_retains_retry_denominators(tmp_path):
    _write_recording(tmp_path / "raw", normalized=False)
    _write_recording(tmp_path / "normalized")
    raw, normalized = lite_report.analyze(tmp_path / "raw"), lite_report.analyze(tmp_path / "normalized")
    with pytest.raises(ValueError, match="time_basis"):
        lite_compare.compare(raw, normalized)
    other = deepcopy(normalized)
    other["run"] = "another-recording"
    other["config"]["model"] = "another-model"
    comparison = lite_compare.compare(normalized, other)
    lite_compare.report(comparison, tmp_path / "comparison")
    text = (tmp_path / "comparison" / "COMPARISON.md").read_text()
    assert "25.00%（1/4）" in text
    assert "33.33%（1/3）" in text
    assert comparison["overall"]["paired_decision_counts"]["both_correct"] == 3
    jev = deepcopy(other)
    jev["config"].update(provider="typesafe", model="jev-latest", reasoning_effort=None)
    jev["run_sources"] = {**jev["run_sources"], "lite/runtime.py": "a-later-runtime"}
    assert "reasoning_effort" not in lite_compare.compare(normalized, jev)["matched_config_excluding_model"]
    jev["config"]["workers"] = 8
    with pytest.raises(ValueError, match="workers"):
        lite_compare.compare(normalized, jev)


def test_attempt_event_and_embedded_attempt_must_match_even_with_updated_log_hash(tmp_path):
    run = tmp_path / "run"
    frozen = _write_recording(run)
    events = [json.loads(line) for line in (run / "events.jsonl").read_text().splitlines()]
    next(e for e in events if e["kind"] == "attempt")["completed_s"] += 0.1
    event_bytes = ("\n".join(json.dumps(e) for e in events) + "\n").encode()
    (run / "events.jsonl").write_bytes(event_bytes)
    frozen["events_sha256"] = hashlib.sha256(event_bytes).hexdigest()
    (run / "run.json").write_text(json.dumps(frozen))
    with pytest.raises(ValueError, match="attempt event differs"):
        lite_report.analyze(run)


def test_incomplete_runs_are_rejected_and_saved_metrics_do_not_override_rescoring(tmp_path):
    run = tmp_path / "run"
    frozen = _write_recording(run)
    frozen["status"] = "incomplete"
    (run / "run.json").write_text(json.dumps(frozen))
    with pytest.raises(ValueError, match="incomplete"):
        lite_report.analyze(run)
    frozen["status"] = "complete"
    (run / "run.json").write_text(json.dumps(frozen))
    raw = json.loads((run / "raw_wallclock_metrics.json").read_text())
    raw["overall"]["time_accuracy"] = 1
    (run / "raw_wallclock_metrics.json").write_text(json.dumps(raw))
    assert lite_report.analyze(run)["raw_wallclock_scores"]["overall"]["time_accuracy"] != 1


def test_cli_new_runs_default_to_explicit_retry_protocol(monkeypatch, tmp_path):
    import streamdecisionbench.cli
    import streamdecisionbench.lite.runtime

    captured = {}
    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder")
    monkeypatch.setattr(streamdecisionbench.cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(lite_cli, "load_dataset", lambda path: ([], {}))

    def fake_run(episodes, manifest, factory, output, config):
        captured.update(config)
        return {"result": "no API invoked"}

    monkeypatch.setattr(streamdecisionbench.lite.runtime, "run_dataset", fake_run)
    monkeypatch.setattr(sys, "argv", ["sdb-lite", "run", "--data", str(tmp_path), "--out", str(tmp_path / "out"),
                                    "--model", "test-model", "--effort", "low"])
    lite_cli.main()
    assert captured["protocol"] == lite_cli.RETRY_PROTOCOL
    assert captured["max_attempts"] == 5 and captured["retry_delay_s"] == 0.5
    assert captured["sdk_retries"] == 0


def test_cli_typesafe_provider_records_no_effort_and_disables_sdk_retries(monkeypatch, tmp_path):
    import streamdecisionbench.adapters.remote
    import streamdecisionbench.cli
    import streamdecisionbench.lite.runtime

    captured = {}
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-placeholder")
    monkeypatch.delenv("TYPESAFE_BASE_URL", raising=False)
    monkeypatch.setattr(streamdecisionbench.cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(lite_cli, "load_dataset", lambda path: ([], {}))

    def fake_run(episodes, manifest, factory, output, config):
        captured.update(config, adapter=factory())
        return {"result": "no API invoked"}

    monkeypatch.setattr(streamdecisionbench.lite.runtime, "run_dataset", fake_run)
    monkeypatch.setattr(streamdecisionbench.adapters.remote, "TypeSafeAdapter", lambda **kwargs: kwargs)
    argv = ["sdb-lite", "run", "--data", str(tmp_path), "--out", str(tmp_path / "out"), "--provider", "typesafe", "--model", "jev-latest"]
    monkeypatch.setattr(sys, "argv", argv)
    lite_cli.main()
    assert captured["provider"] == "typesafe" and captured["reasoning_effort"] is None
    assert captured["protocol"] == lite_cli.RETRY_PROTOCOL and captured["sdk_retries"] == 0
    assert captured["adapter"] == {"model": "jev-latest", "timeout": 20.0, "max_retries": 0}
    assert lite_report.model_label(captured) == "jev-latest"
    monkeypatch.setattr(sys, "argv", argv + ["--effort", "low"])
    with pytest.raises(SystemExit):
        lite_cli.main()


def test_network_estimate_recovers_a_known_delay_and_appears_as_a_secondary_section(tmp_path):
    import numpy as np
    import network

    rng = np.random.default_rng(1)
    X = np.column_stack([np.ones(400), rng.uniform(2, 4, 400), rng.uniform(50, 200, 400)])
    y = 0.3 + 0.0 * X[:, 1] + 0.01 * X[:, 2] + rng.exponential(0.2, 400)
    coef = network.fit(X, y)
    assert coef[0] == pytest.approx(0.3, abs=0.05) and coef[1] >= 0 and coef[2] == pytest.approx(0.01, abs=0.002)
    run = tmp_path / "run"
    _write_recording(run)
    data = lite_report.analyze(run)
    net = data["network_adjustment"]
    assert net["network_s"]["low"] <= net["network_s"]["estimate"] <= net["network_s"]["high"] <= net["latency_floor_s"] + 1e-9
    assert net["observed"]["overall"] == data["scores"]["overall"]["time_accuracy"]
    assert net["scores"]["low"]["overall"]["time_accuracy"] <= net["scores"]["high"]["overall"]["time_accuracy"] <= net["untimed_ceiling"]["overall"]
    lite_report.report(data, tmp_path / "report")
    assert "移除網路延遲後的估計（次要）" in (tmp_path / "report" / "REPORT.md").read_text()
    raw = tmp_path / "raw"
    _write_recording(raw, normalized=False)
    assert lite_report.analyze(raw)["network_adjustment"] is None
    other = deepcopy(data)
    other["run"], other["config"]["model"] = "another-recording", "another-model"
    assert lite_compare.compare(data, other)["network_adjustment"]["overall"]["ranges_overlap"] is True
    assert lite_compare.compare(lite_report.analyze(raw), deepcopy(lite_report.analyze(raw)))["network_adjustment"] is None


def test_network_fit_survives_an_almost_constant_output_length():
    import numpy as np
    import network

    rng = np.random.default_rng(3)
    y = 1.0 + rng.exponential(0.3, 300)
    X = np.column_stack([np.ones(300), rng.uniform(2, 4, 300), np.full(300, 48.0)])
    for _ in range(20):
        index = rng.integers(0, 300, 300)
        coef = network.fit(X[index], y[index])
        assert np.all(np.isfinite(coef)) and coef[1] >= 0 and coef[2] >= 0
        assert y[index].min() - 1e-6 <= coef[0] + coef[1] * X[index, 1].min() + coef[2] * 48 <= y[index].max()


def test_analysis_names_runs_relative_to_the_repository(tmp_path, monkeypatch):
    """Reports store repository-relative run paths for new relative and old absolute merge entries alike."""
    run, part = tmp_path / "merged", tmp_path / "part"
    frozen = _write_recording(run)
    frozen["combined_from"] = [{"run": "../part"}, {"run": str(part)}]
    (run / "run.json").write_text(json.dumps(frozen))
    monkeypatch.chdir(tmp_path)
    data = lite_report.analyze(Path("merged"))
    paths = [data["run"], *(p["run"] for p in data["combined_from"])]
    assert not any(Path(p).is_absolute() for p in paths)
    assert (lite_report.ROOT / data["run"]).resolve() == run.resolve()
    assert [(lite_report.ROOT / p["run"]).resolve() for p in data["combined_from"]] == [part.resolve()] * 2

