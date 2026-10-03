"""Lossless Decision 2.0 audit rejects native input or candidate changes."""
import importlib.util
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('decision20_record', ROOT / 'scripts/runpod/decision20_record.py')
record = importlib.util.module_from_spec(spec)
spec.loader.exec_module(record)


def request():
    return {'state': {'messages': ['a', 'b'], 'count': 3}, 'questions': {
        'route': {'type': 'choice', 'instructions': {'rule': 'use the latest evidence'},
                  'criteria': {'a': {'definition': 'first'}, 'b': None}}}}


def native_row(item, qid, question):
    return {'state': item['state'], 'instructions': question['instructions'],
            'options': [{'key': key, 'description': value} for key, value in question['criteria'].items()]}


def test_audit_preserves_structured_input_and_null_criteria():
    runtime = SimpleNamespace(backend=SimpleNamespace(tokenizer=object(), cap=8192))
    def encode(row, tokenizer, cap):
        assert cap == 8192
        assert row['state'] == request()['state']
        return {'ids': [1, 2, 3], 'keys': ['a', 'b']}
    result = record.audit_request(runtime, request(), encode, native_row)
    assert result == {'request_sha256': record.digest(request()), 'sequence_tokens': [3], 'question_rows': 1}


@pytest.mark.parametrize('change', ['state', 'instructions', 'options', 'keys'])
def test_audit_rejects_lossy_native_encoding(change):
    runtime = SimpleNamespace(backend=SimpleNamespace(tokenizer=None, cap=8192))
    def row(item, qid, question):
        value = native_row(item, qid, question)
        if change != 'keys':
            value[change] = []
        return value
    def encode(*args):
        return {'ids': [1], 'keys': ['b', 'a'] if change == 'keys' else ['a', 'b']}
    with pytest.raises(ValueError, match='changed'):
        record.audit_request(runtime, request(), encode, row)


def test_incomplete_recording_has_no_full_dataset_score(tmp_path):
    module_spec = importlib.util.spec_from_file_location('decision20_report', ROOT / 'scripts/runpod/decision20_report.py')
    report = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(report)
    (tmp_path / 'run.json').write_text(json.dumps({'status': 'running'}))
    with pytest.raises(ValueError, match='Incomplete'):
        report.validate(tmp_path, tmp_path, {}, {})


@pytest.mark.parametrize('changed', ['archive', 'runtime'])
def test_preserved_native_archive_rejects_changed_source(tmp_path, changed):
    module_spec = importlib.util.spec_from_file_location('decision20_report', ROOT / 'scripts/runpod/decision20_report.py')
    report = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(report)
    source = b'published native runtime\n'
    path = tmp_path / 'upstream-sources.tar.gz'
    with tarfile.open(path, 'w:gz') as archive:
        entry = tarfile.TarInfo('model/decision2/api.py')
        entry.size = len(source)
        archive.addfile(entry, io.BytesIO(source))
    (tmp_path / 'archives.json').write_text(json.dumps({'upstream-sources.tar.gz': report.sha(path)}))
    manifest = {'runtime_files': {'decision2/api.py': {'sha256': hashlib.sha256(source).hexdigest()}}}
    report.verify_native_archive(tmp_path, {'model': 'owner/model'}, manifest)
    if changed == 'archive':
        path.write_bytes(path.read_bytes() + b'changed')
    else:
        manifest['runtime_files']['decision2/api.py']['sha256'] = hashlib.sha256(b'other runtime').hexdigest()
    with pytest.raises(ValueError, match='(archive changed|runtime differs)'):
        report.verify_native_archive(tmp_path, {'model': 'owner/model'}, manifest)
