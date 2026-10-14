@echo off
REM RenpyBox Electron 壳（React 开发版）—— 双击或 cmd 里直接跑，不需要 WSL / bash
setlocal
cd /d "%~dp0"

call npm run dev -- %*
endlocal
