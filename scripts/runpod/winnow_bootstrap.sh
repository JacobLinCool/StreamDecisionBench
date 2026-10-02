#!/usr/bin/env bash
# Execute on a dedicated RunPod CUDA 12.8+ development image after uploading this repository.
set -euo pipefail
ROOT=/workspace/sdb
OUT=/workspace/results
mkdir -p "$OUT" /workspace/models
exec > "$OUT/prepare.log" 2>&1
nvidia-smi > "$OUT/nvidia-smi.txt"
export CUDACXX=/usr/local/cuda/bin/nvcc
export PATH=/usr/local/cuda/bin:$PATH
"$CUDACXX" --version > "$OUT/nvcc.txt"
apt-get update -qq
apt-get install -y -qq cmake build-essential libssl-dev python3-venv git curl rsync
python3 -m venv /workspace/bench-env
/workspace/bench-env/bin/pip install "$ROOT"
/workspace/bench-env/bin/pip freeze > "$OUT/bench-requirements.txt"
git clone https://github.com/EldanRing/winnow-inference.git /workspace/winnow
python3 - <<'PY'
import hashlib,json,pathlib,subprocess
plan=json.loads(pathlib.Path('/workspace/sdb/scripts/runpod/winnow-plan.json').read_text())
subprocess.run(['git','-C','/workspace/winnow','checkout','--detach',plan['upstream_commit']],check=True)
for setting in plan['settings']:
    path=pathlib.Path('/workspace/models')/setting['file']
    url=f"https://huggingface.co/{setting['model']}/resolve/{setting['revision']}/gguf/{setting['file']}"
    subprocess.run(['curl','--fail','--location','--retry','3',url,'-o',str(path)],check=True)
    with path.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=setting['sha256']:
            raise ValueError('Downloaded weight checksum mismatch')
PY
python3 /workspace/winnow/scripts/build.py --backend cuda --cuda-arch 120 --jobs 16 > "$OUT/build.log" 2>&1
exec /workspace/bench-env/bin/python "$ROOT/scripts/runpod/winnow_cohort.py"
