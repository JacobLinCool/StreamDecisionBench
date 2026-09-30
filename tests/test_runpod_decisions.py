"""Native payload preservation and process cleanup for the paid experiment."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/runpod" / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def request():
    return {"state": {"logs": ["A", "B"], "tick": 4}, "questions": {
        "route": {"type": "choice", "instructions": {"rule": ["keep", "all"]},
                  "criteria": {"K02": "repair: do this", "K01": {"rule": "wait"}}}}}


def test_native_encodings_preserve_structured_instructions_and_option_order():
    record = module("decision_record")
    original = request()
    encoded = record.enum_schema(original)["route"]
    assert json.loads(encoded["description"]) == original["questions"]["route"]["instructions"]
    assert encoded["choices"] == ["K02", "K01"]
    assert json.loads(encoded["choice_descriptions"]["K01"]) == {"rule": "wait"}
    row = list(record.direct_rows(original))[0]
    assert row["state"] == original["state"]
    assert [o["id"] for o in row["options"]] == encoded["choices"]
    assert json.loads(row["question"]) == original["questions"]["route"]["instructions"]


def test_choice_conversion_preserves_native_committed_tie_and_probabilities():
    record = module("decision_record")
    p = {"K02": 0.5, "K01": 0.5}
    answer = record.choice_answer("K01", p)
    assert answer["choice"] == "K01" and answer["probabilities"] == p
    assert answer["confidence"] == 0


def test_timeout_kills_installer_descendants(tmp_path):
    cohort = module("decision_cohort")
    sentinel = tmp_path / "orphan"
    child = f"import time,pathlib;time.sleep(1);pathlib.Path({str(sentinel)!r}).touch()"
    parent = f"import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',{child!r}]);time.sleep(30)"
    with pytest.raises(subprocess.TimeoutExpired):
        cohort.bounded_run([sys.executable, "-c", parent], tmp_path / "log", 0.2)
    # A separate bounded child is a timer; it cannot be killed with the tested group.
    subprocess.run([sys.executable, "-c", "import time;time.sleep(1.1)"], check=True)
    assert not sentinel.exists()
