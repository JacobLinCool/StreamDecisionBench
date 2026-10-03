"""Record pinned Decision 2.0 native CUDA decisions without altering requests."""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from streamdecisionbench.adapters.base import StatelessAdapter
from streamdecisionbench.jev import validate_response
from streamdecisionbench.lite.core import digest, load_dataset, request_for
from streamdecisionbench.lite.runtime import run_dataset


def audit_request(runtime, request, encode, question_to_row):
    backend = runtime.backend
    lengths = []
    for qid, question in request['questions'].items():
        row = question_to_row({'id': 'audit', 'state': request['state']}, qid, question)
        if (row['state'] != request['state'] or row['instructions'] != question['instructions']
                or row['options'] != [{'key': key, 'description': description}
                                      for key, description in question['criteria'].items()]):
            raise ValueError('Native input mapping changed the request')
        encoded = encode(row, backend.tokenizer, backend.cap)
        if encoded['keys'] != list(question['criteria']):
            raise ValueError('Native encoder changed the answer options')
        lengths.append(len(encoded['ids']))
    return {'request_sha256': digest(request), 'sequence_tokens': lengths,
            'question_rows': len(lengths)}


class DecisionAdapter(StatelessAdapter):
    def __init__(self, runtime, lock, model):
        self.runtime, self.lock, self.name = runtime, lock, 'decision20:' + model

    def system_one(self, request):
        import torch
        with self.lock:
            response = self.runtime.system_one(**request)
            torch.cuda.synchronize()
            validate_response(response, request['questions'])
            response['usage']['native_answers'] = response['answers']
            return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--setting', required=True)
    parser.add_argument('--pass-number', type=int, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    if not 1 <= args.pass_number <= plan['passes']:
        raise ValueError('Pass number outside frozen plan')
    setting = next(s for s in plan['settings'] if s['id'] == args.setting)
    prepared = json.loads((Path('/workspace/prepared') / (args.setting + '.json')).read_text())
    if (prepared['model'], prepared['model_revision']) != (setting['model'], setting['revision']):
        raise ValueError('Prepared checkpoint differs from frozen plan')
    sys.path.insert(0, prepared['model_path'])
    from decision2 import Decision2
    import torch
    runtime = Decision2.from_pretrained(prepared['model_path'], device='cuda:0',
        base_path=prepared['base_path'], threads=8, bf16_resident=True, share_context=False)
    placement = {str(p.device) for p in runtime.backend.model.parameters()}
    if not placement or any(not d.startswith('cuda') for d in placement):
        raise RuntimeError('Native model has CPU/offload parameters')
    encoder = importlib.import_module('decision2._vendor.dev2model.decision_model').encode
    question_to_row = importlib.import_module('decision2._vendor.dev2model.infer').question_to_row
    episodes, manifest = load_dataset(ROOT / 'data/lite/v1')
    if manifest['dataset_hash'] != plan['dataset_sha256']:
        raise ValueError('Dataset differs from frozen plan')
    rows = []
    for episode in episodes:
        for step in episode['steps']:
            rows.append({'episode_id': episode['episode_id'], 't': step['t'],
                         **audit_request(runtime, request_for(episode, step), encoder, question_to_row)})
    audit = {'dataset_hash': manifest['dataset_hash'], 'model_revision': setting['revision'],
             'requests': len(rows), 'question_rows': sum(r['question_rows'] for r in rows),
             'max_sequence_tokens': max(max(r['sequence_tokens']) for r in rows),
             'issues': [], 'rows': rows}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    audit_path = args.out.parent / (args.setting + '.input-audit.json')
    audit_path.write_text(json.dumps(audit, indent=2) + '\n')
    lock = threading.Lock()
    factory = lambda: DecisionAdapter(runtime, lock, setting['model'])
    probe = {'state': {'message': 'The meeting is tomorrow.'}, 'questions': {
        'when': {'type': 'choice', 'instructions': 'When does the meeting start?',
                 'criteria': {'today': 'today', 'tomorrow': 'tomorrow'}}}}
    for _ in range(3):
        factory().system_one(probe)
    import hashlib
    inference = {'device': 'cuda:0', 'bf16_resident': True, 'share_context': False,
        'max_input_tokens': runtime.max_input_tokens, 'temperatures': runtime.backend.temperatures,
        'residency': runtime.backend.residency, 'native_fast_path': runtime.backend.fast is not None,
        'parameter_count': runtime.backend.parameter_count(), 'placement': sorted(placement),
        'generated_tokens': 0}
    config = {'provider': 'decision20', 'model': setting['model'], 'model_revision': setting['revision'],
        'reasoning_effort': None, 'protocol': 'retry_excluded_successful_attempt_v1',
        'workers': 32, 'episode_concurrency': 1, 'request_timeout_s': None,
        'max_attempts': 3, 'retry_delay_s': 0.5, 'sdk_retries': 0, 'custom_endpoint': False,
        'transport': 'native_library', 'pass_number': args.pass_number,
        'measurement_location': 'RunPod RTX PRO 6000; benchmark and model on the same GPU host',
        'untimed': 'final successful response per state; transport failures excluded',
        'adapter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'input_audit_sha256': hashlib.sha256(audit_path.read_bytes()).hexdigest(),
        'prepared_checkpoint': prepared, 'inference': inference}
    print(json.dumps(config), flush=True)
    run_dataset(episodes, manifest, factory, args.out, config)


if __name__ == '__main__':
    main()
