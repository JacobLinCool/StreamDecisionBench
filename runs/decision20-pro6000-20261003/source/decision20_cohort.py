"""Prepare pinned packages and run eighteen isolated native CUDA recordings."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from decision_cohort import atomic_json, bounded_run

ROOT = Path(__file__).resolve().parents[2]
OUT = Path('/workspace/results')
PLAN = ROOT / 'scripts/runpod/decision20-plan.json'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare(setting):
    from huggingface_hub import snapshot_download
    package = Path('/workspace/models') / setting['id']
    snapshot_download(setting['model'], revision=setting['revision'], local_dir=package, max_workers=8)
    if sha(package / 'MODEL_MANIFEST.json') != setting['manifest_sha256']:
        raise ValueError('Downloaded manifest differs from frozen plan')
    manifest = json.loads((package / 'MODEL_MANIFEST.json').read_text())
    (OUT / (setting['id'] + '.MODEL_MANIFEST.json')).write_bytes((package / 'MODEL_MANIFEST.json').read_bytes())
    base_path = None
    if setting['base'] is not None:
        base = setting['base']
        base_path = Path('/workspace/models') / (setting['id'] + '-base')
        snapshot_download(base['repo_id'], revision=base['revision'], local_dir=base_path,
                          allow_patterns=list(base['files_sha256']), max_workers=8)
        for name, checksum in base['files_sha256'].items():
            if sha(base_path / name) != checksum:
                raise ValueError('Pinned base checksum mismatch: ' + name)
    for name, checksum in manifest['files_sha256'].items():
        if sha(package / name) != checksum:
            raise ValueError('Package checksum mismatch: ' + name)
    prepared = {'model': setting['model'], 'model_revision': setting['revision'],
        'model_path': str(package), 'base_path': str(base_path) if base_path else None,
        'manifest_sha256': setting['manifest_sha256'], 'manifest': manifest}
    Path('/workspace/prepared').mkdir(exist_ok=True)
    atomic_json(Path('/workspace/prepared') / (setting['id'] + '.json'), prepared)
    atomic_json(OUT / (setting['id'] + '.prepared.json'), prepared)


def main():
    plan = json.loads(PLAN.read_text())
    OUT.mkdir(exist_ok=True)
    (OUT / 'logs').mkdir(exist_ok=True)
    (OUT / 'source').mkdir(exist_ok=True)
    for name in ['decision20_record.py', 'decision20_cohort.py', 'decision20-plan.json', 'decision_cohort.py']:
        (OUT / 'source' / name).write_bytes((ROOT / 'scripts/runpod' / name).read_bytes())
    atomic_json(OUT / 'source-provenance.json', {'plan': plan,
        'source_sha256': {p.name: sha(p) for p in (OUT / 'source').iterdir()}})
    status = {'status': 'preparing', 'completed': [], 'failures': {}}
    def update():
        atomic_json(OUT / 'status.json', status)
    update()
    for setting in plan['settings']:
        status['current_setting'] = setting['id']
        update()
        prepare(setting)
    deadline = float(os.environ['SDB_WORKER_DEADLINE'])
    env = {**os.environ, 'HF_HUB_OFFLINE': '1', 'PYTHONUNBUFFERED': '1'}
    for number in range(1, plan['passes'] + 1):
        for setting in plan['settings']:
            label = f"{setting['id']}-pass{number}"
            remaining = deadline - time.time()
            if remaining < 1100:
                status['failures'][label] = 'Insufficient time before rental deadline'
                update()
                continue
            status.update(status='running', current_setting=label)
            update()
            try:
                bounded_run([sys.executable, str(ROOT / 'scripts/runpod/decision20_record.py'),
                    '--plan', str(PLAN), '--setting', setting['id'], '--pass-number', str(number),
                    '--out', str(OUT / f'pass{number}' / setting['id'])],
                    OUT / 'logs' / (label + '.log'), min(3600, remaining), cwd=ROOT, env=env)
                status['completed'].append(label)
            except Exception as error:
                status['failures'][label] = repr(error)
            update()
    status.pop('current_setting', None)
    status['status'] = 'complete' if not status['failures'] else 'finished_with_failures'
    update()
    os.sync()


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        OUT.mkdir(exist_ok=True)
        atomic_json(OUT / 'status.json', {'status': 'failed', 'error': repr(error)})
        raise
