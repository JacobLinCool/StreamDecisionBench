"""The training split: its variants are valid, kept apart from evaluation, and leave the evaluation build unchanged."""

from copy import deepcopy
from collections import Counter
import json
from pathlib import Path

import pytest

from streamdecisionbench.lite.core import build_dataset, load_dataset
from streamdecisionbench.lite.training import MODULES, modules
from streamdecisionbench.lite.training.audit import (
    FAMILIES, MAX_LAYOUT_OVERLAP, SHARED_SPEC, check_module, eval_scenarios, layout_overlap, leakage, spec_overlap)

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "data/lite/v1"
TRAIN = ROOT / "data/lite/train-v1"


@pytest.fixture(scope="module")
def training():
    return [s for m in modules() for s in m.scenarios()]


@pytest.fixture(scope="module")
def evaluation():
    return eval_scenarios()


def test_evaluation_build_is_unchanged(tmp_path):
    manifest = build_dataset(tmp_path / "eval")
    frozen = json.loads((EVAL / "manifest.json").read_text())
    assert manifest["dataset_hash"] == frozen["dataset_hash"]
    assert manifest["hashes"] == frozen["hashes"] and "split" not in manifest
    for eid in frozen["hashes"]:
        assert (tmp_path / "eval" / f"{eid}.json").read_bytes() == (EVAL / f"{eid}.json").read_bytes()


@pytest.mark.parametrize("name", MODULES)
def test_each_training_module_is_valid_and_reproduced_by_its_reference(name):
    module = next(m for m in modules() if m.__name__.endswith("." + name))
    result = check_module(module)
    for episode in result["episodes"]:
        assert episode["steps"] == 60 and episode["decision_transitions"] >= 10


def test_every_family_gains_at_least_two_training_variants(training, evaluation):
    ids = [s["episode_id"] for s in training]
    assert len(ids) == len(set(ids)) and all(i.startswith("train_") for i in ids)
    assert not set(ids) & {s["episode_id"] for s in evaluation}
    counts = Counter(s["task_family"] for s in training)
    assert set(counts) == FAMILIES and min(counts.values()) >= 2


def test_training_split_shares_no_evaluation_content(training, evaluation):
    assert leakage(training, evaluation) == []


def test_leakage_audit_rejects_copied_evaluation_content(training, evaluation):
    copied = deepcopy(evaluation[0])
    copied.update(episode_id="train_copy", scenario_id="train_copy", title="A new title")
    issues = leakage([copied], evaluation)
    assert any("equals an evaluation state" in i for i in issues)
    assert any("repeats evaluation text" in i for i in issues)
    # A single evaluation identifier or six-word run inside otherwise new text is also caught.
    variant = deepcopy(training[0])
    step = variant["steps"][-1]
    step["state"]["note"] = "Ask about src/refunds/grace.ts later."
    assert any("evaluation identifier" in i for i in leakage([variant], evaluation))
    step["state"]["note"] = "Keep the scratch notes.md open."
    assert any("evaluation identifier 'notes.md'" in i for i in leakage([variant], evaluation))
    step["state"]["note"] = "She said it: the decoder keeps one running hypothesis today."
    assert any("shares" in i for i in leakage([variant], evaluation))


def test_training_writes_its_own_rules_questions_and_state_layout(training, evaluation):
    own = [s for s in training if s["episode_id"] not in SHARED_SPEC]
    assert SHARED_SPEC <= {s["episode_id"] for s in training}
    assert {s["task_family"] for s in own} == FAMILIES
    assert spec_overlap(own, evaluation) == []
    for scenario in own:
        assert layout_overlap(scenario, evaluation) <= MAX_LAYOUT_OVERLAP, scenario["episode_id"]
        for evaluated in evaluation:
            if evaluated["task_family"] == scenario["task_family"]:
                assert set(scenario["questions"]) != set(evaluated["questions"])


def test_spec_audit_rejects_copied_rules_questions_and_layout(evaluation):
    copied = deepcopy(evaluation[-1])
    copied.update(episode_id="train_copy", scenario_id="train_copy", title="A new title")
    issues = spec_overlap([copied], evaluation)
    assert any("repeats evaluation rules" in i for i in issues)
    assert any("repeats an evaluation instruction" in i for i in issues)
    assert any("evaluation option set" in i for i in issues)
    assert layout_overlap(copied, evaluation) == 1.0
    # A paraphrase that keeps a ten-word run of an evaluation rule is still caught.
    rules = copied["steps"][0]["state"]["prepared"]["rules"]
    copied["steps"] = copied["steps"][:1]
    rules[:] = ["Our own wording first, then " + rules[0][:200]]
    assert any("shares" in i for i in spec_overlap([copied], evaluation))


def test_training_build_round_trips_and_matches_the_committed_build(tmp_path):
    manifest = build_dataset(tmp_path / "train", "train")
    episodes, loaded = load_dataset(tmp_path / "train")
    assert loaded == manifest and manifest["split"] == "train"
    assert {e["task_family"] for e in episodes} == FAMILIES
    committed = json.loads((TRAIN / "manifest.json").read_text())
    assert committed["hashes"] == manifest["hashes"]
    assert committed["dataset_hash"] == manifest["dataset_hash"]
    with pytest.raises(FileExistsError):
        build_dataset(tmp_path / "train", "train")


def test_unknown_split_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="unknown split"):
        build_dataset(tmp_path / "x", "dev")
