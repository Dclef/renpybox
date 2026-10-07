#!/usr/bin/env bash
# 开发模式：sidecar + vite + 可见的 Electron 窗口（肉眼验证用）
set -u
cd "$(dirname "$0")"

N="C:/Users/su/.workbuddy/binaries/node/versions/22.22.2-6/node.exe"
export RENPYBOX_SIDECAR_PORT="${RENPYBOX_SIDECAR_PORT:-9712}"
export RENPYBOX_WEB_PORT="${RENPYBOX_WEB_PORT:-5273}"
SIDECAR="$RENPYBOX_SIDECAR_PORT"
WEB="http://127.0.0.1:$RENPYBOX_WEB_PORT"

cleanup() {
  echo
  echo "[dev] 收尾中…"
  [ -n "${VITE_PID:-}" ] && kill "$VITE_PID" 2>/dev/null
  [ -n "${SIDECAR_PID:-}" ] && kill "$SIDECAR_PID" 2>/dev/null
  wait 2>/dev/null
  exit 0
}
trap cleanup INT TERM

echo "[dev] 1/2 启动 vite（$WEB）"
"$N" node_modules/vite/bin/vite.js --config renderer/vite.config.ts &
VITE_PID=$!
for i in $(seq 1 60); do
  curl -sf "$WEB/" >/dev/null 2>&1 && break
  sleep 0.5
done
curl -sf "$WEB/" >/dev/null || { echo "[dev] vite 未就绪"; exit 1; }

echo "[dev] 2/2 启动 Electron 窗口"
echo "[dev] sidecar 由主进程自动拉起并守护（端口 $SIDECAR）"
echo "[dev] 关闭 Electron 窗口即可退出；Ctrl+Shift+W 开欢迎页，Ctrl+Shift+U 开更新弹窗"
echo

# 环境里预置了 ELECTRON_RUN_AS_NODE=1，不清掉 electron.exe 会以纯 Node 模式运行
unset ELECTRON_RUN_AS_NODE
VITE_DEV_SERVER_URL="$WEB" ./node_modules/electron/dist/electron.exe .