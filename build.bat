@echo off
setlocal

echo Cleaning caches and old logs...
rem 删除 __pycache__
for /d /r %%i in (__pycache__) do rd /s /q "%%i" 2>nul
rem 清理日志
if exist log\\*.log del /q log\\*.log 2>nul
if exist log\\*.log.* del /q log\\*.log.* 2>nul

echo Building RenpyBox...
pyinstaller main.spec --clean --noconfirm

set "OPENCC_T2S=dist\RenpyBox\_internal\opencc\clib\share\opencc\t2s.json"
if not exist "%OPENCC_T2S%" (
  echo [ERROR] Missing OpenCC config: %OPENCC_T2S%
  exit /b 1
)

rem Move updater under _internal to reduce accidental clicks
if not exist dist\\RenpyBox\\_internal mkdir dist\\RenpyBox\\_internal
if exist dist\\RenpyBox\\RenpyBoxUpdater.exe (
  move /y dist\\RenpyBox\\RenpyBoxUpdater.exe dist\\RenpyBox\\_internal\\RenpyBoxUpdater.exe >nul
)
if exist dist\\RenpyBoxUpdater.exe (
  move /y dist\\RenpyBoxUpdater.exe dist\\RenpyBox\\_internal\\RenpyBoxUpdater.exe >nul
)
if exist dist\\RenpyBox\\_internal\\RenpyBoxUpdater.exe (
  attrib +h +s dist\\RenpyBox\\_internal\\RenpyBoxUpdater.exe >nul 2>nul
)
echo Build complete. Output in dist/RenpyBox
if defined CI goto :eof
if defined GITHUB_ACTIONS goto :eof
pause
