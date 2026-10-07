#!/usr/bin/env bash
# M0 spike 一键联调：sidecar + vite + 无头性能门禁，全在同一个上下文里跑。
set -u
cd "$(dirname "$0")"

N="C:/Users/su/.workbuddy/binaries/node/versions/22.22.2-6/node.exe"
export RENPYBOX_SIDECAR_PORT="${RENPYBOX_SIDECAR_PORT:-9712}"
export RENPYBOX_WEB_PORT="${RENPYBOX_WEB_PORT:-5273}"
SIDECAR="$RENPYBOX_SIDECAR_PORT"
WEB="http://127.0.0.1:$RENPYBOX_WEB_PORT"
OUT="${1:-perf-result-react.json}"

echo "端口 sidecar=$SIDECAR  web=$RENPYBOX_WEB_PORT"
echo "--- 启动 sidecar ---"
( cd sidecar && RENPYBOX_SIDECAR_PORT="$SIDECAR" ./.venv/Scripts/python.exe main.py --bench ) &
SIDECAR_PID=$!

for i in $(seq 1 40); do
  curl -sf "http://127.0.0.1:$SIDECAR/health" >/dev/null 2>&1 && break
  sleep 0.5
done
curl -sf "http://127.0.0.1:$SIDECAR/health" || { echo "sidecar 未就绪"; kill $SIDECAR_PID 2>/dev/null; exit 1; }
echo

echo "--- 启动 vite ---"
"$N" node_modules/vite/bin/vite.js --config renderer/vite.config.ts >/tmp/vite.log 2>&1 &
VITE_PID=$!
for i in $(seq 1 60); do
  curl -sf "$WEB/" >/dev/null 2>&1 && break
  sleep 0.5
done
curl -sf "$WEB/" >/dev/null || { echo "vite 未就绪，见 /tmp/vite.log"; kill $SIDECAR_PID $VITE_PID 2>/dev/null; exit 1; }
echo

echo "--- 跑性能门禁（offscreen，不弹窗）---"
# 环境里预置了 ELECTRON_RUN_AS_NODE=1，会让 electron.exe 以纯 Node 模式跑，必须清掉
unset ELECTRON_RUN_AS_NODE
VITE_DEV_SERVER_URL="$WEB" PERF_OUT="$OUT" ./node_modules/electron/dist/electron.exe main/perf-gate.js
GATE=$?

kill $SIDECAR_PID $VITE_PID 2>/dev/null
wait $SIDECAR_PID 2>/dev/null
wait $VITE_PID 2>/dev/null
echo "退出码 $GATE"
exit $GATE