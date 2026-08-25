@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if not errorlevel 1 goto :python_ready
echo [ERROR] Python was not found. Install Python 3.10 and add it to PATH.
if defined CI goto :eof
if defined GITHUB_ACTIONS goto :eof
pause
exit /b 1

:python_ready

echo Cleaning caches and old logs...
rem Clean __pycache__
for /d /r %%i in (__pycache__) do rd /s /q "%%i" 2>nul
rem Clean logs
if exist log\*.log del /q log\*.log 2>nul
if exist log\*.log.* del /q log\*.log.* 2>nul

echo Building RenpyBox...
python -m PyInstaller main.spec --clean --noconfirm
if not errorlevel 1 goto :pyinstaller_ready
echo [ERROR] PyInstaller build failed.
if defined CI goto :eof
if defined GITHUB_ACTIONS goto :eof
pause
exit /b 1

:pyinstaller_ready

set "OPENCC_T2S=dist\RenpyBox\_internal\opencc\clib\share\opencc\t2s.json"
if exist "%OPENCC_T2S%" goto :opencc_ready
echo [ERROR] Missing OpenCC config: %OPENCC_T2S%
if defined CI goto :eof
if defined GITHUB_ACTIONS goto :eof
pause
exit /b 1

:opencc_ready

rem Move updater under _internal to reduce accidental clicks
if not exist dist\RenpyBox\_internal mkdir dist\RenpyBox\_internal
if exist dist\RenpyBox\RenpyBoxUpdater2.exe (
  move /y dist\RenpyBox\RenpyBoxUpdater2.exe dist\RenpyBox\_internal\RenpyBoxUpdater2.exe >nul
)
if exist dist\RenpyBoxUpdater2.exe (
  move /y dist\RenpyBoxUpdater2.exe dist\RenpyBox\_internal\RenpyBoxUpdater2.exe >nul
)
if exist dist\RenpyBox\RenpyBoxUpdater.exe (
  move /y dist\RenpyBox\RenpyBoxUpdater.exe dist\RenpyBox\_internal\RenpyBoxUpdater.exe >nul
)
if exist dist\RenpyBoxUpdater.exe (
  move /y dist\RenpyBoxUpdater.exe dist\RenpyBox\_internal\RenpyBoxUpdater.exe >nul
)
if exist dist\RenpyBox\_internal\RenpyBoxUpdater.exe (
  attrib +h +s dist\RenpyBox\_internal\RenpyBoxUpdater.exe >nul 2>nul
)
if exist dist\RenpyBox\_internal\RenpyBoxUpdater2.exe (
  attrib +h +s dist\RenpyBox\_internal\RenpyBoxUpdater2.exe >nul 2>nul
)
echo Build complete. Output in dist/RenpyBox
if defined CI goto :eof
if defined GITHUB_ACTIONS goto :eof
pause
