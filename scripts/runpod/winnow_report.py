"""Validate and summarize the three frozen Winnow passes without model inference."""
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
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(run, raw, plan, setting):
    frozen = json.loads((run / 'run.json').read_text())
    if frozen['status'] != 'complete' or sha(run / 'events.jsonl') != frozen['events_sha256']:
        raise ValueError('Incomplete recording or changed event bytes')
    config = frozen['config']
    if config['model_revision'] != setting['revision'] or config['inference']['sha256'] != setting['sha256']:
        raise ValueError('Model differs from frozen plan')
    if sha(raw / 'source/winnow_record.py') != config['adapter_sha256']:
        raise ValueError('Recorder differs from frozen source')
    archives = json.loads((raw / 'archives.json').read_text())
    if any(sha(raw / name) != checksum for name, checksum in archives.items()):
        raise ValueError('Source archive checksum mismatch')
    with tarfile.open(raw / 'deployment.tar.gz') as archive:
        archived_manifest = json.load(archive.extractfile('data/lite/v1/manifest.json'))
        if archived_manifest != frozen['dataset_manifest']:
            raise ValueError('Dataset manifest differs from frozen deployment')
        for name, checksum in frozen['run_sources'].items():
            member = archive.extractfile('src/streamdecisionbench/' + name)
            if member is None or hashlib.sha256(member.read()).hexdigest() != checksum:
                raise ValueError(f'Frozen source mismatch: {name}')
    audit_path = run.parent / (setting['id'] + '.input-audit.json')
    if sha(audit_path) != config['input_audit_sha256']:
        raise ValueError('Input audit hash mismatch')
    audit = json.loads(audit_path.read_text())
    if audit['requests'] != 480 or audit['issues'] or audit['dataset_sha256'] != plan['dataset_sha256']:
        raise ValueError('Input audit coverage mismatch')
    verified = rescore_run(run)
    episodes = json.loads((run / 'episodes.json').read_text())
    if frozen['dataset_manifest']['dataset_hash'] != plan['dataset_sha256']:
        raise ValueError('Dataset identity mismatch')
    hashes = frozen['dataset_manifest']['hashes']
    if {e['episode_id']: digest(e) for e in episodes} != hashes:
        raise ValueError('Frozen episode content differs from the manifest')
    audited = {(r['episode_id'], r['t']): r['request_sha256'] for r in audit['rows']}
    seen = set()
    for episode in episodes:
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
            if {key: committed_answer(question, native[key])
                    for key, question in episode['questions'].items()} != response['wire_answers']:
                raise ValueError('Committed answer differs from native response')
            seen.add(key)
    if len(seen) != 480 or len(episodes) != 8:
        raise ValueError('Incomplete dataset coverage')
    return frozen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, default=ROOT / 'runs/winnow-pro6000-20261003')
    parser.add_argument('--reports', type=Path, default=ROOT / 'docs/lite/results/winnow-pro6000-20261003')
    args = parser.parse_args()
    plan = json.loads((args.raw / 'source/winnow-plan.json').read_text())
    args.reports.mkdir(parents=True, exist_ok=True)
    rows = []
    for number in range(1, plan['passes'] + 1):
        for setting in plan['settings']:
            name = f"{setting['id']}-pass{number}"
            run = args.raw / f'pass{number}' / setting['id']
            if not (run / 'run.json').exists() or json.loads((run / 'run.json').read_text())['status'] != 'complete':
                continue
            frozen = validate(run, args.raw, plan, setting)
            out = args.reports / name
            evaluate_one(run, out, f"{setting['model']} — pass {number}")
            data = json.loads((out / 'analysis.json').read_text())
            primary = data['auc']['primary']['overall']
            witnesses = []
            seen_families = set()
            for episode in data['scores']['per_episode']:
                family = episode['task_family']
                if family not in seen_families and episode['mistakes']:
                    seen_families.add(family)
                    witnesses.append({'family': family, 'episode_id': episode['episode_id'],
                                      **episode['mistakes'][0]})
            (out / 'error-witnesses.json').write_text(json.dumps(witnesses, ensure_ascii=False, indent=2) + '\n')
            findings = [f'# Recorded errors: {name}', '',
                        'The first untimed mismatch in each family is selected deterministically. '
                        'These observations do not establish a cause or estimate generalization.', '']
            for witness in witnesses:
                findings += [f"## {witness['family']}: {witness['episode_id']}, tick {witness['t']}", '',
                             f"Wrong active fields: {', '.join(witness['wrong_active_questions'])}.", '',
                             '```json', json.dumps({key: witness[key] for key in
                                 ['reference_decision', 'predicted_decision', 'reference_evidence']},
                                 ensure_ascii=False, indent=2), '```', '']
            if not witnesses:
                findings += ['No untimed mismatch occurred in this pass.', '']
            findings += ['For deployment review, inspect routing and its active fields together against '
                         'the frozen state and recorded evidence. All errors remain in `analysis.json`.', '']
            (out / 'FINDINGS.md').write_text('\n'.join(findings))
            with (out / 'REPORT.md').open('a') as stream:
                stream.write('\n[Recorded error examples](FINDINGS.md).\n')
            rows.append({'setting': name, 'model': setting['model'], 'pass': number,
                         'requests': 480, 'log_auc_pct': 100 * primary['accuracy'],
                         'untimed_accuracy_pct': 100 * primary['untimed'],
                         'latency_p50_s': data['latency_s']['p50'], 'latency_p95_s': data['latency_s']['p95'],
                         'failed_attempts': data['retry_reliability']['failed_attempts'],
                         'events_sha256': frozen['events_sha256']})
    aggregate = []
    for setting in plan['settings']:
        selected = [r for r in rows if r['model'] == setting['model']]
        if len(selected) == plan['passes']:
            aggregate.append({'model': setting['model'], 'passes': len(selected),
                              **{metric + '_mean': statistics.mean(r[metric] for r in selected)
                                 for metric in ['log_auc_pct', 'untimed_accuracy_pct']},
                              'log_auc_pct_sd': statistics.stdev(r['log_auc_pct'] for r in selected),
                              'log_auc_pct_min': min(r['log_auc_pct'] for r in selected),
                              'log_auc_pct_max': max(r['log_auc_pct'] for r in selected)})
    summary = {'complete_passes': len(rows), 'expected_passes': 6, 'results': rows, 'aggregate': aggregate}
    (args.reports / 'results.json').write_text(json.dumps(summary, indent=2) + '\n')
    if rows:
        with (args.reports / 'results.csv').open('w') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    lines = ['# Winnow on RTX PRO 6000', '', f'{len(rows)} of 6 full-dataset passes completed and hash-verified.', '',
             '| Model | Mean log-AUC (%) | Sample SD (pp) | Range (%) | Mean untimed (%) |',
             '|---|---:|---:|---:|---:|']
    for a in aggregate:
        lines.append(f"| {a['model']} | {a['log_auc_pct_mean']:.2f} | {a['log_auc_pct_sd']:.2f} | {a['log_auc_pct_min']:.2f}–{a['log_auc_pct_max']:.2f} | {a['untimed_accuracy_pct_mean']:.2f} |")
    lines += ['', '| Pass | Log-AUC (%) | Untimed (%) | p50 / p95 (s) | Failed attempts |',
              '|---|---:|---:|---:|---:|']
    for r in rows:
        lines.append(f"| [{r['setting']}]({r['setting']}/REPORT.md) | {r['log_auc_pct']:.2f} | {r['untimed_accuracy_pct']:.2f} | {r['latency_p50_s']:.3f} / {r['latency_p95_s']:.3f} | {r['failed_attempts']} |")
    lines += ['', '## Measurement', '',
              'One RunPod NVIDIA RTX PRO 6000 Blackwell Server Edition (96 GB), with model and benchmark on the same host. '
              'Both models use verified BF16 GGUF weights, the pinned upstream Winnow native CUDA decision server, '
              'F16 KV cache, a 32,768-position context, four decision branches, selected answer head and exclusive memory scheduling. '
              'Native prefix reuse is enabled within each pass. Each pass starts a fresh server; three unrelated synthetic warmups and '
              'a model-free input audit are excluded from recording. Loopback HTTP, tokenization, queueing and inference are included in latency.', '',
              'The unchanged dataset contains 480 states across eight scenarios, released at a 2 s cadence with 32 workers and serial scenarios. '
              'The primary score is equal-family normalized log-AUC over 0.5–8 s under the existing retry-excluded protocol. '
              'Reported means give each of the three passes equal weight. Sample SD and ranges describe repeat variation on this fixed dataset; '
              'they are not uncertainty estimates over independent tasks.', '',
              'Winnow-12B uses upstream temperature 1.0. Winnow-E4B uses its published BF16 calibration temperature '
              '1.3331553765162731. Native committed choices are preserved; no setting was selected using SDB accuracy.', '',
              '## Reproduction and provenance', '',
              '`uv run python scripts/runpod/winnow_report.py`', '',
              f"Dataset SHA-256: `{plan['dataset_sha256']}`. Winnow inference commit: `{plan['upstream_commit']}`. "
              'The frozen plan records model revisions and weight checksums. Raw events, request audits, dependencies, source snapshots, '
              'GPU details and server logs are retained in `runs/winnow-pro6000-20261003`.', '']
    cleanup = args.raw / 'cleanup.json'
    if cleanup.exists():
        cost = json.loads(cleanup.read_text())
        preflight = json.loads((args.raw / 'preflight.json').read_text())
        gpu_total = cost['estimated_gpu_charge_usd'] + preflight['estimated_gpu_charge_usd']
        lines += ['## Rental cleanup', '',
                  f"Pod deletion verified: {cost['deletion_verified']}. Estimated GPU charge across both allocations: "
                  f"US${gpu_total:.2f}, excluding container-disk charges. This is an elapsed-time estimate, not a final invoice. "
                  'The first allocation ended during a pre-recording residency-log check and produced no benchmark requests. '
                  'The replacement used the same termination deadline and completed the recorded cohort.', '']
    (args.reports / 'README.md').write_text('\n'.join(lines))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
