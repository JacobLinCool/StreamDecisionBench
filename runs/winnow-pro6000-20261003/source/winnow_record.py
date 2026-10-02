"""Record a pinned Winnow server using the existing SDB timing and scoring protocol."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from streamdecisionbench.adapters.base import FatalAdapterError, StatelessAdapter
from streamdecisionbench.jev import validate_response
from streamdecisionbench.lite.core import digest, load_dataset, request_for
from streamdecisionbench.lite.runtime import run_dataset


class WinnowAdapter(StatelessAdapter):
    def __init__(self, endpoint, setting):
        self.client = httpx.Client(base_url=endpoint, timeout=90.0)
        self.setting = setting
        self.name = 'winnow:' + setting['model']

    def post(self, endpoint, request):
        try:
            reply = self.client.post(endpoint, json={
                **request, 'model': self.setting['model'],
                'winnow': {'temperature': self.setting['temperature'],
                           'diagnostics': True, 'reuse_prefix': True},
            })
            reply.raise_for_status()
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise ConnectionError('Winnow transport failed') from error
        except httpx.HTTPStatusError as error:
            raise FatalAdapterError(f'Winnow HTTP {error.response.status_code}: {error.response.text}') from error
        return reply.json()

    def system_one(self, request):
        result = self.post('/v1/systemone', request)
        if result['model'] != self.setting['model']:
            raise FatalAdapterError('Unexpected served model')
        result['usage']['winnow_diagnostics'] = result.pop('winnow')
        result['usage']['native_answers'] = result['answers']
        return result

    def close(self):
        self.client.close()


def audit_inputs(adapter, episodes, manifest, plan):
    rows = []
    runtime = None
    for episode in episodes:
        for step in episode['steps']:
            request = request_for(episode, step)
            inspected = adapter.post('/v1/winnow/inspect', request)
            info = inspected.pop('runtime')
            if runtime is None:
                runtime = info
            if info != runtime:
                raise ValueError('Runtime changed during audit')
            if 'RTX PRO 6000' not in info['device'] or info['cache_type'] != plan['kv_cache']:
                raise ValueError('Unexpected device or KV precision')
            if info['context'] != plan['context'] or info['parallel'] != plan['decision_parallel']:
                raise ValueError('Unexpected decision capacity')
            if len(inspected['suffix_tokens']) != len(request['questions']):
                raise ValueError('Question count changed during encoding')
            if inspected['prefix_tokens'] + inspected['request_prefix_tokens'] + max(inspected['suffix_tokens']) >= info['context']:
                raise ValueError('Request exceeds configured context')
            if any(len(q['criteria']) > len(info['labels']) for q in request['questions'].values()):
                raise ValueError('Not enough answer labels')
            rows.append({'episode_id': episode['episode_id'], 't': step['t'],
                         'request_sha256': digest(request), **inspected})
    if len(rows) != 480:
        raise ValueError('Expected all 480 requests')
    return {'dataset_sha256': manifest['dataset_hash'], 'requests': len(rows),
            'runtime': runtime, 'issues': [], 'rows': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--setting', required=True)
    parser.add_argument('--pass-number', type=int, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--endpoint', default='http://127.0.0.1:8091')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    setting = next(s for s in plan['settings'] if s['id'] == args.setting)
    if not 1 <= args.pass_number <= plan['passes']:
        raise ValueError('Pass number outside plan')
    episodes, manifest = load_dataset(ROOT / 'data/lite/v1')
    if manifest['dataset_hash'] != plan['dataset_sha256'] or len(episodes) != 8:
        raise ValueError('Dataset differs from frozen plan')
    factory = lambda: WinnowAdapter(args.endpoint, setting)
    adapter = factory()
    try:
        audit = audit_inputs(adapter, episodes, manifest, plan)
        audit_bytes = (json.dumps(audit, indent=2) + '\n').encode()
        args.out.parent.mkdir(parents=True, exist_ok=True)
        (args.out.parent / f'{args.setting}.input-audit.json').write_bytes(audit_bytes)
        probe = {'state': {'message': 'The meeting starts tomorrow.'}, 'questions': {
            'when': {'type': 'choice', 'instructions': 'When does the meeting start?',
                     'criteria': {'today': 'today', 'tomorrow': 'tomorrow'}}}}
        for _ in range(3):
            validate_response(adapter.system_one(probe), probe['questions'])
    finally:
        adapter.close()
    config = {
        'provider': 'winnow', 'model': setting['model'], 'model_revision': setting['revision'],
        'reasoning_effort': None, 'protocol': 'retry_excluded_successful_attempt_v1',
        'workers': 32, 'episode_concurrency': 1, 'request_timeout_s': 90.0,
        'max_attempts': 3, 'retry_delay_s': 0.5, 'sdk_retries': 0, 'custom_endpoint': True,
        'measurement_location': 'RunPod RTX PRO 6000; benchmark and model on the same GPU host',
        'transport': 'loopback_http', 'pass_number': args.pass_number,
        'untimed': 'final successful response per state; transport failures excluded',
        'adapter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'input_audit_sha256': hashlib.sha256(audit_bytes).hexdigest(),
        'inference': {**setting, 'upstream_commit': plan['upstream_commit'],
                      'runtime': audit['runtime'], 'weight_dtype': 'BF16',
                      'memory_policy': 'exclusive', 'reuse_prefix': True,
                      'warmups': 3, 'fresh_server_per_pass': True},
    }
    run_dataset(episodes, manifest, factory, args.out, config)


if __name__ == '__main__':
    main()
