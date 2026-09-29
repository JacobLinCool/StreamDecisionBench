"""Recording selected families or episodes and merging parts into one complete run."""

import json
from pathlib import Path

import pytest

from streamdecisionbench.lite import SCHEMA_VERSION
from streamdecisionbench.lite.__main__ import merge_runs, rescore_run
from streamdecisionbench.lite.core import digest, select_episodes, validate_episode
from streamdecisionbench.lite.retry_scoring import PROTOCOL, summarize_normalized
from streamdecisionbench.lite.runtime import run_dataset
from test_lite_core import example
from test_lite_runtime_retries import answer

BASE = example(0.01)


def _episode(eid, family, **changes):
    return {**BASE, "episode_id": eid, "task_family": family, **changes}


def _dataset(path, episodes):
    hashes = {e["episode_id"]: digest(e) for e in episodes}
    manifest = {"schema_version": SCHEMA_VERSION, "episodes": [validate_episode(e) for e in episodes],
                "hashes": hashes, "dataset_hash": digest(hashes)}
    path.mkdir()
    for e in episodes:
        (path / f"{e['episode_id']}.json").write_text(json.dumps(e))
    (path / "manifest.json").write_text(json.dumps(manifest))
    return manifest


def _record(path, episodes, manifest, *, served="served-1", max_attempts=1):
    class Adapter:
        def start_episode(self, session):
            pass

        def close(self):
            pass

        def system_one(self, request):
            return {**answer(BASE, request), "model": served}

    config = {"protocol": PROTOCOL, "workers": 1, "max_attempts": max_attempts, "retry_delay_s": 0,
              "selection": {"episodes": [e["episode_id"] for e in episodes]}}
    run_dataset(episodes, manifest, Adapter, path, config, progress=lambda *a, **kw: None)
    return path


@pytest.fixture
def build(tmp_path):
    episodes = [_episode("f1_a", "f1"), _episode("f1_b", "f1"), _episode("f2_a", "f2")]
    return episodes, _dataset(tmp_path / "data", episodes), tmp_path


def test_selection_keeps_dataset_order_and_rejects_unknown_names(build):
    episodes, _, _ = build
    assert [e["episode_id"] for e in select_episodes(episodes, families=["f2", "f1"])] == ["f1_a", "f1_b", "f2_a"]
    assert [e["episode_id"] for e in select_episodes(episodes, episode_ids=["f2_a", "f1_a"])] == ["f1_a", "f2_a"]
    assert select_episodes(episodes) == episodes
    with pytest.raises(ValueError, match="f3"):
        select_episodes(episodes, families=["f3"])
    with pytest.raises(ValueError, match="either"):
        select_episodes(episodes, families=["f1"], episode_ids=["f2_a"])


def test_merged_parts_score_exactly_as_recorded(build):
    episodes, manifest, root = build
    first = _record(root / "first", select_episodes(episodes, families=["f1"]), manifest)
    second = _record(root / "second", select_episodes(episodes, families=["f2"]), manifest)
    combined = merge_runs([second, first], root / "data", root / "merged")
    parts = [rescore_run(first)["scores"], rescore_run(second)["scores"]]
    assert combined == summarize_normalized(parts[0]["per_episode"] + parts[1]["per_episode"])
    assert rescore_run(root / "merged")["scores"] == combined
    frozen = json.loads((root / "merged" / "run.json").read_text())
    assert [e["episode_id"] for e in json.loads((root / "merged" / "episodes.json").read_text())] == ["f1_a", "f1_b", "f2_a"]
    assert [p["episodes"] for p in frozen["combined_from"]] == [["f2_a"], ["f1_a", "f1_b"]]
    assert "selection" not in frozen["config"] and frozen["dataset_manifest"] == manifest


@pytest.mark.parametrize("problem", ["overlap", "missing", "settings", "served", "changed_episode"])
def test_merge_refuses_parts_that_do_not_form_one_setting_on_this_build(build, problem):
    episodes, manifest, root = build
    first = _record(root / "first", episodes[:2], manifest)
    if problem == "overlap":
        second = _record(root / "second", episodes[1:], manifest)
    elif problem == "missing":
        second = None
    elif problem == "settings":
        second = _record(root / "second", episodes[2:], manifest, max_attempts=2)
    elif problem == "served":
        second = _record(root / "second", episodes[2:], manifest, served="served-2")
    else:
        second = _record(root / "second", episodes[2:], manifest)
        changed = [*episodes[:2], _episode("f2_a", "f2", title="revised")]
        _dataset(root / "rebuilt", changed)
    data = root / ("rebuilt" if problem == "changed_episode" else "data")
    match = {"overlap": "more than one part", "missing": "no part records f2_a", "settings": "max_attempts",
             "served": "different served models", "changed_episode": "not an episode of this build"}[problem]
    with pytest.raises(ValueError, match=match):
        merge_runs([p for p in (first, second) if p], data, root / "merged")
    assert not (root / "merged").exists()
    if problem == "served":
        merge_runs([first, second], data, root / "merged", allow_served_model_change=True)
        served = [p["served_models"] for p in json.loads((root / "merged" / "run.json").read_text())["combined_from"]]
        assert served == [["served-1"], ["served-2"]]


def test_merge_names_parts_relative_to_the_merged_folder(build, monkeypatch):
    """combined_from records each part relative to the merged run folder, whatever the working directory."""
    episodes, manifest, root = build
    _record(root / "first", select_episodes(episodes, families=["f1"]), manifest)
    _record(root / "second", select_episodes(episodes, families=["f2"]), manifest)
    monkeypatch.chdir(root / "first")
    merge_runs([Path("../second"), Path(".")], Path("../data"), Path("../out/merged"))
    frozen = json.loads((root / "out" / "merged" / "run.json").read_text())
    assert [p["run"] for p in frozen["combined_from"]] == ["../../second", "../../first"]

