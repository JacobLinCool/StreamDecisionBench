"""Submission copies preserve measurements while propagating metadata digests."""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/paper/build_submission.py'
SPEC = importlib.util.spec_from_file_location('submission_packaging', SCRIPT)
packaging = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packaging)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def test_redacted_metadata_receipts_propagate_through_report_and_manifest():
    measurement = b'{"latency_s":2.35,"prediction":"K02"}\n'
    run = b'{"host":"private-host","events_sha256":"' + digest(measurement).encode() + b'"}\n'
    report = json.dumps({'recording': digest(run), 'accuracy': 0.49508445}).encode()
    manifest = json.dumps({'report': digest(report)}).encode()
    original = {'events.jsonl': measurement, 'run.json': run, 'report.json': report, 'manifest.json': manifest}
    sanitized = {**original, 'run.json': run.replace(b'private-host', b'anonymous-host')}
    result = packaging.remap_receipts(sanitized, {p: digest(x) for p, x in original.items()})
    assert result['events.jsonl'] == measurement
    assert json.loads(result['report.json']) == {'recording': digest(result['run.json']), 'accuracy': 0.49508445}
    assert json.loads(result['manifest.json']) == {'report': digest(result['report.json'])}
    assert json.loads(result['run.json'])['events_sha256'] == digest(measurement)


def test_immutable_public_data_is_rejected_instead_of_silently_redacted(tmp_path):
    path = tmp_path/'data/lite/v1/episode.json'
    path.parent.mkdir(parents=True)
    path.write_text('{"state":"NYCU"}')
    manifest = {'openweight': {'policy': {'manuscript_settings': []}}, 'hosted': {}}
    with pytest.raises(ValueError, match='immutable measurement'):
        packaging.transformed_inputs(tmp_path, {'data/lite/v1/episode.json'}, manifest)
    assert path.read_text() == '{"state":"NYCU"}'


def test_author_redaction_preserves_third_party_attribution():
    text = 'Copyright 2026 JacobLinCool\nCopyright 2026 Third Party\nNVIDIA RTX PRO 6000\n'
    result = packaging.redact_text(text)
    assert 'JacobLinCool' not in result
    assert 'Copyright 2026 Third Party' in result
    assert 'NVIDIA RTX PRO 6000' in result


def test_zip_preserves_exact_measurement_bytes_and_has_no_host_metadata(tmp_path):
    payload = {'runs/model/events.jsonl': b'{"latency":0.23220369}\n', 'README.md': b'Anonymous artifact\n'}
    archive = tmp_path/'data.zip'
    packaging.write_zip(archive, payload, set(payload))
    with zipfile.ZipFile(archive) as z:
        for name, raw in payload.items():
            item = z.getinfo('streamdecisionbench/'+name)
            assert z.read(item) == raw
            assert item.date_time == (2026, 10, 4, 0, 0, 0)
            assert item.extra == b''


def test_native_cache_redaction_changes_only_diagnostic_source_path():
    source = '/eva_data1/takala/sdb-pro6000/hf/models--Qwen/snapshots/abc'
    event = {'request_hash': 'same-input', 'received_s': 2.350001, 'pred': {'route': 'K02'},
             'usage': {'input_tokens': 100, 'native_fields': {
                 'route': {'model': {'source': source, 'revision': 'abc'}, 'answer': 'K02'}}}}
    raw = (json.dumps(event)+'\n').encode()
    result = packaging.redact_event_metadata(raw, 'events.jsonl')
    assert result == raw.replace(b'/eva_data1/takala/sdb-pro6000', b'/anonymous-host')
    event['usage']['native_fields']['route']['model']['source'] = '/anonymous-host/hf/models--Qwen/snapshots/abc'
    assert json.loads(result) == event
    # A matching literal in an actual response is evidence, not metadata.
    event['pred']['route'] = source
    event['usage']['native_fields']['route']['model']['source'] = source
    with pytest.raises(ValueError, match='measurement or unapproved'):
        packaging.redact_event_metadata(json.dumps(event).encode(), 'events.jsonl')


def test_verifier_accepts_dependency_environment_but_rejects_extra_evidence(tmp_path, monkeypatch):
    path = SCRIPT.with_name('verify_submission.py')
    spec = importlib.util.spec_from_file_location('submission_verifier', path)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    monkeypatch.setattr(verifier, 'ROOT', tmp_path)
    (tmp_path/'README.md').write_bytes(b'Artifact')
    receipt = {'files': {'README.md': {'bytes': 8, 'sha256': digest(b'Artifact')}}}
    (tmp_path/'ARTIFACT_MANIFEST.json').write_text(json.dumps(receipt))
    (tmp_path/'.venv').mkdir()
    (tmp_path/'.venv/pyvenv.cfg').write_text('Environment installed by the reviewer')
    assert verifier.verify_inventory() == receipt
    (tmp_path/'unexpected.json').write_text('{}')
    with pytest.raises(ValueError, match='Unexpected files'):
        verifier.verify_inventory()


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf'), True])
def test_score_verifier_rejects_nonfinite_or_boolean_numeric_results(value):
    spec = importlib.util.spec_from_file_location('submission_verifier', SCRIPT.with_name('verify_submission.py'))
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    with pytest.raises(ValueError, match='numeric result differs'):
        verifier.compare(value, 1.0, 'accuracy')
