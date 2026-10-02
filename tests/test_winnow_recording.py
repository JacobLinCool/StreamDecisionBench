"""Winnow's adapter must preserve the benchmark request and native committed answer."""
import importlib.util
from pathlib import Path

import httpx
import pytest

SPEC = importlib.util.spec_from_file_location('winnow_record', Path(__file__).parents[1] / 'scripts/runpod/winnow_record.py')
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_lossless_request_and_native_answer():
    request = {'state': {'text': '會議 <tomorrow>', 'nested': [1, 2]}, 'questions': {
        'route': {'type': 'choice', 'instructions': {'rule': 'Pick the recorded day'},
                  'criteria': {'today': None, 'tomorrow': {'description': '明天'}}}}}
    answer = {'type': 'choice', 'choice': 'tomorrow',
              'probabilities': {'today': .2, 'tomorrow': .8}, 'confidence': .278}
    def handler(req):
        import json
        body = json.loads(req.content)
        assert body['state'] == request['state']
        assert body['questions'] == request['questions']
        assert body['winnow']['temperature'] == 1.3331553765162731
        return httpx.Response(200, json={'model': 'test', 'answers': {'route': answer},
                                         'usage': {'input_tokens': 30, 'output_tokens': 0},
                                         'winnow': {'prefix_tokens': 20}})
    adapter = module.WinnowAdapter('http://localhost', {'model': 'test', 'temperature': 1.3331553765162731})
    adapter.client.close()
    adapter.client = httpx.Client(transport=httpx.MockTransport(handler), base_url='http://localhost')
    try:
        result = adapter.system_one(request)
        assert result['answers']['route'] == answer
        assert result['usage']['native_answers']['route'] == answer
        assert result['usage']['winnow_diagnostics']['prefix_tokens'] == 20
        module.validate_response(result, request['questions'])
    finally:
        adapter.close()


def test_capacity_errors_are_fatal():
    adapter = module.WinnowAdapter('http://localhost', {'model': 'test', 'temperature': 1})
    adapter.client.close()
    adapter.client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(400, json={'error': 'context capacity'})), base_url='http://localhost')
    try:
        with pytest.raises(module.FatalAdapterError, match='context capacity'):
            adapter.system_one({'state': 'test', 'questions': {}})
    finally:
        adapter.close()
