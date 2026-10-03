"""Mirror this owned rental's evidence, validate completions, and delete the Pod."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]


def call(args, timeout=180):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection', type=Path, required=True)
    args = parser.parse_args()
    connection = json.loads(args.connection.read_text())
    cache = args.connection.parent
    plan = json.loads((ROOT / 'scripts/runpod/decision20-plan.json').read_text())
    raw = ROOT / 'runs' / plan['experiment_id']
    raw.mkdir(parents=True, exist_ok=True)
    archive = cache / 'deployment.tar.gz'
    if hashlib.sha256(archive.read_bytes()).hexdigest() != connection['deployment_sha256']:
        raise ValueError('Deployment source changed')
    (raw / 'deployment.tar.gz').write_bytes(archive.read_bytes())
    (raw / 'archives.json').write_text(json.dumps({'deployment.tar.gz': connection['deployment_sha256']}, indent=2))
    ssh = ['ssh', '-i', connection['key'], '-p', str(connection['port']), '-o', 'BatchMode=yes',
           '-o', 'ConnectTimeout=15', '-o', 'StrictHostKeyChecking=yes',
           '-o', 'UserKnownHostsFile=' + str(cache / 'known_hosts')]
    remote = 'root@' + connection['ip']
    completed = []
    deadline = datetime.fromisoformat(connection['deadline']['terminate_at_utc'])
    while True:
        try:
            call(['rsync', '-az', '--partial', '--delay-updates', '--timeout=30', '-e', shlex.join(ssh),
                  remote + ':/workspace/results/', str(raw) + '/'])
            status_path = raw / 'status.json'
            status = json.loads(status_path.read_text()) if status_path.exists() else {'status': 'bootstrapping'}
            print(datetime.now(timezone.utc).isoformat(), json.dumps(status), flush=True)
            if status.get('completed', []) != completed and status.get('completed'):
                report = call([str(ROOT / '.venv/bin/python'), str(ROOT / 'scripts/runpod/decision20_report.py')], timeout=900)
                print(report.stdout, flush=True)
                completed = status['completed']
            if status['status'] in {'complete', 'finished_with_failures', 'failed'}:
                if status.get('completed'):
                    call([str(ROOT / '.venv/bin/python'), str(ROOT / 'scripts/runpod/decision20_report.py')], timeout=900)
                pod = json.loads(call(['runpodctl', 'pod', 'get', connection['pod_id']]).stdout)
                if pod['id'] != connection['pod_id'] or pod['name'] != 'sdb-decision20-20261003':
                    raise ValueError('Rental identity changed; refusing deletion')
                call(['runpodctl', 'pod', 'delete', connection['pod_id']])
                pods = json.loads(call(['runpodctl', 'pod', 'list']).stdout)
                if any(p['id'] == connection['pod_id'] for p in pods):
                    raise RuntimeError('Deletion not yet verified')
                now = datetime.now(timezone.utc)
                started = datetime.fromisoformat(connection['created_at_utc'])
                (raw / 'cleanup.json').write_text(json.dumps({'pod_id': connection['pod_id'],
                    'deletion_verified': True, 'deleted_at_utc': now.isoformat(), 'gpu_hourly_usd': 2.09,
                    'estimated_gpu_charge_usd': (now-started).total_seconds() / 3600 * 2.09,
                    'benchmark_status': status['status']}, indent=2) + '\n')
                print('Rental deleted and absence verified', flush=True)
                return
        except Exception as error:
            print('Collection:', type(error).__name__, str(error)[:500], flush=True)
        if datetime.now(timezone.utc) >= deadline:
            raise TimeoutError('Provider rental cap reached; preserve local evidence and verify auto-termination')
        time.sleep(30)


if __name__ == '__main__':
    main()
