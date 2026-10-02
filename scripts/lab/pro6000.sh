#!/usr/bin/env bash
# Rerun every open-weight SDB setting, plus Kev-9B and Kev-27B, on one lab RTX PRO 6000 (EVA-241-125).
# Same recorders, pinned checkpoints, upstream commits and frozen RunPod requirements; only host paths differ.
# ponytail: settings run sequentially per GPU; a second supervisor on the other RTX PRO 6000 (own SDB_OUT) halves wall time.
# Run on the host:  setsid nohup scripts/lab/pro6000.sh <nvidia-smi index> [setting ...] > $SDB_LAB/supervisor.log 2>&1 &
set -uo pipefail
GPU=${1:?nvidia-smi index of an idle RTX PRO 6000}; shift
SETTINGS=${*:-kev-9b kev-27b kev-4b nimble-9b semif-qwen35-4b laya-english laya-typed-decisions laya-multilingual djev-diffusiongemma}
B=${SDB_LAB:-/eva_data1/takala/sdb-pro6000}
SDB=$B/sdb UP=$B/upstream OUT=${SDB_OUT:-$B/results} PLAN=$B/sdb/scripts/lab/pro6000-plan.json
R1=$SDB/runs/runpod-openweight-20260930 R2=$SDB/runs/runpod-openweight-20260930-round2
DIFFUSION_REVISION=f7f5b7f5fa82ffc52addd066915886d497f5517b
# The root disk is full: every cache and temporary file stays on the data disk.
export HF_HOME=$B/hf UV_CACHE_DIR=$B/uv-cache UV_PYTHON_INSTALL_DIR=$B/uv-python XDG_CACHE_HOME=$B/cache \
  TRITON_CACHE_DIR=$B/cache/triton VLLM_CACHE_ROOT=$B/cache/vllm TMPDIR=$B/tmp
export TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=4 PYTHONUNBUFFERED=1
export HF_HUB_DISABLE_XET=1   # anonymous Xet downloads stalled at 0 MB/s on this host; plain HTTPS ran at ~60 MB/s
export CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=$GPU
export VLLM_FLASHINFER_MOE_BACKEND=masked_gemm VLLM_ENABLE_V1_MULTIPROCESSING=0
export SDB_MODELS=$B/models
export SDB_MEASUREMENT_LOCATION="NYCU lab host EVA-241-125, one RTX PRO 6000 Blackwell Server Edition (96 GB); benchmark and model on the same GPU host"
UV=${UV:-$HOME/.local/bin/uv}
mkdir -p "$OUT/logs" "$OUT/runs" "$SDB_MODELS" "$UP" "$TMPDIR" "$B/envs"

log() { echo "$(date -u +%FT%TZ) $*" >> "$OUT/status.log"; }

clone() {  # dir github-repo commit
  [ -d "$UP/$1/.git" ] || git clone -q "https://github.com/$2" "$UP/$1"
  [ "$(git -C "$UP/$1" rev-parse HEAD)" = "$3" ] || git -C "$UP/$1" checkout -q "$3"
}

env_from() {  # name frozen-requirements [uv pip args]
  local name=$1 env=$B/envs/$1 req=$2; shift 2
  [ -f "$env/.ready" ] && return 0
  rm -rf "$env"
  "$UV" venv -q --python 3.12 "$env" || return 1
  sed -e "s#file:///workspace/sdb#file://$SDB#" -e "s#file:///workspace/laya#file://$UP/laya#" \
      -e "s#file:///workspace/upstream/semif#file://$UP/semif#" "$req" > "$OUT/$name-requirements.in.txt"
  "$UV" pip install -q --python "$env/bin/python" -r "$OUT/$name-requirements.in.txt" "$@" > "$OUT/logs/env-$name.log" 2>&1 \
    || { rm -rf "$env"; return 1; }
  "$UV" pip freeze --python "$env/bin/python" > "$OUT/$name-requirements.txt" && touch "$env/.ready"
}
CU128=(--extra-index-url https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match)

