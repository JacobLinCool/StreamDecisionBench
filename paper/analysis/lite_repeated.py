"""Three-pass manuscript measurements; retain pass 1 only for concrete traces.

Run this module to regenerate manuscript evidence, numbers and figures without
model calls. Public leaderboard cohorts remain separate from the fixed paper cohort.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import hashlib
from itertools import permutations
import json
from pathlib import Path
from statistics import mean, stdev
import sys

import numpy as np

import lite_numbers as n
from leaderboard_models import HOSTED_PASSES
from lite_openweight import verified_run, verify_standalone, compare_published, mean_evaluations
from lite_trajectory_value import integrate, transition_errors, regression_example
from trajectory_replay import prepare, evaluate, aggregate, METRICS

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/research/manuscript-three-pass'
REPORT = 'docs/research/manuscript-three-pass/analysis.json'
DESIGN_COUNTS = frozenset({'RegimeSteps', 'RegimeDraws',
                           *(f'Regime{name}Changes' for name, _, _ in n.REGIMES)})
HEADLINE_SETTINGS = (('Jev', 'Jev'), ('TerraNone', 'Terra none'),
                     ('KevTwentySeven', 'Kev-27B'),
                     ('KevTwentySevenHybrid', 'Kev-27B + Terra none'))


def decision_diagnostics(run):
    """Count route, reference-consumed fields and composed decisions separately.

    Field accuracy pools the fields consumed by the reference branch, including
    the route. It is a diagnostic with its own denominator, not the benchmark
    score; placeholders in inactive branches are excluded.
    """
    rows = []
    for episode in run['episodes']:
        spec = episode['decision_spec']; route = spec['route_question']
        predictions = {r['t']: r['pred'] for r in run['responses'][episode['episode_id']]}
        row = dict(episode_id=episode['episode_id'], states=len(episode['steps']),
                   route_correct=0, field_correct=0, fields=0, composed_correct=0)
        for step in episode['steps']:
            gold, pred = step['gold'], predictions[step['t']]
            keys = [route, *spec['always'], *spec['branches'][gold[route]]]
            row['route_correct'] += pred[route] == gold[route]
            row['field_correct'] += sum(pred[key] == gold[key] for key in keys)
            row['fields'] += len(keys)
            row['composed_correct'] += n.compose(spec, pred) == n.compose(spec, gold)
        rows.append(row)
    return {'per_episode': rows, **{key: sum(row[key] for row in rows)
        for key in ('states', 'route_correct', 'fields', 'field_correct', 'composed_correct')}}


def pairing_sensitivity(runs_by_pass, records, auc_policy):
    """Evaluate every one-to-one pass matching for the headline comparisons."""
    matchings = list(permutations(range(3)))
    pairs = {}
    for fast, slow in (('KevTwentySeven', 'TerraNone'), ('Jev', 'TerraNone'), ('Jev', 'Terra')):
        matrix = []
        for i in range(3):
            values = []
            for j in range(3):
                if i == j:
                    branch, key = ('hosted_systems', slow) if fast == 'Jev' else ('local_systems', fast)
                    value = records[i][branch][key]['freshest']['integrated']['overall']['accuracy']
                else:
                    scenarios = prepare({fast: runs_by_pass[i][fast], slow: runs_by_pass[j][slow]})
                    value = integrate(scenarios, fast, slow, 'freshest', auc_policy)['overall']['accuracy']
                values.append(value)
            matrix.append(values)
        means = [mean(matrix[i][j] for i, j in enumerate(order)) for order in matchings]
        pairs[fast+'+'+slow] = {'fast': fast, 'slow': slow, 'auc_matrix': matrix,
                              'matching_means': means, 'min': min(means), 'max': max(means)}
    return {'arbitration': 'freshest', 'matchings': [[j+1 for j in order] for order in matchings],
            'provenance': 'matrix rows/columns index passes[*].provenance for fast/slow; components recorded separately',
            'pairs': pairs}


def compact_report(report):
    """Keep statistical evidence here; reference full trajectories by their digest."""
    keys = ('config', 'dataset_hash', 'run_sources', 'combined_from', 'started_at_utc',
            'events_sha256', 'latency_s')
    result = {key: report[key] for key in keys if key in report}
    result['raw_wallclock_scores'] = {'overall': report['raw_wallclock_scores']['overall']}
    result['scores'] = {scope: report['scores'][scope] for scope in ('overall', 'by_family')}
    result['scores']['per_episode'] = [{key: value for key, value in episode.items()
                                      if key not in ('intervals', 'normalization')}
                                     for episode in report['scores']['per_episode']]
    primary = report['auc']['primary']
    result['auc'] = {'primary': {key: primary[key] for key in
                    ('overall', 'by_family', 'per_episode', 'curve', 'quadrature')},
                    'sensitivity': {key: {field: value[field] for field in ('overall', 'quadrature')}
                                    for key, value in report['auc']['sensitivity'].items()}}
    network = report['network_adjustment']
    result['network_adjustment'] = {key: network[key] for key in
        ('network_s', 'prefill_s_per_1k_input_tokens', 'decode_s_per_output_token', 'latency_floor_s')}
    result['network_adjustment']['scores'] = {bound: {scope: network['scores'][bound][scope]
        for scope in ('overall', 'by_family')} for bound in ('estimate', 'low', 'high')}
    return result


def finalize_analysis(result):
    """Make every summary and provenance field describe the manuscript cohort."""
    records = result['passes']
    hosted_names = set(result['hosted'])
    for row in records:
        row['hosted_reports'] = {name: compact_report(report)
                                 for name, report in row['hosted_reports'].items()}
    result['trajectory']['verification']['max_nominal_recorded_gap_points'] = max(
        row['gaps'][name] for row in records for name in hosted_names)
    local = result['openweight']
    local['hosted'] = {name: {'accuracy': report['auc']['primary']['overall']['accuracy'],
                            'untimed': report['scores']['overall']['untimed_decision_accuracy'],
                            'median_s': report['latency_s']['p50']}
                       for name, report in result['hosted'].items()}
    local['provenance'] = [row['provenance'] for row in records]
    local['verification'] = {
        'original_clock_episode_checks': sum(len(row['provenance'])*8 for row in records),
        'nominal_recorded_gaps_points': {name: max(row['gaps'][name] for row in records)
                                       for name in records[0]['gaps']},
        'max_nominal_recorded_gap_points': max(gap for row in records for gap in row['gaps'].values())}
    local.pop('sources_sha256', None)
    for rules in local['systems'].values():
        for system in rules.values():
            system.pop('passes', None)  # Per-pass evidence already lives in result['passes'].
    paths = ['paper/analysis/lite_repeated.py', 'paper/analysis/lite_numbers.py',
             'paper/analysis/lite_auc.py', 'paper/analysis/lite_figures.py',
             'paper/analysis/lite_trajectory_value.py', 'paper/analysis/lite_openweight.py',
             'paper/analysis/trajectory_replay.py', 'paper/analysis/evaluation_policy.json',
             'paper/analysis/trajectory_policy.json', 'scripts/lite/network.py',
             'src/streamdecisionbench/lite/scoring.py',
             'src/streamdecisionbench/lite/retry_scoring.py',
             'src/streamdecisionbench/lite/interval_scoring.py']
    result['sources_sha256'] = {path: hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in paths}
    return result


def mean_tree(values):
    """Mean matching statistical fields; reject mismatched identities or grids."""
    first = values[0]
    if isinstance(first, (int, float)) and not isinstance(first, bool):
        return mean(values)
    if isinstance(first, dict):
        if any(v.keys() != first.keys() for v in values):
            raise ValueError('Different statistical fields across passes')
        return {k: mean_tree([v[k] for v in values]) for k in first}
    if isinstance(first, list):
        if any(len(v) != len(first) for v in values):
            raise ValueError('Different statistical grids across passes')
        return [mean_tree(list(v)) for v in zip(*values, strict=True)]
    if any(v != first for v in values):
        raise ValueError('Different statistical identities across passes')
    return first


def mean_report(reports):
    """Statistical view only; raw trajectories remain in the individual passes."""
    result = {k: reports[0][k] for k in ('config', 'dataset_hash', 'run_sources', 'combined_from')}
    result['raw_wallclock_scores'] = {'overall': mean_tree([r['raw_wallclock_scores']['overall'] for r in reports])}
    scores = {'overall': mean_tree([r['scores']['overall'] for r in reports]),
              'by_family': mean_tree([r['scores']['by_family'] for r in reports])}
    fields = [k for k, v in reports[0]['scores']['per_episode'][0].items()
              if isinstance(v, (int, float, str)) and k != 'events_sha256']
    scores['per_episode'] = mean_tree([[{k: e[k] for k in fields} for e in r['scores']['per_episode']]
                                     for r in reports])
    result['scores'] = scores
    result['latency_s'] = mean_tree([r['latency_s'] for r in reports])
    result['auc'] = {'primary': mean_tree([{k: r['auc']['primary'][k]
                     for k in ('overall', 'by_family', 'per_episode', 'curve')} for r in reports]),
                     'sensitivity': {key: {'overall': mean_tree([r['auc']['sensitivity'][key]['overall'] for r in reports])}
                                     for key in reports[0]['auc']['sensitivity']}}
    for key in ('primary', *reports[0]['auc']['sensitivity']):
        values = [r['auc']['primary']['quadrature'] if key == 'primary' else r['auc']['sensitivity'][key]['quadrature'] for r in reports]
        target = result['auc']['primary'] if key == 'primary' else result['auc']['sensitivity'][key]
        target['quadrature'] = {k: max(v[k] for v in values) for k in values[0]}
    net = {'network_s': mean_tree([r['network_adjustment']['network_s'] for r in reports]),
           'scores': {b: {scope: mean_tree([r['network_adjustment']['scores'][b][scope] for r in reports])
                         for scope in ('overall', 'by_family')} for b in ('estimate', 'low', 'high')}}
    for key in ('prefill_s_per_1k_input_tokens', 'decode_s_per_output_token', 'latency_floor_s'):
        net[key] = mean_tree([r['network_adjustment'][key] for r in reports])
    result['network_adjustment'] = net
    return result


def analyze():
    from lite_trajectory_value import POLICY_PATH
    policy = json.loads(POLICY_PATH.read_text())
    auc = json.loads((ROOT / 'paper/analysis/evaluation_policy.json').read_text())
    local = json.loads((ROOT / 'docs/research/openweight-hybrids/analysis.json').read_text())
    paper_names = local['policy']['manuscript_settings']
    specs = [s for s in local['policy']['settings'] if s['name'] in paper_names]
    records, runs_by_pass = [], []
    for index in range(3):
        runs, reports, provenance = {}, {}, {}
        for name, _, _ in n.MODELS:
            folder, run_folder = HOSTED_PASSES[name][index]
            path = ROOT / 'runs' / run_folder
            runs[name], hashes = verified_run(path)
            report = ROOT / 'docs/lite/results' / folder / 'analysis.json'
            reports[name] = json.loads(report.read_text())
            if reports[name]['events_sha256'] != hashes['events.jsonl']:
                raise ValueError(f'{name}: report differs from recording')
            provenance[name] = {'run': str(path.relative_to(ROOT)), 'sha256': hashes,
                                'published_report': {'path': str(report.relative_to(ROOT)),
                                                     'sha256': hashlib.sha256(report.read_bytes()).hexdigest()}}
        for spec in specs:
            name = spec['name']
            path = ROOT / 'runs' / [spec['run'], *spec['repeats']][index]
            runs[name], hashes = verified_run(path)
            expected = local['standalone'][name]['passes'][index]['provenance']
            if hashes != expected['sha256']:
                raise ValueError(f'{name}: local evidence differs from published provenance')
            report = ROOT / expected['published_report']['path']
            reports[name] = json.loads(report.read_text())
            provenance[name] = expected
            if regenerated_report(name, expected):  # scores are compared with the replay below
                provenance[name] = {**expected, 'published_report': {
                    'path': expected['published_report']['path'],
                    'sha256': hashlib.sha256(report.read_bytes()).hexdigest()}}
        scenarios = prepare(runs)
        row = {'pass': index + 1, 'provenance': provenance, 'hosted_reports': {},
               'standalone': {}, 'transition_errors': {}, 'hosted_systems': {}, 'local_systems': {}, 'gaps': {},
               'laya_diagnostics': {}, 'local_measurement_seconds': {}}
        for spec in specs:
            name = spec['name']; frozen = runs[name]['frozen']
            row['local_measurement_seconds'][name] = (
                datetime.fromisoformat(frozen['finished_at_utc']) -
                datetime.fromisoformat(frozen['started_at_utc'])).total_seconds()
            if name.startswith('Laya'):
                row['laya_diagnostics'][name] = decision_diagnostics(runs[name])
        for name, run in runs.items():
            own, row['gaps'][name] = verify_standalone(scenarios, name, run)
            independently_integrated = integrate(own, name, None, 'freshest', auc['primary'])
            compare_published(independently_integrated, reports[name], name, auc['integration']['tolerance'])
            if name in {x[0] for x in n.MODELS}:
                row['hosted_reports'][name] = reports[name]
                row['transition_errors'][name] = transition_errors(scenarios, name, 1)
                row['standalone'][name] = {'integrated': integrate(scenarios, name, None, 'freshest', auc['primary']),
                    'fixed': {str(d): aggregate([evaluate(sc, name, None, d) for sc in scenarios])
                              for d in policy['fixed_intervals_s']}}
        for slow in policy['slow_settings']:
            row['hosted_systems'][slow] = {}
            for rule in policy['policies']:
                row['hosted_systems'][slow][rule] = {'integrated': integrate(scenarios, 'Jev', slow, rule, auc['primary']),
                    'fixed': {str(d): aggregate([evaluate(sc, 'Jev', slow, d, rule) for sc in scenarios])
                              for d in policy['fixed_intervals_s']}}
        for spec in specs:
            name = spec['name']; row['local_systems'][name] = {}
            for rule in policy['policies']:
                row['local_systems'][name][rule] = {'integrated': integrate(scenarios, name, 'TerraNone', rule, auc['primary']),
                    'fixed_two': aggregate([evaluate(sc, name, 'TerraNone', 2, rule) for sc in scenarios])}
        if index == 0:
            traces = {rule: [evaluate(sc, 'Jev', 'Terra', 2, rule, trace=True) for sc in scenarios]
                      for rule in ('freshest', 'arrival')}
            row['regression_example'] = regression_example({'traces': traces}, scenarios)
        records.append(row)
        runs_by_pass.append(runs)
        print(f'Manuscript pass {index+1}: verified 15 recordings and all pair/rule replays', flush=True)
    trajectory = {'policy': policy, 'auc_policy': auc, 'standalone': {}, 'systems': {}, 'transition_errors': {},
                  'regression_example': records[0]['regression_example'], 'example_pass': 1,
                  'verification': {'max_nominal_recorded_gap_points': max(max(r['gaps'].values()) for r in records)}}
    for name, _, _ in n.MODELS:
        trajectory['standalone'][name] = {
            'integrated': mean_evaluations([r['standalone'][name]['integrated'] for r in records]),
            'fixed': {str(d): mean_evaluations([r['standalone'][name]['fixed'][str(d)] for r in records])
                      for d in policy['fixed_intervals_s']}}
        trajectory['transition_errors'][name] = {}
        for group in ('near', 'far'):
            values = [r['transition_errors'][name][group] for r in records]
            trajectory['transition_errors'][name][group] = {'states': sum(v['states'] for v in values),
                'errors': sum(v['errors'] for v in values), 'error_rate': mean(v['error_rate'] for v in values)}
    for slow in policy['slow_settings']:
        trajectory['systems'][slow] = {}
        for rule in policy['policies']:
            values = [r['hosted_systems'][slow][rule] for r in records]
            trajectory['systems'][slow][rule] = {
                'integrated': mean_evaluations([v['integrated'] for v in values]),
                'fixed': {str(d): mean_evaluations([v['fixed'][str(d)] for v in values]) for d in policy['fixed_intervals_s']},
                'auc_sample_sd': stdev(v['integrated']['overall']['accuracy'] for v in values)}
    local = {**local, 'policy': {**local['policy'], 'settings': specs},
             'standalone': {k: local['standalone'][k] for k in paper_names}, 'systems': {},
             'controls': {'TerraNone': trajectory['standalone']['TerraNone']['integrated'],
                          'JevTerraNone': trajectory['systems']['TerraNone']['freshest']['integrated']}}
    for name in paper_names:
        local['systems'][name] = {}
        for rule in policy['policies']:
            values = [r['local_systems'][name][rule] for r in records]
            areas = [v['integrated']['overall']['accuracy'] for v in values]
            local['systems'][name][rule] = {'integrated': mean_evaluations([v['integrated'] for v in values]),
                'fixed_two': mean_evaluations([v['fixed_two'] for v in values]), 'passes': values,
                'auc_range': max(areas)-min(areas), 'auc_sample_sd': stdev(areas)}
    local['verification']['nominal_recorded_gaps_points'] = {name: max(r['gaps'][name] for r in records) for name in records[0]['gaps']}
    local['verification']['max_nominal_recorded_gap_points'] = max(local['verification']['nominal_recorded_gaps_points'].values())
    local['aggregation'] = {'self_hosted_passes': 3, 'hosted_passes': 3,
                            'composition': 'same ordinal pass paired before equal averaging; separately recorded components'}
    result = {'aggregation': local['aggregation'], 'hosted': {name: mean_report([r['hosted_reports'][name] for r in records])
              for name, _, _ in n.MODELS}, 'passes': records, 'trajectory': trajectory, 'openweight': local}
    result['pairing_sensitivity'] = pairing_sensitivity(runs_by_pass, records, auc['primary'])
    result['measurement_budget'] = {
        'local_run_hours': sum(seconds for row in records for seconds in row['local_measurement_seconds'].values()) / 3600,
        'scope': 'sum of 27 measured local run durations; excludes downloads, initialization, audits, warmups and other experiments'}
    result['selection_annotation'] = (
        'The frozen evaluation policy describes the original AUC-selection stage. '
        'The current manuscript subsequently includes all three complete passes per setting; '
        'no valid response or complete pass from the fixed manuscript cohort is excluded.')
    finalize_analysis(result)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'analysis.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    return result


def regenerated_report(name, source, embedded=None):
    """Return a published report's path if only its non-statistical content changed.

    Report regeneration rewrites provenance and wording without changing scores, so a
    new digest is recorded rather than rejected. The report must still describe the
    recorded events and, for hosted settings, keep the statistics the manifest uses.
    """
    report = source['published_report']
    path = ROOT/report['path']
    if hashlib.sha256(path.read_bytes()).hexdigest() == report['sha256']:
        return None
    current = json.loads(path.read_text())
    if current['events_sha256'] != source['sha256']['events.jsonl']:
        raise ValueError(f'{name}: published report describes another recording')
    if embedded is not None and compact_report(current) != embedded:
        raise ValueError(f'{name}: published report statistics changed; run lite_repeated.py')
    return report['path']


def load_analysis():
    result = json.loads((OUT/'analysis.json').read_text())
    edited = []
    for path, checksum in result['sources_sha256'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest() != checksum:
            # Scorers and policies define the statistics; generator scripts only render them.
            if path.startswith('paper/analysis/') and path.endswith('.py') and path != 'paper/analysis/trajectory_replay.py':
                edited.append(path)
            else:
                raise ValueError(f'Stale manuscript analysis: {path}; run lite_repeated.py')
    if edited:
        print(f'Note: generator code changed after the manifest: {", ".join(edited)}', flush=True)
    regenerated = []
    for row in result['passes']:
        for name, source in row['provenance'].items():
            for filename, checksum in source['sha256'].items():
                if hashlib.sha256((ROOT/source['run']/filename).read_bytes()).hexdigest() != checksum:
                    raise ValueError(f'{name}: recording changed')
            path = regenerated_report(name, source, row['hosted_reports'].get(name))
            if path:
                regenerated.append(path)
    if regenerated:
        print(f'Note: {len(regenerated)} published reports were regenerated after the manifest; '
              'recordings and manuscript statistics are unchanged', flush=True)
    return result


def aggregate_macros(groups):
    """Aggregate exact numeric values retained by the rendering helpers."""
    result = n.Macros()
    common = set.intersection(*(set(g.items) for g in groups))
    for name in groups[0].items:
        if name.startswith('Cross'):
            continue  # A mean of per-pass crossing locations is not a crossing of the mean curves.
        if name not in common:
            if not name.startswith('Cross'):
                raise ValueError(f'{name}: missing macro in a pass')
            continue  # Crossing roots exist only for some individual passes; no aggregate root is asserted.
        values = [g.items[name].value for g in groups]
        first = values[0]
        source = '; '.join(g.items[name].source for g in groups)
        if isinstance(first, n.NumericText):
            if not all(isinstance(v, n.NumericText) for v in values):
                raise ValueError(f'{name}: inconsistent numeric formatting')
            raw = [v.number for v in values]
            if name in DESIGN_COUNTS:
                if any(value != raw[0] for value in raw[1:]):
                    raise ValueError(f'{name}: experimental design differs across passes')
                value, operation = raw[0], 'fixed experimental design, identical across passes'
            elif name.endswith(('TokMin', 'LatencyFloor')):
                value, operation = min(raw), 'minimum across passes'
            elif name.endswith(('TokMax', 'LatencyMax', 'MaxDispatchLagSec', 'MaxResidual', 'MaxDeviation')):
                value, operation = max(raw), 'maximum across passes'
            elif first.is_count or name.endswith(('CostUSD', 'CostInputUSD', 'CostOutputUSD')) or name == 'CostTotalUSD':
                value, operation = sum(raw), 'sum across passes'
            else:
                value, operation = sum(raw)/Decimal(3), 'equal mean across passes'
            rendered = n.count(int(value)) if first.is_count else n.fixed(value, first.places)
            result.add(name, rendered, f'{operation}: {source}')
        else:
            if any(v != first for v in values) and not name.endswith(('EventsHash', 'RecordedUTC')):
                raise ValueError(f'{name}: conflicting nonnumeric macro')
            result.add(name, first, 'pass 1: '+groups[0].items[name].source if name.endswith(('EventsHash','RecordedUTC')) else source)
    return result


def summary_macros(m, data):
    """Publish compact comparisons and diagnostics from the same verified passes."""
    m.add('ManuscriptPasses', n.count(len(data['passes'])), REPORT+':passes (count)')
    for name, _ in HEADLINE_SETTINGS:
        if name in ('Jev', 'TerraNone'):
            values = [row['hosted_reports'][name]['auc']['primary']['overall']['accuracy'] for row in data['passes']]
        elif name == 'KevTwentySeven':
            values = [row['integrated']['overall']['accuracy'] for row in data['openweight']['standalone'][name]['passes']]
        else:
            values = [row['local_systems']['KevTwentySeven']['freshest']['integrated']['overall']['accuracy'] for row in data['passes']]
        source = REPORT+':three independent pass scores for '+name
        m.add('Headline'+name+'Auc', n.fixed(100*mean(values), 2), source+' (equal mean, %)')
        m.add('Headline'+name+'SD', n.fixed(100*stdev(values), 2), source+' (sample SD, percentage points)')
    m.add('OwMeasuredHours', n.fixed(data['measurement_budget']['local_run_hours'], 2),
          REPORT+':measurement_budget.local_run_hours; measured runs only')
    for name in data['passes'][0]['laya_diagnostics']:
        values = [row['laya_diagnostics'][name] for row in data['passes']]
        totals = {key: sum(row[key] for row in values)
                  for key in ('states', 'route_correct', 'fields', 'field_correct', 'composed_correct')}
        source = REPORT+':passes[*].laya_diagnostics.'+name
        for suffix, numerator, denominator in [('Route', 'route_correct', 'states'),
                                               ('GoldFields', 'field_correct', 'fields'),
                                               ('Composed', 'composed_correct', 'states')]:
            m.add(name+suffix, n.fixed(100*totals[numerator]/totals[denominator], 2),
                  source+f': pooled {numerator}/{denominator}; gold-active fields include route')
        m.add(name+'States', n.count(totals['states']), source+':total state evaluations')
        m.add(name+'Fields', n.count(totals['fields']), source+':total gold-active fields, including route')
    sensitivity = data['pairing_sensitivity']
    m.add('PairingMatchings', n.count(len(sensitivity['matchings'])), REPORT+':pairing_sensitivity.matchings (count)')
    for key, prefix in [('KevTwentySeven+TerraNone', 'KevTwentySeven'),
                        ('Jev+TerraNone', 'JevTerraNone'), ('Jev+Terra', 'JevTerra')]:
        for label, bound in [('Min', 'min'), ('Max', 'max')]:
            m.add('Pairing'+prefix+label, n.fixed(100*sensitivity['pairs'][key][bound], 2),
                  REPORT+':pairing_sensitivity.pairs.'+key+'.'+bound+' (%, six one-to-one matchings)')


def write_summary_tables():
    rows = ['% Generated by paper/analysis/lite_repeated.py; do not edit by hand.',
            '% Source: '+REPORT, r'\newcommand{\TabHeadlineBody}{%']
    rows += [f'  {label} & \\Headline{name}Auc & \\Headline{name}SD \\\\'
             for name, label in HEADLINE_SETTINGS]
    rows += ['}', '']
    (ROOT/'paper/generated/summary_tables.tex').write_text('\n'.join(rows))


def generate_numbers(args):
    from lite_auc import auc_macros
    data = load_analysis()
    checks = n.Checks(); bench = n.load_benchmark(checks)
    groups, model_passes = [], []
    for index in range(3):
        models = {name: n.load_model(name, *HOSTED_PASSES[name][index], bench, checks) for name, _, _ in n.MODELS}
        m = n.Macros(); n.benchmark_macros(m, bench, checks)
        for model in models.values(): n.model_macros(m, model, bench, checks)
        n.counterfactual_macros(m, models, bench, checks)
        n.decomposition_macros(m, models, bench, checks, write_crossings=False)
        groups.append(m); model_passes.append(models)
    first = model_passes[0]
    m = aggregate_macros(groups)
    # Dataset constants describe unique states, not repeated evaluations.
    constants = n.Macros(); n.benchmark_macros(constants, bench, checks)
    m.items.update(constants.items)
    average_models = {}
    for name in first:
        src = n.Source.from_data(REPORT+':hosted.'+name, data['hosted'][name])
        average_models[name] = {**first[name], 'analysis': src,
                               'events': {**first[name]['events'], 'usage': [u for p in model_passes for u in p[name]['events']['usage']]}}
    auc_macros(m, average_models)
    # Ratios are computed from mean masses, not the mean of pass-level ratios.
    for name in first:
        records = [r['hosted_reports'][name]['scores']['per_episode'] for r in data['passes']]
        current = mean(mean(e['time_partition_seconds']['current_correct']/e['observed_duration_s'] for e in rows) for rows in records)
        oracle = mean(mean(e['current_source_share'] for e in rows) for rows in records)
        old = m.items[f'{name}UCurrent']; m.items[old.name] = n.Macro(old.name,n.pct(current/oracle),REPORT+':mean current-correct / mean current-source')
        m.add(name+'AucSD',n.fixed(100*stdev(r['hosted_reports'][name]['auc']['primary']['overall']['accuracy'] for r in data['passes']),2),REPORT+':passes.hosted_reports.'+name)
    auxiliary = n.Macros(); n.benchmark_macros(auxiliary, bench, checks); n.shared_macros(auxiliary, first, checks)
    n.comparison_macros(auxiliary, average_models, {eid:bench['episodes'][eid].get('task_family') for eid in bench['order']}, checks)
    n.pair_macros(auxiliary, average_models, checks)
    n.window_macros(auxiliary, first, bench, checks)
    facts,_ = n.parse_facts(); n.audit_macros(auxiliary,facts,bench,checks)
    n.setting_macros(auxiliary,first,checks)
    auxiliary.items['AstraUntimedStates'] = groups[0].items['AstraUntimedStates']
    n.astra_macros(auxiliary,first,bench,checks)
    m.items.update(auxiliary.items)
    dates = sorted({part['started_at_utc'][:10] for r in data['passes'] for a in r['hosted_reports'].values() for part in a.get('combined_from') or [a]})
    for key, value in [('AstraMinusJevUntimed', n.shown(data['hosted']['Astra']['scores']['overall']['untimed_decision_accuracy']) - n.shown(data['hosted']['Jev']['scores']['overall']['untimed_decision_accuracy']))]:
        m.items[key] = n.Macro(key, n.points(value), REPORT+':three-pass printed untimed difference')
    low_gains = [m.items[f'Regime{regime}{name}'].value.number - m.items[f'RegimeUniform{name}'].value.number
                 for regime in ('Bursty', 'LongTail') for name in ('Luna', 'Terra', 'Astra')]
    other_gains = [m.items[f'Regime{regime}{name}'].value.number - m.items[f'RegimeUniform{name}'].value.number
                   for regime in ('Bursty', 'LongTail') for name in ('LunaNone', 'TerraNone', 'Jev')]
    for key,value in [('RegimeStructureGainLowMin',min(low_gains)),('RegimeStructureGainLowMax',max(low_gains)),('RegimeStructureGainOtherMax',max(map(abs,other_gains)))]:
        m.items[key] = n.Macro(key,n.points(value),REPORT+':reference schedule projections, three-pass means')
    deviation = max(abs(m.items['RegimeLite'+name].value.number - Decimal(str(data['hosted'][name]['scores']['overall']['time_accuracy']))*100) for name in first)
    m.items['RegimeLiteMaxDiff'] = n.Macro('RegimeLiteMaxDiff',n.points(deviation),REPORT+':projection versus observed three-pass means')
    m.items['RecordingDatesUTC'] = n.Macro('RecordingDatesUTC',', '.join(dates[:-1])+' and '+dates[-1],REPORT+':passes.hosted_reports.started_at_utc')
    m.items['RecordingDaysWord'] = n.Macro('RecordingDaysWord',n.word(len(dates)),REPORT+':recording dates')
    # Agreement totals and first-pass case details have explicitly different scopes.
    correct = sum(round(r['hosted_reports']['Astra']['scores']['overall']['untimed_decision_accuracy']*480) for r in data['passes'])
    for key,value in [('AstraUntimedStates',n.count(correct)),('AstraStates',n.count(1440)),('AstraUntimedMissesWord',n.word(1440-correct))]:
        m.items[key] = n.Macro(key,value,REPORT+':Astra three-pass agreement')
    m.items['AstraReasoningResponses'] = n.Macro('AstraReasoningResponses', n.count(sum(bool(u.get('reasoning_tokens')) for p in model_passes for u in p['Astra']['events']['usage'])), REPORT+':Astra usage across passes')
    m.items['AstraFirstPassUntimedStates'] = n.Macro('AstraFirstPassUntimedStates',n.count(479),'pass 1 validity case, verified by astra_macros')
    misses = [[(s['episode_id'], s['t']) for s in r['transition_errors']['Astra']['states'] if s['wrong']] for r in data['passes']]
    checks.equal('Astra: one miss in pass 1, none in pass 2 and one in pass 3, in the same scenario',
                 ([len(x) for x in misses], misses[0][0][0] == misses[2][0][0]), ([1, 0, 1], True))
    m.items['AstraMissStepPassThree'] = n.Macro('AstraMissStepPassThree', str(misses[2][0][1]), REPORT+':passes[2].transition_errors.Astra')
    # Arbitration at 1 s: late overrides fall below Jev alone in every pass; freshest does not.
    one = [(r['hosted_systems']['Terra']['arrival']['fixed']['1']['overall']['accuracy'],
            r['hosted_systems']['Terra']['freshest']['fixed']['1']['overall']['accuracy'],
            r['standalone']['Jev']['fixed']['1']['overall']['accuracy']) for r in data['passes']]
    checks.equal('paper claim: at 1 s Jev plus Terra low with late overrides is below Jev alone in every pass',
                 all(arrival < alone for arrival, _, alone in one), True)
    checks.equal('paper claim: at 1 s the freshness rule stays at or above Jev alone in every pass',
                 all(freshest >= alone for _, freshest, alone in one), True)
    m.items['TrajJevOne'] = n.Macro('TrajJevOne', n.pct(data['trajectory']['standalone']['Jev']['fixed']['1']['overall']['accuracy']),
                                    REPORT+':trajectory.standalone.Jev.fixed.1')
    products, deviations, current_gaps = {}, [], []
    for name in first:
        rows = [row['hosted_reports'][name]['scores']['per_episode'] for row in data['passes']]
        per_scenario = [mean(e['untimed_decision_accuracy']*e['current_source_share'] for e in scenario)
                        for scenario in zip(*rows, strict=True)]
        observed = data['hosted'][name]['scores']
        products[name] = observed['overall']['time_accuracy'] - mean(per_scenario)
        deviations.extend(abs(e['time_accuracy']-product) for e,product in
                          zip(observed['per_episode'],per_scenario,strict=True))
        current_gaps.append(abs(m.items[name+'UCurrent'].value.number -
                                Decimal(str(observed['overall']['untimed_decision_accuracy']))*100))
    for key,value in [('ProductMaxDeviation',100*max(deviations)),
                      ('InForceMinusProductMin',100*min(products.values())),
                      ('InForceMinusProductMax',100*max(products.values())),
                      ('LuckyPctMax',max(m.items[name+'LuckyPct'].value.number for name in first)),
                      ('UCurrentMaxDiff',max(current_gaps)),
                      ('MaxReplayPhysicalDiff',max(abs(row['hosted_reports'][name]['scores']['overall']['time_accuracy'] -
                                                     row['hosted_reports'][name]['raw_wallclock_scores']['overall']['time_accuracy'])*100
                                                 for row in data['passes'] for name in first))]:
        places = m.items[key].value.places
        m.items[key] = n.Macro(key,n.fixed(value,places),REPORT+':three-pass statistics; extrema after aggregation, physical gaps across passes')
    # Paired counts use state and ordinal pass; do not multiply descriptive sample size claims.
    for candidate, baseline,_ in n.COMPARISONS:
        vals=[r['transition_errors'] for r in data['passes']]
        for label,family in [('',None),*n.FAMILIES]:
            counts=dict.fromkeys(('Both','CandidateOnly','BaselineOnly','Neither'),0)
            for v in vals:
                aa=v[candidate]['states'];bb=v[baseline]['states']
                for a,b in zip(aa,bb,strict=True):
                    if family is not None and a['family']!=family:continue
                    key='Neither' if a['wrong'] and b['wrong'] else 'BaselineOnly' if a['wrong'] else 'CandidateOnly' if b['wrong'] else 'Both'
                    counts[key]+=1
            for key,value in counts.items():
                macro=f'Pair{candidate}{baseline}{label}{baseline if key == 'BaselineOnly' else candidate if key == 'CandidateOnly' else ''}{'Only' if key.endswith('Only') else key}'
                if macro in m.items:m.items[macro]=n.Macro(macro,n.count(value),REPORT+':same state and ordinal pass counts')
    n.claim_checks(m, average_models, checks)
    summary_macros(m, data)
    if checks.failures:
        raise ValueError('\n'.join(checks.failures))
    inputs=[REPORT,*[p for p in data['sources_sha256']],f'{n.DATA}/manifest.json',n.AUDIT]
    n.write(m,inputs)
    n.write_facts(m,average_models,bench)
    write_summary_tables()
    print(f'Three-pass manuscript: {checks.passed} checks; {len(m.items)} macros',flush=True)
    if args.list:
        for item in m.items.values():print(f'\\{item.name}\t{item.value}\t{item.source}')
    return 0


def publish_compositions(data):
    from lite_trajectory_value import write_tex as trajectory_tex, plot as trajectory_plot
    from lite_openweight import write_tex as local_tex, plot as local_plot
    trajectory_tex(data['trajectory'],report_path=REPORT+':trajectory')
    trajectory_plot(data['trajectory'])
    local_tex(data['openweight'],report_path=REPORT+':openweight')
    local_plot(data['openweight'])


def main():
    import argparse
    data = analyze()
    generate_numbers(argparse.Namespace(list=False))
    publish_compositions(data)
    from lite_figures import main as figures
    figures()


if __name__ == '__main__':main()
