#!/usr/bin/env bash
# Vue 对照版：同 sidecar、同门禁，只换渲染层，用于肉眼对比
set -u
cd "$(dirname "$0")"

N="C:/Users/su/.workbuddy/binaries/node/versions/22.22.2-6/node.exe"
export RENPYBOX_SIDECAR_PORT="${RENPYBOX_SIDECAR_PORT:-9712}"
export RENPYBOX_WEB_PORT="${RENPYBOX_WEB_PORT:-5274}"
SIDECAR="$RENPYBOX_SIDECAR_PORT"
WEB="http://127.0.0.1:$RENPYBOX_WEB_PORT"

cleanup() {
  echo
  echo "[dev-vue] 收尾中…"
  [ -n "${VITE_PID:-}" ] && kill "$VITE_PID" 2>/dev/null
  [ -n "${SIDECAR_PID:-}" ] && kill "$SIDECAR_PID" 2>/dev/null
  wait 2>/dev/null
  exit 0
}
trap cleanup INT TERM

echo "[dev-vue] 1/2 启动 vite（$WEB，renderer-vue）"
"$N" node_modules/vite/bin/vite.js --config renderer-vue/vite.config.ts &
VITE_PID=$!
for i in $(seq 1 60); do
  curl -sf "$WEB/" >/dev/null 2>&1 && break
  sleep 0.5
done
curl -sf "$WEB/" >/dev/null || { echo "[dev-vue] vite 未就绪"; exit 1; }

echo "[dev-vue] 2/2 启动 Electron 窗口"
echo "[dev-vue] 重点：加载后持续滚动，看「最低帧率」和「长任务」两栏"
echo

unset ELECTRON_RUN_AS_NODE
VITE_DEV_SERVER_URL="$WEB" ./node_modules/electron/dist/electron.exe .