"""Public exports keep completed recordings and the manuscript cohort consistent."""
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "paper/analysis"))
from leaderboard_models import HOSTED_MODELS
from lite_numbers import MODELS
from lite_openweight import write_tex


def load_script(name, path):
    spec = spec_from_file_location(name, ROOT / path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


figure_data = load_script("sdb_figure_data", "docs/figures/prepare.py")
site_build = load_script("sdb_site_build", "site/build.py")


@pytest.mark.parametrize("missing", ["Clef", "ClefFlash"])
def test_omitting_completed_cloudflare_recording_cannot_publish(missing, tmp_path, monkeypatch):
    summary = json.loads(figure_data.SUMMARY.read_text())
    del summary["hosted"][missing]
    path = tmp_path / "analysis.json"
    path.write_text(json.dumps(summary))
    monkeypatch.setattr(figure_data, "SUMMARY", path)
    with pytest.raises(ValueError, match="every registered"):
        figure_data.build()


def test_site_preserves_every_setting_and_exact_cloudflare_measurements(tmp_path):
    data = site_build.build(tmp_path)
    rows = {row["id"]: row for row in data["settings"]}
    policy = json.loads((ROOT / "paper/analysis/openweight_policy.json").read_text())
    hosted = {name for name, _, _ in HOSTED_MODELS}
    local = {spec["name"] for spec in policy["settings"]}
    assert len(rows) == len(data["settings"])
    assert {row["id"] for row in rows.values() if row["deployment"] == "hosted"} == hosted
    assert {row["id"] for row in rows.values() if row["deployment"] == "self-hosted"} == local
    for name, folder, _ in HOSTED_MODELS:
        if name not in {"Clef", "ClefFlash"}:
            continue
        report = json.loads((ROOT / "docs/lite/results" / folder / "analysis.json").read_text())
        row = rows[name]
        assert row["log_auc_pct"] == 100 * report["auc"]["primary"]["overall"]["accuracy"]
        assert row["untimed_pct"] == 100 * report["scores"]["overall"]["untimed_decision_accuracy"]
        assert row["p50_s"] == report["latency_s"]["p50"]
        assert row["p95_s"] == report["latency_s"]["p95"]
        assert len(row["curve_pct"]) == len(data["intervals_s"])
    assert json.loads((tmp_path / "data.json").read_text()) == data


def test_public_extension_keeps_manuscript_setting_count(tmp_path, monkeypatch):
    summary = json.loads(figure_data.SUMMARY.read_text())
    paper_names = {name for name, _, _ in MODELS}
    assert {"Clef", "ClefFlash"} <= summary["hosted"].keys() - paper_names
    output = tmp_path / "paper/generated"
    output.mkdir(parents=True)
    monkeypatch.setattr(sys.modules[write_tex.__module__], "ROOT", tmp_path)
    write_tex(summary)
    numbers = (output / "openweight_numbers.tex").read_text()
    assert r"\newcommand{\OwTotalSettingsWord}{fifteen}" in numbers


def test_self_hosted_exports_use_all_three_passes(tmp_path):
    summary = json.loads(figure_data.SUMMARY.read_text())
    site = site_build.build(tmp_path)
    exported = {row["id"]: row for row in site["settings"]}
    for name, result in summary["standalone"].items():
        passes = result["passes"]
        assert len(passes) == exported[name]["passes"] == 3
        assert len({p["provenance"]["run"] for p in passes}) == 3
        assert exported[name]["log_auc_pct"] == pytest.approx(
            100 * sum(p["integrated"]["overall"]["accuracy"] for p in passes) / 3)
        assert exported[name]["untimed_pct"] == pytest.approx(100 * sum(p["untimed"] for p in passes) / 3)
        for q in ("p50", "p95"):
            assert exported[name][q + "_s"] == pytest.approx(sum(p["latency_s"][q] for p in passes) / 3)
        for system in summary["systems"][name].values():
            areas = [p["integrated"]["overall"]["accuracy"] for p in system["passes"]]
            assert system["integrated"]["overall"]["accuracy"] == pytest.approx(sum(areas) / 3)
            assert system["auc_range"] == pytest.approx(max(areas) - min(areas))
            curves = [p["integrated"]["curve"]["accuracy"] for p in system["passes"]]
            assert system["integrated"]["curve"]["accuracy"] == pytest.approx(
                [sum(values) / 3 for values in zip(*curves, strict=True)])


def test_generated_markdown_tables_have_consistent_columns():
    from lite_openweight import render_report, render_results
    summary = json.loads(figure_data.SUMMARY.read_text())
    for text in (render_results(summary), render_report(summary)):
        columns = None
        for line in text.splitlines():
            if not line.startswith("|"):
                columns = None
                continue
            count = len(line.split("|"))
            if columns is None:
                columns = count
            assert count == columns
