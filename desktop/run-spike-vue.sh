#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"
N="C:/Users/su/.workbuddy/binaries/node/versions/22.22.2-6/node.exe"
export RENPYBOX_SIDECAR_PORT="${RENPYBOX_SIDECAR_PORT:-9712}"
export RENPYBOX_WEB_PORT="${RENPYBOX_WEB_PORT:-5274}"
SIDECAR="$RENPYBOX_SIDECAR_PORT"
WEB="http://127.0.0.1:$RENPYBOX_WEB_PORT"
OUT="${1:-perf-result-vue.json}"
echo "Vue 对照版：sidecar=$SIDECAR web=$RENPYBOX_WEB_PORT"
( cd sidecar && ./.venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port "$SIDECAR" --log-level warning ) &
SIDECAR_PID=$!
for i in $(seq 1 40); do curl -sf "http://127.0.0.1:$SIDECAR/health" >/dev/null 2>&1 && break; sleep 0.5; done
"$N" node_modules/vite/bin/vite.js --config renderer-vue/vite.config.ts >/tmp/vite-vue.log 2>&1 &
VITE_PID=$!
for i in $(seq 1 60); do curl -sf "$WEB/" >/dev/null 2>&1 && break; sleep 0.5; done
curl -sf "$WEB/" >/dev/null || { echo "vite 未就绪"; tail -20 /tmp/vite-vue.log; kill $SIDECAR_PID $VITE_PID 2>/dev/null; exit 1; }
unset ELECTRON_RUN_AS_NODE
VITE_DEV_SERVER_URL="$WEB" PERF_OUT="$OUT" ./node_modules/electron/dist/electron.exe main/perf-gate.js
kill $SIDECAR_PID $VITE_PID 2>/dev/null
wait $SIDECAR_PID 2>/dev/null; wait $VITE_PID 2>/dev/null
