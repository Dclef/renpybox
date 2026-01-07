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

rem Move updater under _internal to reduce accidental clicks
if exist dist\\RenpyBox\\RenpyBoxUpdater.exe (
  if not exist dist\\RenpyBox\\_internal mkdir dist\\RenpyBox\\_internal
  move /y dist\\RenpyBox\\RenpyBoxUpdater.exe dist\\RenpyBox\\_internal\\RenpyBoxUpdater.exe >nul
  attrib +h +s dist\\RenpyBox\\_internal\\RenpyBoxUpdater.exe >nul 2>nul
)
echo Build complete. Output in dist/RenpyBox
if defined CI goto :eof
if defined GITHUB_ACTIONS goto :eof
pause