gpu_idle() {  # another user's process on our card would contaminate latency
  nvidia-smi -i "$GPU" --query-compute-apps=pid,used_memory --format=csv,noheader > "$OUT/logs/$1.gpu-before.txt"
  [ "$(nvidia-smi -i "$GPU" --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 1000 ]
}

stop() {  # process-group leader pid; never pkill -f
  kill -TERM -- "-$1" 2>/dev/null
  for _ in $(seq 30); do kill -0 "$1" 2>/dev/null || return 0; sleep 1; done
  kill -KILL -- "-$1" 2>/dev/null
}

wait_http() {  # url seconds pid
  for _ in $(seq $(($2 / 5))); do
    kill -0 "$3" 2>/dev/null || return 1
    curl -sf -m 5 -o /dev/null "$1" && return 0
    sleep 5
  done
  return 1
}

native() {  # Kev, Nimble and SemIf: decision_cohort.py --prepare, then decision_record.py, as in round 2
  local id=$1 env=native req=$R2/native-requirements.txt
  case $id in semif-*) env=semif req=$R2/semif-requirements.txt ;; esac
  env_from "$env" "$req" "${CU128[@]}" || return 1
  local -a run=(env PYTHONPATH="$UP/kev:$UP/nimble:$UP/semif/src" KEV_PREFIX_CACHE=0 KEV_DATE_FACTS=0)
  # A finished prepare is reused (hashing 51 GB twice on this HDD takes ~30 min); decision_record.py rechecks the revision.
  [ -f "$SDB_MODELS/$id/prepared.json" ] || "${run[@]}" timeout -k 30 7200 "$B/envs/$env/bin/python" \
    "$SDB/scripts/runpod/decision_cohort.py" --plan "$PLAN" --prepare "$id" > "$OUT/logs/$id.prepare.log" 2>&1 || return 1
  cp "$SDB_MODELS/$id/prepared.json" "$OUT/$id.prepared.json"
  gpu_idle "$id" || { log "$id gpu busy, not recorded"; return 1; }
  "${run[@]}" HF_HUB_OFFLINE=1 timeout -k 30 3600 "$B/envs/$env/bin/python" "$SDB/scripts/runpod/decision_record.py" \
    --plan "$PLAN" --setting "$id" --out "$OUT/runs/$id" > "$OUT/logs/$id.record.log" 2>&1
}

laya() {  # id model revision; round 1 recorder, which loads the pinned checkpoint itself
  env_from bench "$R1/bench-requirements.txt" || return 1
  gpu_idle "$1" || { log "$1 gpu busy, not recorded"; return 1; }
  timeout -k 30 3600 "$B/envs/bench/bin/python" "$SDB/scripts/runpod/record.py" --backend laya \
    --model "$2" --revision "$3" --out "$OUT/runs/$1" > "$OUT/logs/$1.log" 2>&1
}

