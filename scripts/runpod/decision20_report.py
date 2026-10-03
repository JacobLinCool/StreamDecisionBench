"""Validate complete Decision 2.0 recordings and publish three-pass means."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'paper/analysis')]
from streamdecisionbench.lite.core import compose, decode, digest, request_for
from streamdecisionbench.jev import committed_answer, validate_response
from streamdecisionbench.lite.__main__ import rescore_run
from lite_reports import evaluate_one


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_native_archive(raw, setting, manifest):
    archives = json.loads((raw / 'archives.json').read_text())
    path = raw / 'upstream-sources.tar.gz'
    if sha(path) != archives['upstream-sources.tar.gz']:
        raise ValueError('Preserved native source archive changed')
    prefix = setting['model'].split('/')[-1] + '/'
    with tarfile.open(path) as archive:
        for name, receipt in manifest['runtime_files'].items():
            source = archive.extractfile(prefix + name)
            if source is None or hashlib.file_digest(source, 'sha256').hexdigest() != receipt['sha256']:
                raise ValueError('Preserved native runtime differs from release')


def validate(run, raw, plan, setting):
    frozen = json.loads((run / 'run.json').read_text())
    if frozen['status'] != 'complete' or sha(run / 'events.jsonl') != frozen['events_sha256']:
        raise ValueError('Incomplete or changed recording')
    config = frozen['config']
    if config['pass_number'] != int(run.parent.name.removeprefix('pass')):
        raise ValueError('Pass identity differs from recording directory')
    if (config['model'], config['model_revision']) != (setting['model'], setting['revision']):
        raise ValueError('Model identity differs from frozen plan')
    prepared = json.loads((raw / (setting['id'] + '.prepared.json')).read_text())
    if config['prepared_checkpoint'] != prepared or prepared['manifest_sha256'] != setting['manifest_sha256']:
        raise ValueError('Prepared checkpoint provenance differs from plan')
    manifest_path = raw / (setting['id'] + '.MODEL_MANIFEST.json')
    if sha(manifest_path) != setting['manifest_sha256'] or json.loads(manifest_path.read_text()) != prepared['manifest']:
        raise ValueError('Native manifest differs from frozen release')
    verify_native_archive(raw, setting, prepared['manifest'])
    if config['inference']['parameter_count'] != setting['parameters']:
        raise ValueError('Loaded parameter count differs from frozen plan')
    expected_archive = json.loads((raw / 'archives.json').read_text())['deployment.tar.gz']
    if sha(raw / 'deployment.tar.gz') != expected_archive:
        raise ValueError('Deployment archive changed')
    with tarfile.open(raw / 'deployment.tar.gz') as archive:
        source = archive.extractfile('scripts/runpod/decision20_record.py').read()
        if hashlib.sha256(source).hexdigest() != config['adapter_sha256']:
            raise ValueError('Recorder differs from frozen deployment')
        if json.load(archive.extractfile('data/lite/v1/manifest.json')) != frozen['dataset_manifest']:
            raise ValueError('Dataset differs from frozen deployment')
        for name, checksum in frozen['run_sources'].items():
            if hashlib.sha256(archive.extractfile('src/streamdecisionbench/' + name).read()).hexdigest() != checksum:
                raise ValueError('Runtime source differs from frozen deployment')
    audit_path = run.parent / (setting['id'] + '.input-audit.json')
    audit = json.loads(audit_path.read_text())
    if (sha(audit_path) != config['input_audit_sha256'] or audit['requests'] != 480
            or audit['question_rows'] != 3120 or audit['issues']):
        raise ValueError('Incomplete or changed input audit')
    if audit['dataset_hash'] != plan['dataset_sha256'] or frozen['dataset_manifest']['dataset_hash'] != plan['dataset_sha256']:
        raise ValueError('Dataset identity differs from frozen plan')
    verified = rescore_run(run)
    audited = {(r['episode_id'], r['t']): r['request_sha256'] for r in audit['rows']}
    seen = set()
    for episode in verified['episodes']:
        if digest(episode) != frozen['dataset_manifest']['hashes'][episode['episode_id']]:
            raise ValueError('Frozen episode changed')
        steps = {s['t']: s for s in episode['steps']}
        for response in verified['responses'][episode['episode_id']]:
            key = episode['episode_id'], response['t']
            expected = digest(request_for(episode, steps[response['t']]))
            if key in seen or not response['ok'] or response['request_hash'] != expected or audited.get(key) != expected:
                raise ValueError('Missing, duplicate or changed request')
            pred = decode(episode, response['wire_answers'])
            if pred != response['pred'] or compose(episode['decision_spec'], pred) != response['decision']:
                raise ValueError('Committed answer changed')
            native = response['usage']['native_answers']
            validate_response({'answers': native}, episode['questions'])
            if {qid: committed_answer(question, native[qid]) for qid, question in episode['questions'].items()} != response['wire_answers']:
                raise ValueError('Committed answer differs from native response')
            seen.add(key)
    if len(seen) != 480 or len(verified['episodes']) != 8 or len(audited) != 480:
        raise ValueError('Incomplete dataset coverage')
    return frozen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, default=ROOT / 'runs/decision20-pro6000-20261003')
    parser.add_argument('--reports', type=Path, default=ROOT / 'docs/lite/results/decision20-pro6000-20261003')
    args = parser.parse_args()
    plan = json.loads((args.raw / 'source/decision20-plan.json').read_text())
    args.reports.mkdir(parents=True, exist_ok=True)
    rows = []
    for number in range(1, plan['passes'] + 1):
        for setting in plan['settings']:
            run = args.raw / f'pass{number}' / setting['id']
            if not (run / 'run.json').exists() or json.loads((run / 'run.json').read_text())['status'] != 'complete':
                continue
            validate(run, args.raw, plan, setting)
            name = f"{setting['id']}-pass{number}"
            report_path = args.reports / name / 'analysis.json'
            if not report_path.exists():
                evaluate_one(run, args.reports / name, setting['label'] + f' — pass {number}')
            report = json.loads(report_path.read_text())
            if report['events_sha256'] != sha(run / 'events.jsonl') or report['config'] != json.loads((run / 'run.json').read_text())['config']:
                raise ValueError('Published analysis uses different recording')
            rows.append({'model': setting['model'], 'setting': setting['id'], 'pass': number,
                'log_auc_pct': 100 * report['auc']['primary']['overall']['accuracy'],
                'untimed_pct': 100 * report['scores']['overall']['untimed_decision_accuracy'],
                'p50_s': report['latency_s']['p50'], 'p95_s': report['latency_s']['p95'],
                'failed_attempts': report['retry_reliability']['failed_attempts']})
    means = []
    for setting in plan['settings']:
        passes = [r for r in rows if r['setting'] == setting['id']]
        if len(passes) == plan['passes']:
            means.append({'model': setting['model'], 'setting': setting['id'], 'passes': len(passes),
                **{k: statistics.mean(r[k] for r in passes) for k in ['log_auc_pct', 'untimed_pct', 'p50_s', 'p95_s']},
                'log_auc_sd_pp': statistics.stdev(r['log_auc_pct'] for r in passes)})
    result = {'complete_passes': len(rows), 'expected_passes': 18, 'results': rows, 'aggregate': means}
    (args.reports / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    if rows:
        with (args.reports / 'results.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
    lines = ['# Decision 2.0 on RunPod RTX PRO 6000', '', f'{len(rows)} of 18 passes complete and verified.', '',
        '| Model | Mean log-AUC (%) | Mean untimed (%) | SD (pp) | Mean p50 / p95 (s) |', '|---|---:|---:|---:|---:|']
    for row in means:
        lines.append(f"| {row['model']} | {row['log_auc_pct']:.2f} | {row['untimed_pct']:.2f} | {row['log_auc_sd_pp']:.2f} | {row['p50_s']:.3f} / {row['p95_s']:.3f} |")
    lines += ['', 'Each pass records all 480 states across eight scenarios at the unchanged 2 s cadence, '
        '32 workers and serial scenarios. Primary scores use equal-family normalized log-AUC over 0.5–8 s. '
        'Three-pass means give each complete pass equal weight. Partial recordings receive no full-dataset score.', '',
        'All six models use the immutable model release and its native Decision 2.0 CUDA runtime, BF16-resident '
        'backbones and the exact independent-question path. Model and benchmark run on the same RTX PRO 6000 '
        'Blackwell Server Edition (96 GB). Native manifest checks, loaded parameter counts, CUDA placement and '
        'all 480 untruncated input encodings are checked before three unrelated warmups. Every pass loads a '
        'fresh process. Latency includes queueing, tokenization and native inference. Native answers and '
        'probabilities are preserved in events.', '',
        'Reproduce: `uv run python scripts/runpod/decision20_report.py`.', '',
        '| Pass | Log-AUC (%) | Untimed (%) | p50 / p95 (s) | Failed attempts |', '|---|---:|---:|---:|---:|']
    for row in rows:
        name = f"{row['setting']}-pass{row['pass']}"
        lines.append(f"| [{name}]({name}/REPORT.md) | {row['log_auc_pct']:.2f} | {row['untimed_pct']:.2f} | {row['p50_s']:.3f} / {row['p95_s']:.3f} | {row['failed_attempts']} |")
    lines += ['', 'Pinned revisions, native file checksums and parameter counts are recorded in '
        '[the frozen plan](../../../../scripts/runpod/decision20-plan.json). '
        '[Raw events, input audits and source receipts](../../../../runs/decision20-pro6000-20261003/) '
        'preserve each measurement. The deployment archive freezes the benchmark source and dataset; '
        'the upstream source archive preserves each native runtime and is checked against its release manifest. '
        'Dependency versions and GPU identity are retained alongside the recordings. '
        'The upstream optimized path targets ROCm; these measurements use the native CUDA eager path.', '']
    cleanup_path = args.raw / 'cleanup.json'
    if cleanup_path.exists():
        cleanup = json.loads(cleanup_path.read_text())
        if cleanup['deletion_verified']:
            lines += [f"Rental deletion and absence were verified at {cleanup['deleted_at_utc']}. "
                f"Estimated GPU charge: US${cleanup['estimated_gpu_charge_usd']:.2f} "
                f"at US${cleanup['gpu_hourly_usd']:.2f}/h; disk charges are additional.", '']
    (args.reports / 'README.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({'complete_passes': len(rows), 'aggregate': means}), flush=True)


if __name__ == '__main__':
    main()
