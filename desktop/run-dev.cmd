@echo off
REM RenpyBox Electron 壳（React 开发版）—— 双击或 cmd 里直接跑，不需要 WSL / bash
setlocal
cd /d "%~dp0"

set "BASH=C:\Users\su\.workbuddy\binaries\PortableGit\versions\1.2.0\bin\bash.exe"
if not exist "%BASH%" set "BASH=bash"

"%BASH%" -lc "cd '$(cygpath -u "%~dp0" 2>nul || echo .)' 2>/dev/null || true"
"%BASH%" "%~dp0run-dev.sh" %*
endlocal