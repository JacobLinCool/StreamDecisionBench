"""Integrity failures and independent composition examples for the paper extension."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "paper/analysis"))
import lite_openweight as analysis
from trajectory_replay import Component, Scenario, evaluate, prepare

ROOT = Path(__file__).resolve().parents[1]
KEV = ROOT / "runs/runpod-openweight-20260930-round2/runs/kev-4b"


@pytest.fixture
def recording(tmp_path):
    for filename in ("run.json", "episodes.json", "events.jsonl"):
        shutil.copyfile(KEV / filename, tmp_path / filename)
    return tmp_path


def test_frozen_recording_loads_without_model_runtime(recording):
    run, hashes = analysis.verified_run(recording)
    assert len(run["episodes"]) == 8
    assert hashes["events.jsonl"] == run["frozen"]["events_sha256"]


def test_valid_json_event_change_is_rejected_by_frozen_hash(recording):
    path = recording / "events.jsonl"
    path.write_bytes(b" " + path.read_bytes())
    with pytest.raises(ValueError, match="event hash mismatch"):
        analysis.verified_run(recording)


def test_non_decision_state_edit_is_rejected_by_episode_hash(recording):
    path = recording / "episodes.json"
    episodes = json.loads(path.read_text())
    episodes[0]["steps"][0]["state"]["extra_audit_field"] = "changed"
    path.write_text(json.dumps(episodes))
    with pytest.raises(ValueError, match="episode hash mismatch"):
        analysis.verified_run(recording)


def test_different_frozen_content_cannot_be_composed(recording):
    run, _ = analysis.verified_run(recording)
    other = deepcopy(run)
    other["episodes"][0]["steps"][0]["state"]["extra_audit_field"] = "changed"
    with pytest.raises(ValueError, match="identical frozen episodes"):
        prepare({"first": run, "second": other})


def test_input_audit_issues_cannot_be_published(tmp_path, monkeypatch):
    spec = {"name": "fixture", "audit": "fixture.json", "audit_setting": "fixture"}
    path = tmp_path / "runs" / "fixture.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"dataset_hash": "dataset", "settings": {
        "fixture": {"model_revision": "revision", "states": 480, "question_rows": 3120,
                    "issues": ["truncated option"], "max_sequence_tokens": 10}}}))
    run = {"frozen": {"dataset_manifest": {"dataset_hash": "dataset"}, "config": {"model_revision": "revision"}}}
    monkeypatch.setattr(analysis, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="invalid input audit"):
        analysis.verify_audit(spec, run)


def test_new_wrong_provisional_answer_displaces_still_correct_old_correction():
    gold = ({"route": "A"},) * 3
    sc = Scenario("test", "test", 2, (0, 2, 4), gold, {
        "provisional": Component((gold[0], {"route": "B"}, {"route": "B"}), (.1, .1, .1)),
        "correction": Component(gold, (1.5, 1.5, 1.5)),
    })
    # Correction alone is correct from 1.5 until 6: 4.5/6.
    standalone = evaluate(sc, "correction", None, 2)
    # Composition is correct [.1,2.1), [3.5,4.1) and [5.5,6): 3.1/6.
    hybrid = evaluate(sc, "provisional", "correction", 2, trace=True)
    assert standalone["accuracy"] == pytest.approx(.75)
    assert hybrid["accuracy"] == pytest.approx(3.1 / 6)
    assert any(s["source_t"] == 1 and s["component"] == "provisional"
               and s["kind"] == "judgment" for s in hybrid["spans"])


def test_original_clock_replay_checks_all_six_time_classes():
    run, _ = analysis.verified_run(KEV)
    scenarios = prepare({"Kev": run})
    own, gap = analysis.verify_standalone(scenarios, "Kev", run)
    assert own[0].releases_s != scenarios[0].releases_s
    assert gap >= 0
