"""Manuscript aggregation preserves precision, scope and timing identities."""
import json
from pathlib import Path
import sys
from statistics import mean, stdev

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "paper/analysis"))
from lite_numbers import Macros, count, pct
from lite_repeated import aggregate_macros


def test_aggregation_rounds_after_averaging_and_sums_request_counts():
    groups = []
    for fraction in (.01449, .01449, .01459):
        group = Macros()
        group.add("Accuracy", pct(fraction), "independent pass")
        group.add("ValidResponses", count(480), "complete pass")
        groups.append(group)
    result = aggregate_macros(groups)
    assert result.items["Accuracy"].value == "1.5"
    assert result.items["ValidResponses"].value == "1440"


def test_three_pass_manifest_uses_exactly_the_manuscript_cohort():
    data = json.loads((ROOT / "docs/research/manuscript-three-pass/analysis.json").read_text())
    assert [r["pass"] for r in data["passes"]] == [1, 2, 3]
    assert len(data["hosted"]) == 6
    assert len(data["openweight"]["standalone"]) == 9
    for name, report in data["hosted"].items():
        values = [r["hosted_reports"][name]["auc"]["primary"]["overall"] for r in data["passes"]]
        actual = report["auc"]["primary"]["overall"]
        assert actual["accuracy"] == pytest.approx(mean(v["accuracy"] for v in values), abs=1e-12)
        assert actual["current_correct"] + actual["outdated_correct"] == pytest.approx(actual["accuracy"], abs=1e-12)
        assert len({r["provenance"][name]["run"] for r in data["passes"]}) == 3
    assert data["trajectory"]["example_pass"] == 1


def test_composition_pairs_both_components_by_pass_before_averaging():
    data = json.loads((ROOT / "docs/research/manuscript-three-pass/analysis.json").read_text())
    for name, rules in data["openweight"]["systems"].items():
        for rule, result in rules.items():
            values = [r["local_systems"][name][rule]["integrated"]["overall"]["accuracy"] for r in data["passes"]]
            assert result["integrated"]["overall"]["accuracy"] == pytest.approx(mean(values), abs=1e-12)
            assert result["auc_sample_sd"] == pytest.approx(stdev(values), abs=1e-12)
    # Averaging the repeated runs no longer supports the pass-1 reversal claim.
    t = data["trajectory"]
    jev = t["standalone"]["Jev"]["fixed"]["2"]["overall"]["accuracy"]
    assert t["systems"]["Terra"]["arrival"]["fixed"]["2"]["overall"]["accuracy"] > jev
