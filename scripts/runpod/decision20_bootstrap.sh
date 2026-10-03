#!/usr/bin/env bash
set -euo pipefail
mkdir -p /workspace/results/logs
exec > /workspace/results/bootstrap.log 2>&1
export HF_HOME=/workspace/hf
export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=8
nvidia-smi -q > /workspace/results/nvidia-smi.txt
python3 -m venv --system-site-packages /workspace/bench-env
/workspace/bench-env/bin/pip install /workspace/sdb transformers==5.17.0 peft==0.21.0 accelerate==1.15.0 sentencepiece==0.2.2 pillow==12.3.0
/workspace/bench-env/bin/pip freeze > /workspace/results/bench-requirements.txt
exec /workspace/bench-env/bin/python /workspace/sdb/scripts/runpod/decision20_cohort.py
