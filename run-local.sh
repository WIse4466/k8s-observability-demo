#!/usr/bin/env bash
# 本機一次起四支程式（不需要 Docker / Kubernetes）
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python
mkdir -p .logs

: "${BUG_SILENT_DISCOUNT:=false}"
: "${BUG_N_PLUS_ONE:=false}"
: "${LEAK_KB_PER_REQUEST:=0}"
export BUG_SILENT_DISCOUNT BUG_N_PLUS_ONE LEAK_KB_PER_REQUEST

echo "故障開關: SILENT_DISCOUNT=$BUG_SILENT_DISCOUNT N_PLUS_ONE=$BUG_N_PLUS_ONE LEAK_KB=$LEAK_KB_PER_REQUEST"

SERVICE_NAME=pricing $PY -m uvicorn pricing.main:app --port 8002 --log-level warning > .logs/pricing.log 2>&1 &
SERVICE_NAME=catalog $PY -m uvicorn catalog.main:app --port 8001 --log-level warning > .logs/catalog.log 2>&1 &
SERVICE_NAME=gateway $PY -m uvicorn gateway.main:app --port 8000 --log-level warning > .logs/gateway.log 2>&1 &
sleep 2
$PY loadgen/main.py > .logs/loadgen.log 2>&1 &

echo "起來了。log 在 demo/.logs/，用 ./stop-local.sh 停掉"
