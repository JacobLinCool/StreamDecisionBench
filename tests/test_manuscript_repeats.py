"""Manuscript aggregation preserves precision, scope and timing identities."""
import json
from copy import deepcopy
from pathlib import Path
import sys
from statistics import mean, stdev

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "paper/analysis"))
from lite_numbers import Checks, Macros, count, network_measurements, pct
from lite_repeated import aggregate_macros, decision_diagnostics


def test_network_prose_corrections_do_not_relax_fit_verification():
    saved = {'assumption': 'Historical network attribution', 'interpretation': 'Historical bound',
             'method': 'quantile_fit', 'estimator': '0.10 quantile; 500 resamples',
             'prefill_s_per_1k_input_tokens': .03, 'network_s': {'estimate': .15},
             'scores': {'estimate': {'overall': {'time_accuracy': .7}}}}
    corrected = {**saved, 'assumption': 'Token-independent fitted remainder',
                 'interpretation': 'No identified network delay or guaranteed upper bound'}
    checks = Checks()
    checks.same('unchanged fit', network_measurements(corrected), network_measurements(saved))
    assert not checks.failures
    for key, value in [('prefill_s_per_1k_input_tokens', .04),
                       ('estimator', '0.05 quantile; 500 resamples'),
                       ('network_s', {'estimate': .16}),
                       ('scores', {'estimate': {'overall': {'time_accuracy': .8}}})]:
        changed = deepcopy(corrected)
        changed[key] = value
        checks = Checks()
        checks.same('changed fit', network_measurements(changed), network_measurements(saved))
        assert checks.failures, key
    changed = {**corrected, 'unverified_coefficient': .2}
    checks = Checks()
    checks.same('added field', network_measurements(changed), network_measurements(saved))
    assert checks.failures
    for key in ('assumption', 'interpretation'):
        changed = {**corrected, key: None}
        with pytest.raises(ValueError, match=f'documentary field {key}'):
            network_measurements(changed)


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


def test_repeated_measurements_do_not_triple_the_experimental_design():
    groups = []
    for _ in range(3):
        group = Macros()
        for name, value in [('RegimeSteps', 60), ('RegimeDraws', 300),
                            ('RegimeBurstyChanges', 22), ('ValidResponses', 480)]:
            group.add(name, count(value), 'recorded design or observed count')
        groups.append(group)
    result = aggregate_macros(groups)
    assert {name: value.value for name, value in result.items.items()} == {
        'RegimeSteps': '60', 'RegimeDraws': '300',
        'RegimeBurstyChanges': '22', 'ValidResponses': '1440'}
    groups[2] = Macros()
    for name, value in [('RegimeSteps', 61), ('RegimeDraws', 300),
                        ('RegimeBurstyChanges', 22), ('ValidResponses', 480)]:
        groups[2].add(name, count(value), 'inconsistent experimental design')
    with pytest.raises(ValueError, match='RegimeSteps: experimental design differs'):
        aggregate_macros(groups)


def test_field_diagnostic_uses_gold_active_fields_and_keeps_route_errors():
    episode = {'episode_id': 'example',
               'decision_spec': {'route_question': 'route', 'always': ['global'],
                                 'branches': {'a': ['a'], 'b': ['b']}},
               'steps': [{'t': 0, 'gold': {'route': 'a', 'global': 'yes', 'a': 'ok', 'b': 'inactive'}},
                         {'t': 1, 'gold': {'route': 'b', 'global': 'yes', 'a': 'inactive', 'b': 'ok'}}]}
    run = {'episodes': [episode], 'responses': {'example': [
        {'t': 0, 'pred': {'route': 'b', 'global': 'yes', 'a': 'ok', 'b': 'wrong'}},
        {'t': 1, 'pred': {'route': 'b', 'global': 'yes', 'a': 'wrong', 'b': 'ok'}}]}}
    result = decision_diagnostics(run)
    assert result['states'] == 2
    assert result['route_correct'] == result['composed_correct'] == 1
    assert result['field_correct'] == 5
    assert result['fields'] == 6


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


def test_pairing_sensitivity_preserves_recordings_and_enumerates_every_matching():
    from itertools import permutations
    data = json.loads((ROOT / "docs/research/manuscript-three-pass/analysis.json").read_text())
    sensitivity = data['pairing_sensitivity']
    assert sensitivity['matchings'] == [list(p) for p in permutations((1, 2, 3))]
    for pair in sensitivity['pairs'].values():
        matrix = pair['auc_matrix']
        means = [mean(matrix[i][j-1] for i, j in enumerate(order))
                 for order in sensitivity['matchings']]
        assert pair['matching_means'] == pytest.approx(means, abs=1e-12)
        assert (pair['min'], pair['max']) == pytest.approx((min(means), max(means)), abs=1e-12)
        for index, row in enumerate(data['passes']):
            branch, key = ('hosted_systems', pair['slow']) if pair['fast'] == 'Jev' else ('local_systems', pair['fast'])
            assert matrix[index][index] == row[branch][key]['freshest']['integrated']['overall']['accuracy']