djev() {  # round 1: vLLM DiffusionGemma engine + DJev structured server + record.py
  env_from bench "$R1/bench-requirements.txt" && env_from djev "$R1/djev-requirements.txt" || return 1
  local py=$B/envs/djev/bin/python path engine server rc
  path=$("$py" -c "from huggingface_hub import snapshot_download; print(snapshot_download('google/diffusiongemma-26B-A4B-it', revision='$DIFFUSION_REVISION', ignore_patterns=['*.msgpack','*.h5','*.bin','original/*']))" 2>> "$OUT/logs/download.log" | tail -1) || return 1
  gpu_idle djev-diffusiongemma || { log "djev gpu busy, not recorded"; return 1; }
  setsid "$B/envs/djev/bin/vllm" serve "$path" --served-model-name dgemma --host 127.0.0.1 --port 18010 \
    --enforce-eager --language-model-only --attention-backend TRITON_ATTN --gpu-memory-utilization 0.9 \
    --max-model-len 16384 --max-num-seqs 32 --max-logprobs 32 --enable-prefix-caching \
    --diffusion-config '{"canvas_length":128}' > "$OUT/logs/vllm.log" 2>&1 &
  engine=$!
  if wait_http http://127.0.0.1:18010/health 1800 "$engine"; then   # 52 GB load from a slow HDD
    setsid "$py" "$UP/djev/structured_server.py" --upstream http://127.0.0.1:18010 --model dgemma \
      --tokenizer "$path" --canvas 128 --host 127.0.0.1 --port 18011 > "$OUT/logs/djev-server.log" 2>&1 &
    server=$!
    wait_http http://127.0.0.1:18011/v1/models 180 "$server" \
      && timeout -k 30 3600 "$B/envs/bench/bin/python" "$SDB/scripts/runpod/record.py" --backend djev --model dgemma \
        --revision "$DIFFUSION_REVISION" --endpoint http://127.0.0.1:18011 \
        --out "$OUT/runs/djev-diffusiongemma" > "$OUT/logs/djev-diffusiongemma.log" 2>&1
    rc=$?
    stop "$server"
  else
    rc=1
  fi
  stop "$engine"
  return $rc
}

log "start gpu=$GPU settings=[$SETTINGS] pid=$$"
nvidia-smi -i "$GPU" --query-gpu=name --format=csv,noheader | grep -q "RTX PRO 6000" || { log "gpu $GPU is not an RTX PRO 6000"; exit 1; }
clone kev jaredpalmer/kev 90512f1c517d977741f2104470a40635408236c9
clone nimble bespokelabsai/nimble 62076b4f2d365b5879dafcf7f6dd072a1fe76df7
clone semif TheoLeeCJ/SemIf-OpenJev 23cf1f39fc9534fe81437200959b6dfc7106e45a
clone laya NandhaKishorM/laya 6d942c92081fbc139e736bbd9ac0023223c29b7f
clone djev mmastrac/djev e5841cf41e9211608e698492658685c36e24e77a
{ echo "sdb $(git -C "$SDB" rev-parse HEAD) + sdb-local.diff"
  for r in kev nimble semif laya djev; do echo "$r $(git -C "$UP/$r" rev-parse HEAD)"; done
  echo "host $(hostname) driver $(nvidia-smi --query-gpu=driver_version --format=csv,noheader -i "$GPU")"
} > "$OUT/source-provenance.txt"
git -C "$SDB" diff HEAD > "$OUT/sdb-local.diff"
nvidia-smi -q -i "$GPU" > "$OUT/nvidia-smi.txt"

for id in $SETTINGS; do
  if [ -f "$OUT/runs/$id/run.json" ] && grep -q '"status": "complete"' "$OUT/runs/$id/run.json"; then
    log "$id already complete, skipped"; continue
  fi
  # The runtime refuses an existing output directory; a partial pass is kept aside, never scored.
  [ -e "$OUT/runs/$id" ] && mv "$OUT/runs/$id" "$OUT/runs/$id.partial-$(date +%s)"
  # Two supervisors (one per GPU) may share $B: a setting runs in at most one of them.
  mkdir -p "$B/claims"; mkdir "$B/claims/$id" 2>/dev/null || { log "$id claimed by another supervisor, skipped"; continue; }
  log "$id begin"
  case $id in
    laya-english) laya "$id" convaiinnovations/laya 55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851 ;;
    laya-typed-decisions) laya "$id" convaiinnovations/laya-typed-decisions 1a793eb568e6718f15941d08f85432581df534e3 ;;
    laya-multilingual) laya "$id" convaiinnovations/laya-multilingual e4e9ddf21a7b1903b7acffd8814ad4307bf63a67 ;;
    djev-diffusiongemma) djev ;;
    *) native "$id" ;;
  esac
  rc=$?
  nvidia-smi -i "$GPU" --query-compute-apps=pid,used_memory --format=csv,noheader > "$OUT/logs/$id.gpu-after.txt"
  rmdir "$B/claims/$id"
  log "$id end exit=$rc"
done
log "finished"
