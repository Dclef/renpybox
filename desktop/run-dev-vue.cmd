@echo off
REM RenpyBox Electron 壳（Vue 对照版）—— 双击或 cmd 里直接跑，不需要 WSL / bash
setlocal
cd /d "%~dp0"

set "BASH=C:\Users\su\.workbuddy\binaries\PortableGit\versions\1.2.0\bin\bash.exe"
if not exist "%BASH%" set "BASH=bash"

"%BASH%" "%~dp0run-dev-vue.sh" %*
endlocal