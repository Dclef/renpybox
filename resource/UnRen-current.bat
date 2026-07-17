@echo off

:: Original Author:
:: UnRen.bat by Sam - https://f95zone.com/members/sam.7899/ ^& Gideon - https://f95zone.to/members/gideon.21585/
:: https://f95zone.to/threads/unren-bat-v1-0-11d-rpa-extractor-rpyc-decompiler-console-developer-menu-enabler.3083/

:: Modified by VepsrP - https://f95zone.to/members/vepsrp.329951/
:: https://f95zone.to/threads/unrengui-unren-forall-v9-4-unren-powershell-forall-v9-4-unren-old.92717/

:: Purpose:
:: This script is designed to automate the process of extracting and decompiling Ren'Py games.

:: Using:
:: rpatool - https://github.com/Shizmob/rpatool
:: unrpyc - https://github.com/CensoredUsername/unrpyc
:: altrpatool - Modified version of rpatool by JoeLurmel based on the version found in UnRen script by VepsrP.

:: UnRen-current.bat - UnRen Script for Ren'Py >= 8
:: heavily modified by (SM) aka JoeLurmel @ f95zone.to
:: This script is licensed under GNU GPL v3 — see LICENSE for details
:: RenpyBox 中文精简版：保留解包和反编译功能，已移除自更新。


:: Get the current code page
for /f "tokens=2 delims=:" %%a in ('%SystemRoot%\System32\chcp.com') do set "OLD_CP=%%a"
:: Switch to code page 65001 for UTF-8
"%SystemRoot%\System32\chcp.com" 65001 >nul


:: In case it contains spaces, we need to use a temporary variable to avoid issues with delayed expansion
set "TEMPDIR=%~1"
set "AUTO_MODE="
if /i "%~3" == "--auto" set "AUTO_MODE=1"

setlocal enabledelayedexpansion
:: DO NOT MODIFY BELOW THIS LINE unless you know what you're doing
:: Define various global names
set "NAME=current"
set "VERSION=v9.7.80 - 05/17/26"
title UnRen-%NAME%.bat - %VERSION%
set "URL_REF=https://f95zone.to/threads/92717/post-17110063/"
set "SCRIPTDIR=%~dp0"
set "SCRIPTNAME=%~nx0"
set "BASENAME=%SCRIPTNAME:.bat=%"
set "UNRENLOG=%TEMP%\%BASENAME%.log"
set "PWRSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
set "regexe=%SystemRoot%\System32\reg.exe"
if exist "%UNRENLOG%" del /f /q "%UNRENLOG%" >nul 2>&1


:: Use wmic for older system or PowerShell for newer ones to get date and time
set "datetime="
set "WMICEXE=%SystemRoot%\System32\wbem\wmic.exe"
if exist "%WMICEXE%" (
    for /f "skip=1 tokens=1" %%a in ('%WMICEXE% os get LocalDateTime 2^>nul') do (
        set "datetime=%%a"
        goto :dbreak
    )
)
if not defined datetime (
    for /f "delims=" %%a in ('"%PWRSHELL%" -NoProfile -Command "(Get-CimInstance Win32_OperatingSystem).LocalDateTime.ToString(\"yyyyMMddHHmmss\")"') do (
         set "datetime=%%a"
         goto :dbreak
    )
)
:dbreak
:: Parse the datetime string
set year=%datetime:~0,4%
set month=%datetime:~4,2%
set day=%datetime:~6,2%
set hour=%datetime:~8,2%
set minute=%datetime:~10,2%
set second=%datetime:~12,2%
set formatted_date=%month%/%day%/%year:~2,2%
set formatted_time=%hour%:%minute%:%second%


:: Start the Log
>> "%UNRENLOG%" echo.
echo UnRen-%NAME%.bat %VERSION%，启动时间：%formatted_date% %formatted_time% >> "%UNRENLOG%"
>> "%UNRENLOG%" echo.


:: Set default values
set "MDEFS=acefg"
set "MDEFS2=12acefg"
set "CTIME=5"
set "_7ZIPLOC=%ProgramFiles%\7-Zip\7z.exe"
:: External configuration file for LNG, MDEFS, MDEFS2 and CTIME.
set "UNREN_CFG=%SCRIPTDIR%UnRen-cfg.txt"
set "OLD_UNREN_CFG=%SCRIPTDIR%UnRen-cfg.bat"
if exist "%OLD_UNREN_CFG%" if not exist "%UNREN_CFG%" (
    move /y "%OLD_UNREN_CFG%" "%UNREN_CFG%" %DEBUGREDIR%
)
:: Load external configuration
if exist "%UNREN_CFG%" (
    for /f "usebackq tokens=1,* delims== " %%A in ("%UNREN_CFG%") do (
        if /i "%%A"=="set" (
            set %%B
        )
    )
)

:: 固定使用简体中文，配置文件中的 LNG 设置将被忽略。
set "LNG=zh"

:: 定义与语言无关的通用文本
set "GRY=[90m"
set "RED=[91m"
set "ORA=[38;5;208m"
set "GRE=[92m"
set "YEL=[93m"
set "MAG=[95m"
set "CYA=[96m"
set "RES=[0m"
for /f "tokens=4-5 delims=. " %%i in ('ver') do set OSVERS=%%i.%%j
if "%OSVERS%" == "6.1" (
    if exist "%SystemRoot%\ansicon.exe" (
        "%SystemRoot%\ansicon.exe" -i %DEBUGREDIR%
    ) else (
        set "ansmsg1.zh=注意：Windows 7 无 Ansicon 不支持 ANSI 颜色。"

        set "ansmsg2.zh=请从 https://github.com/adoxa/ansicon/releases 下载 Ansicon"

        set "ansmsg3.zh=将 x86/x64 目录内容提取到 %SystemRoot% 并且它将自动使用。"

        echo.
        echo !ansmsg1.%LNG%!
        echo.
        echo !ansmsg2.%LNG%!
        echo !ansmsg3.%LNG%!
        echo.
        pause

        call :exitn 3
    )
)


:: Definition of reusable texts
set "EMPTY=[      ]"
set "NOK=[ %RED%失败%RES% ]"
set "OK=[ %GRE%成功%RES% ]"
set "SKIP=[ %CYA%跳过%RES% ]"
set "WARN=[ %ORA%警告%RES% ]"

:: language dependent here, defined for each supported language.
:: The script will use the appropriate one based on the detected or selected language.
set "ANYKEY.zh=按任意键退出"

set "ARIGHT.zh=请以管理员身份运行此脚本以添加条目。"

set "FDELETE.zh=无法删除："

set "FCREATE.zh=创建失败："

set "FMOVE.zh=移动失败："

set "APRESENT.zh=选项已安装。"

set "TWRM.zh=这将移除："

set "TWADD.zh=这将添加："

set "INCASEOF.zh=如果出现问题，请参考："

set "INCASEDEL.zh=如果出现问题，请删除以下文件/目录："

set "UNDWNLD.zh=无法下载："

set "UNINSTALL.zh=无法安装："

set "UNEXTRACT.zh=无法提取："

set "FNOTFOUND.zh=找不到文件："

set "ENTERYN.zh=输入 [Y/N]（默认 N）："

set "CLEANUP.zh=清理临时文件"

set "UNACONT.zh=无法继续。"

set "NOTFOUND.zh=找不到文件"

set "LOGCHK.zh=请查看 "%UNRENLOG%" 以了解详情。"

set "UNIT.zh=字节"
:: End of reusable texts


:: Initializing debug mode
set "DEBUGREDIR=>nul 2>>%UNRENLOG%"
set "DEBUGLEVEL=0"
set "NOCLS=0"


:: 设置控制台尺寸
set "NEW_COLS=110"
set "NEW_LINES=60"
set /a "NEW_LINES_UP=%NEW_LINES%+5"
if not defined WT_SESSION (
    REM Set the cmd screen size with backup of old settings
    set "count=0"
    for /f "tokens=*" %%A in ('"%SystemRoot%\System32\mode.com" con') do (
        REM Split the line into tokens
        for %%B in (%%A) do (
            set "val=%%B"
            REM Check if it's a number
            echo !val! |  "%SystemRoot%\System32\findstr.exe" /r "[0-9][0-9]" >nul
            if !errorlevel! EQU 0 (
                set /a count+=1
                if !count! EQU 1 (
                    set "ORIG_LINES=!val!"
                )
                if !count! EQU 2 (
                    set "ORIG_COLS=!val!"
                )
            )
        )
    )
    %SystemRoot%\System32\mode.com con: cols=%NEW_COLS% lines=%NEW_LINES_UP% %DEBUGREDIR%
    %SystemRoot%\System32\mode.com con: cols=%NEW_COLS% lines=%NEW_LINES% %DEBUGREDIR%
)

:: 已移除首次赞助提示和异步重启，保证后台调用可以等待任务完成。
cls


:: We need PowerShell for later, make sure it exists
set "pshell.zh=检查 PowerShell 是否可用"

call :elog -n "%EMPTY%" "!pshell.%LNG%!..."
for /f "delims=" %%A in ('"%SystemRoot%\System32\where.exe" pwsh.exe 2^>nul') do (
    if not "%%A" == "" set "PWRSHELL=%%A"
)
if not exist "%PWRSHELL%" (
    set "pshell1.zh=需要 PowerShell。"

    set "pshell2.zh=Windows 7、8 和 10 包含此组件。XP/Vista 用户可以"

    set "pshell3.zh=在此下载：%MAG%https://learn.microsoft.com/en-us/powershell/scripting/install/installing-powershell-on-windows?view=powershell-7.5%RES%"

    call :elog "%NOK%"
    call :elog .
    call :elog "    !pshell1.%LNG%!. !UNACONT.%LNG%!"
    call :elog "    !pshell2.%LNG%!"
    call :elog "    !pshell3.%LNG%!"
    call :elog .
    pause>nul|set /p=".      !ANYKEY.%LNG%!..."

    call :exitn 3
) else (
    call :elog "%OK%"
)


:: Set the working directory
set "wdir1.zh=错误：指定的目录不存在。"

set "wdir2.zh=确定我们在游戏根目录中吗？"

set "wdir3.zh=测试对游戏目录的写入权限"

:: Check if game path is provided and set it
set "LAUNCHED_WDIR=0"
set "WORKDIR="
:: Remove surrounding quotes if any
if not "!TEMPDIR!" == "" set "TEMPDIR=!TEMPDIR:"=!"
if "!TEMPDIR!" == "" (
    set "setpath1.zh=输入游戏路径，将其拖放到此处，"

    set "setpath2.zh=或者如果此工具已在所需文件夹中，请按 Enter 键。"

    set "setpath3.zh=如果拖放不起作用，请复制/粘贴路径："

    setlocal enabledelayedexpansion
    echo.
    echo !setpath1.%LNG%!
    echo !setpath2.%LNG%!
    echo.
    set "_question=!setpath3.%LNG%!"
    for /f "delims=" %%A in ("!_question!") do (
        endlocal
        set /p "WORKDIR=%%A"
    )
    if not defined WORKDIR (
        set "WORKDIR=%cd%"
    )
) else (
    set "WORKDIR=!TEMPDIR!"
    if "%WORKDIR%" == "." (
        set "WORKDIR=%cd%"
    )
    set "LAUNCHED_WDIR=1"
)

setlocal disabledelayedexpansion
:: Remove surrounding quotes if any
set "WORKDIR=%WORKDIR:"=%"

:: Normalize WORKDIR to an absolute path
for %%A in ("%WORKDIR%") do set "WORKDIR=%%~fA"

:: Check if WORKDIR is a valid path
set "HAS_BAD="
:: Characters that CAN appear in a valid Windows path but WILL break batch logic:
setlocal disabledelayedexpansion
echo "%WORKDIR%" | "%SystemRoot%\System32\findstr.exe" /C:"!" >nul && (
    call set "HAS_BAD=!"
)
echo "%WORKDIR%" | "%SystemRoot%\System32\findstr.exe" /C:"&" >nul && (
    if not defined HAS_BAD (
        call set "HAS_BAD=&"
    ) else (
        call set "HAS_BAD=%%HAS_BAD%%,&"
    )
)
endlocal & set "HAS_BAD=%HAS_BAD%"
for %%C in ("(" ")" "=" ";" "'" "`" "[" "]" "{" "}" "+" "~") do (
    echo "%WORKDIR%" | "%SystemRoot%\System32\findstr.exe" /C:"%%~C" >nul && (
        if not defined HAS_BAD (
            call set "HAS_BAD=%%~C"
        ) else (
            call set "HAS_BAD=%%HAS_BAD%%,%%~C"
        )
    )
)
setlocal enabledelayedexpansion
if defined HAS_BAD (
    set "invchars.zh=路径中检测到无效字符"

    echo %NOK% !invchars.%LNG%! '%RED%!HAS_BAD!%RES%'. !UNACONT.%LNG%!
    call :elog .
    pause>nul|set /p=".      !ANYKEY.%LNG%!..."

    call :exitn 3
)

setlocal disabledelayedexpansion
for /f "delims=" %%A in ("%WORKDIR%") do (
    endlocal
    cd /d "%%A"
    if %errorlevel% NEQ 0 (
        call :elog "%NOK%" "!wdir1.%LNG%!%RES%"
        call :elog .
        call :elog "    !wdir2.%LNG%!"
        call :elog .
        pause>nul|set /p=".      !ANYKEY.%LNG%!..."

        call :exitn 3
    )
)

:: Analysis of debug arguments
if /i "%~3" == "-d" (
    set "DEBUGREDIR=>>%UNRENLOG% 2>&1"
    set "DEBUGLEVEL=1"
    set "NOCLS=1"
    if %DEBUGLEVEL% GEQ 1 echo "%PWRSHELL%" -NoProfile -Command "$h = Get-Host; $h.UI.RawUI.BufferSize = New-Object Management.Automation.Host.Size(!NEW_COLS!,5000)" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "$h = Get-Host; $h.UI.RawUI.BufferSize = New-Object Management.Automation.Host.Size(!NEW_COLS!,5000)" %DEBUGREDIR%
)
if /i "%~3" == "-dd" (
    echo on
    set "DEBUGREDIR=>>%UNRENLOG% 2>&1"
    set "DEBUGLEVEL=2"
    set "NOCLS=1"
    if %DEBUGLEVEL% GEQ 1 echo "%PWRSHELL%" -NoProfile -Command "$h = Get-Host; $h.UI.RawUI.BufferSize = New-Object Management.Automation.Host.Size(!NEW_COLS!,9000)" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "$h = Get-Host; $h.UI.RawUI.BufferSize = New-Object Management.Automation.Host.Size(!NEW_COLS!,9000)" %DEBUGREDIR%
)


:: Check that you are in the root directory of the game.
set "reqdir1.zh=检查 game、lib、renpy 目录是否存在"

setlocal disabledelayedexpansion
for /f "delims=" %%A in ("%WORKDIR%") do (
    endlocal
    cd /d "%%A"
)
set "missing="
call :elog -n "%EMPTY%" "!reqdir1.%LNG%!..."
set "missing="
if not exist ".\game" (
    set "missing=%YEL%.\game%RES%"
)
if not exist ".\lib" (
    if defined missing (
        set "missing=!missing!, %YEL%.\lib%RES%"
    ) else (
        set "missing=%YEL%.\lib%RES%"
    )
)
if not exist ".\renpy" (
    if defined missing (
        set "missing=!missing!, %YEL%.\renpy%RES%"
    ) else (
        set "missing=%YEL%.\renpy%RES%"
    )
)

set "reqdir2.zh=找不到 %missing% 目录。"
if defined missing (
    call :elog "%NOK%"
    call :elog .
    call :elog "    !reqdir2.%LNG%!. !UNACONT.%LNG%!"
    call :elog "    !wdir2.%LNG%!"
    call :elog .
    pause>nul|set /p=".      !ANYKEY.%LNG%!..."

    call :exitn 3
) else (
    call :elog "%OK%"
)

:: Check if .\game is writable
call :elog -n "%EMPTY%" "!wdir3.%LNG%!..."
if %DEBUGLEVEL% GEQ 1 echo copy /y nul ".\game\test.txt" >> "%UNRENLOG%"
copy /y nul ".\game\test.txt" %DEBUGREDIR%
if %errorlevel% NEQ 0 (
    call :elog "%NOK%"
    call :elog .
    call :elog "    !wdir2.%LNG%!"
    call :elog .
    pause>nul|set /p=".      !ANYKEY.%LNG%!..."

    call :exitn 3
) else (
    if %DEBUGLEVEL% GEQ 1 echo del /f /q ".\game\test.txt" >> "%UNRENLOG%"
    del /f /q ".\game\test.txt" %DEBUGREDIR%
    call :elog "%OK%"
)


:: Set UNRENLOG for debugging purpose
If exist "%TEMP%\%BASENAME%.log" (
    if %DEBUGLEVEL% GEQ 1 echo move /y "%TEMP%\%BASENAME%.log" "%WORKDIR%\%BASENAME%.log" >> "%UNRENLOG%"
    move /y "%TEMP%\%BASENAME%.log" "%WORKDIR%\%BASENAME%.log" >nul 2>&1
    if !errorlevel! NEQ 0 (
        call :elog "%NOK%" "!FMOVE.%LNG%! %YEL%%TEMP%\%BASENAME%.log%RES% !decm10a.%LNG%! %YEL%%WORKDIR%\%BASENAME%.log%RES%"
        call :elog .
        pause>nul|set /p=".      !ANYKEY.%LNG%!..."

        call :exitn 3
    )
)
set "UNRENLOG=%WORKDIR%\%BASENAME%.log"
set "UNRENLOG=%UNRENLOG:"=%"


:: Check for Python System
set "PYTHONEXE="
set "PYVERSION2="
set "PYVERSION3="
set "PYTHONSYSTEM="

setlocal enabledelayedexpansion
set "pysystem1.zh=检查系统是否安装 Python"

set "pysystem2.zh=系统上可用 Python 2 和 3。"

set "pysystem3.zh=只有 Python 2 可用于系统。"

set "pysystem4.zh=只有 Python 3 可用于系统。"

set "pysystem5.zh=系统上不可用 Python。"

set "pythonv2="
set "pythonv3="
set "pythonexe="
set "pythonsystem="
call :elog -n "%EMPTY%" "!pysystem1.%LNG%!..."
if exist "%SystemRoot%\py.exe" (
    "%SystemRoot%\py.exe" --list >"%TEMP%\pylist.txt" 2>&1
    for /f "tokens=1,2 delims=:" %%A in ('%SystemRoot%\System32\findstr.exe /i "V:" "%TEMP%\pylist.txt"') do (
        :: %%B contains major.minor eg: "3.14", "3.9 *", "2.7"
        for /f "tokens=1,2 delims=." %%M in ("%%B") do (
            :: %%M = major (eg: "3"), %%N = minor with optional " *" (eg: "14", "9 *")
            for /f "tokens=1 delims= " %%V in ("%%N") do (
                :: %%V = minor clean (eg: "14", "9", "7")
                if "%%M" == "2" (
                    if "%%V" == "7" (
                        set "pythonexe=%SystemRoot%\py.exe"
                        set "pythonv2=-V:%%M.%%V"
                        set "pythonsystem=-E"
                    )
                ) else if "%%M" == "3" (
                    if %%V GEQ 9 (
                        set "pythonexe=%SystemRoot%\py.exe"
                        set "pythonv3=-V:%%M.%%V"
                        set "pythonsystem=-E"
                    )
                )
            )
        )
    )
)
del /f /q "%TEMP%\pylist.txt" %DEBUGREDIR%

set "PATH=%SystemDrive%\Python27:%PATH%"
for /f "delims=" %%A in ('"%SystemRoot%\System32\where.exe" python.exe 2^>nul') do (
    if not "%%A" == "" (
        echo "%%A" | "%SystemRoot%\System32\findstr.exe" /i "WindowsApps" >nul
        if errorlevel 1 (
            if exist "%%A" (
                for /f "tokens=2 delims= " %%B in ('"%%A" -V 2^>^&1') do (
                    for /f "tokens=1,2 delims=." %%M in ("%%B") do (
                        if "%%M" == "2" (
                            if not defined pythonexe (
                                set "pythonexe=%%A"
                                set "pythonsystem=-E"
                            )
                        ) else if "%%M" == "3" (
                            if %%N GEQ 9 (
                                if not defined pythonv3 (
                                    set "pythonexe=%%A"
                                    set "pythonsystem=-E"
                                )
                            )
                        )
                    )
                )
            )
        )
    )
)

if defined pythonv2 if defined pythonv3 (
    call :elog "%OK%"
    call :elog "         !pysystem2.%LNG%!"
) else if defined pythonv2 if not defined pythonv3 (
    call :elog "%OK%"
    call :elog "         !pysystem3.%LNG%!"
) else if not defined pythonv2 if defined pythonv3 (
    call :elog "%OK%"
    call :elog "         !pysystem4.%LNG%!"
) else (
    call :elog "%SKIP%"
    call :elog "         !pysystem5.%LNG%!"
)
endlocal & set "PYTHONEXE=%pythonexe%" & set "PYVERSION2=%pythonv2%" & set "PYVERSION3=%pythonv3%" & set "PYTHONSYSTEM=%pythonsystem%"


:: Check for Python Game
set "python1.zh=检查 Python 游戏是否可用"

set "python2.zh=Python 版本："

set "python3.zh=找不到 python 目录。"

call :elog -n "%EMPTY%" "!python1.%LNG%!..."

:: Doublecheck to avoid issues with Milfania games
set "PYTHONHOME="
set "PYTHONPATH="
if exist "%WORKDIR%\lib\py3-windows-x86_64\pythonw.exe" if exist "%WORKDIR%\lib\py3-windows-x86_64\python.exe" (
    if not "%PROCESSOR_ARCHITECTURE%" == "x86" (
        <nul set /p=.
        set "PYTHONHOME=%WORKDIR%\lib\py3-windows-x86_64\"
    ) else if exist "%WORKDIR%\lib\py3-windows-i686\python.exe" (
        <nul set /p=.
        set "PYTHONHOME=%WORKDIR%\lib\py3-windows-i686\"
    )
) else if exist "%WORKDIR%\lib\py3-windows-i686\python.exe" (
    <nul set /p=.
    set "PYTHONHOME=%WORKDIR%\lib\py3-windows-i686\"
)
if exist "%WORKDIR%\lib\py2-windows-x86_64\python.exe" (
    if not "%PROCESSOR_ARCHITECTURE%" == "x86" (
        <nul set /p=.
        set "PYTHONHOME=%WORKDIR%\lib\py2-windows-x86_64\"
    ) else if exist "%WORKDIR%\lib\py2-windows-i686\python.exe" (
        <nul set /p=.
        set "PYTHONHOME=%WORKDIR%\lib\py2-windows-i686\"
    )
) else if exist "%WORKDIR%\lib\py2-windows-i686\python.exe" (
    <nul set /p=.
    set "PYTHONHOME=%WORKDIR%\lib\py2-windows-i686\"
)
if exist "%WORKDIR%\lib\windows-x86_64\python.exe" (
    if not "%PROCESSOR_ARCHITECTURE%" == "x86" (
        <nul set /p=.
        set "PYTHONHOME=%WORKDIR%\lib\windows-x86_64\"
    ) else if exist "%WORKDIR%\lib\windows-i686\python.exe" (
        <nul set /p=.
        set "PYTHONHOME=%WORKDIR%\lib\windows-i686\"
    )
) else if exist "%WORKDIR%\lib\windows-i686\python.exe" (
    <nul set /p=.
    set "PYTHONHOME=%WORKDIR%\lib\windows-i686\"
)
set "PYTHONPATH=%PYTHONHOME%"

:: Set the PYNOASSERT according to "%PYTHONHOME%Lib".
if exist "%PYTHONHOME%Lib" (
    set "PYNOASSERT=-O"
) else (
    set "PYNOASSERT="
)

for /f "tokens=2 delims= " %%a in ('"%PYTHONHOME%python.exe" -V 2^>^&1') do set PYTHONVERS=%%a
:: Extraction of major and minor versions
for /f "tokens=1,2 delims=." %%b in ("%PYTHONVERS%") do (
    set PYTHONMAJOR=%%b
    set PYTHONMINOR=%%c
)

set "RPATOOL_NEW="
set "UNRPYC_NEW="
:: Priority to Python 3.x if present
if %PYTHONMAJOR% GEQ 3 if exist "%WORKDIR%\lib\python%PYTHONMAJOR%.%PYTHONMINOR%" (
    <nul set /p=.
    set "PYTHONPATH=%WORKDIR%\lib\python%PYTHONMAJOR%.%PYTHONMINOR%"
    set "RPATOOL_NEW=y"
    set "UNRPYC_NEW=y"
    goto :pyend
)

:: Searching for the latest version of Python 2.x
if exist "%WORKDIR%\lib\pythonlib%PYTHONMAJOR%.%PYTHONMINOR%" (
    <nul set /p=.
    set "PYTHONPATH=%WORKDIR%\lib\pythonlib%PYTHONMAJOR%.%PYTHONMINOR%"
    set "RPATOOL_NEW=n"
    set "UNRPYC_NEW=n"
) else if exist "%WORKDIR%\lib\python%PYTHONMAJOR%.%PYTHONMINOR%" (
    <nul set /p=.
    set "PYTHONPATH=%WORKDIR%\lib\python%PYTHONMAJOR%.%PYTHONMINOR%"
    set "RPATOOL_NEW=n"
    set "UNRPYC_NEW=n"
)

:pyend
if not exist "%PYTHONPATH%" (
    call :elog "%NOK%"
    call :elog .
    call :elog "    %RED%!python3.%LNG%!%RES%. !UNACONT.%LNG%!"
    call :elog "    !wdir2.%LNG%!"
    call :elog .
    pause>nul|set /p=".      !ANYKEY.%LNG%!..."

    call :exitn 3
) else (
    call :elog "%OK%" "!python2.%LNG%! %YEL%%PYTHONVERS%%RES%"
)
if not defined PYTHONEXE (
    set "PYTHONEXE=%PYTHONHOME%python.exe"
)

:: Used later for base64 decoding
>"%TEMP%\b64decode.py" (
    echo import base64, sys, os
    echo.
    echo if len^(sys.argv^) ^< 3:
    echo     sys.stderr.write^("Usage: script.py <src> <dst>\n"^)
    echo     sys.exit^(1^)
    echo.
    echo src, dst = sys.argv[1], sys.argv[2]
    echo.
    echo try:
    echo    with open^(src, 'rb'^) as f:
    echo        raw = f.read^(^)
    echo except IOError as e:
    echo    sys.stderr.write^("Failed to read source file '%%s': %%s\n" %% ^(src, e^)^)
    echo    sys.exit^(1^)
    echo.
    echo try:
    echo    raw = raw.replace^(b'\r', b''^).replace^(b'\n', b''^)
    echo    missing = len^(raw^) %% 4
    echo    if missing:
    echo        raw += b'=' * ^(4 - missing^)
    echo    data = base64.b64decode^(raw^)
    echo except Exception as e:
    echo    sys.stderr.write^("Failed to decode base64 from '%%s': %%s\n" %% ^(src, e^)^)
    echo    sys.exit^(1^)
    echo.
    echo try:
    echo    with open^(dst, 'wb'^) as f:
    echo        f.write^(data^)
    echo except IOError as e:
    echo    sys.stderr.write^("Failed to write destination file '%%s': %%s\n" %% ^(dst, e^)^)
    echo    if os.path.exists^(dst^):
    echo        try:
    echo            os.remove^(dst^)
    echo            sys.stderr.write^("Cleaned up partial file '%%s'\n" %% dst^)
    echo        except OSError as e2:
    echo            sys.stderr.write^("Failed to clean up '%%s': %%s\n" %% ^(dst, e2^)^)
    echo    sys.exit^(1^)
)

:: Check for Ren'Py version
set "renpyvers1.zh=检测到的 Ren'Py 版本 :"

set "renpyvers2.zh=检查 Ren'Py 版本"

set "renpyvers3.zh=无法检测 Ren'Py 版本，"

set "renpyvers4.zh=请确保游戏与 UnRen 兼容。"

setlocal disabledelayedexpansion
for /f "delims=" %%A in ("%WORKDIR%") do (
    endlocal
    cd /d "%%A"
)

set "detect_renpy_version=%WORKDIR%\detect_renpy_version.py"
>"%detect_renpy_version%.b64" (
    <nul set /p="IyEvdXNyL2Jpbi9lbnYgcHl0aG9uDQojIC0qLSBjb2Rpbmc6IHV0Zi04IC0qLQ0KaW1wb3J0IG9zDQppbXBvcnQgc3lzDQppbXBvcnQgcmUNCg0KIyAtLS0gMS4gU3RhbmRhcmQgbWV0aG9kOiBpbXBvcnQgcmVucHkgLS0tDQp0cnk6DQogICAgaW1wb3J0IHJlbnB5DQogICAgcHJpbnQocmVucHkudmVyc2lvbl90dXBsZVswXSkNCiAgICBzeXMuZXhpdCgwKQ0KZXhjZXB0IEV4Y2VwdGlvbjoNCiAgICBwYXNzICAjIGZhbGxiYWNrIGJlbG93DQoNCmRlZiBkZXRlY3RfZnJvbV9zY3JpcHRfdmVyc2lvbihnYW1lX2Rpcik6DQogICAgIyAxKSBSZW4nUHkgNy84IDogc2NyaXB0X3ZlcnNpb24udHh0DQogICAgcGF0aCA9IG9zLnBhdGguam9pbihnYW1lX2RpciwgInNjcmlwdF92ZXJzaW9uLnR4dCIpDQogICAgaWYgb3MucGF0aC5pc2ZpbGUocGF0aCk6DQogICAgICAgIHRyeToNCiAgICAgICAgICAgIHdpdGggb3BlbihwYXRoLCAiciIpIGFzIGY6DQogICAgICAgICAgICAgICAgY29udGVudCA9IGYucmVhZCgpLnN0cmlwKCkNCg0KICAgICAgICAgICAgIyBUdXBsZSBmb3JtYXQgOiAoOCwgMSwgMCkNCiAgICAgICAgICAgIG0gPSByZS5zZWFyY2gocidcKFxzKihcZCspXHMqLCcsIGNvbnRlbnQpDQogICAgICAgICAgICBpZiBtOg0KICAgICAgICAgICAgICAgIHJldHVybiBpbnQobS5ncm91cCgxKSkNCg0KICAgICAgICAgICAgIyBTaW1wbGUgZm9ybWF0IDogOC4xLjAgb3UgOA0KICAgICAgICAgICAgbSA9IHJlLm1hdGNoKHInXHMqKFxkKyknLCBjb250ZW50KQ0KICAgICAgICAgICAgaWYgbToNCiAgICAgICAgICAgICAgICByZXR1cm4gaW50KG0uZ3JvdXAoMSkpDQoNCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoNCiAgICAgICAgICAgIHBhc3MNCg0KICAgICMgMikgUmVuJ1B5IDYgOiByZW5weS92ZXJzaW9uLnB5DQogICAgdmVyc2lvbl9weSA9IG9zLnBhdGguam9pbihnYW1lX2RpciwgInJlbnB5IiwgInZlcnNpb24ucHkiKQ0KICAgIGlmIG9zLnBhdGguaXNmaWxlKHZlcnNpb25fcHkpOg0KICAgICAgICB0cnk6DQogICAgICAgICAgICB3aXRoIG9wZW4odmVyc2lvbl9weSwgInIiKSBhcyBmOg0KICAgICAgICAgICAgICAgIGNvbnRlbnQgPSBmLnJlYWQoKQ0KDQogICAgICAgICAgICAjIHZlcnNpb24gPSAiNi45OS4xNCINCiAgICAgICAgICAgIG0gPSByZS5zZWFyY2gocid2ZXJzaW9uXHMqPVxzKiIoXGQrKScsIGNvbnRlbnQpDQogICAgICAgICAgICBpZiBtOg0KICAgICAgICAgICAgICAgIHJldHVybiBpbnQobS5ncm91cCgxKSkNCg0KICAgICAgICBleGNlcHQgRXhjZXB0aW9uOg0KICAgICAgICAgICAgcGFzcw0KDQogICAgcmV0dXJuIE5vbmUNCg0KDQpkZWYgZGV0ZWN0X2Zyb21fcnB5YyhnYW1lX2Rpcik6DQogICAgIiIiDQogICAgUmVhZHMgdGhlIG1hZ2ljIG51bWJlciBvZiAucnB5YyAvIC5ycHltYyBmaWxlcy4NCiAgICBSZW4nUHkgNjogbWFnaWMg4oCcUkVOUFkgUlBDMeKAnSAgLT4gbWFqb3IgNiAoYW5kIHNvbWUgZWFybHkgNykNCiAgICBSZW4nUHkgNzogbWFnaWMg4oCcUkVOUFkgUlBDMuKAnSAgLT4gbWFqb3IgNw0KICAgIFJlbidQeSA4OiBtYWdpYyDigJxSRU5QWSBSUEMy4oCdICB3aXRoIFB5dGhvbiAzIChjYW5ub3QgYmUgZWFzaWx5IGRpc3Rpbmd1aXNoZWQNCiAgICAgICAgICAgICAgICBmcm9tIDcgdXNpbmcgbWFnaWMgYWxvbmUsIG90aGVyIG1ldGhvZHMgYXJlIHVzZWQgdG8gY29tcGxldGUgdGhlIHByb2Nlc3MpDQogICAgTm90ZTogc29tZSBlYXJseSBSZW4nUHkgNyBtYXkgc3RpbGwgdXNlIOKAnFJFTlBZIFJQQzHigJ0gbWFnaWMsIGJ1dCB0aGV5IGFyZSByYXJlIGFuZCB3ZSBwcmlvcml0aXplIHRoZSBtb3JlIGNvbW1vbiBjYXNlLg0KICAgICIiIg0KICAgIG1hZ2ljX21hcCA9IHsNCiAgICAgICAgYiJSRU5QWSBSUEMxIjogNiwNCiAgICAgICAgYiJSRU5QWSBSUEMyIjogNywgICMgY2FuIGFsc28gYmUgOA0KICAgIH0NCiAgICBmb3Igcm9vdCwgZGlycywgZmlsZXMgaW4gb3Mud2FsayhnYW1lX2Rpcik6DQogICAgICAgIGZvciBmbmFtZSBpbiBmaWxlczoNCiAgICAgICAgICAgIGlmIGZuYW1lLmVuZHN3aXRoKCIucnB5YyIpIG9yIGZuYW1lLmVuZHN3aXRoKCIucnB5bWMiKToNCiAgICAgICAgICAgICAgICBmcGF0aCA9IG9zLnBhdGguam9pbihyb290LCBmbmFtZSkNCiAgICAgICAgICAgICAgICB0cnk6DQogICAgICAgICAgICAgICAgICAgIHdpdGggb3BlbihmcGF0aCwgInJiIikgYXMgZjoNCiAgICAgICAgICAgICAgICAgICAgICAgIGhlYWRlciA9IGYucmVhZCgxMCkNCiAgICAgICAgICAgICAgICAgICAgZm9yIG1hZ2ljLCBtYWpvciBpbiBtYWdpY19tYXAuaXRlbXMoKToNCiAgICAgICAgICAgICAgICAgICAgICAgIGlmIGhlYWRlci5zdGFydHN3aXRoKG1hZ2ljKToNCiAgICAgICAgICAgICAgICAgICAgICAgICAgICByZXR1cm4gbWFqb3INCiAgICAgICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uOg0KICAgICAgICAgICAgICAgICAgICBjb250aW51ZQ0KICAgIHJldHVybiBOb25lDQoNCg0KZGVmIGRldGVjdF9mcm9tX2V4ZWN1dGFibGUoZ2FtZV9kaXIpOg0KICAgICIiIg0KICAgIExvb2sgZm9yIHZlcnNpb24gY2x1ZXMgaW4gdGhlIGV4ZWN1dGFibGVzL2xpYnMgcHJlc2VudA0KICAgIGluIHRoZSBnYW1lIGZvbGRlciAoc3RyaW5ncyDigJw3LuKAnSBvciDigJw4LuKAnSBjbG9zZSB0byDigJxSZW4nUHnigJ0pLg0KICAgICIiIg0KICAgIGJhc2UgPSBvcy5wYXRoLmRpcm5hbWUoZ2FtZV9kaXIpICAjIHBhcmVudCBmb2xkZXIgb2YgdGhlIGdhbWUvIGZvbGRlcg0KICAgIHNlYXJjaF9kaXJzID0gW2Jhc2UsIGdhbWVfZGlyXQ0KICAgIHBhdHRlcm5zID0gWw0KICAgICAgICAocmUuY29tcGlsZShyIlJlbi4/UHlccysoXGQpXC5cZCIpLCBOb25lKSwNCiAgICAgICAgKHJlLmNvbXBpbGUociJyZW5weVtfXC1dKFxkKVwuXGQiKSwgcmUuSUdOT1JFQ0FTRSksDQogICAgXQ0KICAgIGZvciBzZGlyIGluIHNlYXJjaF9kaXJzOg0KICAgICAgICBmb3IgZm5hbWUgaW4gb3MubGlzdGRpcihzZGlyKToNCiAgICAgICAgICAgIGZwYXRoID0gb3MucGF0aC5qb2luKHNkaXIsIGZuYW1lKQ0KICAgICAgICAgICAgaWYgbm90IG9zLnBhdGguaXNmaWxlKGZwYXRoKToNCiAgICAgICAgICAgICAgICBjb250aW51ZQ0KICAgICAgICAgICAgIyBPbmx5IHNtYWxsIHRleHQgb3IgbG9nIGZpbGVzIGFyZSByZWFkLg0KICAgICAgICAgICAgaWYgZm5hbWUuZW5kc3dpdGgoKCIudHh0IiwgIi5sb2ciLCAiLmluaSIsICIuY2ZnIiwgIi5qc29uIikpOg0KICAgICAgICAgICAgICAgIHRyeToNCiAgICAgICAgICAgICAgICAgICAgd2l0aCBvcGVuKGZwYXRoLCAiciIpIGFzIGY6DQogICAgICAgICAgICAgICAgICAgICAgICBjb250ZW50ID0gZi5yZWFkKDQwOTYpDQogICAgICAgICAgICAgICAgICAgIGZvciBwYXQsIGZsYWdzIGluIHBhdHRlcm5zOg0KICAgICAgICAgICAgICAgICAgICAgICAgbSA9IHBhdC5zZWFyY2goY29udGVudCkNCiAgICAgICAgICAgICAgICAgICAgICAgIGlmIG06DQogICAgICAgICAgICAgICAgICAgICAgICAgICAgbWFqb3IgPSBpbnQobS5ncm91cCgxKSkNCiAgICAgICAgICAgICAgICAgICAgICAgICAgICBpZiBtYWpvciBpbiAoNiwgNywgOCk6DQogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIHJldHVybiBtYWpvcg0KICAgICAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb246DQogICAgICAgICAgICAgICAgICAgIHBhc3MNCiAgICByZXR1cm4gTm9uZQ0KDQoNCmRlZiBkZXRlY3RfZnJvbV9hcmNoaXZlKGdhbWVfZGlyKToNCiAgICAiIiINCiAgICBJbnNwZWN0IHRoZSAucnBhIGFyY2hpdmVzIHRvIGRldGVjdCB0aGUgdmVyc2lvbi4NCiAgICBSUEEtMS4wIC0+IFJlbidQeSA2IGVhcmx5DQogICAgUlBBLTIuMCAtPiBSZW4nUHkgNg0KICAgIFJQQS0zLjAgLT4gUmVuJ1B5IDYvNw0KICAgIFJQQU4zLjAgLT4gUmVuJ1B5IDggKG5ldyBuZXV0cm9uIGFyY2hpdmUpDQogICAgWmlYLTEyQSAtPiBSZW4nUHkgOCAobmV3IG5ldXRyb24gYXJjaGl2ZSkNCiAgICBaaVgtMTJCIC0+IFJlbidQeSA4IChuZXcgbmV1dHJvbiBhcmNoaXZlKQ0KICAgICIiIg0KICAgIHJwYV9tYWpvcl9tYXAgPSB7DQogICAgICAgIGIiUlBBLTEuMCI6IDYsDQogICAgICAgIGIiUlBBLTIuMCI6IDYsDQogICAgICAgIGIiUlBBLTMuMCI6IDcsICAgIyBNYXliZSA2IGFzIHdlbGwsIGJ1dCB3ZSdsbCByZWZpbmUgaXQgbGF0ZXIuDQogICAgICAgIGIiUlBBTjMuMCI6IDgsDQogICAgICAgIGIiWmlYLTEyQSI6IDgsDQogICAgICAgIGIiWmlYLTEyQiI6IDgsDQogICAgfQ0KICAgIGZvdW5kID0gTm9uZQ0KICAgIGZvciBmbmFtZSBpbiBvcy5saXN0ZGlyKGdhbWVfZGlyKToNCiAgICAgICAgaWYgbm90IGZuYW1lLmVuZHN3aXRoKCIucnBhIik6DQogICAgICAgICAgICBjb250aW51ZQ0KICAgICAgICBmcGF0aCA9IG9zLnBhdGguam9pbihnYW1lX2RpciwgZm5hbWUpDQogICAgICAgIHRyeToNCiAgICAgICAgICAgIHdpdGggb3BlbihmcGF0aCwgInJiIikgYXMgZjoNCiAgICAgICAgICAgICAgICBoZWFkZXIgPSBmLnJlYWQoOCkNCiAgICAgICAgICAgIGZvciBtYWdpYywgbWFqb3IgaW4gcnBhX21ham9yX21hcC5pdGVtcygpOg0KICAgICAgICAgICAgICAgIGlmIGhlYWRlci5zdGFydHN3aXRoKG1hZ2ljKToNCiAgICAgICAgICAgICAgICAgICAgIyBXZSBrZWVwIHRoZSBoaWdoZXN0IG1ham9yIGZvdW5kLg0KICAgICAgICAgICAgICAgICAgICBpZiBmb3VuZCBpcyBOb25lIG9yIG1ham9yID4gZm91bmQ6DQogICAgICAgICAgICAgICAgICAgICAgICBmb3VuZCA9IG1ham9yDQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb246DQogICAgICAgICAgICBwYXNzDQogICAgcmV0dXJuIGZvdW5kDQoNCg0KZGVmIGRldGVjdF9yZW5weV9tYWpvcihnYW1lX3BhdGgpOg0KICAgICIiIg0KICAgIERldGVjdHMgdGhlIG1ham9yIFJlbidQeSB2ZXJzaW9uICg2LCA3LCBvciA4KSBmcm9tIHRoZSBnYW1lIHBhdGguDQogICAgZ2FtZV9wYXRoIGNhbiBiZSB0aGUgZ2FtZSdzIHJvb3QgZm9sZGVyIG9yIHRoZSDigJxnYW1lL+KAnSBzdWJmb2xkZXIuDQogICAgIiIiDQogICAgIyBOb3JtYWxpemU6IHdlIHdhbnQgdGhlIOKAnGdhbWUv4oCdIGZvbGRlcg0KICAgIGlmIG9zLnBhdGguYmFzZW5hbWUoZ2FtZV9wYXRoKSA9PSAiZ2FtZSI6DQogICAgICAgIGdhbWVfZGlyID0gZ2FtZV9wYXRoDQogICAgZWxzZToNCiAgICAgICAgY2FuZGlkYXRlID0gb3MucGF0aC5qb2luKGdhbWVfcGF0aCwgImdhbWUiKQ0KICAgICAgICBpZiBvcy5wYXRoLmlzZGlyKGNhbmRpZGF0ZSk6DQogICAgICAgICAgICBnYW1lX2RpciA9IGNhbmRpZGF0ZQ0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgZ2FtZV9kaXIgPSBnYW1lX3BhdGggICMgd2UgdHJ5IGRpcmVjdGx5DQoNCiAgICBpZiBub3Qgb3MucGF0aC5pc2RpcihnYW1lX2Rpcik6DQogICAgICAgIHByaW50KCJFUlJPUjogZGlyZWN0b3J5IG5vdCBmb3VuZDoge30iLmZvcm1hdChnYW1lX2RpcikpDQogICAgICAgIHN5cy5leGl0KDEpDQoNCiAgICAjIDEuIHNjcmlwdF92ZXJzaW9uLnR4dCAocHJpb3JpdHkgYnV0IG9wdGlvbmFsKQ0KICAgIG1ham9yID0gZGV0ZWN0X2Zyb21fc2NyaXB0X3ZlcnNpb24oZ2FtZV9kaXIpDQogICAgaWYgbWFqb3IgaXMgbm90IE5vbmU6DQogICAgICAgIHJldHVybiBtYWpvcg0KDQogICAgIyAyLiBBcmNoaXZlcyAucnBhIChSZWxpYWJsZSBzaWduYXR1cmVzIGZvciBSZW4nUHkgOCkNCiAgICBtYWpvciA9IGRldGVjdF9mcm9tX2FyY2hpdmUoZ2FtZV9kaXIpDQogICAgaWYgbWFqb3IgaXMgbm90IE5vbmU6DQogICAgICAgICMgUlBBLTMuMCBjYW4gYmUgNiBvciA3OyB3ZSByZWZpbmUgaXQgd2l0aCB0aGUgLnJweWMgZmlsZXMuDQogICAgICAgIGlmIG1ham9yID09IDc6DQogICAgICAgICAgICBycHljX21ham9yID0gZGV0ZWN0X2Zyb21fcnB5YyhnYW1lX2RpcikNCiAgICAgICAgICAgIGlmIHJweWNfbWFqb3IgaXMgbm90IE5vbmU6DQogICAgICAgICAgICAgICAgcmV0dXJuIHJweWNfbWFqb3INCiAgICAgICAgcmV0dXJuIG1ham9yDQoNCiAgICAjIDMuIC5ycHljIGZpbGVzICh2ZXJ5IHJlbGlhYmxlIGZvciBSZW4nUHkgNiBhbmQgN"
    <nul set /p="ywgYnV0IGRvIG5vdCBkaXN0aW5ndWlzaCBiZXR3ZWVuIDcgYW5kIDgpOg0KICAgIG1ham9yID0gZGV0ZWN0X2Zyb21fcnB5YyhnYW1lX2RpcikNCiAgICBpZiBtYWpvciBpcyBub3QgTm9uZToNCiAgICAgICAgcmV0dXJuIG1ham9yDQoNCiAgICAjIDQuIFRleHQgZmlsZXMgaW4gdGhlIHJvb3QgZm9sZGVyIChtYXkgY29udGFpbiB2ZXJzaW9uIGluZm8sIGVzcGVjaWFsbHkgZm9yIFJlbidQeSA4KToNCiAgICBtYWpvciA9IGRldGVjdF9mcm9tX2V4ZWN1dGFibGUoZ2FtZV9kaXIpDQogICAgaWYgbWFqb3IgaXMgbm90IE5vbmU6DQogICAgICAgIHJldHVybiBtYWpvcg0KDQogICAgcmV0dXJuIE5vbmUNCg0KDQpkZWYgbWFpbigpOg0KICAgIGlmIGxlbihzeXMuYXJndikgPCAyOg0KICAgICAgICBwcmludCgiVXNhZ2U6IHt9IDxnYW1lX3BhdGg+Ii5mb3JtYXQoc3lzLmFyZ3ZbMF0pKQ0KICAgICAgICBzeXMuZXhpdCgxKQ0KDQogICAgZ2FtZV9wYXRoID0gc3lzLmFyZ3ZbMV0NCg0KICAgIG1ham9yID0gZGV0ZWN0X3JlbnB5X21ham9yKGdhbWVfcGF0aCkNCg0KICAgIGlmIG1ham9yIGlzIE5vbmU6DQogICAgICAgIHByaW50KCJFUlJPUjogaW1wb3NzaWJsZSB0byBkZXRlY3QgUmVuJ1B5IHZlcnNpb24gaW4gOiB7fSIuZm9ybWF0KGdhbWVfcGF0aCkpDQogICAgICAgIHN5cy5leGl0KDEpDQoNCiAgICBpZiBtYWpvciBub3QgaW4gKDYsIDcsIDgpOg0KICAgICAgICBwcmludCgiRVJST1I6IHVuZXhwZWN0ZWQgUmVuJ1B5IHZlcnNpb24gZGV0ZWN0ZWQgOiB7fSIuZm9ybWF0KG1ham9yKSkNCiAgICAgICAgc3lzLmV4aXQoMSkNCg0KICAgIHByaW50KG1ham9yKQ0KDQoNCmlmIF9fbmFtZV9fID09ICJfX21haW5fXyI6DQogICAgbWFpbigpDQo="
)

call :pwsh_exp "!renpyvers2.%LNG%!..." "%detect_renpy_version%"
if not exist "%detect_renpy_version%" (
    call :elog "%NOK%"
    call :elog .
    call :elog "!FCREATE.%LNG%! %YEL%%detect_renpy_version%%RES%. !UNACONT.%LNG%!"
    call :elog .
    pause>nul|set /p=".      !ANYKEY.%LNG%!..."

    call :exitn 3
) else (
    if %DEBUGLEVEL% GEQ 1 echo "%PYTHONHOME%python.exe" %PYNOASSERT% "%detect_renpy_version% "%WORKDIR%" >> "%UNRENLOG%"
    "%PYTHONHOME%python.exe" %PYNOASSERT% "%detect_renpy_version%" "%WORKDIR%" > "%TEMP%\renpy_version.tmp"
    set /p RENPYVERSION=<"%TEMP%\renpy_version.tmp"
    del "%TEMP%\renpy_version.tmp"
    if not defined RENPYVERSION (
        call :elog "%NOK%"
        call :elog .
        call :elog "    !renpyvers3.%LNG%!"
        call :elog "    !renpyvers4.%LNG%!. !UNACONT.%LNG%!"
        call :elog .
        pause>nul|set /p=".      !ANYKEY.%LNG%!..."

        call :exitn 3
    ) else (
        call :elog "%OK%" "!renpyvers1.%LNG%! %YEL%!RENPYVERSION!%RES%"
    )
)
if %DEBUGLEVEL% GEQ 1 echo del /f /q "%detect_renpy_version%" >> "%UNRENLOG%"
del /f /q "%detect_renpy_version%" %DEBUGREDIR%

set "renpyvers5.zh=您已启动 %SCRIPTNAME% 但检测到 Ren'Py %RENPYVERSION%。请改用 UnRen-legacy.bat。"

set "renpyvers6.zh=您已启动 %SCRIPTNAME% 但检测到 Ren'Py %RENPYVERSION%。请改用 UnRen-current.bat。"
:: Check to ensure you are using the correct UnRen version
if %RENPYVERSION% LEQ 7 (
    call :elog .
    call :elog .
    call :elog "!renpyvers5.%LNG%!"
    call :elog .
    pause>nul|set /p=".      !ANYKEY.%LNG%!..."

    call :exitn 3
)

:: Set the proper argument for py.exe according to the Ren'Py version detected
set "PYVERSION="
if %RENPYVERSION% GEQ 8 if defined PYVERSION3 (
    set "PYVERSION=%PYVERSION3%"
)
if %RENPYVERSION% LEQ 7 if defined PYVERSION2 (
    set "PYVERSION=%PYVERSION2%"
)

:: Display all the variables in the log for debugging purpose
call :DisplayVars "初始化阶段"


:: Splash screen
:menu
set "sscreen.zh=由 JoeLurmel @ f95zone.to 为粉丝制作 - %RED%<3%RES%"

if "%NOCLS%" == "0" cls
REM call :center "%ORA%__________________________________________________________________________________%RES%"
call :center "%ORA%╔═══════════════════════════════════════════════════════════════════════════════════╗%RES%"
echo               %ORA%    __  __      ____                  __          __%RES%
echo               %ORA%   / / / /___  / __ \___  ____       / /_  ____ _/ /_%RES%
echo               %ORA%  / / / / __ \/ /_/ / _ \/ __ \     / __ \/ __ ^`/ __/%RES%
echo               %ORA% / /_/ / / / / __  /  __/ / / / _  / /_/ / /_/ / /_%RES%
echo               %ORA% \____/_/ /_/_/  \_\___/_/ /_/ (_) \_.__/\__^,_/\__/ - %NAME% %CYA%%VERSION%%RES%
echo.
call :center "Sam @ www.f95zone.to & Gideon"
call :center "修改：VepsrP @ www.f95zone.to"
call :center "!sscreen.%LNG%!"
echo.
call :center "%YEL%!INCASEOF.%LNG%!%RES%"
call :center "%MAG%%URL_REF%%RES%"
echo.
REM call :center "%ORA%__________________________________________________________________________________%RES%"
call :center "%ORA%╚═══════════════════════════════════════════════════════════════════════════════════╝%RES%"

set "MTITLE.zh=工作目录："

set "choice1.zh=解包 RPA 包。"

set "choice2.zh=反编译 RPYC 文件。"

set "choice3.zh=解包 RPA 文件时进行反混淆 %YEL%（使用基础代码）"

set "choice4.zh=反编译 RPYC 文件时进行反混淆 %YEL%（使用基础代码）"

set "choice5.zh=解包并反编译（RPA 和 RPYC）"

set "choice6.zh=对 RPA 和 RPYC 文件进行反混淆、解包和反编译 %YEL%（使用基础代码）"

set "choice7.zh=使用替代方法解包 RPA 包。"

set "minfo1.zh=以下选项与 Ren'Py 版本无关。"

set "choicea.zh=启用控制台（Shift+O）和开发者菜单（Shift+D）"

set "choiceb.zh=启用调试模式 %RED%（可能会破坏游戏）%RES%"

set "choicec.zh=强制跳过（未读文本、选择后）"

set "choiced.zh=强制全部跳过（未读文本、选择后、过渡）"

set "choicee.zh=强制启用 'Rollback'（滚轮）"

set "choicef.zh=启用 'Quick Save' (Shift+S, F5) 和 'Quick Load' (Shift+L, F9)。"

set "choiceg.zh=尝试强制显示 'Quick Menu'。"

set "choiceh.zh=下载并添加 ZLZK 的通用画廊解锁器"

set "choicei.zh=下载并添加 ZLZK 的通用选择描述器"

set "choicej.zh=下载并添加 Penfold Mole 的通用透明文本框 Mod"

set "choicek.zh=下载并添加 0x52_URM by 0x52。"

set "choicel.zh=替换任何角色的名字。"

set "choicen.zh=在 %YEL%AppData%RES% 子文件夹中删除那个不好的同步文件夹。"

set "choicep.zh=添加自定义插件。"

set "choicer.zh=还原原始文件。"

set "choices.zh=删除备份。"

set "choicet.zh=提取文本用于翻译目的"


set "minfo2.zh=以下选项需要管理员权限。"

set "minfo2a.zh=以下选项不再需要管理员权限。"

set "choice+.zh=添加右键菜单项以运行脚本。"

set "choice-.zh=从注册表中移除右键菜单项。"

set "mquest.zh=您的选择（1-7、a-l、p、r、s、t、+、-、x，默认 [%YEL%%MDEFS2%%RES%]）："

set "choicex.zh=退出"

set "uchoice.zh=未知选择："

:: Menu display
echo.
call :center "!MTITLE.%LNG%!%YEL%%WORKDIR%%RES%"
echo.
echo        1) %GRE%!choice1.%LNG%!%RES%
echo        2) %GRE%!choice2.%LNG%!%RES%
echo        3) %GRY%!choice3.%LNG%!%RES%
echo        4) %GRE%!choice4.%LNG%!%RES%
echo        5) %GRE%!choice5.%LNG%!%RES%
echo        6) %GRE%!choice6.%LNG%!%RES%
echo        7) %GRE%!choice7.%LNG%!%RES%
echo.
echo        %YEL%!minfo1.%LNG%!%RES%
echo        a) %CYA%!choicea.%LNG%!%RES%
echo        b) %CYA%!choiceb.%LNG%!%RES%
echo        c) %CYA%!choicec.%LNG%!%RES%
echo        d) %CYA%!choiced.%LNG%!%RES%
echo        e) %CYA%!choicee.%LNG%!%RES%
echo        f) %CYA%!choicef.%LNG%!%RES%
echo        g) %CYA%!choiceg.%LNG%!%RES%
echo        h) %CYA%!choiceh.%LNG%!%RES%
echo        i) %CYA%!choicei.%LNG%!%RES%
echo        j) %CYA%!choicej.%LNG%!%RES%
echo        k) %CYA%!choicek.%LNG%!%RES%
echo        l) %CYA%!choicel.%LNG%!%RES%
echo        n) %CYA%!choicen.%LNG%!%RES%
echo        p) %CYA%!choicep.%LNG%!%RES%
echo        r) %YEL%!choicer.%LNG%!%RES%
echo        s) %YEL%!choices.%LNG%!%RES%
echo        t) %CYA%!choicet.%LNG%!%RES%
echo.
set OLDREG=0
call :check_old_reg
if %OLDREG% EQU 1 (
    echo        %YEL%!minfo2.%LNG%!%RES%
) else (
    echo        %YEL%!minfo2a.%LNG%!%RES%
)
echo        +) %CYA%!choice+.%LNG%!%RES%
echo        -) %CYA%!choice-.%LNG%!%RES%
echo.
echo        x) %YEL%!choicex.%LNG%!%RES%

:: Reading the selection
echo.
echo.
set "OPTIONS="
set /p "OPTIONS=!mquest.%LNG%!"
if not defined OPTIONS set "OPTIONS=!MDEFS2!"
set "OPTIONS=%OPTIONS: =%"

:: List of valid characters
set "VALID=1234567abctdefghijklnprst+-x"

:: Dispatch table: OPTION → LABEL
set "ACT.1=extract_rpa"
set "ACT.2=decompile"
set "ACT.3=extract_wkey"
set "ACT.4=decompile"
set "ACT.5=extract_rpa"
set "ACT.6=extract_rpa"
set "ACT.7=extract_rpa"

set "ACT.a=console"
set "ACT.b=debug"
set "ACT.c=skip"
set "ACT.d=skipall"
set "ACT.e=rollback"
set "ACT.f=quick"
set "ACT.g=qmenu"
set "ACT.h=add_ugu"
set "ACT.i=add_ucd"
set "ACT.j=add_utbox"
set "ACT.k=add_urm"
set "ACT.l=replace_anyname"
set "ACT.n=nasty_sync"
set "ACT.p=add_custom_addon"
set "ACT.r=restore_files"
set "ACT.s=delete_backups"
set "ACT.t=extract_text"

set "ACT.+=add_reg"
set "ACT.-=remove_reg"
set "ACT.x=exitn"

:: Loop through each character in the input
:: First, check for invalid characters
:: Process each character in input, in order
for /L %%I in (0,1,15) do (
    set "OPTION=!OPTIONS:~%%I,1!"
    if "!OPTION!"=="" goto :end_process

    echo "!VALID!" |  "%SystemRoot%\System32\findstr.exe"  /IC:"!OPTION!" >nul || (
        echo.
        echo %RED%!uchoice.%LNG%! %YEL%!OPTION!%RES%
        timeout /T 2 %DEBUGREDIR%
        goto :end_process
    )

    set "LABEL="
    REM Indirection: building ACT.<OPTION> properly
    for %%# in (!OPTION!) do set "LABEL=!ACT.%%#!"

    if defined LABEL (
        if /i "!LABEL!"=="exitn" call :exitn 0
        call :!LABEL!
        set "MDEFS2=x"
    )
)

:end_process
timeout /T 2 %DEBUGREDIR%
goto :menu


:extract_rpa
set "extm1.zh=提取后是否删除 RPA 存档？输入 [Y/N]（默认 N）："

set "extm2.zh=RPA 存档将被重命名为 .org 扩展名。"

set "extm3.zh=RPA 存档将在提取后被删除。"

set "extm4.zh=解包全部还是选择 RPA 存档？输入 [A/S]（默认 A）："

set "extm5.zh=您将选择要解包的 RPA 存档。"

set "extm6.zh=所有 RPA 存档将被解包。"

set "extm7.zh=正在创建 RPA 版本检测脚本"

set "extm8.zh=在游戏目录中搜索 RPA 文件"

set "extm9.zh=正在创建 rpatool 脚本"

set "extm9a.zh=正在创建 altrpatool 脚本"

set "extm10.zh=RPA 扩展名已重命名为："

set "extm11.zh=未检测到 RPA 存档。"

set "extm12.zh=处理 RPA 文件时出错："

:: set extm13 to extm15 are set later in the code because of the dynamic variables.

set "extm16.zh=正在解包文件"

set "extm17.zh=是否要解包 RPA 存档："

:: set extm18 to extm22 are set later in the code because of the dynamic variables.

set "extm23.zh=找到扩展名："

:: set extm26 are set later in the code because of the dynamic variables.

set "extm27.zh=正在创建 RPA 存档检测脚本"

setlocal disabledelayedexpansion
for /f "delims=" %%A in ("%WORKDIR%") do (
    endlocal
    cd /d "%%A"
)

call :DisplayVars "RPA 解包阶段"

:: Detect RPA extension
set "rpaExt="

:: Create Python script to detect RPA extension
call :elog .
set "detect_rpa_ext=%TEMP%\detect_rpa_ext.py"
>"%detect_rpa_ext%.b64" (
    <nul set /p="IyEvdXNyL2Jpbi9lbnYgcHl0aG9uDQojIC0qLSBjb2Rpbmc6IHV0Zi04IC0qLQ0KDQojIFdyaXR0ZW4gYnkgU00gYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCiMgVmVyc2lvbiAwLjQgLSAyMDI1LTEyLTI2DQoNCmZyb20gX19mdXR1cmVfXyBpbXBvcnQgcHJpbnRfZnVuY3Rpb24NCmltcG9ydCBvcw0KaW1wb3J0IHN5cw0KDQoNCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tDQojIE5vcm1hbGl6ZSBpbnB1dCBwYXRoDQojIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQ0KZGVmIG5vcm1hbGl6ZV9wYXRoKGFyZyk6DQogICAgcCA9IGFyZy5zdHJpcCgpLnN0cmlwKCdcJyInKQ0KICAgIHJldHVybiBwDQoNCg0KaWYgbGVuKHN5cy5hcmd2KSA+IDE6DQogICAgcmF3ID0gc3lzLmFyZ3ZbMV0NCiAgICBnYW1lX2RpciA9IG5vcm1hbGl6ZV9wYXRoKHJhdykNCmVsc2U6DQogICAgZ2FtZV9kaXIgPSBvcy5nZXRjd2QoKQ0KDQpnYW1lX2RpciA9IG9zLnBhdGguYWJzcGF0aChnYW1lX2RpcikNCm9zLmNoZGlyKGdhbWVfZGlyKQ0KDQoNCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tDQojIFRyeSB0byBsb2FkIFJlbidQeSBhcmNoaXZlIGhhbmRsZXJzIHNhZmVseQ0KIyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0NCmRlZiB0cnlfcmVucHlfaGFuZGxlcnMoKToNCiAgICB0cnk6DQogICAgICAgIGltcG9ydCByZW5weS5vYmplY3QNCiAgICAgICAgaW1wb3J0IHJlbnB5LmxvYWRlcg0KDQogICAgICAgIHRyeToNCiAgICAgICAgICAgIGltcG9ydCByZW5weS5lcnJvcg0KICAgICAgICAgICAgaW1wb3J0IHJlbnB5LmNvbmZpZw0KICAgICAgICBleGNlcHQgRXhjZXB0aW9uOg0KICAgICAgICAgICAgcGFzcw0KDQogICAgICAgIHRyeToNCiAgICAgICAgICAgIGFoID0gcmVucHkubG9hZGVyLmFyY2hpdmVfaGFuZGxlcnMNCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoNCiAgICAgICAgICAgIHJldHVybiBOb25lDQoNCiAgICAgICAgaGFuZGxlcnMgPSBnZXRhdHRyKGFoLCAiaGFuZGxlcnMiLCBhaCkNCg0KICAgICAgICBleHRzID0gW10NCiAgICAgICAgdHJ5Og0KICAgICAgICAgICAgZm9yIGggaW4gaGFuZGxlcnM6DQogICAgICAgICAgICAgICAgaWYgaGFzYXR0cihoLCAiZ2V0X3N1cHBvcnRlZF9leHRlbnNpb25zIik6DQogICAgICAgICAgICAgICAgICAgIGV4dHMuZXh0ZW5kKGguZ2V0X3N1cHBvcnRlZF9leHRlbnNpb25zKCkpDQogICAgICAgICAgICAgICAgZWxpZiBoYXNhdHRyKGgsICJnZXRfc3VwcG9ydGVkX2V4dCIpOg0KICAgICAgICAgICAgICAgICAgICBleHRzLmV4dGVuZChoLmdldF9zdXBwb3J0ZWRfZXh0KCkpDQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb246DQogICAgICAgICAgICByZXR1cm4gTm9uZQ0KDQogICAgICAgIGV4dHMgPSBzb3J0ZWQoc2V0KGUgZm9yIGUgaW4gZXh0cyBpZiBpc2luc3RhbmNlKGUsIChzdHIsIGJ5dGVzKSkpKQ0KICAgICAgICByZXR1cm4gZXh0cyBvciBOb25lDQoNCiAgICBleGNlcHQgRXhjZXB0aW9uOg0KICAgICAgICByZXR1cm4gTm9uZQ0KDQoNCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tDQojIERldGVjdCByZWFsIFJQQSBhcmNoaXZlcyBieSByZWFkaW5nIHRoZSBoZWFkZXINCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tDQpkZWYgaXNfcnBhX2ZpbGUocGF0aCk6DQogICAgdHJ5Og0KICAgICAgICB3aXRoIG9wZW4ocGF0aCwgInJiIikgYXMgZjoNCiAgICAgICAgICAgIHNpZyA9IGYucmVhZCg4KQ0KICAgICAgICByZXR1cm4gc2lnLnN0YXJ0c3dpdGgoYiJSUEEtIikNCiAgICBleGNlcHQgRXhjZXB0aW9uOg0KICAgICAgICByZXR1cm4gRmFsc2UNCg0KDQpkZWYgc2Nhbl9wcmVzZW50X2FyY2hpdmVzKGJhc2VfZGlyKToNCiAgICBleHRzID0gc2V0KCkNCg0KICAgIGRlZiBzY2FuKGQpOg0KICAgICAgICB0cnk6DQogICAgICAgICAgICBmb3IgbmFtZSBpbiBvcy5saXN0ZGlyKGQpOg0KICAgICAgICAgICAgICAgIGZ1bGwgPSBvcy5wYXRoLmpvaW4oZCwgbmFtZSkNCiAgICAgICAgICAgICAgICBpZiBub3Qgb3MucGF0aC5pc2ZpbGUoZnVsbCk6DQogICAgICAgICAgICAgICAgICAgIGNvbnRpbnVlDQogICAgICAgICAgICAgICAgaWYgb3MucGF0aC5zcGxpdGV4dChuYW1lKVsxXS5sb3dlcigpID09ICcub3JnJzoNCiAgICAgICAgICAgICAgICAgICAgY29udGludWUNCiAgICAgICAgICAgICAgICBpZiBpc19ycGFfZmlsZShmdWxsKToNCiAgICAgICAgICAgICAgICAgICAgXywgZXh0ID0gb3MucGF0aC5zcGxpdGV4dChuYW1lKQ0KICAgICAgICAgICAgICAgICAgICBpZiBleHQ6DQogICAgICAgICAgICAgICAgICAgICAgICBleHRzLmFkZChleHQubG93ZXIoKSkNCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoNCiAgICAgICAgICAgIHBhc3MNCg0KICAgIHNjYW4oYmFzZV9kaXIpDQoNCiAgICBnYW1lX3N1YiA9IG9zLnBhdGguam9pbihiYXNlX2RpciwgImdhbWUiKQ0KICAgIGlmIG9zLnBhdGguaXNkaXIoZ2FtZV9zdWIpOg0KICAgICAgICBzY2FuKGdhbWVfc3ViKQ0KDQogICAgcmV0dXJuIHNvcnRlZChleHRzKQ0KDQoNCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tDQojIEh5YnJpZCBkZXRlY3Rpb24gc3RyYXRlZ3kNCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tDQpkZWYgZGV0ZWN0X2FyY2hpdmVfZXh0ZW5zaW9ucyhiYXNlX2Rpcik6DQogICAgZXh0cyA9IHRyeV9yZW5weV9oYW5kbGVycygpDQogICAgaWYgZXh0czoNCiAgICAgICAgcmV0dXJuIGV4dHMNCg0KICAgIGV4dHMgPSBzY2FuX3ByZXNlbnRfYXJjaGl2ZXMoYmFzZV9kaXIpDQogICAgaWYgZXh0czoNCiAgICAgICAgcmV0dXJuIGV4dHMNCg0KICAgIHJldHVybiBbIi5ycGEiXQ0KDQoNCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tDQojIE1haW4gZW50cnkgcG9pbnQNCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tDQpkZWYgbWFpbigpOg0KICAgIGV4dHMgPSBkZXRlY3RfYXJjaGl2ZV9leHRlbnNpb25zKGdhbWVfZGlyKQ0KDQogICAgdHJ5Og0KICAgICAgICBvdXQgPSBzeXMuc3Rkb3V0DQogICAgICAgIGlmIGhhc2F0dHIob3V0LCAiYnVmZmVyIik6DQogICAgICAgICAgICBvdXQuYnVmZmVyLndyaXRlKChyZXByKGV4dHMpICsgIlxuIikuZW5jb2RlKCJ1dGYtOCIsICJyZXBsYWNlIikpDQogICAgICAgIGVsc2U6DQogICAgICAgICAgICBwcmludChyZXByKGV4dHMpKQ0KICAgIGV4Y2VwdCBFeGNlcHRpb246DQogICAgICAgIHByaW50KGV4dHMpDQoNCiAgICBzeXMuZXhpdCgwIGlmIGV4dHMgZWxzZSAxKQ0KDQoNCmlmIF9fbmFtZV9fID09ICJfX21haW5fXyI6DQogICAgbWFpbigp"
)

call :elog .
call :pwsh_exp "!extm7.%LNG%!..." "%detect_rpa_ext%"
if not exist "!detect_rpa_ext!" (
    call :elog "%NOK%" "!FCREATE.%LNG%! %YEL%!detect_rpa_ext!%RES%"
    goto :rpa_cleanup
) else (
    call :elog "%OK%"
)

:: Run the script and capture the output
if %DEBUGLEVEL% GEQ 1 echo "%PYTHONHOME%python.exe" %PYNOASSERT% "%detect_rpa_ext%" "%WORKDIR%" >> %UNRENLOG%
"%PYTHONHOME%python.exe" %PYNOASSERT% "%detect_rpa_ext%" "%WORKDIR%" > "%TEMP%\extlist.tmp"
set /p EXTLINE=<"%TEMP%\extlist.tmp"
del /f /q "%TEMP%\extlist.tmp" %DEBUGREDIR%
del /f /q "%detect_rpa_ext%" %DEBUGREDIR%

:: Clean the line to remove snags, dot and hooks.
if defined EXTLINE (
    set EXTLINE=!EXTLINE:[=!
    set EXTLINE=!EXTLINE:]=!
    set EXTLINE=!EXTLINE:'=!
    set EXTLINE=!EXTLINE:,= !
    set EXTLINE=!EXTLINE:.=!
    echo "!EXTLINE!" |  "%SystemRoot%\System32\findstr.exe" /i "rpa" >nul
    if !errorlevel! GEQ 1 (
        set "rpaExt=!EXTLINE! rpa"
    ) else (
        set "rpaExt=!EXTLINE!"
    )
) else (
    set "rpaExt=rpa"
)

call :elog -n "%EMPTY%" "!extm8.%LNG%!..."

:: Search first with known extensions
set "file_found="
for %%e in (!rpaExt!) do (
    for /R .\game %%f in (*.%%e) do (
        if exist "%%f" (
            set "file_found=1"
            set "rpaExt=%%e"
            if /I not "!rpaExt!" == "rpa" (
                call :elog "%OK%" "!extm10.%LNG%! %YEL%!rpaExt!%RES%"
            ) else (
                call :elog "%OK%" "!extm23.%LNG%! %YEL%!rpaExt!%RES%"
            )
        )
        goto :found_ext
    )
)

:: If no RPA found
if not defined file_found (
    call :elog "%SKIP%" "!extm11.%LNG%!"
    call :elog .
    goto :rpa_cleanup
)

:found_ext
call :elog .
set "extans="
call :choiceEx "!extm1.%LNG%!" "OSJYN" "N" "%CTIME%" "-rawMsg"
if errorlevel 5 (
    set "extans=n"
) else if errorlevel 4 (
    set "extans=y"
) else if errorlevel 3 (
    set "extans=y"
) else if errorlevel 2 (
    set "extans=y"
) else if errorlevel 1 (
    set "extans=y"
)
set "extans=%extans: =%"
set "delrpa="
if /i "%extans%" == "n" (
	set "delrpa=n"
	call :elog "    %YEL%!extm2.%LNG%!%RES%"
) else (
	set "delrpa=y"
	call :elog "    %YEL%!extm3.%LNG%!%RES%"
)

:: Ask if we want to extract all RPA or select
call :elog .
set "extans="
set "def=A"
call :choiceEx "!extm4.%LNG%! " "ATS" "%def%" "%CTIME%" "-rawMsg"
if errorlevel 3 (
    set "extans=s"
) else if errorlevel 2 (
    set "extans=a"
) else if errorlevel 1 (
    set "extans=a"
)
set "extans=%extans: =%"
if /i "%extans%" == "s" (
    set "extract_all_rpa=n"
    call :elog "    %YEL%!extm5.%LNG%!%RES%"
) else (
    set "extract_all_rpa=y"
    call :elog "    %YEL%!extm6.%LNG%!%RES%"
)

:: detect_archive.py
set "detect_archive=%TEMP%\detect_archive.py"
>"%detect_archive%.b64" (
    <nul set /p="IyEvdXNyL2Jpbi9lbnYgcHl0aG9uDQppbXBvcnQgc3lzDQoNCmRlZiBkZXRlY3RfYXJjaGl2ZV90eXBlKHBhdGgpOg0KICAgIHRyeToNCiAgICAgICAgd2l0aCBvcGVuKHBhdGgsICJyYiIpIGFzIGY6DQogICAgICAgICAgICBoZWFkZXIgPSBmLnJlYWQoOCkNCiAgICAgICAgICAgICMgU3RhbmRhcmQgUlBBIGFyY2hpdmVzIHN0YXJ0IHdpdGggIlJQQS0zLjAiIG9yICJSUEEtMi4wIiBvciAiU1ZBQy0xLjAiIG9yICJSV0EtMy4wICINCiAgICAgICAgICAgIGlmIGhlYWRlci5zdGFydHN3aXRoKGIiUlBBLSIpIG9yIGhlYWRlci5zdGFydHN3aXRoKGIiU1ZBQy0iKSBvciBoZWFkZXIuc3RhcnRzd2l0aChiIlJXQS0zLjAgIik6DQogICAgICAgICAgICAgICAgcmV0dXJuIDAgICMgc3RhbmRhcmQNCiAgICAgICAgICAgIGVsc2U6DQogICAgICAgICAgICAgICAgcmV0dXJuIDEgICMgbW9kaWZpZWQgLyB1bmtub3duDQogICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOg0KICAgICAgICAjIFB5dGhvbiAyIGRvZXNuJ3Qgc3VwcG9ydCBmLXN0cmluZ3MsIHNvIHdlIHVzZSBmb3JtYXQoKQ0KICAgICAgICBzeXMuc3RkZXJyLndyaXRlKCJFcnJvcjoge31cbiIuZm9ybWF0KGUpKQ0KICAgICAgICByZXR1cm4gMSAgIyBieSBkZWZhdWx0LCB3ZSBjb25zaWRlciBtb2RpZmllZA0KDQppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOg0KICAgIGlmIGxlbihzeXMuYXJndikgPCAyOg0KICAgICAgICBwcmludCgiVXNhZ2U6IGRldGVjdF9hcmNoaXZlLnB5IDxhcmNoaXZlX2ZpbGU+IikNCiAgICAgICAgc3lzLmV4aXQoMSkNCg0KICAgIGFyY2hpdmVfZmlsZSA9IHN5cy5hcmd2WzFdDQogICAgcmVzdWx0ID0gZGV0ZWN0X2FyY2hpdmVfdHlwZShhcmNoaXZlX2ZpbGUpDQogICAgc3lzLmV4aXQocmVzdWx0KQ0K"
)

call :elog .
call :pwsh_exp "!extm27.%LNG%!..." "%detect_archive%"
if not exist "%detect_archive%" (
    call :elog "%NOK%" "!FCREATE.%LNG%! %YEL%%detect_archive%%RES%"
    goto :rpa_cleanup
) else (
    call :elog "%OK%"
)

:: Creating rpatool and altrpatool from our base64 strings
:: rpatool by Shizmob 9a58396 2019-02-22T17:31:07.000Z
::  https://github.com/Shizmob/rpatool
::  Version 0.8 wo pickle5 for Ren'Py <= 7
set "rpatool=%WORKDIR%\rpatool.py"
set "altrpatool=%WORKDIR%\altrpatool.py"
if "%RPATOOL_NEW%" == "n" (
    >"%rpatool%.b64" (
        <nul set /p="IyEvdXNyL2Jpbi9lbnYgcHl0aG9uDQoNCmZyb20gX19mdXR1cmVfXyBpbXBvcnQgcHJpbnRfZnVuY3Rpb24NCg0KaW1wb3J0IHN5cw0KaW1wb3J0IG9zDQppbXBvcnQgY29kZWNzDQppbXBvcnQgcGlja2xlDQppbXBvcnQgZXJybm8NCmltcG9ydCByYW5kb20NCg0KaWYgc3lzLnZlcnNpb25faW5mb1swXSA+PSAzOg0KICAgIGRlZiBfdW5pY29kZSh0ZXh0KToNCiAgICAgICAgcmV0dXJuIHRleHQNCg0KICAgIGRlZiBfcHJpbnRhYmxlKHRleHQpOg0KICAgICAgICByZXR1cm4gdGV4dA0KDQogICAgZGVmIF91bm1hbmdsZShkYXRhKToNCiAgICAgICAgcmV0dXJuIGRhdGEuZW5jb2RlKCdsYXRpbjEnKQ0KDQogICAgZGVmIF91bnBpY2tsZShkYXRhKToNCiAgICAgICAgIyBTcGVjaWZ5IGxhdGluMSBlbmNvZGluZyB0byBwcmV2ZW50IHJhdyBieXRlIHZhbHVlcyBmcm9tIGNhdXNpbmcgYW4gQVNDSUkgZGVjb2RlIGVycm9yLg0KICAgICAgICByZXR1cm4gcGlja2xlLmxvYWRzKGRhdGEsIGVuY29kaW5nPSdsYXRpbjEnKQ0KZWxpZiBzeXMudmVyc2lvbl9pbmZvWzBdID09IDI6DQogICAgZGVmIF91bmljb2RlKHRleHQpOg0KICAgICAgICBpZiBpc2luc3RhbmNlKHRleHQsIHVuaWNvZGUpOg0KICAgICAgICAgICAgcmV0dXJuIHRleHQNCiAgICAgICAgcmV0dXJuIHRleHQuZGVjb2RlKCd1dGYtOCcpDQoNCiAgICBkZWYgX3ByaW50YWJsZSh0ZXh0KToNCiAgICAgICAgcmV0dXJuIHRleHQuZW5jb2RlKCd1dGYtOCcpDQoNCiAgICBkZWYgX3VubWFuZ2xlKGRhdGEpOg0KICAgICAgICByZXR1cm4gZGF0YQ0KDQogICAgZGVmIF91bnBpY2tsZShkYXRhKToNCiAgICAgICAgcmV0dXJuIHBpY2tsZS5sb2FkcyhkYXRhKQ0KDQpjbGFzcyBSZW5QeUFyY2hpdmU6DQogICAgZmlsZSA9IE5vbmUNCiAgICBoYW5kbGUgPSBOb25lDQoNCiAgICBmaWxlcyA9IHt9DQogICAgaW5kZXhlcyA9IHt9DQoNCiAgICB2ZXJzaW9uID0gTm9uZQ0KICAgIHBhZGxlbmd0aCA9IDANCiAgICBrZXkgPSBOb25lDQogICAgdmVyYm9zZSA9IEZhbHNlDQoNCiAgICBSUEEyX01BR0lDID0gJ1JQQS0yLjAgJw0KICAgIFJQQTNfTUFHSUMgPSAnUlBBLTMuMCAnDQogICAgUlBBM18yX01BR0lDID0gJ1JQQS0zLjIgJw0KDQogICAgIyBGb3IgYmFja3dhcmQgY29tcGF0aWJpbGl0eSwgb3RoZXJ3aXNlIFB5dGhvbjMtcGFja2VkIGFyY2hpdmVzIHdvbid0IGJlIHJlYWQgYnkgUHl0aG9uMg0KICAgIFBJQ0tMRV9QUk9UT0NPTCA9IDINCg0KICAgIGRlZiBfX2luaXRfXyhzZWxmLCBmaWxlID0gTm9uZSwgdmVyc2lvbiA9IDMsIHBhZGxlbmd0aCA9IDAsIGtleSA9IDB4REVBREJFRUYsIHZlcmJvc2UgPSBGYWxzZSk6DQogICAgICAgIHNlbGYucGFkbGVuZ3RoID0gcGFkbGVuZ3RoDQogICAgICAgIHNlbGYua2V5ID0ga2V5DQogICAgICAgIHNlbGYudmVyYm9zZSA9IHZlcmJvc2UNCg0KICAgICAgICBpZiBmaWxlIGlzIG5vdCBOb25lOg0KICAgICAgICAgICAgc2VsZi5sb2FkKGZpbGUpDQogICAgICAgIGVsc2U6DQogICAgICAgICAgICBzZWxmLnZlcnNpb24gPSB2ZXJzaW9uDQoNCiAgICBkZWYgX19kZWxfXyhzZWxmKToNCiAgICAgICAgaWYgc2VsZi5oYW5kbGUgaXMgbm90IE5vbmU6DQogICAgICAgICAgICBzZWxmLmhhbmRsZS5jbG9zZSgpDQoNCiAgICAjIERldGVybWluZSBhcmNoaXZlIHZlcnNpb24uDQogICAgZGVmIGdldF92ZXJzaW9uKHNlbGYpOg0KICAgICAgICBzZWxmLmhhbmRsZS5zZWVrKDApDQogICAgICAgIG1hZ2ljID0gc2VsZi5oYW5kbGUucmVhZGxpbmUoKS5kZWNvZGUoJ3V0Zi04JykNCg0KICAgICAgICBpZiBtYWdpYy5zdGFydHN3aXRoKHNlbGYuUlBBM18yX01BR0lDKToNCiAgICAgICAgICAgIHJldHVybiAzLjINCiAgICAgICAgZWxpZiBtYWdpYy5zdGFydHN3aXRoKHNlbGYuUlBBM19NQUdJQyk6DQogICAgICAgICAgICByZXR1cm4gMw0KICAgICAgICBlbGlmIG1hZ2ljLnN0YXJ0c3dpdGgoc2VsZi5SUEEyX01BR0lDKToNCiAgICAgICAgICAgIHJldHVybiAyDQogICAgICAgIGVsaWYgc2VsZi5maWxlLmVuZHN3aXRoKCcucnBpJyk6DQogICAgICAgICAgICByZXR1cm4gMQ0KDQogICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ3RoZSBnaXZlbiBmaWxlIGlzIG5vdCBhIHZhbGlkIFJlblwnUHkgYXJjaGl2ZSwgb3IgYW4gdW5zdXBwb3J0ZWQgdmVyc2lvbicpDQoNCiAgICAjIEV4dHJhY3QgZmlsZSBpbmRleGVzIGZyb20gb3BlbmVkIGFyY2hpdmUuDQogICAgZGVmIGV4dHJhY3RfaW5kZXhlcyhzZWxmKToNCiAgICAgICAgc2VsZi5oYW5kbGUuc2VlaygwKQ0KICAgICAgICBpbmRleGVzID0gTm9uZQ0KDQogICAgICAgIGlmIHNlbGYudmVyc2lvbiBpbiBbMiwgMywgMy4yXToNCiAgICAgICAgICAgICMgRmV0Y2ggbWV0YWRhdGEuDQogICAgICAgICAgICBtZXRhZGF0YSA9IHNlbGYuaGFuZGxlLnJlYWRsaW5lKCkNCiAgICAgICAgICAgIHZhbHMgPSBtZXRhZGF0YS5zcGxpdCgpDQogICAgICAgICAgICBvZmZzZXQgPSBpbnQodmFsc1sxXSwgMTYpDQogICAgICAgICAgICBpZiBzZWxmLnZlcnNpb24gPT0gMzoNCiAgICAgICAgICAgICAgICBzZWxmLmtleSA9IDANCiAgICAgICAgICAgICAgICBmb3Igc3Via2V5IGluIHZhbHNbMjpdOg0KICAgICAgICAgICAgICAgICAgICBzZWxmLmtleSBePSBpbnQoc3Via2V5LCAxNikNCiAgICAgICAgICAgIGVsaWYgc2VsZi52ZXJzaW9uID09IDMuMjoNCiAgICAgICAgICAgICAgICBzZWxmLmtleSA9IDANCiAgICAgICAgICAgICAgICBmb3Igc3Via2V5IGluIHZhbHNbMzpdOg0KICAgICAgICAgICAgICAgICAgICBzZWxmLmtleSBePSBpbnQoc3Via2V5LCAxNikNCg0KICAgICAgICAgICAgIyBMb2FkIGluIGluZGV4ZXMuDQogICAgICAgICAgICBzZWxmLmhhbmRsZS5zZWVrKG9mZnNldCkNCiAgICAgICAgICAgIGNvbnRlbnRzID0gY29kZWNzLmRlY29kZShzZWxmLmhhbmRsZS5yZWFkKCksICd6bGliJykNCiAgICAgICAgICAgIGluZGV4ZXMgPSBfdW5waWNrbGUoY29udGVudHMpDQoNCiAgICAgICAgICAgICMgRGVvYmZ1c2NhdGUgaW5kZXhlcy4NCiAgICAgICAgICAgIGlmIHNlbGYudmVyc2lvbiBpbiBbMywgMy4yXToNCiAgICAgICAgICAgICAgICBvYmZ1c2NhdGVkX2luZGV4ZXMgPSBpbmRleGVzDQogICAgICAgICAgICAgICAgaW5kZXhlcyA9IHt9DQogICAgICAgICAgICAgICAgZm9yIGkgaW4gb2JmdXNjYXRlZF9pbmRleGVzLmtleXMoKToNCiAgICAgICAgICAgICAgICAgICAgaWYgbGVuKG9iZnVzY2F0ZWRfaW5kZXhlc1tpXVswXSkgPT0gMjoNCiAgICAgICAgICAgICAgICAgICAgICAgIGluZGV4ZXNbaV0gPSBbIChvZmZzZXQgXiBzZWxmLmtleSwgbGVuZ3RoIF4gc2VsZi5rZXkpIGZvciBvZmZzZXQsIGxlbmd0aCBpbiBvYmZ1c2NhdGVkX2luZGV4ZXNbaV0gXQ0KICAgICAgICAgICAgICAgICAgICBlbHNlOg0KICAgICAgICAgICAgICAgICAgICAgICAgaW5kZXhlc1tpXSA9IFsgKG9mZnNldCBeIHNlbGYua2V5LCBsZW5ndGggXiBzZWxmLmtleSwgcHJlZml4KSBmb3Igb2Zmc2V0LCBsZW5ndGgsIHByZWZpeCBpbiBvYmZ1c2NhdGVkX2luZGV4ZXNbaV0gXQ0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgaW5kZXhlcyA9IHBpY2tsZS5sb2Fkcyhjb2RlY3MuZGVjb2RlKHNlbGYuaGFuZGxlLnJlYWQoKSwgJ3psaWInKSkNCg0KICAgICAgICByZXR1cm4gaW5kZXhlcw0KDQogICAgIyBHZW5lcmF0ZSBwc2V1ZG9yYW5kb20gcGFkZGluZyAoZm9yIHdoYXRldmVyIHJlYXNvbikuDQogICAgZGVmIGdlbmVyYXRlX3BhZGRpbmcoc2VsZik6DQogICAgICAgIGxlbmd0aCA9IHJhbmRvbS5yYW5kaW50KDEsIHNlbGYucGFkbGVuZ3RoKQ0KDQogICAgICAgIHBhZGRpbmcgPSAnJw0KICAgICAgICB3aGlsZSBsZW5ndGggPiAwOg0KICAgICAgICAgICAgcGFkZGluZyArPSBjaHIocmFuZG9tLnJhbmRpbnQoMSwgMjU1KSkNCiAgICAgICAgICAgIGxlbmd0aCAtPSAxDQoNCiAgICAgICAgcmV0dXJuIHBhZGRpbmcNCg0KICAgICMgQ29udmVydHMgYSBmaWxlbmFtZSB0byBhcmNoaXZlIGZvcm1hdC4NCiAgICBkZWYgY29udmVydF9maWxlbmFtZShzZWxmLCBmaWxlbmFtZSk6DQogICAgICAgIChkcml2ZSwgZmlsZW5hbWUpID0gb3MucGF0aC5zcGxpdGRyaXZlKG9zLnBhdGgubm9ybXBhdGgoZmlsZW5hbWUpLnJlcGxhY2Uob3Muc2VwLCAnLycpKQ0KICAgICAgICByZXR1cm4gZmlsZW5hbWUNCg0KICAgICMgRGVidWcgKHZlcmJvc2UpIG1lc3NhZ2VzLg0KICAgIGRlZiB2ZXJib3NlX3ByaW50KHNlbGYsIG1lc3NhZ2UpOg0KICAgICAgICBpZiBzZWxmLnZlcmJvc2U6DQogICAgICAgICAgICBwcmludChtZXNzYWdlKQ0KDQoNCiAgICAjIExpc3QgZmlsZXMgaW4gYXJjaGl2ZSBhbmQgY3VycmVudCBpbnRlcm5hbCBzdG9yYWdlLg0KICAgIGRlZiBsaXN0KHNlbGYpOg0KICAgICAgICByZXR1cm4gbGlzdChzZWxmLmluZGV4ZXMua2V5cygpKSArIGxpc3Qoc2VsZi5maWxlcy5rZXlzKCkpDQoNCiAgICAjIENoZWNrIGlmIGEgZmlsZSBleGlzdHMgaW4gdGhlIGFyY2hpdmUuDQogICAgZGVmIGhhc19maWxlKHNlbGYsIGZpbGVuYW1lKToNCiAgICAgICAgZmlsZW5hbWUgPSBfdW5pY29kZShmaWxlbmFtZSkNCiAgICAgICAgcmV0dXJuIGZpbGVuYW1lIGluIHNlbGYuaW5kZXhlcy5rZXlzKCkgb3IgZmlsZW5hbWUgaW4gc2VsZi5maWxlcy5rZXlzKCkNCg0KICAgICMgUmVhZCBmaWxlIGZyb20gYXJjaGl2ZSBvciBpbnRlcm5hbCBzdG9yYWdlLg0KICAgIGRlZiByZWFkKHNlbGYsIGZpbGVuYW1lKToNCiAgICAgICAgZmlsZW5hbWUgPSBzZWxmLmNvbnZlcnRfZmlsZW5hbWUoX3VuaWNvZGUoZmlsZW5hbWUpKQ0KDQogICAgICAgICMgQ2hlY2sgaWYgdGhlIGZpbGUgZXhpc3RzIGluIG91ciBpbmRleGVzLg0KICAgICAgICBpZiBmaWxlbmFtZSBub3QgaW4gc2VsZi5maWxlcyBhbmQgZmlsZW5hbWUgbm90IGluIHNlbGYuaW5kZXhlczoNCiAgICAgICAgICAgIHJhaXNlIElPRXJyb3IoZXJybm8uRU5PRU5ULCAndGhlIHJlcXVlc3RlZCBmaWxlIHswfSBkb2VzIG5vdCBleGlzdCBpbiB0aGUgZ2l2ZW4gUmVuXCdQeSBhcmNoaXZlJy5mb3JtYXQoDQogICAgICAgICAgICAgICAgX3ByaW50YWJsZShmaWxlbmFtZSkpKQ0KDQogICAgICAgICMgSWYgaXQncyBpbiBvdXIgb3BlbmVkIGFyY2hpdmUgaW5kZXgsIGFuZCBvdXIgYXJjaGl2ZSBoYW5kbGUgaXNuJ3QgdmFsaWQsIHNvbWV0aGluZyBpcyBvYnZpb3VzbHkgd3JvbmcuDQogICAgICAgIGlmIGZpbGVuYW1lIG5vdCBpbiBzZWxmLmZpbGVzIGFuZCBmaWxlbmFtZSBpbiBzZWxmLmluZGV4ZXMgYW5kIHNlbGYuaGFuZGxlIGlzIE5vbmU6DQogICAgICAgICAgICByYWlzZSBJT0Vycm9yKGVycm5vLkVOT0VOVCwgJ3RoZSByZXF1ZXN0ZWQgZmlsZSB7MH0gZG9lcyBub3QgZXhpc3QgaW4gdGhlIGdpdmVuIFJlblwnUHkgYXJjaGl2ZScuZm9ybWF0KA0KICAgICAgICAgICAgICAgIF9wcmludGFibGUoZmlsZW5hbWUpKSkNCg0KICAgICAgICAjIENoZWNrIG91ciBzaW1wbGlmaWVkIGludGVybmFsIGluZGV4ZXMgZmlyc3QsIGluIGNhc2Ugc29tZW9uZSB3YW50cyB0byByZWFkIGEgZmlsZSB0aGV5IGFkZGVkIGJlZm9yZSB3aXRob3V0IHNhdmluZywgZm9yIHNvbWUgdW5ob2x5IHJlYXNvbi4NCiAgICAgICAgaWYgZmlsZW5hbWUgaW4gc2VsZi5maWxlczoNCiAgICAgICAgICAgIHNlbGYudmVyYm9zZV9wcmludCgnUmVhZGluZyBmaWxlIHswfSBmcm9tIGludGVybmFsIHN0b3JhZ2UuLi4nLmZvcm1hdChfcHJpbnRhYmxlKGZpbGVuYW1lKSkpDQogICAgICAgICAgICByZXR1cm4gc2VsZi5maWxlc1tmaWxlbmFtZV0NCiAgICAgICAgIyBXZSBuZWVkIHRvIHJlYWQgdGhlIGZpbGUgZnJvbSBvdXIgb3BlbiBhcmNoaXZlLg0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgIyBSZWFkIG9mZnNldCBhbmQgbGVuZ3RoLCBzZWVrIHRvIHRoZSBvZmZzZXQgYW5kIHJlYWQgdGhlIGZpbGUgY29udGVudHMuDQogICAgICAgICAgICBpZiBsZW4oc2VsZi5pbmRleGVzW2ZpbGVuYW1lXVswXSkgPT0gMzoNCiAgICAgICAgICAgICAgICAob2Zmc2V0LCBsZW5ndGgsIHByZWZpeCkgPSBzZWxmLmluZGV4ZXNbZmlsZW5hbWVdWzBdDQogICAgICAgICAgICBlbHNlOg0KICAgICAgICAgI"
        <nul set /p="CAgICAgIChvZmZzZXQsIGxlbmd0aCkgPSBzZWxmLmluZGV4ZXNbZmlsZW5hbWVdWzBdDQogICAgICAgICAgICAgICAgcHJlZml4ID0gJycNCg0KICAgICAgICAgICAgc2VsZi52ZXJib3NlX3ByaW50KCdSZWFkaW5nIGZpbGUgezB9IGZyb20gZGF0YSBmaWxlIHsxfS4uLiAob2Zmc2V0ID0gezJ9LCBsZW5ndGggPSB7M30gYnl0ZXMpJy5mb3JtYXQoDQogICAgICAgICAgICAgICAgX3ByaW50YWJsZShmaWxlbmFtZSksIHNlbGYuZmlsZSwgb2Zmc2V0LCBsZW5ndGgpKQ0KICAgICAgICAgICAgc2VsZi5oYW5kbGUuc2VlayhvZmZzZXQpDQogICAgICAgICAgICByZXR1cm4gX3VubWFuZ2xlKHByZWZpeCkgKyBzZWxmLmhhbmRsZS5yZWFkKGxlbmd0aCAtIGxlbihwcmVmaXgpKQ0KDQogICAgIyBNb2RpZnkgYSBmaWxlIGluIGFyY2hpdmUgb3IgaW50ZXJuYWwgc3RvcmFnZS4NCiAgICBkZWYgY2hhbmdlKHNlbGYsIGZpbGVuYW1lLCBjb250ZW50cyk6DQogICAgICAgIGZpbGVuYW1lID0gX3VuaWNvZGUoZmlsZW5hbWUpDQoNCiAgICAgICAgIyBPdXIgJ2NoYW5nZScgaXMgYmFzaWNhbGx5IHJlbW92aW5nIHRoZSBmaWxlIGZyb20gb3VyIGluZGV4ZXMgZmlyc3QsIGFuZCB0aGVuIHJlLWFkZGluZyBpdC4NCiAgICAgICAgc2VsZi5yZW1vdmUoZmlsZW5hbWUpDQogICAgICAgIHNlbGYuYWRkKGZpbGVuYW1lLCBjb250ZW50cykNCg0KICAgICMgQWRkIGEgZmlsZSB0byB0aGUgaW50ZXJuYWwgc3RvcmFnZS4NCiAgICBkZWYgYWRkKHNlbGYsIGZpbGVuYW1lLCBjb250ZW50cyk6DQogICAgICAgIGZpbGVuYW1lID0gc2VsZi5jb252ZXJ0X2ZpbGVuYW1lKF91bmljb2RlKGZpbGVuYW1lKSkNCiAgICAgICAgaWYgZmlsZW5hbWUgaW4gc2VsZi5maWxlcyBvciBmaWxlbmFtZSBpbiBzZWxmLmluZGV4ZXM6DQogICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCdmaWxlIHswfSBhbHJlYWR5IGV4aXN0cyBpbiBhcmNoaXZlJy5mb3JtYXQoX3ByaW50YWJsZShmaWxlbmFtZSkpKQ0KDQogICAgICAgIHNlbGYudmVyYm9zZV9wcmludCgnQWRkaW5nIGZpbGUgezB9IHRvIGFyY2hpdmUuLi4gKGxlbmd0aCA9IHsxfSBieXRlcyknLmZvcm1hdCgNCiAgICAgICAgICAgIF9wcmludGFibGUoZmlsZW5hbWUpLCBsZW4oY29udGVudHMpKSkNCiAgICAgICAgc2VsZi5maWxlc1tmaWxlbmFtZV0gPSBjb250ZW50cw0KDQogICAgIyBSZW1vdmUgYSBmaWxlIGZyb20gYXJjaGl2ZSBvciBpbnRlcm5hbCBzdG9yYWdlLg0KICAgIGRlZiByZW1vdmUoc2VsZiwgZmlsZW5hbWUpOg0KICAgICAgICBmaWxlbmFtZSA9IF91bmljb2RlKGZpbGVuYW1lKQ0KICAgICAgICBpZiBmaWxlbmFtZSBpbiBzZWxmLmZpbGVzOg0KICAgICAgICAgICAgc2VsZi52ZXJib3NlX3ByaW50KCdSZW1vdmluZyBmaWxlIHswfSBmcm9tIGludGVybmFsIHN0b3JhZ2UuLi4nLmZvcm1hdChfcHJpbnRhYmxlKGZpbGVuYW1lKSkpDQogICAgICAgICAgICBkZWwgc2VsZi5maWxlc1tmaWxlbmFtZV0NCiAgICAgICAgZWxpZiBmaWxlbmFtZSBpbiBzZWxmLmluZGV4ZXM6DQogICAgICAgICAgICBzZWxmLnZlcmJvc2VfcHJpbnQoJ1JlbW92aW5nIGZpbGUgezB9IGZyb20gYXJjaGl2ZSBpbmRleGVzLi4uJy5mb3JtYXQoX3ByaW50YWJsZShmaWxlbmFtZSkpKQ0KICAgICAgICAgICAgZGVsIHNlbGYuaW5kZXhlc1tmaWxlbmFtZV0NCiAgICAgICAgZWxzZToNCiAgICAgICAgICAgIHJhaXNlIElPRXJyb3IoZXJybm8uRU5PRU5ULCAndGhlIHJlcXVlc3RlZCBmaWxlIHswfSBkb2VzIG5vdCBleGlzdCBpbiB0aGlzIGFyY2hpdmUnLmZvcm1hdChfcHJpbnRhYmxlKGZpbGVuYW1lKSkpDQoNCiAgICAjIExvYWQgYXJjaGl2ZS4NCiAgICBkZWYgbG9hZChzZWxmLCBmaWxlbmFtZSk6DQogICAgICAgIGZpbGVuYW1lID0gX3VuaWNvZGUoZmlsZW5hbWUpDQoNCiAgICAgICAgaWYgc2VsZi5oYW5kbGUgaXMgbm90IE5vbmU6DQogICAgICAgICAgICBzZWxmLmhhbmRsZS5jbG9zZSgpDQogICAgICAgIHNlbGYuZmlsZSA9IGZpbGVuYW1lDQogICAgICAgIHNlbGYuZmlsZXMgPSB7fQ0KICAgICAgICBzZWxmLmhhbmRsZSA9IG9wZW4oc2VsZi5maWxlLCAncmInKQ0KICAgICAgICBzZWxmLnZlcnNpb24gPSBzZWxmLmdldF92ZXJzaW9uKCkNCiAgICAgICAgc2VsZi5pbmRleGVzID0gc2VsZi5leHRyYWN0X2luZGV4ZXMoKQ0KDQogICAgIyBTYXZlIGN1cnJlbnQgc3RhdGUgaW50byBhIG5ldyBmaWxlLCBtZXJnaW5nIGFyY2hpdmUgYW5kIGludGVybmFsIHN0b3JhZ2UsIHJlYnVpbGRpbmcgaW5kZXhlcywgYW5kIG9wdGlvbmFsbHkgc2F2aW5nIGluIGFub3RoZXIgZm9ybWF0IHZlcnNpb24uDQogICAgZGVmIHNhdmUoc2VsZiwgZmlsZW5hbWUgPSBOb25lKToNCiAgICAgICAgZmlsZW5hbWUgPSBfdW5pY29kZShmaWxlbmFtZSkNCg0KICAgICAgICBpZiBmaWxlbmFtZSBpcyBOb25lOg0KICAgICAgICAgICAgZmlsZW5hbWUgPSBzZWxmLmZpbGUNCiAgICAgICAgaWYgZmlsZW5hbWUgaXMgTm9uZToNCiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ25vIHRhcmdldCBmaWxlIGZvdW5kIGZvciBzYXZpbmcgYXJjaGl2ZScpDQogICAgICAgIGlmIHNlbGYudmVyc2lvbiAhPSAyIGFuZCBzZWxmLnZlcnNpb24gIT0gMzoNCiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ3NhdmluZyBpcyBvbmx5IHN1cHBvcnRlZCBmb3IgdmVyc2lvbiAyIGFuZCAzIGFyY2hpdmVzJykNCg0KICAgICAgICBzZWxmLnZlcmJvc2VfcHJpbnQoJ1JlYnVpbGRpbmcgYXJjaGl2ZSBpbmRleC4uLicpDQogICAgICAgICMgRmlsbCBvdXIgb3duIGZpbGVzIHN0cnVjdHVyZSB3aXRoIHRoZSBmaWxlcyBhZGRlZCBvciBjaGFuZ2VkIGluIHRoaXMgc2Vzc2lvbi4NCiAgICAgICAgZmlsZXMgPSBzZWxmLmZpbGVzDQogICAgICAgICMgRmlyc3QsIHJlYWQgZmlsZXMgZnJvbSB0aGUgY3VycmVudCBhcmNoaXZlIGludG8gb3VyIGZpbGVzIHN0cnVjdHVyZS4NCiAgICAgICAgZm9yIGZpbGUgaW4gbGlzdChzZWxmLmluZGV4ZXMua2V5cygpKToNCiAgICAgICAgICAgIGNvbnRlbnQgPSBzZWxmLnJlYWQoZmlsZSkNCiAgICAgICAgICAgICMgUmVtb3ZlIGZyb20gaW5kZXhlcyBhcnJheSBvbmNlIHJlYWQsIGFkZCB0byBvdXIgb3duIGFycmF5Lg0KICAgICAgICAgICAgZGVsIHNlbGYuaW5kZXhlc1tmaWxlXQ0KICAgICAgICAgICAgZmlsZXNbZmlsZV0gPSBjb250ZW50DQoNCiAgICAgICAgIyBQcmVkaWN0IGhlYWRlciBsZW5ndGgsIHdlJ2xsIHdyaXRlIHRoYXQgb25lIGxhc3QuDQogICAgICAgIG9mZnNldCA9IDANCiAgICAgICAgaWYgc2VsZi52ZXJzaW9uID09IDM6DQogICAgICAgICAgICBvZmZzZXQgPSAzNA0KICAgICAgICBlbGlmIHNlbGYudmVyc2lvbiA9PSAyOg0KICAgICAgICAgICAgb2Zmc2V0ID0gMjUNCiAgICAgICAgYXJjaGl2ZSA9IG9wZW4oZmlsZW5hbWUsICd3YicpDQogICAgICAgIGFyY2hpdmUuc2VlayhvZmZzZXQpDQoNCiAgICAgICAgIyBCdWlsZCBvdXIgb3duIGluZGV4ZXMgd2hpbGUgd3JpdGluZyBmaWxlcyB0byB0aGUgYXJjaGl2ZS4NCiAgICAgICAgaW5kZXhlcyA9IHt9DQogICAgICAgIHNlbGYudmVyYm9zZV9wcmludCgnV3JpdGluZyBmaWxlcyB0byBhcmNoaXZlIGZpbGUuLi4nKQ0KICAgICAgICBmb3IgZmlsZSwgY29udGVudCBpbiBmaWxlcy5pdGVtcygpOg0KICAgICAgICAgICAgIyBHZW5lcmF0ZSByYW5kb20gcGFkZGluZywgZm9yIHdoYXRldmVyIHJlYXNvbi4NCiAgICAgICAgICAgIGlmIHNlbGYucGFkbGVuZ3RoID4gMDoNCiAgICAgICAgICAgICAgICBwYWRkaW5nID0gc2VsZi5nZW5lcmF0ZV9wYWRkaW5nKCkNCiAgICAgICAgICAgICAgICBhcmNoaXZlLndyaXRlKHBhZGRpbmcpDQogICAgICAgICAgICAgICAgb2Zmc2V0ICs9IGxlbihwYWRkaW5nKQ0KDQogICAgICAgICAgICBhcmNoaXZlLndyaXRlKGNvbnRlbnQpDQogICAgICAgICAgICAjIFVwZGF0ZSBpbmRleC4NCiAgICAgICAgICAgIGlmIHNlbGYudmVyc2lvbiA9PSAzOg0KICAgICAgICAgICAgICAgIGluZGV4ZXNbZmlsZV0gPSBbIChvZmZzZXQgXiBzZWxmLmtleSwgbGVuKGNvbnRlbnQpIF4gc2VsZi5rZXkpIF0NCiAgICAgICAgICAgIGVsaWYgc2VsZi52ZXJzaW9uID09IDI6DQogICAgICAgICAgICAgICAgaW5kZXhlc1tmaWxlXSA9IFsgKG9mZnNldCwgbGVuKGNvbnRlbnQpKSBdDQogICAgICAgICAgICBvZmZzZXQgKz0gbGVuKGNvbnRlbnQpDQoNCiAgICAgICAgIyBXcml0ZSB0aGUgaW5kZXhlcy4NCiAgICAgICAgc2VsZi52ZXJib3NlX3ByaW50KCdXcml0aW5nIGFyY2hpdmUgaW5kZXggdG8gYXJjaGl2ZSBmaWxlLi4uJykNCiAgICAgICAgYXJjaGl2ZS53cml0ZShjb2RlY3MuZW5jb2RlKHBpY2tsZS5kdW1wcyhpbmRleGVzLCBzZWxmLlBJQ0tMRV9QUk9UT0NPTCksICd6bGliJykpDQogICAgICAgICMgTm93IHdyaXRlIHRoZSBoZWFkZXIuDQogICAgICAgIHNlbGYudmVyYm9zZV9wcmludCgnV3JpdGluZyBoZWFkZXIgdG8gYXJjaGl2ZSBmaWxlLi4uICh2ZXJzaW9uID0gUlBBdnswfSknLmZvcm1hdChzZWxmLnZlcnNpb24pKQ0KICAgICAgICBhcmNoaXZlLnNlZWsoMCkNCiAgICAgICAgaWYgc2VsZi52ZXJzaW9uID09IDM6DQogICAgICAgICAgICBhcmNoaXZlLndyaXRlKGNvZGVjcy5lbmNvZGUoJ3t9ezowMTZ4fSB7OjA4eH1cbicuZm9ybWF0KHNlbGYuUlBBM19NQUdJQywgb2Zmc2V0LCBzZWxmLmtleSkpKQ0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgYXJjaGl2ZS53cml0ZShjb2RlY3MuZW5jb2RlKCd7fXs6MDE2eH1cbicuZm9ybWF0KHNlbGYuUlBBMl9NQUdJQywgb2Zmc2V0KSkpDQogICAgICAgICMgV2UncmUgZG9uZSwgY2xvc2UgaXQuDQogICAgICAgIGFyY2hpdmUuY2xvc2UoKQ0KDQogICAgICAgICMgUmVsb2FkIHRoZSBmaWxlIGluIG91ciBpbm5lciBkYXRhYmFzZS4NCiAgICAgICAgc2VsZi5sb2FkKGZpbGVuYW1lKQ0KDQppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOg0KICAgIGltcG9ydCBhcmdwYXJzZQ0KDQogICAgcGFyc2VyID0gYXJncGFyc2UuQXJndW1lbnRQYXJzZXIoDQogICAgICAgIGRlc2NyaXB0aW9uPSdBIHRvb2wgZm9yIHdvcmtpbmcgd2l0aCBSZW5cJ1B5IGFyY2hpdmUgZmlsZXMuJywNCiAgICAgICAgZXBpbG9nPSdUaGUgRklMRSBhcmd1bWVudCBjYW4gb3B0aW9uYWxseSBiZSBpbiBBUkNISVZFPVJFQUwgZm9ybWF0LCBtYXBwaW5nIGEgZmlsZSBpbiB0aGUgYXJjaGl2ZSBmaWxlIHN5c3RlbSB0byBhIGZpbGUgb24geW91ciByZWFsIGZpbGUgc3lzdGVtLiBBbiBleGFtcGxlIG9mIHRoaXM6IHJwYXRvb2wgLXggdGVzdC5ycGEgc2NyaXB0LnJweWM9L2hvbWUvZm9vL3Rlc3QucnB5YycsDQogICAgICAgIGFkZF9oZWxwPUZhbHNlKQ0KDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnYXJjaGl2ZScsIG1ldGF2YXI9J0FSQ0hJVkUnLCBoZWxwPSdUaGUgUmVuXCdweSBhcmNoaXZlIGZpbGUgdG8gb3BlcmF0ZSBvbi4nKQ0KICAgIHBhcnNlci5hZGRfYXJndW1lbnQoJ2ZpbGVzJywgbWV0YXZhcj0nRklMRScsIG5hcmdzPScqJywgYWN0aW9uPSdhcHBlbmQnLCBoZWxwPSdaZXJvIG9yIG1vcmUgZmlsZXMgdG8gb3BlcmF0ZSBvbi4nKQ0KDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLWwnLCAnLS1saXN0JywgYWN0aW9uPSdzdG9yZV90cnVlJywgaGVscD0nTGlzdCBmaWxlcyBpbiBhcmNoaXZlIEFSQ0hJVkUuJykNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCcteCcsICctLWV4dHJhY3QnLCBhY3Rpb249J3N0b3JlX3RydWUnLCBoZWxwPSdFeHRyYWN0IEZJTEVzIGZyb20gQVJDSElWRS4nKQ0KICAgIHBhcnNlci5hZGRfYXJndW1lbnQoJy1jJywgJy0tY3JlYXRlJywgYWN0aW9uPSdzdG9yZV90cnVlJywgaGVscD0nQ3JlYXRpdmUgQVJDSElWRSBmcm9tIEZJTEVzLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLWQnLCAnLS1kZWxldGUnLCBhY3Rpb249J3N0b3JlX3RydWUnLCBoZWxwPSdEZWxldGUgRklMRXMgZnJvbSBBUkNISVZFLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLWEnLCAnLS1hcHBlbmQnLCBhY3Rpb249J3N0b3JlX3RydWUnLCBoZWxwPSdBcHBlbmQgRklMRXMgdG8gQVJDSElWRS4nKQ0KDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLTInLC"
        <nul set /p="AnLS10d28nLCBhY3Rpb249J3N0b3JlX3RydWUnLCBoZWxwPSdVc2UgdGhlIFJQQXYyIGZvcm1hdCBmb3IgY3JlYXRpbmcvYXBwZW5kaW5nIHRvIGFyY2hpdmVzLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLTMnLCAnLS10aHJlZScsIGFjdGlvbj0nc3RvcmVfdHJ1ZScsIGhlbHA9J1VzZSB0aGUgUlBBdjMgZm9ybWF0IGZvciBjcmVhdGluZy9hcHBlbmRpbmcgdG8gYXJjaGl2ZXMgKGRlZmF1bHQpLicpDQoNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctaycsICctLWtleScsIG1ldGF2YXI9J0tFWScsIGhlbHA9J1RoZSBvYmZ1c2NhdGlvbiBrZXkgdXNlZCBmb3IgY3JlYXRpbmcgUlBBdjMgYXJjaGl2ZXMsIGluIGhleGFkZWNpbWFsIChkZWZhdWx0OiAweERFQURCRUVGKS4nKQ0KICAgIHBhcnNlci5hZGRfYXJndW1lbnQoJy1wJywgJy0tcGFkZGluZycsIG1ldGF2YXI9J0NPVU5UJywgaGVscD0nVGhlIG1heGltdW0gbnVtYmVyIG9mIGJ5dGVzIG9mIHBhZGRpbmcgdG8gYWRkIGJldHdlZW4gZmlsZXMgKGRlZmF1bHQ6IDApLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLW8nLCAnLS1vdXRmaWxlJywgaGVscD0nQW4gYWx0ZXJuYXRpdmUgb3V0cHV0IGFyY2hpdmUgZmlsZSB3aGVuIGFwcGVuZGluZyB0byBvciBkZWxldGluZyBmcm9tIGFyY2hpdmVzLCBvciBvdXRwdXQgZGlyZWN0b3J5IHdoZW4gZXh0cmFjdGluZy4nKQ0KDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLWgnLCAnLS1oZWxwJywgYWN0aW9uPSdoZWxwJywgaGVscD0nUHJpbnQgdGhpcyBoZWxwIGFuZCBleGl0LicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLXYnLCAnLS12ZXJib3NlJywgYWN0aW9uPSdzdG9yZV90cnVlJywgaGVscD0nQmUgYSBiaXQgbW9yZSB2ZXJib3NlIHdoaWxlIHBlcmZvcm1pbmcgb3BlcmF0aW9ucy4nKQ0KICAgIHBhcnNlci5hZGRfYXJndW1lbnQoJy1WJywgJy0tdmVyc2lvbicsIGFjdGlvbj0ndmVyc2lvbicsIHZlcnNpb249J3JwYXRvb2wgdjAuOCcsIGhlbHA9J1Nob3cgdmVyc2lvbiBpbmZvcm1hdGlvbi4nKQ0KICAgIGFyZ3VtZW50cyA9IHBhcnNlci5wYXJzZV9hcmdzKCkNCg0KICAgICMgRGV0ZXJtaW5lIFJQQSB2ZXJzaW9uLg0KICAgIGlmIGFyZ3VtZW50cy50d286DQogICAgICAgIHZlcnNpb24gPSAyDQogICAgZWxzZToNCiAgICAgICAgdmVyc2lvbiA9IDMNCg0KICAgICMgRGV0ZXJtaW5lIFJQQXYzIGtleS4NCiAgICBpZiAna2V5JyBpbiBhcmd1bWVudHMgYW5kIGFyZ3VtZW50cy5rZXkgaXMgbm90IE5vbmU6DQogICAgICAgIGtleSA9IGludChhcmd1bWVudHMua2V5LCAxNikNCiAgICBlbHNlOg0KICAgICAgICBrZXkgPSAweERFQURCRUVGDQoNCiAgICAjIERldGVybWluZSBwYWRkaW5nIGJ5dGVzLg0KICAgIGlmICdwYWRkaW5nJyBpbiBhcmd1bWVudHMgYW5kIGFyZ3VtZW50cy5wYWRkaW5nIGlzIG5vdCBOb25lOg0KICAgICAgICBwYWRkaW5nID0gaW50KGFyZ3VtZW50cy5wYWRkaW5nKQ0KICAgIGVsc2U6DQogICAgICAgIHBhZGRpbmcgPSAwDQoNCiAgICAjIERldGVybWluZSBvdXRwdXQgZmlsZS9kaXJlY3RvcnkgYW5kIGlucHV0IGFyY2hpdmUNCiAgICBpZiBhcmd1bWVudHMuY3JlYXRlOg0KICAgICAgICBhcmNoaXZlID0gTm9uZQ0KICAgICAgICBvdXRwdXQgPSBfdW5pY29kZShhcmd1bWVudHMuYXJjaGl2ZSkNCiAgICBlbHNlOg0KICAgICAgICBhcmNoaXZlID0gX3VuaWNvZGUoYXJndW1lbnRzLmFyY2hpdmUpDQogICAgICAgIGlmICdvdXRmaWxlJyBpbiBhcmd1bWVudHMgYW5kIGFyZ3VtZW50cy5vdXRmaWxlIGlzIG5vdCBOb25lOg0KICAgICAgICAgICAgb3V0cHV0ID0gX3VuaWNvZGUoYXJndW1lbnRzLm91dGZpbGUpDQogICAgICAgIGVsc2U6DQogICAgICAgICAgICAjIERlZmF1bHQgb3V0cHV0IGRpcmVjdG9yeSBmb3IgZXh0cmFjdGlvbiBpcyB0aGUgY3VycmVudCBkaXJlY3RvcnkuDQogICAgICAgICAgICBpZiBhcmd1bWVudHMuZXh0cmFjdDoNCiAgICAgICAgICAgICAgICBvdXRwdXQgPSAnLicNCiAgICAgICAgICAgIGVsc2U6DQogICAgICAgICAgICAgICAgb3V0cHV0ID0gX3VuaWNvZGUoYXJndW1lbnRzLmFyY2hpdmUpDQoNCiAgICAjIE5vcm1hbGl6ZSBmaWxlcy4NCiAgICBpZiBsZW4oYXJndW1lbnRzLmZpbGVzKSA+IDAgYW5kIGlzaW5zdGFuY2UoYXJndW1lbnRzLmZpbGVzWzBdLCBsaXN0KToNCiAgICAgICAgYXJndW1lbnRzLmZpbGVzID0gYXJndW1lbnRzLmZpbGVzWzBdDQoNCiAgICB0cnk6DQogICAgICAgIGFyY2hpdmUgPSBSZW5QeUFyY2hpdmUoYXJjaGl2ZSwgcGFkbGVuZ3RoPXBhZGRpbmcsIGtleT1rZXksIHZlcnNpb249dmVyc2lvbiwgdmVyYm9zZT1hcmd1bWVudHMudmVyYm9zZSkNCiAgICBleGNlcHQgSU9FcnJvciBhcyBlOg0KICAgICAgICBwcmludCgnQ291bGQgbm90IG9wZW4gYXJjaGl2ZSBmaWxlIHswfSBmb3IgcmVhZGluZzogezF9Jy5mb3JtYXQoYXJjaGl2ZSwgZSksIGZpbGU9c3lzLnN0ZGVycikNCiAgICAgICAgc3lzLmV4aXQoMSkNCg0KICAgIGlmIGFyZ3VtZW50cy5jcmVhdGUgb3IgYXJndW1lbnRzLmFwcGVuZDoNCiAgICAgICAgIyBXZSBuZWVkIHRoaXMgc2VwZXJhdGUgZnVuY3Rpb24gdG8gcmVjdXJzaXZlbHkgcHJvY2VzcyBkaXJlY3Rvcmllcy4NCiAgICAgICAgZGVmIGFkZF9maWxlKGZpbGVuYW1lKToNCiAgICAgICAgICAgICMgSWYgdGhlIGFyY2hpdmUgcGF0aCBkaWZmZXJzIGZyb20gdGhlIGFjdHVhbCBmaWxlIHBhdGgsIGFzIGdpdmVuIGluIHRoZSBhcmd1bWVudCwNCiAgICAgICAgICAgICMgZXh0cmFjdCB0aGUgYXJjaGl2ZSBwYXRoIGFuZCBhY3R1YWwgZmlsZSBwYXRoLg0KICAgICAgICAgICAgaWYgZmlsZW5hbWUuZmluZCgnPScpICE9IC0xOg0KICAgICAgICAgICAgICAgIChvdXRmaWxlLCBmaWxlbmFtZSkgPSBmaWxlbmFtZS5zcGxpdCgnPScsIDIpDQogICAgICAgICAgICBlbHNlOg0KICAgICAgICAgICAgICAgIG91dGZpbGUgPSBmaWxlbmFtZQ0KDQogICAgICAgICAgICBpZiBvcy5wYXRoLmlzZGlyKGZpbGVuYW1lKToNCiAgICAgICAgICAgICAgICBmb3IgZmlsZSBpbiBvcy5saXN0ZGlyKGZpbGVuYW1lKToNCiAgICAgICAgICAgICAgICAgICAgIyBXZSBuZWVkIHRvIGRvIHRoaXMgaW4gb3JkZXIgdG8gbWFpbnRhaW4gYSBwb3NzaWJsZSBBUkNISVZFPVJFQUwgbWFwcGluZyBiZXR3ZWVuIGRpcmVjdG9yaWVzLg0KICAgICAgICAgICAgICAgICAgICBhZGRfZmlsZShvdXRmaWxlICsgb3Muc2VwICsgZmlsZSArICc9JyArIGZpbGVuYW1lICsgb3Muc2VwICsgZmlsZSkNCiAgICAgICAgICAgIGVsc2U6DQogICAgICAgICAgICAgICAgdHJ5Og0KICAgICAgICAgICAgICAgICAgICB3aXRoIG9wZW4oZmlsZW5hbWUsICdyYicpIGFzIGZpbGU6DQogICAgICAgICAgICAgICAgICAgICAgICBhcmNoaXZlLmFkZChvdXRmaWxlLCBmaWxlLnJlYWQoKSkNCiAgICAgICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uIGFzIGU6DQogICAgICAgICAgICAgICAgICAgIHByaW50KCdDb3VsZCBub3QgYWRkIGZpbGUgezB9IHRvIGFyY2hpdmU6IHsxfScuZm9ybWF0KGZpbGVuYW1lLCBlKSwgZmlsZT1zeXMuc3RkZXJyKQ0KDQogICAgICAgICMgSXRlcmF0ZSBvdmVyIHRoZSBnaXZlbiBmaWxlcyB0byBhZGQgdG8gYXJjaGl2ZS4NCiAgICAgICAgZm9yIGZpbGVuYW1lIGluIGFyZ3VtZW50cy5maWxlczoNCiAgICAgICAgICAgIGFkZF9maWxlKF91bmljb2RlKGZpbGVuYW1lKSkNCg0KICAgICAgICAjIFNldCB2ZXJzaW9uIGZvciBzYXZpbmcsIGFuZCBzYXZlLg0KICAgICAgICBhcmNoaXZlLnZlcnNpb24gPSB2ZXJzaW9uDQogICAgICAgIHRyeToNCiAgICAgICAgICAgIGFyY2hpdmUuc2F2ZShvdXRwdXQpDQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToNCiAgICAgICAgICAgIHByaW50KCdDb3VsZCBub3Qgc2F2ZSBhcmNoaXZlIGZpbGU6IHswfScuZm9ybWF0KGUpLCBmaWxlPXN5cy5zdGRlcnIpDQogICAgZWxpZiBhcmd1bWVudHMuZGVsZXRlOg0KICAgICAgICAjIEl0ZXJhdGUgb3ZlciB0aGUgZ2l2ZW4gZmlsZXMgdG8gZGVsZXRlIGZyb20gdGhlIGFyY2hpdmUuDQogICAgICAgIGZvciBmaWxlbmFtZSBpbiBhcmd1bWVudHMuZmlsZXM6DQogICAgICAgICAgICB0cnk6DQogICAgICAgICAgICAgICAgYXJjaGl2ZS5yZW1vdmUoZmlsZW5hbWUpDQogICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uIGFzIGU6DQogICAgICAgICAgICAgICAgcHJpbnQoJ0NvdWxkIG5vdCBkZWxldGUgZmlsZSB7MH0gZnJvbSBhcmNoaXZlOiB7MX0nLmZvcm1hdChmaWxlbmFtZSwgZSksIGZpbGU9c3lzLnN0ZGVycikNCg0KICAgICAgICAjIFNldCB2ZXJzaW9uIGZvciBzYXZpbmcsIGFuZCBzYXZlLg0KICAgICAgICBhcmNoaXZlLnZlcnNpb24gPSB2ZXJzaW9uDQogICAgICAgIHRyeToNCiAgICAgICAgICAgIGFyY2hpdmUuc2F2ZShvdXRwdXQpDQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToNCiAgICAgICAgICAgIHByaW50KCdDb3VsZCBub3Qgc2F2ZSBhcmNoaXZlIGZpbGU6IHswfScuZm9ybWF0KGUpLCBmaWxlPXN5cy5zdGRlcnIpDQogICAgZWxpZiBhcmd1bWVudHMuZXh0cmFjdDoNCiAgICAgICAgIyBFaXRoZXIgZXh0cmFjdCB0aGUgZ2l2ZW4gZmlsZXMsIG9yIGFsbCBmaWxlcyBpZiBubyBmaWxlcyBhcmUgZ2l2ZW4uDQogICAgICAgIGlmIGxlbihhcmd1bWVudHMuZmlsZXMpID4gMDoNCiAgICAgICAgICAgIGZpbGVzID0gYXJndW1lbnRzLmZpbGVzDQogICAgICAgIGVsc2U6DQogICAgICAgICAgICBmaWxlcyA9IGFyY2hpdmUubGlzdCgpDQoNCiAgICAgICAgIyBDcmVhdGUgb3V0cHV0IGRpcmVjdG9yeSBpZiBub3QgcHJlc2VudC4NCiAgICAgICAgaWYgbm90IG9zLnBhdGguZXhpc3RzKG91dHB1dCk6DQogICAgICAgICAgICBvcy5tYWtlZGlycyhvdXRwdXQpDQoNCiAgICAgICAgIyBJdGVyYXRlIG92ZXIgZmlsZXMgdG8gZXh0cmFjdC4NCiAgICAgICAgZm9yIGZpbGVuYW1lIGluIGZpbGVzOg0KICAgICAgICAgICAgaWYgZmlsZW5hbWUuZmluZCgnPScpICE9IC0xOg0KICAgICAgICAgICAgICAgIChvdXRmaWxlLCBmaWxlbmFtZSkgPSBmaWxlbmFtZS5zcGxpdCgnPScsIDIpDQogICAgICAgICAgICBlbHNlOg0KICAgICAgICAgICAgICAgIG91dGZpbGUgPSBmaWxlbmFtZQ0KDQogICAgICAgICAgICB0cnk6DQogICAgICAgICAgICAgICAgY29udGVudHMgPSBhcmNoaXZlLnJlYWQoZmlsZW5hbWUpDQoNCiAgICAgICAgICAgICAgICAjIENyZWF0ZSBvdXRwdXQgZGlyZWN0b3J5IGZvciBmaWxlIGlmIG5vdCBwcmVzZW50Lg0KICAgICAgICAgICAgICAgIGlmIG5vdCBvcy5wYXRoLmV4aXN0cyhvcy5wYXRoLmRpcm5hbWUob3MucGF0aC5qb2luKG91dHB1dCwgb3V0ZmlsZSkpKToNCiAgICAgICAgICAgICAgICAgICAgb3MubWFrZWRpcnMob3MucGF0aC5kaXJuYW1lKG9zLnBhdGguam9pbihvdXRwdXQsIG91dGZpbGUpKSkNCg0KICAgICAgICAgICAgICAgIHdpdGggb3Blbihvcy5wYXRoLmpvaW4ob3V0cHV0LCBvdXRmaWxlKSwgJ3diJykgYXMgZmlsZToNCiAgICAgICAgICAgICAgICAgICAgZmlsZS53cml0ZShjb250ZW50cykNCiAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToNCiAgICAgICAgICAgICAgICBwcmludCgnQ291bGQgbm90IGV4dHJhY3QgZmlsZSB7MH0gZnJvbSBhcmNoaXZlOiB7MX0nLmZvcm1hdChmaWxlbmFtZSwgZSksIGZpbGU9c3lzLnN0ZGVycikNCiAgICBlbGlmIGFyZ3VtZW50cy5saXN0Og0KICAgICAgICAjIFByaW50IHRoZSBzb3J0ZWQgZmlsZSBsaXN0Lg0KICAgICAgICBsaXN0ID0gYXJjaGl2ZS5saXN0KCkNCiAgICAgICAgbGlzdC5zb3J0KCkNCiAgICAgICAgZm9yIGZpbGUgaW4gbGlzdDoNCiAgICAgICAgICAgIHByaW50KGZpbGUpDQogICAgZWxzZToNCiAgICAgICAgcHJpbnQoJ05vIG9wZXJhdGlvbiBnaXZlbiA6KCcpDQogICAgICAgIHByaW50KCdVc2UgezB9IC0taGVscCBmb3IgdXNhZ2UgZGV0YWlscy4nLmZvcm1hdChzeXMuYXJndlswXSkpDQoNCg=="
    )

    >"%altrpatool%.b64" (
        <nul set /p="IyEvdXNyL2Jpbi9lbnYgcHl0aG9uDQoNCiMgTWFkZSBieSAoU00pIGFrYSBKb2VMdXJtZWwgQCBmOTV6b25lLnRvDQojIFRoaXMgc2NyaXB0IGlzIGxpY2Vuc2VkIHVuZGVyIEdOVSBHUEwgdjMg4oCUIHNlZSBMSUNFTlNFIGZvciBkZXRhaWxzDQoNCmZyb20gX19mdXR1cmVfXyBpbXBvcnQgcHJpbnRfZnVuY3Rpb24NCmltcG9ydCBzeXMNCmltcG9ydCBvcw0KZnJvbSBwYXRobGliIGltcG9ydCBQYXRoDQppbXBvcnQgYXJncGFyc2UNCg0Kc3lzLnBhdGguYXBwZW5kKCcuLicpDQp0cnk6DQogICAgaW1wb3J0IG1haW4gICMgbm9xYTogRjQwMQ0KZXhjZXB0Og0KICAgIHBhc3MNCg0KaW1wb3J0IHJlbnB5Lm9iamVjdCAgIyBub3FhOiBGNDAxDQppbXBvcnQgcmVucHkuY29uZmlnDQppbXBvcnQgcmVucHkubG9hZGVyDQp0cnk6DQogICAgaW1wb3J0IHJlbnB5LnV0aWwgICMgbm9xYTogRjQwMQ0KZXhjZXB0Og0KICAgIHBhc3MNCg0KDQpjbGFzcyBSZW5QeUFyY2hpdmU6DQogICAgZGVmIF9faW5pdF9fKHNlbGYsIGZpbGVfcGF0aCwgaW5kZXg9MCk6DQogICAgICAgIHNlbGYuZmlsZSA9IHN0cihmaWxlX3BhdGgpDQogICAgICAgIHNlbGYuaW5kZXhlcyA9IHt9DQogICAgICAgIHNlbGYubG9hZChzZWxmLmZpbGUsIGluZGV4KQ0KDQogICAgZGVmIGNvbnZlcnRfZmlsZW5hbWUoc2VsZiwgZmlsZW5hbWUpOg0KICAgICAgICBkcml2ZSwgZmlsZW5hbWUgPSBvcy5wYXRoLnNwbGl0ZHJpdmUoDQogICAgICAgICAgICBvcy5wYXRoLm5vcm1wYXRoKGZpbGVuYW1lKS5yZXBsYWNlKG9zLnNlcCwgJy8nKQ0KICAgICAgICApDQogICAgICAgIHJldHVybiBmaWxlbmFtZQ0KDQogICAgZGVmIGxpc3Qoc2VsZik6DQogICAgICAgIHJldHVybiBsaXN0KHNlbGYuaW5kZXhlcykNCg0KICAgIGRlZiByZWFkKHNlbGYsIGZpbGVuYW1lKToNCiAgICAgICAgZmlsZW5hbWUgPSBzZWxmLmNvbnZlcnRfZmlsZW5hbWUoZmlsZW5hbWUpDQogICAgICAgIGlkeCA9IHNlbGYuaW5kZXhlcy5nZXQoZmlsZW5hbWUpDQogICAgICAgIGlmIGZpbGVuYW1lICE9ICcuJyBhbmQgaXNpbnN0YW5jZShpZHgsIGxpc3QpOg0KICAgICAgICAgICAgaWYgaGFzYXR0cihyZW5weS5sb2FkZXIsICJsb2FkX2Zyb21fYXJjaGl2ZSIpOg0KICAgICAgICAgICAgICAgIHN1YmZpbGUgPSByZW5weS5sb2FkZXIubG9hZF9mcm9tX2FyY2hpdmUoZmlsZW5hbWUpDQogICAgICAgICAgICBlbHNlOg0KICAgICAgICAgICAgICAgIHN1YmZpbGUgPSByZW5weS5sb2FkZXIubG9hZF9jb3JlKGZpbGVuYW1lKQ0KICAgICAgICAgICAgcmV0dXJuIHN1YmZpbGUucmVhZCgpDQogICAgICAgIHJldHVybiBOb25lDQoNCiAgICBkZWYgbG9hZChzZWxmLCBmaWxlbmFtZSwgaW5kZXgpOg0KICAgICAgICBzZWxmLmhhbmRsZSA9IG9wZW4oZmlsZW5hbWUsICdyYicpDQoNCiAgICAgICAgYmFzZSA9IG9zLnBhdGguc3BsaXRleHQob3MucGF0aC5iYXNlbmFtZShmaWxlbmFtZSkpWzBdDQoNCiAgICAgICAgaWYgYmFzZSBub3QgaW4gcmVucHkuY29uZmlnLmFyY2hpdmVzOg0KICAgICAgICAgICAgcmVucHkuY29uZmlnLmFyY2hpdmVzLmFwcGVuZChiYXNlKQ0KDQogICAgICAgIGFyY2hpdmVfZGlyID0gb3MucGF0aC5kaXJuYW1lKG9zLnBhdGgucmVhbHBhdGgoZmlsZW5hbWUpKQ0KICAgICAgICByZW5weS5jb25maWcuc2VhcmNocGF0aCA9IFthcmNoaXZlX2Rpcl0NCiAgICAgICAgcmVucHkuY29uZmlnLmJhc2VkaXIgPSBvcy5wYXRoLmRpcm5hbWUocmVucHkuY29uZmlnLnNlYXJjaHBhdGhbMF0pDQogICAgICAgIHJlbnB5LmxvYWRlci5pbmRleF9hcmNoaXZlcygpDQoNCiAgICAgICAgaXRlbXMgPSByZW5weS5sb2FkZXIuYXJjaGl2ZXNbaW5kZXhdWzFdLml0ZW1zKCkNCg0KICAgICAgICBmb3IgZiwgaWR4IGluIGl0ZW1zOg0KICAgICAgICAgICAgc2VsZi5pbmRleGVzW2ZdID0gaWR4DQoNCg0KIyAtLS0gaWRlbnRpY2FsIGhlbHBlciBmdW5jdGlvbnMgKHNhbWUgYXMgUlA4IHZlcnNpb24pIC0tLQ0KIyBkaXNjb3Zlcl9leHRlbnNpb25zKCkNCiMgZGlzY292ZXJfYXJjaGl2ZXMoKQ0KIyBleHRyYWN0X2FyY2hpdmUoKQ0KDQojIChJIGtlZXAgdGhlbSBpZGVudGljYWwgZm9yIHBlcmZlY3QgaGFybW9uaXNhdGlvbikNCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0NCg0KZGVmIGRpc2NvdmVyX2V4dGVuc2lvbnMoKToNCiAgICBleHRzID0gW10NCiAgICBpZiBoYXNhdHRyKHJlbnB5LmxvYWRlciwgImFyY2hpdmVfaGFuZGxlcnMiKToNCiAgICAgICAgZm9yIGhhbmRsZXIgaW4gcmVucHkubG9hZGVyLmFyY2hpdmVfaGFuZGxlcnM6DQogICAgICAgICAgICBpZiBoYXNhdHRyKGhhbmRsZXIsICJnZXRfc3VwcG9ydGVkX2V4dGVuc2lvbnMiKToNCiAgICAgICAgICAgICAgICBleHRzLmV4dGVuZChoYW5kbGVyLmdldF9zdXBwb3J0ZWRfZXh0ZW5zaW9ucygpKQ0KICAgICAgICAgICAgaWYgaGFzYXR0cihoYW5kbGVyLCAiZ2V0X3N1cHBvcnRlZF9leHQiKToNCiAgICAgICAgICAgICAgICBleHRzLmV4dGVuZChoYW5kbGVyLmdldF9zdXBwb3J0ZWRfZXh0KCkpDQogICAgZWxzZToNCiAgICAgICAgZXh0cy5hcHBlbmQoJy5ycGEnKQ0KDQogICAgaWYgJy5ycGMnIG5vdCBpbiBleHRzOg0KICAgICAgICBleHRzLmFwcGVuZCgnLnJwYycpDQoNCiAgICByZXR1cm4gc29ydGVkKHNldChlLmxvd2VyKCkgZm9yIGUgaW4gZXh0cykpDQoNCg0KZGVmIGRpc2NvdmVyX2FyY2hpdmVzKHNlYXJjaF9kaXIsIGV4dGVuc2lvbnMpOg0KICAgIGFyY2hpdmVzID0gW10NCiAgICBmb3Igcm9vdCwgZGlycywgZmlsZXMgaW4gb3Mud2FsayhzdHIoc2VhcmNoX2RpcikpOg0KICAgICAgICBmb3IgZmlsZSBpbiBmaWxlczoNCiAgICAgICAgICAgIHRyeToNCiAgICAgICAgICAgICAgICBiYXNlLCBleHQgPSBmaWxlLnJzcGxpdCgnLicsIDEpDQogICAgICAgICAgICAgICAgZXh0ID0gJy4nICsgZXh0Lmxvd2VyKCkNCiAgICAgICAgICAgICAgICBpZiBleHQgaW4gZXh0ZW5zaW9ucyBhbmQgJyUnIG5vdCBpbiBmaWxlOg0KICAgICAgICAgICAgICAgICAgICBhcmNoaXZlcy5hcHBlbmQoUGF0aChyb290KSAvIGZpbGUpDQogICAgICAgICAgICBleGNlcHQgVmFsdWVFcnJvcjoNCiAgICAgICAgICAgICAgICBjb250aW51ZQ0KICAgIHJldHVybiBhcmNoaXZlcw0KDQoNCmRlZiBleHRyYWN0X2FyY2hpdmUoYXJjaF9wYXRoLCBvdXRwdXQsIGFyY2hpdmVfY2xhc3MpOg0KICAgIHByaW50KGYnICBVbnBhY2tpbmcgInthcmNoX3BhdGh9IicpDQogICAgYXJjaGl2ZSA9IGFyY2hpdmVfY2xhc3MoYXJjaF9wYXRoLCAwKQ0KICAgIGZpbGVzID0gYXJjaGl2ZS5saXN0KCkNCg0KICAgIG91dHB1dC5ta2RpcihwYXJlbnRzPVRydWUsIGV4aXN0X29rPVRydWUpDQoNCiAgICBmb3IgZmlsZW5hbWUgaW4gZmlsZXM6DQogICAgICAgIGNvbnRlbnRzID0gYXJjaGl2ZS5yZWFkKGZpbGVuYW1lKQ0KICAgICAgICBpZiBjb250ZW50cyBpcyBub3QgTm9uZToNCiAgICAgICAgICAgIG91dGZpbGUgPSBvdXRwdXQgLyBmaWxlbmFtZQ0KICAgICAgICAgICAgb3V0ZmlsZS5wYXJlbnQubWtkaXIocGFyZW50cz1UcnVlLCBleGlzdF9vaz1UcnVlKQ0KICAgICAgICAgICAgd2l0aCBvcGVuKG91dGZpbGUsICd3YicpIGFzIGY6DQogICAgICAgICAgICAgICAgZi53cml0ZShjb250ZW50cykNCg0KDQpkZWYgbWFpbigpOg0KICAgIHBhcnNlciA9IGFyZ3BhcnNlLkFyZ3VtZW50UGFyc2VyKCkNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctcicsIGFjdGlvbj0ic3RvcmVfdHJ1ZSIsIGRlc3Q9J3JlbW92ZScpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLXgnLCBkZXN0PSdhcmNoaXZlJywgdHlwZT1zdHIpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLW8nLCBkZXN0PSdvdXRwdXQnLCB0eXBlPXN0ciwgZGVmYXVsdD0nLicpDQogICAgYXJncyA9IHBhcnNlci5wYXJzZV9hcmdzKCkNCg0KICAgIG91dHB1dCA9IFBhdGgoYXJncy5vdXRwdXQpLnJlc29sdmUoKQ0KICAgIGFyY2hpdmVfZmlsdGVyID0gYXJncy5hcmNoaXZlDQogICAgcmVtb3ZlID0gYXJncy5yZW1vdmUNCg0KICAgIGV4dGVuc2lvbnMgPSBkaXNjb3Zlcl9leHRlbnNpb25zKCkNCg0KICAgICMgTW9kZSAteA0KICAgIGlmIGFyY2hpdmVfZmlsdGVyOg0KICAgICAgICB0YXJnZXQgPSBQYXRoKGFyY2hpdmVfZmlsdGVyKS5yZXNvbHZlKCkNCiAgICAgICAgaWYgbm90IHRhcmdldC5leGlzdHMoKToNCiAgICAgICAgICAgIGJhc2VuYW1lID0gb3MucGF0aC5iYXNlbmFtZShhcmNoaXZlX2ZpbHRlcikNCiAgICAgICAgICAgIGZvdW5kID0gTm9uZQ0KICAgICAgICAgICAgZm9yIHJvb3QsIGRpcnMsIGZpbGVzIGluIG9zLndhbGsoJy4nKToNCiAgICAgICAgICAgICAgICBpZiBiYXNlbmFtZSBpbiBmaWxlczoNCiAgICAgICAgICAgICAgICAgICAgZm91bmQgPSBQYXRoKHJvb3QpIC8gYmFzZW5hbWUNCiAgICAgICAgICAgICAgICAgICAgYnJlYWsNCiAgICAgICAgICAgIGlmIGZvdW5kIGlzIE5vbmU6DQogICAgICAgICAgICAgICAgcHJpbnQoZidBcmNoaXZlICJ7YXJjaGl2ZV9maWx0ZXJ9IiBub3QgZm91bmQuJykNCiAgICAgICAgICAgICAgICBzeXMuZXhpdCgxKQ0KICAgICAgICAgICAgdGFyZ2V0ID0gZm91bmQucmVzb2x2ZSgpDQoNCiAgICAgICAgZXh0cmFjdF9hcmNoaXZlKHRhcmdldCwgb3V0cHV0LCBSZW5QeUFyY2hpdmUpDQoNCiAgICAgICAgaWYgcmVtb3ZlOg0KICAgICAgICAgICAgb3MucmVtb3ZlKHN0cih0YXJnZXQpKQ0KICAgICAgICByZXR1cm4NCg0KICAgICMgTW9kZSBkw6lmYXV0DQogICAgYXJjaGl2ZXMgPSBkaXNjb3Zlcl9hcmNoaXZlcyhQYXRoKCcuJyksIGV4dGVuc2lvbnMpDQoNCiAgICBpZiBub3QgYXJjaGl2ZXM6DQogICAgICAgIHByaW50KCJObyBhcmNoaXZlcyBmb3VuZC4iKQ0KICAgICAgICByZXR1cm4NCg0KICAgIGZvciBhcmNoIGluIGFyY2hpdmVzOg0KICAgICAgICBleHRyYWN0X2FyY2hpdmUoYXJjaCwgb3V0cHV0LCBSZW5QeUFyY2hpdmUpDQoNCiAgICBpZiByZW1vdmU6DQogICAgICAgIGZvciBhcmNoIGluIGFyY2hpdmVzOg0KICAgICAgICAgICAgb3MucmVtb3ZlKHN0cihhcmNoKSkNCg0KDQppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOg0KICAgIG1haW4oKQ0K"
    )
)

:: rpatool by Shizmob 2022-08-24
::  https://github.com/Shizmob/rpatool
::  Version 0.8 w pickle5 - Require Python ^>= 3.8
::  Include SVAC-1.0 decoder & .jas files extensions by JoeLurmel@f95zone
if "%RPATOOL_NEW%" == "y" (
    >"%rpatool%.b64" (
        <nul set /p="IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMw0KDQpmcm9tIF9fZnV0dXJlX18gaW1wb3J0IHByaW50X2Z1bmN0aW9uDQoNCmltcG9ydCBzeXMNCmltcG9ydCBvcw0KaW1wb3J0IGNvZGVjcw0KaW1wb3J0IHBpY2tsZQ0KaW1wb3J0IGVycm5vDQppbXBvcnQgcmFuZG9tDQoNCnRyeToNCiAgICBpbXBvcnQgcGlja2xlNSBhcyBwaWNrbGUNCmV4Y2VwdDoNCiAgICBpbXBvcnQgcGlja2xlDQogICAgaWYgc3lzLnZlcnNpb25faW5mbyA8ICgzLCA4KToNCiAgICAgICAgcHJpbnQoJ3dhcm5pbmc6IHBpY2tsZTUgbW9kdWxlIGNvdWxkIG5vdCBiZSBsb2FkZWQgYW5kIFB5dGhvbiB2ZXJzaW9uIGlzIDwgMy44LCcsIGZpbGU9c3lzLnN0ZGVycikNCiAgICAgICAgcHJpbnQoJyAgICAgICAgIG5ld2VyIFJlblwnUHkgZ2FtZXMgbWF5IGZhaWwgdG8gdW5wYWNrIScsIGZpbGU9c3lzLnN0ZGVycikNCiAgICAgICAgaWYgc3lzLnZlcnNpb25faW5mbyA+PSAoMywgNSk6DQogICAgICAgICAgICBwcmludCgnICAgICAgICAgaWYgdGhpcyBvY2N1cnMsIGZpeCBpdCBieSBpbnN0YWxsaW5nIHBpY2tsZTU6JywgZmlsZT1zeXMuc3RkZXJyKQ0KICAgICAgICAgICAgcHJpbnQoJyAgICAgICAgICAgICB7fSAtbSBwaXAgaW5zdGFsbCBwaWNrbGU1Jy5mb3JtYXQoc3lzLmV4ZWN1dGFibGUpLCBmaWxlPXN5cy5zdGRlcnIpDQogICAgICAgIGVsc2U6DQogICAgICAgICAgICBwcmludCgnICAgICAgICAgaWYgdGhpcyBvY2N1cnMsIHBsZWFzZSB1cGdyYWRlIHRvIGEgbmV3ZXIgUHl0aG9uICg+PSAzLjUpLicsIGZpbGU9c3lzLnN0ZGVycikNCiAgICAgICAgcHJpbnQoZmlsZT1zeXMuc3RkZXJyKQ0KDQoNCmlmIHN5cy52ZXJzaW9uX2luZm9bMF0gPj0gMzoNCiAgICBkZWYgX3VuaWNvZGUodGV4dCk6DQogICAgICAgIHJldHVybiB0ZXh0DQoNCiAgICBkZWYgX3ByaW50YWJsZSh0ZXh0KToNCiAgICAgICAgcmV0dXJuIHRleHQNCg0KICAgIGRlZiBfdW5tYW5nbGUoZGF0YSk6DQogICAgICAgIGlmIHR5cGUoZGF0YSkgPT0gYnl0ZXM6DQogICAgICAgICAgICByZXR1cm4gZGF0YQ0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgcmV0dXJuIGRhdGEuZW5jb2RlKCdsYXRpbjEnKQ0KDQogICAgZGVmIF91bnBpY2tsZShkYXRhKToNCiAgICAgICAgIyBTcGVjaWZ5IGxhdGluMSBlbmNvZGluZyB0byBwcmV2ZW50IHJhdyBieXRlIHZhbHVlcyBmcm9tIGNhdXNpbmcgYW4gQVNDSUkgZGVjb2RlIGVycm9yLg0KICAgICAgICByZXR1cm4gcGlja2xlLmxvYWRzKGRhdGEsIGVuY29kaW5nPSdsYXRpbjEnKQ0KZWxpZiBzeXMudmVyc2lvbl9pbmZvWzBdID09IDI6DQogICAgZGVmIF91bmljb2RlKHRleHQpOg0KICAgICAgICBpZiBpc2luc3RhbmNlKHRleHQsIHVuaWNvZGUpOg0KICAgICAgICAgICAgcmV0dXJuIHRleHQNCiAgICAgICAgcmV0dXJuIHRleHQuZGVjb2RlKCd1dGYtOCcpDQoNCiAgICBkZWYgX3ByaW50YWJsZSh0ZXh0KToNCiAgICAgICAgcmV0dXJuIHRleHQuZW5jb2RlKCd1dGYtOCcpDQoNCiAgICBkZWYgX3VubWFuZ2xlKGRhdGEpOg0KICAgICAgICByZXR1cm4gZGF0YQ0KDQogICAgZGVmIF91bnBpY2tsZShkYXRhKToNCiAgICAgICAgcmV0dXJuIHBpY2tsZS5sb2FkcyhkYXRhKQ0KDQpjbGFzcyBSZW5QeUFyY2hpdmU6DQogICAgZmlsZSA9IE5vbmUNCiAgICBoYW5kbGUgPSBOb25lDQoNCiAgICBmaWxlcyA9IHt9DQogICAgaW5kZXhlcyA9IHt9DQoNCiAgICB2ZXJzaW9uID0gTm9uZQ0KICAgIHBhZGxlbmd0aCA9IDANCiAgICBrZXkgPSBOb25lDQogICAgdmVyYm9zZSA9IEZhbHNlDQoNCiAgICBSUEEyX01BR0lDID0gJ1JQQS0yLjAgJw0KICAgIFJQQTNfTUFHSUMgPSAnUlBBLTMuMCAnDQogICAgUldBM19NQUdJQyA9ICdSV0EtMy4wICcNCiAgICBSUEEzXzJfTUFHSUMgPSAnUlBBLTMuMiAnDQogICAgU1ZBQzFfTUFHSUMgPSAnU1ZBQy0xLjAgJw0KDQogICAgIyBGb3IgYmFja3dhcmQgY29tcGF0aWJpbGl0eSwgb3RoZXJ3aXNlIFB5dGhvbjMtcGFja2VkIGFyY2hpdmVzIHdvbid0IGJlIHJlYWQgYnkgUHl0aG9uMg0KICAgIFBJQ0tMRV9QUk9UT0NPTCA9IDINCg0KICAgIGRlZiBfX2luaXRfXyhzZWxmLCBmaWxlID0gTm9uZSwgdmVyc2lvbiA9IDMsIHBhZGxlbmd0aCA9IDAsIGtleSA9IDB4REVBREJFRUYsIHZlcmJvc2UgPSBGYWxzZSk6DQogICAgICAgIHNlbGYucGFkbGVuZ3RoID0gcGFkbGVuZ3RoDQogICAgICAgIHNlbGYua2V5ID0ga2V5DQogICAgICAgIHNlbGYudmVyYm9zZSA9IHZlcmJvc2UNCg0KICAgICAgICBpZiBmaWxlIGlzIG5vdCBOb25lOg0KICAgICAgICAgICAgc2VsZi5sb2FkKGZpbGUpDQogICAgICAgIGVsc2U6DQogICAgICAgICAgICBzZWxmLnZlcnNpb24gPSB2ZXJzaW9uDQoNCiAgICBkZWYgX19kZWxfXyhzZWxmKToNCiAgICAgICAgaWYgc2VsZi5oYW5kbGUgaXMgbm90IE5vbmU6DQogICAgICAgICAgICBzZWxmLmhhbmRsZS5jbG9zZSgpDQoNCiAgICAjIERldGVybWluZSBhcmNoaXZlIHZlcnNpb24uDQogICAgZGVmIGdldF92ZXJzaW9uKHNlbGYpOg0KICAgICAgICBzZWxmLmhhbmRsZS5zZWVrKDApDQogICAgICAgIG1hZ2ljID0gc2VsZi5oYW5kbGUucmVhZGxpbmUoKS5kZWNvZGUoJ3V0Zi04JykNCg0KICAgICAgICBpZiBtYWdpYy5zdGFydHN3aXRoKHNlbGYuU1ZBQzFfTUFHSUMpOg0KICAgICAgICAgICAgcGFydHMgPSBtYWdpYy5zcGxpdCgpDQogICAgICAgICAgICBpZiBsZW4ocGFydHMpID09IDQ6DQogICAgICAgICAgICAgICAgcmV0dXJuIDQgICAgICAjIHRydWUgU1ZBQy0xLjAgYXJjaGl2ZQ0KICAgICAgICAgICAgZWxzZToNCiAgICAgICAgICAgICAgICByZXR1cm4gMyAgICAjIGZhbHNlIFNWQUMsIGFjdHVhbGx5IFJQQS0zLjAgd2l0aCBhIGN1c3RvbSBoZWFkZXINCiAgICAgICAgZWxpZiBtYWdpYy5zdGFydHN3aXRoKHNlbGYuUlBBM18yX01BR0lDKToNCiAgICAgICAgICAgIHJldHVybiAzLjINCiAgICAgICAgZWxpZiBtYWdpYy5zdGFydHN3aXRoKHNlbGYuUlBBM19NQUdJQyk6DQogICAgICAgICAgICByZXR1cm4gMw0KICAgICAgICBlbGlmIG1hZ2ljLnN0YXJ0c3dpdGgoc2VsZi5SV0EzX01BR0lDKToNCiAgICAgICAgICAgIHJldHVybiAzDQogICAgICAgIGVsaWYgbWFnaWMuc3RhcnRzd2l0aChzZWxmLlJQQTJfTUFHSUMpOg0KICAgICAgICAgICAgcmV0dXJuIDINCiAgICAgICAgZWxpZiBzZWxmLmZpbGUuZW5kc3dpdGgoJy5ycGknKToNCiAgICAgICAgICAgIHJldHVybiAxDQoNCiAgICAgICAgcmFpc2UgVmFsdWVFcnJvcigndGhlIGdpdmVuIGZpbGUgaXMgbm90IGEgdmFsaWQgUmVuXCdQeSBhcmNoaXZlLCBvciBhbiB1bnN1cHBvcnRlZCB2ZXJzaW9uJykNCg0KICAgICMgRXh0cmFjdCBmaWxlIGluZGV4ZXMgZnJvbSBvcGVuZWQgYXJjaGl2ZS4NCiAgICBkZWYgZXh0cmFjdF9pbmRleGVzKHNlbGYpOg0KICAgICAgICBzZWxmLmhhbmRsZS5zZWVrKDApDQogICAgICAgIGluZGV4ZXMgPSBOb25lDQoNCiAgICAgICAgaWYgc2VsZi52ZXJzaW9uIGluIFsyLCAzLCAzLjJdOg0KICAgICAgICAgICAgIyBGZXRjaCBtZXRhZGF0YS4NCiAgICAgICAgICAgIG1ldGFkYXRhID0gc2VsZi5oYW5kbGUucmVhZGxpbmUoKQ0KICAgICAgICAgICAgdmFscyA9IG1ldGFkYXRhLnNwbGl0KCkNCiAgICAgICAgICAgIG9mZnNldCA9IGludCh2YWxzWzFdLCAxNikNCiAgICAgICAgICAgIGlmIHNlbGYudmVyc2lvbiA9PSAzOg0KICAgICAgICAgICAgICAgIHNlbGYua2V5ID0gMA0KICAgICAgICAgICAgICAgIGZvciBzdWJrZXkgaW4gdmFsc1syOl06DQogICAgICAgICAgICAgICAgICAgIHNlbGYua2V5IF49IGludChzdWJrZXksIDE2KQ0KICAgICAgICAgICAgZWxpZiBzZWxmLnZlcnNpb24gPT0gMy4yOg0KICAgICAgICAgICAgICAgIHNlbGYua2V5ID0gMA0KICAgICAgICAgICAgICAgIGZvciBzdWJrZXkgaW4gdmFsc1szOl06DQogICAgICAgICAgICAgICAgICAgIHNlbGYua2V5IF49IGludChzdWJrZXksIDE2KQ0KDQogICAgICAgICAgICAjIExvYWQgaW4gaW5kZXhlcy4NCiAgICAgICAgICAgIHNlbGYuaGFuZGxlLnNlZWsob2Zmc2V0KQ0KICAgICAgICAgICAgY29udGVudHMgPSBjb2RlY3MuZGVjb2RlKHNlbGYuaGFuZGxlLnJlYWQoKSwgJ3psaWInKQ0KICAgICAgICAgICAgaW5kZXhlcyA9IF91bnBpY2tsZShjb250ZW50cykNCg0KICAgICAgICAgICAgIyBEZW9iZnVzY2F0ZSBpbmRleGVzLg0KICAgICAgICAgICAgaWYgc2VsZi52ZXJzaW9uIGluIFszLCAzLjJdOg0KICAgICAgICAgICAgICAgIG9iZnVzY2F0ZWRfaW5kZXhlcyA9IGluZGV4ZXMNCiAgICAgICAgICAgICAgICBpbmRleGVzID0ge30NCiAgICAgICAgICAgICAgICBmb3IgaSBpbiBvYmZ1c2NhdGVkX2luZGV4ZXMua2V5cygpOg0KICAgICAgICAgICAgICAgICAgICBpZiBsZW4ob2JmdXNjYXRlZF9pbmRleGVzW2ldWzBdKSA9PSAyOg0KICAgICAgICAgICAgICAgICAgICAgICAgaW5kZXhlc1tpXSA9IFsgKG9mZnNldCBeIHNlbGYua2V5LCBsZW5ndGggXiBzZWxmLmtleSkgZm9yIG9mZnNldCwgbGVuZ3RoIGluIG9iZnVzY2F0ZWRfaW5kZXhlc1tpXSBdDQogICAgICAgICAgICAgICAgICAgIGVsc2U6DQogICAgICAgICAgICAgICAgICAgICAgICBpbmRleGVzW2ldID0gWyAob2Zmc2V0IF4gc2VsZi5rZXksIGxlbmd0aCBeIHNlbGYua2V5LCBwcmVmaXgpIGZvciBvZmZzZXQsIGxlbmd0aCwgcHJlZml4IGluIG9iZnVzY2F0ZWRfaW5kZXhlc1tpXSBdDQogICAgICAgIGVsc2U6DQogICAgICAgICAgICBpbmRleGVzID0gcGlja2xlLmxvYWRzKGNvZGVjcy5kZWNvZGUoc2VsZi5oYW5kbGUucmVhZCgpLCAnemxpYicpKQ0KDQogICAgICAgIHJldHVybiBpbmRleGVzDQoNCiAgICAjIEdlbmVyYXRlIHBzZXVkb3JhbmRvbSBwYWRkaW5nIChmb3Igd2hhdGV2ZXIgcmVhc29uKS4NCiAgICBkZWYgZ2VuZXJhdGVfcGFkZGluZyhzZWxmKToNCiAgICAgICAgbGVuZ3RoID0gcmFuZG9tLnJhbmRpbnQoMSwgc2VsZi5wYWRsZW5ndGgpDQoNCiAgICAgICAgcGFkZGluZyA9ICcnDQogICAgICAgIHdoaWxlIGxlbmd0aCA+IDA6DQogICAgICAgICAgICBwYWRkaW5nICs9IGNocihyYW5kb20ucmFuZGludCgxLCAyNTUpKQ0KICAgICAgICAgICAgbGVuZ3RoIC09IDENCg0KICAgICAgICByZXR1cm4gYnl0ZXMocGFkZGluZywgJ3V0Zi04JykNCg0KICAgICMgQ29udmVydHMgYSBmaWxlbmFtZSB0byBhcmNoaXZlIGZvcm1hdC4NCiAgICBkZWYgY29udmVydF9maWxlbmFtZShzZWxmLCBmaWxlbmFtZSk6DQogICAgICAgIChkcml2ZSwgZmlsZW5hbWUpID0gb3MucGF0aC5zcGxpdGRyaXZlKG9zLnBhdGgubm9ybXBhdGgoZmlsZW5hbWUpLnJlcGxhY2Uob3Muc2VwLCAnLycpKQ0KICAgICAgICByZXR1cm4gZmlsZW5hbWUNCg0KICAgICMgRGVidWcgKHZlcmJvc2UpIG1lc3NhZ2VzLg0KICAgIGRlZiB2ZXJib3NlX3ByaW50KHNlbGYsIG1lc3NhZ2UpOg0KICAgICAgICBpZiBzZWxmLnZlcmJvc2U6DQogICAgICAgICAgICBwcmludChtZXNzYWdlKQ0KDQoNCiAgICAjIExpc3QgZmlsZXMgaW4gYXJjaGl2ZSBhbmQgY3VycmVudCBpbnRlcm5hbCBzdG9yYWdlLg0KICAgIGRlZiBsaXN0KHNlbGYpOg0KICAgICAgICByZXR1cm4gbGlzdChzZWxmLmluZGV4ZXMua2V5cygpKSArIGxpc3Qoc2VsZi5maWxlcy5rZXlzKCkpDQoNCiAgICAjIENoZWNrIGlmIGEgZmlsZSBleGlzdHMgaW4gdGhlIGFyY2hpdmUuDQogICAgZGVmIGhhc19maWxlKHNlbGYsIGZpbGVuYW1lKToNCiAgICAgICAgZmlsZW5hbWUgPSBfdW5pY29kZShmaWxlbmFtZSkNCiAgICAgICAgcmV0dXJuIGZpbGVuYW1lIGluIHNlbGYuaW5kZXhlcy5rZXlzKCkgb3IgZmlsZW5hbWUgaW4gc2VsZi5maWxlcy5rZXlzKCkNCg0KICAgICMgUmVhZCBmaWxlIGZyb20gYXJjaGl2ZSBvciBpbnRlcm5hbCBzdG9yYWdlLg0KICAgIGRlZiByZWFkKHNlbGYsIGZpbGVuYW1lKToNCiAgICAgICAgZmlsZW5hbWUgPSBzZWxmLmNvbnZlcnRfZmlsZW5hbWUoX3VuaWNvZGUoZmlsZW5hbWUpKQ0KDQogICAgICAgICMgQ2hlY2sgaWYgdGhlIGZpbGUgZXhpc3RzIGluIG91ciBpbmRleGVzLg0KICAgICAgICBpZiBmaWxlbmFtZSBub3QgaW4gc2VsZi5maWxlcyBhbmQgZmlsZW5hbWUgbm90IGluIHNlbGYua"
        <nul set /p="W5kZXhlczoNCiAgICAgICAgICAgIHJhaXNlIElPRXJyb3IoZXJybm8uRU5PRU5ULCAndGhlIHJlcXVlc3RlZCBmaWxlIHswfSBkb2VzIG5vdCBleGlzdCBpbiB0aGUgZ2l2ZW4gUmVuXCdQeSBhcmNoaXZlJy5mb3JtYXQoDQogICAgICAgICAgICAgICAgX3ByaW50YWJsZShmaWxlbmFtZSkpKQ0KDQogICAgICAgICMgSWYgaXQncyBpbiBvdXIgb3BlbmVkIGFyY2hpdmUgaW5kZXgsIGFuZCBvdXIgYXJjaGl2ZSBoYW5kbGUgaXNuJ3QgdmFsaWQsIHNvbWV0aGluZyBpcyBvYnZpb3VzbHkgd3JvbmcuDQogICAgICAgIGlmIGZpbGVuYW1lIG5vdCBpbiBzZWxmLmZpbGVzIGFuZCBmaWxlbmFtZSBpbiBzZWxmLmluZGV4ZXMgYW5kIHNlbGYuaGFuZGxlIGlzIE5vbmU6DQogICAgICAgICAgICByYWlzZSBJT0Vycm9yKGVycm5vLkVOT0VOVCwgJ3RoZSByZXF1ZXN0ZWQgZmlsZSB7MH0gZG9lcyBub3QgZXhpc3QgaW4gdGhlIGdpdmVuIFJlblwnUHkgYXJjaGl2ZScuZm9ybWF0KA0KICAgICAgICAgICAgICAgIF9wcmludGFibGUoZmlsZW5hbWUpKSkNCg0KICAgICAgICAjIENoZWNrIG91ciBzaW1wbGlmaWVkIGludGVybmFsIGluZGV4ZXMgZmlyc3QsIGluIGNhc2Ugc29tZW9uZSB3YW50cyB0byByZWFkIGEgZmlsZSB0aGV5IGFkZGVkIGJlZm9yZSB3aXRob3V0IHNhdmluZywgZm9yIHNvbWUgdW5ob2x5IHJlYXNvbi4NCiAgICAgICAgaWYgZmlsZW5hbWUgaW4gc2VsZi5maWxlczoNCiAgICAgICAgICAgIHNlbGYudmVyYm9zZV9wcmludCgnUmVhZGluZyBmaWxlIHswfSBmcm9tIGludGVybmFsIHN0b3JhZ2UuLi4nLmZvcm1hdChfcHJpbnRhYmxlKGZpbGVuYW1lKSkpDQogICAgICAgICAgICByZXR1cm4gc2VsZi5maWxlc1tmaWxlbmFtZV0NCiAgICAgICAgIyBXZSBuZWVkIHRvIHJlYWQgdGhlIGZpbGUgZnJvbSBvdXIgb3BlbiBhcmNoaXZlLg0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgIyBSZWFkIG9mZnNldCBhbmQgbGVuZ3RoLCBzZWVrIHRvIHRoZSBvZmZzZXQgYW5kIHJlYWQgdGhlIGZpbGUgY29udGVudHMuDQogICAgICAgICAgICBpZiBsZW4oc2VsZi5pbmRleGVzW2ZpbGVuYW1lXVswXSkgPT0gMzoNCiAgICAgICAgICAgICAgICAob2Zmc2V0LCBsZW5ndGgsIHByZWZpeCkgPSBzZWxmLmluZGV4ZXNbZmlsZW5hbWVdWzBdDQogICAgICAgICAgICBlbHNlOg0KICAgICAgICAgICAgICAgIChvZmZzZXQsIGxlbmd0aCkgPSBzZWxmLmluZGV4ZXNbZmlsZW5hbWVdWzBdDQogICAgICAgICAgICAgICAgcHJlZml4ID0gJycNCg0KICAgICAgICAgICAgc2VsZi52ZXJib3NlX3ByaW50KCdSZWFkaW5nIGZpbGUgezB9IGZyb20gZGF0YSBmaWxlIHsxfS4uLiAob2Zmc2V0ID0gezJ9LCBsZW5ndGggPSB7M30gYnl0ZXMpJy5mb3JtYXQoDQogICAgICAgICAgICAgICAgX3ByaW50YWJsZShmaWxlbmFtZSksIHNlbGYuZmlsZSwgb2Zmc2V0LCBsZW5ndGgpKQ0KICAgICAgICAgICAgc2VsZi5oYW5kbGUuc2VlayhvZmZzZXQpDQogICAgICAgICAgICByZXR1cm4gX3VubWFuZ2xlKHByZWZpeCkgKyBzZWxmLmhhbmRsZS5yZWFkKGxlbmd0aCAtIGxlbihwcmVmaXgpKQ0KDQogICAgIyBNb2RpZnkgYSBmaWxlIGluIGFyY2hpdmUgb3IgaW50ZXJuYWwgc3RvcmFnZS4NCiAgICBkZWYgY2hhbmdlKHNlbGYsIGZpbGVuYW1lLCBjb250ZW50cyk6DQogICAgICAgIGZpbGVuYW1lID0gX3VuaWNvZGUoZmlsZW5hbWUpDQoNCiAgICAgICAgIyBPdXIgJ2NoYW5nZScgaXMgYmFzaWNhbGx5IHJlbW92aW5nIHRoZSBmaWxlIGZyb20gb3VyIGluZGV4ZXMgZmlyc3QsIGFuZCB0aGVuIHJlLWFkZGluZyBpdC4NCiAgICAgICAgc2VsZi5yZW1vdmUoZmlsZW5hbWUpDQogICAgICAgIHNlbGYuYWRkKGZpbGVuYW1lLCBjb250ZW50cykNCg0KICAgICMgQWRkIGEgZmlsZSB0byB0aGUgaW50ZXJuYWwgc3RvcmFnZS4NCiAgICBkZWYgYWRkKHNlbGYsIGZpbGVuYW1lLCBjb250ZW50cyk6DQogICAgICAgIGZpbGVuYW1lID0gc2VsZi5jb252ZXJ0X2ZpbGVuYW1lKF91bmljb2RlKGZpbGVuYW1lKSkNCiAgICAgICAgaWYgZmlsZW5hbWUgaW4gc2VsZi5maWxlcyBvciBmaWxlbmFtZSBpbiBzZWxmLmluZGV4ZXM6DQogICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCdmaWxlIHswfSBhbHJlYWR5IGV4aXN0cyBpbiBhcmNoaXZlJy5mb3JtYXQoX3ByaW50YWJsZShmaWxlbmFtZSkpKQ0KDQogICAgICAgIHNlbGYudmVyYm9zZV9wcmludCgnQWRkaW5nIGZpbGUgezB9IHRvIGFyY2hpdmUuLi4gKGxlbmd0aCA9IHsxfSBieXRlcyknLmZvcm1hdCgNCiAgICAgICAgICAgIF9wcmludGFibGUoZmlsZW5hbWUpLCBsZW4oY29udGVudHMpKSkNCiAgICAgICAgc2VsZi5maWxlc1tmaWxlbmFtZV0gPSBjb250ZW50cw0KDQogICAgIyBSZW1vdmUgYSBmaWxlIGZyb20gYXJjaGl2ZSBvciBpbnRlcm5hbCBzdG9yYWdlLg0KICAgIGRlZiByZW1vdmUoc2VsZiwgZmlsZW5hbWUpOg0KICAgICAgICBmaWxlbmFtZSA9IF91bmljb2RlKGZpbGVuYW1lKQ0KICAgICAgICBpZiBmaWxlbmFtZSBpbiBzZWxmLmZpbGVzOg0KICAgICAgICAgICAgc2VsZi52ZXJib3NlX3ByaW50KCdSZW1vdmluZyBmaWxlIHswfSBmcm9tIGludGVybmFsIHN0b3JhZ2UuLi4nLmZvcm1hdChfcHJpbnRhYmxlKGZpbGVuYW1lKSkpDQogICAgICAgICAgICBkZWwgc2VsZi5maWxlc1tmaWxlbmFtZV0NCiAgICAgICAgZWxpZiBmaWxlbmFtZSBpbiBzZWxmLmluZGV4ZXM6DQogICAgICAgICAgICBzZWxmLnZlcmJvc2VfcHJpbnQoJ1JlbW92aW5nIGZpbGUgezB9IGZyb20gYXJjaGl2ZSBpbmRleGVzLi4uJy5mb3JtYXQoX3ByaW50YWJsZShmaWxlbmFtZSkpKQ0KICAgICAgICAgICAgZGVsIHNlbGYuaW5kZXhlc1tmaWxlbmFtZV0NCiAgICAgICAgZWxzZToNCiAgICAgICAgICAgIHJhaXNlIElPRXJyb3IoZXJybm8uRU5PRU5ULCAndGhlIHJlcXVlc3RlZCBmaWxlIHswfSBkb2VzIG5vdCBleGlzdCBpbiB0aGlzIGFyY2hpdmUnLmZvcm1hdChfcHJpbnRhYmxlKGZpbGVuYW1lKSkpDQoNCiAgICAjIExvYWQgYXJjaGl2ZS4NCiAgICBkZWYgbG9hZChzZWxmLCBmaWxlbmFtZSk6DQogICAgICAgIGZpbGVuYW1lID0gX3VuaWNvZGUoZmlsZW5hbWUpDQoNCiAgICAgICAgaWYgc2VsZi5oYW5kbGUgaXMgbm90IE5vbmU6DQogICAgICAgICAgICBzZWxmLmhhbmRsZS5jbG9zZSgpDQogICAgICAgIHNlbGYuZmlsZSA9IGZpbGVuYW1lDQogICAgICAgIHNlbGYuZmlsZXMgPSB7fQ0KICAgICAgICBzZWxmLmhhbmRsZSA9IG9wZW4oc2VsZi5maWxlLCAncmInKQ0KICAgICAgICBzZWxmLnZlcnNpb24gPSBzZWxmLmdldF92ZXJzaW9uKCkNCiAgICAgICAgaWYgc2VsZi52ZXJzaW9uIGluIFsxLCAyLCAzLCAzLjJdOg0KICAgICAgICAgICAgc2VsZi5pbmRleGVzID0gc2VsZi5leHRyYWN0X2luZGV4ZXMoKQ0KICAgICAgICBlbGlmIHNlbGYudmVyc2lvbiA9PSA0Og0KICAgICAgICAgICAgc2VsZi5pbmRleGVzID0gc2VsZi5leHRyYWN0X3N2YWMxX2luZGV4ZXMoKQ0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcigndW5zdXBwb3J0ZWQgUmVuXCdQeSBhcmNoaXZlIHZlcnNpb24nKQ0KDQogICAgIyBFeHRyYWN0IGZpbGUgaW5kZXhlcyBmcm9tIG9wZW5lZCBTVkFDLTEuMCBhcmNoaXZlLg0KICAgIGRlZiBleHRyYWN0X3N2YWMxX2luZGV4ZXMoc2VsZik6DQogICAgICAgIGltcG9ydCBqc29uLCB6bGliDQoNCiAgICAgICAgc2VsZi5oYW5kbGUuc2VlaygwKQ0KICAgICAgICBoZWFkZXIgPSBzZWxmLmhhbmRsZS5yZWFkbGluZSgpLmRlY29kZSgndXRmLTgnKQ0KICAgICAgICBwYXJ0cyA9IGhlYWRlci5zcGxpdCgpDQoNCiAgICAgICAgIyBwYXJ0c1sxXSA9IG9mZnNldCBoZXgNCiAgICAgICAgaW5kZXhfb2Zmc2V0ID0gaW50KHBhcnRzWzFdLCAxNikNCg0KICAgICAgICAjIEdvIHRvIHRoZSBPZ2dTIGJsb2NrIGNvbnRhaW5pbmcgdGhlIGNvbXByZXNzZWQgSlNPTiBkYXRhLA0KICAgICAgICAjIHJlYWQgaXQgYW5kIHRyeSB0byBkZWNvZGUgaXQgYXMgemxpYiBmaXJzdCwgaWYgdGhhdCBmYWlscywNCiAgICAgICAgIyBkZWNvZGUgaXQgYXMgT2dnIGVuY2Fwc3VsYXRlZCBWb3JiaXMgY29tbWVudHMuDQogICAgICAgIHNlbGYuaGFuZGxlLnNlZWsoaW5kZXhfb2Zmc2V0KQ0KICAgICAgICBjb21wcmVzc2VkID0gc2VsZi5oYW5kbGUucmVhZCgpDQoNCiAgICAgICAgdHJ5Og0KICAgICAgICAgICAgIyBWYXJpYW50IEI6IERpcmVjdCB6bGliIHN0cmVhbSwgbm8gT2dnIGVuY2Fwc3VsYXRpb24NCiAgICAgICAgICAgIGpzb25fZGF0YSA9IHpsaWIuZGVjb21wcmVzcyhjb21wcmVzc2VkKS5kZWNvZGUoInV0Zi04IikNCiAgICAgICAgZXhjZXB0Og0KICAgICAgICAgICAgIyBWYXJpYW50IEE6IEVuY2Fwc3VsYXRlZCBPZ2cgc3RyZWFtLCBkZWNvZGUgaXQgdG8gZXh0cmFjdCB0aGUgSlNPTiBmcm9tIFZvcmJpcyBjb21tZW50cw0KICAgICAgICAgICAganNvbl9kYXRhID0gc2VsZi5kZWNvZGVfc3ZhYzFfb2dnKGNvbXByZXNzZWQpDQoNCiAgICAgICAgIyBEZWNvZGUgVm9yYmlzIHN0cmVhbSDihpIgSlNPTiBkYXRhDQogICAgICAgIGpzb25fZGF0YSA9IHNlbGYuZGVjb2RlX3N2YWMxX29nZyhvZ2dfZGF0YSkNCg0KICAgICAgICAjIExvYWQgSlNPTiBkYXRhIGludG8gYSBQeXRob24gZGljdA0KICAgICAgICByYXcgPSBqc29uLmxvYWRzKGpzb25fZGF0YSkNCg0KICAgICAgICAjIENvbnZlcnQgdG8gaW50ZXJuYWwgaW5kZXggZm9ybWF0DQogICAgICAgIGluZGV4ZXMgPSB7fQ0KICAgICAgICBmb3IgbmFtZSwgaW5mbyBpbiByYXdbImZpbGVzIl0uaXRlbXMoKToNCiAgICAgICAgICAgIG9mZnNldCwgbGVuZ3RoID0gaW5mbw0KICAgICAgICAgICAgaW5kZXhlc1tuYW1lXSA9IFsob2Zmc2V0LCBsZW5ndGgpXQ0KDQogICAgICAgIHJldHVybiBpbmRleGVzDQoNCiAgICBkZWYgZGVjb2RlX3N2YWMxX29nZyhzZWxmLCBkYXRhKToNCiAgICAgICAgIyBTZWFyY2ggZm9yIHBhY2tldCB0eXBlIDMg4oCcdm9yYmlz4oCdLCB3aGljaCBjb250YWlucyB0aGUgY29tbWVudHMgd2l0aCB0aGUgSlNPTiBkYXRhLg0KICAgICAgICBtYXJrZXIgPSBiIlx4MDN2b3JiaXMiDQogICAgICAgIHBvcyA9IGRhdGEuZmluZChtYXJrZXIpDQogICAgICAgIGlmIHBvcyA9PSAtMToNCiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoIlNWQUMtMS4wOiBWb3JiaXMgcGFja2FnZSAodHlwZSAzKSBub3QgZm91bmQgaW4gT2dnIHN0cmVhbSIpDQoNCiAgICAgICAgIyBBZnRlciB0aGUgbWFya2VyLCB0aGVyZSBpcyBhIOKAnHZlbmRvcl9sZW5ndGjigJ0gZmllbGQgKDQgbGl0dGxlLWVuZGlhbiBieXRlcykuDQogICAgICAgIHZlbmRvcl9sZW4gPSBpbnQuZnJvbV9ieXRlcyhkYXRhW3Bvcys3OnBvcysxMV0sICJsaXR0bGUiKQ0KDQogICAgICAgICMgU2tpcCB0aGUgdmVuZG9yIHN0cmluZyAodmVuZG9yX2xlbmd0aCBieXRlcykgdG8gZ2V0IHRvIHRoZSBjb21tZW50IGxpc3QuDQogICAgICAgIGNvbW1lbnRfc3RhcnQgPSBwb3MgKyAxMSArIHZlbmRvcl9sZW4NCg0KICAgICAgICAjIFJlYWQgdGhlIG51bWJlciBvZiBjb21tZW50cyAoNCBieXRlcyBMRSkNCiAgICAgICAgY29tbWVudF9jb3VudCA9IGludC5mcm9tX2J5dGVzKGRhdGFbY29tbWVudF9zdGFydDpjb21tZW50X3N0YXJ0KzRdLCAibGl0dGxlIikNCiAgICAgICAgcCA9IGNvbW1lbnRfc3RhcnQgKyA0DQoNCiAgICAgICAgIyBCcm93c2UgVm9yYmlzIGNvbW1lbnRzIHRvIGZpbmQgdGhlIG9uZSBzdGFydGluZyB3aXRoICJKU09OPSIsIHdoaWNoIGNvbnRhaW5zIHRoZSBKU09OIGRhdGEuDQogICAgICAgIGZvciBfIGluIHJhbmdlKGNvbW1lbnRfY291bnQpOg0KICAgICAgICAgICAgbGVuZ3RoID0gaW50LmZyb21fYnl0ZXMoZGF0YVtwOnArNF0sICJsaXR0bGUiKQ0KICAgICAgICAgICAgcCArPSA0DQogICAgICAgICAgICBjb21tZW50ID0gZGF0YVtwOnArbGVuZ3RoXQ0KICAgICAgICAgICAgcCArPSBsZW5ndGgNCg0KICAgICAgICAgICAgIyBUaGUgSlNPTiBpcyBpbiBhIGNvbW1lbnQuDQogICAgICAgICAgICBpZiBjb21tZW50LnN0YXJ0c3dpdGgoYiJKU09OPSIpOg0KICAgICAgICAgICAgICAgIHJldHVybiBjb21tZW50WzU6XS5kZWNvZGUoInV0Zi"
        <nul set /p="04IikNCg0KICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJTVkFDLTEuMDogSlNPTiBub3QgZm91bmQgaW4gVm9yYmlzIGNvbW1lbnRzLiIpDQoNCiAgICAjIFNhdmUgY3VycmVudCBzdGF0ZSBpbnRvIGEgbmV3IGZpbGUsIG1lcmdpbmcgYXJjaGl2ZSBhbmQgaW50ZXJuYWwgc3RvcmFnZSwgcmVidWlsZGluZyBpbmRleGVzLCBhbmQgb3B0aW9uYWxseSBzYXZpbmcgaW4gYW5vdGhlciBmb3JtYXQgdmVyc2lvbi4NCiAgICBkZWYgc2F2ZShzZWxmLCBmaWxlbmFtZSA9IE5vbmUpOg0KICAgICAgICBmaWxlbmFtZSA9IF91bmljb2RlKGZpbGVuYW1lKQ0KDQogICAgICAgIGlmIGZpbGVuYW1lIGlzIE5vbmU6DQogICAgICAgICAgICBmaWxlbmFtZSA9IHNlbGYuZmlsZQ0KICAgICAgICBpZiBmaWxlbmFtZSBpcyBOb25lOg0KICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignbm8gdGFyZ2V0IGZpbGUgZm91bmQgZm9yIHNhdmluZyBhcmNoaXZlJykNCiAgICAgICAgaWYgc2VsZi52ZXJzaW9uICE9IDIgYW5kIHNlbGYudmVyc2lvbiAhPSAzOg0KICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignc2F2aW5nIGlzIG9ubHkgc3VwcG9ydGVkIGZvciB2ZXJzaW9uIDIgYW5kIDMgYXJjaGl2ZXMnKQ0KDQogICAgICAgIHNlbGYudmVyYm9zZV9wcmludCgnUmVidWlsZGluZyBhcmNoaXZlIGluZGV4Li4uJykNCiAgICAgICAgIyBGaWxsIG91ciBvd24gZmlsZXMgc3RydWN0dXJlIHdpdGggdGhlIGZpbGVzIGFkZGVkIG9yIGNoYW5nZWQgaW4gdGhpcyBzZXNzaW9uLg0KICAgICAgICBmaWxlcyA9IHNlbGYuZmlsZXMNCiAgICAgICAgIyBGaXJzdCwgcmVhZCBmaWxlcyBmcm9tIHRoZSBjdXJyZW50IGFyY2hpdmUgaW50byBvdXIgZmlsZXMgc3RydWN0dXJlLg0KICAgICAgICBmb3IgZmlsZSBpbiBsaXN0KHNlbGYuaW5kZXhlcy5rZXlzKCkpOg0KICAgICAgICAgICAgY29udGVudCA9IHNlbGYucmVhZChmaWxlKQ0KICAgICAgICAgICAgIyBSZW1vdmUgZnJvbSBpbmRleGVzIGFycmF5IG9uY2UgcmVhZCwgYWRkIHRvIG91ciBvd24gYXJyYXkuDQogICAgICAgICAgICBkZWwgc2VsZi5pbmRleGVzW2ZpbGVdDQogICAgICAgICAgICBmaWxlc1tmaWxlXSA9IGNvbnRlbnQNCg0KICAgICAgICAjIFByZWRpY3QgaGVhZGVyIGxlbmd0aCwgd2UnbGwgd3JpdGUgdGhhdCBvbmUgbGFzdC4NCiAgICAgICAgb2Zmc2V0ID0gMA0KICAgICAgICBpZiBzZWxmLnZlcnNpb24gPT0gMzoNCiAgICAgICAgICAgIG9mZnNldCA9IDM0DQogICAgICAgIGVsaWYgc2VsZi52ZXJzaW9uID09IDI6DQogICAgICAgICAgICBvZmZzZXQgPSAyNQ0KICAgICAgICBhcmNoaXZlID0gb3BlbihmaWxlbmFtZSwgJ3diJykNCiAgICAgICAgYXJjaGl2ZS5zZWVrKG9mZnNldCkNCg0KICAgICAgICAjIEJ1aWxkIG91ciBvd24gaW5kZXhlcyB3aGlsZSB3cml0aW5nIGZpbGVzIHRvIHRoZSBhcmNoaXZlLg0KICAgICAgICBpbmRleGVzID0ge30NCiAgICAgICAgc2VsZi52ZXJib3NlX3ByaW50KCdXcml0aW5nIGZpbGVzIHRvIGFyY2hpdmUgZmlsZS4uLicpDQogICAgICAgIGZvciBmaWxlLCBjb250ZW50IGluIGZpbGVzLml0ZW1zKCk6DQogICAgICAgICAgICAjIEdlbmVyYXRlIHJhbmRvbSBwYWRkaW5nLCBmb3Igd2hhdGV2ZXIgcmVhc29uLg0KICAgICAgICAgICAgaWYgc2VsZi5wYWRsZW5ndGggPiAwOg0KICAgICAgICAgICAgICAgIHBhZGRpbmcgPSBzZWxmLmdlbmVyYXRlX3BhZGRpbmcoKQ0KICAgICAgICAgICAgICAgIGFyY2hpdmUud3JpdGUocGFkZGluZykNCiAgICAgICAgICAgICAgICBvZmZzZXQgKz0gbGVuKHBhZGRpbmcpDQoNCiAgICAgICAgICAgIGFyY2hpdmUud3JpdGUoY29udGVudCkNCiAgICAgICAgICAgICMgVXBkYXRlIGluZGV4Lg0KICAgICAgICAgICAgaWYgc2VsZi52ZXJzaW9uID09IDM6DQogICAgICAgICAgICAgICAgaW5kZXhlc1tmaWxlXSA9IFsgKG9mZnNldCBeIHNlbGYua2V5LCBsZW4oY29udGVudCkgXiBzZWxmLmtleSkgXQ0KICAgICAgICAgICAgZWxpZiBzZWxmLnZlcnNpb24gPT0gMjoNCiAgICAgICAgICAgICAgICBpbmRleGVzW2ZpbGVdID0gWyAob2Zmc2V0LCBsZW4oY29udGVudCkpIF0NCiAgICAgICAgICAgIG9mZnNldCArPSBsZW4oY29udGVudCkNCg0KICAgICAgICAjIFdyaXRlIHRoZSBpbmRleGVzLg0KICAgICAgICBzZWxmLnZlcmJvc2VfcHJpbnQoJ1dyaXRpbmcgYXJjaGl2ZSBpbmRleCB0byBhcmNoaXZlIGZpbGUuLi4nKQ0KICAgICAgICBhcmNoaXZlLndyaXRlKGNvZGVjcy5lbmNvZGUocGlja2xlLmR1bXBzKGluZGV4ZXMsIHNlbGYuUElDS0xFX1BST1RPQ09MKSwgJ3psaWInKSkNCiAgICAgICAgIyBOb3cgd3JpdGUgdGhlIGhlYWRlci4NCiAgICAgICAgc2VsZi52ZXJib3NlX3ByaW50KCdXcml0aW5nIGhlYWRlciB0byBhcmNoaXZlIGZpbGUuLi4gKHZlcnNpb24gPSBSUEF2ezB9KScuZm9ybWF0KHNlbGYudmVyc2lvbikpDQogICAgICAgIGFyY2hpdmUuc2VlaygwKQ0KICAgICAgICBpZiBzZWxmLnZlcnNpb24gPT0gMzoNCiAgICAgICAgICAgIGFyY2hpdmUud3JpdGUoY29kZWNzLmVuY29kZSgne317OjAxNnh9IHs6MDh4fVxuJy5mb3JtYXQoc2VsZi5SUEEzX01BR0lDLCBvZmZzZXQsIHNlbGYua2V5KSkpDQogICAgICAgIGVsc2U6DQogICAgICAgICAgICBhcmNoaXZlLndyaXRlKGNvZGVjcy5lbmNvZGUoJ3t9ezowMTZ4fVxuJy5mb3JtYXQoc2VsZi5SUEEyX01BR0lDLCBvZmZzZXQpKSkNCiAgICAgICAgIyBXZSdyZSBkb25lLCBjbG9zZSBpdC4NCiAgICAgICAgYXJjaGl2ZS5jbG9zZSgpDQoNCiAgICAgICAgIyBSZWxvYWQgdGhlIGZpbGUgaW4gb3VyIGlubmVyIGRhdGFiYXNlLg0KICAgICAgICBzZWxmLmxvYWQoZmlsZW5hbWUpDQoNCmlmIF9fbmFtZV9fID09ICJfX21haW5fXyI6DQogICAgaW1wb3J0IGFyZ3BhcnNlDQoNCiAgICBwYXJzZXIgPSBhcmdwYXJzZS5Bcmd1bWVudFBhcnNlcigNCiAgICAgICAgZGVzY3JpcHRpb249J0EgdG9vbCBmb3Igd29ya2luZyB3aXRoIFJlblwnUHkgYXJjaGl2ZSBmaWxlcy4nLA0KICAgICAgICBlcGlsb2c9J1RoZSBGSUxFIGFyZ3VtZW50IGNhbiBvcHRpb25hbGx5IGJlIGluIEFSQ0hJVkU9UkVBTCBmb3JtYXQsIG1hcHBpbmcgYSBmaWxlIGluIHRoZSBhcmNoaXZlIGZpbGUgc3lzdGVtIHRvIGEgZmlsZSBvbiB5b3VyIHJlYWwgZmlsZSBzeXN0ZW0uIEFuIGV4YW1wbGUgb2YgdGhpczogcnBhdG9vbCAteCB0ZXN0LnJwYSBzY3JpcHQucnB5Yz0vaG9tZS9mb28vdGVzdC5ycHljJywNCiAgICAgICAgYWRkX2hlbHA9RmFsc2UpDQoNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCdhcmNoaXZlJywgbWV0YXZhcj0nQVJDSElWRScsIGhlbHA9J1RoZSBSZW5cJ3B5IGFyY2hpdmUgZmlsZSB0byBvcGVyYXRlIG9uLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnZmlsZXMnLCBtZXRhdmFyPSdGSUxFJywgbmFyZ3M9JyonLCBhY3Rpb249J2FwcGVuZCcsIGhlbHA9J1plcm8gb3IgbW9yZSBmaWxlcyB0byBvcGVyYXRlIG9uLicpDQoNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctbCcsICctLWxpc3QnLCBhY3Rpb249J3N0b3JlX3RydWUnLCBoZWxwPSdMaXN0IGZpbGVzIGluIGFyY2hpdmUgQVJDSElWRS4nKQ0KICAgIHBhcnNlci5hZGRfYXJndW1lbnQoJy14JywgJy0tZXh0cmFjdCcsIGFjdGlvbj0nc3RvcmVfdHJ1ZScsIGhlbHA9J0V4dHJhY3QgRklMRXMgZnJvbSBBUkNISVZFLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLWMnLCAnLS1jcmVhdGUnLCBhY3Rpb249J3N0b3JlX3RydWUnLCBoZWxwPSdDcmVhdGl2ZSBBUkNISVZFIGZyb20gRklMRXMuJykNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctZCcsICctLWRlbGV0ZScsIGFjdGlvbj0nc3RvcmVfdHJ1ZScsIGhlbHA9J0RlbGV0ZSBGSUxFcyBmcm9tIEFSQ0hJVkUuJykNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctYScsICctLWFwcGVuZCcsIGFjdGlvbj0nc3RvcmVfdHJ1ZScsIGhlbHA9J0FwcGVuZCBGSUxFcyB0byBBUkNISVZFLicpDQoNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctMicsICctLXR3bycsIGFjdGlvbj0nc3RvcmVfdHJ1ZScsIGhlbHA9J1VzZSB0aGUgUlBBdjIgZm9ybWF0IGZvciBjcmVhdGluZy9hcHBlbmRpbmcgdG8gYXJjaGl2ZXMuJykNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctMycsICctLXRocmVlJywgYWN0aW9uPSdzdG9yZV90cnVlJywgaGVscD0nVXNlIHRoZSBSUEF2MyBmb3JtYXQgZm9yIGNyZWF0aW5nL2FwcGVuZGluZyB0byBhcmNoaXZlcyAoZGVmYXVsdCkuJykNCg0KICAgIHBhcnNlci5hZGRfYXJndW1lbnQoJy1rJywgJy0ta2V5JywgbWV0YXZhcj0nS0VZJywgaGVscD0nVGhlIG9iZnVzY2F0aW9uIGtleSB1c2VkIGZvciBjcmVhdGluZyBSUEF2MyBhcmNoaXZlcywgaW4gaGV4YWRlY2ltYWwgKGRlZmF1bHQ6IDB4REVBREJFRUYpLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLXAnLCAnLS1wYWRkaW5nJywgbWV0YXZhcj0nQ09VTlQnLCBoZWxwPSdUaGUgbWF4aW11bSBudW1iZXIgb2YgYnl0ZXMgb2YgcGFkZGluZyB0byBhZGQgYmV0d2VlbiBmaWxlcyAoZGVmYXVsdDogMCkuJykNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctbycsICctLW91dGZpbGUnLCBoZWxwPSdBbiBhbHRlcm5hdGl2ZSBvdXRwdXQgYXJjaGl2ZSBmaWxlIHdoZW4gYXBwZW5kaW5nIHRvIG9yIGRlbGV0aW5nIGZyb20gYXJjaGl2ZXMsIG9yIG91dHB1dCBkaXJlY3Rvcnkgd2hlbiBleHRyYWN0aW5nLicpDQoNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctaCcsICctLWhlbHAnLCBhY3Rpb249J2hlbHAnLCBoZWxwPSdQcmludCB0aGlzIGhlbHAgYW5kIGV4aXQuJykNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctdicsICctLXZlcmJvc2UnLCBhY3Rpb249J3N0b3JlX3RydWUnLCBoZWxwPSdCZSBhIGJpdCBtb3JlIHZlcmJvc2Ugd2hpbGUgcGVyZm9ybWluZyBvcGVyYXRpb25zLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLVYnLCAnLS12ZXJzaW9uJywgYWN0aW9uPSd2ZXJzaW9uJywgdmVyc2lvbj0ncnBhdG9vbCB2MC44JywgaGVscD0nU2hvdyB2ZXJzaW9uIGluZm9ybWF0aW9uLicpDQogICAgYXJndW1lbnRzID0gcGFyc2VyLnBhcnNlX2FyZ3MoKQ0KDQogICAgIyBEZXRlcm1pbmUgUlBBIHZlcnNpb24uDQogICAgaWYgYXJndW1lbnRzLnR3bzoNCiAgICAgICAgdmVyc2lvbiA9IDINCiAgICBlbHNlOg0KICAgICAgICB2ZXJzaW9uID0gMw0KDQogICAgIyBEZXRlcm1pbmUgUlBBdjMga2V5Lg0KICAgIGlmICdrZXknIGluIGFyZ3VtZW50cyBhbmQgYXJndW1lbnRzLmtleSBpcyBub3QgTm9uZToNCiAgICAgICAga2V5ID0gaW50KGFyZ3VtZW50cy5rZXksIDE2KQ0KICAgIGVsc2U6DQogICAgICAgIGtleSA9IDB4REVBREJFRUYNCg0KICAgICMgRGV0ZXJtaW5lIHBhZGRpbmcgYnl0ZXMuDQogICAgaWYgJ3BhZGRpbmcnIGluIGFyZ3VtZW50cyBhbmQgYXJndW1lbnRzLnBhZGRpbmcgaXMgbm90IE5vbmU6DQogICAgICAgIHBhZGRpbmcgPSBpbnQoYXJndW1lbnRzLnBhZGRpbmcpDQogICAgZWxzZToNCiAgICAgICAgcGFkZGluZyA9IDANCg0KICAgICMgRGV0ZXJtaW5lIG91dHB1dCBmaWxlL2RpcmVjdG9yeSBhbmQgaW5wdXQgYXJjaGl2ZQ0KICAgIGlmIGFyZ3VtZW50cy5jcmVhdGU6DQogICAgICAgIGFyY2hpdmUgPSBOb25lDQogICAgICAgIG91dHB1dCA9IF91bmljb2RlKGFyZ3VtZW50cy5hcmNoaXZlKQ0KICAgIGVsc2U6DQogICAgICAgIGFyY2hpdmUgPSBfdW5pY29kZShhcmd1bWVudHMuYXJjaGl2ZSkNCiAgICAgICAgaWYgJ291dGZpbGUnIGluIGFyZ3VtZW50cyBhbmQgYXJndW1lbnRzLm91dGZpbGUgaXMgbm90IE5vbmU6DQogICAgICAgICAgICBvdXRwdXQgPSBfdW5pY29kZShhcmd1bWVudHMub3V0ZmlsZSkNCiAgICAgICAgZWxzZToNCiAgICAgICAgICAgICMgRGVmYXVsdCBvdXRwdXQgZGlyZWN0b3J5IGZvciBleHRyYWN0aW9uIGlzIHRoZSBjdXJyZW50IGRpcmVjdG9yeS4NCiAgICAgICAgICAgIGlmIGFyZ3VtZW50cy5leHRyYWN0Og0KICAgICAgICAgICAgICAgIG91dHB1dCA9ICcuJw0KICAgICAgICAgICAgZWxzZToNCiAgICAgICAgICAgICAgICBvdXRwdXQgPSBfdW5pY29kZShhcmd1bWVudHMuYXJjaGl2ZSkNCg0KICAgICM"
        <nul set /p="gTm9ybWFsaXplIGZpbGVzLg0KICAgIGlmIGxlbihhcmd1bWVudHMuZmlsZXMpID4gMCBhbmQgaXNpbnN0YW5jZShhcmd1bWVudHMuZmlsZXNbMF0sIGxpc3QpOg0KICAgICAgICBhcmd1bWVudHMuZmlsZXMgPSBhcmd1bWVudHMuZmlsZXNbMF0NCg0KICAgIHRyeToNCiAgICAgICAgYXJjaGl2ZSA9IFJlblB5QXJjaGl2ZShhcmNoaXZlLCBwYWRsZW5ndGg9cGFkZGluZywga2V5PWtleSwgdmVyc2lvbj12ZXJzaW9uLCB2ZXJib3NlPWFyZ3VtZW50cy52ZXJib3NlKQ0KICAgIGV4Y2VwdCBJT0Vycm9yIGFzIGU6DQogICAgICAgIHByaW50KCdDb3VsZCBub3Qgb3BlbiBhcmNoaXZlIGZpbGUgezB9IGZvciByZWFkaW5nOiB7MX0nLmZvcm1hdChhcmNoaXZlLCBlKSwgZmlsZT1zeXMuc3RkZXJyKQ0KICAgICAgICBzeXMuZXhpdCgxKQ0KDQogICAgaWYgYXJndW1lbnRzLmNyZWF0ZSBvciBhcmd1bWVudHMuYXBwZW5kOg0KICAgICAgICAjIFdlIG5lZWQgdGhpcyBzZXBlcmF0ZSBmdW5jdGlvbiB0byByZWN1cnNpdmVseSBwcm9jZXNzIGRpcmVjdG9yaWVzLg0KICAgICAgICBkZWYgYWRkX2ZpbGUoZmlsZW5hbWUpOg0KICAgICAgICAgICAgIyBJZiB0aGUgYXJjaGl2ZSBwYXRoIGRpZmZlcnMgZnJvbSB0aGUgYWN0dWFsIGZpbGUgcGF0aCwgYXMgZ2l2ZW4gaW4gdGhlIGFyZ3VtZW50LA0KICAgICAgICAgICAgIyBleHRyYWN0IHRoZSBhcmNoaXZlIHBhdGggYW5kIGFjdHVhbCBmaWxlIHBhdGguDQogICAgICAgICAgICBpZiBmaWxlbmFtZS5maW5kKCc9JykgIT0gLTE6DQogICAgICAgICAgICAgICAgKG91dGZpbGUsIGZpbGVuYW1lKSA9IGZpbGVuYW1lLnNwbGl0KCc9JywgMikNCiAgICAgICAgICAgIGVsc2U6DQogICAgICAgICAgICAgICAgb3V0ZmlsZSA9IGZpbGVuYW1lDQoNCiAgICAgICAgICAgIGlmIG9zLnBhdGguaXNkaXIoZmlsZW5hbWUpOg0KICAgICAgICAgICAgICAgIGZvciBmaWxlIGluIG9zLmxpc3RkaXIoZmlsZW5hbWUpOg0KICAgICAgICAgICAgICAgICAgICAjIFdlIG5lZWQgdG8gZG8gdGhpcyBpbiBvcmRlciB0byBtYWludGFpbiBhIHBvc3NpYmxlIEFSQ0hJVkU9UkVBTCBtYXBwaW5nIGJldHdlZW4gZGlyZWN0b3JpZXMuDQogICAgICAgICAgICAgICAgICAgIGFkZF9maWxlKG91dGZpbGUgKyBvcy5zZXAgKyBmaWxlICsgJz0nICsgZmlsZW5hbWUgKyBvcy5zZXAgKyBmaWxlKQ0KICAgICAgICAgICAgZWxzZToNCiAgICAgICAgICAgICAgICB0cnk6DQogICAgICAgICAgICAgICAgICAgIHdpdGggb3BlbihmaWxlbmFtZSwgJ3JiJykgYXMgZmlsZToNCiAgICAgICAgICAgICAgICAgICAgICAgIGFyY2hpdmUuYWRkKG91dGZpbGUsIGZpbGUucmVhZCgpKQ0KICAgICAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToNCiAgICAgICAgICAgICAgICAgICAgcHJpbnQoJ0NvdWxkIG5vdCBhZGQgZmlsZSB7MH0gdG8gYXJjaGl2ZTogezF9Jy5mb3JtYXQoZmlsZW5hbWUsIGUpLCBmaWxlPXN5cy5zdGRlcnIpDQoNCiAgICAgICAgIyBJdGVyYXRlIG92ZXIgdGhlIGdpdmVuIGZpbGVzIHRvIGFkZCB0byBhcmNoaXZlLg0KICAgICAgICBmb3IgZmlsZW5hbWUgaW4gYXJndW1lbnRzLmZpbGVzOg0KICAgICAgICAgICAgYWRkX2ZpbGUoX3VuaWNvZGUoZmlsZW5hbWUpKQ0KDQogICAgICAgICMgU2V0IHZlcnNpb24gZm9yIHNhdmluZywgYW5kIHNhdmUuDQogICAgICAgIGFyY2hpdmUudmVyc2lvbiA9IHZlcnNpb24NCiAgICAgICAgdHJ5Og0KICAgICAgICAgICAgYXJjaGl2ZS5zYXZlKG91dHB1dCkNCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOg0KICAgICAgICAgICAgcHJpbnQoJ0NvdWxkIG5vdCBzYXZlIGFyY2hpdmUgZmlsZTogezB9Jy5mb3JtYXQoZSksIGZpbGU9c3lzLnN0ZGVycikNCiAgICBlbGlmIGFyZ3VtZW50cy5kZWxldGU6DQogICAgICAgICMgSXRlcmF0ZSBvdmVyIHRoZSBnaXZlbiBmaWxlcyB0byBkZWxldGUgZnJvbSB0aGUgYXJjaGl2ZS4NCiAgICAgICAgZm9yIGZpbGVuYW1lIGluIGFyZ3VtZW50cy5maWxlczoNCiAgICAgICAgICAgIHRyeToNCiAgICAgICAgICAgICAgICBhcmNoaXZlLnJlbW92ZShmaWxlbmFtZSkNCiAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToNCiAgICAgICAgICAgICAgICBwcmludCgnQ291bGQgbm90IGRlbGV0ZSBmaWxlIHswfSBmcm9tIGFyY2hpdmU6IHsxfScuZm9ybWF0KGZpbGVuYW1lLCBlKSwgZmlsZT1zeXMuc3RkZXJyKQ0KDQogICAgICAgICMgU2V0IHZlcnNpb24gZm9yIHNhdmluZywgYW5kIHNhdmUuDQogICAgICAgIGFyY2hpdmUudmVyc2lvbiA9IHZlcnNpb24NCiAgICAgICAgdHJ5Og0KICAgICAgICAgICAgYXJjaGl2ZS5zYXZlKG91dHB1dCkNCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOg0KICAgICAgICAgICAgcHJpbnQoJ0NvdWxkIG5vdCBzYXZlIGFyY2hpdmUgZmlsZTogezB9Jy5mb3JtYXQoZSksIGZpbGU9c3lzLnN0ZGVycikNCiAgICBlbGlmIGFyZ3VtZW50cy5leHRyYWN0Og0KICAgICAgICAjIEVpdGhlciBleHRyYWN0IHRoZSBnaXZlbiBmaWxlcywgb3IgYWxsIGZpbGVzIGlmIG5vIGZpbGVzIGFyZSBnaXZlbi4NCiAgICAgICAgaWYgbGVuKGFyZ3VtZW50cy5maWxlcykgPiAwOg0KICAgICAgICAgICAgZmlsZXMgPSBhcmd1bWVudHMuZmlsZXMNCiAgICAgICAgZWxzZToNCiAgICAgICAgICAgIGZpbGVzID0gYXJjaGl2ZS5saXN0KCkNCg0KICAgICAgICAjIENyZWF0ZSBvdXRwdXQgZGlyZWN0b3J5IGlmIG5vdCBwcmVzZW50Lg0KICAgICAgICBpZiBub3Qgb3MucGF0aC5leGlzdHMob3V0cHV0KToNCiAgICAgICAgICAgIG9zLm1ha2VkaXJzKG91dHB1dCkNCg0KICAgICAgICAjIEl0ZXJhdGUgb3ZlciBmaWxlcyB0byBleHRyYWN0Lg0KICAgICAgICBmb3IgZmlsZW5hbWUgaW4gZmlsZXM6DQogICAgICAgICAgICBpZiBmaWxlbmFtZS5maW5kKCc9JykgIT0gLTE6DQogICAgICAgICAgICAgICAgKG91dGZpbGUsIGZpbGVuYW1lKSA9IGZpbGVuYW1lLnNwbGl0KCc9JywgMikNCiAgICAgICAgICAgIGVsc2U6DQogICAgICAgICAgICAgICAgb3V0ZmlsZSA9IGZpbGVuYW1lDQoNCiAgICAgICAgICAgIHRyeToNCiAgICAgICAgICAgICAgICBjb250ZW50cyA9IGFyY2hpdmUucmVhZChmaWxlbmFtZSkNCg0KICAgICAgICAgICAgICAgICMgQ3JlYXRlIG91dHB1dCBkaXJlY3RvcnkgZm9yIGZpbGUgaWYgbm90IHByZXNlbnQuDQogICAgICAgICAgICAgICAgaWYgbm90IG9zLnBhdGguZXhpc3RzKG9zLnBhdGguZGlybmFtZShvcy5wYXRoLmpvaW4ob3V0cHV0LCBvdXRmaWxlKSkpOg0KICAgICAgICAgICAgICAgICAgICBvcy5tYWtlZGlycyhvcy5wYXRoLmRpcm5hbWUob3MucGF0aC5qb2luKG91dHB1dCwgb3V0ZmlsZSkpKQ0KDQogICAgICAgICAgICAgICAgd2l0aCBvcGVuKG9zLnBhdGguam9pbihvdXRwdXQsIG91dGZpbGUpLCAnd2InKSBhcyBmaWxlOg0KICAgICAgICAgICAgICAgICAgICBmaWxlLndyaXRlKGNvbnRlbnRzKQ0KICAgICAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOg0KICAgICAgICAgICAgICAgIHByaW50KCdDb3VsZCBub3QgZXh0cmFjdCBmaWxlIHswfSBmcm9tIGFyY2hpdmU6IHsxfScuZm9ybWF0KGZpbGVuYW1lLCBlKSwgZmlsZT1zeXMuc3RkZXJyKQ0KICAgIGVsaWYgYXJndW1lbnRzLmxpc3Q6DQogICAgICAgICMgUHJpbnQgdGhlIHNvcnRlZCBmaWxlIGxpc3QuDQogICAgICAgIGxpc3QgPSBhcmNoaXZlLmxpc3QoKQ0KICAgICAgICBsaXN0LnNvcnQoKQ0KICAgICAgICBmb3IgZmlsZSBpbiBsaXN0Og0KICAgICAgICAgICAgcHJpbnQoZmlsZSkNCiAgICBlbHNlOg0KICAgICAgICBwcmludCgnTm8gb3BlcmF0aW9uIGdpdmVuIDooJykNCiAgICAgICAgcHJpbnQoJ1VzZSB7MH0gLS1oZWxwIGZvciB1c2FnZSBkZXRhaWxzLicuZm9ybWF0KHN5cy5hcmd2WzBdKSkNCg0K"
    )

    >"%altrpatool%.b64" (
        <nul set /p="IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMw0KDQojIE1hZGUgYnkgKFNNKSBha2EgSm9lTHVybWVsIEAgZjk1em9uZS50bw0KIyBUaGlzIHNjcmlwdCBpcyBsaWNlbnNlZCB1bmRlciBHTlUgR1BMIHYzIOKAlCBzZWUgTElDRU5TRSBmb3IgZGV0YWlscw0KDQpmcm9tIF9fZnV0dXJlX18gaW1wb3J0IHByaW50X2Z1bmN0aW9uDQppbXBvcnQgc3lzDQppbXBvcnQgb3MNCmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aA0KaW1wb3J0IGFyZ3BhcnNlDQppbXBvcnQgaGFzaGxpYg0KaW1wb3J0IHBpY2tsZQ0KaW1wb3J0IHpsaWINCg0Kc3lzLnBhdGguYXBwZW5kKCcuLicpDQp0cnk6DQogICAgaW1wb3J0IG1haW4gICMgbm9xYTogRjQwMQ0KZXhjZXB0Og0KICAgIHBhc3MNCg0KaW1wb3J0IHJlbnB5Lm9iamVjdCAgIyBub3FhOiBGNDAxDQppbXBvcnQgcmVucHkuY29uZmlnDQppbXBvcnQgcmVucHkubG9hZGVyDQp0cnk6DQogICAgaW1wb3J0IHJlbnB5LnV0aWwgICMgbm9xYTogRjQwMQ0KZXhjZXB0Og0KICAgIHBhc3MNCg0KY2xhc3MgSkFTQXJjaGl2ZUhhbmRsZXJMb2NhbDoNCiAgICAiIiINCiAgICBTdGFuZGFsb25lIEpBUyBIYW5kbGVyICh3aXRob3V0IFJlbidQeSkNCiAgICAiIiINCg0KICAgIGRlZiBfX2luaXRfXyhzZWxmLCBmaWxlX3BhdGgpOg0KICAgICAgICBzZWxmLmZpbGUgPSBmaWxlX3BhdGgNCiAgICAgICAgc2VsZi5pbmRleCA9IHt9DQogICAgICAgIHNlbGYuX2xvYWRfaW5kZXgoKQ0KDQogICAgZGVmIF9kZWNvZGVfaGVhZGVyKHNlbGYsIGhlYWRlcik6DQogICAgICAgICMgVGhlIGRldiBhbHdheXMgcmV0dXJucyB0aGlzIHN0cmluZywgc28gd2UgY2FuIHVzZSBpdCB0byBmaW5kIHRoZSBvZmZzZXRzIGFuZCBrZXkNCiAgICAgICAgcmV0dXJuICJkYW5zdG9uY3VsbGFiYWxheWV0dGUiDQoNCiAgICBkZWYgX2xvYWRfaW5kZXgoc2VsZik6DQogICAgICAgIHdpdGggb3BlbihzZWxmLmZpbGUsICJyYiIpIGFzIGY6DQogICAgICAgICAgICBoZWFkZXIgPSBmLnJlYWQoNDApDQoNCiAgICAgICAgICAgICMgMSkgZGVjb2RlKCkg4oaSIHJldHVybnMgYSBmaXhlZCBzdHJpbmcNCiAgICAgICAgICAgIGRlY29kZWQgPSBzZWxmLl9kZWNvZGVfaGVhZGVyKGhlYWRlcikNCg0KICAgICAgICAgICAgIyAyKSBNRDUNCiAgICAgICAgICAgIG1kNWhleCA9IGhhc2hsaWIubWQ1KGRlY29kZWQuZW5jb2RlKCkpLmhleGRpZ2VzdCgpDQogICAgICAgICAgICB4NTAgPSBpbnQobWQ1aGV4WzBdLCAxNikgJSA4DQogICAgICAgICAgICB4NEIgPSBpbnQobWQ1aGV4WzFdLCAxNikgJSA0DQoNCiAgICAgICAgICAgICMgMykgZXh0cmFjdGlvbiBvZiBoZXggZmllbGRzDQogICAgICAgICAgICB4MjIgPSBoZWFkZXJbOCt4NTAgOiAyNCt4NTBdLmRlY29kZSgpLnJlcGxhY2UoIlgiLCAiMCIpDQogICAgICAgICAgICB4MjMgPSBoZWFkZXJbMjUreDRCIDogMzMreDRCXS5kZWNvZGUoKS5yZXBsYWNlKCJYIiwgIjAiKQ0KDQogICAgICAgICAgICB4NEYgPSBpbnQoeDIyLCAxNikgICMgb2Zmc2V0IGluZGV4DQogICAgICAgICAgICB4NkIgPSBpbnQoeDIzLCAxNikgICMgWE9SIGtleQ0KDQogICAgICAgICAgICAjIDQpIHJlYWRpbmcgdGhlIGluZGV4DQogICAgICAgICAgICBmLnNlZWsoeDRGKQ0KICAgICAgICAgICAgcmF3ID0gZi5yZWFkKCkNCiAgICAgICAgICAgIHRyeToNCiAgICAgICAgICAgICAgICBpbmRleCA9IHBpY2tsZS5sb2Fkcyh6bGliLmRlY29tcHJlc3MocmF3KSkNCiAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb246DQogICAgICAgICAgICAgICAgcmFpc2UgUnVudGltZUVycm9yKCJJbXBvc3NpYmxlIGRlIGTDqWNvbXByZXNzZXIgbOKAmWluZGV4IEpBUyIpDQoNCiAgICAgICAgICAgICMgNSkgZGVjb2RpbmcgdGhlIG9mZnNldHMNCiAgICAgICAgICAgIGZpeGVkID0ge30NCiAgICAgICAgICAgIGZvciBuYW1lLCBlbnRyaWVzIGluIGluZGV4Lml0ZW1zKCk6DQogICAgICAgICAgICAgICAgbmV3X2VudHJpZXMgPSBbXQ0KICAgICAgICAgICAgICAgIGZvciBlIGluIGVudHJpZXM6DQogICAgICAgICAgICAgICAgICAgIGlmIGxlbihlKSA9PSAyOg0KICAgICAgICAgICAgICAgICAgICAgICAgb2ZmLCBzaXplID0gZQ0KICAgICAgICAgICAgICAgICAgICAgICAgbmV3X2VudHJpZXMuYXBwZW5kKChvZmYgXiB4NkIsIHNpemUgXiB4NkIpKQ0KICAgICAgICAgICAgICAgICAgICBlbHNlOg0KICAgICAgICAgICAgICAgICAgICAgICAgb2ZmLCBzaXplLCBleHRyYSA9IGUNCiAgICAgICAgICAgICAgICAgICAgICAgIG5ld19lbnRyaWVzLmFwcGVuZCgob2ZmIF4geDZCLCBzaXplIF4geDZCLCBleHRyYSkpDQogICAgICAgICAgICAgICAgZml4ZWRbbmFtZV0gPSBuZXdfZW50cmllcw0KDQogICAgICAgICAgICBzZWxmLmluZGV4ID0gZml4ZWQNCg0KICAgIGRlZiBsaXN0KHNlbGYpOg0KICAgICAgICByZXR1cm4gbGlzdChzZWxmLmluZGV4LmtleXMoKSkNCg0KICAgIGRlZiByZWFkKHNlbGYsIGZpbGVuYW1lKToNCiAgICAgICAgZW50cmllcyA9IHNlbGYuaW5kZXguZ2V0KGZpbGVuYW1lKQ0KICAgICAgICBpZiBub3QgZW50cmllczoNCiAgICAgICAgICAgIHJldHVybiBOb25lDQoNCiAgICAgICAgb2ZmLCBzaXplID0gZW50cmllc1swXVs6Ml0NCiAgICAgICAgd2l0aCBvcGVuKHNlbGYuZmlsZSwgInJiIikgYXMgZjoNCiAgICAgICAgICAgIGYuc2VlayhvZmYpDQogICAgICAgICAgICByZXR1cm4gZi5yZWFkKHNpemUpDQoNCg0KY2xhc3MgUmVuUHlBcmNoaXZlOg0KICAgIGRlZiBfX2luaXRfXyhzZWxmLCBmaWxlX3BhdGgsIGluZGV4PTApOg0KICAgICAgICBzZWxmLmZpbGUgPSBzdHIoZmlsZV9wYXRoKQ0KICAgICAgICBzZWxmLmluZGV4ZXMgPSB7fQ0KICAgICAgICBzZWxmLmxvYWQoc2VsZi5maWxlLCBpbmRleCkNCg0KICAgIGRlZiBjb252ZXJ0X2ZpbGVuYW1lKHNlbGYsIGZpbGVuYW1lKToNCiAgICAgICAgZHJpdmUsIGZpbGVuYW1lID0gb3MucGF0aC5zcGxpdGRyaXZlKA0KICAgICAgICAgICAgb3MucGF0aC5ub3JtcGF0aChmaWxlbmFtZSkucmVwbGFjZShvcy5zZXAsICcvJykNCiAgICAgICAgKQ0KICAgICAgICByZXR1cm4gZmlsZW5hbWUNCg0KICAgIGRlZiBsaXN0KHNlbGYpOg0KICAgICAgICByZXR1cm4gbGlzdChzZWxmLmluZGV4ZXMpDQoNCiAgICBkZWYgcmVhZChzZWxmLCBmaWxlbmFtZSk6DQogICAgICAgIGZpbGVuYW1lID0gc2VsZi5jb252ZXJ0X2ZpbGVuYW1lKGZpbGVuYW1lKQ0KICAgICAgICBpZHggPSBzZWxmLmluZGV4ZXMuZ2V0KGZpbGVuYW1lKQ0KICAgICAgICBpZiBmaWxlbmFtZSAhPSAnLicgYW5kIGlzaW5zdGFuY2UoaWR4LCBsaXN0KToNCiAgICAgICAgICAgIGlmIGhhc2F0dHIocmVucHkubG9hZGVyLCAibG9hZF9mcm9tX2FyY2hpdmUiKToNCiAgICAgICAgICAgICAgICBzdWJmaWxlID0gcmVucHkubG9hZGVyLmxvYWRfZnJvbV9hcmNoaXZlKGZpbGVuYW1lKQ0KICAgICAgICAgICAgZWxzZToNCiAgICAgICAgICAgICAgICBzdWJmaWxlID0gcmVucHkubG9hZGVyLmxvYWRfY29yZShmaWxlbmFtZSkNCiAgICAgICAgICAgIHJldHVybiBzdWJmaWxlLnJlYWQoKQ0KICAgICAgICByZXR1cm4gTm9uZQ0KDQogICAgZGVmIGxvYWQoc2VsZiwgZmlsZW5hbWUsIGluZGV4KToNCiAgICAgICAgYmFzZSA9IG9zLnBhdGguc3BsaXRleHQob3MucGF0aC5iYXNlbmFtZShmaWxlbmFtZSkpWzBdDQoNCiAgICAgICAgaWYgYmFzZSBub3QgaW4gcmVucHkuY29uZmlnLmFyY2hpdmVzOg0KICAgICAgICAgICAgcmVucHkuY29uZmlnLmFyY2hpdmVzLmFwcGVuZChiYXNlKQ0KDQogICAgICAgIGFyY2hpdmVfZGlyID0gb3MucGF0aC5kaXJuYW1lKG9zLnBhdGgucmVhbHBhdGgoZmlsZW5hbWUpKQ0KICAgICAgICByZW5weS5jb25maWcuc2VhcmNocGF0aCA9IFthcmNoaXZlX2Rpcl0NCiAgICAgICAgcmVucHkuY29uZmlnLmJhc2VkaXIgPSBvcy5wYXRoLmRpcm5hbWUocmVucHkuY29uZmlnLnNlYXJjaHBhdGhbMF0pDQogICAgICAgIHJlbnB5LmxvYWRlci5pbmRleF9hcmNoaXZlcygpDQoNCiAgICAgICAgYXJjaGl2ZXNfb2JqID0gcmVucHkubG9hZGVyLmFyY2hpdmVzDQoNCiAgICAgICAgaWYgaXNpbnN0YW5jZShhcmNoaXZlc19vYmosIGRpY3QpOg0KICAgICAgICAgICAgaXRlbXMgPSBhcmNoaXZlc19vYmpbYmFzZV1bMV0uaXRlbXMoKQ0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgaXRlbXMgPSBhcmNoaXZlc19vYmpbaW5kZXhdWzFdLml0ZW1zKCkNCg0KICAgICAgICBmb3IgZiwgaWR4IGluIGl0ZW1zOg0KICAgICAgICAgICAgc2VsZi5pbmRleGVzW2ZdID0gaWR4DQoNCg0KZGVmIGxpc3RfYXJjaGl2ZShhcmNoX3BhdGgsIGFyY2hpdmVfY2xhc3MpOg0KICAgIHByaW50KGYnQ29udGVudSBkZSAie2FyY2hfcGF0aH0iOicpDQogICAgYXJjaGl2ZSA9IGFyY2hpdmVfY2xhc3MoYXJjaF9wYXRoKQ0KICAgIGZvciBmaWxlbmFtZSBpbiBhcmNoaXZlLmxpc3QoKToNCiAgICAgICAgcHJpbnQoIiAgIiwgZmlsZW5hbWUpDQoNCg0KZGVmIGRpc2NvdmVyX2V4dGVuc2lvbnMoKToNCiAgICBleHRzID0gW10NCiAgICBpZiBoYXNhdHRyKHJlbnB5LmxvYWRlciwgImFyY2hpdmVfaGFuZGxlcnMiKToNCiAgICAgICAgZm9yIGhhbmRsZXIgaW4gcmVucHkubG9hZGVyLmFyY2hpdmVfaGFuZGxlcnM6DQogICAgICAgICAgICBpZiBoYXNhdHRyKGhhbmRsZXIsICJnZXRfc3VwcG9ydGVkX2V4dGVuc2lvbnMiKToNCiAgICAgICAgICAgICAgICBleHRzLmV4dGVuZChoYW5kbGVyLmdldF9zdXBwb3J0ZWRfZXh0ZW5zaW9ucygpKQ0KICAgICAgICAgICAgaWYgaGFzYXR0cihoYW5kbGVyLCAiZ2V0X3N1cHBvcnRlZF9leHQiKToNCiAgICAgICAgICAgICAgICBleHRzLmV4dGVuZChoYW5kbGVyLmdldF9zdXBwb3J0ZWRfZXh0KCkpDQogICAgZWxzZToNCiAgICAgICAgZXh0cy5hcHBlbmQoJy5ycGEnKQ0KDQogICAgIyBBam91dCBtYW51ZWwgc2kgbGUgaGFuZGxlciBuJ2VzdCBwYXMgZMOpdGVjdMOpDQogICAgaWYgJy5qYXMnIG5vdCBpbiBleHRzOg0KICAgICAgICBleHRzLmFwcGVuZCgnLmphcycpDQoNCiAgICBpZiAnLnJwYycgbm90IGluIGV4dHM6DQogICAgICAgIGV4dHMuYXBwZW5kKCcucnBjJykNCg0KICAgIHJldHVybiBzb3J0ZWQoc2V0KGUubG93ZXIoKSBmb3IgZSBpbiBleHRzKSkNCg0KDQpkZWYgZGlzY292ZXJfYXJjaGl2ZXMoc2VhcmNoX2RpciwgZXh0ZW5zaW9ucyk6DQogICAgYXJjaGl2ZXMgPSBbXQ0KICAgIGZvciByb290LCBkaXJzLCBmaWxlcyBpbiBvcy53YWxrKHN0cihzZWFyY2hfZGlyKSk6DQogICAgICAgIGZvciBmaWxlIGluIGZpbGVzOg0KICAgICAgICAgICAgdHJ5Og0KICAgICAgICAgICAgICAgIGJhc2UsIGV4dCA9IGZpbGUucnNwbGl0KCcuJywgMSkNCiAgICAgICAgICAgICAgICBleHQgPSAnLicgKyBleHQubG93ZXIoKQ0KICAgICAgICAgICAgICAgIGlmIGV4dCBpbiBleHRlbnNpb25zIGFuZCAnJScgbm90IGluIGZpbGU6DQogICAgICAgICAgICAgICAgICAgIGFyY2hpdmVzLmFwcGVuZChQYXRoKHJvb3QpIC8gZmlsZSkNCiAgICAgICAgICAgIGV4Y2VwdCBWYWx1ZUVycm9yOg0KICAgICAgICAgICAgICAgIGNvbnRpbnVlDQogICAgcmV0dXJuIGFyY2hpdmVzDQoNCg0KZGVmIGV4dHJhY3RfYXJjaGl2ZShhcmNoX3BhdGgsIG91dHB1dCwgYXJjaGl2ZV9jbGFzcyk6DQogICAgcHJpbnQoZicgIFVucGFja2luZyAie2FyY2hfcGF0aH0iJykNCiAgICBhcmNoaXZlID0gYXJjaGl2ZV9jbGFzcyhhcmNoX3BhdGgpDQogICAgZmlsZXMgPSBhcmNoaXZlLmxpc3QoKQ0KDQogICAgb3V0cHV0Lm1rZGlyKHBhcmVudHM9VHJ1ZSwgZXhpc3Rfb2s9VHJ1ZSkNCg0KICAgIGZvciBmaWxlbmFtZSBpbiBmaWxlczoNCiAgICAgICAgY29udGVudHMgPSBhcmNoaXZlLnJlYWQoZmlsZW5hbWUpDQogICAgICAgIGlmIGNvbnRlbnRzIGlzIG5vdCBOb25lOg0KICAgICAgICAgICAgb3V0ZmlsZSA9IG91dHB1dCAvIGZpbGVuYW1lDQogICAgICAgICAgICBvdXRmaWxlLnBhcmVudC5ta2RpcihwYXJlbnRzPVRydWUsIGV4aXN0X29rPVRydWUpDQogICAgICAgICAgICB3aXRoIG9wZW4ob3V0ZmlsZSwgJ3diJykgYXMgZjoNCiAgICAgICAgICAgICAgICBmLndyaXRlKGNvbnRlbnRzKQ0KDQoNCmRlZiBtYWluKCk6DQogICA"
        <nul set /p="gcGFyc2VyID0gYXJncGFyc2UuQXJndW1lbnRQYXJzZXIoKQ0KICAgIHBhcnNlci5hZGRfYXJndW1lbnQoJy1sJywgJy0tbGlzdCcsIGFjdGlvbj0ic3RvcmVfdHJ1ZSIsIGRlc3Q9J2xpc3Rfb25seScsDQogICAgICAgICAgICAgICAgICAgICAgICBoZWxwPSJMaXN0IHRoZSBjb250ZW50cyBvZiB0aGUgYXJjaGl2ZSB3aXRob3V0IGV4dHJhY3RpbmcgdGhlbSIpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLXInLCBhY3Rpb249InN0b3JlX3RydWUiLCBkZXN0PSdyZW1vdmUnKQ0KICAgIHBhcnNlci5hZGRfYXJndW1lbnQoJy14JywgZGVzdD0nYXJjaGl2ZScsIHR5cGU9c3RyKQ0KICAgIHBhcnNlci5hZGRfYXJndW1lbnQoJy1vJywgZGVzdD0nb3V0cHV0JywgdHlwZT1zdHIsIGRlZmF1bHQ9Jy4nKQ0KICAgIGFyZ3MgPSBwYXJzZXIucGFyc2VfYXJncygpDQoNCiAgICBvdXRwdXQgPSBQYXRoKGFyZ3Mub3V0cHV0KS5yZXNvbHZlKCkNCiAgICBhcmNoaXZlX2ZpbHRlciA9IGFyZ3MuYXJjaGl2ZQ0KICAgIHJlbW92ZSA9IGFyZ3MucmVtb3ZlDQoNCiAgICBleHRlbnNpb25zID0gZGlzY292ZXJfZXh0ZW5zaW9ucygpDQoNCiAgICAjIE1vZGUgLXgNCiAgICBpZiBhcmNoaXZlX2ZpbHRlcjoNCiAgICAgICAgdGFyZ2V0ID0gUGF0aChhcmNoaXZlX2ZpbHRlcikucmVzb2x2ZSgpDQogICAgICAgIGlmIG5vdCB0YXJnZXQuZXhpc3RzKCk6DQogICAgICAgICAgICBiYXNlbmFtZSA9IG9zLnBhdGguYmFzZW5hbWUoYXJjaGl2ZV9maWx0ZXIpDQogICAgICAgICAgICBmb3VuZCA9IE5vbmUNCiAgICAgICAgICAgIGZvciByb290LCBkaXJzLCBmaWxlcyBpbiBvcy53YWxrKCcuJyk6DQogICAgICAgICAgICAgICAgaWYgYmFzZW5hbWUgaW4gZmlsZXM6DQogICAgICAgICAgICAgICAgICAgIGZvdW5kID0gUGF0aChyb290KSAvIGJhc2VuYW1lDQogICAgICAgICAgICAgICAgICAgIGJyZWFrDQogICAgICAgICAgICBpZiBmb3VuZCBpcyBOb25lOg0KICAgICAgICAgICAgICAgIHByaW50KGYnQXJjaGl2ZSAie2FyY2hpdmVfZmlsdGVyfSIgbm90IGZvdW5kLicpDQogICAgICAgICAgICAgICAgc3lzLmV4aXQoMSkNCiAgICAgICAgICAgIHRhcmdldCA9IGZvdW5kLnJlc29sdmUoKQ0KDQogICAgICAgICMgQ2hvaXggZHUgaGFuZGxlcg0KICAgICAgICBpZiB0YXJnZXQuc3VmZml4Lmxvd2VyKCkgPT0gIi5qYXMiOg0KICAgICAgICAgICAgaGFuZGxlciA9IEpBU0FyY2hpdmVIYW5kbGVyTG9jYWwNCiAgICAgICAgZWxzZToNCiAgICAgICAgICAgIGhhbmRsZXIgPSBSZW5QeUFyY2hpdmUNCg0KICAgICAgICBpZiBhcmdzLmxpc3Rfb25seToNCiAgICAgICAgICAgIGxpc3RfYXJjaGl2ZSh0YXJnZXQsIGhhbmRsZXIpDQogICAgICAgICAgICByZXR1cm4NCg0KICAgICAgICBleHRyYWN0X2FyY2hpdmUodGFyZ2V0LCBvdXRwdXQsIGhhbmRsZXIpDQoNCiAgICAgICAgaWYgcmVtb3ZlOg0KICAgICAgICAgICAgb3MucmVtb3ZlKHN0cih0YXJnZXQpKQ0KICAgICAgICByZXR1cm4NCg0KICAgICMgRMOpZmF1bHQgbW9kZQ0KICAgIGFyY2hpdmVzID0gZGlzY292ZXJfYXJjaGl2ZXMoUGF0aCgnLicpLCBleHRlbnNpb25zKQ0KDQogICAgaWYgbm90IGFyY2hpdmVzOg0KICAgICAgICBwcmludCgiTm8gYXJjaGl2ZXMgZm91bmQuIikNCiAgICAgICAgcmV0dXJuDQoNCiAgICBmb3IgYXJjaCBpbiBhcmNoaXZlczoNCiAgICAgICAgaWYgYXJjaC5zdWZmaXgubG93ZXIoKSA9PSAiLmphcyI6DQogICAgICAgICAgICBoYW5kbGVyID0gSkFTQXJjaGl2ZUhhbmRsZXJMb2NhbA0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgaGFuZGxlciA9IFJlblB5QXJjaGl2ZQ0KDQogICAgICAgIGlmIGFyZ3MubGlzdF9vbmx5Og0KICAgICAgICAgICAgbGlzdF9hcmNoaXZlKGFyY2gsIGhhbmRsZXIpDQogICAgICAgIGVsc2U6DQogICAgICAgICAgICBleHRyYWN0X2FyY2hpdmUoYXJjaCwgb3V0cHV0LCBoYW5kbGVyKQ0KDQogICAgaWYgcmVtb3ZlOg0KICAgICAgICBmb3IgYXJjaCBpbiBhcmNoaXZlczoNCiAgICAgICAgICAgIG9zLnJlbW92ZShzdHIoYXJjaCkpDQoNCg0KaWYgX19uYW1lX18gPT0gIl9fbWFpbl9fIjoNCiAgICBtYWluKCkNCg=="
    )
)

call :pwsh_exp "!extm9.%LNG%!..." "%rpatool%"
if not exist "%rpatool%" (
    call :elog "%NOK%" "!FCREATE.%LNG%! %YEL%%rpatool%%RES%"
    goto :rpa_cleanup
) else (
    call :elog "%OK%"
)

>"%altrpatool%.b64" (
    <nul set /p="IyEvdXNyL2Jpbi9lbnYgcHl0aG9uDQoNCiMgTWFkZSBieSAoU00pIGFrYSBKb2VMdXJtZWwgQCBmOTV6b25lLnRvDQojIFRoaXMgc2NyaXB0IGlzIGxpY2Vuc2VkIHVuZGVyIEdOVSBHUEwgdjMg4oCUIHNlZSBMSUNFTlNFIGZvciBkZXRhaWxzDQoNCmZyb20gX19mdXR1cmVfXyBpbXBvcnQgcHJpbnRfZnVuY3Rpb24NCmltcG9ydCBzeXMNCmltcG9ydCBvcw0KZnJvbSBwYXRobGliIGltcG9ydCBQYXRoDQppbXBvcnQgYXJncGFyc2UNCmltcG9ydCBoYXNobGliDQppbXBvcnQgcGlja2xlDQppbXBvcnQgemxpYg0KDQpzeXMucGF0aC5hcHBlbmQoJy4uJykNCnRyeToNCiAgICBpbXBvcnQgbWFpbiAgIyBub3FhOiBGNDAxDQpleGNlcHQ6DQogICAgcGFzcw0KDQppbXBvcnQgcmVucHkub2JqZWN0ICAjIG5vcWE6IEY0MDENCmltcG9ydCByZW5weS5jb25maWcNCmltcG9ydCByZW5weS5sb2FkZXINCnRyeToNCiAgICBpbXBvcnQgcmVucHkudXRpbCAgIyBub3FhOiBGNDAxDQpleGNlcHQ6DQogICAgcGFzcw0KDQpjbGFzcyBKQVNBcmNoaXZlSGFuZGxlckxvY2FsOg0KICAgICIiIg0KICAgIFN0YW5kYWxvbmUgSkFTIEhhbmRsZXIgKHdpdGhvdXQgUmVuJ1B5KQ0KICAgICIiIg0KDQogICAgZGVmIF9faW5pdF9fKHNlbGYsIGZpbGVfcGF0aCk6DQogICAgICAgIHNlbGYuZmlsZSA9IGZpbGVfcGF0aA0KICAgICAgICBzZWxmLmluZGV4ID0ge30NCiAgICAgICAgc2VsZi5fbG9hZF9pbmRleCgpDQoNCiAgICBkZWYgX2RlY29kZV9oZWFkZXIoc2VsZiwgaGVhZGVyKToNCiAgICAgICAgIyBUaGUgZGV2IGFsd2F5cyByZXR1cm5zIHRoaXMgc3RyaW5nLCBzbyB3ZSBjYW4gdXNlIGl0IHRvIGZpbmQgdGhlIG9mZnNldHMgYW5kIGtleQ0KICAgICAgICByZXR1cm4gImRhbnN0b25jdWxsYWJhbGF5ZXR0ZSINCg0KICAgIGRlZiBfbG9hZF9pbmRleChzZWxmKToNCiAgICAgICAgd2l0aCBvcGVuKHNlbGYuZmlsZSwgInJiIikgYXMgZjoNCiAgICAgICAgICAgIGhlYWRlciA9IGYucmVhZCg0MCkNCg0KICAgICAgICAgICAgIyAxKSBkZWNvZGUoKSDihpIgcmV0dXJucyBhIGZpeGVkIHN0cmluZw0KICAgICAgICAgICAgZGVjb2RlZCA9IHNlbGYuX2RlY29kZV9oZWFkZXIoaGVhZGVyKQ0KDQogICAgICAgICAgICAjIDIpIE1ENQ0KICAgICAgICAgICAgbWQ1aGV4ID0gaGFzaGxpYi5tZDUoZGVjb2RlZC5lbmNvZGUoKSkuaGV4ZGlnZXN0KCkNCiAgICAgICAgICAgIHg1MCA9IGludChtZDVoZXhbMF0sIDE2KSAlIDgNCiAgICAgICAgICAgIHg0QiA9IGludChtZDVoZXhbMV0sIDE2KSAlIDQNCg0KICAgICAgICAgICAgIyAzKSBleHRyYWN0aW9uIG9mIGhleCBmaWVsZHMNCiAgICAgICAgICAgIHgyMiA9IGhlYWRlcls4K3g1MCA6IDI0K3g1MF0uZGVjb2RlKCkucmVwbGFjZSgiWCIsICIwIikNCiAgICAgICAgICAgIHgyMyA9IGhlYWRlclsyNSt4NEIgOiAzMyt4NEJdLmRlY29kZSgpLnJlcGxhY2UoIlgiLCAiMCIpDQoNCiAgICAgICAgICAgIHg0RiA9IGludCh4MjIsIDE2KSAgIyBvZmZzZXQgaW5kZXgNCiAgICAgICAgICAgIHg2QiA9IGludCh4MjMsIDE2KSAgIyBYT1Iga2V5DQoNCiAgICAgICAgICAgICMgNCkgcmVhZGluZyB0aGUgaW5kZXgNCiAgICAgICAgICAgIGYuc2Vlayh4NEYpDQogICAgICAgICAgICByYXcgPSBmLnJlYWQoKQ0KICAgICAgICAgICAgdHJ5Og0KICAgICAgICAgICAgICAgIGluZGV4ID0gcGlja2xlLmxvYWRzKHpsaWIuZGVjb21wcmVzcyhyYXcpKQ0KICAgICAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoNCiAgICAgICAgICAgICAgICByYWlzZSBSdW50aW1lRXJyb3IoIkltcG9zc2libGUgZGUgZMOpY29tcHJlc3NlciBs4oCZaW5kZXggSkFTIikNCg0KICAgICAgICAgICAgIyA1KSBkZWNvZGluZyB0aGUgb2Zmc2V0cw0KICAgICAgICAgICAgZml4ZWQgPSB7fQ0KICAgICAgICAgICAgZm9yIG5hbWUsIGVudHJpZXMgaW4gaW5kZXguaXRlbXMoKToNCiAgICAgICAgICAgICAgICBuZXdfZW50cmllcyA9IFtdDQogICAgICAgICAgICAgICAgZm9yIGUgaW4gZW50cmllczoNCiAgICAgICAgICAgICAgICAgICAgaWYgbGVuKGUpID09IDI6DQogICAgICAgICAgICAgICAgICAgICAgICBvZmYsIHNpemUgPSBlDQogICAgICAgICAgICAgICAgICAgICAgICBuZXdfZW50cmllcy5hcHBlbmQoKG9mZiBeIHg2Qiwgc2l6ZSBeIHg2QikpDQogICAgICAgICAgICAgICAgICAgIGVsc2U6DQogICAgICAgICAgICAgICAgICAgICAgICBvZmYsIHNpemUsIGV4dHJhID0gZQ0KICAgICAgICAgICAgICAgICAgICAgICAgbmV3X2VudHJpZXMuYXBwZW5kKChvZmYgXiB4NkIsIHNpemUgXiB4NkIsIGV4dHJhKSkNCiAgICAgICAgICAgICAgICBmaXhlZFtuYW1lXSA9IG5ld19lbnRyaWVzDQoNCiAgICAgICAgICAgIHNlbGYuaW5kZXggPSBmaXhlZA0KDQogICAgZGVmIGxpc3Qoc2VsZik6DQogICAgICAgIHJldHVybiBsaXN0KHNlbGYuaW5kZXgua2V5cygpKQ0KDQogICAgZGVmIHJlYWQoc2VsZiwgZmlsZW5hbWUpOg0KICAgICAgICBlbnRyaWVzID0gc2VsZi5pbmRleC5nZXQoZmlsZW5hbWUpDQogICAgICAgIGlmIG5vdCBlbnRyaWVzOg0KICAgICAgICAgICAgcmV0dXJuIE5vbmUNCg0KICAgICAgICBvZmYsIHNpemUgPSBlbnRyaWVzWzBdWzoyXQ0KICAgICAgICB3aXRoIG9wZW4oc2VsZi5maWxlLCAicmIiKSBhcyBmOg0KICAgICAgICAgICAgZi5zZWVrKG9mZikNCiAgICAgICAgICAgIHJldHVybiBmLnJlYWQoc2l6ZSkNCg0KDQpjbGFzcyBSZW5QeUFyY2hpdmU6DQogICAgZGVmIF9faW5pdF9fKHNlbGYsIGZpbGVfcGF0aCwgaW5kZXg9MCk6DQogICAgICAgIHNlbGYuZmlsZSA9IHN0cihmaWxlX3BhdGgpDQogICAgICAgIHNlbGYuaW5kZXhlcyA9IHt9DQogICAgICAgIHNlbGYubG9hZChzZWxmLmZpbGUsIGluZGV4KQ0KDQogICAgZGVmIGNvbnZlcnRfZmlsZW5hbWUoc2VsZiwgZmlsZW5hbWUpOg0KICAgICAgICBkcml2ZSwgZmlsZW5hbWUgPSBvcy5wYXRoLnNwbGl0ZHJpdmUoDQogICAgICAgICAgICBvcy5wYXRoLm5vcm1wYXRoKGZpbGVuYW1lKS5yZXBsYWNlKG9zLnNlcCwgJy8nKQ0KICAgICAgICApDQogICAgICAgIHJldHVybiBmaWxlbmFtZQ0KDQogICAgZGVmIGxpc3Qoc2VsZik6DQogICAgICAgIHJldHVybiBsaXN0KHNlbGYuaW5kZXhlcykNCg0KICAgIGRlZiByZWFkKHNlbGYsIGZpbGVuYW1lKToNCiAgICAgICAgZmlsZW5hbWUgPSBzZWxmLmNvbnZlcnRfZmlsZW5hbWUoZmlsZW5hbWUpDQogICAgICAgIGlkeCA9IHNlbGYuaW5kZXhlcy5nZXQoZmlsZW5hbWUpDQogICAgICAgIGlmIGZpbGVuYW1lICE9ICcuJyBhbmQgaXNpbnN0YW5jZShpZHgsIGxpc3QpOg0KICAgICAgICAgICAgaWYgaGFzYXR0cihyZW5weS5sb2FkZXIsICJsb2FkX2Zyb21fYXJjaGl2ZSIpOg0KICAgICAgICAgICAgICAgIHN1YmZpbGUgPSByZW5weS5sb2FkZXIubG9hZF9mcm9tX2FyY2hpdmUoZmlsZW5hbWUpDQogICAgICAgICAgICBlbHNlOg0KICAgICAgICAgICAgICAgIHN1YmZpbGUgPSByZW5weS5sb2FkZXIubG9hZF9jb3JlKGZpbGVuYW1lKQ0KICAgICAgICAgICAgcmV0dXJuIHN1YmZpbGUucmVhZCgpDQogICAgICAgIHJldHVybiBOb25lDQoNCiAgICBkZWYgbG9hZChzZWxmLCBmaWxlbmFtZSwgaW5kZXgpOg0KICAgICAgICBiYXNlID0gb3MucGF0aC5zcGxpdGV4dChvcy5wYXRoLmJhc2VuYW1lKGZpbGVuYW1lKSlbMF0NCg0KICAgICAgICBpZiBiYXNlIG5vdCBpbiByZW5weS5jb25maWcuYXJjaGl2ZXM6DQogICAgICAgICAgICByZW5weS5jb25maWcuYXJjaGl2ZXMuYXBwZW5kKGJhc2UpDQoNCiAgICAgICAgYXJjaGl2ZV9kaXIgPSBvcy5wYXRoLmRpcm5hbWUob3MucGF0aC5yZWFscGF0aChmaWxlbmFtZSkpDQogICAgICAgIHJlbnB5LmNvbmZpZy5zZWFyY2hwYXRoID0gW2FyY2hpdmVfZGlyXQ0KICAgICAgICByZW5weS5jb25maWcuYmFzZWRpciA9IG9zLnBhdGguZGlybmFtZShyZW5weS5jb25maWcuc2VhcmNocGF0aFswXSkNCiAgICAgICAgcmVucHkubG9hZGVyLmluZGV4X2FyY2hpdmVzKCkNCg0KICAgICAgICBhcmNoaXZlc19vYmogPSByZW5weS5sb2FkZXIuYXJjaGl2ZXMNCg0KICAgICAgICAjIEF1dG8tZGV0ZWN0aW9uDQogICAgICAgIGlmIGlzaW5zdGFuY2UoYXJjaGl2ZXNfb2JqLCBkaWN0KTogICMgUmVuJ1B5IDgNCiAgICAgICAgICAgIGl0ZW1zID0gYXJjaGl2ZXNfb2JqW2Jhc2VdWzFdLml0ZW1zKCkNCiAgICAgICAgZWxzZTogICMgUmVuJ1B5IDcNCiAgICAgICAgICAgIGl0ZW1zID0gYXJjaGl2ZXNfb2JqW2luZGV4XVsxXS5pdGVtcygpDQoNCiAgICAgICAgZm9yIGYsIGlkeCBpbiBpdGVtczoNCiAgICAgICAgICAgIHNlbGYuaW5kZXhlc1tmXSA9IGlkeA0KDQoNCmRlZiBsaXN0X2FyY2hpdmUoYXJjaF9wYXRoLCBhcmNoaXZlX2NsYXNzKToNCiAgICBwcmludChmJ0NvbnRlbnUgZGUgInthcmNoX3BhdGh9IjonKQ0KICAgIGFyY2hpdmUgPSBhcmNoaXZlX2NsYXNzKGFyY2hfcGF0aCkNCiAgICBmb3IgZmlsZW5hbWUgaW4gYXJjaGl2ZS5saXN0KCk6DQogICAgICAgIHByaW50KCIgICIsIGZpbGVuYW1lKQ0KDQoNCmRlZiBkaXNjb3Zlcl9leHRlbnNpb25zKCk6DQogICAgZXh0cyA9IFtdDQogICAgaWYgaGFzYXR0cihyZW5weS5sb2FkZXIsICJhcmNoaXZlX2hhbmRsZXJzIik6DQogICAgICAgIGZvciBoYW5kbGVyIGluIHJlbnB5LmxvYWRlci5hcmNoaXZlX2hhbmRsZXJzOg0KICAgICAgICAgICAgaWYgaGFzYXR0cihoYW5kbGVyLCAiZ2V0X3N1cHBvcnRlZF9leHRlbnNpb25zIik6DQogICAgICAgICAgICAgICAgZXh0cy5leHRlbmQoaGFuZGxlci5nZXRfc3VwcG9ydGVkX2V4dGVuc2lvbnMoKSkNCiAgICAgICAgICAgIGlmIGhhc2F0dHIoaGFuZGxlciwgImdldF9zdXBwb3J0ZWRfZXh0Iik6DQogICAgICAgICAgICAgICAgZXh0cy5leHRlbmQoaGFuZGxlci5nZXRfc3VwcG9ydGVkX2V4dCgpKQ0KICAgIGVsc2U6DQogICAgICAgIGV4dHMuYXBwZW5kKCcucnBhJykNCg0KICAgICMgQWRkIG1hbnVhbGx5IGlmIHRoZSBoYW5kbGVyIGlzIG5vdCBkZXRlY3RlZA0KICAgIGlmICcuamFzJyBub3QgaW4gZXh0czoNCiAgICAgICAgZXh0cy5hcHBlbmQoJy5qYXMnKQ0KDQogICAgaWYgJy5ycGMnIG5vdCBpbiBleHRzOg0KICAgICAgICBleHRzLmFwcGVuZCgnLnJwYycpDQoNCiAgICByZXR1cm4gc29ydGVkKHNldChlLmxvd2VyKCkgZm9yIGUgaW4gZXh0cykpDQoNCg0KZGVmIGRpc2NvdmVyX2FyY2hpdmVzKHNlYXJjaF9kaXIsIGV4dGVuc2lvbnMpOg0KICAgIGFyY2hpdmVzID0gW10NCiAgICBmb3Igcm9vdCwgZGlycywgZmlsZXMgaW4gb3Mud2FsayhzdHIoc2VhcmNoX2RpcikpOg0KICAgICAgICBmb3IgZmlsZSBpbiBmaWxlczoNCiAgICAgICAgICAgIHRyeToNCiAgICAgICAgICAgICAgICBiYXNlLCBleHQgPSBmaWxlLnJzcGxpdCgnLicsIDEpDQogICAgICAgICAgICAgICAgZXh0ID0gJy4nICsgZXh0Lmxvd2VyKCkNCiAgICAgICAgICAgICAgICBpZiBleHQgaW4gZXh0ZW5zaW9ucyBhbmQgJyUnIG5vdCBpbiBmaWxlOg0KICAgICAgICAgICAgICAgICAgICBhcmNoaXZlcy5hcHBlbmQoUGF0aChyb290KSAvIGZpbGUpDQogICAgICAgICAgICBleGNlcHQgVmFsdWVFcnJvcjoNCiAgICAgICAgICAgICAgICBjb250aW51ZQ0KICAgIHJldHVybiBhcmNoaXZlcw0KDQoNCmRlZiBleHRyYWN0X2FyY2hpdmUoYXJjaF9wYXRoLCBvdXRwdXQpOg0KICAgIHByaW50KGYnICBVbnBhY2tpbmcgInthcmNoX3BhdGh9IiAuLi4nKQ0KICAgIGFyY2hpdmUgPSBSZW5QeUFyY2hpdmUoYXJjaF9wYXRoLCAwKQ0KICAgIGZpbGVzID0gYXJjaGl2ZS5saXN0KCkNCg0KICAgIG91dHB1dC5ta2RpcihwYXJlbnRzPVRydWUsIGV4aXN0X29rPVRydWUpDQoNCiAgICBmb3IgZmlsZW5hbWUgaW4gZmlsZXM6DQogICAgICAgIGNvbnRlbnRzID0gYXJjaGl2ZS5yZWFkKGZpbGVuYW1lKQ0KICAgICAgICBpZiBjb250ZW50cyBpcyBub3QgTm9uZToNCiAgICAgICAgICAgIG91dGZpbGUgPSBvdXRwdXQgLyBmaWxlbmFtZQ0KICAgICAgICAgICAgb3V0ZmlsZS5wYXJlbnQubWtkaXIocGFyZW50cz1UcnVlLCBleGlzdF9vaz1UcnVlKQ0KICAgICAgICAgICAgd2l0aCBvcGVuKG91dGZpbGUsICd3YicpIGFzIGY6DQogICAgICAgI"
    <nul set /p="CAgICAgICAgZi53cml0ZShjb250ZW50cykNCg0KDQpkZWYgbWFpbigpOg0KICAgIHBhcnNlciA9IGFyZ3BhcnNlLkFyZ3VtZW50UGFyc2VyKA0KICAgICAgICBkZXNjcmlwdGlvbj0iVG9vbCBmb3Igd29ya2luZyB3aXRoIFJlbidQeSBhcmNoaXZlIGZpbGVzLiIsDQogICAgICAgIGFkZF9oZWxwPVRydWUNCiAgICApDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLWwnLCAnLS1saXN0JywgYWN0aW9uPSJzdG9yZV90cnVlIiwgZGVzdD0nbGlzdF9vbmx5JywNCiAgICAgICAgICAgICAgICAgICAgICAgIGhlbHA9Ikxpc3QgdGhlIGNvbnRlbnRzIG9mIHRoZSBhcmNoaXZlIHdpdGhvdXQgZXh0cmFjdGluZyB0aGVtIikNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctcicsIGFjdGlvbj0ic3RvcmVfdHJ1ZSIsIGRlc3Q9J3JlbW92ZScsDQogICAgICAgICAgICAgICAgICAgICAgICBoZWxwPSdSZW1vdmUgYXJjaGl2ZXMgYWZ0ZXIgZXh0cmFjdGlvbi4nKQ0KICAgIHBhcnNlci5hZGRfYXJndW1lbnQoJy14JywgZGVzdD0nYXJjaGl2ZScsIHR5cGU9c3RyLA0KICAgICAgICAgICAgICAgICAgICAgICAgaGVscD0nU3BlY2lmaWMgYXJjaGl2ZSBmaWxlIHRvIGV4dHJhY3QgKGZ1bGwgcGF0aCkuJykNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctbycsIGRlc3Q9J291dHB1dCcsIHR5cGU9c3RyLCBkZWZhdWx0PScuJywNCiAgICAgICAgICAgICAgICAgICAgICAgIGhlbHA9J091dHB1dCBkaXJlY3RvcnkgZm9yIGV4dHJhY3RlZCBmaWxlcy4nKQ0KICAgIGFyZ3MgPSBwYXJzZXIucGFyc2VfYXJncygpDQoNCiAgICBvdXRwdXQgPSBQYXRoKGFyZ3Mub3V0cHV0KS5yZXNvbHZlKCkNCiAgICBhcmNoaXZlX2ZpbHRlciA9IGFyZ3MuYXJjaGl2ZQ0KICAgIHJlbW92ZSA9IGFyZ3MucmVtb3ZlDQoNCiAgICBleHRlbnNpb25zID0gZGlzY292ZXJfZXh0ZW5zaW9ucygpDQoNCiAgICAjIC14IG1vZGU6IGV4dHJhY3Qgb25seSB0aGUgc3BlY2lmaWVkIGFyY2hpdmUgKGV4YWN0IHBhdGgpDQogICAgaWYgYXJjaGl2ZV9maWx0ZXI6DQogICAgICAgIHRhcmdldCA9IFBhdGgoYXJjaGl2ZV9maWx0ZXIpLnJlc29sdmUoKQ0KDQogICAgICAgIGlmIG5vdCB0YXJnZXQuZXhpc3RzKCk6DQogICAgICAgICAgICBiYXNlbmFtZSA9IG9zLnBhdGguYmFzZW5hbWUoYXJjaGl2ZV9maWx0ZXIpDQogICAgICAgICAgICBmb3VuZCA9IE5vbmUNCiAgICAgICAgICAgIGZvciByb290LCBkaXJzLCBmaWxlcyBpbiBvcy53YWxrKCcuJyk6DQogICAgICAgICAgICAgICAgaWYgYmFzZW5hbWUgaW4gZmlsZXM6DQogICAgICAgICAgICAgICAgICAgIGZvdW5kID0gUGF0aChyb290KSAvIGJhc2VuYW1lDQogICAgICAgICAgICAgICAgICAgIGJyZWFrDQogICAgICAgICAgICBpZiBmb3VuZCBpcyBOb25lOg0KICAgICAgICAgICAgICAgIHByaW50KGYnQXJjaGl2ZSAie2FyY2hpdmVfZmlsdGVyfSIgbm90IGZvdW5kLicpDQogICAgICAgICAgICAgICAgc3lzLmV4aXQoMSkNCiAgICAgICAgICAgIHRhcmdldCA9IGZvdW5kLnJlc29sdmUoKQ0KDQogICAgICAgICMgQ2hvb3NpbmcgYSBoYW5kbGVyDQogICAgICAgIGlmIHRhcmdldC5zdWZmaXgubG93ZXIoKSA9PSAiLmphcyI6DQogICAgICAgICAgICBoYW5kbGVyID0gSkFTQXJjaGl2ZUhhbmRsZXJMb2NhbA0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgaGFuZGxlciA9IFJlblB5QXJjaGl2ZQ0KDQogICAgICAgIGlmIGFyZ3MubGlzdF9vbmx5Og0KICAgICAgICAgICAgbGlzdF9hcmNoaXZlKHRhcmdldCwgaGFuZGxlcikNCiAgICAgICAgICAgIHJldHVybg0KDQogICAgICAgIGV4dHJhY3RfYXJjaGl2ZSh0YXJnZXQsIG91dHB1dCwgaGFuZGxlcikNCg0KICAgICAgICBpZiByZW1vdmU6DQogICAgICAgICAgICBvcy5yZW1vdmUoc3RyKHRhcmdldCkpDQogICAgICAgIHJldHVybg0KDQogICAgIyBEZWZhdWx0IG1vZGUNCiAgICBhcmNoaXZlcyA9IGRpc2NvdmVyX2FyY2hpdmVzKFBhdGgoJy4nKSwgZXh0ZW5zaW9ucykNCg0KICAgIGlmIG5vdCBhcmNoaXZlczoNCiAgICAgICAgcHJpbnQoIk5vIGFyY2hpdmVzIGZvdW5kLiIpDQogICAgICAgIHJldHVybg0KDQogICAgZm9yIGFyY2ggaW4gYXJjaGl2ZXM6DQogICAgICAgIGlmIGFyY2guc3VmZml4Lmxvd2VyKCkgPT0gIi5qYXMiOg0KICAgICAgICAgICAgaGFuZGxlciA9IEpBU0FyY2hpdmVIYW5kbGVyTG9jYWwNCiAgICAgICAgZWxzZToNCiAgICAgICAgICAgIGhhbmRsZXIgPSBSZW5QeUFyY2hpdmUNCg0KICAgICAgICBpZiBhcmdzLmxpc3Rfb25seToNCiAgICAgICAgICAgIGxpc3RfYXJjaGl2ZShhcmNoLCBoYW5kbGVyKQ0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgZXh0cmFjdF9hcmNoaXZlKGFyY2gsIG91dHB1dCwgaGFuZGxlcikNCg0KICAgIGlmIHJlbW92ZToNCiAgICAgICAgZm9yIGFyY2ggaW4gYXJjaGl2ZXM6DQogICAgICAgICAgICBvcy5yZW1vdmUoc3RyKGFyY2gpKQ0KDQoNCmlmIF9fbmFtZV9fID09ICJfX21haW5fXyI6DQogICAgbWFpbigpDQo="
)
call :pwsh_exp "!extm9a.%LNG%!..." "%altrpatool%"
if not exist "%altrpatool%" (
    call :elog "%NOK%" "!FCREATE.%LNG%! %YEL%%altrpatool%%RES%"
    goto :rpa_cleanup
) else (
    call :elog "%OK%"
)

call :elog .
:: Unpack RPA
setlocal disabledelayedexpansion
for /f "delims=" %%A in ("%WORKDIR%") do (
    endlocal
    cd /d "%%A"
)
set "prevDir="
for /R "game" %%f in (*.%rpaExt%) do (
    set "rpafile=%%~dpnf.%rpaExt%"
    set "rpasize=%%~zf"
    set "relativePath=%%f"
    set "currDir=%%~dpf"
    set "relativePath=!relativePath:%WORKDIR%\game\=!"
    set "usealt=0"

    set "extm18.zh=RPA 文件 %YEL%!relativePath!%RES% 被忽略。"

    set "extm19.zh=处理 RPA 文件時发生错误：%YEL%!relativePath!%RES%。"

    set "extm20.zh=RPA 文件已解包: %YEL%!relativePath!%RES%"

    set "extm21.zh=正在删除 RPA 文件: %YEL%!relativePath!%RES%"

    set "extm22.zh=正在将 RPA 文件 %RES%%YEL%!relativePath!%RES% 重命名为 %YEL%!relativePath!.org%RES%。"

    set "extm24.zh=检测到修改过的 %YEL%!relativePath!%RES% RPA 存档，使用 altrpatool.py 进行提取。"

    if not "!prevDir!" == "!currDir!" (
        call :elog .
        call :elog "!MTITLE.%LNG%! %YEL%!currDir!%RES%"
        set "prevDir=!currDir!"
    )

    if !OPTION! EQU 7 (
        set "usealt=1"
        call :elog .
        call :elog "!extm24.%LNG%!"
    )
    if exist "!rpafile!" if not "!relativePath!" == "saves\persistent" (
        if %DEBUGLEVEL% GEQ 1 echo "%PYTHONEXE%" %PYVERSION% %PYTHONSYSTEM% "!detect_archive!" "!rpafile!" >> "%UNRENLOG%"
        "%PYTHONEXE%" %PYVERSION% %PYTHONSYSTEM% "!detect_archive!" "!rpafile!" %DEBUGREDIR%
        if !errorlevel! EQU 1 if !OPTION! NEQ 7 (
            set "usealt=1"
            call :elog .
            call :elog "!extm24.%LNG%!"
        )
        if "!extract_all_rpa!" == "n" (
            call :elog .
            set "qmark=?"
            if %DEBUGLEVEL% GEQ 1 echo !extm16.%LNG%! !relativePath! - !rpasize! !UNIT.%LNG%!!qmark! >> "%UNRENLOG%"
            call :choiceEx "!extm16.%LNG%! !relativePath! - !rpasize! !UNIT.%LNG%!!qmark! !ENTERYN.%LNG%! " "OSJYN" "N" "%CTIME%" "-rawMsg"
            if errorlevel 5 (
                call :elog "%SKIP%" "!extm18.%LNG%!%RES%"
            ) else (
                if !usealt! EQU 0 (
                    if %DEBUGLEVEL% GEQ 1 echo "%PYTHONEXE%" %PYVERSION% %PYTHONSYSTEM% "!rpatool!" -o game -x "!rpafile!" >> "%UNRENLOG%"
                    "%PYTHONEXE%" %PYVERSION% %PYTHONSYSTEM% "!rpatool!" -o game -x "!rpafile!" %DEBUGREDIR%
                    set "elevel=!errorlevel!"
                ) else if !usealt! EQU 1 (
                    if %DEBUGLEVEL% GEQ 1 echo "%PYTHONEXE%" %PYVERSION% %PYTHONSYSTEM% "!altrpatool!" -o .\game -x "!rpafile!" >> "%UNRENLOG%"
                    "%PYTHONEXE%" %PYVERSION% %PYTHONSYSTEM% "!altrpatool!" -o .\game -x "!rpafile!" %DEBUGREDIR%
                    set "elevel=!errorlevel!"
                )
                if !elevel! NEQ 0 (
                    call :elog "%NOK%" "!extm19.%LNG%! %YEL%!LOGCHK.%LNG%!%RES%"
                ) else (
                    call :elog "%OK%" "!extm20.%LNG%!%RES%"
                    if "!delrpa!" == "y" (
                        call :elog -n"%EMPTY%" "!extm21.%LNG%!%RES%"
                        if %DEBUGLEVEL% GEQ 1 echo del /f /q "!rpafile!" >> "%UNRENLOG%"
                        del /f /q "!rpafile!" %DEBUGREDIR%
                        call :elog "%OK%"
                    ) else (
                        if not exist "!rpafile!.org" (
                            call :elog -n "%EMPTY%" "!extm22.%LNG%!%RES%"
                            if %DEBUGLEVEL% GEQ 1 echo move /y "!rpafile!" "!rpafile!.org" >> "%UNRENLOG%"
                            move /y "!rpafile!" "!rpafile!.org" %DEBUGREDIR%
                            if !errorlevel! NEQ 0 (
                                call :elog "%NOK%" "%YEL%!LOGCHK.%LNG%!%RES%"
                            ) else (
                                call :elog "%OK%"
                            )
                        )
                    )
                )
            )
        ) else (
            call :elog .
            call :elog -n "%EMPTY%" "!extm16.%LNG%! %YEL%!relativePath!%RES% - %YEL%!rpasize!%RES% !UNIT.%LNG%!"
            set "elevel=0"
            if !usealt! EQU 0 (
                if %DEBUGLEVEL% GEQ 1 echo "%PYTHONEXE%" %PYVERSION% %PYTHONSYSTEM% "!rpatool!" -o game -x "!rpafile!" >> "%UNRENLOG%"
                "%PYTHONEXE%" %PYVERSION% %PYTHONSYSTEM% "!rpatool!" -o game -x "!rpafile!" %DEBUGREDIR%
                set "elevel=!errorlevel!"
            ) else if !usealt! EQU 1 (
                if %DEBUGLEVEL% GEQ 1 echo "%PYTHONEXE%" %PYVERSION% %PYTHONSYSTEM% "!altrpatool!" -o .\game -x "!rpafile!" >> "%UNRENLOG%"
                "%PYTHONEXE%" %PYVERSION% %PYTHONSYSTEM% "!altrpatool!" -o .\game -x "!rpafile!" %DEBUGREDIR%
                set "elevel=!errorlevel!"
            )
            if !elevel! NEQ 0 (
                call :elog "%NOK%" "%YEL%!LOGCHK.%LNG%!%RES%"
            ) else (
                call :elog "%OK%"
                if "!delrpa!" == "y" (
                    call :elog -n "%EMPTY%" "!extm21.%LNG%!%RES%"
                    if %DEBUGLEVEL% GEQ 1 echo del /f /q "!rpafile!" >> "%UNRENLOG%"
                    del /f /q "!rpafile!" %DEBUGREDIR%
                    call :elog "%OK%"
                ) else (
                    if not exist "!rpafile!.org" (
                        call :elog -n "%EMPTY%" "!extm22.%LNG%!%RES%"
                        if %DEBUGLEVEL% GEQ 1 echo move /y "!rpafile!" "!rpafile!.org" >> "%UNRENLOG%"
                        move /y "!rpafile!" "!rpafile!.org" %DEBUGREDIR%
                        if !errorlevel! NEQ 0 (
                            call :elog "%NOK%" "%YEL%!LOGCHK.%LNG%!%RES%"
                        ) else (
                            call :elog "%OK%"
                        )
                    )
                )
            )
        )
    )
)

:: Clean up
:rpa_cleanup
call :elog .
call :elog -n "%EMPTY%" "!CLEANUP.%LNG%!..."

set "error="
if not "%rpatool%" == "" if exist "%rpatool%" (
    if %DEBUGLEVEL% GEQ 1 echo del /f /q "%rpatool%" >> "%UNRENLOG%"
    del /f /q "%rpatool%" %DEBUGREDIR%
    set /a error=!errorlevel!
)
if not "%altrpatool%" == "" if exist "%altrpatool%" (
    if %DEBUGLEVEL% GEQ 1 echo del /f /q "%altrpatool%" >> "%UNRENLOG%"
    del /f /q "%altrpatool%" %DEBUGREDIR%
    set /a error=!error!+!errorlevel!
)
if exist "%WORKDIR%\__pycache__" if exist "%WORKDIR%\__pycache__" (
    if %DEBUGLEVEL% GEQ 1 echo rmdir /q /s "%WORKDIR%\__pycache__" >> "%UNRENLOG%"
    rmdir /q /s "%WORKDIR%\__pycache__" %DEBUGREDIR%
    set /a error=!error!+!errorlevel!
)
if not "%detect_archive%" == "" if exist "%detect_archive%" (
    if %DEBUGLEVEL% GEQ 1 echo del /f /q "%detect_archive%" >> "%UNRENLOG%"
    del /f /q "%detect_archive%" %DEBUGREDIR%
    set /a error=!error!+!errorlevel!
)
if not "%detect_rpa_ext%" == "" if exist "%detect_rpa_ext%" (
    if %DEBUGLEVEL% GEQ 1 echo del /f /q "%detect_rpa_ext%" >> "%UNRENLOG%"
    del /f /q "%detect_rpa_ext%" %DEBUGREDIR%
    set /a error=!error!+!errorlevel!
)

if !error! NEQ 0 (
    call :elog "%NOK%" "!LOGCHK.%LNG%!"
) else (
    call :elog "%OK%"
)
timeout /T 1 %DEBUGREDIR%

if "%OPTION%" == "5" call :decompile
if "%OPTION%" == "6" call :decompile
goto :eof


:: Use unrpa instead of rpatool which offer the ability to extract RPA archives with a different header.
:extract_wkey
call :elog .
goto :unavailable
goto :eof

:: Decrypt all RPYC files with the WOS SHIELD
:wos_decrypt_all
set "wosmsg0.zh=创建 WOS 解密脚本"

set "wosmsg1.zh=运行 wos_decrypt_all.py 以使用 WOS SHIELD 解密 RPYC 文件。"

set "wos_decrypt_all=%WORKDIR%\wos_decrypt_all.py"
>"%wos_decrypt_all%.b64" (
    <nul set /p="IyEvdXNyL2Jpbi9lbnYgcHl0aG9uDQojIC0qLSBjb2Rpbmc6IHV0Zi04IC0qLQ0KDQojIHdvc19kZWNyeXB0X2FsbC5weQ0KDQppbXBvcnQgb3MNCmltcG9ydCBoYXNobGliDQpmcm9tIHBhdGhsaWIgaW1wb3J0IFBhdGgNCmltcG9ydCBzdHJ1Y3QNCmltcG9ydCBzeXMNCmltcG9ydCB0cmFjZWJhY2sNCg0Kc3lzLnBhdGguYXBwZW5kKHN0cihQYXRoKF9fZmlsZV9fKS5wYXJlbnQgLyAicmVucHkiKSkNCmZyb20gcmVucHkud29zX3JweWNfbG9hZGVyIGltcG9ydCBNQUdJQ19SUFlDLCBTRUNSRVRfS0VZDQoNCiNNQUdJQ19SUFlDID0gYiJXT1NceDAwXHgwMlx4MDAiDQojU0VDUkVUX0tFWSA9IGIiUldBX1dvU19lc2o2N1h3RzRIYW91TGc4TnJLXzZvSmpDZnlnNVNmRDBvSld3TzlHcnV0dzFzYWsiDQoNCmRlZiBfd29zX2Rlcml2ZV9rZXlfc3RyZWFtKGtleV9tYXRlcmlhbCwgbGVuZ3RoKToNCiAgICBzdHJlYW0gPSBieXRlYXJyYXkoKQ0KICAgIGNvdW50ZXIgPSAwDQogICAgd2hpbGUgbGVuKHN0cmVhbSkgPCBsZW5ndGg6DQogICAgICAgIGggPSBoYXNobGliLnNoYTI1NihrZXlfbWF0ZXJpYWwgKyBzdHJ1Y3QucGFjaygiPEkiLCBjb3VudGVyKSkuZGlnZXN0KCkNCiAgICAgICAgc3RyZWFtLmV4dGVuZChoKQ0KICAgICAgICBjb3VudGVyICs9IDENCiAgICByZXR1cm4gYnl0ZXMoc3RyZWFtWzpsZW5ndGhdKQ0KDQpkZWYgX3dvc194b3JfY3J5cHQoZGF0YSwga2V5X21hdGVyaWFsKToNCiAgICBrZXlfc3RyZWFtID0gX3dvc19kZXJpdmVfa2V5X3N0cmVhbShrZXlfbWF0ZXJpYWwsIGxlbihkYXRhKSkNCiAgICByZXR1cm4gYnl0ZXMoYSBeIGIgZm9yIGEsIGIgaW4gemlwKGRhdGEsIGtleV9zdHJlYW0pKQ0KDQpkZWYgd29zX2RlY3J5cHRfcnB5YyhmaWxlcGF0aCk6DQogICAgd2l0aCBvcGVuKGZpbGVwYXRoLCAicmIiKSBhcyBmOg0KICAgICAgICBtYWdpYyA9IGYucmVhZChsZW4oTUFHSUNfUlBZQykpDQogICAgICAgIGlmIG1hZ2ljICE9IE1BR0lDX1JQWUM6DQogICAgICAgICAgICByZXR1cm4gTm9uZQ0KDQogICAgICAgIG5vbmNlX2xlbiA9IHN0cnVjdC51bnBhY2soIjxIIiwgZi5yZWFkKDIpKVswXQ0KICAgICAgICBub25jZSA9IGYucmVhZChub25jZV9sZW4pDQoNCiAgICAgICAgb3JpZ2luYWxfbGVuID0gc3RydWN0LnVucGFjaygiPEkiLCBmLnJlYWQoNCkpWzBdDQogICAgICAgIGNoZWNrc3VtID0gZi5yZWFkKDMyKQ0KDQogICAgICAgIGVuY3J5cHRlZF9kYXRhID0gZi5yZWFkKCkNCg0KICAgIHJweWNfa2V5ID0gaGFzaGxpYi5zaGEyNTYoU0VDUkVUX0tFWSArIGIiX3JweWMiKS5kaWdlc3QoKQ0KDQogICAgY2FuZGlkYXRlcyA9IFtdDQoNCiAgICAjIEhlcmUsIHdlIGFyZSBFWEFDVExZIHJlcGxpY2F0aW5nIHRoZSBnYW1lJ3MgYmVoYXZpb3I6DQogICAgIyByZW5weS5jb25maWcuZ2FtZWRpciA9PSDigJxnYW1l4oCdIGZvbGRlcg0KICAgIGdhbWVfZGlyID0gUGF0aCgiZ2FtZSIpLnJlc29sdmUoKQ0KDQogICAgdHJ5Og0KICAgICAgICByZWwgPSBvcy5wYXRoLnJlbHBhdGgoUGF0aChmaWxlcGF0aCkucmVzb2x2ZSgpLCBnYW1lX2RpcikucmVwbGFjZSgiXFwiLCAiLyIpDQogICAgICAgIGNhbmRpZGF0ZXMuYXBwZW5kKHJlbCkNCiAgICBleGNlcHQgRXhjZXB0aW9uOg0KICAgICAgICBwYXNzDQoNCiAgICAjIEZpbGUgbmFtZSBvbmx5IChhcyBpbiB0aGUgbG9hZGVyKQ0KICAgIGNhbmRpZGF0ZXMuYXBwZW5kKG9zLnBhdGguYmFzZW5hbWUoZmlsZXBhdGgpKQ0KDQogICAgc2VlbiA9IHNldCgpDQogICAgZm9yIGMgaW4gY2FuZGlkYXRlczoNCiAgICAgICAgaWYgYyBpbiBzZWVuOg0KICAgICAgICAgICAgY29udGludWUNCiAgICAgICAgc2Vlbi5hZGQoYykNCg0KICAgICAgICBmaWxlX2tleSA9IGhhc2hsaWIuc2hhMjU2KHJweWNfa2V5ICsgYy5lbmNvZGUoKSkuZGlnZXN0KCkNCiAgICAgICAgY29tYmluZWRfa2V5ID0gZmlsZV9rZXkgKyBub25jZQ0KICAgICAgICBkZWNyeXB0ZWQgPSBfd29zX3hvcl9jcnlwdChlbmNyeXB0ZWRfZGF0YSwgY29tYmluZWRfa2V5KQ0KICAgICAgICBkZWNyeXB0ZWQgPSBkZWNyeXB0ZWRbOm9yaWdpbmFsX2xlbl0NCg0KICAgICAgICBpZiBoYXNobGliLnNoYTI1NihkZWNyeXB0ZWQpLmRpZ2VzdCgpID09IGNoZWNrc3VtOg0KICAgICAgICAgICAgcmV0dXJuIGRlY3J5cHRlZA0KDQogICAgcmV0dXJuIE5vbmUNCg0KDQpJTlBVVF9ESVIgPSBQYXRoKCJnYW1lIikNCg0KIyBUdXJucyBzaW11bGF0aW9uIG1vZGUgb24gb3Igb2ZmDQpEUllfUlVOID0gRmFsc2UNCg0KDQojIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQ0KIyBBTlNJIGNvbG91ciBoZWxwZXJzDQojIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQ0KIyBXaW5kb3dzIDEwKyBzdXBwb3J0cyBWVCBzZXF1ZW5jZXM7IG9sZGVyIFdpbmRvd3MgbmVlZHMgd29ya2Fyb3VuZA0KZGVmIF9lbmFibGVfdnRfd2luZG93cygpOg0KICAgIHRyeToNCiAgICAgICAgaW1wb3J0IGN0eXBlcw0KICAgICAgICBrZXJuZWwgPSBjdHlwZXMud2luZGxsLmtlcm5lbDMyDQogICAgICAgIGhhbmRsZSA9IGtlcm5lbC5HZXRTdGRIYW5kbGUoLTExKSAgIyBTVERfT1VUUFVUX0hBTkRMRQ0KICAgICAgICBtb2RlICAgPSBjdHlwZXMuY191bG9uZygwKQ0KICAgICAgICBrZXJuZWwuR2V0Q29uc29sZU1vZGUoaGFuZGxlLCBjdHlwZXMuYnlyZWYobW9kZSkpDQogICAgICAgIGtlcm5lbC5TZXRDb25zb2xlTW9kZShoYW5kbGUsIG1vZGUudmFsdWUgfCAweDAwMDQpDQogICAgZXhjZXB0IEV4Y2VwdGlvbjoNCiAgICAgICAgcGFzcw0KDQpfZW5hYmxlX3Z0X3dpbmRvd3MoKQ0KDQojIE9wdGlvbmFsIGNvbG9ycyAoZGlzYWJsZSBpZiBuZWVkZWQpDQpVU0VfQ09MT1JTID0gVHJ1ZQ0KQ1lBID0gIlwwMzNbOTZtIiBpZiBVU0VfQ09MT1JTIGVsc2UgIiINCkdSRSA9ICJcMDMzWzkybSIgaWYgVVNFX0NPTE9SUyBlbHNlICIiDQpSRUQgPSAiXDAzM1s5MW0iIGlmIFVTRV9DT0xPUlMgZWxzZSAiIg0KWUVMID0gIlwwMzNbOTNtIiBpZiBVU0VfQ09MT1JTIGVsc2UgIiINClJFUyA9ICJcMDMzWzBtIiBpZiBVU0VfQ09MT1JTIGVsc2UgIiINCg0KDQpkZWYgc2FmZV9yZW5hbWUoc3JjOiBQYXRoLCBkc3Q6IFBhdGgpOg0KICAgICIiIlNlY3VyZSByZW5hbWluZyB3aXRoIGRyeS1ydW4gc3VwcG9ydC4iIiINCiAgICBpZiBEUllfUlVOOg0KICAgICAgICBkaXNwbGF5X3N0YXQoZiJSZW5hbWUge3NyY30g4oaSIHtkc3R9IiwgZiJ7WUVMfURSWS1SVU4iKQ0KICAgIGVsc2U6DQogICAgICAgIHNyYy5yZW5hbWUoZHN0KQ0KDQoNCmRlZiBzYWZlX3dyaXRlKHBhdGg6IFBhdGgsIGRhdGE6IGJ5dGVzKToNCiAgICAiIiJTZWN1cmUgd3JpdGluZyB3aXRoIGRyeS1ydW4gc3VwcG9ydC4iIiINCiAgICBpZiBEUllfUlVOOg0KICAgICAgICBkaXNwbGF5X3N0YXQoZiJXcml0ZSB7cGF0aH0iLCBmIntZRUx9RFJZLVJVTiIpDQogICAgZWxzZToNCiAgICAgICAgd2l0aCBvcGVuKHBhdGgsICJ3YiIpIGFzIGY6DQogICAgICAgICAgICBmLndyaXRlKGRhdGEpDQoNCg0KZGVmIGRpc3BsYXlfc3RhdChtZXNzYWdlLCBzdGF0PU5vbmUpOg0KICAgICIiIiBEaXNwbGF5IGEgc3RhdHVzIG1lc3NhZ2Ugd2l0aCBvcHRpb25hbCBzdGF0IHZhbHVlLCBvdmVyd3JpdGluZyB0aGUgcHJldmlvdXMgbGluZS4iIiINCiAgICBpZiBzdGF0IGlzIE5vbmU6DQogICAgICAgIHN5cy5zdGRvdXQud3JpdGUoZiJcclsgICAgICBdIHttZXNzYWdlfSIpDQogICAgZWxzZToNCiAgICAgICAgc3lzLnN0ZG91dC53cml0ZShmIlxyWyB7c3RhdH17UkVTfSBdIHttZXNzYWdlfVxuIikNCiAgICBzeXMuc3Rkb3V0LmZsdXNoKCkNCg0KDQoNCmRlZiBwcm9jZXNzX2ZpbGUocGF0aDogUGF0aCwgc3RhdHMpOg0KICAgIHJlbF9uYW1lID0gc3RyKHBhdGgucmVsYXRpdmVfdG8oSU5QVVRfRElSKSkNCiAgICBkaXNwbGF5X3N0YXQoZiJ7cmVsX25hbWV9IikNCiAgICBzdGF0c1sicnB5YyJdICs9IDENCg0KICAgICMgTUFHSUMgVmVyaWZpY2F0aW9uDQogICAgdHJ5Og0KICAgICAgICB3aXRoIG9wZW4ocGF0aCwgInJiIikgYXMgZjoNCiAgICAgICAgICAgIG1hZ2ljID0gZi5yZWFkKGxlbihNQUdJQ19SUFlDKSkNCiAgICAgICAgaWYgbWFnaWMgIT0gTUFHSUNfUlBZQzoNCiAgICAgICAgICAgIGRpc3BsYXlfc3RhdChmIntyZWxfbmFtZX0iLCBmIntDWUF9U0tJUCIpDQogICAgICAgICAgICBzdGF0c1sic2tpcCJdICs9IDENCiAgICAgICAgICAgIHJldHVybg0KICAgIGV4Y2VwdCBFeGNlcHRpb246DQogICAgICAgIGRpc3BsYXlfc3RhdChmIntyZWxfbmFtZX0iLCBmIntSRUR9Tk9LICIpDQogICAgICAgIHN0YXRzWyJub2siXSArPSAxDQogICAgICAgIHJldHVybg0KDQogICAgdHJ5Og0KICAgICAgICBkYXRhID0gd29zX2RlY3J5cHRfcnB5YyhzdHIocGF0aCkpDQoNCiAgICAgICAgaWYgbm90IGRhdGE6DQogICAgICAgICAgICBkaXNwbGF5X3N0YXQoZiJ7cmVsX25hbWV9IiwgZiJ7UkVEfU5PSyAiKQ0KICAgICAgICAgICAgc3RhdHNbIm5vayJdICs9IDENCiAgICAgICAgICAgIHJldHVybg0KDQogICAgICAgICMgVGVtcG9yYXJ5IGZpbGUgLmRlYyBpbiBJTlBVVF9ESVINCiAgICAgICAgZGVjX3BhdGggPSBwYXRoLndpdGhfc3VmZml4KHBhdGguc3VmZml4ICsgIi5kZWMiKQ0KICAgICAgICBzYWZlX3dyaXRlKGRlY19wYXRoLCBkYXRhKQ0KDQogICAgICAgICMgUmVuYW1lIG9yaWdpbmFsIGZpbGUg4oaSIC5vcmcNCiAgICAgICAgb3JnX3BhdGggPSBwYXRoLndpdGhfc3VmZml4KHBhdGguc3VmZml4ICsgIi5vcmciKQ0KICAgICAgICBpZiBub3Qgb3JnX3BhdGguZXhpc3RzKCk6DQogICAgICAgICAgICBzYWZlX3JlbmFtZShwYXRoLCBvcmdfcGF0aCkNCg0KICAgICAgICAjIFJlbmFtZSB0aGUgLmRlYyDihpIgZmluYWwgZmlsZSAob3JpZ2luYWwgbmFtZSkNCiAgICAgICAgZmluYWxfcGF0aCA9IHBhdGgNCiAgICAgICAgaWYgZmluYWxfcGF0aC5leGlzdHMoKToNCiAgICAgICAgICAgIGlmIG5vdCBEUllfUlVOOg0KICAgICAgICAgICAgICAgIGZpbmFsX3BhdGgudW5saW5rKCkNCiAgICAgICAgc2FmZV9yZW5hbWUoZGVjX3BhdGgsIGZpbmFsX3BhdGgpDQoNCiAgICAgICAgZGlzcGxheV9zdGF0KGYie3JlbF9uYW1lfSIsIGYie0dSRX0gT0sgIikNCiAgICAgICAgc3RhdHNbIm9rIl0gKz0gMQ0KDQogICAgZXhjZXB0IEV4Y2VwdGlvbjoNCiAgICAgICAgZGlzcGxheV9zdGF0KGYie3JlbF9uYW1lfSIsIGYie1JFRH1OT0sgIikNCiAgICAgICAgc3RhdHNbIm5vayJdICs9IDENCiAgICAgICAgdHJhY2ViYWNrLnByaW50X2V4YygpDQoNCg0KZGVmIG1haW4oKToNCiAgICBzdGF0cyA9IHsicnB5YyI6IDAsICJvayI6IDAsICJub2siOiAwLCAic2tpcCI6IDB9DQoNCiAgICBwcmV2aW91c19kaXIgPSBOb25lDQogICAgZm9yIHBhdGggaW4gSU5QVVRfRElSLnJnbG9iKCIqLnJweWMiKToNCiAgICAgICAgY3VycmVudF9kaXIgPSBwYXRoLnBhcmVudA0KICAgICAgICBpZiBjdXJyZW50X2RpciAhPSBwcmV2aW91c19kaXI6DQogICAgICAgICAgICBwcmludChmIlxuLT4gLlxce2N1cnJlbnRfZGlyfToiKQ0KICAgICAgICAgICAgcHJldmlvdXNfZGlyID0gcGF0aC5wYXJlbnQNCiAgICAgICAgaWYgcGF0aC5pc19maWxlKCk6DQogICAgICAgICAgICBwcm9jZXNzX2ZpbGUocGF0aCwgc3RhdHMpDQoNCiAgICBwcmludCgNCiAgICAgICAgZiJcblxuUlBZQyA9ICd7c3RhdHNbJ3JweWMnXX0nLCBPSyA9IHtHUkV9J3tzdGF0c1snb2snXX0ne1JFU30sIE5PSyA9IHtSRUR9J3tzdGF0c1snbm9rJ119J3tSRVN9LCBTS0lQID0ge0NZQX0ne3N0YXRzWydza2lwJ119J3tSRVN9XG4iDQogICAgKQ0KDQoNCmlmIF9fbmFtZV9fID09ICJfX21haW5fXyI6DQogICAgbWFpbigpDQo="
)

call :pwsh_exp "!wosmsg0.%LNG%!" "%wos_decrypt_all%"
if not exist "%wos_decrypt_all%" (
    call :elog "%NOK%"
    call :elog .
    call :elog "    !FCREATE.%LNG%! %YEL%%wos_decrypt_all%%RES%. !UNACONT.%LNG%!"
    call :elog .
    pause>nul|set /p=".      !ANYKEY.%LNG%!..."

    call :exitn 3
) else (
    call :elog "%OK%"
)

call :elog -n "%EMPTY%" "!wosmsg1.%LNG%!"
if %DEBUGLEVEL% GEQ 1 echo "%PYTHONHOME%python.exe" %PYNOASSERT% "%wos_decrypt_all%" >> "%UNRENLOG%"
"%PYTHONHOME%python.exe" %PYNOASSERT% "%wos_decrypt_all%" 2>> "%UNRENLOG%"
if %errorlevel% NEQ 0 (
    call :elog "%NOK%" "!LOGCHK.%LNG%!"
) else (
    call :elog "%OK%"
)

if %DEBUGLEVEL% GEQ 1 echo del /f /q "%wos_decrypt_all%" >> "%UNRENLOG%"
del /f /q "%wos_decrypt_all%" %DEBUGREDIR%
goto :eof

:decompile
:: 组合模式 6 与反混淆模式 4 使用相同的 try-harder 参数。
if "%OPTION%" == "6" set "OPTION=4"

set "decm1.zh=正在创建反编译工具"

set "decm2.zh=正在检查 RPYC 版本"

set "decm2a.zh=当你使用 Ren'Py 版本时"

set "decm2b.zh=，继续进行警告"

set "decm3.zh=反编译后是否覆盖 RPY 文件？"

set "decm4.zh=现有的 RPY 文件不会被覆盖。"

set "decm5.zh=反编译后将覆盖现有的 RPY 文件。"

set "decm6.zh=正在提取 decomp.cab"

set "decm7.zh=找不到："

set "decm8.zh=在游戏目录中搜索 RPYC 文件"

set "decm9.zh=正在反编译文件："

set "decm10.zh=从复制"

set "decm10a.zh=到"

set "decm11.zh=正在覆盖现有的 RPY 文件："

set "decm12.zh=检测到 WOS 盾牌，正在解密后 进行反编译。"

setlocal disabledelayedexpansion
for /f "delims=" %%A in ("%WORKDIR%") do (
    endlocal
    cd /d "%%A"
)

:: Write to temporary file first, then convert. Needed due to binary file and avoid antivirus false positive.
set "decompcab=%WORKDIR%\decomp.cab"
set "decompilerdir=%WORKDIR%\decompiler"
set "unrpycpy=%WORKDIR%\unrpyc.py"
set "deobfuscate=%WORKDIR%\deobfuscate.py"

:: Check if game use WOS shield, if so use wos_decrypt_all before decompilation.
if exist ".\renpy\wos_rpyc_loader.py" (
    call :elog .
    call :elog "%YEL%!decm12.%LNG%!%RES%"
    call :wos_decrypt_all
)

:: Check if rpyc files are compiled with Ren'Py 7 or 8, and set the appropriate unrpyc.py version.
set "detect_rpyc_version=%TEMP%\detect_rpyc_version.py"
>"%detect_rpyc_version%.b64" (
    <nul set /p="ZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBwcmludF9mdW5jdGlvbg0KaW1wb3J0IHN5cw0KaW1wb3J0IG9zDQoNCkdBTUVfRElSID0gImdhbWUiDQpDQU5ESURBVEVTID0gWyJzY3JpcHQucnB5YyIsICJzY3JlZW4ucnB5YyIsICJvcHRpb25zLnJweWMiLCAiZ3VpLnJweWMiXQ0KDQpkZWYgZmluZF9ycHljKCk6DQogICAgZm9yIGZpbGVuYW1lIGluIENBTkRJREFURVM6DQogICAgICAgIGZvciByb290LCBkaXJzLCBmaWxlcyBpbiBvcy53YWxrKEdBTUVfRElSKToNCiAgICAgICAgICAgIGlmIGZpbGVuYW1lIGluIGZpbGVzOg0KICAgICAgICAgICAgICAgIHJldHVybiBvcy5wYXRoLmpvaW4ocm9vdCwgZmlsZW5hbWUpDQogICAgcmV0dXJuIE5vbmUNCg0KZGVmIGNoZWNrX3JweWNfdmVyc2lvbihwYXRoKToNCiAgICB3aXRoIG9wZW4ocGF0aCwgInJiIikgYXMgZjoNCiAgICAgICAgaGVhZGVyID0gZi5yZWFkKDEwKQ0KDQogICAgaWYgaGVhZGVyLnN0YXJ0c3dpdGgoYiJSRU5QWSBSUEMyIik6DQogICAgICAgIHJldHVybiAwDQogICAgZWxpZiBoZWFkZXIuc3RhcnRzd2l0aChiIlJFTlBZIFJQQzMiKToNCiAgICAgICAgcmV0dXJuIDENCiAgICBlbHNlOg0KICAgICAgICByZXR1cm4gMQ0KDQpwYXRoID0gZmluZF9ycHljKCkNCmlmIHBhdGggaXMgTm9uZToNCiAgICBwcmludCgiTm8gcnB5YyBmaWxlIGZvdW5kIGluICd7MH0nIi5mb3JtYXQoR0FNRV9ESVIpLCBmaWxlPXN5cy5zdGRlcnIpDQogICAgc3lzLmV4aXQoMikNCg0KdmVyc2lvbl9jb2RlID0gY2hlY2tfcnB5Y192ZXJzaW9uKHBhdGgpDQpwcmludCgiRGV0ZWN0ZWQ6IHswfSAoezF9KSIuZm9ybWF0KA0KICAgICJSRU5QWSBSUEMyIiBpZiB2ZXJzaW9uX2NvZGUgPT0gMCBlbHNlICJSRU5QWSBSUEMzL3Vua25vd24iLA0KICAgIG9zLnBhdGguYmFzZW5hbWUocGF0aCkNCiksIGZpbGU9c3lzLnN0ZGVycikNCnN5cy5leGl0KHZlcnNpb25fY29kZSk="
)

call :elog .
call :pwsh_exp "!decm2.%LNG%!" "%detect_rpyc_version%"
if not exist "%detect_rpyc_version%" (
    call :elog "%NOK%"
    call :elog .
    call :elog "!FCREATE.%LNG%! %YEL%%detect_rpyc_version%%RES%. !UNACONT.%LNG%!"
    call :elog .
    pause>nul|set /p=".      !ANYKEY.%LNG%!..."
    call :exitn 3
)

if %DEBUGLEVEL% GEQ 1 echo "%PYTHONEXE%" %PYVERSION% %PYTHONSYSTEM% "%detect_rpyc_version%" >> "%UNRENLOG%"
"%PYTHONEXE%" %PYVERSION% %PYTHONSYSTEM% "%detect_rpyc_version%" %DEBUGREDIR%
if %errorlevel% EQU 0 (
    if %RENPYVERSION% GEQ 8 (
        call :elog "%WARN%" "%RED%v2%RES%,"
        call :elog "         !decm2a.%LNG%! %YEL%v8+%RES%!decm2b.%LNG%!."
    ) else (
        call :elog "%OK%" "%YEL%v3%RES%."
    )
) else (
    if %RENPYVERSION% LEQ 7 (
        call :elog "%WARN%" "%RED%v3%RES%,"
        call :elog "         !decm2a.%LNG%! %YEL%v7-%RES%!decm2b.%LNG%!."
    ) else (
        call :elog "%OK%" "%YEL%v2%RES%."
    )
)
if %DEBUGLEVEL% GEQ 1 echo del /f /q "%detect_rpyc_version%" >> "%UNRENLOG%"
del /f /q "%detect_rpyc_version%" %DEBUGREDIR%

:: Display all the variables in the log for debugging purpose
call :DisplayVars "RPYC 检测完成阶段"

if "%UNRPYC_NEW%" == "n" (
    REM unrpyc by CensoredUsername
    REM https://github.com/CensoredUsername/unrpyc
    REM __title__ = "Unrpyc Legacy for Ren'Py v7 and lower"
    REM __version__ = 'v1.3.2'
    >"%decompcab%.b64" (
        <nul set /p="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"
        <nul set /p="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"
        <nul set /p="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"
        <nul set /p="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"
        <nul set /p="IlMSLpThHGMs0SjrxAm9lqKOY3KJMEyDp6ctD4jzK52fBfYIFljOHr0uY6+UHsIMV9DEIo9vNveW03aMBEbXSyVmYoagSRmcWzQc9BNKY1gx6HRBpZdxGIWykfhn3yjkPtOUikN/bW5WykkVZNmaHIu1iGOqOyOHH1bMXULexRcTn7ndbH4xjqdfV9gKRnnIJIeZToaqjs3M/wGmT6/96BgAgENL7T1rb9tGtt/1K3gdFDK9Cjd2ut2tcXMBJ1YaYR3bsJRNA99ApiVK5oYWVVGKqwb973seM8OZ4fAhyekWRYOiMsmZM68zZ86cZ+kY3d0ICUQhmHXe+2AZ6YG45TrcZ9NS4SX9SSY4ftWuRBi+Y0jxdLbxkMiwDWOPLhXe8mNWvUO4kF85EjYVck2QRkeoSRGfwR7SarrlqFz7ObC7bHfXMB66JntlJutzH0XOwQLNqub7vgx8y8MLEvF6h3GiiXTFGHW2yDFOTTF0+J2MwVIsIdQhJdhMVtoVyGxF0MjBRnnU7XxEPbLrJgq8yx4jO/G2+9s3Gd/UMH0AXKWZP+MwkbxHiN6QmVjbd4OQ5udGCxgTB83QXXuR2DIR+pwaIX+fiu1soIU1rRTg3D1xO03a729Q3Z+j0U5DigBAFXK6mb1pkt7CwV+uKiIDp2pKK2AUgWOIsyTbmZIzGMeMKY/0rYlePdnJ1rORZtZUpwIf6mUF67lwwHWDRF9OaK8gczIGxPKpQz10Dts25NyVYU8Tc5RlNLywojXmHJs5SeTyCv0oxwr6XEZ1cJTuT2rrFNJb57pF51rBqUT+itzTAB4zJ4jISDVSNOpmgVHW5lw2BEu8qlFv6yc2Gu1WY6yA6Z6eY3tu7AuZhSr52Etwr4pwzcPxmGPCX5OaFaXF6PGdTyPc89UL4YiQ+VVz+OkB4z5iXds4HqkkvO8ohwagHb/Asa8a66j+/MUzG6yUOzrIqTXrANx36RJUR8oW17VAL9oVwnh5hyC4vkusCJRkAf2pbrN+dMWJZ7gUp5f9NkqynZv9yMuXyztds3DQlovEcLZWKtqcWaFf/iP2x33EOJVW5VxcXfdq9D0lA/ZrEe+gHvFK4Ymk2PA135/1aIc2/gdtKwRt5TbOoXdkc8M/5C7GKJlfYRMT2OZ72Cq+4RbO9wzBebwtbHWr4Q5u1J1H2MG1vdt0A1d01xpgsw1swSt258+T9BFP0uanyKPu/WrULzJ5ZeLvy/VzirS9kbxD47eNUcoRmiSlGePr2IU2Yuubzhrhp2iNURQ3EOHY8hTV96q1cYweDzkdE0tEtq5NXCLhsYYmPV0a3Eb58nb0FS9v+ljYHVPT1mtxzmRAKL54UJRVjB9qH1e8asaNSb4rZF8ndyMLAF7q+K5AALg5+ZL0q2pTZL4zXpT7clh+9SkQUsqnIQU3NNIdaSTC8C37mB9//JHjuuORH1FaJeXETGG4SYslBG4ceju+TezU0PSPFPLCrf4o+C5o1XAUaomKwxLBgfG7mgFZvpZ8l0yENRkCXBPeJ8eFaqZHoUftYdO8x+VURrbW9BrSnA+phmwcNr/RWMU+a8qubchyuey7XHKZXaQhvSZUtqh1cwqBJ801Uxt1WX58QFdKkv8VzJ2UyEXow8ls1c7trRW4fvax4/Umjo0z4yTLZtlS8xQ1PTS+cl1qUbNvzlazWaubvUazWM6wV1ksNLBcaGrBUGPJYBej7eaWI6eLevlxuqiUGxsgGsmLyzfDjnJePFza2+sTbdWCjUqY1m2DDagsX5w2GeTV/GiUgzf24xGP6r4T7qA/di3yUKEK7LGA/HfRh9ictsmNWgwDhaJtF5jCKoG3U1tHcHZj+sgcGeEI9V05ZaJ8oZJ9wwwF93ESLjBTEse7YWNraXbR8ShLzTxBa0sK00N5jH5eCv/GhZ14Ce2dOACTTLBMAJ5SyBROrhzPpkkk8ljJdlp1wzJvEfnxpU4qosrl5xR+plMKkazmnBJlW/Vyn8LaNuv+LhyGAtnE2zUQqzWMVAht42SitI1hMvwcLpqpmNoY2qlG4WpALfT/Mqz01K3XJKObfLsIlnJhlsgo6PYjcd4hrWjQKLlWN1bI5xZb2bLhvGJwlup5HReYFyILhhWAyrKSywO2tQNwiTeW4p6elA+kU1yb0yiJlk2PtzKlbbKZOURjg6gmUyHZBGtcg8W6XCpGyMaisQAzgSRpLFKVT0KZpjSPw7hCAYdy4MJDhnIrczRa11mqqhaV4zRgcg5AArKVpaxwLagxllVtuGZG9O6xeJrlYt34YoPrL+LFKwSQ8eNLbWVFgd+JwXEeyaYGwyxypt/dmp6IarEqDJANbJNVdzAzLZsxa5lrl7pkIWpwuTEe86DfMGo8Gi5HBLVdRDU0WKw4ImrOB6ztVhggFal2nXIc64xmr5xp+MqNxQNO4XDSH/jHjZRNxRwJDVRg1fY6W3JWP5Ch2E7HFNuaeW1pX0oHE0cXye3y/ELLwBqQFdlObc8EkI1bvyJzoI3bzrVgxHI0YXJEzJQaPLYYj2p9CIMs8hwvyz2QGs4nCUqKgDEpTTxb7cbOjASQIvirMM6iSj72Uonevb96z4NnSlxvbtHqlbNuskCRdBUKPDZcUOxt3XoCNDdZGlGG0KZ6zLZn2xKXXnoQruWDYg0YaaU+Ynx+xCGXk2IklhuobpvcMvcVYHeTSw7H/BXaJMiNdypOXFt5mHTzLH8FiZJkf7cyqAfQ4ykHBzn2xqtICjYQ19KJ9//jg+vgI/yf2MRJkobAlouXDwcdjDJN0TJ0D6+UQqqTrgAgZejnxSlrQ0zTuYymEepFlyj0QF84vHhg9mLFxRPial6ZjmNTREM6X91vqmSsJJ6Vio6oPNqQdEb4+5at5W4FLlQIlLkBzlGRxAK/tt3So6tsxXLJ6H+UgVCEh/P2WfUZfooofzRllfarlgqj5+y0UkOom4P6zRarrLHiWj0x0z9PZahkIyspcIyUYV0aABtqe8uIt/QSgp/pEqLCMQNdKGZ5Ygnd0tQQE8BqfX45EKXEldHndD1h6T1I76UxAL8yAFKlFXmdJIPsSWbKtmRzGYa+Xwo2RWW2Vc1V842lKAVVfHMV/Gaq94aC8w1U7XUq9maq9U1U6tuOoUyFXqs6r1OZFwiTfYcJ77c7r+0LXTx2wga+GwnHDk523AZmsNIPr0Jj/aWpw8TD+3a9jDK3Iqq8UYxvIeuaCyzY8uGIomwKrUMW0CN5xwbRDMPF77dXy8nTf+jOb8VjoBaYkQj7Llot4mwZjyg/OGWAxyioFJGeUk4cqpAS6mO49JIIQ87+49k3GigRqSmP9orKH85+/WBmXBctvbD6+n/iUFCHBWWM/hu6AurltggdgfnfsjSPLicjoEWzdDWdGUFNRd8wfO9ExKmapsgeUHpZbqmYM8LukhYTwRXY4yTBmLrTO0/jNYBhXCYR8xse5sAwA+C6sknzJIo/VKAcPWaVe+LKJSpNgFrLZmhEtWr7lXGH0JauBnCR5jdcbf26K2A/Le00/gthwDkdsKilCGRMIUNCjFVpfL2LwnG06LAalPZbeH0MhYJsnpC9sKjc8Q5NsDLQ0LUJD3ZPSf4fFUBENCVaaGN8Lt9pbUKwSmzXRCzojONFAvsdO8uVd0fn7GLplhVLj2roFVAp3/umLExgjG791PfKdp2xebjjIkhWbE6r8OE3CQumDn3BKenLAnvxYcCrWfo5R4UD73m50BoJNknZuLFNwVVem3U0LQq58GipNbvoLyttdvAyssmZqoUonobL+DOqzYV8MYjvw6mymp0FmK7d9/4XA2kLLvvyw3NDgChAVF9s6NnKWnCNSQQ+Yi5f/XQ7jL7//ntqbBEllAJqsogBazivD3AvaPJK6Vni2cSwFLkVvpszvqwgnCIL6uytjQ1P2+WYQnDbJUJ6mr1q2P9uaieeo83MN21Y6qbcydxxABqdK5quwsWYdRxG7Bh6zygg7lRR4tS7bnsdMixnSmA3d3N36c0QqO8I1GlrubcftTXHwyz6aUUhfblrmAChw9lr/WPMu7AGwrI8xtymmIboRffZ0WG+jdQquXdxA0bVuSbYiSb27JWWTcVZ2Nia3Vwnx0TyPNlx2akyTzGj8FlM+fzsuW5fY56kj2I5BcGMnCW/YMlfHeYN8WiX0B/anEMTm2wFuFB3couP3AcyWkvvRzYA8be/sPs7uNw4442oZXPN5Mt4djHfbiop2HVHjz4uAmZXhYQpDcKih0w3qmDmncv0wTh0HtLFJylhZCOjdpYfjrZ8GK2j7uNfzKQsDiljOu9QS8fVwSccu9SKFiMT61ScGZsBbB4LXY85YO7SmvPmZZomj48JRuqybVBhg7g8au9a8/J1jbRqppWU+YsdxDTavPx90zBFpUiGU4LYznlzdUqWziUhIx0nO5T5NW6Aeq4xXmQR/al0EjfDzXeYEv3RkdNmbzfGzka7kokV06pj0xA4nJGVGgaHpQRdbBEr9VzS409QMT09wGyMiTqF+Zqkcg+UAXRBtUUi1lwdYzn40a3A7VwCWIF98Uu+QlOzMatiiqL+3J9PFBQXEnU/yV8j4+2jPOLZbso3AXE3jU4VvBrUhKnKRnAd344deaLyKMiVk8uZWQvo7SuRIODQ5frI/7qqzVxh9vtWbxq83HWFA0aGCcDLWaOPRdaoB/voZ8cNzJZJP/GoJCpWUJspguW6EsE98d6TcBdWW2ANFBslK8qCyzFLVS6CDqdx0jBAJMIV6YdtK2HqW318zoamPrUezn2czjKjGfrYYD7ysGAPnNm4whbECP/10MQRSEJfzeebQKfiRSjZEhiMRuYqx21n1PZ9e5MiRNijaEyXW8XgyyAeU1pObKZdFr7BUH1F86IdZZLEc0CbsjWS3xssk2FHEARth83mshIf4HvWECXoPjv+uaMutREcg5RbXFjkx/dZUWoNNbaysDFJJzbZ4c1cOeuCMnDxonGtW+xfF+7vgxUfuMN735b3PPEoQh0RA7IFkKmxY6IrKoa78EKhgOWsYpFZA11cQb1ajWo1Pku2MFTkYZUaeW1MwXSw7Q2G4jzl89DIDRao+5nS15PyiUeFu5v/IrOkZTS6m8UjctdKR6PVfF1M6HnY8UbRAlPVe6iW1MCvMsoRiQmXMLtAksC1N/GiYBp4e0ISo7UV7vt7HDQCl4DuzasZhbtHqys90+iKU8Jodc2MALGBOoH31ZCniBXOiKblTMN2a3wW3t+Ow0e5qB25B5NQCyUesvUBDculQNWRPUs52KGyMnJJQf8b0k7LitWOAsT64XsYC7BRGYWqETd6NZKskvIalR9LxIlXfBRe2rPpknPq1kzOOvtYx7dlo6VNVAlIsdJXEZJaVivRemtEtTbu5utbv7YNZKC9CdqWPcbGf16Imt9gayrn902jT+iSnxKSw1nvKsDaMQvqrrswzEW0Scwmd782D6l0FZUF97WcTYPvtg2O1b7ZMJS3Vk2YWL+JErxsnEONgo11mMRhKTtOH71xGjGvRGIBPe5TDV/u8MtRwbEyfL+Bq7EyFM604FD5MIx9tknwrsrID48cOsKUuomDF9mwZbRAYaInzZZvIwdzQ/GaSjf5txtFqLD3krrkTIZ5NIJJZbztSYXvA4DxW+gzNl+zMHd/5HtHzw7/9vTo2dG33itYJtji43cZjvs+aj2BwpeYyzrLRKg3HOvt2psuQsyPhcZ3EVnto5HZFJUxKeUPBLTOoEJ6izwpcqBoNDVft4RRGgDK0snyIRQp5sMsS0cx2QOM0xFxNhxcDrMMZmgBHnl7fVFjz6dmxlGYtChYAn6VH1V29EWEhi8UJLsj5CbYD/mZDD24DaxOs5G1yJVghUlLsbcdjLcVT/A3osHNV7dJnN11UNErXAc6KJ3B2+oMa8FY/sp2VNg1gBFjWLSJ0cMOY1aKcwR9EFNFpm4Pd8jv66OJsU8TYCagWUbBcQpTR63+Gw3fhO/EJMW8NmQ0n87GMeWOPablG2C28Nv0c0RD4lWHrY33a+oHrsU8X2LxKbsLOXKckDjhjbGFdCdRo1qQXAotPtEOHePhk9W5NdqAO/Gm6/UvXg/en1x1vV7fu7y6+FfvtHvq7Z304Xmv473vDd5cvBt4UOLq5Hzwwbt47Z2cf/D+2Ts/7XjdHy+vuv2+d3EFwHpvL896XXjbO3919u60d/6D9xJqnl8MvLPe294AwA4uqEkBrNftI7i33atXb+Dx5GXvrDf40AFQr3uDc4T7+uLKO/EuT64GvVfvzk6uvMt3V5cX/S504RQAn/fOX19BO9233fNBAO3CO6/7L3jw+m9Ozs6wMYB28g7GcIW99F5dXH646v3wZuC9uTg77cLLl13o3cnLsy43BkN7dXbSe9vxTk/envzQpVoXAAdHiAW5j977N118iW2ewH+vBr2LcxzMq4vzwRU8dmCsVwNV+X2v3+14J1e9Pk7L66uLtzhMnFioc0FgoOZ5l+HgpJtrA0Xw+V2/q0B6p92TM4DWx8o8UFk8aBGC5YHp5ov0czwmu800yTgVVjiJ0AlhFibr+BfE0Hk8+pREYmtDDaAl93hW0RW31RK5FbI1HImod3iBfwafYZcAflGuQVQEIPP0zIcCR2RRy4ZLsi7qZjL5wM0psMvFagRMOfoxi1OYnSQ+h3GCxhsi3T0Q/Gjs813yefAtFAJsHmccTI/dhQhgEt/C2TWCIyGCc0I0wnl4+vNo1GJXYm4KA2NAHyfY12MNUCrrkblY7wLP1T7Ql9m0d9HKBRZUeCQ/yDqqYGsIPEMyxETU11R+L0nDMWwt+s3wD1yLoXyrHvJP49X93HiATwxqEn6KhvNw9CmcRlhiEd0DSRmar7noa3jHE4AF8ekyr6c9nqVo2qfXojiYA1g7WZJevA5HwMmvCwVloT6Refn0PlzgeSMfOf2jXvfdjBACynQXi3QhC4rXEb3ow/i1F1wZX16KV62PiPlYz+MYmZi2MVLHVqvFb41B7ZPPIS/l3t4e/SJxvo+WIReX8R5HwAWhU5oCH2WBN0Ctz5yWnHWtMZ0aQk7HCKJVIOJ+TA/HN/mS3HhSfpl5o1W2BIxSKVnxeAfGDTCZ1QUUhvLhLh7dieMl49MiSafx6Jj5kx5T+xT+t4DTno4kky29uaGPwXCIHMVweHMDx+OS9BVrMvrDktFPqzAJGGQX7yAoai2HxNTGAYvgQGUCdHNDnE9eHFjVvWBPOl/LDqHw3O6i1pXm0DU46p0y165qjRt7JyR1cZYvSQeaefHi5gZ//0f83oXZ3b7Pf2viaHhDreFLOJhp5fElwSZWQqIoIFmYcwsSlZTEV0cahbwa3rSk7rYau0hLORoh4xxP8jkEBncJ/C0NNWUGQ4VVYSKZhCP1VtzSxOlyF8OtfjG6W4vlGaitEmq4r0SeeCzJvcVuoygGj2LCVXQ2NYvkeb1FWNp4BgUBC1kKe6dvSBkTVg52GqMU9zaCWQ1YazdOZSdYNSeGgFFlCDi1rQFELswxNRkwq8kYH8jhbxLDdCqRrnfAUA9MFz9yCVkalIX0geRMqQ0SZu0YfbuOb26MLcVVcudY0hXwyzyTrVgBHEWcsY6SiwD/JxEDCd5NoAheS9oj8Kzx2iHPSQRFEzRicsvhcH+UoHEJRaugqLudvE9ZR0wo5Vw2rsbUpQc5ayEw+vndLK9PVvZ7wyHuaN6GQPcJVssIrTxdAc7ifeEBwwGJRXyI5Lpk4VroS2Jdbwski5ear9WyHnRMWnAka+IG8AZFLjqrBV4nVQMibPPoLs0iHbDmLW0tiEocjPmGCVXWiCU6Kco8SXL0W3/eN/eFP5+z670c2t5HzEXNOQh1aHoRAhhrbtbWtZUd9ZG60Em8v3euZgo1f7dIjHKsR17SIEnel2e/7gUs59gn2YOxdji798jPSXyzpbOInUETXNNl4MB/xksoLwQZmyGnaLEJCCUi0gh0YZtEPykwdKQUs4xL70363MHVEchuSeTFlJhOJZr3Z15fra4bwiOdiRXqupKGGh7tJpUpnT7RiHSYUnD06ngOCwDFmnRIN+qjhV2Mq+QXp3on3xabEZAk8ZXVZAX4RO+tVuziIruyeFtsZV/OQU7kHYHbb+HKty9LQMuE09Cy01ecMjSX9J7CoxuR1x1QcbM/8fD6h0wiOjUm8aeIKCNeGh+AMMNJpE5AwRDjJ1lectNc5"
        <nul set /p="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"
        <nul set /p="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"
        <nul set /p="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"
        <nul set /p="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"
        <nul set /p="M7Lb4CuxGq3ta8T3K2qOqvvJs7uXI+9Hes75u+khbmDjwucSZS8wKXFqVUnvCfgTjIrObvJqrHdXPoszATNlkk7WkSUUkdj9F82XRoNnOfOif+i0q1Dgxzs93C6g01XJKLHoy+7/uVKUVY+sqmT1qEDRtiS2vHUiV2Zd8krmMnO574bWNgKRJ+mB2nwlxUfFNEwr4TFdV1RwF2uT+m7wbzIFo2+WkLjPSa1ogZaJlyX03ewpyoTlh4JUKYplv2wAaaGkwgC301ctiUdPGtLO53IpWXciDd07fSekgAE/xFLlsuriXMM+MQ7CnrNEl6BcNf4Lw=="
    )

    set "OFFSET=--init-offset"
) else (
    REM unrpyc by CensoredUsername
    REM https://github.com/CensoredUsername/unrpyc
    REM __title__ = "Unrpyc Master for Ren'Py v8"
    REM __version__ = 'v2.0.4'
    REM Modified to include Inceton + Version display.
    >"%decompcab%.b64" (
        <nul set /p="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"
        <nul set /p="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"
        <nul set /p="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"
        <nul set /p="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"
        <nul set /p="1ozJVnGmc+cmgq12jC0fqy1BUoZfJaEmqsAkZTCpG9eYleoKeopLgmDDsh2obInbEKRMaOdQKHGtr0OjOXDdzRJXS9iBovy1vNI8cwkeApk8w9Am2NR8gjcz4TU/n3Vek6aESS5UevC2EDwN7oAbPAqLQYXzSsgAPVNclBwTxrWktWTjl4t7XWSr3vtLyOvSW4wbOg19AtTISUu2CGOiOY5GcYRJ2spyd/IyWimLYBF4Lff0NhmIddS6E05ken/tt++Yn/0Bogvq3uvZ55oEaBgHV2uEBvuuKTyjGvKHq2aoRlhoVby1lfhqE3958i4z8Ai0hGUnCTnkBFHKBpwDwy7FM2DIr9Gpknx5lxCWYzY1WGXcwVtMZ8ww8i77xUUxOmdeMpuxSoLBU/w1hlyafPAJH/EcQ5TOJE0wXw87f16VtP9htbhB0BZWlFN4RoWlOozT2YZqSIUPg3WXrECFM8Fdzl3Pb8ZCCIbOsYwkUb1dLvTJxw/Bm4j2TG0QeXWxfMEoK0KleCisL1w9vGAa8Zzy5uycYLR5RdvhsizhcKeZMsRbfz4chhaIwR/sJHjvBDWUk7GaEBNn8hdCvKlajk1ipngrKu0QtCmY20I2BipmwAWKxuJ4HjWCZ+fIoK3xPCd+yM22UJqWuJ2trTQ8dU+ROo8TqXNeB0eIDhHRQleFi2zwuWv7zwpLY7uBDToMwmPfoufd427z/Yy/XMtp6gcxwNzDsPD3sEAuCpERn2eUhzfSFdFKRhKG1wcW1ML6/ssI+i0QSQIYyFRNNw2UIrxOPfLVG9dBUq8LOY22og691m4rAYDnB/RohcNac0WY1FZXePe/ZFE8/8fLX593eihf+38MjbQRZ3j0OuM7vqXjfmAyRMoDTZqT3XWgEMHvIDHu0DTi+mNKAcC47vkrOu2AD5gMjstXzYNnb6TVkC18+1PDLhjm2JgHeUUO1PywoTKsPqHep2F5b4QgOpEehiMeVZgx4j8FC4Va17ydpXmDt37UyR5jOzmATiAg9qSiUV4Jlo1/b8InKu8cbzugif94nFf2Os8djNHuBOqCEkSTF25wVfyKYW+SZIb2OTTEmge9/kZQNH/o2SZ+NnmaxRjaztjs2ue6Ej3enr3+giFJ9JKI3JaIob2ilmLtbVECjlpEUaBNUPbUVwg2egoq+sSgIncvlDyFXmOL2SthVLGy4+F7Yp78ktmbj6/iSwdjiTY2+hjm2dWVNnGbWwzZtBGKL62cWZOuSukC8w4tPJ8q9Gbz7dTdUJDfHNVHznbJt0OXi8Bw5p3kFtO56yDsSHNjNFom9R3nn1y32rXafZImkQj6AX4JzJUBK0e7RDZF+CuM7ejM0aR+mxJjjvyyhmi0qrFWNFGPcVyJns1IOGgYhsp6in5Hri/G7Jxw2acWFcbbFbcRZUSNGeZEpI8vRYzoWRhdWx72VUAy+kgTERMTPi+Ox5O9dFFpsr+TVslU6f0Sfz3q5msM6Wd5+ToUF/B9ZG9yDlHcbQe7E7H0T8Y5PTQOA+3M7usYbkrJNzGc8MVaaQQwk7TCx9a2wZvO23OIz4ILj3l5JGPEfXdcFkV9TB5gWNfKvqABXvTYbJIDzDLeoa1h1G1tG0Hv3akaoqVukxCGWoQj0iYeas6jW7Cc45QOhBCxMABrVhVbpKArGTcZXvhCSiCfHckaQxdiqiWZTViYFASFOb7B9OaSNTH4KLO57ZqIvYZ50vgdLDf8z4RXk4kin5l4UWzc2YVgSWDnohFYl03SYRqMpV2a4hwQsSh1zqXowjSxaIBZ5dVhgGWAJyAJ1qGTGapHGcrNKs95i+PyC4PKYaObB+g0tQMF4swPugS7e4CETHsY9/YYbBdvwYxEy3EbI89rxT+XHzkwsNuVakfY69a5QJo6W3zIL7SFR7kF7WNaev1FuOaG1XNU8GV5L17K+MWlKn5gytRURl7FAvwpvmSaapcW1PapI2ssX5msxw328jDQkt8YBl8H0pi+47N2ZvWZ0uadpAtE9+1gdm8p0MKcII+frWOWWmqGEJCSkqd1ivbrpqkJTq6TcZzIwNzECbqNkabhGNk8jkHjVFVQfhzZXxsnEYwCxIPy78OFAk346YIqj6Tk+i9TKS7Dqkvo1BItselJNz6a2iCcE+Js6mzwkYhxaxokwDULdOf8JUTDXSEo6VhUati5NCB2VU2mfc4JTab4Oh80BQEEWMs5tD9ZZTmcDBUbsdnhQQnXSsc0PIGzYFURBAScusaRgmni1pEiJ/okWxC5Gerb1EAFLERXiDtKUqktAEcNXKwRz01FCaJGe8y3GPENHoNOirOBUkscpaRqVse8RIKnm2oylQO1wQiEpoBW25hrkhoUfydVTRP5Nh6jFGB7cSM0CWN9VHTPeGw9p0iDsbMuOlzPtvPvnFi2gQctw9UjM5MKIjabUtiYDM+JCZlSxOJgDcVbmjqIApYuG4mp1e8GxkHNzhJquVDtvHoxoZVGW8NejjS7ulSWqmuWOTWLopAXLGaQqep0ldy7P6Kyb51TTgXCgg8zu9ZpTWVTg/PvvCd8yLexTgVybTZ7h+JkPOz01NxZ8BgDiC6Oi4agGY/7nqRhqXRy5MeFeIoR193wVjMdjoOOGdSpMHbAl63qtMtAKuGpFw5iGOspEr/t9Q36mP9Zp/mZtc+N+GfnZx0aexWUF4Gbvske5JZUcfUN1bL5wzbN/z3S+H11R9cV9VziJ9svi/Two94V0TCy51VRvA/Rl3e/KML/183gCFO6Fh4wxv/26ItIVO49h1a3GlYjcR8ydz0vaCfqTlFEUTvNGhwSvMAHhwdE0fNUkoaOgaAdWr04bz/96eaCd8CIymFWmj2wYiqHChOQeAKuT0CqgMlQTh9quHQajOsyvUXMpHVnntxb96k6R5B6xl5CAxgoRV9XFyAIFFlr+BnoGhF+Unp7zNFNberCJ6kKDe6rQjefrirIYYZN+QM0NErrCf1R3MjxS3FbcgnGtQu7wwuCNfOblDOu30iTOVlrVUGp6wMK87TFJMxhLHg2clw7xJtaZd5nXJ0H6RHFohGi3KOFZSMNkuUSYxYLr122/srg+0N/dk2d8iIHKi3INilApIrccMQ8ab/OUoTr1i74qhHzan9y+6BngM5YN6IlDSSdjIWQsbIe9Z/0u29Rv6OLucXyDPa5vdX4sszgYVlznkTEHdmoX6sK0DU52KhoySMMaCIsXLeklAy/nO5penKRbAh9MZNiPbx1bQiWW1TWPs+GxwWIMjT3m1gyz3fBDLNqDvCYL/Rn5iG+yNvbEJsYPHySKBu8w3SrObFdtdTTcxpFUlWT1NAad9BHPUKH2+naRydFvHER9ebSzpIdjx1zJOOeC6Ko1ZhJE6p7+qsgrECNHx5Wn/bXahVeyaJJiq+nbVFS2zXKSNaT8SiT+tYVoLVuvyMgu5INMJQfmuprq27adMTHI3+1a3aTzmk5Cj2N7KEjTEV55zMznJ8WF7xegK0N74jZ4VPftU2NsJGRxnShVoHdQlu3r7Xid75h7t0Gs9y7FoXZSCPn9yxTEdliojdhbCitVEqUKaxsQtZB0/EUdRbAPzBWD5dNQlWX6sEN5JCszEHq21lZjNmCh1MTkJ7IyeSURFsrjQLu08odKEK8i/+XyhQBBIt1NkpgMhvW2cjn3EZCQWVssSZC3zgxEHk2q9daM5OfKOoSf3KlF0lRY+QrEMXSiVPd8HCGNfKBoHAWXhhW8QFEV8YHuEmkoYOWcK4Nu6rkg9Wk01g2HTyQjm7zYpIYiGcglneiiHN0S0WcBep+SG94IZfNkB3PCBNB5ZWl+ePF2+/PLjZhb/8bEugHpUhRbf7e+ov92tW2QJLgRBc1gWb+voUoZEvP76i/9UkTabJ9mJdXZ6//e8SD3RlGYW9G9fbh1JD1wV53Vd+8eNWNwQzM03kBl0hsth+RZkdHobFILy67rAimhhYtVl47e3fOJXjxTO0dYq/i/7uBMHuPWy8RkTIzO9BWr1dOYr40IFgd35vlFo2kyGtjuWdbF0Gp8oyAa7APsnpVu25ssK8SOeTcyUDauWuatLfeZBsHmjG+f54OLbQcFp6ESxiVuStEF/V9M0htf0gc7Vvoxn8+B8A/fh10nrN6+PzJ/P/bux7u5/zSuzumh/UO0/xlmzghBAo38fhx5NBlNs/ypMRxneDAOfhmzAWzaqCf0m+8ue3xNGV66cJP6ovvWPwirAxe4qhApmG11juSDTJtB4YaIGVhSD9kbvvpsx/XLe5yb/dLZeQOedRCw2/+xCBQeXyeC4mvnWHEE6OTtWf3G3CAE76DzCONtMX+OPSgS73zBeSub3J/vLPlt2xQbjl6nszJT+bkJ33hX8OcHBydTSnZ0EV0R94B9vgn6WYlZv/D9BH0Hkvbt6r8+DO4Tfn5UrOJRSf48sxrikwX0yI/FUPAT+c//vTm8mr07v3bq7ev3140jHpwGMKWy9Cn7bbSxxLkNvJbWQ7JQW6egDOGZ5CFu3SGxPjTrAyPPn39oaE8HE3Fw/nqA6m89ml5nNriIRJhs9v41CLCh9AiTMeamUhdFKSnDPim779iyGNlMPt1HLiTYmRVF6gSiQvHst3VDnH29NLAQ4jykBe4bpF1d6Bgl9Ek27NzTKylMdpWrrSqTQU3gErRZANVfoMza45clWYjxrfldbukcETMIg1wlsqpozpDJCwTFebGX0nVpzQrNY+sOZk9cbMA4F+npE/WLt4/yrILSbhwTMNRUfQ0z46LPsVgDdaDaqO1sIyrlgweH83AGEaSnnglyMGrFwQhbQQTDrrNfQTzgpSmzbNWmzDkKSrSvuKoQSOqAKJMsrYU1MSm5V+55U/6Yw78nq1F2cOa0QMsK4Dx9roR1r+4IbYNzSm62JtME4W/dawWKSgIMLQ5zgpYJKwcGGbZD/S6jGQchs9H4v0kKP40kv4TSfE3S2XIK6z3ciANNKCglZtQ7LUowyL1jWKizKUSp5HpFO6jWdNDXZISFeU932JpvedFQWFRJjKrMcoq2A20EThvT1YNbGjaY6LvyvLh+ziQKVtj7jLYiUGd/4HLhKcUozOWRuRAVXZZKNSTA0hZFpm48+sywepd7LupTblA8Z25PTOIkRkdcDgkT5INO2c3Ne3lrPLFniCVuE1kLNLzorSwNh6oiQ2Pk4HBCVSysDVvWfwXc2+FW+sEFwCcmTlh07odDzu2uUaEd5LumEhww9/wPG0JbAjKqfyY1gJww60ySsGHLFGYBf5ulVQHfrwZIxqGTAJTzMONCFHOnXTUUg0Pb5D+iY740DewK2bRwh1NiNGlSTBrER+N7q/cOY99SXaJL2ujfT/rnDmtQkAfVC6SQ30wkuXoyEklQq3LFE6cfjBwH2aD5t5mmIdMEtQYTYRlIDYpJGQL09tJi6yT5H4j6GRcLKNUYoZ/ItISQQd3FNhCWKaAA6TV81rUgqKqMoQMBbbdsy6lQ0rVBuR7EBVWKBODTkPlQDMBBKKKLwHUUmoMOa7InugvbggmdQz3E9f3w7RMW0NmUhb38N9qOXyqfPpU+fSp8ulT5dPPUfn0rshnFSEQOLBMVXmmuoNVckcqkr2qEyS3VKEpbrimNl8L62ySYezMkFcx4T4YZEBE8ePcSaMZ5JwDCWrJbIVFwBLe+RVd2hC5dplihegprl2DHcbSBVE0aOMnH4ps1plns1mevihuXpB9QFJdYKgkjIdOFGMhKvp36GnIXRpCt2+KrfKIqCDa/yVHfkFWKhB7JNERFesHM8syivvxmEkl642GvLKwi3L0iJsJZT/2+hy6Pbu8kjijZ9JldXT57s3r87OLEay/y0tYeHBsE+AcPPYLirH6miiSFkYYtYRl1PL1CI5J7KvSOUBc2ztbmOc/vOKppuxIscNWzgxjjSmd74ZcaQg6/J3tmoJh58lyycIOJcnHsiCcPp7RTm80MumUo5E2/plvsbT3R1gFBP/+MWGXFhPOl2S27+PtFB6jB4zzCAOsuMidczOUfPe0joln1gjN5PMiTA18Mk0XjPEB1plE6uGewODQ1OTi69JgGEgplI9GXR9PbLaapk28G1UexCLi20wt+1I/AjVTe+9hwjOTpoB7Ol343A2XyBAnZDHr8eP4oh2Znbme/eurjtJSERur/dEbsf1207jd6KCpP8WfE668W795WJY9Fg0auBq2ZpQ3JCGGSVV3W+o/VmwJ5ksJ7P90sZpPENVpuQ7D9KSoBXTll/UL45FNe/Cs+dN/wHUDj7gP/kNLTN1brrcVsIBNDaTgfDQn2sbnrbcCAcOg+O2BP4ZBSPHANLlDOO6ubX7GaZfj79DZHxD2FR598hGk62q++LZWBn1p6ISfzJ8BzjFRbqqYPK0qXFWvMUQzXFV7yJGt1WOAV34VmCBCtjcSsqtiVU7tGAqrYlGgKMapR2ubuOXgTWpsUcQfgEUxKm5uUDsIHqHoXp/2PxxIu53cDYN4XEr/41MpHfhUbSB8E13hCv5kOgZhn03C6AH0+mpubtsJP5YFKACzC9g7ESHLJY0iu+I574o8fUjL5y0S1m1Ps9MRbgkRX+v0Af6lxN6mxZ769IVpb7emtisRl5hSsEjzfXY+e7q7G4pIqzHAw4j3SK/EK19hyLhC9g1HDz8f8f0Pby5IPFcEEaBxjNhAvZr8g6Cek9nYVmqG+9Tm8b+Ha0VZo9J+kVV1ZMJz+HoDL0r7fpwfzdnEBn1GbJsjR+MPWEGjSeNs83ztTyM2eCiNl2mMxDZ9/VAKRblWBO53ErUVK4vg5OqCWD+/vDbQsRtkW+M1Skz4Pr0pCFKS7q//OfzD714NX7JTI88+cBQWs4NjsQZ47cMLuGelwDvgfZouyZCbouHr8y5wpuXbXdz70felF/Z+1P3mFjWaaisxp+GifjX8vS2SJi7/WkzTczTXWyOd+PyqGt0AAeqFuPuGtkC0mDzIokMY9mL81XW0UjR4y+NkkYEZ7KyW7BJL4Bf4u7BoxZxpV2EXJSWzdlYLMuy5OEQa4gyPVW8kZnB10XmJFnaYX7STUQ6keOyYK7VF/9p2Aifrw9Tuj3eFVrNwpCP9BRXlwsJgp52rcpX62d6VftIFnqov0UFXlEm5HsVf4mzEm4yuZ/bb9AGNolk9av68jRHni6w+jBPLMitKlI2nnZdbu7lIJvupO66fukwWVU4K6qhM8/RDsvC4izbjeVqzj9Ky5C4j5ZPBtcV9Vt2B9rbIbrECm7jjbosalBj9Cz37J1l8aysLUEmK3EO7+H23AYjfnhxswcf5zesdc4pHjLa99T6Jgu8wNpNUIBsh/tGNMHFL528wJO+rUnA+J3DeQ/oOb35Jne+6g65wfaK//cBtFF2+IS+2yrO74uNh/auRkkBLyqXZXbt0epGs0/LRe6bAA2wZ35snGMyynQevgY9l8m3QcjlNFwcuxWyODqGWxfgoxP2UHWp02md1/B1RZQ/cEhkqKDvuv9dJfuDJEj2B4SwtU3aXn6raDJz1PMrxHMO2tnOZixceRplHxE5c+Gu6WH2e8zUwLDU0HtDuRtOE3W6aY1HuZqDgjKK/lEWeT5LpPTltinK6g9D7CwZsfzp/P2WSMZjm0tg9DqOFgeWopICeDnJpauIIPcQ87BTG+Oy51zRfGUaCT9ZqNSFDTuW6JtwdT63b8yj8ge4Mj3f6c3m8goTbqYTnLmbpwx704L3hcQjaKvLrdX7g2G3dKjutXPhXzyOGZesnPiRllriXdtJScrxGHkSht4rwct7dSXYkUlfXozxPFrcrjsx0RxxFtO47loNvccEms/Q+ynjktiGgXCbQD2j9p7xAvlnMHn9t7b4CKL3n8xx8jXndmapPuQVtomp3Cr7Hc+JLsWVHmuiC+EUJe0YGKQlanKVAT0k1viWvNJ0y8D+RPfrz2eurt+//F9521Hk54sEoB+q5y/8HBsSE+OAaAIBDS+1d628bR5L/rr9ibhyAQ4Rh/FhcckSUnG05t17E8WLtIB8cgR6RI3kSikNwSMk6wf/7db26qx8zomjtxndnI4Hpmenq6ld1dz1+Ra04oNAKUqlNVfDmyfb0tFpPKACXGytpX7Ay9a3VAVChUeaxB0mF2fMePOzyDxrC4vGrp8+fJ6D2EnxR4N5ufOlvSf8IYQRXK8iCacTPhEPGAGj4UlASm+1mtd2g8e0HIv/8JbiV4s8fkuz43"
        <nul set /p="IyABIIT9LFVSCfJx35Td+x9/VnQ3wHBubmpz8whCRf4wyTle5RlRyDUwOdNMCgg4tt6yAlOWvbQBabcc0hfFbgPP3n+86vX4Jz69au/vvzH66n9tzkawXnQ4RxbaS90AHYg+1piZhmXYMxvHRcuCj17BDHnIH9HjNEGvzFOv5MNUaxBDitA1ZhVTkssHFL24gq84sn5DkLAwfnysiTnDdweyZHyWyaIbocYzQ1uj+s5OZljL0v8u+XaZYEAYruwK36Fs3dN03L2V1xEFQXpIaCDKfTLz8+fvjx6xkNJhZnErLyoyo0MOMLXYZswgvMttmg6Pd2Cmz44MpJbKEfQTxc1bPGL9q0Qa87NMAnu3HTaLpoN+D9SIqM1BjBANA+o/VcLQNnKeTxzl1Nm6aVTg+7grpBWSKuLRQ2RIlePhlz4RdNql1Kr3p8TVrXjB91yS8RyyCDEW5xHD2wgB405eueZ6d1gRJdyhh2fVcvGiRJPk0pFx6SIM9L/t/ff3s/DJO7YsejD+TwDsEFhmzDyLs357LK8amkU1EoLqECUhmH/HNzlBxKVMa9PMaxj48zckOUbs2O+MzuLzQNMoxri4ZkWZ99lCUw8FjS0f0fodVDs+55iSn+d6CeYCa9/yZNqY1ehRyoRH/KXdHzIKPubOZSdz07K9fJzrMjnWJHPsSKfY0V6YkUogGK7qS0w0VEFPhRm3a6fYIq4HyEMeKQDGaZo/ICUWKPstwTKhv7USBX6EFOQm5PdGQDlTMHb0pwVj+p2hSix6zCUo9ws5pYRfkmHDdmVa0Nz8RAEHDr54rmEIvSMSLn4dvwXlGXWk5eSPmHqPnKLgo2HjOAY01GaxVGXrapJuQFLpVyV2Yyggi+Dj4OvSvE/nkIiP9jAyKkFiuqSG4xzpqLwW78zLZRX7cJILXOOuKJwD4CfWsz1t/xavjc/jaAcCfwDeL2dg0QkiTpfl2fzdbMa0f0MDGFwQ3jhgYGuMMVpYchMCXUD91aK1Wi97Zkc6qYYlH14X7tEHz4w4/RHvZryJwCjuZgiiCph3Pgn+1c/PXQTUNXMlTLch60aGdKV+97YHRWji9HzZB45v35/LYRQKHJb4IsUBgJxzL3MXdqhbAxVO1vDocVeeR/yk5bQyBCVibWYADsV4wQHKOtx/0wC9FevPZz0z2G1x+VFDYYRZHPaf+EmgteBcwZ5Me3BKza4gpxA1PSUkI8FL61uLToU3LzM5rSUCw6eAhknWfLgwjGQCrYL6wxCTWb5YG73TlTorEM4QadLcMemHinbKLtmOb8AN5/ppkGxU5hPrO/smwfHgau9VIkh53Bbhu/hxAI/qfuoUsbNHqqKia//FBKFWb1jbNL41U+vcKCHAec0/B7vCgP/75hhGEOKaeJYX0064FICHXiPBga/ITTti6B5hF58OmCC18AcHBs/DDT4/vNTkIvobOEM3SPOeAwgCGN9tgUa7rOEJxRVmtxBCr/wcKjbT/WJx6pLVg87Eo4lg6HRdiKpj1oAzWCcuHZaAoD/u3oxNyuwcINEFZj5jDr8BThMU49Y/1iEUWHYuXEQSIFjx1VMmzVVUGi+3O9DONJjPAiZgQ4xdbjie+hlgFIv/J7EWyaPLIx8W01liON7CIbngyOYEeedFHdpExTrndfPT8M5XZ8m1yLdtyni9BJiQd7h7SFbNBs5dLaE4HK6Lm20vN/xU1sDCv68Ps37F52pKmaQGOhgkv1IfV7NYvh92244bTdkgZoDQA9GfVoILPSeWwIE4rq0Wv5+/ol8rp0X4z4cCeihx6dDJLI3BgyrwWhVmEdrZn7EcKfmS7i7urRkjKR4SCe8gv9tuILPcjcpya2W62BveUy1bLqYMRoSaz6UulgsLXe7RZadN14bKaJK0sFgRq8F+Tdu2+iGH5XshXXPgVJ+Syz408E1d14x/JBd2xpBpgZNeXYBQBGOJ8CCKLlLG9bOyuR94sn0YKFiEepUONiZQYfrN0sYkDjRJkkl1KwKS+nTGHFrUXcRIJA5ypaoK7I7fSkZKKo1NCEBO4u6GJLAjriqhmcUkoLvEJGV5y78jxd6iFX4irxb55k+CY8VpVM163kFY+FlY/nSnrZLJ3VQWKJAorDigOjMrH5z0Nb1jhwkD5cZJ1sXdPNEIFdHFo6UgcLSTAJ9vjggMhaqHzw5ANpG14eA51WvVQP23y29uZecMsG/1XS3252pJ/gK7QnhHnhwlzus/TU8+N+xtartRyAa8O6txhWda+iEjUHzNke1nFj8uLZw1u3f3m7JHMpOyFLdvx//2KzDzdi0q2MnpqzO6JWv0ZVBiVnCPkVXKtyX4eLUggu7w+4zK0fR+iIrRycjcM+bGn6mNXsukOpNxUCR1LhytZYzRD+7LFt9bCREJueN79EYZ0dobqIdCjk6W9L6Bb0pdwXDqCIOVniYRicR9HGAKH1kONAWuy+wgCxZiE5APTMFCr6ZfPUfftoo+TAs92DS59Ic1Cb/HIMSdVUMIfV8lu9Sz8ENV5TaRh3IAQ/8hqbO7ysfsr55Mw5fdQcVe1s1DNW1tOAD+SVdp+h9gMHFN+rZRG/pHXEfXTX1E6N9BvC8ISKDt1QRAARRhVO9xLghUtnDXgm7cZsSnviikJ4fZQ96V+bTBmIbt1W4PGf8vPt63XfPzKV4v1h4YmTQH2HNJ/Bwz2qxbH+dtP7CSsk6uUOtatyewYF/xvd0XHfkl26BwoIlz/GdcMlGwOUShBXdHhTVZXVJ+xxdgsFuBwckNp/yrKgwaZ//xRdOEjnkDvKTx6XoxMOBd0yGx8gLsFLkvy3D3NNMBP7y5EW0DSCLk+AUffs9B8nR5loktMeUhu3GKCxZjV/AwXxe2TN5x6zA1MfBnHDZ/8It6jGYG9tEh988RW/eLH9po9VoDrOdnGwlEAv3MT4GtloZL+Dv7mheExoPYQGJ0m03/qE6NcQA+WAmR0L1jxoeeO0fxlT8HXywAfOjkfgFqcxHSnU+HPYMq5L/147OhyDlGJls2/6rH41lvvOMCuo76PjI1KvZCbe4QT0fqE1tvuM2lpkvaduae5VHOyhKCrVtJo6D0bXSftc7P9FDDK2L4TTd2Dd7ym9HoH+JsKdwWD8HHnYuFQlM3GPdng6k8LU+Cn0wcz/c3vslzZG7Skbsu1f6vu7uN/FNPUHVu73jEQ6Sz2CyExvwn/2KKRDNXeoMkCmb7UbRRFW9OhlvNMUTgLssF1f/LUIFVGP+zZwxx64WlX90FjxcrYky3YezThXHVo+xvBsJUG89Xs6fuuOlVdpzMQy5I8BYQ9dfGWFp1ggRo0CHrSBmkKZ04ydqoT+LzX4pSvKSUGQdgi8e5ihDi2PNo9LRkg4OsD1BB3WkOlSreV6dbM+K+AY7eCWpjAyn+XXAirlEfMjhLGHRcfFkqgb2OuAklEAd/Rx2o2C4l1mhtTtDry4bpIyOQ+WJmaPj0L2oJE/kCfihmJ3NMS4+pIqeZCV1WVD8KSpaFWJtXSL+enO64VzRcC8fZ38VjztMf2FoYuY0QsWTOcEJc0JrRpnhqGRmUFuBRu+eE4VdA2angLDwwS6DfToYDH4t1+C4M8meLWcI942eaJ1qNKt9zKPBzam/fzF7+XqzBTd6MJfoPu7UzclmRu6A7r7MBsk55WlA8j+yLxgemKHBRJ3YwQdmUgqwZOvmLyfNatyilLEzVZp6AURRcMPxSbsC7asZKIHToDVrrtla8KI8G5t+HDqYSAvHQ35WcrUaMhiLGrnd9xMfIl6MaU1bk+Gp8wRgLtx07R7/3tTLwi+lrWjlZjG1Jn6V6ZkOH97bgUbXliVakXMh3UdR3yRJosiwffmuoiWyxpHOzS6V0/VEa0wuQV1FGbl+rQbs5Uii9yqDvJqUbMqCNhfV+1m12oDkUVTmNQzo4spcjlo5zZ6PMjLXEOI5ODJ7F2hAUpCBGukdE7VLuKm1CIdZLzF8Z8lI6uMD33J1WQ0YiEGSHuD1HMGc6TIGuwjvBuCeCnMIb+jW+VJvbt4+i5r0DYLBAT13ZxdEadQ3Mr6bOOARcRCfqMoib+KF1gzbUTcdJJplynksyZlgFKgN8VHItLngFOPTk8gUIXD3TtFzmD1IfrEgu+tYLZeuT4M7gdJqoa9P99kpJBTpxMJ1qT/GVkIJ7qN03iDeE3AkIFnYfAHT7AS8hyDZWwm5iEBJc7Yt13MzKGewXDaC8S0K9jRtMz6FYuDNVw+O3zw41jcBT+kf/Qmbq6xs2fdZTHmcQAjUf4bpXi18WSIQHl1NuoErTQvegUlQuz98tKV/xHpX+5DtYrvq53c0Nihj2ydnT+j1gekYm+FHWABAkuRdPHQ4Y+lYoK6jjboQRYIh6H+0ftjRCY+cVlxPxPl8JIdGs7NZOywI0z/g1MD3nbublHc+/egueLDXjLrFbIp1IZ9WNyScaj6tJRldUUFj4I6U4qU5fmyYg1RncLvIWdeQDyfyXV6a9yt8n4NOf5Qg8WS72YCnRn6CP1xpJsGPu4qb3RW8yZ9Yv1GPjSKf03tT/n6y/PPlaku2G/N3UDmUp+ddpV805lACnQAfTMLOLvJzeA+dsAsFgtu9NYWXy2cXiA+Z4AAoYOfdUDRR9Q1FX5tjcHLQuSgck9dhafHjHR+ZH1DY/JWn+g1fBEMeFE6yvFthBALt6G/48Aze5/YOq8jU5+P6HFPpdDTcThv4Kmw+OTmP/2tdg+PSmfmrozS+StXPFF6YiusnzXtD5bR+X0VkCn68G4l3J837xMzHx7tRuEhTuLiBws9mYv8DL73p3izypfkCblHhcAqB7WLRNxSGgPmiYxhe1eAZlLc16G2Tw4Cvevj/1Qhl2JPzU/AITVVPL9LM29KX+CPRf/wiKE5O8WMLCWUo2KOpIlKopwGFdjEHX/1yPu9eRiS+5/Ow87jsSbm+oaz5oqPsxQ2FYeJ0F66rS4gYgFnHP72eK9zjdKsvVme0/uhHatquOtcfRDyMXyMObw6/864W4MugBe4C0Tt2PQO3rcfTm0ata+Cg7Ltmg32f048U94W8SxeHhJJUHn6lpry8SrCOQvFE9nv81zTY9Vly2k3/fpLGebkSAuZnLP3sm9QYAhVz9rm5E81HKQ4QucdUj3+nJ0DBLxOlYWKc9B55ePZ0d4Emcb9vAkYkPjg3y54TL1lxyHEy6XYZ31UTNh5M7UJ6TIfhXGavflJWGnQHhFuOMNLhfmnTbTp/EqCvAKLT3oxLDGBts6pGrR/UfuTZbDIJdUAVQBa6sXp+n+LWKFkZlVYZtTgQiGqVmspsLe7ittU2S5uiDpH4GOKKWa4lRkLr2UC5gkHEkvPxqtpob9Is7buJrqV0/zAU3rFPWqOTxC7qZeUT8kd3kh01lFJwCQ5/G6Xyk8AZm9iWVarOaqcVkwBTgJnr3jE6hoSzWeeTpU7oYCfFIT6PNF7KbevNMVrpfb7J0RqLxi5d91TjWVd5KZl4QOdIfnkyv2imir8T600JPwkJOOsJdv2UHgrjSl/htOrgveK+K7xyXxrZmcV+kdQg/eWB72NPamo/GiTszummPFOadVrm+QaPzCgRMZ3gkvStmKZY1khEqWxjQmJj7qF2lDAy3uOJAQHe0P3YxfVmJHH06Jto2yQux2DWvbosr260HzBz3mvhUPdhpPkEQ1iVfTP+5utvxw8nSk7RKmXol5Iu4DMEJiE1NMyQpcsxL7pxhEPTVgIIBG3+KK8kxWe5GUcLYHpyheMNE73AJOE6hYqZJ/iMZgeGG3QrXzFGj+nmQdGc1L/5DcXZoIQFh0PSTLknoIUQvo9110ZSXR54rcOHesGYUcNnOZuwqEI2JywtEa8qsMw5w6aL6sMRANMe2iVowiFiSYZ3GXCitQMMk/CsYUGp9zXxv6epCYMtPIzjrGFgOlxUYIPMNuutiJtm0I4469mpv4AxRZ3ZtSmLuVhoKRUa6PFNo9uVWQ4AKgC22RnMLQQFMRtwM/L20UTfo2DAKGGW2yekNVrb5Ky8U8H5msKNqVZoUzszlxnJgeYZnBCwIL2HtwJ1wkYmrMrUDdu4oiC7OnUPxS+O4lg6eTCtl1Ni2uIKptYLZR9oK6UHDidd4hPyWY/Wnm6VPAwVtoH9ZCJYIYizwwcIbeOTTobJRp2IOZsl229kkq8u6marTktV2daLq9B5LGQd7Sj3j7tDiqJulbRlUYeumlURKitRh91V53dRn/Gbu+eivU3LonkQ0kzPgtDHdF+OiXr/dNqfd1mRYPPdKMsq5KAOTARgww/tZGmHPvjMHldS9rCDSK1fj7JCVvTU/DcEjmDbAsTNqogamFBu1yITQvui5uc7/iat8hY0zzr5Fp2vd5hJQgUMxDHjBzeMHJ0mCyQyItOkdAwcSszm5vXoMIq0ef3y6OXEbC5b9PZA5xGKpSJDum9ZNyRzmbo/eBHEfE4x4sZIfr4V8f3Egrp43+Nc8574Mi4gTlJcpj/AM0FH1Ag2RhXQIRCORpuFRnNQdGaz7fl2gZisiDxGTCu6Tppv1xAQbU0ZfIxwCJnsiWHuGi6jtSFUpPeZsfmj/UlcVm7ITaFe8JFEPxHekg+nMMbJF3zkine4M0pWRRucF92qmLes48qKpt0kCi9N9VfntoAAfBjVQ81NL6+QY5FSlk13fmNeY6ssbiFclxxOO2pLj7irzI7DKHvDFR73V8hDsG/rwqE09R7v2laYFh9dL8kPv9JdBNpHjW5qHIa3GbFOZ4x95tNHTKiOVQFnl8PD3n2lq3FvHh7bXmIOD5IE0uNydz3/Eevl7hdMJ4dFR/enllb3xbRjIPoW4s4byO1W7kdOqNt2H1mUOoTCnr2yz7L9Eydzt1/XHQrSnt0zfV6+XZPV4eBXVooiIFhbny150rQCdxjcMkU3aTWTCHmTPQEMjbNt1eqDCyNQ2Juk0zdKnixP0Vm9rwmyit0+wZ+cfF+t9lgf3C7KeoHuyJ5GGW8CmAIPEC4L7wDNfRMGTdl7Rvjhmxrujt63mEUg9d2D44P0fheKFXL8tLeM/jtyR2WPjg9SO2yd/dthdj+9LnoamX2V0fX5y4TvafdKsxS1cvng4KYlYfhPbgnJE007jHXOm8vGzUacgoYL6VBwxD8vHegMzE49aeZzNpkgrBH6OX8zfpRtV5clXiFAXT0DFFj0X10typlZGzEYRpu9JUykt0GQMgQGIcgw+FE1S20yIb0yL8gFYdHJib9hM01DODlvy/YtXTuzt4ajt9ZFuXaceL7fLvCFyqLRRdTgQYiKaSURxch8wljTfJq7i2nDmQddc8/MEfIjX1dmPbbQxHKRQaT/VUa+bUrhRApL0TRBloe2AS/C6pK/pQggb2SEvjKUUPyLNN0nGqiv6o1HCugPynZgv1+RXj8yRMFIXlaLxUGs0ALLxSRG25EucOAStpICes4IHYC6Xjbbs3fDznoj/N5qVpLDOUNtCZarWIRERuJak9D3MSqFcRjLJSQ4aU1fB5QvMaSgu/1wjce5H4ov1DUHa3dy4+q2G15oYQoOfwXbgFRnD49jRYQNX9A8swrBwn/gLBxJG3GAYpVhJIbuo8j7PgsZ3aGNrF+5P8rupJlpEQtBClcgGTBEh9USONn9rdhbEQz2nfTaRDgN7+beOao8BbAE+MTr4HfbvGH3AYwKuptJqhu6D16kJEt0CII8INgLNZTGekxWcsS+RvTi7fpEGVpbNuoN2gRFUxMoiwA0Bboa4+jIMFsvT6rNJVrAbajeZoCJACBAJDVcjUzBenmLbbRrdnV2z11MOyXmynZHKZeSIR2HsLsRIfpcETWwbFX7yvb/pvDYoZG8/MEgF4wQbRW0kZ6SrGh4U5VRu0VL9WDcrpUfN4z/H4Rj2AmfReM/Y1YFQYuxiEsc08QxB7Ar7VkXIfrxWLtaNxDg5psxwExarT0U2ATKW0o2ZoQmmVqA5mKnpcUNl/8OGRP007FvxWOUaRdIMrWiH3IdraeRgZxLJFgexQ8BFicAc4hiQsgXEDIqegEt7AbYDfLQViuL1QnRv6bLXXF2NzEtzr0ALHt/hfr0PR/v+PhQmxn7NdgBuFSBxR8GtgDqLx8OALLFWFZ3wAolrvsAQj1VSOArw2x1hk6bjiyGwx5cF8RDBuguQzCENggVHrHWErKwrDeZFzoLKna6cHt3m+SluwxMzATgsl9jck1pEkbm4YfK7enQR9"
        <nul set /p="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"
        <nul set /p="u7Gb9wjUy260GVHMEA1EYgb3pDP65Dz2LieaEm4Ne/jbVHUO15/DPJ4YcU9X1cbL/RTmBqbbrC50WCv1A6OqL86Hjpt1L1LFt2S7oWyhzcJgIJ6u9j8HeRyHicRcvF/XyRm4PI/0IKmY3hDDW65uLct6FyoWe+WasZozJyOYZft5R9EhU7ewG/yWUbAkMReCYEM0Ax/Yy+H1y+B2mfFciSOd4oUldQahrctLDDEBhgFBItHXjXVh1RwGSBGVANDTycANbCjoX8zxhm9fPotN+KBfgvLMArPiIYhRiL7QPGtenSA8MAWifBSw8d0QBGbO7QCQaFYRtU99sM4Gij/Yd9U0L5W2HaMTeSS4eJKyc5saIF/hgn9K2K7xu6MYoKKGJtJyaUBh2JpjOPdpUFQWIl6KgMbHSgtADyFqBxTBSYVL4ZkxRsfv4v1vH0aopqJZvHLU4ukif7fQLBJoVsdt9gLQHtV7Supnaaj+20zMhPpwdAWuC3w9aTxDi1Afsgw8qzploQXkXNcm3YkFbmHDTHgFd2S/6xMO6whAAvkWRRI0993TfjK3utI615UB1B0LgpLhsIGCH1hmi6giN/jpvikuVuhTil/Ee/g9aBtMsbdIYQ8P5N4m9pRUprCWqRdeM8GSnTQ20m8zLGiOwhGLpCKY8g1cghBGeu2a38Tv/xjShrawvs20Z08yCfoxGTvvmTdnmZajrKywBZ05+n7UAuOxJG3UTxoJUENJy0yZmclrzpm0wmYC5BuxJg9j5fEHPF57HA359oD0XRwExqHCSP34xDuKA7vLgT21dXorXIAIXUjNMgEEfavJpuk5Uvg+CDdEA9xkXCS7ezLzEd5qqynnMVteldldyp4XFwqNuxBHn41LHTj0nV3sWdV5hC+osUc3SvkpgoyqrtFpPndW5HnsrltfFf9CtxgY/LnLKpWYBK4ugbQHSAgMeb8XRgfBplrV9Ld2dwdShaRO3rQVGEc0bAijTy0ap5DR0Tv4XpSzd+vuIrV6cAcV+q6UOgAMyeUpmrCSzZ3Hi7msHDa2rHU+d3BWZ2b3aZLIR+HcDi1uN0WfJYRL8cUnHSTC2s6y4rUoMYMzkWX43uMnTRS2vi8Agj15DeAVpuARJs5RsieiZOm+6QRbUG85O0PjdNMu27AfP2pKuI/rSUt7XG6p2Op3pBLT5h1OyaK6nzjbAE28r8DVLdgWa58X/Aw=="
    )

    set "OFFSET="
)

call :pwsh_exp "!decm1.%LNG%!..." "%decompcab%"
if not exist "%decompcab%" (
	call :elog "%NOK%" "!FCREATE.%LNG%! %YEL%decomp.cab.%RES%. !UNACONT.%LNG%!"
    call :elog .
	pause>nul|set/p=.			!ANYKEY.%LNG%!...
	call :exitn 3
) else (
	call :elog "%OK%"
)

call :elog .
call :elog "!decm3.%LNG%!"
call :choiceEx "!ENTERYN.%LNG%! " "OSJYN" "N" "%CTIME%" "-rawMsg"
if errorlevel 5 (
	set "owrpy=n"
	call :elog "    %YEL%!decm4.%LNG%!%RES%"
) else (
	set "owrpy=y"
	call :elog "    %YEL%!decm5.%LNG%!%RES%"
)

call :DisplayVars "RPYC 反编译阶段"
call :elog .

:: Once converted, extract the cab file. Needs to be a cab file due to expand.exe
set "found=0"
call :elog -n "%EMPTY%" "!decm6.%LNG%!..."
<nul set /p=!decm6.%LNG%!
mkdir "%decompilerdir%" %DEBUGREDIR%
expand -F:* "%decompcab%" "%decompilerdir%" %DEBUGREDIR%
move /y "%decompilerdir%\unrpyc.py" "%unrpycpy%" %DEBUGREDIR%
move /y "%decompilerdir%\deobfuscate.py" "%deobfuscate%" %DEBUGREDIR%
if not exist "%unrpycpy%" (
    call :elog "%NOK%" "!decm7.%LNG%! %YEL%%unrpycpy%%RES%. !UNACONT.%LNG%!%RES%"
    call :elog .
    pause>nul|set/p=.			!ANYKEY.%LNG%!...
    exit
) else (
    set "found=1"
)
if not exist "%deobfuscate%" (
    call :elog "%NOK%" "!decm7.%LNG%! %YEL%%deobfuscate%%RES%. !UNACONT.%LNG%!%RES%"
    call :elog .
    pause>nul|set/p=.			!ANYKEY.%LNG%!...
    exit
) else (
    if defined found (
        call :elog "%OK%"
    )
)

:: Decompile rpyc files
call :elog .
call :elog .
call :elog "!decm8.%LNG%!..."

set "prevDir="
for /R "game" %%f in (*.rpyc) do (
    set "currDir=%%~dpf"
    set "error=0"
    set "rpycname=%%~nf"
	set "rpyfile=%%~dpnf.rpy"
	set "relativerpy=!rpyfile:%WORKDIR%\game\=!"
	set "relativePath=%%f"
	set "relativePath=!relativePath:%WORKDIR%\game\=!"
    set "size=%%~zf"

    if not "!prevDir!" == "!currDir!" (
        call :elog .
        call :elog "!MTITLE.%LNG%! %YEL%!currDir!%RES%"
        set "prevDir=!currDir!"
    )

	if not exist !rpyfile! (
		call :elog -n "%EMPTY%" "!decm9.%LNG%! %YEL%!rpycname!.rpyc%RES% - %YEL%!size!%RES% !UNIT.%LNG%!"
		if "%OPTION%" == "4" (
			if %DEBUGLEVEL% GEQ 1 echo "%PYTHONEXE%" %PYVERSION% %PYTHONSYSTEM% "%unrpycpy%" %OFFSET% --try-harder "%%f" >>"%UNRENLOG%"
			"%PYTHONEXE%" %PYVERSION% %PYTHONSYSTEM% "%unrpycpy%" %OFFSET% --try-harder "%%f" >>"%UNRENLOG%" 2>&1
			set "error=!errorlevel!"
		) else (
			if %DEBUGLEVEL% GEQ 1 echo "%PYTHONEXE%" %PYVERSION% %PYTHONSYSTEM% "%unrpycpy%" %OFFSET% "%%f" >>"%UNRENLOG%"
			"%PYTHONEXE%" %PYVERSION% %PYTHONSYSTEM% "%unrpycpy%" %OFFSET% "%%f" >>"%UNRENLOG%" 2>&1
			set "error=!errorlevel!"
		)
        if !error! NEQ 0 (
            call :elog "%NOK%" "!LOGCHK.%LNG%!"
        ) else (
            call :elog "%OK%"
        )
	) else if exist !rpyfile! if "%owrpy%" == "y" (
		if not exist "!rpyfile!.org" (
            call :elog -n "%EMPTY%" "!decm10.%LNG%! %YEL%!rpycname!.rpy%RES% !decm10a.%LNG%! %YEL%!rpycname!.rpy.org%RES%"
			copy /y "!rpyfile!" "!rpyfile!.org" %DEBUGREDIR%
            if !errorlevel! NEQ 0 (
                call :elog "%NOK%" "!LOGCHK.%LNG%!"
            ) else (
                call :elog "%OK%"
            )
        ) else if exist !rpyfile! if "%owrpy%" == "n" (
            call :elog "%SKIP%"
		)

		call :elog -n "%EMPTY%" "!decm11.%LNG%! %YEL%!rpycname!.rpy%RES%"
		if "%OPTION%" == "4" (
			if %DEBUGLEVEL% GEQ 1 echo "%PYTHONEXE%" %PYVERSION% %PYTHONSYSTEM% "%unrpycpy%" --clobber %OFFSET% --try-harder "%%f" >>"%UNRENLOG%"
			"%PYTHONEXE%" %PYVERSION% %PYTHONSYSTEM% "%unrpycpy%" --clobber %OFFSET% --try-harder "%%f" >>"%UNRENLOG%" 2>&1
			set "error=!errorlevel!"
		) else (
			if %DEBUGLEVEL% GEQ 1 echo "%PYTHONEXE%" %PYVERSION% %PYTHONSYSTEM% "%unrpycpy%" --clobber %OFFSET% "%%f" >>"%UNRENLOG%"
			"%PYTHONEXE%" %PYVERSION% %PYTHONSYSTEM% "%unrpycpy%" --clobber %OFFSET% "%%f" >>"%UNRENLOG%" 2>&1
			set "error=!errorlevel!"
		)
        if !error! NEQ 0 (
            call :elog "%NOK%" "!LOGCHK.%LNG%!"
        ) else (
            call :elog "%OK%"
        )
	) else (
        call :elog "%SKIP%" "!decm9.%LNG%! %YEL%!rpycname!.rpyc%RES% - %YEL%!size!%RES% !UNIT.%LNG%!"
    )

)

:: Clean up
call :elog .
call :elog -n "%EMPTY%" "!CLEANUP.%LNG%!..."

setlocal disabledelayedexpansion
for /f "delims=" %%A in ("%WORKDIR%") do (
    endlocal
    cd /d "%%A"
)
set "error=0"
if not "%unrpycpy%" == "" if exist "%unrpycpy%" (
    del /f /q "%unrpycpy%" %DEBUGREDIR%
    set /a error=!errorlevel!
    if exist "%unrpycpy%c" del /f /q "%unrpycpy%c" %DEBUGREDIR%
    set /a error=!error!+!errorlevel!
    if exist "%unrpycpy%o" del /f /q "%unrpycpy%o" %DEBUGREDIR%
    set /a error=!error!+!errorlevel!
)
if not "%decompcab%" == "" if exist "%decompcab%" (
    del /f /q "%decompcab%" %DEBUGREDIR%
    set /a error=!error!+!errorlevel!
)
if not "%deobfuscate%" == "" if exist "%deobfuscate%" (
    del /f /q "%deobfuscate%" %DEBUGREDIR%
    set /a error=!error!+!errorlevel!
    if exist "%deobfuscate%c" del /f /q "%deobfuscate%c" %DEBUGREDIR%
    set /a error=!error!+!errorlevel!
    if exist "%deobfuscate%o" del /f /q "%deobfuscate%o" %DEBUGREDIR%
    set /a error=!error!+!errorlevel!
)
if exist "__pycache__" rmdir /q /s "__pycache__" %DEBUGREDIR%
set /a error=!error!+!errorlevel!
if not "%decompilerdir%" == "" if exist "%decompilerdir%" (
    rmdir /q /s "%decompilerdir%" %DEBUGREDIR%
    set /a error=!error!+!errorlevel!
)

if !error! NEQ 0 (
    call :elog "%NOK%" "!LOGCHK.%LNG%!"
) else (
    call :elog "%OK%"
)
timeout /T 1 %DEBUGREDIR%
goto :eof


:: Drop our console/dev mode enabler into the game folder
:console
set "unren-console=%WORKDIR%\game\unren-console.rpy"

call :elog .
call :elog "!TWADD.%LNG%! %YEL%%unren-console%.%RES%"
call :elog .
call :elog "!INCASEDEL.%LNG%!"
call :elog "%YEL%%unren-console%%RES%"
call :elog "%YEL%%unren-console%c%RES%"

if exist "%unren-console%" (
    call :elog .
    call :elog "%SKIP%" "!APRESENT.%LNG%!"
    call :elog .
) else (
    >"%unren-console%.b64" (
        <nul set /p="IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KZGVmaW5lIDk5OSBjb25maWcuY29uc29sZSA9IFRydWUNCmRlZmluZSA5OTkgY29uZmlnLmRldmVsb3BlciA9IFRydWUNCg=="
    )
    call :elog .
    call :pwsh_exp "!choicea.%LNG%!.." "%unren-console%"
    if not exist "!unren-console!" (
        call :elog "%NOK%" "!FCREATE.%LNG%! %YEL%%unren-console%%RES%"
        call :elog .
    ) else (
        call :elog "%OK%"
    )
)
timeout /T 1 %DEBUGREDIR%
goto :eof


:: Drop our debug mode enabler into the game folder
:debug
set "unren-debug=%WORKDIR%\game\unren-debug.rpy"

call :elog .
call :elog "!TWADD.%LNG%! %YEL%%unren-debug%.%RES%"
call :elog .
call :elog "!INCASEDEL.%LNG%!%RES%"
call :elog "%YEL%%unren-debug%%RES%"
call :elog "%YEL%%unren-debug%c%RES%"

if exist "%unren-debug%" (
    call :elog .
    call :elog "%SKIP%" "!APRESENT.%LNG%!%RES%"
    call :elog .
) else (
    >"%unren-debug%.b64" (
        <nul set /p="IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KZGVmaW5lIDk5OSBjb25maWcuZGVidWcgPSBUcnVlDQo="
    )
    call :elog .
    call :pwsh_exp "!choiceb.%LNG%!.." "%unren-debug%"
    if not exist "%unren-debug%" (
        call :elog "%NOK%" "!FCREATE.%LNG%! %YEL%%unren-debug%%RES%"
        call :elog .
    ) else (
        call :elog "%OK%"
    )
)
timeout /T 1 %DEBUGREDIR%
goto :eof


:: Drop our skip file into the game folder
:skip
set "unren-skip=%WORKDIR%\game\unren-skip.rpy"

call :elog .
call :elog "!TWADD.%LNG%! %YEL%%unren-skip%.%RES%"
call :elog .
call :elog "!INCASEDEL.%LNG%!%RES%"
call :elog "%YEL%%unren-skip%%RES%"
call :elog "%YEL%%unren-skip%c%RES%"

if exist "%unren-skip%" (
    call :elog .
    call :elog "%SKIP%" "!APRESENT.%LNG%!%RES%"
    call :elog .
) else (
    >"%unren-skip%.b64" (
        <nul set /p="IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KaW5pdCA5OTkgcHl0aG9uOg0KDQogICAgIyBNYW5kYXRvcnkNCiAgICBfcHJlZmVyZW5jZXMuYWxsb3dfc2tpcHBpbmcgPSBUcnVlDQogICAgcmVucHkuY29uZmlnLmFsbG93X3NraXBwaW5nID0gVHJ1ZQ0KDQogICAgdHJ5Og0KICAgICAgICBjb25maWcua2V5bWFwWydza2lwJ10gPSBbICdLX0xDVFJMJywgJ0tfUkNUUkwnIF0NCiAgICBleGNlcHQ6DQogICAgICAgIHBhc3MNCg0KICAgICMgVW5zZWVuIFRleHQNCiAgICBfcHJlZmVyZW5jZXMuc2tpcF91bnNlZW4gPSBUcnVlDQogICAgcmVucHkuZ2FtZS5wcmVmZXJlbmNlcy5za2lwX3Vuc2VlbiA9IFRydWUNCg0KICAgICMgQWZ0ZXIgQ2hvaWNlcw0KICAgIF9wcmVmZXJlbmNlcy5za2lwX2FmdGVyX2Nob2ljZXMgPSBUcnVlDQogICAgcmVucHkuZ2FtZS5wcmVmZXJlbmNlcy5za2lwX2FmdGVyX2Nob2ljZXMgPSBUcnVlDQoNCiAgICAjIEFsbG93IEZhc3Qgc2tpcHBpbmcNCiAgICByZW5weS5jb25maWcuZmFzdF9za2lwcGluZyA9IFRydWUNCg0KICAgICMgRnJvbSBKYXNvbjogQ29taW5nIG9mIGFnZQ0KICAgIHBlcnNpc3RlbnQuZ2FtZV9jb21wbGV0ZWQgPSBUcnVlDQo="
    )
    call :elog .
    call :pwsh_exp "!choicec.%LNG%!.."  "%unren-skip%"
    if not exist "%unren-skip%" (
        call :elog "%NOK%" "!FCREATE.%LNG%! %YEL%%unren-skip%%RES%"
        call :elog .
    ) else (
        call :elog "%OK%"
    )
)
timeout /T 1 %DEBUGREDIR%
goto :eof


:: Drop our skip file into the game folder
:skipall
set "unren-skipall=%WORKDIR%\game\unren-skipall.rpy"

call :elog .
call :elog "!TWADD.%LNG%! %YEL%%unren-skipall%.%RES%"
call :elog .
call :elog "!INCASEDEL.%LNG%!%RES%"
call :elog "%YEL%%unren-skipall%%RES%"
call :elog "%YEL%%unren-skipall%c%RES%"

if exist "%unren-skipall%" (
    call :elog .
    call :elog "%SKIP%" "!APRESENT.%LNG%!%RES%"
    call :elog .
) else (
    >"%unren-skipall%.b64" (
        <nul set /p="IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KaW5pdCA5OTkgcHl0aG9uOg0KDQogICAgIyBNYW5kYXRvcnkNCiAgICBfcHJlZmVyZW5jZXMuYWxsb3dfc2tpcHBpbmcgPSBUcnVlDQogICAgcmVucHkuY29uZmlnLmFsbG93X3NraXBwaW5nID0gVHJ1ZQ0KDQogICAgdHJ5Og0KICAgICAgICBjb25maWcua2V5bWFwWydza2lwJ10gPSBbICdLX0xDVFJMJywgJ0tfUkNUUkwnIF0NCiAgICBleGNlcHQ6DQogICAgICAgIHBhc3MNCg0KICAgICMgVW5zZWVuIFRleHQNCiAgICBfcHJlZmVyZW5jZXMuc2tpcF91bnNlZW4gPSBUcnVlDQogICAgcmVucHkuZ2FtZS5wcmVmZXJlbmNlcy5za2lwX3Vuc2VlbiA9IFRydWUNCg0KICAgICMgQWZ0ZXIgQ2hvaWNlcw0KICAgIF9wcmVmZXJlbmNlcy5za2lwX2FmdGVyX2Nob2ljZXMgPSBUcnVlDQogICAgcmVucHkuZ2FtZS5wcmVmZXJlbmNlcy5za2lwX2FmdGVyX2Nob2ljZXMgPSBUcnVlDQoNCiAgICAjIFRyYW5zaXRpb25zDQogICAgX3ByZWZlcmVuY2VzLnRyYW5zaXRpb25zID0gMA0KDQogICAgIyBBbGxvdyBGYXN0IHNraXBwaW5nDQogICAgcmVucHkuY29uZmlnLmZhc3Rfc2tpcHBpbmcgPSBUcnVlDQoNCiAgICAjIEZyb20gSmFzb246IENvbWluZyBvZiBhZ2UNCiAgICBwZXJzaXN0ZW50LmdhbWVfY29tcGxldGVkID0gVHJ1ZQ0K"
    )
    call :elog .
    call :pwsh_exp "!choiced.%LNG%!.." "%unren-skipall%"
    if not exist "%unren-skipall%" (
        call :elog "%NOK%" "!FCREATE.%LNG%! %YEL%%unren-skipall%%RES%"
        call :elog .
    ) else (
        call :elog "%OK%"
    )
)
timeout /T 1 %DEBUGREDIR%
goto :eof


:: Drop our rollback file into the game folder
:rollback
set "unren-rollback=%WORKDIR%\game\unren-rollback.rpy"

call :elog .
call :elog "!TWADD.%LNG%! %YEL%%unren-rollback%.%RES%"
call :elog .
call :elog "!INCASEDEL.%LNG%!%RES%"
call :elog "%YEL%%unren-rollback%%RES%"
call :elog "%YEL%%unren-rollback%c%RES%"

if exist "%unren-rollback%" (
    call :elog .
    call :elog "%SKIP%" "!APRESENT.%LNG%!%RES%"
    call :elog .
) else (
    >"%unren-rollback%.b64" (
        <nul set /p="IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KaW5pdCA5OTkgcHl0aG9uOg0KICAgIHJlbnB5LmNvbmZpZy5yb2xsYmFja19lbmFibGVkID0gVHJ1ZQ0KICAgIHJlbnB5LmNvbmZpZy5oYXJkX3JvbGxiYWNrX2xpbWl0ID0gMjU2DQogICAgcmVucHkuY29uZmlnLnJvbGxiYWNrX2xlbmd0aCA9IDI1Ng0KICAgIGRlZiB1bnJlbl9ub2Jsb2NrKCphcmdzLCAqKmt3YXJncyk6DQogICAgICAgIHJldHVybg0KICAgIHJlbnB5LmJsb2NrX3JvbGxiYWNrID0gdW5yZW5fbm9ibG9jaw0KICAgIHRyeToNCiAgICAgICAgY29uZmlnLmtleW1hcFsncm9sbGJhY2snXSA9IFsgJ0tfUEFHRVVQJywgJ3JlcGVhdF9LX1BBR0VVUCcsICdLX0FDX0JBQ0snLCAnbW91c2Vkb3duXzQnIF0NCiAgICBleGNlcHQ6DQogICAgICAgIHBhc3MNCg=="
    )
    call :elog .
    call :pwsh_exp "!choicee.%LNG%!.." "%unren-rollback%"
    if not exist "%unren-rollback%" (
        call :elog "%NOK%" "!FCREATE.%LNG%! %YEL%%unren-rollback%%RES%"
        call :elog .
    ) else (
        call :elog "%OK%"
    )
)
timeout /T 1 %DEBUGREDIR%
goto :eof


:: Drop our Quick Save/Load file into the game folder
:quick
set "unren-quick=%WORKDIR%\game\unren-quick.rpy"

call :elog .
call :elog "!TWADD.%LNG%! %YEL%%unren-quick%.%RES%"
call :elog .
call :elog "!INCASEDEL.%LNG%!%RES%"
call :elog "%YEL%%unren-quick%%RES%"
call :elog "%YEL%%unren-quick%c%RES%"

if exist "%unren-quick%" (
    call :elog .
    call :elog "%SKIP%" "!APRESENT.%LNG%!%RES%"
    call :elog .
) else (
    >"%unren-quick%.b64" (
        <nul set /p="IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KaW5pdCA5OTkgcHl0aG9uOg0KICAgIHRyeToNCiAgICAgICAgY29uZmlnLnVuZGVybGF5WzBdLmtleW1hcFsncXVpY2tTYXZlJ10gPSBRdWlja1NhdmUoKQ0KICAgICAgICBjb25maWcua2V5bWFwWydxdWlja1NhdmUnXSA9ICdLX0Y1Jw0KICAgICAgICBjb25maWcudW5kZXJsYXlbMF0ua2V5bWFwWydxdWlja0xvYWQnXSA9IFF1aWNrTG9hZCgpDQogICAgICAgIGNvbmZpZy5rZXltYXBbJ3F1aWNrTG9hZCddID0gJ0tfRjknDQogICAgZXhjZXB0Og0KICAgICAgICBwYXNzDQo="
    )
    call :elog .
    call :pwsh_exp "!choicef.%LNG%!.." "%unren-quick%"
    if not exist "%unren-quick%" (
        call :elog "%NOK%" "!FCREATE.%LNG%! %YEL%%unren-quick%%RES%"
        call :elog .
    ) else (
        call :elog "%OK%"
    )
)
timeout /T 1 %DEBUGREDIR%
goto :eof


:: Drop our Quick Menu file into the game folder
:qmenu
set "unren-qmenu=%WORKDIR%\game\unren-qmenu.rpy"

call :elog .
call :elog "!TWADD.%LNG%! %YEL%%unren-qmenu%.%RES%"
call :elog .
call :elog "!INCASEDEL.%LNG%!%RES%"
call :elog "%YEL%%unren-qmenu%%RES%"
call :elog "%YEL%%unren-qmenu%c%RES%"

if exist "%unren-qmenu%" (
    call :elog .
    call :elog "%SKIP%" "!APRESENT.%LNG%!%RES%"
    call :elog .
) else (
    >"%unren-qmenu%.b64" (
        <nul set /p="IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KaW5pdCBweXRob246DQogICAgZGVmIGFsd2F5c19lbmFibGVfcXVpY2tfbWVudSgpOg0KICAgICAgICBzdG9yZS5xdWlja19tZW51ID0gVHJ1ZQ0KICAgICAgICByZW5weS5zaG93X3NjcmVlbigicXVpY2tfbWVudSIpDQogICAgY29uZmlnLm92ZXJsYXlfZnVuY3Rpb25zLmFwcGVuZChhbHdheXNfZW5hYmxlX3F1aWNrX21lbnUpDQoNCiAgICBkZWYgZm9yY2VfcXVpY2tfbWVudV9vbl9pbnRlcmFjdCgpOg0KICAgICAgICBzdG9yZS5xdWlja19tZW51ID0gVHJ1ZQ0KICAgIGNvbmZpZy5pbnRlcmFjdF9jYWxsYmFja3MuYXBwZW5kKGZvcmNlX3F1aWNrX21lbnVfb25faW50ZXJhY3Qp"
    )
    call :elog .
    call :pwsh_exp "!choiceg.%LNG%!.." "%unren-qmenu%"
    if not exist "%unren-qmenu%" (
        call :elog "%NOK%" "!FCREATE.%LNG%! %YEL%%unren-qmenu%%RES%"
        call :elog .
    ) else (
        call :elog "%OK%"
    )
)
timeout /T 1 %DEBUGREDIR%
goto :eof


:: Add the Universal Gallery Unlocker to the game folder
:add_ugu
set "ugu_name=Universal_Gallery_Unlocker ZLZK"
set "url=https://attachments.f95zone.to/2024/01/3314515_Universal_Gallery_Unlocker_2024-01-24_ZLZK.zip"
set "uguzip=%TEMP%\Universal_Gallery_Unlocker.zip"
set "uguhardzip=%TEMP%\hard.zip"
set "ugusoftzip=%TEMP%\soft.zip"
set "ugudir=%WORKDIR%\game\_mods"

call :elog .
call :elog "!INCASEOF.%LNG%! %RES%"
call :elog "%MAG%https://f95zone.to/threads/universal-gallery-unlocker-2024-01-24-zlzk.136812/%RES%"
call :elog .
call :elog "!TWADD.%LNG%! %YEL%%ugudir%.%RES%"
call :elog .
call :elog "!INCASEDEL.%LNG%!%RES%"
call :elog "%YEL%%ugudir%\ZLZK_UGU_soft%RES%"
call :elog .
call :elog -n "%EMPTY%" "!choiceh.%LNG%!.."

if %DEBUGLEVEL% GEQ 1 echo "%PWRSHELL%" -NoProfile -Command "(New-Object System.Net.WebClient).DownloadFile('%url%','%uguzip%')" >> "%UNRENLOG%"
"%PWRSHELL%" -NoProfile -Command "(New-Object System.Net.WebClient).DownloadFile('%url%','%uguzip%')" %DEBUGREDIR%
if %errorlevel% NEQ 0 (
    call :elog "%NOK%" "!UNDWNLD.%LNG%! %MAG%%url%%RES%"
    call :elog .
    goto :skip_ugu

) else (
    if %DEBUGLEVEL% GEQ 1 echo "%PWRSHELL%" -NoProfile -Command "Expand-Archive -Force '%uguzip%' '%TEMP%'" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "Expand-Archive -Force '%uguzip%' '%TEMP%'" %DEBUGREDIR%
    if not exist "%uguhardzip%" (
        call :elog "%NOK%" "!FNOTFOUND.%LNG%! %YEL%%uguhardzip%%RES%"
        call :elog .
        goto :skip_ugu
    )
    if not exist "%ugusoftzip%" (
        call :elog "%NOK%" "!FNOTFOUND.%LNG%! %YEL%%ugusoftzip%%RES%"
        call :elog .
        goto :skip_ugu
    )
    if %DEBUGLEVEL% GEQ 1 echo "%PWRSHELL%" -NoProfile -Command "Expand-Archive -Force '%ugusoftzip%' '%WORKDIR%'" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "Expand-Archive -Force '%ugusoftzip%' '%WORKDIR%'" %DEBUGREDIR%
    if !errorlevel! NEQ 0 (
        call :elog "%NOK%" "!UNEXTRACT.%LNG%! %YEL%%ugusoftzip%%RES%"
        call :elog .
        goto :skip_ucd
    ) else (
        call :elog "%OK%"
    )
    del /f /q "%ugusoftzip%" %DEBUGREDIR%
    del /f /q "%uguhardzip%" %DEBUGREDIR%
    del /f /q "%uguzip%" %DEBUGREDIR%
    del /f /q "%TEMP%\readme.txt" %DEBUGREDIR%
)
timeout /T 1 %DEBUGREDIR%
goto :eof


:: Add the Universal Choice Descriptor to the game folder
:add_ucd
set "ucd_name=Universal_Choice_Descriptor ZLZK"
set "url=https://attachments.f95zone.to/2024/01/3314453_Universal_Choice_Descriptor.zip"
set "ucdzip=%TEMP%\Universal_Choice_Descriptor.zip"
set "ucdzip_part1=%TEMP%\Universal_Choice_Descriptor_[2024-01-24]_[ZLZK].zip"
set "ucdzip_part2=%TEMP%\ZLZK_[2024-01-24]_[ZLZK].zip"
set "ucddir=%WORKDIR%\game\_mods\"

call :elog .
call :elog "!INCASEOF.%LNG%!%RES%"
call :elog "%MAG%https://f95zone.to/threads/universal-gallery-unlocker-2024-01-24-zlzk.136812/%RES%"
call :elog .
call :elog "!TWADD.%LNG%! %YEL%%ucddir%.%RES%"
call :elog .
call :elog "!INCASEDEL.%LNG%!%RES%"
call :elog "%YEL%%ucddir%%RES%"
call :elog .
call :elog -n "%EMPTY%" "!choicei.%LNG%!.."

if %DEBUGLEVEL% GEQ 1 echo "%PWRSHELL%" -NoProfile -Command "(New-Object System.Net.WebClient).DownloadFile('%url%','%ucdzip%')" >> "%UNRENLOG%"
"%PWRSHELL%" -NoProfile -Command "(New-Object System.Net.WebClient).DownloadFile('%url%','%ucdzip%')" %DEBUGREDIR%
if not exist "%ucdzip%" (
	call :elog "%NOK%" "!UNDWNLD.%LNG%! %MAG%%url%%RES%"
    call :elog .
	goto :skip_ucd
) else (
    if %DEBUGLEVEL% GEQ 1 echo "%PWRSHELL%" -NoProfile -Command "Expand-Archive -Force '%ucdzip%' '%TEMP%'" >> "%UNRENLOG%"
	"%PWRSHELL%" -NoProfile -Command "Expand-Archive -Force '%ucdzip%' '%TEMP%'" %DEBUGREDIR%
    if not exist "%ucdzip_part1%" (
        call :elog "%NOK%" "!FNOTFOUND.%LNG%! %YEL%%ucdzip_part1%%RES%"
        call :elog .
        goto :skip_ucd
    ) else (
        move /y "%ucdzip_part1%" %TEMP%\part1.zip %DEBUGREDIR%
    )
    if not exist "%ucdzip_part2%" (
        call :elog "%NOK%" "!FNOTFOUND.%LNG%! %YEL%%ucdzip_part2%%RES%"
        call :elog .
        goto :skip_ucd
    ) else (
        move /y "%ucdzip_part2%" %TEMP%\part2.zip %DEBUGREDIR%
    )
    if %DEBUGLEVEL% GEQ 1 echo "%PWRSHELL%" -NoProfile -Command "Expand-Archive -Force '%TEMP%\part1.zip' '%WORKDIR%'" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "Expand-Archive -Force '%TEMP%\part1.zip' '%WORKDIR%'" %DEBUGREDIR%
    if !errorlevel! NEQ 0 (
        call :elog "%NOK%" "!UNEXTRACT.%LNG%! %YEL%%ucdzip_part1%%RES%"
        goto :skip_ucd
    )
    if %DEBUGLEVEL% GEQ 1 echo "%PWRSHELL%" -NoProfile -Command "Expand-Archive -Force '%TEMP%\part2.zip' '%WORKDIR%'" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "Expand-Archive -Force '%TEMP%\part2.zip' '%WORKDIR%'" %DEBUGREDIR%
    if !errorlevel! NEQ 0 (
        call :elog "%NOK%" "!UNEXTRACT.%LNG%! %YEL%%ucdzip_part2%%RES%"
        call :elog .
        goto :skip_ucd
    )
    call :elog "%OK%%"
    :skip_ucd
	del /f /q "%ucdzip%" %DEBUGREDIR%
    del /f /q "%ucdzip_part1%" %DEBUGREDIR%
    del /f /q "%TEMP%\part1.zip" %DEBUGREDIR%
    del /f /q "%ucdzip_part2%" %DEBUGREDIR%
    del /f /q "%TEMP%\part2.zip" %DEBUGREDIR%
    del /f /q "%TEMP%\readme.txt" %DEBUGREDIR%
)
timeout /T i %DEBUGREDIR%
goto :eof


:: Download and install Universal Transparent Text Box Mod by Penfold Mole
:add_utbox
set "utboxmsg.zh=检查7zip.exe的可用性。"

set "utbox_name=Universal Transparent Text Box Mod"
set "url=https://attachments.f95zone.to/2023/12/3214690_RenPy_universal_transparent_textbox_mod_v2.6.4_by_Penfold_Mole.7z"
set "utboxzip=%TEMP%\RenPy_Transparent_Text_Box_Mod.7z"
set "utbox_file=%WORKDIR%\game\y_outline.rpy"
set "utbox_tdir=%TEMP%\utbox"

call :elog -n "%EMPTY%" "!utboxmsg.%LNG%!.."
:: Need 7z.exe for extraction
if not exist "%_7ZIPLOC%" (
    call :elog "%NOK%" "!FNOTFOUND.%LNG%! %YEL%%_7ZIPLOC%%RES%"
    call :elog .
    timeout /T 1 %DEBUGREDIR%
    goto :skip_utbox
) else (
    call :elog "%OK%"
)

call :elog .
call :elog "!INCASEOF.%LNG%! %RES%"
call :elog "%MAG%https://f95zone.to/threads/renpy-transparent-text-box-mod-v2-6-4.11925/%RES%"
call :elog .
call :elog "!TWADD.%LNG%! %YEL%%utbox_file%.%RES%"
call :elog .
call :elog "!INCASEDEL.%LNG%!%RES%"
call :elog "%YEL%%utbox_file%%RES%"
call :elog .
call :elog -n "%EMPTY%" "!choicej.%LNG%!.."
if %DEBUGLEVEL% GEQ 1 echo "%PWRSHELL%" -NoProfile -Command "(New-Object System.Net.WebClient).DownloadFile('%url%','%utboxzip%')" >> "%UNRENLOG%"
"%PWRSHELL%" -NoProfile -Command "(New-Object System.Net.WebClient).DownloadFile('%url%','%utboxzip%')" %DEBUGREDIR%
if not exist "%utboxzip%" (
    call :elog "%NOK%" "!UNDWNLD.%LNG%! %MAG%%url%%RES%"
    call :elog .
    goto :skip_utbox
) else (
    if %DEBUGLEVEL% GEQ 1 echo "%_7ZIPLOC%" x -y -o"%utbox_tdir%" "%utboxzip%" >> "%UNRENLOG%"
    "%_7ZIPLOC%" x -y -o"%utbox_tdir%" "%utboxzip%" %DEBUGREDIR%
    if not exist "%utbox_tdir%\game\y_outline.rpy" (
        call :elog "%NOK%" "!UNEXTRACT.%LNG%! %YEL%%utboxzip%%RES%"
        call :elog .
        goto :skip_utbox
    ) else (
        move /y "%utbox_tdir%\game\y_outline.rpy" "%WORKDIR%\game" %DEBUGREDIR%
        if exist "%utbox_file%" (
            call :elog "%OK%"
        ) else (
            call :elog "%NOK%" "!FNOTFOUND.%LNG%! %YEL%%utbox_file%%RES%"
            call :elog .
        )
    )
)
:skip_utbox
if exist "%utboxzip%" if not %utboxzip% == "" (del /f /q "%utboxzip%" %DEBUGREDIR%)
if exist "%utbox_tdir%" if not %utbox_tdir% == "" (rd /s /q "%utbox_tdir%" %DEBUGREDIR%)

timeout /T 1 %DEBUGREDIR%
goto :eof


:: Download 0x52_URM and add to the game
:add_urm
set "urm_name=0x52_URM"
set "url=https://attachments.f95zone.to/2025/07/5028578_0x52_URM.zip"
set "urm_zip=%TEMP%\0x52_URM.zip"
set "urm_rpa=%WORKDIR%\game\0x52_URM.rpa"

call :elog .
call :elog "!INCASEOF.%LNG%! %RES%"
call :elog "%MAG%https://f95zone.to/threads/universal-renpy-mod-urm-2-6-2-mod-any-renpy-game-yourself.48025/%RES%"
call :elog .
call :elog "!TWADD.%LNG%! %YEL%%urm_rpa%.%RES%"
call :elog .
call :elog "!INCASEDEL.%LNG%!%RES%"
call :elog "%YEL%%urm_rpa%%RES%"
call :elog .
call :elog -n "%EMPTY%" "!choicek.%LNG%!.."

if %DEBUGLEVEL% GEQ 1 echo "%PWRSHELL%" -NoProfile -Command "(New-Object System.Net.WebClient).DownloadFile('%url%','%urm_zip%.tmp')" >> "%UNRENLOG%"
"%PWRSHELL%" -NoProfile -Command "(New-Object System.Net.WebClient).DownloadFile('%url%','%urm_zip%.tmp')" %DEBUGREDIR%
if not exist "%urm_zip%.tmp" (
	call :elog "%NOK%" "!UNDWNLD.%LNG%! %YEL%!urm_name!.zip.%RES%"
    call :elog .
    goto :skip_urm
) else (
    move /y "%urm_zip%.tmp" "%urm_zip%" %DEBUGREDIR%
    if %DEBUGLEVEL% GEQ 1 echo "%PWRSHELL%" -NoProfile -Command "Expand-Archive -Force '%urm_zip%' '%WORKDIR%\game'" >> "%UNRENLOG%"
	"%PWRSHELL%" -NoProfile -Command "Expand-Archive -Force '%urm_zip%' '%WORKDIR%\game'" %DEBUGREDIR%
	if !errorlevel! NEQ 0 (
		call :elog "%NOK%" "!FNOTFOUND.%LNG%! %YEL%!urm_name!%RES%"
        call :elog .
	) else (
		call :elog "%OK%"
	)
    :skip_urm
	del /f /q "%urm_zip%" %DEBUGREDIR%
)
timeout /T 1 %DEBUGREDIR%
goto :eof


:: Add a custom add-on
:add_custom_addon
set "download.zh=从 URL 或本地路径下载并安装自定义插件。"

set "custom_name.zh=自定义插件"

set "enter_url.zh=输入插件的 URL 或本地路径（zip、rar 或文件夹）："

call :elog .
call :elog "!TWADD.%LNG%! %YEL%%WORKDIR%\game\!custom_name.%LNG%!...%RES%"
call :elog .
call :elog "!choicep.%LNG%!.."

set /p "addon_path=!enter_url.%LNG%!"
if not defined addon_path (
    call :elog "%NOK%" "未提供路径。"
    goto :eof
)

set "addon_path=%addon_path:"=%"

:: Check if it's a URL or local path
echo %addon_path% | "%SystemRoot%\System32\findstr.exe" /r "^https\?://" >nul
if %errorlevel% EQU 0 (
    :: It's a URL
    set "temp_zip=%TEMP%\custom_addon.zip"
    call :elog -n "%EMPTY%" "!download.%LNG%!.."
    if %DEBUGLEVEL% GEQ 1 echo "%PWRSHELL%" -NoProfile -Command "(New-Object System.Net.WebClient).DownloadFile('%addon_path%','%temp_zip%')" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "(New-Object System.Net.WebClient).DownloadFile('%addon_path%','%temp_zip%')" %DEBUGREDIR%
    if !errorlevel! NEQ 0 (
        call :elog "%NOK%" "!UNDWNLD.%LNG%! %MAG%%addon_path%%RES%"
        goto :skip_custom
    )
    set "source=%temp_zip%"
) else (
    :: Local path
    if not exist "%addon_path%" (
        call :elog "%NOK%" "!FNOTFOUND.%LNG%! %YEL%%addon_path%%RES%"
        goto :skip_custom
    )
    set "source=%addon_path%"
)

:: Check if it's a zip/rar or folder
if exist "%source%\*" (
    :: It's a folder, copy it
    call :elog "正在复制文件夹..."
    xcopy "%source%" "%WORKDIR%\game\" /E /I /H /Y %DEBUGREDIR%
    if !errorlevel! NEQ 0 (
        call :elog "%NOK%" "复制文件夹失败。"
    ) else (
        call :elog "%OK%"
    )
) else (
    :: Assume it's an archive
    call :elog -n "%EMPTY%" "正在解压存档..."
    if %DEBUGLEVEL% GEQ 1 echo "%PWRSHELL%" -NoProfile -Command "Expand-Archive -Force '%source%' '%WORKDIR%\game'" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "Expand-Archive -Force '%source%' '%WORKDIR%\game'" %DEBUGREDIR%
    if !errorlevel! NEQ 0 (
        call :elog "%NOK%" "!UNEXTRACT.%LNG%! %YEL%%source%%RES%"
    ) else (
        call :elog "%OK%"
    )
    if defined temp_zip del /f /q "%temp_zip%" %DEBUGREDIR%
)

:skip_custom
timeout /T 1 %DEBUGREDIR%
goto :eof


:: Replace any character name in game files
:replace_anyname
set "renaname.zh=请输入新名称（不带引号）："

set "renaname2.zh=未提供名称。"

set "renaname3.zh=请输入旧名称（不带引号）："

set "unr-unkonwn=%WORKDIR%\game\unr-unkonwn.rpy"

call :elog .
:oldname
call :elog .
set "oldname="
echo oldname=!renaname3.%LNG%! >> "%UNRENLOG%"
set /p "oldname=!renaname3.%LNG%!"

if "%oldname%" == "" (
    call :elog .
    call :elog "%NOK%" "!renaname2.%LNG%!%RES%"
    call :elog .
    goto :oldname
) else (
    echo oldname=!oldname! >> "%UNRENLOG%"
)
set "unr-unkonwn=%WORKDIR%\game\unr-%oldname%.rpy"

call :elog .
call :elog "!TWADD.%LNG%! %YEL%%unr-unkonwn%.%RES%"
call :elog .
call :elog "!INCASEDEL.%LNG%!%RES%"
call :elog "%YEL%%unr-unkonwn%%RES%"
call :elog "%YEL%%unr-unkonwn%c%RES%"

:newname
call :elog .
set "newname="
echo newname=!renaname.%LNG%! >> "%UNRENLOG%"
set /p "newname=!renaname.%LNG%!"

if "%newname%" == "" (
    call :elog .
    call :elog "%NOK%" "!renaname2.%LNG%!%RES%"
    call :elog .
    goto :newname
) else (
    echo newname=!newname! >> "%UNRENLOG%"
)

>"%unr-unkonwn%.b64" (
    <nul set /p="IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KaW5pdCA5OTkgcHl0aG9uOg0KICAgIGltcG9ydCByZQ0KDQogICAgIyBQbGFjZWhvbGRlcnMgcmVwbGFjZWQgYnkgUG93ZXJTaGVsbCBiZWZvcmUgZXhlY3V0aW9uDQogICAgT0xEID0gIm9sZG5hbWUiDQogICAgTkVXID0gIm5ld25hbWUiDQoNCiAgICBkZWYgX2Nhc2VfbGlrZShzLCBtb2RlbCk6DQogICAgICAgICMgQWxpZ24gdGhlIGNhc2Ugb2YgcyB3aXRoIHRoYXQgb2YgbW9kZWwgKHVwcGVyLCBUaXRsZSwgbG93ZXIpDQogICAgICAgIGlmIG1vZGVsLmlzdXBwZXIoKToNCiAgICAgICAgICAgIHJldHVybiBzLnVwcGVyKCkNCiAgICAgICAgZWxpZiBtb2RlbFs6MV0uaXN1cHBlcigpIGFuZCBtb2RlbFsxOl0uaXNsb3dlcigpOg0KICAgICAgICAgICAgcmV0dXJuIHMuY2FwaXRhbGl6ZSgpDQogICAgICAgIGVsc2U6DQogICAgICAgICAgICByZXR1cm4gcy5sb3dlcigpDQoNCiAgICBkZWYgcmVwbGFjZV90ZXh0KHQpOg0KICAgICAgICBvbGQgPSBPTEQNCiAgICAgICAgbmV3ID0gTkVXDQoNCiAgICAgICAgb19lc2MgPSByZS5lc2NhcGUob2xkKQ0KICAgICAgICBmX29sZCA9IG9sZFs6MV0NCiAgICAgICAgZl9uZXcgPSBuZXdbOjFdDQoNCiAgICAgICAgIyAxKSBSZXBsYWNlbWVudCBvZiB0aGUgZW50aXJlIHdvcmQgKGNhc2UtaW5zZW5zaXRpdmUpIHdpdGggY2FzZSByZXN0b3JhdGlvbg0KICAgICAgICBiYXNlX3BhdCA9IHJlLmNvbXBpbGUocmYiXGIoP2k6KHtvX2VzY30pKVxiIikNCiAgICAgICAgZGVmIGJhc2VfcmVwbChtKToNCiAgICAgICAgICAgIHJldHVybiBfY2FzZV9saWtlKG5ldywgbS5ncm91cCgxKSkNCiAgICAgICAgdCA9IGJhc2VfcGF0LnN1YihiYXNlX3JlcGwsIHQpDQoNCiAgICAgICAgIyAyKSBTdHV0dGVyaW5nIHR5cGU6IGMtY29ubm9yIOKGkiBqLWpvZSAoYW5kIGNhc2UgdmFyaWFudHMpDQogICAgICAgIHN0MV9wYXQgPSByZS5jb21waWxlKHJmIlxiKFt7Zl9vbGQubG93ZXIoKX17Zl9vbGQudXBwZXIoKX1dKS0oP2k6KHtvX2VzY30pKVxiIikNCiAgICAgICAgZGVmIHN0MV9yZXBsKG0pOg0KICAgICAgICAgICAgcHJlZiA9IG0uZ3JvdXAoMSkgICAgICAgIyBwcmVmaXggbGV0dGVyIChjL0MpDQogICAgICAgICAgICBvbGRfcGFydCA9IG0uZ3JvdXAoMikgICAjIHdvcmQgKGNvbm5vci9Db25ub3IvQ09OTk9SKQ0KICAgICAgICAgICAgbmV3X3dvcmQgPSBfY2FzZV9saWtlKG5ldywgb2xkX3BhcnQpDQogICAgICAgICAgICBuZXdfZmlyc3QgPSBmX25ldy51cHBlcigpIGlmIHByZWYuaXN1cHBlcigpIGVsc2UgZl9uZXcubG93ZXIoKQ0KICAgICAgICAgICAgcmV0dXJuIGYie25ld19maXJzdH0te25ld193b3JkfSINCiAgICAgICAgdCA9IHN0MV9wYXQuc3ViKHN0MV9yZXBsLCB0KQ0KDQogICAgICAgICMgMykgU3R1dHRlcmluZyB0eXBlOiBjby1jb25ub3Ig4oaSIGpvLWpvZSAoYW5kIGNhc2UgdmFyaWFudHMpDQogICAgICAgIHN0Ml9wYXQgPSByZS5jb21waWxlKHJmIlxiKFt7Zl9vbGQubG93ZXIoKX17Zl9vbGQudXBwZXIoKX1dKShbb09dKS0oP2k6KHtvX2VzY30pKVxiIikNCiAgICAgICAgZGVmIHN0Ml9yZXBsKG0pOg0KICAgICAgICAgICAgcHJlZiA9IG0uZ3JvdXAoMSkgICAgICAgIyBwcmVmaXggbGV0dGVyIChjL0MpDQogICAgICAgICAgICBvY2hhciA9IG0uZ3JvdXAoMikgICAgICAjICdvJyBvciAnTycNCiAgICAgICAgICAgIG9sZF9wYXJ0ID0gbS5ncm91cCgzKSAgICMgd29yZCAoY29ubm9yL0Nvbm5vci9DT05OT1IpDQogICAgICAgICAgICBuZXdfd29yZCA9IF9jYXNlX2xpa2UobmV3LCBvbGRfcGFydCkNCiAgICAgICAgICAgIG5ld19maXJzdCA9IGZfbmV3LnVwcGVyKCkgaWYgcHJlZi5pc3VwcGVyKCkgZWxzZSBmX25ldy5sb3dlcigpDQogICAgICAgICAgICAjIEtlZXAgdGhlIGNhc2Ugb2YgdGhlICdvJyBsZXR0ZXIgYXMgZW5jb3VudGVyZWQNCiAgICAgICAgICAgIHJldHVybiBmIntuZXdfZmlyc3R9e29jaGFyfS17bmV3X3dvcmR9Ig0KICAgICAgICB0ID0gc3QyX3BhdC5zdWIoc3QyX3JlcGwsIHQpDQoNCiAgICAgICAgcmV0dXJuIHQNCg0KICAgIGNvbmZpZy5yZXBsYWNlX3RleHQgPSByZXBsYWNlX3RleHQNCiAgICBkZWwgcmVwbGFjZV90ZXh0DQo="
)
call :elog .
call :pwsh_exp "!choicel.%LNG%!.." "%unr-unkonwn%"
if not exist "%unr-unkonwn%" (
    call :elog "%NOK%" "!FNOTFOUND.%LNG%! %YEL%!unr-unkonwn!%RES%"
    call :elog .
    goto :anynameend
) else (
    del /f /q "%unr-unkonwn%.b64" %DEBUGREDIR%
    if %DEBUGLEVEL% GEQ 1 echo "%PWRSHELL%" -NoProfile -Command "(Get-Content '%unr-unkonwn%.tmp') -replace 'newname', '%newname%' | Set-Content '%unr-unkonwn%'" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "(Get-Content '%unr-unkonwn%.tmp') -replace 'newname', '%newname%' | Set-Content '%unr-unkonwn%'" %DEBUGREDIR%
    if %DEBUGLEVEL% GEQ 1 echo "%PWRSHELL%" -NoProfile -Command "(Get-Content '%unr-unkonwn%') -replace 'oldname', '%oldname%' | Set-Content '%unr-unkonwn%'" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "(Get-Content '%unr-unkonwn%') -replace 'oldname', '%oldname%' | Set-Content '%unr-unkonwn%'" %DEBUGREDIR%
    if not exist "%unr-unkonwn%" (
        call :elog "%NOK%" "!FNOTFOUND.%LNG%! %YEL%!unr-unkonwn!%RES%"
        call :elog .
        goto :anynameend
    ) else (
        set "rename4.zh=角色已从 %YEL%!oldname!%RES% 重命名为 %YEL%!newname!%RES%"

        call :elog "%OK%" "!rename4.%LNG%!"
    )
    :anynameend
    del /f /q "%unr-unkonwn%.tmp" %DEBUGREDIR%
)

:anynameend
timeout /T 1 %DEBUGREDIR%
goto :eof


:: Remove nasty sync folder
:nasty_sync
set "unren-nsync=%WORKDIR%\game\unren-nsync.rpy"

call :elog .
call :elog "!TWADD.%LNG%! %YEL%%unren-nsync%.%RES%"
call :elog .
call :elog "!INCASEDEL.%LNG%!"
call :elog "%YEL%%unren-nsync%%RES%"
call :elog "%YEL%%unren-nsync%c%RES%"

if exist "%unren-nsync%" (
    call :elog .
    call :elog "%SKIP%" "!APRESENT.%LNG%!"
    call :elog .
) else (
    >"%unren-nsync%" (
        echo # Made by ^(SM^) aka JoeLurmel @ f95zone.to
        echo.
        echo init 9999 python:
        echo     renpy.config.has_sync = False
        echo     renpy.config.extra_savedirs = []
        echo.
    )
    call :elog .
    call :elog -n "%EMPTY%" "!choicen.%LNG%!.."
    if not exist "%unren-nsync%" (
        call :elog "%NOK%" "!FCREATE.%LNG%! %YEL%%unren-nsync%%RES%"
        call :elog .
    ) else (
        call :elog "%OK%"
    )
)
timeout /T 1 %DEBUGREDIR%
goto :eof


:: Restore .org files into their original name
:restore_files
setlocal disabledelayedexpansion
for /f "delims=" %%A in ("%WORKDIR%") do (
    endlocal
    cd /d "%%A"
)

call :elog .
call :elog "!choicer.%LNG%!"

set "file_found=0"
set "prevDir="
for /R ".\game" %%f in (*.rpa.org *.rpy.org *.rpyc.org) do (
    set "currDir=%%~dpf"
    set "orgfile=%%f"
    set "filename=%%~nxf"
    set "dstfilename=!filename:.org=!"
    set "dstfile=!orgfile:.org=!"

    set "rmsg.tu=Переименование %YEL%!filename!%RES% в %YEL%!dstfilename!%RES%"
set "rmsg.zh=将 %YEL%!filename!%RES% 重命名为 %YEL%!dstfilename!%RES%"

    if not "!prevDir!" == "!currDir!" (
        call :elog .
        call :elog "!MTITLE.%LNG%! %YEL%!currDir!%RES%"
        set "prevDir=!currDir!"
    )

    if exist "!orgfile!" (
        set "file_found=1"
    )

    call :elog -n "%EMPTY%" "!rmsg.%LNG%!"
    move /y "!orgfile!" "!dstfile!" %DEBUGREDIR%
    if not exist "!dstfile!" (
        call :elog "%NOK%" "!FMOVE.%LNG%! %YEL%!filename!%RES% -> %YEL%!dstfilename!%RES%"
    ) else (
        call :elog "%OK%"
    )
)

if %file_found% EQU 0 (
    call :elog .
    call :elog "%SKIP%" "!NOTFOUND.%LNG%!."
    call :elog .
)
timeout /T 1 %DEBUGREDIR%
goto :eof


:: Delete .org files made by the script
:delete_backups
setlocal disabledelayedexpansion
for /f "delims=" %%A in ("%WORKDIR%") do (
    endlocal
    cd /d "%%A"
)

call :elog .
call :elog "!choices.%LNG%!"

set "file_found=0"
set "prevDir="
for /R ".\game" %%f in (*.rpa.org *.rpy.org *.rpyc.org) do (
    set "orgfile=%%f"
    set "currDir=%%~dpf"
    set "filename=%%~nxf"

    set "dmsg.zh=删除 %YEL%!filename!%RES%"

    if not "!prevDir!" == "!currDir!" (
        call :elog .
        call :elog "!MTITLE.%LNG%! %YEL%!currDir!%RES%"
        set "prevDir=!currDir!"
    )

    if exist "!orgfile!" (
        set "file_found=1"
    )

    call :elog -n "%EMPTY%" "!dmsg.%LNG%!"
    del /f /q "!orgfile!" %DEBUGREDIR%
    if exist "!orgfile!" (
        call :elog "%NOK%" "!FDELETE.%LNG%! %YEL%!orgfile!%RES%"
    ) else (
        call :elog "%OK%"
    )
)

call :elog .
if !file_found! EQU 0 (
    call :elog .
    call :elog "%SKIP%" "!NOTFOUND.%LNG%!."
    call :elog .
    exit /b 1
)
timeout /T 1 %DEBUGREDIR%
goto :eof


:: Extract text for translation purpose
:extract_text
if "%LNG%" == "en"  set translation_lang=english
if "%LNG%" == "de"  set translation_lang=german
if "%LNG%" == "ru"  set translation_lang=russian
if "%LNG%" == "zh"  set translation_lang=chinese

setlocal disabledelayedexpansion
for /f "delims=" %%A in ("%WORKDIR%") do (
    endlocal
    cd /d "%%A"
)

set "etext1.zh=正在搜索游戏名称"

set "etext2.zh=未找到带有 .exe 或 .py 扩展名的游戏文件。"

set "etext3.zh=输入目标翻译语言（默认 %YEL%%translation_lang%%RES%）："

set "etext4.zh=无法提取文本用于翻译。"

set "etext5.zh=请输入游戏名称（不带扩展名）："

set "etext6.zh=未找到游戏目录中的 *.rpy 文件。"

set "etext7.zh=请先使用选项 2 来反编译游戏。"

set "etext8.zh=请先使用选项 1 来解压游戏。"

:: Check if needed files for extraction are present
set "RpysFound=0"
for /r ".\game" %%F in (*.rpy) do (
    echo %%F | "%SystemRoot%\System32\findstr.exe" /i /c:"\\tl\\" >nul 2>&1
    if errorlevel 1 set /a RpysFound+=1
)
if %RpysFound% LEQ 3 (
    call :elog .
    call :elog "%NOK%" "!etext6.%LNG%!"
    set "RpycFound=0"
    for /r ".\game" %%F in (*.rpyc) do (
        echo %%F | "%SystemRoot%\System32\findstr.exe" /i /c:"\\tl\\" >nul 2>&1
        if errorlevel 1 set /a RpycFound+=1
    )
    if !RpycFound! GTR 0 (
        call :elog "%NOK%" "!etext7.%LNG%!"
    ) else (
        call :elog "%NOK%" "!etext8.%LNG%!"
    )
    timeout /T 1 %DEBUGREDIR%
    exit /b 1
)

call :elog .
if not "%OPTION%" == "m" echo.
call :elog -n "%EMPTY%" "!etext1.%LNG%!..."

:: find the current game name by checking the presence of same name with .exe, .py and .sh extension
set "processed="
set "fname="
:: Do not test with sh, it can be not shipped
for %%e in (exe py) do (
    for %%f in (*.%%e) do (
        set "tempfname=%%~nf"

        REM Check if this name has already been processed
        echo !processed! | "%SystemRoot%\System32\findstr.exe" /i "\!tempfname!" >nul
        if errorlevel 1 (
            REM Count how many files with this name exist
            set /a count=0
            for %%x in (exe py) do (
                if exist "%%~dpf!tempfname!.%%x" (
                    set /a count+=1
                )
            )
            if !count! EQU 2 (
                call :elog "%OK%" "%YEL%!tempfname!%RES%"
                set "processed=!processed! !tempfname!"
                set "fname=!tempfname!"
                goto :found_name
            )
        )
    )
)

:: If no name found, ask user to input the name
if "%fname%"  == "" (
    call :elog "%NOK%" "!etext2.%LNG%!"
    goto :input_name
)

:input_name
call :elog .
set /p "fname=!etext5.%LNG%!"
if "%fname%" == "" (
    call :elog "%NOK%" "!etext2.%LNG%!"
    goto :input_name
) else (
    if not exist "%WORKDIR%\%fname%.exe" (
        call :elog "%NOK%" "!etext2.%LNG%!"
        goto :input_name
    )
)

:found_name
call :elog .
set /p "translation_lang=!etext3.%LNG%!"

if not defined translation_lang (
	set "translation_lang=french"
)

if not exist "%WORKDIR%\game\tl\" (
	mkdir "%WORKDIR%\game\tl"
)

call :elog .
call :elog -n "%EMPTY%" "!choicet.%LNG%!..."

setlocal disabledelayedexpansion
for /f "delims=" %%A in ("%WORKDIR%") do (
    endlocal
    cd /d "%%A"
)
if %DEBUGLEVEL% GEQ 1 echo "%PYTHONHOME%python.exe" %PYNOASSERT% "%fname%.py" game translate "%translation_lang%" >> "%UNRENLOG%"
"%PYTHONHOME%python.exe" %PYNOASSERT% "%fname%.py" game translate "%translation_lang%" %DEBUGREDIR%
if %errorlevel% NEQ 0 (
	call :elog "%NOK%" "!etext4.%LNG%!"
) else (
    call :elog "%OK%"
)
timeout /T 1 %DEBUGREDIR%
goto :eof


:: Check if old registry key is present and require Administrator rights to remove it
:check_old_reg
"%SystemRoot%\System32\reg.exe" query "HKLM\Software\Classes\Directory\shell\Run%SCRIPTNAME%" %DEBUGREDIR%
if %errorlevel% EQU 0 (
    set OLDREG=1
) else (
    set OLDREG=0
)
goto :eof


:: Add entry to registry
:add_reg
set "reg=%SystemRoot%\System32\reg.exe"

set "areg1.zh=这将为文件夹添加右键菜单项。"

set "areg2.zh=当您选择此选项时，"

set "areg2a.zh=脚本 %YEL%%SCRIPTDIR%%SCRIPTNAME%%RES% 将被执行。"

set "areg3.zh=正在向注册表添加右键菜单项"

set "areg4.zh=运行 %SCRIPTNAME% 脚本"

set "areg5.zh=您需要先使用 - 选项删除旧的注册表键。"

call :check_old_reg
if %OLDREG% EQU 1 (
    call :elog .
    call :elog "%YEL%!areg5.%LNG%!%RES%"
    call :elog .
    pause>nul|set /p=".      !ANYKEY.%LNG%!..."
    exit /b
)

call :elog .
call :elog "!areg1.%LNG%!"
call :elog "!areg2.%LNG%!"
call :elog "!areg2a.%LNG%!%RES%"
call :elog .
call :elog -n "%EMPTY%" "!areg3.%LNG%!..."

"%regexe%" add "HKCU\Software\Classes\Directory\shell\Run%SCRIPTNAME%" /ve /d "!areg4.%LNG%!" /f %DEBUGREDIR%
set error=%errorlevel%
"%regexe%" add "HKCU\Software\Classes\Directory\shell\Run%SCRIPTNAME%" /v "Icon" /d "%SystemRoot%\System32\shell32.dll,-154" /f %DEBUGREDIR%
set /a error=%error%+%errorlevel%
"%regexe%" add "HKCU\Software\Classes\Directory\shell\Run%SCRIPTNAME%\command" /ve /d "%SystemRoot%\System32\cmd.exe /c cd /d \"%%V\" && \"%SCRIPTDIR%%SCRIPTNAME%\" \"%%V\"" /f %DEBUGREDIR%
set /a error=%error%+%errorlevel%
"%regexe%" add "HKCU\Software\Classes\Directory\Background\shell\Run%SCRIPTNAME%" /ve /d "!areg4.%LNG%!" /f %DEBUGREDIR%
set error=%errorlevel%
"%regexe%" add "HKCU\Software\Classes\Directory\Background\shell\Run%SCRIPTNAME%" /v "Icon" /d "%SystemRoot%\System32\shell32.dll,-154" /f %DEBUGREDIR%
set /a error=%error%+%errorlevel%
"%regexe%" add "HKCU\Software\Classes\Directory\Background\shell\Run%SCRIPTNAME%\command" /ve /d "%SystemRoot%\System32\cmd.exe /c cd /d \"%%V\" && \"%SCRIPTDIR%%SCRIPTNAME%\" \"%%V\"" /f %DEBUGREDIR%
set /a error=%error%+%errorlevel%
if %error% EQU 0 (
	call :elog "%OK%"
) else (
	call :elog "%NOK%" "!LOGCHK.%LNG%!"
)
call :elog .

timeout /T 1 %DEBUGREDIR%
goto :eof


:: Remove entry from registry
:remove_reg
set "regexe=%SystemRoot%\System32\reg.exe"

set "rreg1.zh=这将移除先前为文件夹添加的右键菜单项。"

set "rreg2.zh=正在从注册表中移除右键菜单项"

:: Remove registry key with Administrator rights if old registry key is present,
:: otherwise remove registry key with current user rights
set OLDREG=0
call :check_old_reg
if %OLDREG% EQU 1 (
    call :check_admin
)

call :elog .
call :elog .
call :elog "!rreg1.%LNG%!"
call :elog .
call :elog -n "%EMPTY%" "!rreg2.%LNG%!..."

set error=0
if %OLDREG% EQU 1 (
    "!regexe!" query "HKLM\SOFTWARE\Classes\Directory\shell\RunUnrenForAll" %DEBUGREDIR%
    if !errorlevel! EQU 0 (
        "!regexe!" delete "HKLM\SOFTWARE\Classes\Directory\shell\RunUnrenForAll" /f %DEBUGREDIR%
        set error=!errorlevel!
    )
    "!regexe!" query "HKLM\SOFTWARE\Classes\Directory\shell\Run%SCRIPTNAME%" %DEBUGREDIR%
    if !errorlevel! EQU 0 (
        "!regexe!" delete "HKLM\SOFTWARE\Classes\Directory\shell\Run%SCRIPTNAME%" /f %DEBUGREDIR%
        set /a error=!error!+!errorlevel!
    )
    "!regexe!" query "HKLM\SOFTWARE\Classes\Directory\Background\shell\Run%SCRIPTNAME%" %DEBUGREDIR%
    if !errorlevel! EQU 0 (
        "!regexe!" delete "HKLM\SOFTWARE\Classes\Directory\Background\shell\Run%SCRIPTNAME%" /f %DEBUGREDIR%
        set /a error=!error!+!errorlevel!
    )
    if !error! NEQ 0 (
        call :elog "%NOK%" "!ARIGHT.%LNG%!"
        call :elog .
        pause>nul|set /p=".      !ANYKEY.%LNG%!..."

        call :exitn 3
    )
) else (
    "!regexe!" query "HKCU\Software\Classes\Directory\shell\Run%SCRIPTNAME%" %DEBUGREDIR%
    if !errorlevel! EQU 0 (
        "!regexe!" delete "HKCU\Software\Classes\Directory\shell\Run%SCRIPTNAME%" /f %DEBUGREDIR%
        set error=!errorlevel!
    )
    "!regexe!" query "HKCU\Software\Classes\Directory\Background\shell\Run%SCRIPTNAME%" %DEBUGREDIR%
    if !errorlevel! EQU 0 (
        "!regexe!" delete "HKCU\Software\Classes\Directory\Background\shell\Run%SCRIPTNAME%" /f %DEBUGREDIR%
        set /a error=!error!+!errorlevel!
    )
    if !error! NEQ 0 (
        call :elog "%NOK%"
    )
)
if !error! EQU 0 (
    call :elog "%OK%"
    set OLDREG=0
)

timeout /T 1 %DEBUGREDIR%
goto :eof


:: Check for administrative privileges
:check_admin
setlocal
set "admright.zh=检查管理员权限"

set "admright2.zh=您没有以管理员权限运行此脚本。"

set "admright3.zh=请以管理员权限重新启动脚本。"

call :elog .
call :elog .
call :elog -n "%EMPTY%" "!admright.%LNG%!..."

net session %DEBUGREDIR%
if %errorlevel% EQU 0 (
    call :elog "%OK%"
) else (
	call :elog "%NOK%"
    call :elog .
    call :elog "!admright2.%LNG%!"
    call :elog "!admright3.%LNG%!"
    call :elog .
    timeout /T 2 %DEBUGREDIR%
    if %DEBUGLEVEL% GEQ 1 echo "%PWRSHELL%" -NoProfile -Command "Start-Process '%~f0' -ArgumentList '%WORKDIR%' -Verb RunAs" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "Start-Process '%~f0' -ArgumentList '%WORKDIR%' -Verb RunAs" %DEBUGREDIR%

    call :exitn 0
)
endlocal
goto :eof


:: When it's not unavailable, show message and exit
:unavailable
setlocal
if "%RENPYVERSION%" == "7" (
    set "unavailable.zh=此功能在此版本中不可用。"
)
if "%RENPYVERSION%" == "8" (
    set "unavailable.zh=此功能暂不可用，需要更多编码。"
)

call :elog .
call :elog "%WARN%" "!unavailable.%LNG%!"

timeout /T 2 %DEBUGREDIR%
endlocal
goto :menu


:: Params:
:: 1 - Message to display
:: 2 - Choices list (e.g. "YN" for Yes/No)
:: 3 - Default choice (e.g. "N" for No)
:: 4 - Timeout in seconds (e.g. "10" for 10 seconds)
:: 5 - Additional options (optional) (e.g. "-rawMsg" to not encapsulate the default choice in the choice list)
:choiceEx
if defined AUTO_MODE (
    set "AUTO_CHOICES=%~2"
    set "AUTO_DEFAULT=%~3"
    for /l %%I in (0,1,15) do (
        if /i "!AUTO_CHOICES:~%%I,1!" == "!AUTO_DEFAULT!" (
            set /a "AUTO_RESULT=%%I+1"
            exit /b !AUTO_RESULT!
        )
    )
    exit /b 1
)
set "choiceEx=%TEMP%\choiceEx.py"
if not exist "%choiceEx%" if not defined AlreadyCreated (
    >"%choiceEx%.b64" (
        <nul set /p="IyEvdXNyL2Jpbi9lbnYgcHl0aG9uDQojIC0qLSBjb2Rpbmc6IHV0Zi04IC0qLQ0KDQppbXBvcnQgc3lzDQppbXBvcnQgdGltZQ0KaW1wb3J0IG1zdmNydA0KaW1wb3J0IGNvZGVjcw0KDQppZiBzeXMudmVyc2lvbl9pbmZvWzBdIDwgMzoNCiAgICBpbXBvcnQgY3R5cGVzDQogICAgIyBGb3JjZSBsYSBjb25zb2xlIFdpbmRvd3MgZW4gVVRGLTgNCiAgICBjdHlwZXMud2luZGxsLmtlcm5lbDMyLlNldENvbnNvbGVDUCg2NTAwMSkNCiAgICBjdHlwZXMud2luZGxsLmtlcm5lbDMyLlNldENvbnNvbGVPdXRwdXRDUCg2NTAwMSkNCg0KICAgICMgQ1JVQ0lBTDogRW52ZWxvcHBlIHN0ZG91dCBhdmVjIHVuIHdyaXRlciBVVEYtOA0KICAgIHN5cy5zdGRvdXQgPSBjb2RlY3MuZ2V0d3JpdGVyKCd1dGYtOCcpKHN5cy5zdGRvdXQpDQogICAgc3lzLnN0ZGVyciA9IGNvZGVjcy5nZXR3cml0ZXIoJ3V0Zi04Jykoc3lzLnN0ZGVycikNCg0KIyBHw6hyZSBsZXMgZGV1eCBQeXRob24gMiBldCAzDQppZiBzeXMudmVyc2lvbl9pbmZvWzBdIDwgMzoNCiAgICBtc2cgPSBzeXMuYXJndlsxXS5kZWNvZGUoJ2xhdGluLTEnKSBpZiBpc2luc3RhbmNlKHN5cy5hcmd2WzFdLCBzdHIpIGVsc2Ugc3lzLmFyZ3ZbMV0NCmVsc2U6DQogICAgbXNnID0gc3lzLmFyZ3ZbMV0NCg0KY2hvaWNlcyAgICAgPSBzeXMuYXJndlsyXQ0KZGVmYXVsdCAgICAgPSBzeXMuYXJndlszXQ0KdGltZW91dCAgICAgPSBpbnQoc3lzLmFyZ3ZbNF0pDQpyYXcgICAgICAgICA9IChsZW4oc3lzLmFyZ3YpID4gNSBhbmQgc3lzLmFyZ3ZbNV0gPT0gIi1yYXdNc2ciKQ0KDQppZiByYXc6DQogICAgZGlzcGxheSA9IG1zZw0KZWxzZToNCiAgICBkaXNwID0gWyJbJXNdIiAlIGMgaWYgYyA9PSBkZWZhdWx0IGVsc2UgYyBmb3IgYyBpbiBjaG9pY2VzXQ0KICAgIGRpc3BsYXkgPSAiJXMgKCVzLCB0aW1lb3V0ICVzcykgOiAiICUgKG1zZywgJy8nLmpvaW4oZGlzcCksIHRpbWVvdXQpDQoNCnN5cy5zdGRvdXQud3JpdGUoZGlzcGxheSkNCnN5cy5zdGRvdXQuZmx1c2goKQ0KDQplbmQgPSB0aW1lLnRpbWUoKSArIHRpbWVvdXQNCnJlc3VsdCA9IGRlZmF1bHQNCg0Kd2hpbGUgdGltZS50aW1lKCkgPCBlbmQ6DQogICAgaWYgbXN2Y3J0LmtiaGl0KCk6DQogICAgICAgIGtleSA9IG1zdmNydC5nZXR3Y2goKQ0KICAgICAgICBpZiBrZXkgPT0gIlxyIjogICMgRW50ZXINCiAgICAgICAgICAgIGJyZWFrDQogICAgICAgIGtleSA9IGtleS51cHBlcigpDQogICAgICAgIGlmIGtleSBpbiBjaG9pY2VzOg0KICAgICAgICAgICAgcmVzdWx0ID0ga2V5DQogICAgICAgICAgICBicmVhaw0KICAgIHRpbWUuc2xlZXAoMC4wNSkNCg0Kc3lzLnN0ZG91dC53cml0ZShyZXN1bHQpDQpzeXMuc3Rkb3V0LndyaXRlKCJcbiIpDQpzeXMuZXhpdChjaG9pY2VzLmluZGV4KHJlc3VsdCkgKyAxKQ=="
    )
    if defined PYTHONHOME (
        if %DEBUGLEVEL% GEQ 1 echo "%PYTHONHOME%python.exe" %PYNOASSERT% "%TEMP%\b64decode.py" "%choiceEx%.b64" "%choiceEx%.tmp" >> "%UNRENLOG%"
        "%PYTHONHOME%python.exe" %PYNOASSERT% "%TEMP%\b64decode.py" "%choiceEx%.b64" "%choiceEx%.tmp" %DEBUGREDIR%
    ) else (
        if %DEBUGLEVEL% GEQ 1 echo "%PWRSHELL%" -NoProfile -Command "& { [IO.File]::WriteAllBytes('%choiceEx%.tmp', [Convert]::FromBase64String([IO.File]::ReadAllText('%choiceEx%.b64')))}" >> "%UNRENLOG%"
        "%PWRSHELL%" -NoProfile -Command "& { [IO.File]::WriteAllBytes('%choiceEx%.tmp', [Convert]::FromBase64String([IO.File]::ReadAllText('%choiceEx%.b64')))}" %DEBUGREDIR%
    )
    if %DEBUGLEVEL% GEQ 1 echo move /y "%choiceEx%.tmp" "%choiceEx%" >> "%UNRENLOG%"
    move /y "%choiceEx%.tmp" "%choiceEx%" %DEBUGREDIR%
    if %DEBUGLEVEL% GEQ 1 del /f /q "%choiceEx%.b64" >> "%UNRENLOG%"
    del /f /q "%choiceEx%.b64" %DEBUGREDIR%
    set "AlreadyCreated=1"
)

if %DEBUGLEVEL% GEQ 1 echo "%PYTHONHOME%python.exe" %PYNOASSERT% "%choiceEx%" "%~1" "%~2" "%~3" "%~4" "%~5" >> "%UNRENLOG%"
"%PYTHONHOME%python.exe" %PYNOASSERT% "%choiceEx%" "%~1" "%~2" "%~3" "%~4" "%~5"

exit /b %errorlevel%


:: For debugging help
:DisplayVars
set "emsg=%~1"

>> "%UNRENLOG%" echo.
echo "%emsg%" >> "%UNRENLOG%"
echo SCRIPTDIR      = %SCRIPTDIR% >> "%UNRENLOG%"
echo WORKDIR        = %WORKDIR% >> "%UNRENLOG%"
echo PYTHONHOME     = %PYTHONHOME% >> "%UNRENLOG%"
echo PYTHONPATH     = %PYTHONPATH% >> "%UNRENLOG%"
echo PYTHONEXE      = %PYTHONEXE% >> "%UNRENLOG%"
echo PYNOASSERT     = [%PYNOASSERT%] >> "%UNRENLOG%"
echo PYVERSION      = [%PYVERSION%] >> "%UNRENLOG%"
echo PYVERSION2     = [%PYVERSION2%] >> "%UNRENLOG%"
echo PYVERSION3     = [%PYVERSION3%] >> "%UNRENLOG%"
echo PYTHONSYSTEM   = [%PYTHONSYSTEM%] >> "%UNRENLOG%"
echo PYTHONVERS     = [%PYTHONVERS%] >> "%UNRENLOG%"
echo RPATOOL_NEW    = %RPATOOL_NEW% >> "%UNRENLOG%"
echo UNRPYC_NEW     = %UNRPYC_NEW% >> "%UNRENLOG%"
echo RENPYVERSION   = [%RENPYVERSION%] >> "%UNRENLOG%"
echo OFFSET         = [%OFFSET%] >> "%UNRENLOG%"
>> "%UNRENLOG%" echo.
goto :eof


:: Expand a b64-encoded and save it as a file
:: Usage:
::   call :pwsh_exp "Message to display while expanding" "path\to\file_to_expand"
:pwsh_exp
set "expmsg=%~1"
set "f2expand=%~2"
::set DEBUGLEVEL=1

if %DEBUGLEVEL% GEQ 1 (
    echo "expmsg=%expmsg%" >> "%UNRENLOG%"
    echo "f2expand=%f2expand%" >> "%UNRENLOG%"
    echo "PREVMSG=%PREVMSG%" >> "%UNRENLOG%"
    echo "PREVMOD=%PREVMOD%" >> "%UNRENLOG%"
)

call :elog -n "%EMPTY%" "%expmsg%"
if not exist "%f2expand%.b64" (
    call :elog "%NOK%" "!FCREATE.%LNG%! %YEL%!f2expand!.b64%RES%"
    goto :eof
) else (
    set "f2ps=!f2expand:'=''!"
    if defined PYTHONHOME (
        if %DEBUGLEVEL% GEQ 1 echo "%PYTHONHOME%python.exe" %PYNOASSERT% "%TEMP%\b64decode.py" "!f2ps!.b64" "!f2ps!.tmp" >> "%UNRENLOG%"
        "%PYTHONHOME%python.exe" %PYNOASSERT% "%TEMP%\b64decode.py" "!f2ps!.b64" "!f2ps!.tmp"
    ) else (
        if %DEBUGLEVEL% GEQ 1 echo "%PWRSHELL%" -NoProfile -Command "& { $src='!f2ps!.b64'; $dst='!f2ps!.tmp'; [IO.File]::WriteAllBytes($dst, [Convert]::FromBase64String([IO.File]::ReadAllText($src)))}" >> "%UNRENLOG%"
        "%PWRSHELL%" -NoProfile -Command "& { $src='!f2ps!.b64'; $dst='!f2ps!.tmp'; [IO.File]::WriteAllBytes($dst, [Convert]::FromBase64String([IO.File]::ReadAllText($src)))}" %DEBUGREDIR%
    )
    if %DEBUGLEVEL% GEQ 1 echo del /f /q "!f2expand!.b64" >> "%UNRENLOG%"
    del /f /q "!f2expand!.b64" %DEBUGREDIR%
    if not exist "%f2expand%.tmp" (
        call :elog "%NOK%" "!FCREATE.%LNG%! %YEL%!f2expand!.tmp%RES%"
        goto :eof
    ) else (
        if %DEBUGLEVEL% GEQ 1 echo move /y "!f2expand!.tmp" "!f2expand!" >> "%UNRENLOG%"
        move /y "!f2expand!.tmp" "!f2expand!" %DEBUGREDIR%
    )
)
set "expmsg=" & set "f2expand=" & set "f2ps="
::set DEBUGLEVEL=0
goto :eof


:: elog  —  Enhanced echo with optional no-newline mode
::
:: Usage:
::   call :elog .                         Print an empty line
::   call :elog "msg"                     Print msg with newline
::   call :elog "msg" "msg2"              Print msg and msg2 with newline
::   call :elog -n "module" "msg"         Print [module] msg without newline, store module and msg for next call
::   call :elog "status"                  After -n: replace [module] with [status], reprint msg, add newline
::   call :elog "status" "supplement"     After -n: replace [module] with [status], reprint msg and supplement, add newline
::   call :elog .                         After -n: clear the line and reprint msg alone, without the module
::
:: Where module/status is one of: %EMPTY%, %OK%, %NOK%, %SKIP%
::
:: ANSI codes are stripped when writing to the log file.
:elog
setlocal EnableDelayedExpansion

if %DEBUGLEVEL% GEQ 1 (
    setlocal enabledelayedexpansion
    set "arg2=%~2"
    set "arg2=!arg2:(=^(!"
    set "arg2=!arg2:)=^)!"
    echo arg2=!arg2! >> "%UNRENLOG%"
    endlocal
)
if "%~1" == "-n" (
    <nul set /p="[2K[1000D%~2 %~3"
    endlocal & set "PREVMOD=%~2" & set "PREVMSG=%~3"
    goto :eof
)

set "msg=%~1"
set "msg2=%~2"

:: Calculation of cleanmsg (without ANSI codes)
if defined PREVMOD (
    if defined msg2 (
        set "cleanmsg=%~1 %PREVMSG% %~2"
    ) else (
        set "cleanmsg=%~1 %PREVMSG%"
    )
) else (
    if defined msg2 (
        set "cleanmsg=%~1 %~2"
    ) else (
        set "cleanmsg=%~1"
    )
)

:: Strip ANSI codes from cleanmsg
setlocal EnableDelayedExpansion
for %%C in (GRY RED ORA GRE YEL MAG CYA RES) do (
    call set "cleanmsg=%%cleanmsg:!%%C!=%%"
)

:: Console display
if "!msg!" == "." (
    if defined PREVMOD (
        <nul set /p="[2K[1000D!PREVMSG!"
        echo.
        if exist "%UNRENLOG%" >> "%UNRENLOG%" echo !cleanmsg!
    ) else (
        echo.
        if exist "%UNRENLOG%" >> "%UNRENLOG%" echo.
    )
    endlocal & endlocal & set "PREVMOD=" & set "PREVMSG="
    goto :eof
)

if defined PREVMOD (
    if defined msg2 (
        <nul set /p="[2K[1000D!msg! !PREVMSG! !msg2!"
    ) else (
        <nul set /p="[2K[1000D!msg! !PREVMSG!"
    )
    echo.
    if exist "%UNRENLOG%" >> "%UNRENLOG%" echo !cleanmsg!
    endlocal & endlocal & set "PREVMOD=" & set "PREVMSG="
    goto :eof
)

if defined msg2 (
    echo !msg! !msg2!
) else (
    echo !msg!
)
if exist "%UNRENLOG%" >> "%UNRENLOG%" echo !cleanmsg!
endlocal & endlocal & set "PREVMOD=" & set "PREVMSG="
goto :eof


:: Auto centering message
:center
setlocal Enabledelayedexpansion
set "msg=%~1"

:: Strip color variables for logging
set "cleanmsg=%msg%"
for %%C in (GRY RED ORA GRE YEL MAG CYA RES) do (
    call set "cleanmsg=%%cleanmsg:!%%C!=%%"
)

set "len=0"
for /l %%i in (0,1,300) do (
    if "!cleanmsg:~%%i,1!"=="" (
        set "len=%%i"
        goto :len_done
    )
)

:len_done
:: Calculating left padding
set /a pad=(%NEW_COLS% - len) / 2
if !pad! LSS 0 set "pad=0"

:: Space Design
set "spaces="
for /l %%i in (1,1,!pad!) do set "spaces=!spaces! "

echo(!spaces!!msg!
endlocal
goto :eof


:: Call :exitn for cleanup only or goto :exitn for ending script
:exitn
set "val=%~1"

if exist "%TEMP%\b64decode.py" (
    if %DEBUGLEVEL% GEQ 1 echo del /f /q "%TEMP%\b64decode.py" >> "%UNRENLOG%"
    del /f /q "%TEMP%\b64decode.py" %DEBUGREDIR%
)
if exist "%TEMP%\choiceEx.py" (
    if %DEBUGLEVEL% GEQ 1 echo del /f /q "%TEMP%\choiceEx.py" >> "%UNRENLOG%"
    del /f /q "%TEMP%\choiceEx.py" %DEBUGREDIR%
)

if %DEBUGLEVEL% GEQ 1 (
    echo === 变量 ===
    set
    echo === 变量 ===
)

:: Restore modified configuration and we exit with the appropriate code
"%SystemRoot%\System32\chcp.com" %OLD_CP% %DEBUGREDIR%

:: Restore original console mode
if not defined WT_SESSION (
    if %DEBUGLEVEL% GEQ 1 echo "%SystemRoot%\System32\mode.com" con: cols=%ORIG_COLS% lines=%ORIG_LINES% >> "%UNRENLOG%"
    "%SystemRoot%\System32\mode.com" con: cols=%ORIG_COLS% lines=%ORIG_LINES% %DEBUGREDIR%
)

:: Remove old bug entries
"%SystemRoot%\System32\reg.exe" delete "HKCU\Console\MyScript" /f %DEBUGREDIR%
"%SystemRoot%\System32\reg.exe" delete "HKCU\Console\UnRen-forall.bat" /f %DEBUGREDIR%

if defined val exit !val!

exit 0
