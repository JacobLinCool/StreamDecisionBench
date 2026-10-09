"""Verify an extracted anonymous manuscript artifact, with networking disabled.

The verifier checks hashes before importing the packaged benchmark, then rescores
all recordings and verifies their frozen requests, answers and native evidence.
--reproduce additionally runs the unchanged manuscript regeneration entry point.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
MANUSCRIPT = 'docs/research/manuscript-three-pass/analysis.json'
LATER = 'docs/research/later-hosted/analysis.json'


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(path: str):
    return json.loads((ROOT/path).read_text())


def block_network(event, args):
    if event in {'socket.connect', 'socket.connect_ex', 'socket.getaddrinfo', 'socket.gethostbyname'}:
        raise RuntimeError(f'Artifact verification cannot use network access: {event}')


def verify_inventory():
    manifest = load('ARTIFACT_MANIFEST.json')
    for path, receipt in manifest['files'].items():
        if Path(path).is_absolute() or '..' in Path(path).parts:
            raise ValueError('Artifact receipt escapes extraction boundary')
        full = ROOT/path
        if not full.is_file() or full.is_symlink() or full.stat().st_size != receipt['bytes'] or sha(full) != receipt['sha256']:
            raise ValueError(f'Packaged file changed or missing: {path}')
    expected = set(manifest['files']) | {'ARTIFACT_MANIFEST.json'}
    actual = set()
    for directory, dirs, files in os.walk(ROOT, followlinks=False):
        if Path(directory) == ROOT:
            # This is the documented installation location. It is not submitted
            # research evidence; imported benchmark code is checked separately.
            dirs[:] = [name for name in dirs if name != '.venv']
        for name in files:
            actual.add(str((Path(directory)/name).relative_to(ROOT)))
        if any((Path(directory)/name).is_symlink() for name in dirs):
            raise ValueError('Symbolic-link directory found in artifact evidence')
    if actual != expected:
        raise ValueError(f'Unexpected files in fresh extraction: {sorted(actual-expected)[:10]}')
    print(f'Verified {len(manifest["files"])} packaged SHA-256 receipts', flush=True)
    return manifest


def compare(got, expected, where, tolerance=1e-12):
    if isinstance(expected, dict):
        if not isinstance(got, dict) or any(k not in got for k in expected):
            raise ValueError(f'{where}: missing result fields')
        for key, value in expected.items():
            compare(got[key], value, f'{where}.{key}', tolerance)
    elif isinstance(expected, list):
        if not isinstance(got, list) or len(got) != len(expected):
            raise ValueError(f'{where}: list size differs')
        for i, (left, right) in enumerate(zip(got, expected, strict=True)):
            compare(left, right, f'{where}[{i}]', tolerance)
    elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if (isinstance(got, bool) or not isinstance(got, (int, float))
                or not math.isfinite(got) or not math.isfinite(expected)
                or abs(got-expected) > tolerance):
            raise ValueError(f'{where}: numeric result differs ({got!r} != {expected!r})')
    elif got != expected:
        raise ValueError(f'{where}: result differs')


def verify_recordings():
    # Force imports to resolve inside this extracted artifact, regardless of any
    # editable installation in the interpreter used to inspect it.
    sys.path[:0] = [str(ROOT/'src'), str(ROOT/'paper/analysis'), str(ROOT/'scripts/lite'), str(ROOT/'scripts/runpod')]
    from streamdecisionbench.lite.core import compose, decode, digest, request_for
    from lite_openweight import verified_run, verify_audit
    from lite_repeated import load_analysis
    package = importlib.import_module('streamdecisionbench')
    if not Path(package.__file__).resolve().is_relative_to(ROOT):
        raise ValueError('Benchmark import resolved outside the extracted artifact')
    data = load_analysis()  # Includes all current producer/report/run digest checks.
    policy = data['openweight']['policy']
    specs = {row['name']: row for row in policy['settings']}
    records, requests, questions, native_checks = 0, 0, 0, 0

    def verify_recording(name, source, label):
        nonlocal requests, questions
        run, evidence = verified_run(ROOT/source['run'])
        if evidence != source['sha256']:
            raise ValueError(f'{name}: recording receipts disagree')
        report = load(source['published_report']['path'])
        if report['config'] != run['frozen']['config']:
            raise ValueError(f'{name}: redacted configuration differs between report and recording')
        compare(run['scores'], report['scores'], f'{name}/{label}/scores')
        compare(run['raw_wallclock_scores'], report['raw_wallclock_scores'], f'{name}/{label}/wallclock')
        seen = set()
        for episode in run['episodes']:
            eid = episode['episode_id']
            for response in run['responses'][eid]:
                key = eid, response['t']
                if key in seen:
                    raise ValueError(f'{name}: duplicate response')
                seen.add(key)
                step = episode['steps'][response['t']]
                if response['request_hash'] != digest(request_for(episode, step)):
                    raise ValueError(f'{name}: changed public model input')
                decoded = decode(episode, response['wire_answers'])
                if decoded != response['pred'] or compose(episode['decision_spec'], decoded) != response['decision']:
                    raise ValueError(f'{name}: changed committed answer')
                requests += 1
                questions += len(episode['questions'])
        if len(seen) != 480:
            raise ValueError(f'{name}: incomplete 480-state recording')
        return run

    for row in data['passes']:
        for name, source in row['provenance'].items():
            run = verify_recording(name, source, f'pass{row["pass"]}')
            if name in specs:
                spec = deepcopy(specs[name])
                spec['run'] = str(Path(source['run']).relative_to('runs'))
                if 'input_audit' in source:
                    spec['audit'] = str(Path(source['input_audit']['path']).relative_to('runs'))
                    audit = verify_audit(spec, run)
                    if audit['sha256'] != source['input_audit']['sha256']:
                        raise ValueError(f'{name}: native audit receipt differs')
                    native_checks += 1
                native = source['native_sources']
                if sha(ROOT/native['path']) != native['sha256'] or load(native['path']) != native['revisions']:
                    raise ValueError(f'{name}: native-source receipt differs')
                if 'weights' in source:
                    weight = source['weights']
                    if sha(ROOT/weight['path']) != weight['sha256']:
                        raise ValueError(f'{name}: weight-manifest receipt differs')
                    if load(weight['path']) != run['frozen']['config']['prepared_checkpoint']:
                        raise ValueError(f'{name}: checkpoint metadata differs')
            records += 1
        print(f'Pass {row["pass"]}: all 15 recordings, requests, scores and native metadata verified', flush=True)
    later = load(LATER)
    for name, row in later['standalone'].items():
        for record in row['passes']:
            verify_recording(name, record['provenance'], f'pass{record["pass"]}')
            records += 1
    print(f'Later hosted settings: all {sum(len(r["passes"]) for r in later["standalone"].values())} recordings verified', flush=True)
    if (records, requests, questions) != (66, 31680, 205920):
        raise ValueError('Unexpected manuscript cohort or evaluation counts')
    return {'recordings': records, 'state_evaluations': requests, 'question_evaluations': questions,
            'native_input_audits': native_checks}


def visible_tex(path: Path):
    """Ignore generated provenance comments; retain every rendered value/token."""
    return '\n'.join(re.sub(r'(?<!\\)%.*$', '', line).rstrip() for line in path.read_text().splitlines()).strip()


def regenerate():
    before = {str(p.relative_to(ROOT)): visible_tex(p) for p in (ROOT/'paper/generated').glob('*.tex')}
    figure_data = {str(p.relative_to(ROOT)): json.loads(p.read_text())
                   for p in (ROOT/'paper/figures').glob('*.json')}
    from lite_repeated import main
    main()
    from lite_later import main as later
    later()
    after = {str(p.relative_to(ROOT)): visible_tex(p) for p in (ROOT/'paper/generated').glob('*.tex')}
    if before != after:
        changed = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
        raise ValueError(f'Regenerated manuscript content changed: {changed}')
    regenerated_figures = {str(p.relative_to(ROOT)): json.loads(p.read_text())
                           for p in (ROOT/'paper/figures').glob('*.json')}
    if figure_data.keys() != regenerated_figures.keys():
        raise ValueError('Regenerated figure-data inventory changed')
    compare(regenerated_figures, figure_data, 'figure data')
    print(f'Regenerated all manuscript evidence, figures and {len(before)} TeX artifacts with matching values', flush=True)
    return {'regenerated_tex_files': len(before), 'generated_manuscript_values_match': True,
            'regenerated_figure_data_files': len(figure_data), 'generated_figure_values_match': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reproduce', action='store_true')
    args = parser.parse_args()
    start = time.monotonic()
    sys.dont_write_bytecode = True
    sys.addaudithook(block_network)
    package = verify_inventory()
    result = {'inventory_files': len(package['files']), 'network_access': 'blocked by audit hook',
              **verify_recordings()}
    if args.reproduce:
        result.update(regenerate())
    result['elapsed_seconds'] = time.monotonic()-start
    (ROOT/'validation-result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
