"""Public exports keep completed recordings and the manuscript cohort consistent."""
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "paper/analysis"))
from leaderboard_models import HOSTED_MODELS, HOSTED_PASSES
from lite_hosted import load_summary as load_hosted_summary
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
    hosted = set(HOSTED_PASSES)
    local = {spec["name"] for spec in policy["settings"]}
    assert len(rows) == len(data["settings"])
    assert {row["id"] for row in rows.values() if row["deployment"] == "hosted"} == hosted
    assert {row["id"] for row in rows.values() if row["deployment"] == "self-hosted"} == local
    for name, report in load_hosted_summary()["hosted"].items():
        row = rows[name]
        assert row["passes"] == len(report["passes"]) == len(HOSTED_PASSES[name])
        assert row["log_auc_pct"] == 100 * report["accuracy"]
        assert row["untimed_pct"] == 100 * report["untimed"]
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


@pytest.mark.parametrize("name", ["Winnow12B", "WinnowE4B"])
def test_winnow_exports_match_independently_verified_three_pass_report(name, tmp_path):
    data = site_build.build(tmp_path)
    row = next(row for row in data["settings"] if row["id"] == name)
    report = json.loads((ROOT / "docs/lite/results/winnow-pro6000-20261003/results.json").read_text())
    expected = next(value for value in report["aggregate"] if value["model"] == "EldanRing/" + row["label"])
    assert row["passes"] == expected["passes"] == 3
    # The leaderboard uses analytic integration; run reports use converged
    # trapezoidal quadrature. Apply the benchmark's existing integration tolerance.
    policy = json.loads((ROOT / "paper/analysis/evaluation_policy.json").read_text())
    assert row["log_auc_pct"] == pytest.approx(
        expected["log_auc_pct_mean"], abs=100 * policy["integration"]["tolerance"], rel=0)
    assert row["untimed_pct"] == pytest.approx(expected["untimed_accuracy_pct_mean"], abs=1e-9)
    source = json.loads(figure_data.OUT.read_text())
    assert len(source["provenance"][name]) == 3


@pytest.mark.parametrize("missing", ["Winnow12B", "WinnowE4B"])
def test_omitting_completed_winnow_recording_cannot_publish(missing, tmp_path, monkeypatch):
    summary = json.loads(figure_data.SUMMARY.read_text())
    del summary["standalone"][missing]
    path = tmp_path / "analysis.json"
    path.write_text(json.dumps(summary))
    monkeypatch.setattr(figure_data, "SUMMARY", path)
    with pytest.raises(ValueError, match="every registered"):
        figure_data.build()


def test_generated_markdown_tables_have_consistent_columns():
    from lite_openweight import render_report, render_results
    summary = json.loads(figure_data.SUMMARY.read_text())
    for text in (render_results(summary, hosted=load_hosted_summary()["hosted"]), render_report(summary)):
        columns = None
        for line in text.splitlines():
            if not line.startswith("|"):
                columns = None
                continue
            count = len(line.split("|"))
            if columns is None:
                columns = count
            assert count == columns


def test_hosted_exports_average_independent_pass_scores_and_latencies(tmp_path):
    summary = load_hosted_summary()
    site = site_build.build(tmp_path)
    rows = {r["id"]: r for r in site["settings"]}
    for name, result in summary["hosted"].items():
        records = result["passes"]
        count = len(HOSTED_PASSES[name])
        assert rows[name]["passes"] == len(records) == count
        assert len({r["provenance"]["run"] for r in records}) == count
        assert rows[name]["log_auc_pct"] == pytest.approx(
            100 * sum(r["primary"]["overall"]["accuracy"] for r in records) / count)
        if result["auc_sample_sd"] is None:
            assert rows[name]["log_auc_sd_pct"] is None and count == 1
        else:
            assert rows[name]["log_auc_sd_pct"] == pytest.approx(100 * result["auc_sample_sd"])
        for q in ("p50", "p95"):
            assert rows[name][q + "_s"] == pytest.approx(sum(r["latency_s"][q] for r in records) / count)
        assert site["passes_per_setting"][name] == count


def test_hosted_summary_rejects_a_missing_repeat(tmp_path, monkeypatch):
    import lite_hosted
    data = json.loads((lite_hosted.OUT / "analysis.json").read_text())
    data["hosted"]["Astra"]["passes"].pop()
    (tmp_path / "analysis.json").write_text(json.dumps(data))
    monkeypatch.setattr(lite_hosted, "OUT", tmp_path)
    with pytest.raises(ValueError, match="incorrect repeat count"):
        lite_hosted.load_summary()


@pytest.mark.parametrize("metric", ["accuracy", "latency_s"])
def test_hosted_summary_rejects_an_aggregate_that_disagrees_with_passes(metric, tmp_path, monkeypatch):
    import lite_hosted
    data = json.loads((lite_hosted.OUT / "analysis.json").read_text())
    if metric == "accuracy":
        data["hosted"]["Astra"][metric] += .01
    else:
        data["hosted"]["Astra"][metric]["p50"] += .1
    (tmp_path / "analysis.json").write_text(json.dumps(data))
    monkeypatch.setattr(lite_hosted, "OUT", tmp_path)
    with pytest.raises(ValueError, match="aggregate differs"):
        lite_hosted.load_summary()


@pytest.mark.parametrize('name,mode', [('WityAuto', 'auto'), ('WityOff', 'off')])
def test_wity_single_pass_exports_preserve_configuration_and_no_invented_sd(name, mode, tmp_path):
    row = load_hosted_summary()['hosted'][name]
    assert len(row['passes']) == 1 and row['auc_sample_sd'] is None
    record = row['passes'][0]
    run = json.loads((ROOT / record['provenance']['run'] / 'run.json').read_text())
    assert run['status'] == 'complete'
    assert run['config']['reasoning'] == mode and run['config']['workers'] == 16
    assert run['config']['rate_limit_policy'] == 'http429_retry_after_shared_cooldown_v1'
    exported = next(r for r in site_build.build(tmp_path)['settings'] if r['id'] == name)
    assert exported['label'] == f'Wity-1 ({mode})'
    assert exported['passes'] == 1 and exported['workers'] == 16
    assert exported['log_auc_sd_pct'] is None
    assert exported['log_auc_pct'] == pytest.approx(100 * record['primary']['overall']['accuracy'])
    assert record['retry_reliability']['successful_logical_requests'] == 480
