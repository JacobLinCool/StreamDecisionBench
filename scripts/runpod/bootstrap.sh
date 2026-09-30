#!/usr/bin/env bash
set -euo pipefail
cd /workspace/sdb
export HF_HOME=/workspace/hf
export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=4
export VLLM_FLASHINFER_MOE_BACKEND=masked_gemm
export VLLM_ENABLE_V1_MULTIPROCESSING=0
mkdir -p /workspace/results/logs
python3 -m pip install --target /workspace/tools uv
export PATH="/workspace/tools/bin:$PATH"
uv python install 3.12
uv venv --python 3.12 /workspace/bench-env
uv pip install --python /workspace/bench-env/bin/python -e . /workspace/laya
uv venv --python 3.12 /workspace/djev-env
uv pip install --python /workspace/djev-env/bin/python \
  'https://wheels.vllm.ai/1ee7f78e806b5e9b7476c74edf453b58fe108157/vllm-0.30.1rc1.dev370%2Bg1ee7f78e8-cp38-abi3-manylinux_2_28_x86_64.whl'
uv pip freeze --python /workspace/bench-env/bin/python > /workspace/results/bench-requirements.txt
uv pip freeze --python /workspace/djev-env/bin/python > /workspace/results/djev-requirements.txt
nvidia-smi -q > /workspace/results/nvidia-smi.txt
/workspace/djev-env/bin/python /workspace/sdb/scripts/runpod/cohort.py
