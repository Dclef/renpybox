#!/usr/bin/env bash
# api 模式联调：用项目自身解释器起真实契约层，打一遍接口后再起Electron 窗口。
set -u
cd "$(dirname "$0")"

N="${RENPYBOX_NODE:-node}"
PROJECT_PY="${RENPYBOX_PROJECT_PYTHON:-C:/Program Files/Python/python3.10/python.exe}"
export RENPYBOX_SIDECAR_PORT="${RENPYBOX_SIDECAR_PORT:-9712}"
export RENPYBOX_WEB_PORT="${RENPYBOX_WEB_PORT:-5273}"
SIDECAR="$RENPYBOX_SIDECAR_PORT"
WEB="http://127.0.0.1:$RENPYBOX_WEB_PORT"

cleanup() {
  echo
  echo "[dev-api] 收尾中…"
  [ -n "${VITE_PID:-}" ] && kill "$VITE_PID" 2>/dev/null
  wait 2>/dev/null
  exit 0
}
trap cleanup INT TERM

echo "[dev-api] 1/3 启动 sidecar（api 模式，$PROJECT_PY）"
( cd sidecar && QT_QPA_PLATFORM=offscreen "$PROJECT_PY" main.py ) &
for i in $(seq 1 60); do
  curl -sf "http://127.0.0.1:$SIDECAR/health" >/dev/null 2>&1 && break
  sleep 0.5
done

HEALTH=$(curl -sf "http://127.0.0.1:$SIDECAR/health")
if [ -z "$HEALTH" ]; then
  echo "[dev-api] sidecar 未就绪"
  exit 1
fi
echo "[dev-api] health: $HEALTH"

echo
echo "[dev-api] 2/3 验证真实业务接口（术语表去重 + 搜索）"
curl -s -X POST "http://127.0.0.1:$SIDECAR/api/glossary/sync" \
  -H "Content-Type: application/json" \
  -d '{"kind":"GLOSSARY","rows":[{"src":"ソyma","dst":"沙发","info":"","regex":false,"case_sensitive":false},{"src":"ソyma","dst":"","info":"","regex":false,"case_sensitive":false},{"src":"おにぎり","dst":"饭团","info":"","regex":false,"case_sensitive":false}]}'
echo
curl -s -X POST "http://127.0.0.1:$SIDECAR/api/glossary/search" \
  -H "Content-Type: application/json" \
  -d '{"kind":"GLOSSARY","rows":[{"src":"おにぎり","dst":"饭团"}],"keyword":"饭团","start":-1}'
echo

echo
echo "[dev-api] 3/3 启动 vite + Electron 窗口"
"$N" node_modules/vite/bin/vite.js --config renderer/vite.config.ts >/tmp/vite-api.log 2>&1 &
VITE_PID=$!
for i in $(seq 1 60); do
  curl -sf "$WEB/" >/dev/null 2>&1 && break
  sleep 0.5
done
curl -sf "$WEB/" >/dev/null || { echo "[dev-api] vite 未就绪"; tail -20 /tmp/vite-api.log; exit 1; }

unset ELECTRON_RUN_AS_NODE
RENPYBOX_PROJECT_PYTHON="$PROJECT_PY" VITE_DEV_SERVER_URL="$WEB" \
  ./node_modules/electron/dist/electron.exe .