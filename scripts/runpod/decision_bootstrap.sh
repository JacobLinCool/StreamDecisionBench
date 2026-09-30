#!/usr/bin/env bash
set -euo pipefail
cd /workspace/sdb
mkdir -p /workspace/results/logs /opt/sdb-models /opt/sdb-hf
export HF_HOME=/opt/sdb-hf
export UV_CACHE_DIR=/opt/sdb-uv-cache
export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=4
python3 -m pip install --target /opt/sdb-tools uv==0.11.13
export PATH="/opt/sdb-tools/bin:$PATH"
uv python install 3.12
uv venv --python 3.12 /opt/sdb-native-env
uv pip install --python /opt/sdb-native-env/bin/python torch==2.8.0 --index-url https://download.pytorch.org/whl/cu128
uv pip install --python /opt/sdb-native-env/bin/python -e . \
  torch==2.8.0 transformers==5.17.0 peft==0.21.0 accelerate==1.15.0 \
  sentencepiece==0.2.2 pillow==12.3.0 fastapi uvicorn flash-linear-attention==0.5.2
uv venv --python 3.12 /opt/sdb-semif-env
uv pip install --python /opt/sdb-semif-env/bin/python torch==2.10.0 --index-url https://download.pytorch.org/whl/cu128
uv pip install --python /opt/sdb-semif-env/bin/python -e . /workspace/upstream/semif flash-linear-attention==0.5.2
uv pip freeze --python /opt/sdb-native-env/bin/python > /workspace/results/native-requirements.txt
uv pip freeze --python /opt/sdb-semif-env/bin/python > /workspace/results/semif-requirements.txt
nvidia-smi -q > /workspace/results/nvidia-smi.txt
df -h > /workspace/results/filesystems.txt
exec /opt/sdb-native-env/bin/python scripts/runpod/decision_cohort.py --plan /workspace/plan.json
