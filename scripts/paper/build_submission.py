"""Build anonymous, manuscript-scoped ARR software and data ZIP files.

Only copies are transformed. Predictions, measured timestamps and public states
are preserved. Metadata redaction propagates through SHA-256 receipts;
review copies retain the normal verification paths. Run only after the manuscript
analysis and generated artifacts have been regenerated from the final sources.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
MANUSCRIPT = 'docs/research/manuscript-three-pass/analysis.json'
PUBLIC_LOCAL = 'docs/research/openweight-hybrids/analysis.json'
ARCHIVE_ROOT = 'streamdecisionbench'
LIMIT_BYTES = 200_000_000
HEX_SHA = re.compile(r'(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])')
IDENTITY_TERMS = (
    'JacobLinCool', 'jacob.cs14@nycu.edu.tw', 'takalawang.cs14@nycu.edu.tw',
    'Jhen-Ke Lin', 'Chung Chun Wang', 'National Yang Ming Chiao Tung University',
    'NYCU', 'EVA-241-125', '/eva_data1/takala', '/Users/jacoblincool',
)
FORBIDDEN_CONTENT = re.compile('|'.join(re.escape(x) for x in IDENTITY_TERMS), re.IGNORECASE)
CREDENTIAL_CONTENT = re.compile(
    r'\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}'
    r'|hf_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})\b|-----BEGIN [A-Z ]*PRIVATE KEY-----')
TEXT_SUFFIXES = {'.py', '.json', '.jsonl', '.md', '.txt', '.tex', '.bib', '.sty', '.bst', '.toml', '.lock'}

README = '''# StreamDecisionBench: anonymous review artifact

This artifact accompanies the anonymous manuscript. Extract **software.zip** and
**data.zip** into the same directory; both contain the `streamdecisionbench/`
root. The software archive contains the source, manuscript and generated exhibits.
The data archive contains the frozen eight-scenario dataset, exactly 45 complete
manuscript recordings (6 hosted + 9 self-hosted settings, three passes each),
their reports, native input audits and checkpoint/source receipts. No model
weights or credentials are included.

## Reproduce without model calls

Use Python 3.12 or 3.13. Install the analysis environment once with
`uv sync --locked --group paper` (dependency installation may use the network),
then choose the quick verification or full reproduction command:

```sh
uv run --no-sync python scripts/paper/verify_submission.py
# Or, in a fresh extraction, verify and regenerate all manuscript evidence:
uv run --no-sync python scripts/paper/verify_submission.py --reproduce
cd paper
latexmk submission.tex
```

The first command verifies every packaged file hash, all 45 recording receipts,
request/answer mappings, native audits and recording-cadence score partitions.
The second additionally regenerates the full manuscript analysis, all numbers,
tables and figures from the recordings, then compares the generated TeX content
with the supplied manuscript values. It makes no API request and requires no
GPU; a Python audit hook rejects network connection attempts. The full analysis
includes exact crossing-based hybrid integrations and deterministic bootstrap
refits and can take several minutes. Running regeneration updates derived files;
extract a fresh copy to rerun the initial package-integrity check.

`ARTIFACT_MANIFEST.json` is the complete file inventory with SHA-256 digests.
`docs/research/manuscript-three-pass/analysis.json` maps every setting and pass to
its recording and report. `paper/analysis/lite_repeated.py` is the regeneration
entry point. `data/lite/v1/manifest.json` identifies the frozen dataset.

## Measurement and anonymization

Hosted recordings used one MacBook with an Apple M5 Pro chip, a stable connection
and no VPN. Self-hosted recordings used one RTX PRO 6000 Blackwell Server Edition
GPU (96 GB), with the model and benchmark on the same host. Geographic location,
usernames, institutional host identifiers and local checkpoint-cache paths are
withheld for anonymous review. Model identifiers, checkpoint revisions, native
source versions, hardware, configurations, timestamps and measured outputs remain.

Frozen `episodes.json` files, the public dataset and 42 of 45 event logs are
byte-identical to the originals. The three SemIf event logs contain local cache
paths in `usage.native_fields.<question>.model.source`; only those diagnostic
metadata strings are redacted. Every other event value, including measured
timestamps, request hashes, answers and token counts, is checked unchanged.
Other redactions affect identifying metadata and manuscript author fields.
Dependent file checksums are recomputed consistently; the
original unredacted research files are not modified. Historical source digests
remain recording-time provenance and are distinct from the current analysis
source receipts. The local standalone summary is projected onto the manuscript
cohort; scores for retained settings are unchanged. Merged pass-1 recordings
already contain all eight scenarios and retain their original session receipts.
Historical report prose and recording-time producer digests are retained as
historical evidence. Appendix C and the current estimator documentation correct
the original claim that the fitted non-token intercept necessarily bounds network
delay from above. This wording correction does not change the estimator or its
numeric results; reproduction still checks the computational schema and values.

## Audit and scope

The reference audit covered the original six scenarios and was performed by LLM
agents. The preserved record contains check descriptions, reported agreement and
adjudication votes. Model/version identities and complete original audit prompts
were not preserved in this extract, so this artifact does not claim to reproduce
the original agent audit. Executable reference agreement and model recordings
can be checked independently. No human reference adjudication is claimed.

Scores are descriptive means of three passes on fixed synthetic timelines.
Retimed and combined systems reuse observed latencies; joint contention was not
measured. The paper's fixed cohort differs from a continuously expanded public
leaderboard. The bundle's reproduction command addresses the manuscript cohort.
`docs/lite/results/README.md` is retained as a historical recording-contract input;
its links and commands for additional public cohorts refer outside this archive.
Use the verifier and manuscript regeneration command above for this review copy.

The code and synthetic data use the included MIT license. Third-party ACL style
and bibliography attribution are retained. Native checkpoints and dependencies
retain their respective upstream licenses and are not redistributed here.
'''


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text())


def json_bytes(value) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode()


def native_cohorts(manifest):
    return {Path(v['native_sources']['path']).parent for row in manifest['passes']
            for v in row['provenance'].values() if 'native_sources' in v}


def inventory(root: Path, manifest: dict) -> tuple[set[str], set[str]]:
    """Explicit artifact boundary; never traverse caches, Git or model stores."""
    software = {'LICENSE', 'pyproject.toml', 'uv.lock',
                'paper/main.tex', 'paper/appendix.tex', 'paper/submission.tex',
                'paper/model-provenance.tex',
                'paper/.latexmkrc', 'paper/references.bib', 'paper/acl.sty', 'paper/acl_natbib.bst',
                'paper/notes/audit_record.json', 'paper/notes/audit_summary.md',
                'paper/notes/pricing.md', 'docs/lite/PROTOCOL.md', 'docs/lite/results/README.md',
                'scripts/paper/verify_submission.py'}
    for directory, patterns in [('src', ['*.py']), ('scripts/lite', ['*.py']),
                                ('paper/analysis', ['*.py', '*.json']),
                                ('paper/generated', ['*.tex']), ('paper/figures', ['*.pdf', '*.json'])]:
        for pattern in patterns:
            software.update(str(p.relative_to(root)) for p in (root/directory).rglob(pattern)
                            if '__pycache__' not in p.parts and not p.name.endswith('.shadow.md'))
    # These two validators are imported by the shared local-analysis module, even
    # though their additional public-leaderboard cohorts are not manuscript inputs.
    software.update({'scripts/runpod/winnow_report.py', 'scripts/runpod/decision20_report.py',
                     'scripts/runpod/record.py', 'scripts/runpod/decision_record.py',
                     'scripts/runpod/input_audit.py', 'scripts/runpod/cohort.py'})
    data = {MANUSCRIPT, PUBLIC_LOCAL, 'docs/research/trajectory-value/analysis.json'}
    data.update(str(p.relative_to(root)) for p in (root/'data/lite/v1').glob('*.json'))
    for row in manifest['passes']:
        if len(row['provenance']) != 15:
            raise ValueError('The manuscript must contain 15 settings per pass')
        for source in row['provenance'].values():
            data.update(str(Path(source['run'])/name) for name in ('run.json', 'episodes.json', 'events.jsonl'))
            data.add(source['published_report']['path'])
            for key in ('input_audit', 'native_sources', 'weights'):
                if key in source:
                    data.add(source[key]['path'])
    if len({v['run'] for row in manifest['passes'] for v in row['provenance'].values()}) != 45:
        raise ValueError('The bundle requires exactly 45 distinct manuscript recordings')
    for cohort in native_cohorts(manifest) | {Path('runs/hosted-api-repeats-20261003')}:
        data.update(str(p.relative_to(root)) for p in (root/cohort).glob('*-requirements.txt'))
    # Any future manuscript source input must be included explicitly or fail here.
    for path in manifest['sources_sha256']:
        if path not in software | data:
            raise ValueError(f'Manifest input missing from package inventory: {path}')
    if software & data:
        raise ValueError('Software and data inventories overlap')
    for path in software | data:
        if Path(path).is_absolute() or '..' in Path(path).parts or not (root/path).resolve().is_relative_to(root.resolve()):
            raise ValueError(f'Artifact input escapes repository boundary: {path}')
        if not (root/path).is_file() or (root/path).is_symlink():
            raise ValueError(f'Missing or symbolic-link artifact input: {path}')
    for path in software:
        if Path(path).suffix != '.tex':
            continue
        contents = '\n'.join(re.sub(r'(?<!\\)%.*$', '', line)
                             for line in (root/path).read_text().splitlines())
        for included in re.findall(r'\\(?:input|include)\{([^}]+)\}', contents):
            # LaTeX resolves these inputs from the compilation working directory,
            # including commands inside an already included TeX file.
            dependency = Path('paper') / included
            if not dependency.suffix:
                dependency = dependency.with_suffix('.tex')
            if str(dependency) not in software:
                raise ValueError(f'Manuscript include missing from package: {dependency}')
    return software, data


def prune_local_summary(value: dict, names: set[str], hosted: set[str]) -> dict:
    """A declared cohort projection, not a change to any retained result."""
    value['policy']['settings'] = [s for s in value['policy']['settings'] if s['name'] in names]
    for key in ('standalone', 'systems'):
        value[key] = {name: value[key][name] for name in value[key] if name in names}
    for key in ('hosted', 'provenance'):
        value[key] = {name: row for name, row in value[key].items() if name in names | hosted}
    verification = value['verification']
    if 'nominal_recorded_gaps_points' in verification:
        verification['nominal_recorded_gaps_points'] = {
            name: gap for name, gap in verification['nominal_recorded_gaps_points'].items()
            if name in names | hosted}
        verification['max_nominal_recorded_gap_points'] = max(verification['nominal_recorded_gaps_points'].values())
    for row in verification['passes']:
        row['nominal_recorded_gaps_points'] = {
            name: gap for name, gap in row['nominal_recorded_gaps_points'].items()
            if name in names | hosted}
        row['standalone_partition_checks'] = 8 * len(row['nominal_recorded_gaps_points'])
        row['max_nominal_recorded_gap_points'] = max(row['nominal_recorded_gaps_points'].values())
    verification['standalone_partition_checks'] = sum(row['standalone_partition_checks']
                                                       for row in verification['passes'])
    value['scope_annotation'] = (
        'Anonymous review copy: original standalone summary projected onto the fixed manuscript cohort. '
        'Retained scores are unchanged. The final three-pass hosted and hybrid results are in '
        'docs/research/manuscript-three-pass/analysis.json.')
    return value


def redact_text(text: str) -> str:
    replacements = {
        'https://github.com/JacobLinCool/StreamDecisionBench': 'https://example.invalid/anonymous-artifact',
        'jacob.cs14@nycu.edu.tw': 'anonymous@example.invalid',
        'takalawang.cs14@nycu.edu.tw': 'anonymous@example.invalid',
        'Jhen-Ke Lin': 'Anonymous author', 'Chung Chun Wang': 'Anonymous author',
        'National Yang Ming Chiao Tung University': 'Affiliation withheld for anonymous review',
        'NYCU lab host EVA-241-125': 'anonymous laboratory host',
        'NYCU lab EVA-241-125': 'anonymous laboratory host',
        '/eva_data1/takala/sdb-pro6000': '/anonymous-host',
        '/Users/jacoblincool': '/anonymous-client',
        'JacobLinCool': 'Anonymous authors',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    # Recording-time own-project commit IDs identify its authors; native upstream
    # revision and model identifiers remain untouched.
    text = re.sub(r'("benchmark_commit"\s*:\s*)"[0-9a-f]{40}"',
                  r'\1"withheld-for-anonymous-review"', text)
    return text


def redact_event_metadata(raw: bytes, path: str) -> bytes:
    """Allow only native model-cache paths to change inside measurement logs.

    Text replacement preserves every unrelated byte; the independent parsed
    comparison prevents the same path string in a measured input/output from
    being redacted accidentally. Unknown identifying fields fail closed.
    """
    text = raw.decode()
    if not FORBIDDEN_CONTENT.search(text):
        return raw
    lines = []
    for line in text.splitlines(keepends=True):
        if not FORBIDDEN_CONTENT.search(line):
            lines.append(line)
            continue
        expected = deepcopy(json.loads(line))
        replacements = {}
        for field in expected.get('usage', {}).get('native_fields', {}).values():
            model = field.get('model', {})
            source = model.get('source')
            if isinstance(source, str) and source.startswith('/eva_data1/takala/sdb-pro6000/'):
                model['source'] = redact_text(source)
                replacements[source] = model['source']
        updated = line
        for original, redacted in replacements.items():
            updated = updated.replace(json.dumps(original), json.dumps(redacted))
        if FORBIDDEN_CONTENT.search(updated) or json.loads(updated) != expected:
            raise ValueError(f'Identity in a measurement or unapproved event metadata field: {path}')
        lines.append(updated)
    return ''.join(lines).encode()


def transformed_inputs(root: Path, paths: set[str], manifest: dict):
    base, originals = {}, {}
    local_names = set(manifest['openweight']['policy']['manuscript_settings'])
    hosted = set(manifest['hosted'])
    changed = []
    for path in sorted(paths):
        raw = (root/path).read_bytes()
        originals[path] = sha(raw)
        if Path(path).name == 'events.jsonl':
            base[path] = redact_event_metadata(raw, path)
            if base[path] != raw:
                changed.append(path)
            continue
        if Path(path).name == 'episodes.json' or path.startswith('data/lite/v1/'):
            if FORBIDDEN_CONTENT.search(raw.decode()):
                raise ValueError(f'Identity found in immutable measurement input: {path}')
            base[path] = raw
            continue
        if path == PUBLIC_LOCAL:
            raw = json_bytes(prune_local_summary(json.loads(raw), local_names, hosted))
        if Path(path).suffix in TEXT_SUFFIXES or Path(path).name in ('LICENSE', '.latexmkrc'):
            text = redact_text(raw.decode())
            if path == 'paper/.latexmkrc':
                text = text.replace("@default_files = ('submission.tex', 'preprint.tex');", "@default_files = ('submission.tex');")
                text = text.replace('`latexmk` builds both versions of main.tex: submission.pdf (anonymous review) and preprint.pdf.',
                                    '`latexmk` builds submission.pdf, the anonymous review version of main.tex.')
            if path == 'pyproject.toml':
                text = re.sub(r'authors = \[.*?\]\n', 'authors = [{ name = "Anonymous authors" }]\n', text, flags=re.S)
                text = re.sub(r'\[project.urls\]\nRepository = .*?\n', '', text)
            if path == 'paper/main.tex':
                text = re.sub(r'\\author\{.*?(?=\n\\begin\{document\})',
                              r'\\author{Anonymous ACL submission}\n', text, flags=re.S)
                text = re.sub(r'\\ifnum\\pdfstrcmp\{\\SDBVersion\}\{review\}=0 .*?\\fi',
                              r'\\hypersetup{pdfauthor={}}\n\\pdfinfoomitdate=1', text)
            raw = text.encode()
        base[path] = raw
        if sha(raw) != originals[path]:
            changed.append(path)
    return base, originals, changed


def remap_receipts(base: dict[str, bytes], originals: dict[str, str]):
    """Resolve the finite SHA dependency graph without skipping any checks.

    Each round is rendered from the sanitized base, so old-to-new receipt maps
    remain unambiguous. A cycle/self-checksum or nonconvergent graph fails closed.
    """
    current = dict(base)
    text_paths = [p for p in base if Path(p).suffix in TEXT_SUFFIXES
                  and Path(p).name not in ('events.jsonl', 'episodes.json')
                  and not p.startswith('data/lite/v1/')]
    for _ in range(20):
        mapping = {}
        for path, old in originals.items():
            new = sha(current[path])
            if old in mapping and mapping[old] != new:
                raise ValueError('Identical original bytes received incompatible transformations')
            mapping[old] = new
        updated = dict(base)
        for path in text_paths:
            updated[path] = HEX_SHA.sub(lambda match: mapping.get(match[0], match[0]), base[path].decode()).encode()
        if all(updated[path] == current[path] for path in updated):
            return updated
        current = updated
    raise ValueError('Checksum dependency graph did not converge')


def scan(files: dict[str, bytes]):
    for path, raw in files.items():
        if any(part in {'.git', '.cache', '__pycache__', 'legacy'} for part in Path(path).parts):
            raise ValueError(f'Forbidden artifact path: {path}')
        if Path(path).name.startswith('.env') or path.endswith(('.shadow.md', '.safetensors', '.pt', '.gguf')):
            raise ValueError(f'Private or weight artifact included: {path}')
        if Path(path).suffix in TEXT_SUFFIXES or Path(path).name in ('LICENSE', '.latexmkrc'):
            if FORBIDDEN_CONTENT.search(raw.decode()):
                raise ValueError(f'Identifying text remains in review copy: {path}')
            if CREDENTIAL_CONTENT.search(raw.decode()):
                raise ValueError(f'Possible credential found: {path}')


def write_zip(path: Path, files: dict[str, bytes], names: set[str]):
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(names):
            info = zipfile.ZipInfo(f'{ARCHIVE_ROOT}/{name}', date_time=(2026, 10, 4, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, files[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    if path.stat().st_size > LIMIT_BYTES:
        raise ValueError(f'{path.name} exceeds the 200 MB submission limit')


def build(root: Path, output: Path):
    manifest = read_json(root/MANUSCRIPT)
    software, data = inventory(root, manifest)
    for path, expected in manifest['sources_sha256'].items():
        if sha((root/path).read_bytes()) != expected:
            raise ValueError(f'Unfrozen manuscript analysis: {path}; regenerate first')
    base, originals, changed = transformed_inputs(root, software | data, manifest)
    files = remap_receipts(base, originals)
    files['README.md'] = README.encode()
    software.add('README.md')
    scan(files)
    receipt = {
        'schema_version': 1, 'scope': 'anonymous manuscript review copy',
        'dataset_hash': manifest['passes'][0]['hosted_reports']['Luna']['dataset_hash'],
        'settings_per_pass': 15, 'passes_per_setting': 3, 'complete_recordings': 45,
        'redaction': 'Identifying metadata only; event values unchanged except native model.source cache paths. Frozen episodes and public dataset remain byte-identical. Dependent SHA-256 receipts are recomputed.',
        'measurement_files_unchanged': sorted(p for p in originals if
            (Path(p).name in ('events.jsonl', 'episodes.json') or p.startswith('data/lite/v1/'))
            and originals[p] == sha(files[p])),
        'event_metadata_redactions': {p: ['usage.native_fields.<question>.model.source']
                                     for p in changed if Path(p).name == 'events.jsonl'},
        'files': {p: {'sha256': sha(content), 'bytes': len(content), 'archive': 'software.zip' if p in software else 'data.zip'}
                  for p, content in sorted(files.items())},
    }
    files['ARTIFACT_MANIFEST.json'] = json_bytes(receipt)
    software.add('ARTIFACT_MANIFEST.json')
    output.mkdir(parents=True, exist_ok=True)
    for name, entries in [('software.zip', software), ('data.zip', data)]:
        write_zip(output/name, files, entries)
    result = {'recordings': 45, 'settings': 15, 'files': len(files),
              'metadata_files_transformed': len(changed),
              'archives': {name: {'bytes': (output/name).stat().st_size, 'sha256': sha((output/name).read_bytes())}
                           for name in ('software.zip', 'data.zip')}}
    (output/'packaging-result.json').write_bytes(json_bytes(result))
    return result


def extract_and_verify(output: Path, python: str, reproduce: bool, latex: bool = False):
    target = output/'verified-extraction'
    if target.exists():
        raise ValueError(f'Validation destination already exists; use a fresh output directory: {target}')
    target.mkdir()
    for name in ('software.zip', 'data.zip'):
        with zipfile.ZipFile(output/name) as archive:
            for info in archive.infolist():
                path = Path(info.filename)
                if path.is_absolute() or '..' in path.parts or path.parts[0] != ARCHIVE_ROOT:
                    raise ValueError('Unsafe archive member')
            archive.extractall(target)
    artifact = target/ARCHIVE_ROOT
    environment = {name: os.environ[name] for name in
                   ('PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'LC_CTYPE', 'SYSTEMROOT')
                   if name in os.environ}
    environment['MPLCONFIGDIR'] = str(output/'verification-cache/matplotlib')
    command = [python, 'scripts/paper/verify_submission.py']
    if reproduce:
        command.append('--reproduce')
    with (output/'validation.log').open('w') as log:
        subprocess.run(command, cwd=artifact, env=environment,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    result = read_json(artifact/'validation-result.json')
    result['service_credentials_in_environment'] = False
    if latex:
        with (output/'latex-validation.log').open('w') as log:
            subprocess.run(['latexmk', 'submission.tex'], cwd=artifact/'paper',
                           env=environment, stdout=log, stderr=subprocess.STDOUT, check=True)
        pdf = artifact/'paper/submission.pdf'
        if not pdf.is_file():
            raise ValueError('Extracted manuscript compiled without producing submission.pdf')
        shutil.copyfile(pdf, output/'submission.pdf')
        result['latex'] = {'compiled_from_extracted_sources': True, 'bytes': pdf.stat().st_size,
                           'sha256': sha(pdf.read_bytes())}
    (output/'validation-result.json').write_bytes(json_bytes(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--out', type=Path, default=ROOT/'output/submission-2026-10-04')
    parser.add_argument('--verify', action='store_true', help='Extract both archives and validate the independent copy')
    parser.add_argument('--reproduce', action='store_true', help='Also regenerate all manuscript figures and number/table macros')
    parser.add_argument('--latex', action='store_true', help='Also compile the extracted anonymous manuscript and export submission.pdf')
    args = parser.parse_args()
    if (args.verify or args.reproduce or args.latex) and (args.out/'verified-extraction').exists():
        raise ValueError('A validated extraction already exists; select a fresh output directory')
    result = build(args.root.resolve(), args.out.resolve())
    print(json.dumps(result, indent=2), flush=True)
    if args.verify or args.reproduce or args.latex:
        verified = extract_and_verify(args.out.resolve(), sys.executable, args.reproduce, args.latex)
        print(json.dumps(verified, indent=2), flush=True)


if __name__ == '__main__':
    main()
