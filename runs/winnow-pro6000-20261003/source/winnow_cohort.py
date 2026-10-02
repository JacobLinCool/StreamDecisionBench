"""Run three independent passes per Winnow model on one dedicated GPU."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
OUT = Path('/workspace/results')
PLAN = ROOT / 'scripts/runpod/winnow-plan.json'


def status(state, **details):
    temporary = OUT / 'status.tmp'
    temporary.write_text(json.dumps({'status': state, **details}, indent=2) + '\n')
    temporary.replace(OUT / 'status.json')


def main():
    plan = json.loads(PLAN.read_text())
    OUT.mkdir(exist_ok=True)
    (OUT / 'source').mkdir(exist_ok=True)
    for name in ('winnow_record.py', 'winnow_cohort.py', 'winnow-plan.json'):
        (OUT / 'source' / name).write_bytes((ROOT / 'scripts/runpod' / name).read_bytes())
    provenance = {'plan': plan, 'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (OUT / 'source').iterdir()}}
    (OUT / 'source-provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    for setting in plan['settings']:
        with (Path('/workspace/models') / setting['file']).open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != setting['sha256']:
                raise ValueError('Weight checksum mismatch')
    completed = []
    for pass_number in range(1, plan['passes'] + 1):
        for setting in plan['settings']:
            name = f"{setting['id']}-pass{pass_number}"
            status('running', current_setting=name, completed=completed)
            args = ['python3', '/workspace/winnow/scripts/serve.py', '--model',
                    '/workspace/models/' + setting['file'], '--alias', setting['model'],
                    '--text-only', '--context', str(plan['context']), '--cache', plan['kv_cache'],
                    '--decision-parallel', str(plan['decision_parallel']), '--chat-parallel', '1',
                    '--memory', 'exclusive', '--threads', '8', '-lv', '4']
            (OUT / f'{name}.command.json').write_text(json.dumps(args, indent=2))
            with (OUT / f'{name}.server.log').open('w') as server_log:
                server = subprocess.Popen(args, stdout=server_log, stderr=subprocess.STDOUT)
                try:
                    deadline = time.monotonic() + 300
                    while True:
                        if server.poll() is not None:
                            raise RuntimeError(f'{name}: server exited during startup')
                        try:
                            with urllib.request.urlopen('http://127.0.0.1:8091/health', timeout=5) as reply:
                                if reply.status == 200:
                                    break
                        except (OSError, TimeoutError):
                            pass
                        if time.monotonic() >= deadline:
                            raise TimeoutError('Server startup exceeded five minutes')
                        time.sleep(2)
                    # Full model and embedding residency are required by the upstream launcher.
                    log = (OUT / f'{name}.server.log').read_text()
                    offload = re.search(r'offloaded (\d+)/(\d+) layers to GPU', log)
                    if not offload or offload[1] != offload[2] or not re.search(r'CUDA0\s+model buffer', log):
                        raise RuntimeError('Missing CUDA weight residency evidence')
                    with (OUT / f'{name}.record.log').open('w') as record_log:
                        subprocess.run(['/workspace/bench-env/bin/python',
                                        str(ROOT / 'scripts/runpod/winnow_record.py'),
                                        '--plan', str(PLAN), '--setting', setting['id'],
                                        '--pass-number', str(pass_number), '--out',
                                        str(OUT / f'pass{pass_number}' / setting['id'])],
                                       stdout=record_log, stderr=subprocess.STDOUT, check=True, timeout=2400)
                    completed.append(name)
                finally:
                    server.terminate()
                    try:
                        server.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait()
    status('complete', completed=completed)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        status('failed', error=repr(error))
        raise
