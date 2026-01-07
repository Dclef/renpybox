@echo off
setlocal EnableDelayedExpansion

:: RenpyBox automation (optional)
:: - UNREN_AUTORUN: auto menu input (e.g. 2x / 1x / 5x) to run then exit
:: - UNREN_NO_UPDATE: skip update check (avoid network/prompt)
:: - UNREN_NO_PAUSE: never wait for keypress (avoid hangs in headless mode)
set "UNREN_AUTORUN=%UNREN_AUTORUN%"
set "UNREN_NO_UPDATE=%UNREN_NO_UPDATE%"
set "UNREN_NO_PAUSE=%UNREN_NO_PAUSE%"


:: Original Author:
:: Based on UnRen.bat by Sam - https://f95zone.com/members/sam.7899/ & Gideon - https://f95zone.to/members/gideon.21585/
:: https://f95zone.to/threads/unren-bat-v1-0-11d-rpa-extractor-rpyc-decompiler-console-developer-menu-enabler.3083/

:: Modified by VepsrP - https://f95zone.to/members/vepsrp.329951/
:: https://f95zone.to/threads/unrengui-unren-forall-v9-4-unren-powershell-forall-v9-4-unren-old.92717/

:: Purpose:
:: This script is designed to automate the process of extracting and decompiling Ren'Py games.

:: Using:
:: rpatool - https://github.com/Shizmob/rpatool
:: unrpyc - https://github.com/CensoredUsername/unrpyc

:: UnRen-current.bat - UnRen Script for Ren'Py >= 8
:: heavily modified by (SM) aka JoeLurmel @ f95zone.to
:: This script is licensed under GNU GPL v3 — see LICENSE for details

:: DO NOT MODIFY BELOW THIS LINE unless you know what you're doing
:: Define various global names
set "NAME=current"
set "VERSION=(v9.7.27) (12/24/25)"
title UnRen-%NAME%.bat - %VERSION%
set "URL_REF=https://f95zone.to/threads/unrengui-unren-forall-v9-4-unren-powershell-forall-v9-4-unren-old.92717/post-17110063/"
set "SCRIPTDIR=%~dp0"
set "UPD_TDIR=%TEMP%\UnRenUpdate"
set "SCRIPTNAME=%~nx0"
set "BASENAME=%SCRIPTNAME:.bat=%"
set "UNRENLOG=%TEMP%\UnRen-forall.log"
if exist "%UNRENLOG%" del /f /q "%UNRENLOG%" >nul 2>&1
for /f "skip=1 tokens=1" %%a in ('wmic os get LocalDateTime') do (
    set "datetime=%%a"
    goto :break
)
:break
:: Parse the datetime string
set year=!datetime:~0,4!
set month=!datetime:~4,2!
set day=!datetime:~6,2!
set hour=!datetime:~8,2!
set minute=!datetime:~10,2!
set second=!datetime:~12,2!
set formatted_date=!month!/!day!/!year:~2,2!
set formatted_time=!hour!:!minute!:!second!

:: Start the Log
echo. >> "%UNRENLOG%"
echo UnRen-%name%.bat !formatted_date! started at !formatted_time! >> "%UNRENLOG%"
echo. >> "%UNRENLOG%"

:: External configuration file for LNG, MDEFS and MDEFS2.
set "UNREN_CFG=%SCRIPTDIR%UnRen-cfg.bat"
:: Load external configuration
if exist "!UNREN_CFG!" (
    call "!UNREN_CFG!"
    if defined LNG goto lngtest
) else (
    :: Set default values in case of missing configuration
    set "MDEFS=acefg"
    set "MDEFS2=12acefg"
)

:: Set the cmd screen size with backup of old settings
set "count=0"
:: Read the lines of mode con
for /f "tokens=*" %%A in ('mode con') do (
    :: Split the line into tokens
    for %%B in (%%A) do (
        set "val=%%B"
        :: Check if it's a number
        echo !val! | findstr /r "[0-9][0-9]" >nul
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
set "NEW_COLS=110"
mode con: cols=%NEW_COLS% lines=62

if defined LNG goto lngtest
:: Get the current code page
for /f "tokens=2 delims=:" %%a in ('chcp') do set "OLD_CP=%%a"
:: Switch to code page 65001 for UTF-8
chcp 65001 >nul

:: Clean retrieval of language code via WMIC
for /f "skip=1 tokens=1" %%l in ('wmic os get oslanguage') do (
    set LNGID=%%l
    goto found_lcid
)

:found_lcid
:: LCID correspondences
if "!LNGID!" == "1033" set LNG=en
if "!LNGID!" == "2052" set LNG=zh
if "!LNGID!" == "1028" set LNG=zh
if "!LNGID!" == "3076" set LNG=zh
if "!LNGID!" == "4100" set LNG=zh
if "!LNGID!" == "5124" set LNG=zh

if not defined LNG set LNG=en

:lngtest
:: Language support test
set "SUPPORTED= en zh "
set "FIND= %LNG% "
echo %SUPPORTED% | find /i "%FIND%" >nul
if !errorlevel! NEQ 0 set LNG=en

:: To be able to take screenshots for F95zone
if not "%~2" == "" (
    set "LNG=%~2"
)


:: Definition of reusable texts
set "ANYKEY.en=Press any key to exit..."
set "ANYKEY.zh=按任意键退出..."

set "ARIGHT.en=Please run this script as an administrator to add the entry."
set "ARIGHT.zh=请以管理员身份运行该脚本以添加该项。"

set "PASS.en=Pass"
set "PASS.zh=成功"

set "FAIL.en=Fail"
set "FAIL.zh=失败"

set "APRESENT.en=Option already presented."
set "APRESENT.zh=选项已存在。"

set "TWADD.en=This will add:"
set "TWADD.zh=将添加："

set "INCASEOF.en=In case of problem, please refer to:"
set "INCASEOF.zh=如遇问题请参考："

set "INCASEDEL.en=In case of problem, delete the following files/dirs:"
set "INCASEDEL.zh=如遇问题，请删除以下文件/目录："

set "UNDWNLD.en=Unable to download:"
set "UNDWNLD.zh=无法下载："

set "UNINSTALL.en=Unable to install:"
set "UNINSTALL.zh=无法安装："

set "UNEXTRACT.en=Unable to extract:"
set "UNEXTRACT.zh=无法解压："

set "MISSING.en=File not found:"
set "MISSING.zh=未找到文件："

set "ENTERYN.en=Enter [y/n] (default n):"
set "ENTERYN.zh=请输入 [y/n]（默认 n）："

set "CLEANUP.en=Cleaning up temporary files..."
set "CLEANUP.zh=正在清理临时文件..."

set "UNACONT.en=Unable to continue."
set "UNACONT.zh=无法继续。"

set "LOGCHK.en=Please check the "%UNRENLOG%" for details."
set "LOGCHK.zh=详情请查看 "%UNRENLOG%"。"

set "DONE.en=Operation completed."
set "DONE.zh=操作完成。"

set "GRY=[90m"
set "RED=[91m"
set "GRE=[92m"
set "YEL=[93m"
set "MAG=[95m"
set "CYA=[96m"
set "RES=[0m"
for /f "tokens=4-5 delims=. " %%i in ('ver') do set OSVERS=%%i.%%j
if "!OSVERS!" == "6.1" (
    set "GRY="
    set "RED="
    set "GRE="
    set "YEL="
    set "MAG="
    set "CYA="
    set "RES="
)
:: End of reusable texts


set "initialized=0"
set "nocls=0"
:menu
:: Splash screen
if "!nocls!" == "0" cls
echo.
echo           %YEL%  ---------------------------------------------------------------------------------%RES%
echo           %YEL%     __  __      ____                  __          __%RES%
echo           %YEL%    / / / /___  / __ \___  ____       / /_  ____ _/ /_%RES%
echo           %YEL%   / / / / __ \/ /_/ / _ \/ __ \     / __ \/ __ ^`/ __/%RES%
echo           %YEL%  / /_/ / / / / _   /  __/ / / / _  / /_/ / /_/ / /_%RES%
echo           %YEL%  \____/_/ /_/_/ \_\\___/_/ /_/ (_) \_.__/\__^,_/\__/ - %NAME% %VERSION%%RES%
echo.
echo           %YEL%       Sam @ www.f95zone.to ^& Gideon%RES%
echo           %YEL%       Modified by joelurmel @ f95zone.to%RES%
echo.
echo           %YEL%  !INCASEOF.%LNG%!%RES%
echo           %MAG%  %URL_REF%%RES%
echo.
set /a rand=%random% %%17
if !rand! == 0 echo           %GRY%  "Hack the planet!" – Dade Murphy%RES%
if !rand! == 1 echo           %GRY%  "Resistance is futile." – Borg%RES%
if !rand! == 2 echo           %GRY%  "There is no spoon." – Neo%RES%
if !rand! == 3 echo           %GRY%  "I'm in." – Mr. Robot%RES%
if !rand! == 4 echo           %GRY%  "All your base are belong to us." – CATS%RES%
if !rand! == 5 echo           %GRY%  "Would you like to know more?" – Various%RES%
if !rand! == 6 echo           %GRY%  "This message will self-destruct in 5... 4... 3..."%RES%
if !rand! == 7 echo           %GRY%  "If you're reading this, you're already better than 90%% of users..."%RES%
if !rand! == 8 echo           %GRY%  "I'm not a hacker. I'm a code poet."%RES%
if !rand! == 9 echo           %GRY%  "Welcome to the command line. Abandon all GUIs, ye who enter here."%RES%
if !rand! == 10 echo          %GRY%  "rm -rf / — because chaos is an art form."%RES%
if !rand! == 11 echo          %GRY%  "This script runs faster than your Wi-Fi on a Monday."%RES%
if !rand! == 12 echo          %GRY%  "The cake is a lie." – Portal%RES%
if !rand! == 13 echo          %GRY%  "I am Groot." – Groot%RES%
if !rand! == 14 echo          %GRY%  "Do or do not. There is no try." – Yoda%RES%
if !rand! == 15 echo          %GRY%  "I know kung fu." – Neo%RES%
if !rand! == 16 echo          %GRY%  "You have been recruited by the Star League to defend the frontier." – The Last Starfighter%RES%
echo           %YEL%  ---------------------------------------------------------------------------------%RES%
echo.

if "!initialized!" == "1" goto skipInit

:: Initializing debug mode
set "DEBUGREDIR=>nul 2>&1"
set "debuglevel=0"
set "nocls=0"

:: We need PowerShell for later, make sure it exists
set "pshell.en=Checking for availability of PowerShell... "
set "pshell.zh=正在检查 PowerShell 是否可用... "

set "pshell1.en=Powershell is required. !UNACONT.%LNG%!"
set "pshell1.zh=需要 PowerShell。!UNACONT.%LNG%!"

set "pshell2.en=This is included in Windows 7, 8 and 10. XP/Vista users can"
set "pshell2.zh=Windows 7/8/10 已内置；XP/Vista 用户可以"

set "pshell3.en=download it here: %MAG%https://learn.microsoft.com/en-us/powershell/scripting/install/installing-powershell-on-windows?view=powershell-7.5%RES%"
set "pshell3.zh=在此下载： %MAG%https://learn.microsoft.com/en-us/powershell/scripting/install/installing-powershell-on-windows?view=powershell-7.5%RES%"

echo !pshell.%LNG%! >> "%UNRENLOG%"
<nul set /p=!pshell.%LNG%!
if not exist "!SystemRoot!\system32\WindowsPowerShell\v1.0\powershell.exe" (
    call :elog "%RED%!FAIL.%LNG%!%RES%"
    call :elog .
    call :elog "    !pshell1.%LNG%!"
    call :elog "    !pshell2.%LNG%!"
    call :elog "    !pshell3.%LNG%!"
    call :elog .
    call :maybe_pause

    call :exitn 3
) else (
    call :elog "%GRE%!PASS.%LNG%!%RES%"
)

:: Analysis of debug arguments
if /i "%~3" == "-d" (
    set "DEBUGREDIR="
    set "debuglevel=1"
    set "nocls=1"
    powershell.exe -Command "$h = Get-Host; $h.UI.RawUI.BufferSize = New-Object Management.Automation.Host.Size(!NEW_COLS!,3000)"
)
if /i "%~3" == "-dd" (
    echo on
    set "DEBUGREDIR="
    set "debuglevel=2"
    set "nocls=1"
    powershell.exe -Command "$h = Get-Host; $h.UI.RawUI.BufferSize = New-Object Management.Automation.Host.Size(!NEW_COLS!,5000)"
)


:: Set the working directory
set "setpath1.en=Enter the path to the game, drag'n'drop it here,"
set "setpath1.zh=请输入游戏路径，可将文件夹拖拽到此处，"

set "setpath2.en=or press Enter if this tool is already in the desired folder."
set "setpath2.zh=或如果该工具已在目标目录中，直接回车。"

set "setpath3.en=If drag'n'drop does not work, please copy/paste the path instead: "
set "setpath3.zh=如果拖拽无效，请复制/粘贴路径： "

:: Check if game path is provided and set it
set "WORKDIR="
if "%~1" == "" (
    call :elog .
    call :elog "!setpath1.%LNG%!"
    call :elog "!setpath2.%LNG%!"
    call :elog .
    set /p "WORKDIR=!setpath3.%LNG%!"
    if not defined WORKDIR (
        set "WORKDIR=!cd!"
    )
) else (
    set "WORKDIR=%~1"
    if "!WORKDIR!" == "." (
        set "WORKDIR=!cd!"
    )
)

:: Remove surrounding quotes if any
set "WORKDIR=%WORKDIR:"=%"

:: Normalize WORKDIR to an absolute path
for %%A in ("!WORKDIR!") do set "WORKDIR=%%~fA"

set "invchars.en=Invalid character detected in the path..."
set "invchars.zh=路径中检测到非法字符..."
set "HAS_BAD="
:: Characters that CAN appear in a valid Windows path but WILL break batch logic:
for %%C in ("=" ";" "'" "`" "[" "]" "{" "}" "+" "," "~") do (
    echo "!WORKDIR!" | find "%%~C" >nul && set "HAS_BAD=%%~C"
)

if defined HAS_BAD (
    call :elog .
    call :elog "%RED%'!HAS_BAD!' - !invchars.%LNG%!%RES% !UNACONT.%LNG%!"
    call :elog .
    call :maybe_pause

    call :exitn 3
)

set "wdir1.en=Error The specified directory does not exist."
set "wdir1.zh=错误：指定的目录不存在。"

set "wdir2.en=Are you sure we're in the game's root directory?"
set "wdir2.zh=请确认当前是否为游戏根目录？"

set "wdir3.en=Testing write access to game directory"
set "wdir3.zh=正在测试游戏目录写入权限"

set "wdir4.en=You can't write in game directory."
set "wdir4.zh=无法写入游戏目录。"

cd /d "%WORKDIR%"
if !errorlevel! NEQ 0 (
    call :elog .
    call :elog "    %RED%!wdir1.%LNG%!%RES%"
    call :elog "    !wdir2.%LNG%!"
    call :elog .
    call :maybe_pause

    call :exitn 3
)

:: Check if an update is available
if defined UNREN_NO_UPDATE (
    rem skip update check in automation/headless mode
) else (
    call :check_update
)

:: Check for required files
call :check_all_files


set "reqdir1.en=Checking if game, lib, renpy directories exist..."
set "reqdir1.zh=正在检查 game、lib、renpy 目录是否存在..."

set "reqdir2.en=Cannot locate game, lib or renpy directories. !UNACONT.%LNG%!"
set "reqdir2.zh=无法找到 game、lib 或 renpy 目录。!UNACONT.%LNG%!"

:: Check that you are in the root directory of the game.
cd /d "%WORKDIR%"
echo !reqdir1.%LNG%! >> "%UNRENLOG%"
<nul set /p=!reqdir1.%LNG%!
set missing=0
if not exist ".\game" (
    set missing=1
)
if not exist ".\lib" (
    set missing=1
)
if not exist ".\renpy" (
    set missing=1
)
if !missing! EQU 1 (
    call :elog " %RED%!FAIL.%LNG%!%RES%"
    call :elog "    !reqdir2.%LNG%!"
    call :elog "    !wdir2.%LNG%!"
    call :elog .
    call :maybe_pause

    call :exitn 3
) else (
    call :elog " %GRE%!PASS.%LNG%!%RES%"
)

:: Check if %WORKDIR%\game is writable
echo !wdir3.%LNG%!... >> "%UNRENLOG%"
<nul set /p="!wdir3.%LNG%!... "
copy nul "%WORKDIR%\game\test.txt" %DEBUGREDIR%
if !errorlevel! NEQ 0 (
    call :elog "%RED%!FAIL.%LNG%! %YEL%!wdir4.%LNG%!%RES%"
    call :elog .
    call :elog "    !wdir2.%LNG%!"
    call :elog .
    call :maybe_pause

    call :exitn 3
) else (
    del /f /q "!WORKDIR!\game\test.txt" %DEBUGREDIR%
    call :elog "%GRE%!PASS.%LNG%!%RES%"
)


:: Set UNRENLOG for debugging purpose
If exist "!TEMP!\UnRen-forall.log" (
    :: Move the temporary log file to the working directory
    move /y "!TEMP!\UnRen-forall.log" "!WORKDIR!\UnRen-forall.log" %DEBUGREDIR%
)
set "UNRENLOG=%WORKDIR%\UnRen-forall.log"
set "UNRENLOG=%UNRENLOG:"=%"

:: Check for Python
set "python1.en=Checking if Python is available..."
set "python1.zh=正在检查 Python 是否可用..."

set "python2.en=Cannot locate python directory. !UNACONT.%LNG%!"
set "python2.zh=无法定位 python 目录。!UNACONT.%LNG%!"

echo !python1.%LNG%! >> "%UNRENLOG%"
<nul set /p=!python1.%LNG%!

:: Doublecheck to avoid issues with Milfania games
if exist "!WORKDIR!\lib\py3-windows-x86_64\pythonw.exe" if exist "!WORKDIR!\lib\py3-windows-x86_64\python.exe" (
    if not "!PROCESSOR_ARCHITECTURE!" == "x86" (
        <nul set /p=.
        set "PYTHONHOME=!WORKDIR!\lib\py3-windows-x86_64\"
    ) else if exist "!WORKDIR!\lib\py3-windows-i686\python.exe" (
        <nul set /p=.
        set "PYTHONHOME=!WORKDIR!\lib\py3-windows-i686\"
    )
) else if exist "!WORKDIR!\lib\py3-windows-i686\python.exe" (
    <nul set /p=.
    set "PYTHONHOME=!WORKDIR!\lib\py3-windows-i686\"
)
if exist "!WORKDIR!\lib\py2-windows-x86_64\python.exe" (
    if not "!PROCESSOR_ARCHITECTURE!" == "x86" (
        <nul set /p=.
        set "PYTHONHOME=!WORKDIR!\lib\py2-windows-x86_64\"
    ) else if exist "!WORKDIR!\lib\py2-windows-i686\python.exe" (
        <nul set /p=.
        set "PYTHONHOME=!WORKDIR!\lib\py2-windows-i686\"
    )
) else if exist "!WORKDIR!\lib\py2-windows-i686\python.exe" (
    <nul set /p=.
    set "PYTHONHOME=!WORKDIR!\lib\py2-windows-i686\"
)
if exist "!WORKDIR!\lib\windows-x86_64\python.exe" (
    if not "!PROCESSOR_ARCHITECTURE!" == "x86" (
        <nul set /p=.
        set "PYTHONHOME=!WORKDIR!\lib\windows-x86_64\"
    ) else if exist "!WORKDIR!\lib\windows-i686\python.exe" (
        <nul set /p=.
        set "PYTHONHOME=!WORKDIR!\lib\windows-i686\"
    )
) else if exist "!WORKDIR!\lib\windows-i686\python.exe" (
    <nul set /p=.
    set "PYTHONHOME=!WORKDIR!\lib\windows-i686\"
)

:: Set the PYNOASSERT according to “!PYTHONHOME!Lib”.
if exist "!PYTHONHOME!Lib" (
    set "PYNOASSERT=-O"
) else (
    set "PYNOASSERT="
)

set "PYTHONPATH=%PYTHONHOME%"
set "latest="
set "latestver="

:: Priority to Python 2.7 if present
if exist "!WORKDIR!\lib\pythonlib2.7" (
    <nul set /p=.
    set "PYTHONPATH=!WORKDIR!\lib\pythonlib2.7"
    set "PYVERS=2.7"
    goto pyend
) else if exist "!WORKDIR!\lib\python2.7" (
    <nul set /p=.
    set "PYTHONPATH=!WORKDIR!\lib\python2.7"
    set "PYVERS=2.7"
    goto pyend
)

:: Searching for the latest version of Python 3.x
for /D %%D in ("!WORKDIR!\lib\python3.*") do (
    <nul set /p=.
    set "ver=%%~nxD"
    set "found="
    for %%M in (os importlib encodings) do (
        if exist "%%D\%%M" (
            set "found=1"
        )
    )
    if defined found (
        for /f "tokens=2 delims=." %%V in ("!ver!") do (
            <nul set /p=.
            if not defined latest (
                set "latest=%%D"
                set "latestver=%%V"
                set "PYVERS=3.%%V"
            ) else (
                if %%V GTR !latestver! (
                    set "latest=%%D"
                    set "latestver=%%V"
                    set "PYVERS=3.%%V"
                )
            )
        )
    )
)

if defined latest (
    <nul set /p=.
    set "PYTHONPATH=!latest!"
)

:pyend
if not exist "!PYTHONHOME!\python.exe" (
    call :elog " %RED%!FAIL.%LNG%!%RES%"
    call :elog .
    call :elog "    %RED%!python2.%LNG%!%RES%"
    call :elog "    !wdir2.%LNG%!"
    call :elog .
    call :maybe_pause

    call :exitn 3
) else (
    call :elog " %GRE%!PASS.%LNG%!%YEL% Python !PYVERS!%RES%"
)

echo Check Python Version... >> "%UNRENLOG%"
for /f "tokens=2 delims= " %%a in ('"!PYTHONHOME!\python" -V 2^>^&1') do set PYTHONVERS=%%a
:: Extraction of major and minor versions
for /f "tokens=1,2 delims=." %%b in ("!PYTHONVERS!") do (
    set PYTHONMAJOR=%%b
    set PYTHONMINOR=%%c
)

:: Check if Python ^>= 3.8
if !PYTHONMAJOR! GEQ 3 (
	if !PYTHONMINOR! GEQ 8 (
		echo Python version is !PYTHONVERS!, which is upper or equal to 3.8 >> "%UNRENLOG%"
    	set "RPATOOL-NEW=y"
	) else (
		echo Python version is !PYTHONVERS!, which is lower than 3.8 >> "%UNRENLOG%"
		set "RPATOOL-NEW=n"
	)
) else (
	echo Python version is !PYTHONVERS!, which is lower than 3 >> "%UNRENLOG%"
    set "RPATOOL-NEW=n"
)

:: Check for Ren'Py version
set "renpyvers1.en=Ren'Py version found: "
set "renpyvers1.zh=检测到 Ren'Py 版本："

set "renpyvers2.en=Failed to create detect_renpy_version.py. !UNACONT.%LNG%!"
set "renpyvers2.zh=无法创建 detect_renpy_version.py。!UNACONT.%LNG%!"

set "renpyvers3.en=Unable to detect Ren'Py version,"
set "renpyvers3.zh=无法检测 Ren'Py 版本，"

set "renpyvers4.en=        please ensure the game is compatible with UnRen."
set "renpyvers4.zh=        请确保该游戏与 UnRen 兼容。"

echo !renpyvers1.%LNG%! >> "%UNRENLOG%"
<nul set /p=!renpyvers1.%LNG%!

cd /d "%WORKDIR%"
set "detect_renpy_version_py=detect_renpy_version.py"
del /f /q "%detect_renpy_version_py%" %DEBUGREDIR%
>"%detect_renpy_version_py%.b64" (
    echo IyEvdXNyL2Jpbi9lbnYgcHl0aG9uDQojIC0qLSBjb2Rpbmc6IHV0Zi04IC0qLQ0KaW1wb3J0IG9zDQppbXBvcnQgc3lzDQppbXBvcnQgcmUNCg0KIyAtLS0gMS4gU3RhbmRhcmQgbWV0aG9kOiBpbXBvcnQgcmVucHkgLS0tDQp0cnk6DQogICAgaW1wb3J0IHJlbnB5DQogICAgcHJpbnQocmVucHkudmVyc2lvbl90dXBsZVswXSkNCiAgICBzeXMuZXhpdCgwKQ0KZXhjZXB0IEV4Y2VwdGlvbjoNCiAgICBwYXNzICAjIGZhbGxiYWNrIGJlbG93DQoNCiMgLS0tIDIuIEZhbGxiYWNrOiByZWFkIHJlbnB5L3ZlcnNpb24ucHkgbWFudWFsbHkgLS0tDQp2ZXJzaW9uX2ZpbGUgPSBvcy5wYXRoLmpvaW4oInJlbnB5IiwgInZlcnNpb24ucHkiKQ0KDQpkZWYgcmVhZF9maWxlX2NvbXBhdChwYXRoKToNCiAgICAiIiJVVEYtOCByZWFkaW5nIGNvbXBhdGlibGUgd2l0aCBQeXRob24gMiBhbmQgMy4iIiINCiAgICBpZiBzeXMudmVyc2lvbl9pbmZvWzBdIDwgMzoNCiAgICAgICAgaW1wb3J0IGNvZGVjcw0KICAgICAgICB3aXRoIGNvZGVjcy5vcGVuKHBhdGgsICJyIiwgInV0Zi04IikgYXMgZjoNCiAgICAgICAgICAgIHJldHVybiBmLnJlYWQoKQ0KICAgIGVsc2U6DQogICAgICAgIHdpdGggb3BlbihwYXRoLCAiciIsIGVuY29kaW5nPSJ1dGYtOCIsIGVycm9ycz0iaWdub3JlIikgYXMgZjoNCiAgICAgICAgICAgIHJldHVybiBmLnJlYWQoKQ0KDQppZiBvcy5wYXRoLmV4aXN0cyh2ZXJzaW9uX2ZpbGUpOg0KICAgIHRyeToNCiAgICAgICAgdHh0ID0gcmVhZF9maWxlX2NvbXBhdCh2ZXJzaW9uX2ZpbGUpDQoNCiAgICAgICAgIyBTZWFyY2ggdmVyc2lvbl90dXBsZSA9ICg4LCAzLCA0LCAuLi4pDQogICAgICAgIG0gPSByZS5zZWFyY2gociJ2ZXJzaW9uX3R1cGxlXHMqPVxzKlwoXHMqKFxkKykiLCB0eHQpDQogICAgICAgIGlmIG06DQogICAgICAgICAgICBwcmludChtLmdyb3VwKDEpKQ0KICAgICAgICAgICAgc3lzLmV4aXQoMCkNCg0KICAgICAgICAjIFNlYXJjaCB2ZXJzaW9uID0gIjguMy40Ig0KICAgICAgICBtID0gcmUuc2VhcmNoKHIndmVyc2lvblxzKj1ccypbIlwnXShcZCspXC4nLCB0eHQpDQogICAgICAgIGlmIG06DQogICAgICAgICAgICBwcmludChtLmdyb3VwKDEpKQ0KICAgICAgICAgICAgc3lzLmV4aXQoMCkNCg0KICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToNCiAgICAgICAgc3lzLnN0ZGVyci53cml0ZSgiRXJyb3IgcmVhZGluZyB2ZXJzaW9uLnB5OiAlc1xuIiAlIGUpDQoNCiMgLS0tIDMuIElmIGV2ZXJ5dGhpbmcgZmFpbHMgLS0tDQpwcmludCgiRVJST1IiKQ0K
)
powershell.exe -nologo -noprofile -noninteractive -command "[IO.File]::WriteAllText('%detect_renpy_version_py%.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '%detect_renpy_version_py%.b64'))))" %DEBUGREDIR%
if exist "!detect_renpy_version_py!.tmp" (
    del /f /q "!detect_renpy_version_py!.b64" %DEBUGREDIR%
    move /y "!detect_renpy_version_py!.tmp" "!detect_renpy_version_py!" %DEBUGREDIR%
) else (
    call :elog "%RED%!FAIL.%LNG%!%RES%"
    call :elog .
    call :elog "%RED%!renpyvers2.%LNG%!%RES%"
    call :elog .
    call :maybe_pause

    call :exitn 3
)

if not exist "!detect_renpy_version_py!" (
    call :elog "%RED%!FAIL.%LNG%!%RES%"
    call :elog .
    call :elog "!renpyvers2.%LNG%!"
    call :elog .
    call :maybe_pause

    call :exitn 3
) else (
    for /f "delims=" %%A in ('"!PYTHONHOME!\python.exe" !PYNOASSERT! !detect_renpy_version_py!') do (
        echo %%A | findstr /r "[0-9]" >nul
        if !errorlevel! EQU 0 (
            set "RENPYVERSION=%%A"
        )
    )
    if not defined RENPYVERSION (
        call :elog "%RED%!FAIL.%LNG%!%RES%"
        call :elog .
        call :elog "    %RED%!renpyvers3.%LNG%!%RES%"
        call :elog "    %RED%!renpyvers4.%LNG%!%RES%"
    ) else (
        call :elog "%YEL%!RENPYVERSION!%RES%"
    )
)
del /f /q "%detect_renpy_version_py%" %DEBUGREDIR%

set "renpyvers5.en=You have lauched %SCRIPTNAME% but Ren'Py !RENPYVERSION! is found. Please use UnRen-legacy.bat instead."
set "renpyvers5.zh=你启动了 %SCRIPTNAME%，但检测到 Ren'Py !RENPYVERSION!。请改用 UnRen-legacy.bat。"

set "renpyvers6.en=You have lauched %SCRIPTNAME% but Ren'Py !RENPYVERSION! is found. Please use UnRen-current.bat instead."
set "renpyvers6.zh=你启动了 %SCRIPTNAME%，但检测到 Ren'Py !RENPYVERSION!。请改用 UnRen-current.bat。"
:: Check to ensure you are using the correct UnRen version
if !RENPYVERSION! LSS 7 (
    call :elog .
    call :elog "!renpyvers5.%LNG%!"
    call :elog .

    timeout /t 10 /nobreak >nul

    call :exitn 3
)

call :DisplayVars "Init phase"

set "def=5"
set initialized=1

:SkipInit
set "mtitle.en=Working directory: "
set "mtitle.zh=工作目录： "

set "choice1.en=Unpack RPA packages."
set "choice1.zh=解包 RPA 包。"

set "choice2.en=Decompile RPYC files."
set "choice2.zh=反编译 RPYC 文件。"

set "choice3.en=Deobfuscate when unpacking RPA files %YEL%(Use basic code)"
set "choice3.zh=解包 RPA 时去混淆 %YEL%(使用基础方式)"

set "choice4.en=Deobfuscate when decompile RPYC files %YEL%(Use basic code)"
set "choice4.zh=反编译 RPYC 时去混淆 %YEL%(使用基础方式)"

set "choice5.en=Unpack and decompile (RPA and RPYC)"
set "choice5.zh=解包并反编译（RPA 与 RPYC）"

set "choice6.en=Deobfuscate, unpack and decompile for both RPA and RPYC files %YEL%(Use basic code)"
set "choice6.zh=去混淆+解包+反编译（RPA 与 RPYC）%YEL%(使用基础方式)"

set "choice7.en=Unpack RPA packages using alternative method."
set "choice7.zh=使用替代方法解包 RPA。"

set "minfo1.en=The following options are independent of the Ren'Py version."
set "minfo1.zh=以下选项与 Ren'Py 版本无关。"

set "choicea.en=Enable Console (Shift+O) and Developer menu (Shift+D)"
set "choicea.zh=启用控制台（Shift+O）和开发者菜单（Shift+D）"

set "choiceb.en=Enable debug mode %RED%(Can break your game)"
set "choiceb.zh=启用调试模式 %RED%(可能导致游戏异常)"

set "choicec.en=Force Skip (Unseen Text, After Choices)"
set "choicec.zh=强制跳过（未读文本、选项后）"

set "choiced.en=Force all Skip (Unseen Text, After Choices, Transitions)"
set "choiced.zh=强制全部跳过（未读文本、选项后、转场）"

set "choicee.en=Force enable rollback (scroll wheel)"
set "choicee.zh=强制启用回滚（鼠标滚轮）"

set "choicef.en=Enable Quick Save and Quick Load (Shift+S F5, Shift+L F9)"
set "choicef.zh=启用快速保存/快速读取（Shift+S F5，Shift+L F9）"

set "choiceg.en=Try forcing the Quick Menu to display."
set "choiceg.zh=尝试强制显示快捷菜单。"

set "choiceh.en=Download and add Universal Gallery Unlocker ZLZK"
set "choiceh.zh=下载并添加 Universal Gallery Unlocker ZLZK"

set "choicei.en=Download and add Universal Choice Descriptor ZLZK"
set "choicei.zh=下载并添加 Universal Choice Descriptor ZLZK"

set "choicej.en=Download and add Universal Transparent Text Box Mod by Penfold Mole"
set "choicej.zh=下载并添加 Penfold Mole 的透明文本框 Mod"

set "choicek.en=Download and add "0x52_URM by 0x52""
set "choicek.zh=下载并添加 "0x52_URM by 0x52""

set "choicel.en=Rename MC name with a new name"
set "choicel.zh=将主角名重命名为新名字"

set "choicet.en=Extract text for translation purposes"
set "choicet.zh=为翻译用途提取文本"

set "minfo2.en=The following choices require administrative privileges."
set "minfo2.zh=以下选项需要管理员权限。"

set "choice+.en=Add a right-click menu entry for folders to run the script."
set "choice+.zh=添加右键菜单项（文件夹）以运行该脚本。"

set "choice-.en=Remove the right-click menu entry from the registry."
set "choice-.zh=从注册表移除右键菜单项。"

set "mquest.en=Your choice (1-6,a-l,t,+,- by default [%MDEFS2%]): "
set "mquest.zh=请选择（1-6,a-l,t,+,-；默认 [%MDEFS2%]）： "

set "choicex.en=Exit"
set "choicex.zh=退出"

set "uchoice.en=Unknown choice:"
set "uchoice.zh=未知选项："

:: Menu display
call :elog .
call :elog .
call :elog "!mtitle.%LNG%!%YEL%%WORKDIR%%RES%"
call :elog .
echo        1) %GRE%!choice1.%LNG%!%RES%
echo        2) %GRE%!choice2.%LNG%!%RES%
echo        3) %GRY%!choice3.%LNG%!%RES%
echo        4) %GRE%!choice4.%LNG%!%RES%
echo        5) %GRE%!choice5.%LNG%!%RES%
echo        6) %GRY%!choice6.%LNG%!%RES%
echo        7) %GRY%!choice7.%LNG%!%RES%
call :elog .
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
echo        t) %CYA%!choicet.%LNG%!%RES%
call :elog .
echo        %YEL%!minfo2.%LNG%!%RES%
echo        +) %CYA%!choice+.%LNG%!%RES%
echo        -) %CYA%!choice-.%LNG%!%RES%
call :elog .
echo        x) %YEL%!choicex.%LNG%!%RES%

:: Reading the selection
echo.
echo.
set "OPTIONS="
if defined UNREN_AUTORUN (
    set "OPTIONS=!UNREN_AUTORUN!"
) else (
    set /p "OPTIONS=!mquest.%LNG%!"
    if not defined OPTIONS set "OPTIONS=!MDEFS2!"
)
set "OPTIONS=%OPTIONS: =%"

:: Loop through each character in the input
:: First, check for invalid characters
set "VALID=1234567abctdefghijklt+-x"
for /L %%I in (0,1,15) do (
    set "CHAR=!OPTIONS:~%%I,1!"
    if "!CHAR!"=="" goto end_check
    echo "!VALID!" | findstr /C:"!CHAR!" >nul || (
        echo.
        echo.
        echo %RED%!uchoice.%LNG%! %YEL%!CHAR!%RES%
        timeout /t 2 >nul
        echo.
    )
)
:end_check

:: Now process each valid character
for %%C in (1 2 3 4 5 6 7 a b c d e f g h i j k l t + - x) do (
    echo !OPTIONS! | find /i "%%C" >nul
    if !errorlevel! EQU 0 (
        set "OPTION=%%C"
        if "!OPTION!" == "1" call :extract
        if "!OPTION!" == "2" call :decompile
        if "!OPTION!" == "3" call :unavailable REM :extract_wkey
        if "!OPTION!" == "4" call :decompile
        if "!OPTION!" == "5" call :extract
        if "!OPTION!" == "6" call :unavailable REM :extract_wkey
        if "!OPTION!" == "7" call :extract

        if /i "!OPTION!" == "a" call :console
        if /i "!OPTION!" == "b" call :debug
        if /i "!OPTION!" == "c" call :skip
        if /i "!OPTION!" == "d" call :skipall
        if /i "!OPTION!" == "e" call :rollback
        if /i "!OPTION!" == "f" call :quick
        if /i "!OPTION!" == "g" call :qmenu
        if /i "!OPTION!" == "h" call :add_ugu
        if /i "!OPTION!" == "i" call :add_ucd
        if /i "!OPTION!" == "j" call :add_utbox
        if /i "!OPTION!" == "k" call :add_urm
        if /i "!OPTION!" == "l" call :replace_mcname
        if /i "!OPTION!" == "t" call :extract_text

        if "!OPTION!" == "+" call :add_reg
        if "!OPTION!" == "-" call :remove_reg

        if /i "!OPTION!" == "x" goto exitn
    )
)

set "MDEFS2=x"
echo.
echo.
timeout /t 2 >nul

goto menu


:extract
set "extm1.en=Remove RPA archives after extraction? Enter [y/n] (default n): "
set "extm1.zh=解包后是否删除 RPA 归档？请输入 [y/n]（默认 n）： "

set "extm2.en=RPA archives will be moved to %WORKDIR%\rpa."
set "extm2.zh=RPA 归档将移动到 %WORKDIR%\rpa。"

set "extm3.en=RPA archives will be deleted after extraction."
set "extm3.zh=RPA 归档将在解包后删除。"

set "extm4.en=Unpack all or select RPA archives? Enter [a/s] (default a): "
set "extm4.zh=解包全部还是选择部分 RPA？请输入 [a/s]（默认 a）： "

set "extm5.en=You will select the RPA archives to unpack."
set "extm5.zh=你将选择要解包的 RPA 归档。"

set "extm6.en=All RPA archives will be unpacked."
set "extm6.zh=将解包所有 RPA 归档。"

set "extm7.en=Failed to create:"
set "extm7.zh=创建失败："

set "extm8.en=Searching for RPA files in the game directory..."
set "extm8.zh=正在在 game 目录中搜索 RPA 文件..."

set "extm9.en=Creating rpatool and altrpatool..."
set "extm9.zh=正在创建 rpatool 和 altrpatool..."

set "extm10.en=RPA extension renamed to:"
set "extm10.zh=RPA 扩展名已重命名为："

set "extm11.en=No RPA archive detected."
set "extm11.zh=未检测到 RPA 归档。"

set "extm12.en=Error processing RPA files in"
set "extm12.zh=处理 RPA 文件出错："

:: set extm13 to extm16 are set later in the code because of the dynamic variables.

set "extm16.en=Unpacking file:"
set "extm16.zh=正在解包文件："

set "extm17.en=Do you want to unpack the RPA archive:"
set "extm17.zh=是否解包该 RPA 归档："

:: set extm18 to extm24 are set later in the code because of the dynamic variables.

set "extm25.en=Extension found:"
set "extm25.zh=检测到扩展名："

:: set extm26 are set later in the code because of the dynamic variables.

call :DisplayVars "RPA extract phase"

:: Detect RPA extension
set "rpaExt="

:: Create Python script to detect RPA extension
set "detect_rpa_ext_py=%WORKDIR%\detect_rpa_ext.py"
>"%detect_rpa_ext_py%.b64" (
    echo IyEvdXNyL2Jpbi9lbnYgcHl0aG9uDQojIC0qLSBjb2Rpbmc6IHV0Zi04IC0qLQ0KDQojIFdyaXR0ZW4gYnkgU00gYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCiMgVmVyc2lvbiAwLjIgLSAyMDI1LTEyLTE5DQoNCmZyb20gX19mdXR1cmVfXyBpbXBvcnQgcHJpbnRfZnVuY3Rpb24NCmltcG9ydCBvcw0KaW1wb3J0IHN5cw0KDQpkZWYgbm9ybWFsaXplX3BhdGgoYXJnKToNCiAgICAjIFN0cmlwIHN1cnJvdW5kaW5nIHF1b3RlcyBhbmQgd2hpdGVzcGFjZQ0KICAgIHAgPSBhcmcuc3RyaXAoKS5zdHJpcCgnXCciJykNCiAgICAjIE9uIFdpbmRvd3MsIGEgdHJhaWxpbmcgZG90IG9yIHNwYWNlIGNhbiBhbHNvIGJlIHByb2JsZW1hdGljLA0KICAgICMgYnV0IHdlIGxlYXZlIHRoZW0gdW5sZXNzIHRoZXkgY2xlYXJseSBjb21lIGZyb20gcXVvdGluZyBpc3N1ZXMuDQogICAgcmV0dXJuIHANCg0KaWYgbGVuKHN5cy5hcmd2KSA+IDE6DQogICAgcmF3ID0gc3lzLmFyZ3ZbMV0NCiAgICBnYW1lX2RpciA9IG5vcm1hbGl6ZV9wYXRoKHJhdykNCmVsc2U6DQogICAgZ2FtZV9kaXIgPSBvcy5nZXRjd2QoKQ0KDQojIENoYW5nZSB3b3JraW5nIGRpcmVjdG9yeSBzbyBSZW4nUHkgY2FuIGxvY2F0ZSBpdHMgaW50ZXJuYWwgcmVzb3VyY2VzDQpnYW1lX2RpciA9IG9zLnBhdGguYWJzcGF0aChnYW1lX2RpcikNCm9zLmNoZGlyKGdhbWVfZGlyKQ0KDQoNCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tDQojIFRyeSB0byBsb2FkIFJlbidQeSBhcmNoaXZlIGhhbmRsZXJzIHNhZmVseQ0KIyBUaGlzIHVzZXMgdGhlIGltcG9ydCBvcmRlciB5b3UgZGlzY292ZXJlZCwgd3JhcHBlZCBpbiB0cnkvZXhjZXB0IHNvIHRoYXQNCiMgYW55IHBvaXNvbmVkIG9yIGJsYWNrbGlzdGVkIG1vZHVsZSB3b24ndCBjcmFzaCB0aGUgc2NyaXB0Lg0KIyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0NCmRlZiB0cnlfcmVucHlfaGFuZGxlcnMoKToNCiAgICB0cnk6DQogICAgICAgIGltcG9ydCByZW5weS5vYmplY3QNCiAgICAgICAgaW1wb3J0IHJlbnB5LmxvYWRlcg0KDQogICAgICAgICMgVGhlc2UgdHdvIG1heSBmYWlsIGRlcGVuZGluZyBvbiB0aGUgZ2FtZTsgdGhleSBhcmUgb3B0aW9uYWwNCiAgICAgICAgdHJ5Og0KICAgICAgICAgICAgaW1wb3J0IHJlbnB5LmVycm9yDQogICAgICAgICAgICBpbXBvcnQgcmVucHkuY29uZmlnDQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb246DQogICAgICAgICAgICBwYXNzDQoNCiAgICAgICAgIyBSZXRyaWV2ZSBhcmNoaXZlIGhhbmRsZXJzIChtYXkgYmUgYSB3cmFwcGVyIG9yIGEgbGlzdCkNCiAgICAgICAgdHJ5Og0KICAgICAgICAgICAgYWggPSByZW5weS5sb2FkZXIuYXJjaGl2ZV9oYW5kbGVycw0KICAgICAgICBleGNlcHQgRXhjZXB0aW9uOg0KICAgICAgICAgICAgcmV0dXJuIE5vbmUNCg0KICAgICAgICBoYW5kbGVycyA9IGdldGF0dHIoYWgsICJoYW5kbGVycyIsIGFoKQ0KDQogICAgICAgIGV4dHMgPSBbXQ0KICAgICAgICB0cnk6DQogICAgICAgICAgICBmb3IgaCBpbiBoYW5kbGVyczoNCiAgICAgICAgICAgICAgICAjIFJlbidQeSA3LnggLyA4LngNCiAgICAgICAgICAgICAgICBpZiBoYXNhdHRyKGgsICJnZXRfc3VwcG9ydGVkX2V4dGVuc2lvbnMiKToNCiAgICAgICAgICAgICAgICAgICAgZXh0cy5leHRlbmQoaC5nZXRfc3VwcG9ydGVkX2V4dGVuc2lvbnMoKSkNCiAgICAgICAgICAgICAgICAjIFJlbidQeSA2LngNCiAgICAgICAgICAgICAgICBlbGlmIGhhc2F0dHIoaCwgImdldF9zdXBwb3J0ZWRfZXh0Iik6DQogICAgICAgICAgICAgICAgICAgIGV4dHMuZXh0ZW5kKGguZ2V0X3N1cHBvcnRlZF9leHQoKSkNCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoNCiAgICAgICAgICAgIHJldHVybiBOb25lDQoNCiAgICAgICAgIyBEZWR1cGxpY2F0ZSBhbmQgc2FuaXRpemUNCiAgICAgICAgZXh0cyA9IHNvcnRlZChzZXQoZSBmb3IgZSBpbiBleHRzIGlmIGlzaW5zdGFuY2UoZSwgKHN0ciwgYnl0ZXMpKSkpDQogICAgICAgIHJldHVybiBleHRzIG9yIE5vbmUNCg0KICAgIGV4Y2VwdCBFeGNlcHRpb246DQogICAgICAgIHJldHVybiBOb25lDQoNCg0KIyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0NCiMgRmFsbGJhY2s6IHNjYW4gdGhlIGZpbGVzeXN0ZW0gZm9yIGFyY2hpdmUtbGlrZSBleHRlbnNpb25zDQojIE9ubHkgc2NhbnMgdGhlIGdhbWUgZGlyZWN0b3J5IGFuZCBjdXJyZW50IGRpcmVjdG9yeSAodmVyeSBmYXN0KS4NCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tDQpkZWYgc2Nhbl9wcmVzZW50X2FyY2hpdmVzKGJhc2VfZGlyKToNCiAgICBleHRzID0gc2V0KCkNCg0KICAgIGRlZiBzY2FuKGQpOg0KICAgICAgICB0cnk6DQogICAgICAgICAgICBmb3IgbmFtZSBpbiBvcy5saXN0ZGlyKGQpOg0KICAgICAgICAgICAgICAgIGZ1bGwgPSBvcy5wYXRoLmpvaW4oZCwgbmFtZSkNCiAgICAgICAgICAgICAgICBpZiBub3Qgb3MucGF0aC5pc2ZpbGUoZnVsbCk6DQogICAgICAgICAgICAgICAgICAgIGNvbnRpbnVlDQogICAgICAgICAgICAgICAgcm9vdCwgZXh0ID0gb3MucGF0aC5zcGxpdGV4dChuYW1lKQ0KICAgICAgICAgICAgICAgICMgS2VlcCBzaG9ydCBleHRlbnNpb25zIG9ubHkgKC5ycGEsIC5ycHgsIC5ycGssIGV0Yy4pDQogICAgICAgICAgICAgICAgaWYgZXh0IGFuZCBsZW4oZXh0KSA8PSA2Og0KICAgICAgICAgICAgICAgICAgICBleHRzLmFkZChleHQubG93ZXIoKSkNCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoNCiAgICAgICAgICAgIHBhc3MNCg0KICAgIHNjYW4oYmFzZV9kaXIpDQogICAgZ2FtZV9zdWIgPSBvcy5wYXRoLmpvaW4oYmFzZV9kaXIsICJnYW1lIikNCiAgICBpZiBvcy5wYXRoLmlzZGlyKGdhbWVfc3ViKToNCiAgICAgICAgc2NhbihnYW1lX3N1YikNCg0KICAgIHJldHVybiBzb3J0ZWQoZXh0cykNCg0KDQojIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQ0KIyBIeWJyaWQgZGV0ZWN0aW9uIHN0cmF0ZWd5DQojIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQ0KZGVmIGRldGVjdF9hcmNoaXZlX2V4dGVuc2lvbnMoYmFzZV9kaXIpOg0KICAgICMgMSkgVHJ5IFJlbidQeSBoYW5kbGVycw0KICAgIGV4dHMgPSB0cnlfcmVucHlfaGFuZGxlcnMoKQ0KICAgIGlmIGV4dHM6DQogICAgICAgIHJldHVybiBleHRzDQoNCiAgICAjIDIpIFRyeSBzY2FubmluZyB0aGUgZmlsZXN5c3RlbQ0KICAgIGV4dHMgPSBzY2FuX3ByZXNlbnRfYXJjaGl2ZXMoYmFzZV9kaXIpDQogICAgaWYgZXh0czoNCiAgICAgICAgcmV0dXJuIGV4dHMNCg0KICAgICMgMykgRmluYWwgZmFsbGJhY2sNCiAgICByZXR1cm4gWyIucnBhIl0NCg0KDQojIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQ0KIyBNYWluIGVudHJ5IHBvaW50DQojIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQ0KZGVmIG1haW4oKToNCiAgICBleHRzID0gZGV0ZWN0X2FyY2hpdmVfZXh0ZW5zaW9ucyhnYW1lX2RpcikNCg0KICAgICMgUHl0aG9uIDIvMyBzYWZlIG91dHB1dA0KICAgIHRyeToNCiAgICAgICAgb3V0ID0gc3lzLnN0ZG91dA0KICAgICAgICBpZiBoYXNhdHRyKG91dCwgImJ1ZmZlciIpOg0KICAgICAgICAgICAgb3V0LmJ1ZmZlci53cml0ZSgocmVwcihleHRzKSArICJcbiIpLmVuY29kZSgidXRmLTgiLCAicmVwbGFjZSIpKQ0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgcHJpbnQocmVwcihleHRzKSkNCiAgICBleGNlcHQgRXhjZXB0aW9uOg0KICAgICAgICBwcmludChleHRzKQ0KDQogICAgc3lzLmV4aXQoMCBpZiBleHRzIGVsc2UgMSkNCg0KDQppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOg0KICAgIG1haW4oKQ0K
)
if not exist "!detect_rpa_ext_py!.b64" (
    call :elog " %RED%!FAIL.%LNG%!%RES%!extm7.%LNG%! %YEL%!detect_rpa_ext_py!.b64%RES%"
    goto rpa_cleanup
) else (
    if !debuglevel! GEQ 1 (
        call :elog .
        echo powershell.exe -NoLogo -NoProfile -NonInteractive -Command "& { [IO.File]::WriteAllBytes('!detect_rpa_ext_py!.tmp', [Convert]::FromBase64String([IO.File]::ReadAllText('!detect_rpa_ext_py!.b64')))}"
    )
    powershell.exe -NoLogo -NoProfile -NonInteractive -Command "& { [IO.File]::WriteAllBytes('!detect_rpa_ext_py!.tmp', [Convert]::FromBase64String([IO.File]::ReadAllText('!detect_rpa_ext_py!.b64')))}"
    del /f /q "!detect_rpa_ext_py!.b64" %DEBUGREDIR%
)
if not exist "!detect_rpa_ext_py!.tmp" (
    call :elog " %RED%!FAIL.%LNG%!%RES%!extm7.%LNG%! %YEL%!detect_rpa_ext_py!.tmp%RES%"
    goto rpa_cleanup
) else (
    move /y "!detect_rpa_ext_py!.tmp" "!detect_rpa_ext_py!" %DEBUGREDIR%
)

:: Run the script and capture the output
"%PYTHONHOME%python.exe" %PYNOASSERT% "%detect_rpa_ext_py%" "%WORKDIR%" > "%TEMP%\extlist.tmp"
set /p EXTLINE=<"%TEMP%\extlist.tmp"
del /f /q "%TEMP%\extlist.tmp" %DEBUGREDIR%
del /f /q "%detect_rpa_ext_py%" %DEBUGREDIR%

:: Clean the line to remove snags, dot and hooks.
if defined EXTLINE (
    set EXTLINE=!EXTLINE:[=!
    set EXTLINE=!EXTLINE:]=!
    set EXTLINE=!EXTLINE:'=!
    set EXTLINE=!EXTLINE:,= !
    set EXTLINE=!EXTLINE:.=!
    echo "!EXTLINE!" | findstr /i "rpa" >nul
    if !errorlevel! GEQ 1 (
        set "rpaExt=!EXTLINE! rpa"
    ) else (
        set "rpaExt=!EXTLINE!"
    )
) else (
    set "rpaExt=rpa"
)

call :elog .
echo !extm8.%LNG%! >> "%UNRENLOG%"
<nul set /p="!extm8.%LNG%!"

cd /d "%WORKDIR%\game"
: Search first with known extensions
set "file_found="
for %%e in (!rpaExt!) do (
    for /R . %%f in (*.%%e) do (
        if exist "%%f" (
            set "file_found=1"
            set "rpaExt=%%e"
            if /I not "!rpaExt!" == "rpa" (
                call :elog " %GRE%!PASS.%LNG%! %RES%!extm10.%LNG%! %YEL%!rpaExt!%RES%" REM RPA extension renamed to:
            ) else (
                call :elog " %GRE%!PASS.%LNG%! %RES%!extm25.%LNG%! %YEL%!rpaExt!%RES%" REM Extension found:
            )
        )
        goto :found_ext
    )
)

:: If no RPA found
if not defined file_found (
    call :elog "%YEL% !extm11.%LNG%!%RES%"
    call :elog .
    goto rpa_cleanup
)
call :elog .

:found_ext
call :elog .
set "extans="
<nul set /p "extans=!extm1.%LNG%!"
choice /C OSJДYN /N /D N /T 5
if errorlevel 6 (
    set "extans=n"
) else if errorlevel 5 (
    set "extans=y"
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
	call :elog "    + %YEL%!extm2.%LNG%!%RES%" REM RPA archives will be moved to %WORKDIR%\rpa.
) else (
	set "delrpa=y"
	call :elog "    + %YEL%!extm3.%LNG%!%RES%" REM RPA archives will be deleted after extraction.
)

:: Ask if we want to extract all RPA or select
call :elog .
set "extans="
<nul set /p "extans=!extm4.%LNG%!"
choice /C ATДS /N /D A /T 5
if errorlevel 4 (
    set "extans=s"
) else if errorlevel 3 (
    set "extans=a"
) else if errorlevel 2 (
    set "extans=a"
) else if errorlevel 1 (
    set "extans=a"
)
set "extans=%extans: =%"
if /i "%extans%" == "s" (
    set "extract_all_rpa=n"
    call :elog "    %YEL%+ !extm5.%LNG%!%RES%"
) else (
    set "extract_all_rpa=y"
    call :elog "    %YEL%+ !extm6.%LNG%!%RES%"
)
call :elog .

call :elog .
echo !extm9.%LNG%! >> "%UNRENLOG%" REM Creating rpatool...
<nul set /p="!extm9.%LNG%!"

cd /d "%WORKDIR%"
set "rpatool=%WORKDIR%\rpatool.py"
set "altrpatool=%WORKDIR%\altrpatool.py"
del /f /q "%rpatool%.b64" %DEBUGREDIR%
del /f /q "%rpatool%.tmp" %DEBUGREDIR%
del /f /q "%rpatool%" %DEBUGREDIR%
del /f /q "%altrpatool%.b64" %DEBUGREDIR%
del /f /q "%altrpatool%.tmp" %DEBUGREDIR%
del /f /q "%altrpatool%" %DEBUGREDIR%

:: Write Python scripts from our base64 strings
:: detect_archive.py
set "detect_archive_py=%TEMP%\detect_archive.py"
>"%detect_archive_py%.b64" (
    echo IyEvdXNyL2Jpbi9lbnYgcHl0aG9uDQppbXBvcnQgc3lzDQoNCmRlZiBkZXRlY3RfYXJjaGl2ZV90eXBlKHBhdGgpOg0KICAgIHRyeToNCiAgICAgICAgd2l0aCBvcGVuKHBhdGgsICJyYiIpIGFzIGY6DQogICAgICAgICAgICBoZWFkZXIgPSBmLnJlYWQoOCkNCiAgICAgICAgICAgICMgU3RhbmRhcmQgUlBBIGFyY2hpdmVzIHN0YXJ0IHdpdGggIlJQQS0zLjAiIG9yICJSUEEtMi4wIg0KICAgICAgICAgICAgaWYgaGVhZGVyLnN0YXJ0c3dpdGgoYiJSUEEtIik6DQogICAgICAgICAgICAgICAgcmV0dXJuIDAgICMgc3RhbmRhcmQNCiAgICAgICAgICAgIGVsc2U6DQogICAgICAgICAgICAgICAgcmV0dXJuIDEgICMgbW9kaWZpZWQgLyB1bmtub3duDQogICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOg0KICAgICAgICAjIFB5dGhvbiAyIGRvZXNuJ3Qgc3VwcG9ydCBmLXN0cmluZ3MsIHNvIHdlIHVzZSBmb3JtYXQoKQ0KICAgICAgICBzeXMuc3RkZXJyLndyaXRlKCJFcnJvcjoge31cbiIuZm9ybWF0KGUpKQ0KICAgICAgICByZXR1cm4gMSAgIyBieSBkZWZhdWx0LCB3ZSBjb25zaWRlciBtb2RpZmllZA0KDQppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOg0KICAgIGlmIGxlbihzeXMuYXJndikgPCAyOg0KICAgICAgICBwcmludCgiVXNhZ2U6IGRldGVjdF9hcmNoaXZlLnB5IDxhcmNoaXZlX2ZpbGU+IikNCiAgICAgICAgc3lzLmV4aXQoMSkNCg0KICAgIGFyY2hpdmVfZmlsZSA9IHN5cy5hcmd2WzFdDQogICAgcmVzdWx0ID0gZGV0ZWN0X2FyY2hpdmVfdHlwZShhcmNoaXZlX2ZpbGUpDQogICAgc3lzLmV4aXQocmVzdWx0KQ0K
)
if not exist "!detect_archive_py!.b64" (
    call :elog " %RED%!FAIL.%LNG%!%RES%!extm7.%LNG%! %YEL%!detect_archive_py!.b64%RES%"
    goto rpa_cleanup
) else (
    echo powershell.exe -NoLogo -NoProfile -NonInteractive -Command "& { [IO.File]::WriteAllBytes('!detect_archive_py!.tmp', [Convert]::FromBase64String([IO.File]::ReadAllText('!detect_archive_py!.b64')))}" >> "%UNRENLOG%"
    powershell.exe -NoLogo -NoProfile -NonInteractive -Command "& { [IO.File]::WriteAllBytes('!detect_archive_py!.tmp', [Convert]::FromBase64String([IO.File]::ReadAllText('!detect_archive_py!.b64')))}"
    del /f /q "!detect_archive_py!.b64" %DEBUGREDIR%
)
if not exist "!detect_archive_py!.tmp" (
    call :elog " %RED%!FAIL.%LNG%!%RES%!extm7.%LNG%! %YEL%!detect_archive_py!.tmp%RES%"
    goto rpa_cleanup
) else (
    move /y "!detect_archive_py!.tmp" "!detect_archive_py!" %DEBUGREDIR%
)

:: rpatool by Shizmob 9a58396 2019-02-22T17:31:07.000Z
::  https://github.com/Shizmob/rpatool
::  Version 0.8 wo pickle5 for Ren'Py <= 7
if "!RPATOOL-NEW!" == "n" (
    >"!rpatool!.b64" (
        echo IyEvdXNyL2Jpbi9lbnYgcHl0aG9uDQoNCmZyb20gX19mdXR1cmVfXyBpbXBvcnQgcHJpbnRfZnVuY3Rpb24NCg0KaW1wb3J0IHN5cw0KaW1wb3J0IG9zDQppbXBvcnQgY29kZWNzDQppbXBvcnQgcGlja2xlDQppbXBvcnQgZXJybm8NCmltcG9ydCByYW5kb20NCg0KaWYgc3lzLnZlcnNpb25faW5mb1swXSA+PSAzOg0KICAgIGRlZiBfdW5pY29kZSh0ZXh0KToNCiAgICAgICAgcmV0dXJuIHRleHQNCg0KICAgIGRlZiBfcHJpbnRhYmxlKHRleHQpOg0KICAgICAgICByZXR1cm4gdGV4dA0KDQogICAgZGVmIF91bm1hbmdsZShkYXRhKToNCiAgICAgICAgcmV0dXJuIGRhdGEuZW5jb2RlKCdsYXRpbjEnKQ0KDQogICAgZGVmIF91bnBpY2tsZShkYXRhKToNCiAgICAgICAgIyBTcGVjaWZ5IGxhdGluMSBlbmNvZGluZyB0byBwcmV2ZW50IHJhdyBieXRlIHZhbHVlcyBmcm9tIGNhdXNpbmcgYW4gQVNDSUkgZGVjb2RlIGVycm9yLg0KICAgICAgICByZXR1cm4gcGlja2xlLmxvYWRzKGRhdGEsIGVuY29kaW5nPSdsYXRpbjEnKQ0KZWxpZiBzeXMudmVyc2lvbl9pbmZvWzBdID09IDI6DQogICAgZGVmIF91bmljb2RlKHRleHQpOg0KICAgICAgICBpZiBpc2luc3RhbmNlKHRleHQsIHVuaWNvZGUpOg0KICAgICAgICAgICAgcmV0dXJuIHRleHQNCiAgICAgICAgcmV0dXJuIHRleHQuZGVjb2RlKCd1dGYtOCcpDQoNCiAgICBkZWYgX3ByaW50YWJsZSh0ZXh0KToNCiAgICAgICAgcmV0dXJuIHRleHQuZW5jb2RlKCd1dGYtOCcpDQoNCiAgICBkZWYgX3VubWFuZ2xlKGRhdGEpOg0KICAgICAgICByZXR1cm4gZGF0YQ0KDQogICAgZGVmIF91bnBpY2tsZShkYXRhKToNCiAgICAgICAgcmV0dXJuIHBpY2tsZS5sb2FkcyhkYXRhKQ0KDQpjbGFzcyBSZW5QeUFyY2hpdmU6DQogICAgZmlsZSA9IE5vbmUNCiAgICBoYW5kbGUgPSBOb25lDQoNCiAgICBmaWxlcyA9IHt9DQogICAgaW5kZXhlcyA9IHt9DQoNCiAgICB2ZXJzaW9uID0gTm9uZQ0KICAgIHBhZGxlbmd0aCA9IDANCiAgICBrZXkgPSBOb25lDQogICAgdmVyYm9zZSA9IEZhbHNlDQoNCiAgICBSUEEyX01BR0lDID0gJ1JQQS0yLjAgJw0KICAgIFJQQTNfTUFHSUMgPSAnUlBBLTMuMCAnDQogICAgUlBBM18yX01BR0lDID0gJ1JQQS0zLjIgJw0KDQogICAgIyBGb3IgYmFja3dhcmQgY29tcGF0aWJpbGl0eSwgb3RoZXJ3aXNlIFB5dGhvbjMtcGFja2VkIGFyY2hpdmVzIHdvbid0IGJlIHJlYWQgYnkgUHl0aG9uMg0KICAgIFBJQ0tMRV9QUk9UT0NPTCA9IDINCg0KICAgIGRlZiBfX2luaXRfXyhzZWxmLCBmaWxlID0gTm9uZSwgdmVyc2lvbiA9IDMsIHBhZGxlbmd0aCA9IDAsIGtleSA9IDB4REVBREJFRUYsIHZlcmJvc2UgPSBGYWxzZSk6DQogICAgICAgIHNlbGYucGFkbGVuZ3RoID0gcGFkbGVuZ3RoDQogICAgICAgIHNlbGYua2V5ID0ga2V5DQogICAgICAgIHNlbGYudmVyYm9zZSA9IHZlcmJvc2UNCg0KICAgICAgICBpZiBmaWxlIGlzIG5vdCBOb25lOg0KICAgICAgICAgICAgc2VsZi5sb2FkKGZpbGUpDQogICAgICAgIGVsc2U6DQogICAgICAgICAgICBzZWxmLnZlcnNpb24gPSB2ZXJzaW9uDQoNCiAgICBkZWYgX19kZWxfXyhzZWxmKToNCiAgICAgICAgaWYgc2VsZi5oYW5kbGUgaXMgbm90IE5vbmU6DQogICAgICAgICAgICBzZWxmLmhhbmRsZS5jbG9zZSgpDQoNCiAgICAjIERldGVybWluZSBhcmNoaXZlIHZlcnNpb24uDQogICAgZGVmIGdldF92ZXJzaW9uKHNlbGYpOg0KICAgICAgICBzZWxmLmhhbmRsZS5zZWVrKDApDQogICAgICAgIG1hZ2ljID0gc2VsZi5oYW5kbGUucmVhZGxpbmUoKS5kZWNvZGUoJ3V0Zi04JykNCg0KICAgICAgICBpZiBtYWdpYy5zdGFydHN3aXRoKHNlbGYuUlBBM18yX01BR0lDKToNCiAgICAgICAgICAgIHJldHVybiAzLjINCiAgICAgICAgZWxpZiBtYWdpYy5zdGFydHN3aXRoKHNlbGYuUlBBM19NQUdJQyk6DQogICAgICAgICAgICByZXR1cm4gMw0KICAgICAgICBlbGlmIG1hZ2ljLnN0YXJ0c3dpdGgoc2VsZi5SUEEyX01BR0lDKToNCiAgICAgICAgICAgIHJldHVybiAyDQogICAgICAgIGVsaWYgc2VsZi5maWxlLmVuZHN3aXRoKCcucnBpJyk6DQogICAgICAgICAgICByZXR1cm4gMQ0KDQogICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ3RoZSBnaXZlbiBmaWxlIGlzIG5vdCBhIHZhbGlkIFJlblwnUHkgYXJjaGl2ZSwgb3IgYW4gdW5zdXBwb3J0ZWQgdmVyc2lvbicpDQoNCiAgICAjIEV4dHJhY3QgZmlsZSBpbmRleGVzIGZyb20gb3BlbmVkIGFyY2hpdmUuDQogICAgZGVmIGV4dHJhY3RfaW5kZXhlcyhzZWxmKToNCiAgICAgICAgc2VsZi5oYW5kbGUuc2VlaygwKQ0KICAgICAgICBpbmRleGVzID0gTm9uZQ0KDQogICAgICAgIGlmIHNlbGYudmVyc2lvbiBpbiBbMiwgMywgMy4yXToNCiAgICAgICAgICAgICMgRmV0Y2ggbWV0YWRhdGEuDQogICAgICAgICAgICBtZXRhZGF0YSA9IHNlbGYuaGFuZGxlLnJlYWRsaW5lKCkNCiAgICAgICAgICAgIHZhbHMgPSBtZXRhZGF0YS5zcGxpdCgpDQogICAgICAgICAgICBvZmZzZXQgPSBpbnQodmFsc1sxXSwgMTYpDQogICAgICAgICAgICBpZiBzZWxmLnZlcnNpb24gPT0gMzoNCiAgICAgICAgICAgICAgICBzZWxmLmtleSA9IDANCiAgICAgICAgICAgICAgICBmb3Igc3Via2V5IGluIHZhbHNbMjpdOg0KICAgICAgICAgICAgICAgICAgICBzZWxmLmtleSBePSBpbnQoc3Via2V5LCAxNikNCiAgICAgICAgICAgIGVsaWYgc2VsZi52ZXJzaW9uID09IDMuMjoNCiAgICAgICAgICAgICAgICBzZWxmLmtleSA9IDANCiAgICAgICAgICAgICAgICBmb3Igc3Via2V5IGluIHZhbHNbMzpdOg0KICAgICAgICAgICAgICAgICAgICBzZWxmLmtleSBePSBpbnQoc3Via2V5LCAxNikNCg0KICAgICAgICAgICAgIyBMb2FkIGluIGluZGV4ZXMuDQogICAgICAgICAgICBzZWxmLmhhbmRsZS5zZWVrKG9mZnNldCkNCiAgICAgICAgICAgIGNvbnRlbnRzID0gY29kZWNzLmRlY29kZShzZWxmLmhhbmRsZS5yZWFkKCksICd6bGliJykNCiAgICAgICAgICAgIGluZGV4ZXMgPSBfdW5waWNrbGUoY29udGVudHMpDQoNCiAgICAgICAgICAgICMgRGVvYmZ1c2NhdGUgaW5kZXhlcy4NCiAgICAgICAgICAgIGlmIHNlbGYudmVyc2lvbiBpbiBbMywgMy4yXToNCiAgICAgICAgICAgICAgICBvYmZ1c2NhdGVkX2luZGV4ZXMgPSBpbmRleGVzDQogICAgICAgICAgICAgICAgaW5kZXhlcyA9IHt9DQogICAgICAgICAgICAgICAgZm9yIGkgaW4gb2JmdXNjYXRlZF9pbmRleGVzLmtleXMoKToNCiAgICAgICAgICAgICAgICAgICAgaWYgbGVuKG9iZnVzY2F0ZWRfaW5kZXhlc1tpXVswXSkgPT0gMjoNCiAgICAgICAgICAgICAgICAgICAgICAgIGluZGV4ZXNbaV0gPSBbIChvZmZzZXQgXiBzZWxmLmtleSwgbGVuZ3RoIF4gc2VsZi5rZXkpIGZvciBvZmZzZXQsIGxlbmd0aCBpbiBvYmZ1c2NhdGVkX2luZGV4ZXNbaV0gXQ0KICAgICAgICAgICAgICAgICAgICBlbHNlOg0KICAgICAgICAgICAgICAgICAgICAgICAgaW5kZXhlc1tpXSA9IFsgKG9mZnNldCBeIHNlbGYua2V5LCBsZW5ndGggXiBzZWxmLmtleSwgcHJlZml4KSBmb3Igb2Zmc2V0LCBsZW5ndGgsIHByZWZpeCBpbiBvYmZ1c2NhdGVkX2luZGV4ZXNbaV0gXQ0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgaW5kZXhlcyA9IHBpY2tsZS5sb2Fkcyhjb2RlY3MuZGVjb2RlKHNlbGYuaGFuZGxlLnJlYWQoKSwgJ3psaWInKSkNCg0KICAgICAgICByZXR1cm4gaW5kZXhlcw0KDQogICAgIyBHZW5lcmF0ZSBwc2V1ZG9yYW5kb20gcGFkZGluZyAoZm9yIHdoYXRldmVyIHJlYXNvbikuDQogICAgZGVmIGdlbmVyYXRlX3BhZGRpbmcoc2VsZik6DQogICAgICAgIGxlbmd0aCA9IHJhbmRvbS5yYW5kaW50KDEsIHNlbGYucGFkbGVuZ3RoKQ0KDQogICAgICAgIHBhZGRpbmcgPSAnJw0KICAgICAgICB3aGlsZSBsZW5ndGggPiAwOg0KICAgICAgICAgICAgcGFkZGluZyArPSBjaHIocmFuZG9tLnJhbmRpbnQoMSwgMjU1KSkNCiAgICAgICAgICAgIGxlbmd0aCAtPSAxDQoNCiAgICAgICAgcmV0dXJuIHBhZGRpbmcNCg0KICAgICMgQ29udmVydHMgYSBmaWxlbmFtZSB0byBhcmNoaXZlIGZvcm1hdC4NCiAgICBkZWYgY29udmVydF9maWxlbmFtZShzZWxmLCBmaWxlbmFtZSk6DQogICAgICAgIChkcml2ZSwgZmlsZW5hbWUpID0gb3MucGF0aC5zcGxpdGRyaXZlKG9zLnBhdGgubm9ybXBhdGgoZmlsZW5hbWUpLnJlcGxhY2Uob3Muc2VwLCAnLycpKQ0KICAgICAgICByZXR1cm4gZmlsZW5hbWUNCg0KICAgICMgRGVidWcgKHZlcmJvc2UpIG1lc3NhZ2VzLg0KICAgIGRlZiB2ZXJib3NlX3ByaW50KHNlbGYsIG1lc3NhZ2UpOg0KICAgICAgICBpZiBzZWxmLnZlcmJvc2U6DQogICAgICAgICAgICBwcmludChtZXNzYWdlKQ0KDQoNCiAgICAjIExpc3QgZmlsZXMgaW4gYXJjaGl2ZSBhbmQgY3VycmVudCBpbnRlcm5hbCBzdG9yYWdlLg0KICAgIGRlZiBsaXN0KHNlbGYpOg0KICAgICAgICByZXR1cm4gbGlzdChzZWxmLmluZGV4ZXMua2V5cygpKSArIGxpc3Qoc2VsZi5maWxlcy5rZXlzKCkpDQoNCiAgICAjIENoZWNrIGlmIGEgZmlsZSBleGlzdHMgaW4gdGhlIGFyY2hpdmUuDQogICAgZGVmIGhhc19maWxlKHNlbGYsIGZpbGVuYW1lKToNCiAgICAgICAgZmlsZW5hbWUgPSBfdW5pY29kZShmaWxlbmFtZSkNCiAgICAgICAgcmV0dXJuIGZpbGVuYW1lIGluIHNlbGYuaW5kZXhlcy5rZXlzKCkgb3IgZmlsZW5hbWUgaW4gc2VsZi5maWxlcy5rZXlzKCkNCg0KICAgICMgUmVhZCBmaWxlIGZyb20gYXJjaGl2ZSBvciBpbnRlcm5hbCBzdG9yYWdlLg0KICAgIGRlZiByZWFkKHNlbGYsIGZpbGVuYW1lKToNCiAgICAgICAgZmlsZW5hbWUgPSBzZWxmLmNvbnZlcnRfZmlsZW5hbWUoX3VuaWNvZGUoZmlsZW5hbWUpKQ0KDQogICAgICAgICMgQ2hlY2sgaWYgdGhlIGZpbGUgZXhpc3RzIGluIG91ciBpbmRleGVzLg0KICAgICAgICBpZiBmaWxlbmFtZSBub3QgaW4gc2VsZi5maWxlcyBhbmQgZmlsZW5hbWUgbm90IGluIHNlbGYuaW5kZXhlczoNCiAgICAgICAgICAgIHJhaXNlIElPRXJyb3IoZXJybm8uRU5PRU5ULCAndGhlIHJlcXVlc3RlZCBmaWxlIHswfSBkb2VzIG5vdCBleGlzdCBpbiB0aGUgZ2l2ZW4gUmVuXCdQeSBhcmNoaXZlJy5mb3JtYXQoDQogICAgICAgICAgICAgICAgX3ByaW50YWJsZShmaWxlbmFtZSkpKQ0KDQogICAgICAgICMgSWYgaXQncyBpbiBvdXIgb3BlbmVkIGFyY2hpdmUgaW5kZXgsIGFuZCBvdXIgYXJjaGl2ZSBoYW5kbGUgaXNuJ3QgdmFsaWQsIHNvbWV0aGluZyBpcyBvYnZpb3VzbHkgd3JvbmcuDQogICAgICAgIGlmIGZpbGVuYW1lIG5vdCBpbiBzZWxmLmZpbGVzIGFuZCBmaWxlbmFtZSBpbiBzZWxmLmluZGV4ZXMgYW5kIHNlbGYuaGFuZGxlIGlzIE5vbmU6DQogICAgICAgICAgICByYWlzZSBJT0Vycm9yKGVycm5vLkVOT0VOVCwgJ3RoZSByZXF1ZXN0ZWQgZmlsZSB7MH0gZG9lcyBub3QgZXhpc3QgaW4gdGhlIGdpdmVuIFJlblwnUHkgYXJjaGl2ZScuZm9ybWF0KA0KICAgICAgICAgICAgICAgIF9wcmludGFibGUoZmlsZW5hbWUpKSkNCg0KICAgICAgICAjIENoZWNrIG91ciBzaW1wbGlmaWVkIGludGVybmFsIGluZGV4ZXMgZmlyc3QsIGluIGNhc2Ugc29tZW9uZSB3YW50cyB0byByZWFkIGEgZmlsZSB0aGV5IGFkZGVkIGJlZm9yZSB3aXRob3V0IHNhdmluZywgZm9yIHNvbWUgdW5ob2x5IHJlYXNvbi4NCiAgICAgICAgaWYgZmlsZW5hbWUgaW4gc2VsZi5maWxlczoNCiAgICAgICAgICAgIHNlbGYudmVyYm9zZV9wcmludCgnUmVhZGluZyBmaWxlIHswfSBmcm9tIGludGVybmFsIHN0b3JhZ2UuLi4nLmZvcm1hdChfcHJpbnRhYmxlKGZpbGVuYW1lKSkpDQogICAgICAgICAgICByZXR1cm4gc2VsZi5maWxlc1tmaWxlbmFtZV0NCiAgICAgICAgIyBXZSBuZWVkIHRvIHJlYWQgdGhlIGZpbGUgZnJvbSBvdXIgb3BlbiBhcmNoaXZlLg0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgIyBSZWFkIG9mZnNldCBhbmQgbGVuZ3RoLCBzZWVrIHRvIHRoZSBvZmZzZXQgYW5kIHJlYWQgdGhlIGZpbGUgY29udGVudHMuDQogICAgICAgICAgICBpZiBsZW4oc2VsZi5pbmRleGVzW2ZpbGVuYW1lXVswXSkgPT0gMzoNCiAgICAgICAgICAgICAgICAob2Zmc2V0LCBsZW5ndGgsIHByZWZpeCkgPSBzZWxmLmluZGV4ZXNbZmlsZW5hbWVdWzBdDQogICAgICAgICAgICBlbHNlOg0KICAgICAgICAgICAgICAgIChvZmZ
        echo zZXQsIGxlbmd0aCkgPSBzZWxmLmluZGV4ZXNbZmlsZW5hbWVdWzBdDQogICAgICAgICAgICAgICAgcHJlZml4ID0gJycNCg0KICAgICAgICAgICAgc2VsZi52ZXJib3NlX3ByaW50KCdSZWFkaW5nIGZpbGUgezB9IGZyb20gZGF0YSBmaWxlIHsxfS4uLiAob2Zmc2V0ID0gezJ9LCBsZW5ndGggPSB7M30gYnl0ZXMpJy5mb3JtYXQoDQogICAgICAgICAgICAgICAgX3ByaW50YWJsZShmaWxlbmFtZSksIHNlbGYuZmlsZSwgb2Zmc2V0LCBsZW5ndGgpKQ0KICAgICAgICAgICAgc2VsZi5oYW5kbGUuc2VlayhvZmZzZXQpDQogICAgICAgICAgICByZXR1cm4gX3VubWFuZ2xlKHByZWZpeCkgKyBzZWxmLmhhbmRsZS5yZWFkKGxlbmd0aCAtIGxlbihwcmVmaXgpKQ0KDQogICAgIyBNb2RpZnkgYSBmaWxlIGluIGFyY2hpdmUgb3IgaW50ZXJuYWwgc3RvcmFnZS4NCiAgICBkZWYgY2hhbmdlKHNlbGYsIGZpbGVuYW1lLCBjb250ZW50cyk6DQogICAgICAgIGZpbGVuYW1lID0gX3VuaWNvZGUoZmlsZW5hbWUpDQoNCiAgICAgICAgIyBPdXIgJ2NoYW5nZScgaXMgYmFzaWNhbGx5IHJlbW92aW5nIHRoZSBmaWxlIGZyb20gb3VyIGluZGV4ZXMgZmlyc3QsIGFuZCB0aGVuIHJlLWFkZGluZyBpdC4NCiAgICAgICAgc2VsZi5yZW1vdmUoZmlsZW5hbWUpDQogICAgICAgIHNlbGYuYWRkKGZpbGVuYW1lLCBjb250ZW50cykNCg0KICAgICMgQWRkIGEgZmlsZSB0byB0aGUgaW50ZXJuYWwgc3RvcmFnZS4NCiAgICBkZWYgYWRkKHNlbGYsIGZpbGVuYW1lLCBjb250ZW50cyk6DQogICAgICAgIGZpbGVuYW1lID0gc2VsZi5jb252ZXJ0X2ZpbGVuYW1lKF91bmljb2RlKGZpbGVuYW1lKSkNCiAgICAgICAgaWYgZmlsZW5hbWUgaW4gc2VsZi5maWxlcyBvciBmaWxlbmFtZSBpbiBzZWxmLmluZGV4ZXM6DQogICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCdmaWxlIHswfSBhbHJlYWR5IGV4aXN0cyBpbiBhcmNoaXZlJy5mb3JtYXQoX3ByaW50YWJsZShmaWxlbmFtZSkpKQ0KDQogICAgICAgIHNlbGYudmVyYm9zZV9wcmludCgnQWRkaW5nIGZpbGUgezB9IHRvIGFyY2hpdmUuLi4gKGxlbmd0aCA9IHsxfSBieXRlcyknLmZvcm1hdCgNCiAgICAgICAgICAgIF9wcmludGFibGUoZmlsZW5hbWUpLCBsZW4oY29udGVudHMpKSkNCiAgICAgICAgc2VsZi5maWxlc1tmaWxlbmFtZV0gPSBjb250ZW50cw0KDQogICAgIyBSZW1vdmUgYSBmaWxlIGZyb20gYXJjaGl2ZSBvciBpbnRlcm5hbCBzdG9yYWdlLg0KICAgIGRlZiByZW1vdmUoc2VsZiwgZmlsZW5hbWUpOg0KICAgICAgICBmaWxlbmFtZSA9IF91bmljb2RlKGZpbGVuYW1lKQ0KICAgICAgICBpZiBmaWxlbmFtZSBpbiBzZWxmLmZpbGVzOg0KICAgICAgICAgICAgc2VsZi52ZXJib3NlX3ByaW50KCdSZW1vdmluZyBmaWxlIHswfSBmcm9tIGludGVybmFsIHN0b3JhZ2UuLi4nLmZvcm1hdChfcHJpbnRhYmxlKGZpbGVuYW1lKSkpDQogICAgICAgICAgICBkZWwgc2VsZi5maWxlc1tmaWxlbmFtZV0NCiAgICAgICAgZWxpZiBmaWxlbmFtZSBpbiBzZWxmLmluZGV4ZXM6DQogICAgICAgICAgICBzZWxmLnZlcmJvc2VfcHJpbnQoJ1JlbW92aW5nIGZpbGUgezB9IGZyb20gYXJjaGl2ZSBpbmRleGVzLi4uJy5mb3JtYXQoX3ByaW50YWJsZShmaWxlbmFtZSkpKQ0KICAgICAgICAgICAgZGVsIHNlbGYuaW5kZXhlc1tmaWxlbmFtZV0NCiAgICAgICAgZWxzZToNCiAgICAgICAgICAgIHJhaXNlIElPRXJyb3IoZXJybm8uRU5PRU5ULCAndGhlIHJlcXVlc3RlZCBmaWxlIHswfSBkb2VzIG5vdCBleGlzdCBpbiB0aGlzIGFyY2hpdmUnLmZvcm1hdChfcHJpbnRhYmxlKGZpbGVuYW1lKSkpDQoNCiAgICAjIExvYWQgYXJjaGl2ZS4NCiAgICBkZWYgbG9hZChzZWxmLCBmaWxlbmFtZSk6DQogICAgICAgIGZpbGVuYW1lID0gX3VuaWNvZGUoZmlsZW5hbWUpDQoNCiAgICAgICAgaWYgc2VsZi5oYW5kbGUgaXMgbm90IE5vbmU6DQogICAgICAgICAgICBzZWxmLmhhbmRsZS5jbG9zZSgpDQogICAgICAgIHNlbGYuZmlsZSA9IGZpbGVuYW1lDQogICAgICAgIHNlbGYuZmlsZXMgPSB7fQ0KICAgICAgICBzZWxmLmhhbmRsZSA9IG9wZW4oc2VsZi5maWxlLCAncmInKQ0KICAgICAgICBzZWxmLnZlcnNpb24gPSBzZWxmLmdldF92ZXJzaW9uKCkNCiAgICAgICAgc2VsZi5pbmRleGVzID0gc2VsZi5leHRyYWN0X2luZGV4ZXMoKQ0KDQogICAgIyBTYXZlIGN1cnJlbnQgc3RhdGUgaW50byBhIG5ldyBmaWxlLCBtZXJnaW5nIGFyY2hpdmUgYW5kIGludGVybmFsIHN0b3JhZ2UsIHJlYnVpbGRpbmcgaW5kZXhlcywgYW5kIG9wdGlvbmFsbHkgc2F2aW5nIGluIGFub3RoZXIgZm9ybWF0IHZlcnNpb24uDQogICAgZGVmIHNhdmUoc2VsZiwgZmlsZW5hbWUgPSBOb25lKToNCiAgICAgICAgZmlsZW5hbWUgPSBfdW5pY29kZShmaWxlbmFtZSkNCg0KICAgICAgICBpZiBmaWxlbmFtZSBpcyBOb25lOg0KICAgICAgICAgICAgZmlsZW5hbWUgPSBzZWxmLmZpbGUNCiAgICAgICAgaWYgZmlsZW5hbWUgaXMgTm9uZToNCiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ25vIHRhcmdldCBmaWxlIGZvdW5kIGZvciBzYXZpbmcgYXJjaGl2ZScpDQogICAgICAgIGlmIHNlbGYudmVyc2lvbiAhPSAyIGFuZCBzZWxmLnZlcnNpb24gIT0gMzoNCiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ3NhdmluZyBpcyBvbmx5IHN1cHBvcnRlZCBmb3IgdmVyc2lvbiAyIGFuZCAzIGFyY2hpdmVzJykNCg0KICAgICAgICBzZWxmLnZlcmJvc2VfcHJpbnQoJ1JlYnVpbGRpbmcgYXJjaGl2ZSBpbmRleC4uLicpDQogICAgICAgICMgRmlsbCBvdXIgb3duIGZpbGVzIHN0cnVjdHVyZSB3aXRoIHRoZSBmaWxlcyBhZGRlZCBvciBjaGFuZ2VkIGluIHRoaXMgc2Vzc2lvbi4NCiAgICAgICAgZmlsZXMgPSBzZWxmLmZpbGVzDQogICAgICAgICMgRmlyc3QsIHJlYWQgZmlsZXMgZnJvbSB0aGUgY3VycmVudCBhcmNoaXZlIGludG8gb3VyIGZpbGVzIHN0cnVjdHVyZS4NCiAgICAgICAgZm9yIGZpbGUgaW4gbGlzdChzZWxmLmluZGV4ZXMua2V5cygpKToNCiAgICAgICAgICAgIGNvbnRlbnQgPSBzZWxmLnJlYWQoZmlsZSkNCiAgICAgICAgICAgICMgUmVtb3ZlIGZyb20gaW5kZXhlcyBhcnJheSBvbmNlIHJlYWQsIGFkZCB0byBvdXIgb3duIGFycmF5Lg0KICAgICAgICAgICAgZGVsIHNlbGYuaW5kZXhlc1tmaWxlXQ0KICAgICAgICAgICAgZmlsZXNbZmlsZV0gPSBjb250ZW50DQoNCiAgICAgICAgIyBQcmVkaWN0IGhlYWRlciBsZW5ndGgsIHdlJ2xsIHdyaXRlIHRoYXQgb25lIGxhc3QuDQogICAgICAgIG9mZnNldCA9IDANCiAgICAgICAgaWYgc2VsZi52ZXJzaW9uID09IDM6DQogICAgICAgICAgICBvZmZzZXQgPSAzNA0KICAgICAgICBlbGlmIHNlbGYudmVyc2lvbiA9PSAyOg0KICAgICAgICAgICAgb2Zmc2V0ID0gMjUNCiAgICAgICAgYXJjaGl2ZSA9IG9wZW4oZmlsZW5hbWUsICd3YicpDQogICAgICAgIGFyY2hpdmUuc2VlayhvZmZzZXQpDQoNCiAgICAgICAgIyBCdWlsZCBvdXIgb3duIGluZGV4ZXMgd2hpbGUgd3JpdGluZyBmaWxlcyB0byB0aGUgYXJjaGl2ZS4NCiAgICAgICAgaW5kZXhlcyA9IHt9DQogICAgICAgIHNlbGYudmVyYm9zZV9wcmludCgnV3JpdGluZyBmaWxlcyB0byBhcmNoaXZlIGZpbGUuLi4nKQ0KICAgICAgICBmb3IgZmlsZSwgY29udGVudCBpbiBmaWxlcy5pdGVtcygpOg0KICAgICAgICAgICAgIyBHZW5lcmF0ZSByYW5kb20gcGFkZGluZywgZm9yIHdoYXRldmVyIHJlYXNvbi4NCiAgICAgICAgICAgIGlmIHNlbGYucGFkbGVuZ3RoID4gMDoNCiAgICAgICAgICAgICAgICBwYWRkaW5nID0gc2VsZi5nZW5lcmF0ZV9wYWRkaW5nKCkNCiAgICAgICAgICAgICAgICBhcmNoaXZlLndyaXRlKHBhZGRpbmcpDQogICAgICAgICAgICAgICAgb2Zmc2V0ICs9IGxlbihwYWRkaW5nKQ0KDQogICAgICAgICAgICBhcmNoaXZlLndyaXRlKGNvbnRlbnQpDQogICAgICAgICAgICAjIFVwZGF0ZSBpbmRleC4NCiAgICAgICAgICAgIGlmIHNlbGYudmVyc2lvbiA9PSAzOg0KICAgICAgICAgICAgICAgIGluZGV4ZXNbZmlsZV0gPSBbIChvZmZzZXQgXiBzZWxmLmtleSwgbGVuKGNvbnRlbnQpIF4gc2VsZi5rZXkpIF0NCiAgICAgICAgICAgIGVsaWYgc2VsZi52ZXJzaW9uID09IDI6DQogICAgICAgICAgICAgICAgaW5kZXhlc1tmaWxlXSA9IFsgKG9mZnNldCwgbGVuKGNvbnRlbnQpKSBdDQogICAgICAgICAgICBvZmZzZXQgKz0gbGVuKGNvbnRlbnQpDQoNCiAgICAgICAgIyBXcml0ZSB0aGUgaW5kZXhlcy4NCiAgICAgICAgc2VsZi52ZXJib3NlX3ByaW50KCdXcml0aW5nIGFyY2hpdmUgaW5kZXggdG8gYXJjaGl2ZSBmaWxlLi4uJykNCiAgICAgICAgYXJjaGl2ZS53cml0ZShjb2RlY3MuZW5jb2RlKHBpY2tsZS5kdW1wcyhpbmRleGVzLCBzZWxmLlBJQ0tMRV9QUk9UT0NPTCksICd6bGliJykpDQogICAgICAgICMgTm93IHdyaXRlIHRoZSBoZWFkZXIuDQogICAgICAgIHNlbGYudmVyYm9zZV9wcmludCgnV3JpdGluZyBoZWFkZXIgdG8gYXJjaGl2ZSBmaWxlLi4uICh2ZXJzaW9uID0gUlBBdnswfSknLmZvcm1hdChzZWxmLnZlcnNpb24pKQ0KICAgICAgICBhcmNoaXZlLnNlZWsoMCkNCiAgICAgICAgaWYgc2VsZi52ZXJzaW9uID09IDM6DQogICAgICAgICAgICBhcmNoaXZlLndyaXRlKGNvZGVjcy5lbmNvZGUoJ3t9ezowMTZ4fSB7OjA4eH1cbicuZm9ybWF0KHNlbGYuUlBBM19NQUdJQywgb2Zmc2V0LCBzZWxmLmtleSkpKQ0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgYXJjaGl2ZS53cml0ZShjb2RlY3MuZW5jb2RlKCd7fXs6MDE2eH1cbicuZm9ybWF0KHNlbGYuUlBBMl9NQUdJQywgb2Zmc2V0KSkpDQogICAgICAgICMgV2UncmUgZG9uZSwgY2xvc2UgaXQuDQogICAgICAgIGFyY2hpdmUuY2xvc2UoKQ0KDQogICAgICAgICMgUmVsb2FkIHRoZSBmaWxlIGluIG91ciBpbm5lciBkYXRhYmFzZS4NCiAgICAgICAgc2VsZi5sb2FkKGZpbGVuYW1lKQ0KDQppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOg0KICAgIGltcG9ydCBhcmdwYXJzZQ0KDQogICAgcGFyc2VyID0gYXJncGFyc2UuQXJndW1lbnRQYXJzZXIoDQogICAgICAgIGRlc2NyaXB0aW9uPSdBIHRvb2wgZm9yIHdvcmtpbmcgd2l0aCBSZW5cJ1B5IGFyY2hpdmUgZmlsZXMuJywNCiAgICAgICAgZXBpbG9nPSdUaGUgRklMRSBhcmd1bWVudCBjYW4gb3B0aW9uYWxseSBiZSBpbiBBUkNISVZFPVJFQUwgZm9ybWF0LCBtYXBwaW5nIGEgZmlsZSBpbiB0aGUgYXJjaGl2ZSBmaWxlIHN5c3RlbSB0byBhIGZpbGUgb24geW91ciByZWFsIGZpbGUgc3lzdGVtLiBBbiBleGFtcGxlIG9mIHRoaXM6IHJwYXRvb2wgLXggdGVzdC5ycGEgc2NyaXB0LnJweWM9L2hvbWUvZm9vL3Rlc3QucnB5YycsDQogICAgICAgIGFkZF9oZWxwPUZhbHNlKQ0KDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnYXJjaGl2ZScsIG1ldGF2YXI9J0FSQ0hJVkUnLCBoZWxwPSdUaGUgUmVuXCdweSBhcmNoaXZlIGZpbGUgdG8gb3BlcmF0ZSBvbi4nKQ0KICAgIHBhcnNlci5hZGRfYXJndW1lbnQoJ2ZpbGVzJywgbWV0YXZhcj0nRklMRScsIG5hcmdzPScqJywgYWN0aW9uPSdhcHBlbmQnLCBoZWxwPSdaZXJvIG9yIG1vcmUgZmlsZXMgdG8gb3BlcmF0ZSBvbi4nKQ0KDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLWwnLCAnLS1saXN0JywgYWN0aW9uPSdzdG9yZV90cnVlJywgaGVscD0nTGlzdCBmaWxlcyBpbiBhcmNoaXZlIEFSQ0hJVkUuJykNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCcteCcsICctLWV4dHJhY3QnLCBhY3Rpb249J3N0b3JlX3RydWUnLCBoZWxwPSdFeHRyYWN0IEZJTEVzIGZyb20gQVJDSElWRS4nKQ0KICAgIHBhcnNlci5hZGRfYXJndW1lbnQoJy1jJywgJy0tY3JlYXRlJywgYWN0aW9uPSdzdG9yZV90cnVlJywgaGVscD0nQ3JlYXRpdmUgQVJDSElWRSBmcm9tIEZJTEVzLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLWQnLCAnLS1kZWxldGUnLCBhY3Rpb249J3N0b3JlX3RydWUnLCBoZWxwPSdEZWxldGUgRklMRXMgZnJvbSBBUkNISVZFLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLWEnLCAnLS1hcHBlbmQnLCBhY3Rpb249J3N0b3JlX3RydWUnLCBoZWxwPSdBcHBlbmQgRklMRXMgdG8gQVJDSElWRS4nKQ0KDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLTInLCAnLS10d28nLCBhY3Rpb249J3N0b3
        echo JlX3RydWUnLCBoZWxwPSdVc2UgdGhlIFJQQXYyIGZvcm1hdCBmb3IgY3JlYXRpbmcvYXBwZW5kaW5nIHRvIGFyY2hpdmVzLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLTMnLCAnLS10aHJlZScsIGFjdGlvbj0nc3RvcmVfdHJ1ZScsIGhlbHA9J1VzZSB0aGUgUlBBdjMgZm9ybWF0IGZvciBjcmVhdGluZy9hcHBlbmRpbmcgdG8gYXJjaGl2ZXMgKGRlZmF1bHQpLicpDQoNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctaycsICctLWtleScsIG1ldGF2YXI9J0tFWScsIGhlbHA9J1RoZSBvYmZ1c2NhdGlvbiBrZXkgdXNlZCBmb3IgY3JlYXRpbmcgUlBBdjMgYXJjaGl2ZXMsIGluIGhleGFkZWNpbWFsIChkZWZhdWx0OiAweERFQURCRUVGKS4nKQ0KICAgIHBhcnNlci5hZGRfYXJndW1lbnQoJy1wJywgJy0tcGFkZGluZycsIG1ldGF2YXI9J0NPVU5UJywgaGVscD0nVGhlIG1heGltdW0gbnVtYmVyIG9mIGJ5dGVzIG9mIHBhZGRpbmcgdG8gYWRkIGJldHdlZW4gZmlsZXMgKGRlZmF1bHQ6IDApLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLW8nLCAnLS1vdXRmaWxlJywgaGVscD0nQW4gYWx0ZXJuYXRpdmUgb3V0cHV0IGFyY2hpdmUgZmlsZSB3aGVuIGFwcGVuZGluZyB0byBvciBkZWxldGluZyBmcm9tIGFyY2hpdmVzLCBvciBvdXRwdXQgZGlyZWN0b3J5IHdoZW4gZXh0cmFjdGluZy4nKQ0KDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLWgnLCAnLS1oZWxwJywgYWN0aW9uPSdoZWxwJywgaGVscD0nUHJpbnQgdGhpcyBoZWxwIGFuZCBleGl0LicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLXYnLCAnLS12ZXJib3NlJywgYWN0aW9uPSdzdG9yZV90cnVlJywgaGVscD0nQmUgYSBiaXQgbW9yZSB2ZXJib3NlIHdoaWxlIHBlcmZvcm1pbmcgb3BlcmF0aW9ucy4nKQ0KICAgIHBhcnNlci5hZGRfYXJndW1lbnQoJy1WJywgJy0tdmVyc2lvbicsIGFjdGlvbj0ndmVyc2lvbicsIHZlcnNpb249J3JwYXRvb2wgdjAuOCcsIGhlbHA9J1Nob3cgdmVyc2lvbiBpbmZvcm1hdGlvbi4nKQ0KICAgIGFyZ3VtZW50cyA9IHBhcnNlci5wYXJzZV9hcmdzKCkNCg0KICAgICMgRGV0ZXJtaW5lIFJQQSB2ZXJzaW9uLg0KICAgIGlmIGFyZ3VtZW50cy50d286DQogICAgICAgIHZlcnNpb24gPSAyDQogICAgZWxzZToNCiAgICAgICAgdmVyc2lvbiA9IDMNCg0KICAgICMgRGV0ZXJtaW5lIFJQQXYzIGtleS4NCiAgICBpZiAna2V5JyBpbiBhcmd1bWVudHMgYW5kIGFyZ3VtZW50cy5rZXkgaXMgbm90IE5vbmU6DQogICAgICAgIGtleSA9IGludChhcmd1bWVudHMua2V5LCAxNikNCiAgICBlbHNlOg0KICAgICAgICBrZXkgPSAweERFQURCRUVGDQoNCiAgICAjIERldGVybWluZSBwYWRkaW5nIGJ5dGVzLg0KICAgIGlmICdwYWRkaW5nJyBpbiBhcmd1bWVudHMgYW5kIGFyZ3VtZW50cy5wYWRkaW5nIGlzIG5vdCBOb25lOg0KICAgICAgICBwYWRkaW5nID0gaW50KGFyZ3VtZW50cy5wYWRkaW5nKQ0KICAgIGVsc2U6DQogICAgICAgIHBhZGRpbmcgPSAwDQoNCiAgICAjIERldGVybWluZSBvdXRwdXQgZmlsZS9kaXJlY3RvcnkgYW5kIGlucHV0IGFyY2hpdmUNCiAgICBpZiBhcmd1bWVudHMuY3JlYXRlOg0KICAgICAgICBhcmNoaXZlID0gTm9uZQ0KICAgICAgICBvdXRwdXQgPSBfdW5pY29kZShhcmd1bWVudHMuYXJjaGl2ZSkNCiAgICBlbHNlOg0KICAgICAgICBhcmNoaXZlID0gX3VuaWNvZGUoYXJndW1lbnRzLmFyY2hpdmUpDQogICAgICAgIGlmICdvdXRmaWxlJyBpbiBhcmd1bWVudHMgYW5kIGFyZ3VtZW50cy5vdXRmaWxlIGlzIG5vdCBOb25lOg0KICAgICAgICAgICAgb3V0cHV0ID0gX3VuaWNvZGUoYXJndW1lbnRzLm91dGZpbGUpDQogICAgICAgIGVsc2U6DQogICAgICAgICAgICAjIERlZmF1bHQgb3V0cHV0IGRpcmVjdG9yeSBmb3IgZXh0cmFjdGlvbiBpcyB0aGUgY3VycmVudCBkaXJlY3RvcnkuDQogICAgICAgICAgICBpZiBhcmd1bWVudHMuZXh0cmFjdDoNCiAgICAgICAgICAgICAgICBvdXRwdXQgPSAnLicNCiAgICAgICAgICAgIGVsc2U6DQogICAgICAgICAgICAgICAgb3V0cHV0ID0gX3VuaWNvZGUoYXJndW1lbnRzLmFyY2hpdmUpDQoNCiAgICAjIE5vcm1hbGl6ZSBmaWxlcy4NCiAgICBpZiBsZW4oYXJndW1lbnRzLmZpbGVzKSA+IDAgYW5kIGlzaW5zdGFuY2UoYXJndW1lbnRzLmZpbGVzWzBdLCBsaXN0KToNCiAgICAgICAgYXJndW1lbnRzLmZpbGVzID0gYXJndW1lbnRzLmZpbGVzWzBdDQoNCiAgICB0cnk6DQogICAgICAgIGFyY2hpdmUgPSBSZW5QeUFyY2hpdmUoYXJjaGl2ZSwgcGFkbGVuZ3RoPXBhZGRpbmcsIGtleT1rZXksIHZlcnNpb249dmVyc2lvbiwgdmVyYm9zZT1hcmd1bWVudHMudmVyYm9zZSkNCiAgICBleGNlcHQgSU9FcnJvciBhcyBlOg0KICAgICAgICBwcmludCgnQ291bGQgbm90IG9wZW4gYXJjaGl2ZSBmaWxlIHswfSBmb3IgcmVhZGluZzogezF9Jy5mb3JtYXQoYXJjaGl2ZSwgZSksIGZpbGU9c3lzLnN0ZGVycikNCiAgICAgICAgc3lzLmV4aXQoMSkNCg0KICAgIGlmIGFyZ3VtZW50cy5jcmVhdGUgb3IgYXJndW1lbnRzLmFwcGVuZDoNCiAgICAgICAgIyBXZSBuZWVkIHRoaXMgc2VwZXJhdGUgZnVuY3Rpb24gdG8gcmVjdXJzaXZlbHkgcHJvY2VzcyBkaXJlY3Rvcmllcy4NCiAgICAgICAgZGVmIGFkZF9maWxlKGZpbGVuYW1lKToNCiAgICAgICAgICAgICMgSWYgdGhlIGFyY2hpdmUgcGF0aCBkaWZmZXJzIGZyb20gdGhlIGFjdHVhbCBmaWxlIHBhdGgsIGFzIGdpdmVuIGluIHRoZSBhcmd1bWVudCwNCiAgICAgICAgICAgICMgZXh0cmFjdCB0aGUgYXJjaGl2ZSBwYXRoIGFuZCBhY3R1YWwgZmlsZSBwYXRoLg0KICAgICAgICAgICAgaWYgZmlsZW5hbWUuZmluZCgnPScpICE9IC0xOg0KICAgICAgICAgICAgICAgIChvdXRmaWxlLCBmaWxlbmFtZSkgPSBmaWxlbmFtZS5zcGxpdCgnPScsIDIpDQogICAgICAgICAgICBlbHNlOg0KICAgICAgICAgICAgICAgIG91dGZpbGUgPSBmaWxlbmFtZQ0KDQogICAgICAgICAgICBpZiBvcy5wYXRoLmlzZGlyKGZpbGVuYW1lKToNCiAgICAgICAgICAgICAgICBmb3IgZmlsZSBpbiBvcy5saXN0ZGlyKGZpbGVuYW1lKToNCiAgICAgICAgICAgICAgICAgICAgIyBXZSBuZWVkIHRvIGRvIHRoaXMgaW4gb3JkZXIgdG8gbWFpbnRhaW4gYSBwb3NzaWJsZSBBUkNISVZFPVJFQUwgbWFwcGluZyBiZXR3ZWVuIGRpcmVjdG9yaWVzLg0KICAgICAgICAgICAgICAgICAgICBhZGRfZmlsZShvdXRmaWxlICsgb3Muc2VwICsgZmlsZSArICc9JyArIGZpbGVuYW1lICsgb3Muc2VwICsgZmlsZSkNCiAgICAgICAgICAgIGVsc2U6DQogICAgICAgICAgICAgICAgdHJ5Og0KICAgICAgICAgICAgICAgICAgICB3aXRoIG9wZW4oZmlsZW5hbWUsICdyYicpIGFzIGZpbGU6DQogICAgICAgICAgICAgICAgICAgICAgICBhcmNoaXZlLmFkZChvdXRmaWxlLCBmaWxlLnJlYWQoKSkNCiAgICAgICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uIGFzIGU6DQogICAgICAgICAgICAgICAgICAgIHByaW50KCdDb3VsZCBub3QgYWRkIGZpbGUgezB9IHRvIGFyY2hpdmU6IHsxfScuZm9ybWF0KGZpbGVuYW1lLCBlKSwgZmlsZT1zeXMuc3RkZXJyKQ0KDQogICAgICAgICMgSXRlcmF0ZSBvdmVyIHRoZSBnaXZlbiBmaWxlcyB0byBhZGQgdG8gYXJjaGl2ZS4NCiAgICAgICAgZm9yIGZpbGVuYW1lIGluIGFyZ3VtZW50cy5maWxlczoNCiAgICAgICAgICAgIGFkZF9maWxlKF91bmljb2RlKGZpbGVuYW1lKSkNCg0KICAgICAgICAjIFNldCB2ZXJzaW9uIGZvciBzYXZpbmcsIGFuZCBzYXZlLg0KICAgICAgICBhcmNoaXZlLnZlcnNpb24gPSB2ZXJzaW9uDQogICAgICAgIHRyeToNCiAgICAgICAgICAgIGFyY2hpdmUuc2F2ZShvdXRwdXQpDQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToNCiAgICAgICAgICAgIHByaW50KCdDb3VsZCBub3Qgc2F2ZSBhcmNoaXZlIGZpbGU6IHswfScuZm9ybWF0KGUpLCBmaWxlPXN5cy5zdGRlcnIpDQogICAgZWxpZiBhcmd1bWVudHMuZGVsZXRlOg0KICAgICAgICAjIEl0ZXJhdGUgb3ZlciB0aGUgZ2l2ZW4gZmlsZXMgdG8gZGVsZXRlIGZyb20gdGhlIGFyY2hpdmUuDQogICAgICAgIGZvciBmaWxlbmFtZSBpbiBhcmd1bWVudHMuZmlsZXM6DQogICAgICAgICAgICB0cnk6DQogICAgICAgICAgICAgICAgYXJjaGl2ZS5yZW1vdmUoZmlsZW5hbWUpDQogICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uIGFzIGU6DQogICAgICAgICAgICAgICAgcHJpbnQoJ0NvdWxkIG5vdCBkZWxldGUgZmlsZSB7MH0gZnJvbSBhcmNoaXZlOiB7MX0nLmZvcm1hdChmaWxlbmFtZSwgZSksIGZpbGU9c3lzLnN0ZGVycikNCg0KICAgICAgICAjIFNldCB2ZXJzaW9uIGZvciBzYXZpbmcsIGFuZCBzYXZlLg0KICAgICAgICBhcmNoaXZlLnZlcnNpb24gPSB2ZXJzaW9uDQogICAgICAgIHRyeToNCiAgICAgICAgICAgIGFyY2hpdmUuc2F2ZShvdXRwdXQpDQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToNCiAgICAgICAgICAgIHByaW50KCdDb3VsZCBub3Qgc2F2ZSBhcmNoaXZlIGZpbGU6IHswfScuZm9ybWF0KGUpLCBmaWxlPXN5cy5zdGRlcnIpDQogICAgZWxpZiBhcmd1bWVudHMuZXh0cmFjdDoNCiAgICAgICAgIyBFaXRoZXIgZXh0cmFjdCB0aGUgZ2l2ZW4gZmlsZXMsIG9yIGFsbCBmaWxlcyBpZiBubyBmaWxlcyBhcmUgZ2l2ZW4uDQogICAgICAgIGlmIGxlbihhcmd1bWVudHMuZmlsZXMpID4gMDoNCiAgICAgICAgICAgIGZpbGVzID0gYXJndW1lbnRzLmZpbGVzDQogICAgICAgIGVsc2U6DQogICAgICAgICAgICBmaWxlcyA9IGFyY2hpdmUubGlzdCgpDQoNCiAgICAgICAgIyBDcmVhdGUgb3V0cHV0IGRpcmVjdG9yeSBpZiBub3QgcHJlc2VudC4NCiAgICAgICAgaWYgbm90IG9zLnBhdGguZXhpc3RzKG91dHB1dCk6DQogICAgICAgICAgICBvcy5tYWtlZGlycyhvdXRwdXQpDQoNCiAgICAgICAgIyBJdGVyYXRlIG92ZXIgZmlsZXMgdG8gZXh0cmFjdC4NCiAgICAgICAgZm9yIGZpbGVuYW1lIGluIGZpbGVzOg0KICAgICAgICAgICAgaWYgZmlsZW5hbWUuZmluZCgnPScpICE9IC0xOg0KICAgICAgICAgICAgICAgIChvdXRmaWxlLCBmaWxlbmFtZSkgPSBmaWxlbmFtZS5zcGxpdCgnPScsIDIpDQogICAgICAgICAgICBlbHNlOg0KICAgICAgICAgICAgICAgIG91dGZpbGUgPSBmaWxlbmFtZQ0KDQogICAgICAgICAgICB0cnk6DQogICAgICAgICAgICAgICAgY29udGVudHMgPSBhcmNoaXZlLnJlYWQoZmlsZW5hbWUpDQoNCiAgICAgICAgICAgICAgICAjIENyZWF0ZSBvdXRwdXQgZGlyZWN0b3J5IGZvciBmaWxlIGlmIG5vdCBwcmVzZW50Lg0KICAgICAgICAgICAgICAgIGlmIG5vdCBvcy5wYXRoLmV4aXN0cyhvcy5wYXRoLmRpcm5hbWUob3MucGF0aC5qb2luKG91dHB1dCwgb3V0ZmlsZSkpKToNCiAgICAgICAgICAgICAgICAgICAgb3MubWFrZWRpcnMob3MucGF0aC5kaXJuYW1lKG9zLnBhdGguam9pbihvdXRwdXQsIG91dGZpbGUpKSkNCg0KICAgICAgICAgICAgICAgIHdpdGggb3Blbihvcy5wYXRoLmpvaW4ob3V0cHV0LCBvdXRmaWxlKSwgJ3diJykgYXMgZmlsZToNCiAgICAgICAgICAgICAgICAgICAgZmlsZS53cml0ZShjb250ZW50cykNCiAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToNCiAgICAgICAgICAgICAgICBwcmludCgnQ291bGQgbm90IGV4dHJhY3QgZmlsZSB7MH0gZnJvbSBhcmNoaXZlOiB7MX0nLmZvcm1hdChmaWxlbmFtZSwgZSksIGZpbGU9c3lzLnN0ZGVycikNCiAgICBlbGlmIGFyZ3VtZW50cy5saXN0Og0KICAgICAgICAjIFByaW50IHRoZSBzb3J0ZWQgZmlsZSBsaXN0Lg0KICAgICAgICBsaXN0ID0gYXJjaGl2ZS5saXN0KCkNCiAgICAgICAgbGlzdC5zb3J0KCkNCiAgICAgICAgZm9yIGZpbGUgaW4gbGlzdDoNCiAgICAgICAgICAgIHByaW50KGZpbGUpDQogICAgZWxzZToNCiAgICAgICAgcHJpbnQoJ05vIG9wZXJhdGlvbiBnaXZlbiA6KCcpDQogICAgICAgIHByaW50KCdVc2UgezB9IC0taGVscCBmb3IgdXNhZ2UgZGV0YWlscy4nLmZvcm1hdChzeXMuYXJndlswXSkpDQoNCg==
    )

    >"!altrpatool!.b64" (
        echo IyEvdXNyL2Jpbi9lbnYgcHl0aG9uDQpmcm9tIF9fZnV0dXJlX18gaW1wb3J0IHByaW50X2Z1bmN0aW9uDQppbXBvcnQgc3lzDQppbXBvcnQgb3MNCmltcG9ydCBhcmdwYXJzZQ0KZnJvbSBwYXRobGliIGltcG9ydCBQYXRoDQoNCnN5cy5wYXRoLmFwcGVuZCgnLi4nKQ0KdHJ5Og0KICAgIGltcG9ydCBtYWluICAjIG5vcWE6IEY0MDENCmV4Y2VwdDoNCiAgICBwYXNzDQoNCmltcG9ydCByZW5weS5vYmplY3QgICMgbm9xYTogRjQwMQ0KaW1wb3J0IHJlbnB5LmNvbmZpZw0KaW1wb3J0IHJlbnB5LmxvYWRlcg0KdHJ5Og0KICAgIGltcG9ydCByZW5weS51dGlsICAjIG5vcWE6IEY0MDENCmV4Y2VwdDoNCiAgICBwYXNzDQoNCg0KY2xhc3MgUmVuUHlBcmNoaXZlOg0KICAgIGRlZiBfX2luaXRfXyhzZWxmLCBmaWxlX3BhdGgsIGluZGV4PTApOg0KICAgICAgICBzZWxmLmZpbGUgPSBzdHIoZmlsZV9wYXRoKQ0KICAgICAgICBzZWxmLmhhbmRsZSA9IE5vbmUNCiAgICAgICAgc2VsZi5maWxlcyA9IHt9DQogICAgICAgIHNlbGYuaW5kZXhlcyA9IHt9DQogICAgICAgIHNlbGYubG9hZChzZWxmLmZpbGUsIGluZGV4KQ0KDQogICAgZGVmIGNvbnZlcnRfZmlsZW5hbWUoc2VsZiwgZmlsZW5hbWUpOg0KICAgICAgICBkcml2ZSwgZmlsZW5hbWUgPSBvcy5wYXRoLnNwbGl0ZHJpdmUoDQogICAgICAgICAgICBvcy5wYXRoLm5vcm1wYXRoKGZpbGVuYW1lKS5yZXBsYWNlKG9zLnNlcCwgJy8nKQ0KICAgICAgICApDQogICAgICAgIHJldHVybiBmaWxlbmFtZQ0KDQogICAgZGVmIGxpc3Qoc2VsZik6DQogICAgICAgIHJldHVybiBsaXN0KHNlbGYuaW5kZXhlcykNCg0KICAgIGRlZiByZWFkKHNlbGYsIGZpbGVuYW1lKToNCiAgICAgICAgZmlsZW5hbWUgPSBzZWxmLmNvbnZlcnRfZmlsZW5hbWUoZmlsZW5hbWUpDQogICAgICAgIGlkeCA9IHNlbGYuaW5kZXhlcy5nZXQoZmlsZW5hbWUpDQogICAgICAgIGlmIGZpbGVuYW1lICE9ICcuJyBhbmQgaXNpbnN0YW5jZShpZHgsIGxpc3QpOg0KICAgICAgICAgICAgaWYgaGFzYXR0cihyZW5weS5sb2FkZXIsICJsb2FkX2Zyb21fYXJjaGl2ZSIpOg0KICAgICAgICAgICAgICAgIHN1YmZpbGUgPSByZW5weS5sb2FkZXIubG9hZF9mcm9tX2FyY2hpdmUoZmlsZW5hbWUpDQogICAgICAgICAgICBlbHNlOg0KICAgICAgICAgICAgICAgIHN1YmZpbGUgPSByZW5weS5sb2FkZXIubG9hZF9jb3JlKGZpbGVuYW1lKQ0KICAgICAgICAgICAgcmV0dXJuIHN1YmZpbGUucmVhZCgpDQogICAgICAgIHJldHVybiBOb25lDQoNCiAgICBkZWYgbG9hZChzZWxmLCBmaWxlbmFtZSwgaW5kZXgpOg0KICAgICAgICBzZWxmLmZpbGUgPSBmaWxlbmFtZQ0KICAgICAgICBzZWxmLmZpbGVzID0ge30NCiAgICAgICAgc2VsZi5pbmRleGVzID0ge30NCg0KICAgICAgICAjIE91dmVydHVyZSBiYXNpcXVlIChjZXJ0YWluZXMgYW5jaWVubmVzIHZlcnNpb25zIHPigJl5IGF0dGVuZGVudCkNCiAgICAgICAgc2VsZi5oYW5kbGUgPSBvcGVuKHNlbGYuZmlsZSwgJ3JiJykNCg0KICAgICAgICBiYXNlID0gb3MucGF0aC5zcGxpdGV4dChvcy5wYXRoLmJhc2VuYW1lKGZpbGVuYW1lKSlbMF0NCg0KICAgICAgICBpZiBiYXNlIG5vdCBpbiByZW5weS5jb25maWcuYXJjaGl2ZXM6DQogICAgICAgICAgICByZW5weS5jb25maWcuYXJjaGl2ZXMuYXBwZW5kKGJhc2UpDQoNCiAgICAgICAgYXJjaGl2ZV9kaXIgPSBvcy5wYXRoLmRpcm5hbWUob3MucGF0aC5yZWFscGF0aChzZWxmLmZpbGUpKQ0KICAgICAgICByZW5weS5jb25maWcuc2VhcmNocGF0aCA9IFthcmNoaXZlX2Rpcl0NCiAgICAgICAgcmVucHkuY29uZmlnLmJhc2VkaXIgPSBvcy5wYXRoLmRpcm5hbWUocmVucHkuY29uZmlnLnNlYXJjaHBhdGhbMF0pDQogICAgICAgIHJlbnB5LmxvYWRlci5pbmRleF9hcmNoaXZlcygpDQoNCiAgICAgICAgIyBSZW7igJlQeSDiiaQgNzogcmVucHkubG9hZGVyLmFyY2hpdmVzIGVzdCB1bmUgbGlzdGUNCiAgICAgICAgYXJjaGl2ZXNfb2JqID0gcmVucHkubG9hZGVyLmFyY2hpdmVzDQogICAgICAgIGl0ZW1zID0gYXJjaGl2ZXNfb2JqW2luZGV4XVsxXS5pdGVtcygpDQogICAgICAgIGZvciBmLCBpZHggaW4gaXRlbXM6DQogICAgICAgICAgICBzZWxmLmluZGV4ZXNbZl0gPSBpZHgNCg0KDQpkZWYgZGlzY292ZXJfZXh0ZW5zaW9ucygpOg0KICAgIGV4dHMgPSBbXQ0KICAgIGlmIGhhc2F0dHIocmVucHkubG9hZGVyLCAiYXJjaGl2ZV9oYW5kbGVycyIpOg0KICAgICAgICBmb3IgaGFuZGxlciBpbiByZW5weS5sb2FkZXIuYXJjaGl2ZV9oYW5kbGVyczoNCiAgICAgICAgICAgIGlmIGhhc2F0dHIoaGFuZGxlciwgImdldF9zdXBwb3J0ZWRfZXh0ZW5zaW9ucyIpOg0KICAgICAgICAgICAgICAgIGV4dHMuZXh0ZW5kKGhhbmRsZXIuZ2V0X3N1cHBvcnRlZF9leHRlbnNpb25zKCkpDQogICAgICAgICAgICBpZiBoYXNhdHRyKGhhbmRsZXIsICJnZXRfc3VwcG9ydGVkX2V4dCIpOg0KICAgICAgICAgICAgICAgIGV4dHMuZXh0ZW5kKGhhbmRsZXIuZ2V0X3N1cHBvcnRlZF9leHQoKSkNCiAgICBlbHNlOg0KICAgICAgICBleHRzLmFwcGVuZCgnLnJwYScpDQoNCiAgICBpZiAnLnJwYycgbm90IGluIGV4dHM6DQogICAgICAgIGV4dHMuYXBwZW5kKCcucnBjJykNCg0KICAgIHJldHVybiBzb3J0ZWQoc2V0KGUubG93ZXIoKSBmb3IgZSBpbiBleHRzKSkNCg0KDQpkZWYgZGlzY292ZXJfYXJjaGl2ZXMoc2VhcmNoX2RpciwgZXh0ZW5zaW9ucyk6DQogICAgYXJjaGl2ZXMgPSBbXQ0KICAgIGZvciByb290LCBkaXJzLCBmaWxlcyBpbiBvcy53YWxrKHN0cihzZWFyY2hfZGlyKSk6DQogICAgICAgIGZvciBmaWxlIGluIGZpbGVzOg0KICAgICAgICAgICAgdHJ5Og0KICAgICAgICAgICAgICAgIGJhc2UsIGV4dCA9IGZpbGUucnNwbGl0KCcuJywgMSkNCiAgICAgICAgICAgICAgICBleHQgPSAnLicgKyBleHQubG93ZXIoKQ0KICAgICAgICAgICAgICAgIGlmIGV4dCBpbiBleHRlbnNpb25zIGFuZCAnJScgbm90IGluIGZpbGU6DQogICAgICAgICAgICAgICAgICAgIGFyY2hpdmVzLmFwcGVuZChQYXRoKHJvb3QpIC8gZmlsZSkNCiAgICAgICAgICAgIGV4Y2VwdCBWYWx1ZUVycm9yOg0KICAgICAgICAgICAgICAgIGNvbnRpbnVlDQogICAgcmV0dXJuIGFyY2hpdmVzDQoNCg0KZGVmIGV4dHJhY3RfYXJjaGl2ZShhcmNoX3BhdGgsIG91dHB1dCk6DQogICAgcHJpbnQoJyAgVW5wYWNraW5nICJ7fSIgYXJjaGl2ZS4nLmZvcm1hdChhcmNoX3BhdGgpKQ0KICAgIGFyY2hpdmUgPSBSZW5QeUFyY2hpdmUoYXJjaF9wYXRoLCAwKQ0KICAgIGZpbGVzID0gYXJjaGl2ZS5saXN0KCkNCg0KICAgIG91dHB1dC5ta2RpcihwYXJlbnRzPVRydWUsIGV4aXN0X29rPVRydWUpDQoNCiAgICBmb3IgZmlsZW5hbWUgaW4gZmlsZXM6DQogICAgICAgIGNvbnRlbnRzID0gYXJjaGl2ZS5yZWFkKGZpbGVuYW1lKQ0KICAgICAgICBpZiBjb250ZW50cyBpcyBub3QgTm9uZToNCiAgICAgICAgICAgIG91dGZpbGUgPSBvdXRwdXQgLyBmaWxlbmFtZQ0KICAgICAgICAgICAgb3V0ZmlsZS5wYXJlbnQubWtkaXIocGFyZW50cz1UcnVlLCBleGlzdF9vaz1UcnVlKQ0KICAgICAgICAgICAgd2l0aCBvcGVuKHN0cihvdXRmaWxlKSwgJ3diJykgYXMgZjoNCiAgICAgICAgICAgICAgICBmLndyaXRlKGNvbnRlbnRzKQ0KDQoNCmRlZiBtYWluKCk6DQogICAgcGFyc2VyID0gYXJncGFyc2UuQXJndW1lbnRQYXJzZXIoDQogICAgICAgIGRlc2NyaXB0aW9uPSdBIHRvb2wgZm9yIHdvcmtpbmcgd2l0aCBSZW5cJ1B5IGFyY2hpdmUgZmlsZXMuJywNCiAgICAgICAgYWRkX2hlbHA9VHJ1ZQ0KICAgICkNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctcicsIGFjdGlvbj0ic3RvcmVfdHJ1ZSIsIGRlc3Q9J3JlbW92ZScsDQogICAgICAgICAgICAgICAgICAgICAgICBoZWxwPSdEZWxldGUgYXJjaGl2ZXMgYWZ0ZXIgdW5wYWNraW5nLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLXgnLCBkZXN0PSdhcmNoaXZlJywgdHlwZT1zdHIsDQogICAgICAgICAgICAgICAgICAgICAgICBoZWxwPSdTcGVjaWZpYyBhcmNoaXZlIGZpbGUgdG8gdW5wYWNrIChmdWxsIHBhdGggb3IgYmFzZW5hbWUpLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLW8nLCBkZXN0PSdvdXRwdXQnLCB0eXBlPXN0ciwgZGVmYXVsdD0nLicsDQogICAgICAgICAgICAgICAgICAgICAgICBoZWxwPSdPdXRwdXQgZGlyZWN0b3J5IGZvciB1bnBhY2tlZCBmaWxlcy4nKQ0KICAgIGFyZ3MgPSBwYXJzZXIucGFyc2VfYXJncygpDQoNCiAgICByZW1vdmUgPSBhcmdzLnJlbW92ZQ0KICAgIG91dHB1dCA9IFBhdGgoYXJncy5vdXRwdXQpLnJlc29sdmUoKQ0KICAgIGFyY2hpdmVfZmlsdGVyID0gYXJncy5hcmNoaXZlDQoNCiAgICBleHRlbnNpb25zID0gZGlzY292ZXJfZXh0ZW5zaW9ucygpDQoNCiAgICAjIC14IG1vZGU6IGV4dHJhY3Qgb25seSB0aGUgc3BlY2lmaWVkIGFyY2hpdmUNCiAgICBpZiBhcmNoaXZlX2ZpbHRlcjoNCiAgICAgICAgdGFyZ2V0ID0gUGF0aChhcmNoaXZlX2ZpbHRlcikucmVzb2x2ZSgpDQogICAgICAgIGlmIG5vdCB0YXJnZXQuZXhpc3RzKCk6DQogICAgICAgICAgICAjIFNlYXJjaCBieSBiYXNlbmFtZSBpbiB0aGUgY3VycmVudCBkaXJlY3RvcnkNCiAgICAgICAgICAgIGJhc2VuYW1lID0gb3MucGF0aC5iYXNlbmFtZShhcmNoaXZlX2ZpbHRlcikNCiAgICAgICAgICAgIGZvdW5kID0gTm9uZQ0KICAgICAgICAgICAgZm9yIHJvb3QsIGRpcnMsIGZpbGVzIGluIG9zLndhbGsoc3RyKFBhdGgoJy4nKS5yZXNvbHZlKCkpKToNCiAgICAgICAgICAgICAgICBpZiBiYXNlbmFtZSBpbiBmaWxlczoNCiAgICAgICAgICAgICAgICAgICAgZm91bmQgPSBQYXRoKHJvb3QpIC8gYmFzZW5hbWUNCiAgICAgICAgICAgICAgICAgICAgYnJlYWsNCiAgICAgICAgICAgIGlmIGZvdW5kIGlzIE5vbmU6DQogICAgICAgICAgICAgICAgcHJpbnQoJyAgQXJjaGl2ZSAie30iIG5vdCBmb3VuZC4nLmZvcm1hdChhcmNoaXZlX2ZpbHRlcikpDQogICAgICAgICAgICAgICAgc3lzLmV4aXQoMSkNCiAgICAgICAgICAgIHRhcmdldCA9IGZvdW5kLnJlc29sdmUoKQ0KDQogICAgICAgIGlmIG5vdCB0YXJnZXQuaXNfZmlsZSgpOg0KICAgICAgICAgICAgcHJpbnQoJyAgTm90IGEgZmlsZToge30nLmZvcm1hdCh0YXJnZXQpKQ0KICAgICAgICAgICAgc3lzLmV4aXQoMSkNCg0KICAgICAgICBfLCBleHQgPSBvcy5wYXRoLnNwbGl0ZXh0KHRhcmdldC5uYW1lKQ0KICAgICAgICBpZiBleHQubG93ZXIoKSBub3QgaW4gZXh0ZW5zaW9uczoNCiAgICAgICAgICAgIHByaW50KCcgIFVuc3VwcG9ydGVkIGV4dGVuc2lvbiB7fSBmb3Ige30uJy5mb3JtYXQoZXh0LCB0YXJnZXQubmFtZSkpDQogICAgICAgICAgICBzeXMuZXhpdCgxKQ0KDQogICAgICAgIGV4dHJhY3RfYXJjaGl2ZSh0YXJnZXQsIG91dHB1dCkNCiAgICAgICAgcHJpbnQoJyAgQXJjaGl2ZSB7fSBoYXMgYmVlbiB1bnBhY2tlZCB0byB7fS4nLmZvcm1hdCh0YXJnZXQubmFtZSwgb3V0cHV0KSkNCg0KICAgICAgICBpZiByZW1vdmU6DQogICAgICAgICAgICBwcmludCgnICBBcmNoaXZlIHt9IGhhcyBiZWVuIGRlbGV0ZWQuJy5mb3JtYXQodGFyZ2V0KSkNCiAgICAgICAgICAgIHRyeToNCiAgICAgICAgICAgICAgICBvcy5yZW1vdmUoc3RyKHRhcmdldCkpDQogICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uIGFzIGVycjoNCiAgICAgICAgICAgICAgICBwcmludCgnICBEZWxldGlvbiBmYWlsZWQ6IHt9Jy5mb3JtYXQoZXJyKSkNCiAgICAgICAgcmV0dXJuDQoNCiAgICAjIERlZmF1bHQgbW9kZTogZXh0cmFjdCBhbGwgYXJjaGl2ZXMgZnJvbSB0aGUgY3VycmVudCBkaXJlY3RvcnkNCiAgICBjdXJyZW50X2RpciA9IFBhdGgoJy4nKS5yZXNvbHZlKCkNCiAgICBhcmNoaXZlcyA9IGRpc2NvdmVyX2FyY2hpdmVzKGN1cnJlbnRfZGlyLCBleHRlbnNpb25zKQ0KDQogICAgaWYgbm90IGFyY2hpdmVzOg0KICAgICAgICBwcmludCgnICBUaGVyZSBhcmUgbm8gYXJjaGl2ZXMgaW4gdGhlIGN1cnJlbnQgZGlyZWN0b3J5LicpDQogICAgICAgIHJldHVybg0KDQogICAgZm9yIGlkeCwgYXJjaCBpbiBlbnVtZXJhdGUoYXJjaGl2ZXMpOg0KICAgICAgICAjIEZvciBSZW4nUHkg4omkIDcsIHRoZSBpbmRleCBpcyB1c2VkIHRvIHN
        echo lbGVjdCB0aGUgYXJjaGl2ZSBmcm9tIHRoZSBpbnRlcm5hbCBsaXN0DQogICAgICAgIGV4dHJhY3RfYXJjaGl2ZShhcmNoLnJlc29sdmUoKSwgb3V0cHV0KQ0KDQogICAgcHJpbnQoJyAgQWxsIGFyY2hpdmVzIHVucGFja2VkIHRvIHt9LicuZm9ybWF0KG91dHB1dCkpDQogICAgaWYgcmVtb3ZlOg0KICAgICAgICBmb3IgYXJjaCBpbiBhcmNoaXZlczoNCiAgICAgICAgICAgIGFwID0gYXJjaC5yZXNvbHZlKCkNCiAgICAgICAgICAgIHByaW50KCcgIEFyY2hpdmUge30gaGFzIGJlZW4gZGVsZXRlZC4nLmZvcm1hdChhcCkpDQogICAgICAgICAgICB0cnk6DQogICAgICAgICAgICAgICAgb3MucmVtb3ZlKHN0cihhcCkpDQogICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uIGFzIGVycjoNCiAgICAgICAgICAgICAgICBwcmludCgnICBEZWxldGlvbiBmYWlsZWQ6IHt9Jy5mb3JtYXQoZXJyKSkNCg0KDQppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOg0KICAgIG1haW4oKQ0K
    )
)

:: rpatool by Shizmob 2022-08-24
::  https://github.com/Shizmob/rpatool
::  Version 0.8 w pickle5 - Require Python ^>= 3.8
if "!RPATOOL-NEW!" == "y" (
    >"!rpatool!.b64" (
        echo IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMw0KDQpmcm9tIF9fZnV0dXJlX18gaW1wb3J0IHByaW50X2Z1bmN0aW9uDQoNCmltcG9ydCBzeXMNCmltcG9ydCBvcw0KaW1wb3J0IGNvZGVjcw0KaW1wb3J0IHBpY2tsZQ0KaW1wb3J0IGVycm5vDQppbXBvcnQgcmFuZG9tDQp0cnk6DQogICAgaW1wb3J0IHBpY2tsZTUgYXMgcGlja2xlDQpleGNlcHQ6DQogICAgaW1wb3J0IHBpY2tsZQ0KICAgIGlmIHN5cy52ZXJzaW9uX2luZm8gPCAoMywgOCk6DQogICAgICAgIHByaW50KCd3YXJuaW5nOiBwaWNrbGU1IG1vZHVsZSBjb3VsZCBub3QgYmUgbG9hZGVkIGFuZCBQeXRob24gdmVyc2lvbiBpcyA8IDMuOCwnLCBmaWxlPXN5cy5zdGRlcnIpDQogICAgICAgIHByaW50KCcgICAgICAgICBuZXdlciBSZW5cJ1B5IGdhbWVzIG1heSBmYWlsIHRvIHVucGFjayEnLCBmaWxlPXN5cy5zdGRlcnIpDQogICAgICAgIGlmIHN5cy52ZXJzaW9uX2luZm8gPj0gKDMsIDUpOg0KICAgICAgICAgICAgcHJpbnQoJyAgICAgICAgIGlmIHRoaXMgb2NjdXJzLCBmaXggaXQgYnkgaW5zdGFsbGluZyBwaWNrbGU1OicsIGZpbGU9c3lzLnN0ZGVycikNCiAgICAgICAgICAgIHByaW50KCcgICAgICAgICAgICAge30gLW0gcGlwIGluc3RhbGwgcGlja2xlNScuZm9ybWF0KHN5cy5leGVjdXRhYmxlKSwgZmlsZT1zeXMuc3RkZXJyKQ0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgcHJpbnQoJyAgICAgICAgIGlmIHRoaXMgb2NjdXJzLCBwbGVhc2UgdXBncmFkZSB0byBhIG5ld2VyIFB5dGhvbiAoPj0gMy41KS4nLCBmaWxlPXN5cy5zdGRlcnIpDQogICAgICAgIHByaW50KGZpbGU9c3lzLnN0ZGVycikNCg0KDQppZiBzeXMudmVyc2lvbl9pbmZvWzBdID49IDM6DQogICAgZGVmIF91bmljb2RlKHRleHQpOg0KICAgICAgICByZXR1cm4gdGV4dA0KDQogICAgZGVmIF9wcmludGFibGUodGV4dCk6DQogICAgICAgIHJldHVybiB0ZXh0DQoNCiAgICBkZWYgX3VubWFuZ2xlKGRhdGEpOg0KICAgICAgICBpZiB0eXBlKGRhdGEpID09IGJ5dGVzOg0KICAgICAgICAgICAgcmV0dXJuIGRhdGENCiAgICAgICAgZWxzZToNCiAgICAgICAgICAgIHJldHVybiBkYXRhLmVuY29kZSgnbGF0aW4xJykNCg0KICAgIGRlZiBfdW5waWNrbGUoZGF0YSk6DQogICAgICAgICMgU3BlY2lmeSBsYXRpbjEgZW5jb2RpbmcgdG8gcHJldmVudCByYXcgYnl0ZSB2YWx1ZXMgZnJvbSBjYXVzaW5nIGFuIEFTQ0lJIGRlY29kZSBlcnJvci4NCiAgICAgICAgcmV0dXJuIHBpY2tsZS5sb2FkcyhkYXRhLCBlbmNvZGluZz0nbGF0aW4xJykNCmVsaWYgc3lzLnZlcnNpb25faW5mb1swXSA9PSAyOg0KICAgIGRlZiBfdW5pY29kZSh0ZXh0KToNCiAgICAgICAgaWYgaXNpbnN0YW5jZSh0ZXh0LCB1bmljb2RlKToNCiAgICAgICAgICAgIHJldHVybiB0ZXh0DQogICAgICAgIHJldHVybiB0ZXh0LmRlY29kZSgndXRmLTgnKQ0KDQogICAgZGVmIF9wcmludGFibGUodGV4dCk6DQogICAgICAgIHJldHVybiB0ZXh0LmVuY29kZSgndXRmLTgnKQ0KDQogICAgZGVmIF91bm1hbmdsZShkYXRhKToNCiAgICAgICAgcmV0dXJuIGRhdGENCg0KICAgIGRlZiBfdW5waWNrbGUoZGF0YSk6DQogICAgICAgIHJldHVybiBwaWNrbGUubG9hZHMoZGF0YSkNCg0KY2xhc3MgUmVuUHlBcmNoaXZlOg0KICAgIGZpbGUgPSBOb25lDQogICAgaGFuZGxlID0gTm9uZQ0KDQogICAgZmlsZXMgPSB7fQ0KICAgIGluZGV4ZXMgPSB7fQ0KDQogICAgdmVyc2lvbiA9IE5vbmUNCiAgICBwYWRsZW5ndGggPSAwDQogICAga2V5ID0gTm9uZQ0KICAgIHZlcmJvc2UgPSBGYWxzZQ0KDQogICAgUlBBMl9NQUdJQyA9ICdSUEEtMi4wICcNCiAgICBSUEEzX01BR0lDID0gJ1JQQS0zLjAgJw0KICAgIFJQQTNfMl9NQUdJQyA9ICdSUEEtMy4yICcNCg0KICAgICMgRm9yIGJhY2t3YXJkIGNvbXBhdGliaWxpdHksIG90aGVyd2lzZSBQeXRob24zLXBhY2tlZCBhcmNoaXZlcyB3b24ndCBiZSByZWFkIGJ5IFB5dGhvbjINCiAgICBQSUNLTEVfUFJPVE9DT0wgPSAyDQoNCiAgICBkZWYgX19pbml0X18oc2VsZiwgZmlsZSA9IE5vbmUsIHZlcnNpb24gPSAzLCBwYWRsZW5ndGggPSAwLCBrZXkgPSAweERFQURCRUVGLCB2ZXJib3NlID0gRmFsc2UpOg0KICAgICAgICBzZWxmLnBhZGxlbmd0aCA9IHBhZGxlbmd0aA0KICAgICAgICBzZWxmLmtleSA9IGtleQ0KICAgICAgICBzZWxmLnZlcmJvc2UgPSB2ZXJib3NlDQoNCiAgICAgICAgaWYgZmlsZSBpcyBub3QgTm9uZToNCiAgICAgICAgICAgIHNlbGYubG9hZChmaWxlKQ0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgc2VsZi52ZXJzaW9uID0gdmVyc2lvbg0KDQogICAgZGVmIF9fZGVsX18oc2VsZik6DQogICAgICAgIGlmIHNlbGYuaGFuZGxlIGlzIG5vdCBOb25lOg0KICAgICAgICAgICAgc2VsZi5oYW5kbGUuY2xvc2UoKQ0KDQogICAgIyBEZXRlcm1pbmUgYXJjaGl2ZSB2ZXJzaW9uLg0KICAgIGRlZiBnZXRfdmVyc2lvbihzZWxmKToNCiAgICAgICAgc2VsZi5oYW5kbGUuc2VlaygwKQ0KICAgICAgICBtYWdpYyA9IHNlbGYuaGFuZGxlLnJlYWRsaW5lKCkuZGVjb2RlKCd1dGYtOCcpDQoNCiAgICAgICAgaWYgbWFnaWMuc3RhcnRzd2l0aChzZWxmLlJQQTNfMl9NQUdJQyk6DQogICAgICAgICAgICByZXR1cm4gMy4yDQogICAgICAgIGVsaWYgbWFnaWMuc3RhcnRzd2l0aChzZWxmLlJQQTNfTUFHSUMpOg0KICAgICAgICAgICAgcmV0dXJuIDMNCiAgICAgICAgZWxpZiBtYWdpYy5zdGFydHN3aXRoKHNlbGYuUlBBMl9NQUdJQyk6DQogICAgICAgICAgICByZXR1cm4gMg0KICAgICAgICBlbGlmIHNlbGYuZmlsZS5lbmRzd2l0aCgnLnJwaScpOg0KICAgICAgICAgICAgcmV0dXJuIDENCg0KICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCd0aGUgZ2l2ZW4gZmlsZSBpcyBub3QgYSB2YWxpZCBSZW5cJ1B5IGFyY2hpdmUsIG9yIGFuIHVuc3VwcG9ydGVkIHZlcnNpb24nKQ0KDQogICAgIyBFeHRyYWN0IGZpbGUgaW5kZXhlcyBmcm9tIG9wZW5lZCBhcmNoaXZlLg0KICAgIGRlZiBleHRyYWN0X2luZGV4ZXMoc2VsZik6DQogICAgICAgIHNlbGYuaGFuZGxlLnNlZWsoMCkNCiAgICAgICAgaW5kZXhlcyA9IE5vbmUNCg0KICAgICAgICBpZiBzZWxmLnZlcnNpb24gaW4gWzIsIDMsIDMuMl06DQogICAgICAgICAgICAjIEZldGNoIG1ldGFkYXRhLg0KICAgICAgICAgICAgbWV0YWRhdGEgPSBzZWxmLmhhbmRsZS5yZWFkbGluZSgpDQogICAgICAgICAgICB2YWxzID0gbWV0YWRhdGEuc3BsaXQoKQ0KICAgICAgICAgICAgb2Zmc2V0ID0gaW50KHZhbHNbMV0sIDE2KQ0KICAgICAgICAgICAgaWYgc2VsZi52ZXJzaW9uID09IDM6DQogICAgICAgICAgICAgICAgc2VsZi5rZXkgPSAwDQogICAgICAgICAgICAgICAgZm9yIHN1YmtleSBpbiB2YWxzWzI6XToNCiAgICAgICAgICAgICAgICAgICAgc2VsZi5rZXkgXj0gaW50KHN1YmtleSwgMTYpDQogICAgICAgICAgICBlbGlmIHNlbGYudmVyc2lvbiA9PSAzLjI6DQogICAgICAgICAgICAgICAgc2VsZi5rZXkgPSAwDQogICAgICAgICAgICAgICAgZm9yIHN1YmtleSBpbiB2YWxzWzM6XToNCiAgICAgICAgICAgICAgICAgICAgc2VsZi5rZXkgXj0gaW50KHN1YmtleSwgMTYpDQoNCiAgICAgICAgICAgICMgTG9hZCBpbiBpbmRleGVzLg0KICAgICAgICAgICAgc2VsZi5oYW5kbGUuc2VlayhvZmZzZXQpDQogICAgICAgICAgICBjb250ZW50cyA9IGNvZGVjcy5kZWNvZGUoc2VsZi5oYW5kbGUucmVhZCgpLCAnemxpYicpDQogICAgICAgICAgICBpbmRleGVzID0gX3VucGlja2xlKGNvbnRlbnRzKQ0KDQogICAgICAgICAgICAjIERlb2JmdXNjYXRlIGluZGV4ZXMuDQogICAgICAgICAgICBpZiBzZWxmLnZlcnNpb24gaW4gWzMsIDMuMl06DQogICAgICAgICAgICAgICAgb2JmdXNjYXRlZF9pbmRleGVzID0gaW5kZXhlcw0KICAgICAgICAgICAgICAgIGluZGV4ZXMgPSB7fQ0KICAgICAgICAgICAgICAgIGZvciBpIGluIG9iZnVzY2F0ZWRfaW5kZXhlcy5rZXlzKCk6DQogICAgICAgICAgICAgICAgICAgIGlmIGxlbihvYmZ1c2NhdGVkX2luZGV4ZXNbaV1bMF0pID09IDI6DQogICAgICAgICAgICAgICAgICAgICAgICBpbmRleGVzW2ldID0gWyAob2Zmc2V0IF4gc2VsZi5rZXksIGxlbmd0aCBeIHNlbGYua2V5KSBmb3Igb2Zmc2V0LCBsZW5ndGggaW4gb2JmdXNjYXRlZF9pbmRleGVzW2ldIF0NCiAgICAgICAgICAgICAgICAgICAgZWxzZToNCiAgICAgICAgICAgICAgICAgICAgICAgIGluZGV4ZXNbaV0gPSBbIChvZmZzZXQgXiBzZWxmLmtleSwgbGVuZ3RoIF4gc2VsZi5rZXksIHByZWZpeCkgZm9yIG9mZnNldCwgbGVuZ3RoLCBwcmVmaXggaW4gb2JmdXNjYXRlZF9pbmRleGVzW2ldIF0NCiAgICAgICAgZWxzZToNCiAgICAgICAgICAgIGluZGV4ZXMgPSBwaWNrbGUubG9hZHMoY29kZWNzLmRlY29kZShzZWxmLmhhbmRsZS5yZWFkKCksICd6bGliJykpDQoNCiAgICAgICAgcmV0dXJuIGluZGV4ZXMNCg0KICAgICMgR2VuZXJhdGUgcHNldWRvcmFuZG9tIHBhZGRpbmcgKGZvciB3aGF0ZXZlciByZWFzb24pLg0KICAgIGRlZiBnZW5lcmF0ZV9wYWRkaW5nKHNlbGYpOg0KICAgICAgICBsZW5ndGggPSByYW5kb20ucmFuZGludCgxLCBzZWxmLnBhZGxlbmd0aCkNCg0KICAgICAgICBwYWRkaW5nID0gJycNCiAgICAgICAgd2hpbGUgbGVuZ3RoID4gMDoNCiAgICAgICAgICAgIHBhZGRpbmcgKz0gY2hyKHJhbmRvbS5yYW5kaW50KDEsIDI1NSkpDQogICAgICAgICAgICBsZW5ndGggLT0gMQ0KDQogICAgICAgIHJldHVybiBieXRlcyhwYWRkaW5nLCAndXRmLTgnKQ0KDQogICAgIyBDb252ZXJ0cyBhIGZpbGVuYW1lIHRvIGFyY2hpdmUgZm9ybWF0Lg0KICAgIGRlZiBjb252ZXJ0X2ZpbGVuYW1lKHNlbGYsIGZpbGVuYW1lKToNCiAgICAgICAgKGRyaXZlLCBmaWxlbmFtZSkgPSBvcy5wYXRoLnNwbGl0ZHJpdmUob3MucGF0aC5ub3JtcGF0aChmaWxlbmFtZSkucmVwbGFjZShvcy5zZXAsICcvJykpDQogICAgICAgIHJldHVybiBmaWxlbmFtZQ0KDQogICAgIyBEZWJ1ZyAodmVyYm9zZSkgbWVzc2FnZXMuDQogICAgZGVmIHZlcmJvc2VfcHJpbnQoc2VsZiwgbWVzc2FnZSk6DQogICAgICAgIGlmIHNlbGYudmVyYm9zZToNCiAgICAgICAgICAgIHByaW50KG1lc3NhZ2UpDQoNCg0KICAgICMgTGlzdCBmaWxlcyBpbiBhcmNoaXZlIGFuZCBjdXJyZW50IGludGVybmFsIHN0b3JhZ2UuDQogICAgZGVmIGxpc3Qoc2VsZik6DQogICAgICAgIHJldHVybiBsaXN0KHNlbGYuaW5kZXhlcy5rZXlzKCkpICsgbGlzdChzZWxmLmZpbGVzLmtleXMoKSkNCg0KICAgICMgQ2hlY2sgaWYgYSBmaWxlIGV4aXN0cyBpbiB0aGUgYXJjaGl2ZS4NCiAgICBkZWYgaGFzX2ZpbGUoc2VsZiwgZmlsZW5hbWUpOg0KICAgICAgICBmaWxlbmFtZSA9IF91bmljb2RlKGZpbGVuYW1lKQ0KICAgICAgICByZXR1cm4gZmlsZW5hbWUgaW4gc2VsZi5pbmRleGVzLmtleXMoKSBvciBmaWxlbmFtZSBpbiBzZWxmLmZpbGVzLmtleXMoKQ0KDQogICAgIyBSZWFkIGZpbGUgZnJvbSBhcmNoaXZlIG9yIGludGVybmFsIHN0b3JhZ2UuDQogICAgZGVmIHJlYWQoc2VsZiwgZmlsZW5hbWUpOg0KICAgICAgICBmaWxlbmFtZSA9IHNlbGYuY29udmVydF9maWxlbmFtZShfdW5pY29kZShmaWxlbmFtZSkpDQoNCiAgICAgICAgIyBDaGVjayBpZiB0aGUgZmlsZSBleGlzdHMgaW4gb3VyIGluZGV4ZXMuDQogICAgICAgIGlmIGZpbGVuYW1lIG5vdCBpbiBzZWxmLmZpbGVzIGFuZCBmaWxlbmFtZSBub3QgaW4gc2VsZi5pbmRleGVzOg0KICAgICAgICAgICAgcmFpc2UgSU9FcnJvcihlcnJuby5FTk9FTlQsICd0aGUgcmVxdWVzdGVkIGZpbGUgezB9IGRvZXMgbm90IGV4aXN0IGluIHRoZSBnaXZlbiBSZW5cJ1B5IGFyY2hpdmUnLmZvcm1hdCgNCiAgICAgICAgICAgICAgICBfcHJpbnRhYmxlKGZpbGVuYW1lKSkpDQoNCiAgICAgICAgIyBJZiBpdCdzIGluIG91ciBvcGVuZWQgYXJjaGl2ZSBpbmRleCwgYW5kIG91ciBhcmNoaXZlIGhhbmRsZSBpc24ndCB2YWxpZCwgc29tZXRoaW5nIGlzIG9idmlvdXNseSB3cm9uZy4NCiAgICAgICAgaWYgZmlsZW5hbWUgbm90IGluIHNlbGYuZmlsZXMgYW5kIGZpbGVuYW1lIGluIHNlbGYuaW5kZXhlcyBhbmQgc2VsZi5oYW5kbGUgaXMgTm9uZToNCiAgICAgICAgICAgIHJhaXNlIElPRXJyb3IoZXJybm8uRU5PRU5ULCA
        echo ndGhlIHJlcXVlc3RlZCBmaWxlIHswfSBkb2VzIG5vdCBleGlzdCBpbiB0aGUgZ2l2ZW4gUmVuXCdQeSBhcmNoaXZlJy5mb3JtYXQoDQogICAgICAgICAgICAgICAgX3ByaW50YWJsZShmaWxlbmFtZSkpKQ0KDQogICAgICAgICMgQ2hlY2sgb3VyIHNpbXBsaWZpZWQgaW50ZXJuYWwgaW5kZXhlcyBmaXJzdCwgaW4gY2FzZSBzb21lb25lIHdhbnRzIHRvIHJlYWQgYSBmaWxlIHRoZXkgYWRkZWQgYmVmb3JlIHdpdGhvdXQgc2F2aW5nLCBmb3Igc29tZSB1bmhvbHkgcmVhc29uLg0KICAgICAgICBpZiBmaWxlbmFtZSBpbiBzZWxmLmZpbGVzOg0KICAgICAgICAgICAgc2VsZi52ZXJib3NlX3ByaW50KCdSZWFkaW5nIGZpbGUgezB9IGZyb20gaW50ZXJuYWwgc3RvcmFnZS4uLicuZm9ybWF0KF9wcmludGFibGUoZmlsZW5hbWUpKSkNCiAgICAgICAgICAgIHJldHVybiBzZWxmLmZpbGVzW2ZpbGVuYW1lXQ0KICAgICAgICAjIFdlIG5lZWQgdG8gcmVhZCB0aGUgZmlsZSBmcm9tIG91ciBvcGVuIGFyY2hpdmUuDQogICAgICAgIGVsc2U6DQogICAgICAgICAgICAjIFJlYWQgb2Zmc2V0IGFuZCBsZW5ndGgsIHNlZWsgdG8gdGhlIG9mZnNldCBhbmQgcmVhZCB0aGUgZmlsZSBjb250ZW50cy4NCiAgICAgICAgICAgIGlmIGxlbihzZWxmLmluZGV4ZXNbZmlsZW5hbWVdWzBdKSA9PSAzOg0KICAgICAgICAgICAgICAgIChvZmZzZXQsIGxlbmd0aCwgcHJlZml4KSA9IHNlbGYuaW5kZXhlc1tmaWxlbmFtZV1bMF0NCiAgICAgICAgICAgIGVsc2U6DQogICAgICAgICAgICAgICAgKG9mZnNldCwgbGVuZ3RoKSA9IHNlbGYuaW5kZXhlc1tmaWxlbmFtZV1bMF0NCiAgICAgICAgICAgICAgICBwcmVmaXggPSAnJw0KDQogICAgICAgICAgICBzZWxmLnZlcmJvc2VfcHJpbnQoJ1JlYWRpbmcgZmlsZSB7MH0gZnJvbSBkYXRhIGZpbGUgezF9Li4uIChvZmZzZXQgPSB7Mn0sIGxlbmd0aCA9IHszfSBieXRlcyknLmZvcm1hdCgNCiAgICAgICAgICAgICAgICBfcHJpbnRhYmxlKGZpbGVuYW1lKSwgc2VsZi5maWxlLCBvZmZzZXQsIGxlbmd0aCkpDQogICAgICAgICAgICBzZWxmLmhhbmRsZS5zZWVrKG9mZnNldCkNCiAgICAgICAgICAgIHJldHVybiBfdW5tYW5nbGUocHJlZml4KSArIHNlbGYuaGFuZGxlLnJlYWQobGVuZ3RoIC0gbGVuKHByZWZpeCkpDQoNCiAgICAjIE1vZGlmeSBhIGZpbGUgaW4gYXJjaGl2ZSBvciBpbnRlcm5hbCBzdG9yYWdlLg0KICAgIGRlZiBjaGFuZ2Uoc2VsZiwgZmlsZW5hbWUsIGNvbnRlbnRzKToNCiAgICAgICAgZmlsZW5hbWUgPSBfdW5pY29kZShmaWxlbmFtZSkNCg0KICAgICAgICAjIE91ciAnY2hhbmdlJyBpcyBiYXNpY2FsbHkgcmVtb3ZpbmcgdGhlIGZpbGUgZnJvbSBvdXIgaW5kZXhlcyBmaXJzdCwgYW5kIHRoZW4gcmUtYWRkaW5nIGl0Lg0KICAgICAgICBzZWxmLnJlbW92ZShmaWxlbmFtZSkNCiAgICAgICAgc2VsZi5hZGQoZmlsZW5hbWUsIGNvbnRlbnRzKQ0KDQogICAgIyBBZGQgYSBmaWxlIHRvIHRoZSBpbnRlcm5hbCBzdG9yYWdlLg0KICAgIGRlZiBhZGQoc2VsZiwgZmlsZW5hbWUsIGNvbnRlbnRzKToNCiAgICAgICAgZmlsZW5hbWUgPSBzZWxmLmNvbnZlcnRfZmlsZW5hbWUoX3VuaWNvZGUoZmlsZW5hbWUpKQ0KICAgICAgICBpZiBmaWxlbmFtZSBpbiBzZWxmLmZpbGVzIG9yIGZpbGVuYW1lIGluIHNlbGYuaW5kZXhlczoNCiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ2ZpbGUgezB9IGFscmVhZHkgZXhpc3RzIGluIGFyY2hpdmUnLmZvcm1hdChfcHJpbnRhYmxlKGZpbGVuYW1lKSkpDQoNCiAgICAgICAgc2VsZi52ZXJib3NlX3ByaW50KCdBZGRpbmcgZmlsZSB7MH0gdG8gYXJjaGl2ZS4uLiAobGVuZ3RoID0gezF9IGJ5dGVzKScuZm9ybWF0KA0KICAgICAgICAgICAgX3ByaW50YWJsZShmaWxlbmFtZSksIGxlbihjb250ZW50cykpKQ0KICAgICAgICBzZWxmLmZpbGVzW2ZpbGVuYW1lXSA9IGNvbnRlbnRzDQoNCiAgICAjIFJlbW92ZSBhIGZpbGUgZnJvbSBhcmNoaXZlIG9yIGludGVybmFsIHN0b3JhZ2UuDQogICAgZGVmIHJlbW92ZShzZWxmLCBmaWxlbmFtZSk6DQogICAgICAgIGZpbGVuYW1lID0gX3VuaWNvZGUoZmlsZW5hbWUpDQogICAgICAgIGlmIGZpbGVuYW1lIGluIHNlbGYuZmlsZXM6DQogICAgICAgICAgICBzZWxmLnZlcmJvc2VfcHJpbnQoJ1JlbW92aW5nIGZpbGUgezB9IGZyb20gaW50ZXJuYWwgc3RvcmFnZS4uLicuZm9ybWF0KF9wcmludGFibGUoZmlsZW5hbWUpKSkNCiAgICAgICAgICAgIGRlbCBzZWxmLmZpbGVzW2ZpbGVuYW1lXQ0KICAgICAgICBlbGlmIGZpbGVuYW1lIGluIHNlbGYuaW5kZXhlczoNCiAgICAgICAgICAgIHNlbGYudmVyYm9zZV9wcmludCgnUmVtb3ZpbmcgZmlsZSB7MH0gZnJvbSBhcmNoaXZlIGluZGV4ZXMuLi4nLmZvcm1hdChfcHJpbnRhYmxlKGZpbGVuYW1lKSkpDQogICAgICAgICAgICBkZWwgc2VsZi5pbmRleGVzW2ZpbGVuYW1lXQ0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgcmFpc2UgSU9FcnJvcihlcnJuby5FTk9FTlQsICd0aGUgcmVxdWVzdGVkIGZpbGUgezB9IGRvZXMgbm90IGV4aXN0IGluIHRoaXMgYXJjaGl2ZScuZm9ybWF0KF9wcmludGFibGUoZmlsZW5hbWUpKSkNCg0KICAgICMgTG9hZCBhcmNoaXZlLg0KICAgIGRlZiBsb2FkKHNlbGYsIGZpbGVuYW1lKToNCiAgICAgICAgZmlsZW5hbWUgPSBfdW5pY29kZShmaWxlbmFtZSkNCg0KICAgICAgICBpZiBzZWxmLmhhbmRsZSBpcyBub3QgTm9uZToNCiAgICAgICAgICAgIHNlbGYuaGFuZGxlLmNsb3NlKCkNCiAgICAgICAgc2VsZi5maWxlID0gZmlsZW5hbWUNCiAgICAgICAgc2VsZi5maWxlcyA9IHt9DQogICAgICAgIHNlbGYuaGFuZGxlID0gb3BlbihzZWxmLmZpbGUsICdyYicpDQogICAgICAgIHNlbGYudmVyc2lvbiA9IHNlbGYuZ2V0X3ZlcnNpb24oKQ0KICAgICAgICBzZWxmLmluZGV4ZXMgPSBzZWxmLmV4dHJhY3RfaW5kZXhlcygpDQoNCiAgICAjIFNhdmUgY3VycmVudCBzdGF0ZSBpbnRvIGEgbmV3IGZpbGUsIG1lcmdpbmcgYXJjaGl2ZSBhbmQgaW50ZXJuYWwgc3RvcmFnZSwgcmVidWlsZGluZyBpbmRleGVzLCBhbmQgb3B0aW9uYWxseSBzYXZpbmcgaW4gYW5vdGhlciBmb3JtYXQgdmVyc2lvbi4NCiAgICBkZWYgc2F2ZShzZWxmLCBmaWxlbmFtZSA9IE5vbmUpOg0KICAgICAgICBmaWxlbmFtZSA9IF91bmljb2RlKGZpbGVuYW1lKQ0KDQogICAgICAgIGlmIGZpbGVuYW1lIGlzIE5vbmU6DQogICAgICAgICAgICBmaWxlbmFtZSA9IHNlbGYuZmlsZQ0KICAgICAgICBpZiBmaWxlbmFtZSBpcyBOb25lOg0KICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignbm8gdGFyZ2V0IGZpbGUgZm91bmQgZm9yIHNhdmluZyBhcmNoaXZlJykNCiAgICAgICAgaWYgc2VsZi52ZXJzaW9uICE9IDIgYW5kIHNlbGYudmVyc2lvbiAhPSAzOg0KICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignc2F2aW5nIGlzIG9ubHkgc3VwcG9ydGVkIGZvciB2ZXJzaW9uIDIgYW5kIDMgYXJjaGl2ZXMnKQ0KDQogICAgICAgIHNlbGYudmVyYm9zZV9wcmludCgnUmVidWlsZGluZyBhcmNoaXZlIGluZGV4Li4uJykNCiAgICAgICAgIyBGaWxsIG91ciBvd24gZmlsZXMgc3RydWN0dXJlIHdpdGggdGhlIGZpbGVzIGFkZGVkIG9yIGNoYW5nZWQgaW4gdGhpcyBzZXNzaW9uLg0KICAgICAgICBmaWxlcyA9IHNlbGYuZmlsZXMNCiAgICAgICAgIyBGaXJzdCwgcmVhZCBmaWxlcyBmcm9tIHRoZSBjdXJyZW50IGFyY2hpdmUgaW50byBvdXIgZmlsZXMgc3RydWN0dXJlLg0KICAgICAgICBmb3IgZmlsZSBpbiBsaXN0KHNlbGYuaW5kZXhlcy5rZXlzKCkpOg0KICAgICAgICAgICAgY29udGVudCA9IHNlbGYucmVhZChmaWxlKQ0KICAgICAgICAgICAgIyBSZW1vdmUgZnJvbSBpbmRleGVzIGFycmF5IG9uY2UgcmVhZCwgYWRkIHRvIG91ciBvd24gYXJyYXkuDQogICAgICAgICAgICBkZWwgc2VsZi5pbmRleGVzW2ZpbGVdDQogICAgICAgICAgICBmaWxlc1tmaWxlXSA9IGNvbnRlbnQNCg0KICAgICAgICAjIFByZWRpY3QgaGVhZGVyIGxlbmd0aCwgd2UnbGwgd3JpdGUgdGhhdCBvbmUgbGFzdC4NCiAgICAgICAgb2Zmc2V0ID0gMA0KICAgICAgICBpZiBzZWxmLnZlcnNpb24gPT0gMzoNCiAgICAgICAgICAgIG9mZnNldCA9IDM0DQogICAgICAgIGVsaWYgc2VsZi52ZXJzaW9uID09IDI6DQogICAgICAgICAgICBvZmZzZXQgPSAyNQ0KICAgICAgICBhcmNoaXZlID0gb3BlbihmaWxlbmFtZSwgJ3diJykNCiAgICAgICAgYXJjaGl2ZS5zZWVrKG9mZnNldCkNCg0KICAgICAgICAjIEJ1aWxkIG91ciBvd24gaW5kZXhlcyB3aGlsZSB3cml0aW5nIGZpbGVzIHRvIHRoZSBhcmNoaXZlLg0KICAgICAgICBpbmRleGVzID0ge30NCiAgICAgICAgc2VsZi52ZXJib3NlX3ByaW50KCdXcml0aW5nIGZpbGVzIHRvIGFyY2hpdmUgZmlsZS4uLicpDQogICAgICAgIGZvciBmaWxlLCBjb250ZW50IGluIGZpbGVzLml0ZW1zKCk6DQogICAgICAgICAgICAjIEdlbmVyYXRlIHJhbmRvbSBwYWRkaW5nLCBmb3Igd2hhdGV2ZXIgcmVhc29uLg0KICAgICAgICAgICAgaWYgc2VsZi5wYWRsZW5ndGggPiAwOg0KICAgICAgICAgICAgICAgIHBhZGRpbmcgPSBzZWxmLmdlbmVyYXRlX3BhZGRpbmcoKQ0KICAgICAgICAgICAgICAgIGFyY2hpdmUud3JpdGUocGFkZGluZykNCiAgICAgICAgICAgICAgICBvZmZzZXQgKz0gbGVuKHBhZGRpbmcpDQoNCiAgICAgICAgICAgIGFyY2hpdmUud3JpdGUoY29udGVudCkNCiAgICAgICAgICAgICMgVXBkYXRlIGluZGV4Lg0KICAgICAgICAgICAgaWYgc2VsZi52ZXJzaW9uID09IDM6DQogICAgICAgICAgICAgICAgaW5kZXhlc1tmaWxlXSA9IFsgKG9mZnNldCBeIHNlbGYua2V5LCBsZW4oY29udGVudCkgXiBzZWxmLmtleSkgXQ0KICAgICAgICAgICAgZWxpZiBzZWxmLnZlcnNpb24gPT0gMjoNCiAgICAgICAgICAgICAgICBpbmRleGVzW2ZpbGVdID0gWyAob2Zmc2V0LCBsZW4oY29udGVudCkpIF0NCiAgICAgICAgICAgIG9mZnNldCArPSBsZW4oY29udGVudCkNCg0KICAgICAgICAjIFdyaXRlIHRoZSBpbmRleGVzLg0KICAgICAgICBzZWxmLnZlcmJvc2VfcHJpbnQoJ1dyaXRpbmcgYXJjaGl2ZSBpbmRleCB0byBhcmNoaXZlIGZpbGUuLi4nKQ0KICAgICAgICBhcmNoaXZlLndyaXRlKGNvZGVjcy5lbmNvZGUocGlja2xlLmR1bXBzKGluZGV4ZXMsIHNlbGYuUElDS0xFX1BST1RPQ09MKSwgJ3psaWInKSkNCiAgICAgICAgIyBOb3cgd3JpdGUgdGhlIGhlYWRlci4NCiAgICAgICAgc2VsZi52ZXJib3NlX3ByaW50KCdXcml0aW5nIGhlYWRlciB0byBhcmNoaXZlIGZpbGUuLi4gKHZlcnNpb24gPSBSUEF2ezB9KScuZm9ybWF0KHNlbGYudmVyc2lvbikpDQogICAgICAgIGFyY2hpdmUuc2VlaygwKQ0KICAgICAgICBpZiBzZWxmLnZlcnNpb24gPT0gMzoNCiAgICAgICAgICAgIGFyY2hpdmUud3JpdGUoY29kZWNzLmVuY29kZSgne317OjAxNnh9IHs6MDh4fVxuJy5mb3JtYXQoc2VsZi5SUEEzX01BR0lDLCBvZmZzZXQsIHNlbGYua2V5KSkpDQogICAgICAgIGVsc2U6DQogICAgICAgICAgICBhcmNoaXZlLndyaXRlKGNvZGVjcy5lbmNvZGUoJ3t9ezowMTZ4fVxuJy5mb3JtYXQoc2VsZi5SUEEyX01BR0lDLCBvZmZzZXQpKSkNCiAgICAgICAgIyBXZSdyZSBkb25lLCBjbG9zZSBpdC4NCiAgICAgICAgYXJjaGl2ZS5jbG9zZSgpDQoNCiAgICAgICAgIyBSZWxvYWQgdGhlIGZpbGUgaW4gb3VyIGlubmVyIGRhdGFiYXNlLg0KICAgICAgICBzZWxmLmxvYWQoZmlsZW5hbWUpDQoNCmlmIF9fbmFtZV9fID09ICJfX21haW5fXyI6DQogICAgaW1wb3J0IGFyZ3BhcnNlDQoNCiAgICBwYXJzZXIgPSBhcmdwYXJzZS5Bcmd1bWVudFBhcnNlcigNCiAgICAgICAgZGVzY3JpcHRpb249J0EgdG9vbCBmb3Igd29ya2luZyB3aXRoIFJlblwnUHkgYXJjaGl2ZSBmaWxlcy4nLA0KICAgICAgICBlcGlsb2c9J1RoZSBGSUxFIGFyZ3VtZW50IGNhbiBvcHRpb25hbGx5IGJlIGluIEFSQ0hJVkU9UkVBTCBmb3JtYXQsIG1hcHBpbmcgYSBmaWxlIGluIHRoZSBhcmNoaXZlIGZpbGUgc3lzdGVtIHRvIGEgZmlsZSBvbiB5b3VyIHJlYWwgZmlsZSBzeXN0ZW0uIEFuIGV4YW1wbGUgb2YgdGhpczogcnBhdG9vbCAteCB0ZXN0LnJwYSBzY3JpcHQucnB5Yz0vaG9tZS9mb28vdGVzdC5ycHljJywNCiAgICAgICAgYWRkX2hlbHA9RmFsc2UpDQoNCi
        echo AgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCdhcmNoaXZlJywgbWV0YXZhcj0nQVJDSElWRScsIGhlbHA9J1RoZSBSZW5cJ3B5IGFyY2hpdmUgZmlsZSB0byBvcGVyYXRlIG9uLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnZmlsZXMnLCBtZXRhdmFyPSdGSUxFJywgbmFyZ3M9JyonLCBhY3Rpb249J2FwcGVuZCcsIGhlbHA9J1plcm8gb3IgbW9yZSBmaWxlcyB0byBvcGVyYXRlIG9uLicpDQoNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctbCcsICctLWxpc3QnLCBhY3Rpb249J3N0b3JlX3RydWUnLCBoZWxwPSdMaXN0IGZpbGVzIGluIGFyY2hpdmUgQVJDSElWRS4nKQ0KICAgIHBhcnNlci5hZGRfYXJndW1lbnQoJy14JywgJy0tZXh0cmFjdCcsIGFjdGlvbj0nc3RvcmVfdHJ1ZScsIGhlbHA9J0V4dHJhY3QgRklMRXMgZnJvbSBBUkNISVZFLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLWMnLCAnLS1jcmVhdGUnLCBhY3Rpb249J3N0b3JlX3RydWUnLCBoZWxwPSdDcmVhdGl2ZSBBUkNISVZFIGZyb20gRklMRXMuJykNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctZCcsICctLWRlbGV0ZScsIGFjdGlvbj0nc3RvcmVfdHJ1ZScsIGhlbHA9J0RlbGV0ZSBGSUxFcyBmcm9tIEFSQ0hJVkUuJykNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctYScsICctLWFwcGVuZCcsIGFjdGlvbj0nc3RvcmVfdHJ1ZScsIGhlbHA9J0FwcGVuZCBGSUxFcyB0byBBUkNISVZFLicpDQoNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctMicsICctLXR3bycsIGFjdGlvbj0nc3RvcmVfdHJ1ZScsIGhlbHA9J1VzZSB0aGUgUlBBdjIgZm9ybWF0IGZvciBjcmVhdGluZy9hcHBlbmRpbmcgdG8gYXJjaGl2ZXMuJykNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctMycsICctLXRocmVlJywgYWN0aW9uPSdzdG9yZV90cnVlJywgaGVscD0nVXNlIHRoZSBSUEF2MyBmb3JtYXQgZm9yIGNyZWF0aW5nL2FwcGVuZGluZyB0byBhcmNoaXZlcyAoZGVmYXVsdCkuJykNCg0KICAgIHBhcnNlci5hZGRfYXJndW1lbnQoJy1rJywgJy0ta2V5JywgbWV0YXZhcj0nS0VZJywgaGVscD0nVGhlIG9iZnVzY2F0aW9uIGtleSB1c2VkIGZvciBjcmVhdGluZyBSUEF2MyBhcmNoaXZlcywgaW4gaGV4YWRlY2ltYWwgKGRlZmF1bHQ6IDB4REVBREJFRUYpLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLXAnLCAnLS1wYWRkaW5nJywgbWV0YXZhcj0nQ09VTlQnLCBoZWxwPSdUaGUgbWF4aW11bSBudW1iZXIgb2YgYnl0ZXMgb2YgcGFkZGluZyB0byBhZGQgYmV0d2VlbiBmaWxlcyAoZGVmYXVsdDogMCkuJykNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctbycsICctLW91dGZpbGUnLCBoZWxwPSdBbiBhbHRlcm5hdGl2ZSBvdXRwdXQgYXJjaGl2ZSBmaWxlIHdoZW4gYXBwZW5kaW5nIHRvIG9yIGRlbGV0aW5nIGZyb20gYXJjaGl2ZXMsIG9yIG91dHB1dCBkaXJlY3Rvcnkgd2hlbiBleHRyYWN0aW5nLicpDQoNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctaCcsICctLWhlbHAnLCBhY3Rpb249J2hlbHAnLCBoZWxwPSdQcmludCB0aGlzIGhlbHAgYW5kIGV4aXQuJykNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctdicsICctLXZlcmJvc2UnLCBhY3Rpb249J3N0b3JlX3RydWUnLCBoZWxwPSdCZSBhIGJpdCBtb3JlIHZlcmJvc2Ugd2hpbGUgcGVyZm9ybWluZyBvcGVyYXRpb25zLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLVYnLCAnLS12ZXJzaW9uJywgYWN0aW9uPSd2ZXJzaW9uJywgdmVyc2lvbj0ncnBhdG9vbCB2MC44JywgaGVscD0nU2hvdyB2ZXJzaW9uIGluZm9ybWF0aW9uLicpDQogICAgYXJndW1lbnRzID0gcGFyc2VyLnBhcnNlX2FyZ3MoKQ0KDQogICAgIyBEZXRlcm1pbmUgUlBBIHZlcnNpb24uDQogICAgaWYgYXJndW1lbnRzLnR3bzoNCiAgICAgICAgdmVyc2lvbiA9IDINCiAgICBlbHNlOg0KICAgICAgICB2ZXJzaW9uID0gMw0KDQogICAgIyBEZXRlcm1pbmUgUlBBdjMga2V5Lg0KICAgIGlmICdrZXknIGluIGFyZ3VtZW50cyBhbmQgYXJndW1lbnRzLmtleSBpcyBub3QgTm9uZToNCiAgICAgICAga2V5ID0gaW50KGFyZ3VtZW50cy5rZXksIDE2KQ0KICAgIGVsc2U6DQogICAgICAgIGtleSA9IDB4REVBREJFRUYNCg0KICAgICMgRGV0ZXJtaW5lIHBhZGRpbmcgYnl0ZXMuDQogICAgaWYgJ3BhZGRpbmcnIGluIGFyZ3VtZW50cyBhbmQgYXJndW1lbnRzLnBhZGRpbmcgaXMgbm90IE5vbmU6DQogICAgICAgIHBhZGRpbmcgPSBpbnQoYXJndW1lbnRzLnBhZGRpbmcpDQogICAgZWxzZToNCiAgICAgICAgcGFkZGluZyA9IDANCg0KICAgICMgRGV0ZXJtaW5lIG91dHB1dCBmaWxlL2RpcmVjdG9yeSBhbmQgaW5wdXQgYXJjaGl2ZQ0KICAgIGlmIGFyZ3VtZW50cy5jcmVhdGU6DQogICAgICAgIGFyY2hpdmUgPSBOb25lDQogICAgICAgIG91dHB1dCA9IF91bmljb2RlKGFyZ3VtZW50cy5hcmNoaXZlKQ0KICAgIGVsc2U6DQogICAgICAgIGFyY2hpdmUgPSBfdW5pY29kZShhcmd1bWVudHMuYXJjaGl2ZSkNCiAgICAgICAgaWYgJ291dGZpbGUnIGluIGFyZ3VtZW50cyBhbmQgYXJndW1lbnRzLm91dGZpbGUgaXMgbm90IE5vbmU6DQogICAgICAgICAgICBvdXRwdXQgPSBfdW5pY29kZShhcmd1bWVudHMub3V0ZmlsZSkNCiAgICAgICAgZWxzZToNCiAgICAgICAgICAgICMgRGVmYXVsdCBvdXRwdXQgZGlyZWN0b3J5IGZvciBleHRyYWN0aW9uIGlzIHRoZSBjdXJyZW50IGRpcmVjdG9yeS4NCiAgICAgICAgICAgIGlmIGFyZ3VtZW50cy5leHRyYWN0Og0KICAgICAgICAgICAgICAgIG91dHB1dCA9ICcuJw0KICAgICAgICAgICAgZWxzZToNCiAgICAgICAgICAgICAgICBvdXRwdXQgPSBfdW5pY29kZShhcmd1bWVudHMuYXJjaGl2ZSkNCg0KICAgICMgTm9ybWFsaXplIGZpbGVzLg0KICAgIGlmIGxlbihhcmd1bWVudHMuZmlsZXMpID4gMCBhbmQgaXNpbnN0YW5jZShhcmd1bWVudHMuZmlsZXNbMF0sIGxpc3QpOg0KICAgICAgICBhcmd1bWVudHMuZmlsZXMgPSBhcmd1bWVudHMuZmlsZXNbMF0NCg0KICAgIHRyeToNCiAgICAgICAgYXJjaGl2ZSA9IFJlblB5QXJjaGl2ZShhcmNoaXZlLCBwYWRsZW5ndGg9cGFkZGluZywga2V5PWtleSwgdmVyc2lvbj12ZXJzaW9uLCB2ZXJib3NlPWFyZ3VtZW50cy52ZXJib3NlKQ0KICAgIGV4Y2VwdCBJT0Vycm9yIGFzIGU6DQogICAgICAgIHByaW50KCdDb3VsZCBub3Qgb3BlbiBhcmNoaXZlIGZpbGUgezB9IGZvciByZWFkaW5nOiB7MX0nLmZvcm1hdChhcmNoaXZlLCBlKSwgZmlsZT1zeXMuc3RkZXJyKQ0KICAgICAgICBzeXMuZXhpdCgxKQ0KDQogICAgaWYgYXJndW1lbnRzLmNyZWF0ZSBvciBhcmd1bWVudHMuYXBwZW5kOg0KICAgICAgICAjIFdlIG5lZWQgdGhpcyBzZXBlcmF0ZSBmdW5jdGlvbiB0byByZWN1cnNpdmVseSBwcm9jZXNzIGRpcmVjdG9yaWVzLg0KICAgICAgICBkZWYgYWRkX2ZpbGUoZmlsZW5hbWUpOg0KICAgICAgICAgICAgIyBJZiB0aGUgYXJjaGl2ZSBwYXRoIGRpZmZlcnMgZnJvbSB0aGUgYWN0dWFsIGZpbGUgcGF0aCwgYXMgZ2l2ZW4gaW4gdGhlIGFyZ3VtZW50LA0KICAgICAgICAgICAgIyBleHRyYWN0IHRoZSBhcmNoaXZlIHBhdGggYW5kIGFjdHVhbCBmaWxlIHBhdGguDQogICAgICAgICAgICBpZiBmaWxlbmFtZS5maW5kKCc9JykgIT0gLTE6DQogICAgICAgICAgICAgICAgKG91dGZpbGUsIGZpbGVuYW1lKSA9IGZpbGVuYW1lLnNwbGl0KCc9JywgMikNCiAgICAgICAgICAgIGVsc2U6DQogICAgICAgICAgICAgICAgb3V0ZmlsZSA9IGZpbGVuYW1lDQoNCiAgICAgICAgICAgIGlmIG9zLnBhdGguaXNkaXIoZmlsZW5hbWUpOg0KICAgICAgICAgICAgICAgIGZvciBmaWxlIGluIG9zLmxpc3RkaXIoZmlsZW5hbWUpOg0KICAgICAgICAgICAgICAgICAgICAjIFdlIG5lZWQgdG8gZG8gdGhpcyBpbiBvcmRlciB0byBtYWludGFpbiBhIHBvc3NpYmxlIEFSQ0hJVkU9UkVBTCBtYXBwaW5nIGJldHdlZW4gZGlyZWN0b3JpZXMuDQogICAgICAgICAgICAgICAgICAgIGFkZF9maWxlKG91dGZpbGUgKyBvcy5zZXAgKyBmaWxlICsgJz0nICsgZmlsZW5hbWUgKyBvcy5zZXAgKyBmaWxlKQ0KICAgICAgICAgICAgZWxzZToNCiAgICAgICAgICAgICAgICB0cnk6DQogICAgICAgICAgICAgICAgICAgIHdpdGggb3BlbihmaWxlbmFtZSwgJ3JiJykgYXMgZmlsZToNCiAgICAgICAgICAgICAgICAgICAgICAgIGFyY2hpdmUuYWRkKG91dGZpbGUsIGZpbGUucmVhZCgpKQ0KICAgICAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToNCiAgICAgICAgICAgICAgICAgICAgcHJpbnQoJ0NvdWxkIG5vdCBhZGQgZmlsZSB7MH0gdG8gYXJjaGl2ZTogezF9Jy5mb3JtYXQoZmlsZW5hbWUsIGUpLCBmaWxlPXN5cy5zdGRlcnIpDQoNCiAgICAgICAgIyBJdGVyYXRlIG92ZXIgdGhlIGdpdmVuIGZpbGVzIHRvIGFkZCB0byBhcmNoaXZlLg0KICAgICAgICBmb3IgZmlsZW5hbWUgaW4gYXJndW1lbnRzLmZpbGVzOg0KICAgICAgICAgICAgYWRkX2ZpbGUoX3VuaWNvZGUoZmlsZW5hbWUpKQ0KDQogICAgICAgICMgU2V0IHZlcnNpb24gZm9yIHNhdmluZywgYW5kIHNhdmUuDQogICAgICAgIGFyY2hpdmUudmVyc2lvbiA9IHZlcnNpb24NCiAgICAgICAgdHJ5Og0KICAgICAgICAgICAgYXJjaGl2ZS5zYXZlKG91dHB1dCkNCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOg0KICAgICAgICAgICAgcHJpbnQoJ0NvdWxkIG5vdCBzYXZlIGFyY2hpdmUgZmlsZTogezB9Jy5mb3JtYXQoZSksIGZpbGU9c3lzLnN0ZGVycikNCiAgICBlbGlmIGFyZ3VtZW50cy5kZWxldGU6DQogICAgICAgICMgSXRlcmF0ZSBvdmVyIHRoZSBnaXZlbiBmaWxlcyB0byBkZWxldGUgZnJvbSB0aGUgYXJjaGl2ZS4NCiAgICAgICAgZm9yIGZpbGVuYW1lIGluIGFyZ3VtZW50cy5maWxlczoNCiAgICAgICAgICAgIHRyeToNCiAgICAgICAgICAgICAgICBhcmNoaXZlLnJlbW92ZShmaWxlbmFtZSkNCiAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToNCiAgICAgICAgICAgICAgICBwcmludCgnQ291bGQgbm90IGRlbGV0ZSBmaWxlIHswfSBmcm9tIGFyY2hpdmU6IHsxfScuZm9ybWF0KGZpbGVuYW1lLCBlKSwgZmlsZT1zeXMuc3RkZXJyKQ0KDQogICAgICAgICMgU2V0IHZlcnNpb24gZm9yIHNhdmluZywgYW5kIHNhdmUuDQogICAgICAgIGFyY2hpdmUudmVyc2lvbiA9IHZlcnNpb24NCiAgICAgICAgdHJ5Og0KICAgICAgICAgICAgYXJjaGl2ZS5zYXZlKG91dHB1dCkNCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOg0KICAgICAgICAgICAgcHJpbnQoJ0NvdWxkIG5vdCBzYXZlIGFyY2hpdmUgZmlsZTogezB9Jy5mb3JtYXQoZSksIGZpbGU9c3lzLnN0ZGVycikNCiAgICBlbGlmIGFyZ3VtZW50cy5leHRyYWN0Og0KICAgICAgICAjIEVpdGhlciBleHRyYWN0IHRoZSBnaXZlbiBmaWxlcywgb3IgYWxsIGZpbGVzIGlmIG5vIGZpbGVzIGFyZSBnaXZlbi4NCiAgICAgICAgaWYgbGVuKGFyZ3VtZW50cy5maWxlcykgPiAwOg0KICAgICAgICAgICAgZmlsZXMgPSBhcmd1bWVudHMuZmlsZXMNCiAgICAgICAgZWxzZToNCiAgICAgICAgICAgIGZpbGVzID0gYXJjaGl2ZS5saXN0KCkNCg0KICAgICAgICAjIENyZWF0ZSBvdXRwdXQgZGlyZWN0b3J5IGlmIG5vdCBwcmVzZW50Lg0KICAgICAgICBpZiBub3Qgb3MucGF0aC5leGlzdHMob3V0cHV0KToNCiAgICAgICAgICAgIG9zLm1ha2VkaXJzKG91dHB1dCkNCg0KICAgICAgICAjIEl0ZXJhdGUgb3ZlciBmaWxlcyB0byBleHRyYWN0Lg0KICAgICAgICBmb3IgZmlsZW5hbWUgaW4gZmlsZXM6DQogICAgICAgICAgICBpZiBmaWxlbmFtZS5maW5kKCc9JykgIT0gLTE6DQogICAgICAgICAgICAgICAgKG91dGZpbGUsIGZpbGVuYW1lKSA9IGZpbGVuYW1lLnNwbGl0KCc9JywgMikNCiAgICAgICAgICAgIGVsc2U6DQogICAgICAgICAgICAgICAgb3V0ZmlsZSA9IGZpbGVuYW1lDQoNCiAgICAgICAgICAgIHRyeToNCiAgICAgICAgICAgICAgICBjb250ZW50cyA9IGFyY2hpdmUucmVhZChmaWxlbmFtZSkNCg0KICAgICAgICAgICAgICAgICMgQ3JlYXRlIG91dHB1dCBkaXJlY3RvcnkgZm9yIGZpbGUgaWYgbm90IHByZXNlbnQuDQogICAgICAgICAgICAgICAgaWYgbm90IG9zLnBhdGguZXhpc3RzKG9zLnBhdGguZGlybmFtZShvcy5wYXRoLmpvaW4ob3V0cHV0LCBvdXRmaWxlKSkpOg0KICAgI
        echo CAgICAgICAgICAgICAgICBvcy5tYWtlZGlycyhvcy5wYXRoLmRpcm5hbWUob3MucGF0aC5qb2luKG91dHB1dCwgb3V0ZmlsZSkpKQ0KDQogICAgICAgICAgICAgICAgd2l0aCBvcGVuKG9zLnBhdGguam9pbihvdXRwdXQsIG91dGZpbGUpLCAnd2InKSBhcyBmaWxlOg0KICAgICAgICAgICAgICAgICAgICBmaWxlLndyaXRlKGNvbnRlbnRzKQ0KICAgICAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOg0KICAgICAgICAgICAgICAgIHByaW50KCdDb3VsZCBub3QgZXh0cmFjdCBmaWxlIHswfSBmcm9tIGFyY2hpdmU6IHsxfScuZm9ybWF0KGZpbGVuYW1lLCBlKSwgZmlsZT1zeXMuc3RkZXJyKQ0KICAgIGVsaWYgYXJndW1lbnRzLmxpc3Q6DQogICAgICAgICMgUHJpbnQgdGhlIHNvcnRlZCBmaWxlIGxpc3QuDQogICAgICAgIGxpc3QgPSBhcmNoaXZlLmxpc3QoKQ0KICAgICAgICBsaXN0LnNvcnQoKQ0KICAgICAgICBmb3IgZmlsZSBpbiBsaXN0Og0KICAgICAgICAgICAgcHJpbnQoZmlsZSkNCiAgICBlbHNlOg0KICAgICAgICBwcmludCgnTm8gb3BlcmF0aW9uIGdpdmVuIDooJykNCiAgICAgICAgcHJpbnQoJ1VzZSB7MH0gLS1oZWxwIGZvciB1c2FnZSBkZXRhaWxzLicuZm9ybWF0KHN5cy5hcmd2WzBdKSkNCg0K
    )

    >"!altrpatool!.b64" (
        echo IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMw0KaW1wb3J0IHN5cw0KaW1wb3J0IG9zDQppbXBvcnQgYXJncGFyc2UNCmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aA0KDQpzeXMucGF0aC5hcHBlbmQoJy4uJykNCg0KdHJ5Og0KICAgIGltcG9ydCBtYWluICAjIG5vcWE6IEY0MDENCmV4Y2VwdCBJbXBvcnRFcnJvcjoNCiAgICBwYXNzDQoNCmltcG9ydCByZW5weS5vYmplY3QgICMgbm9xYTogRjQwMQ0KaW1wb3J0IHJlbnB5LmNvbmZpZw0KaW1wb3J0IHJlbnB5LmxvYWRlcg0KDQp0cnk6DQogICAgaW1wb3J0IHJlbnB5LnV0aWwgICMgbm9xYTogRjQwMQ0KZXhjZXB0IEltcG9ydEVycm9yOg0KICAgIHBhc3MNCg0KDQpjbGFzcyBSZW5QeUFyY2hpdmU6DQogICAgZGVmIF9faW5pdF9fKHNlbGYsIGZpbGVfcGF0aDogUGF0aCwgaW5kZXg6IGludCA9IDApOg0KICAgICAgICBzZWxmLmZpbGUgPSBzdHIoZmlsZV9wYXRoKQ0KICAgICAgICBzZWxmLmhhbmRsZSA9IE5vbmUNCiAgICAgICAgc2VsZi5maWxlcyA9IHt9DQogICAgICAgIHNlbGYuaW5kZXhlcyA9IHt9DQogICAgICAgIHNlbGYubG9hZChzZWxmLmZpbGUsIGluZGV4KQ0KDQogICAgZGVmIGNvbnZlcnRfZmlsZW5hbWUoc2VsZiwgZmlsZW5hbWUpOg0KICAgICAgICBkcml2ZSwgZmlsZW5hbWUgPSBvcy5wYXRoLnNwbGl0ZHJpdmUoDQogICAgICAgICAgICBvcy5wYXRoLm5vcm1wYXRoKGZpbGVuYW1lKS5yZXBsYWNlKG9zLnNlcCwgJy8nKQ0KICAgICAgICApDQogICAgICAgIHJldHVybiBmaWxlbmFtZQ0KDQogICAgZGVmIGxpc3Qoc2VsZik6DQogICAgICAgIHJldHVybiBsaXN0KHNlbGYuaW5kZXhlcykNCg0KICAgIGRlZiByZWFkKHNlbGYsIGZpbGVuYW1lKToNCiAgICAgICAgZmlsZW5hbWUgPSBzZWxmLmNvbnZlcnRfZmlsZW5hbWUoZmlsZW5hbWUpDQogICAgICAgIGlmIGZpbGVuYW1lICE9ICcuJyBhbmQgaXNpbnN0YW5jZShzZWxmLmluZGV4ZXMuZ2V0KGZpbGVuYW1lKSwgbGlzdCk6DQogICAgICAgICAgICBpZiBoYXNhdHRyKHJlbnB5LmxvYWRlciwgImxvYWRfZnJvbV9hcmNoaXZlIik6DQogICAgICAgICAgICAgICAgc3ViZmlsZSA9IHJlbnB5LmxvYWRlci5sb2FkX2Zyb21fYXJjaGl2ZShmaWxlbmFtZSkNCiAgICAgICAgICAgIGVsc2U6DQogICAgICAgICAgICAgICAgc3ViZmlsZSA9IHJlbnB5LmxvYWRlci5sb2FkX2NvcmUoZmlsZW5hbWUpDQogICAgICAgICAgICByZXR1cm4gc3ViZmlsZS5yZWFkKCkNCiAgICAgICAgcmV0dXJuIE5vbmUNCg0KICAgIGRlZiBsb2FkKHNlbGYsIGZpbGVuYW1lLCBpbmRleCk6DQogICAgICAgIHNlbGYuZmlsZXMgPSB7fQ0KICAgICAgICBzZWxmLmluZGV4ZXMgPSB7fQ0KDQogICAgICAgIGJhc2UgPSBvcy5wYXRoLnNwbGl0ZXh0KG9zLnBhdGguYmFzZW5hbWUoZmlsZW5hbWUpKVswXQ0KDQogICAgICAgIGlmIGJhc2Ugbm90IGluIHJlbnB5LmNvbmZpZy5hcmNoaXZlczoNCiAgICAgICAgICAgIHJlbnB5LmNvbmZpZy5hcmNoaXZlcy5hcHBlbmQoYmFzZSkNCg0KICAgICAgICAjIElNUE9SVEFOVDogdXNlIHRoZSBleGFjdCBkaXJlY3Rvcnkgb2YgdGhlIGFyY2hpdmUNCiAgICAgICAgYXJjaGl2ZV9kaXIgPSBvcy5wYXRoLmRpcm5hbWUob3MucGF0aC5yZWFscGF0aChmaWxlbmFtZSkpDQogICAgICAgIHJlbnB5LmNvbmZpZy5zZWFyY2hwYXRoID0gW2FyY2hpdmVfZGlyXQ0KICAgICAgICByZW5weS5jb25maWcuYmFzZWRpciA9IG9zLnBhdGguZGlybmFtZShyZW5weS5jb25maWcuc2VhcmNocGF0aFswXSkNCiAgICAgICAgcmVucHkubG9hZGVyLmluZGV4X2FyY2hpdmVzKCkNCg0KICAgICAgICBhcmNoaXZlc19vYmogPSByZW5weS5sb2FkZXIuYXJjaGl2ZXMNCiAgICAgICAgdHJ5Og0KICAgICAgICAgICAgaWYgaXNpbnN0YW5jZShhcmNoaXZlc19vYmosIGRpY3QpOg0KICAgICAgICAgICAgICAgIGlmIGJhc2UgaW4gYXJjaGl2ZXNfb2JqOg0KICAgICAgICAgICAgICAgICAgICBpdGVtcyA9IGFyY2hpdmVzX29ialtiYXNlXVsxXS5pdGVtcygpDQogICAgICAgICAgICAgICAgZWxzZToNCiAgICAgICAgICAgICAgICAgICAgcmFpc2UgS2V5RXJyb3IoZiJBcmNoaXZlIHtiYXNlfSBub3QgZm91bmQgaW4gcmVucHkubG9hZGVyLmFyY2hpdmVzIikNCiAgICAgICAgICAgIGVsaWYgaXNpbnN0YW5jZShhcmNoaXZlc19vYmosIGxpc3QpOg0KICAgICAgICAgICAgICAgIGl0ZW1zID0gYXJjaGl2ZXNfb2JqW2luZGV4XVsxXS5pdGVtcygpDQogICAgICAgICAgICBlbHNlOg0KICAgICAgICAgICAgICAgIHJhaXNlIFR5cGVFcnJvcigiVW5leHBlY3RlZCB0eXBlIGZvciByZW5weS5sb2FkZXIuYXJjaGl2ZXMiKQ0KDQogICAgICAgICAgICBmb3IgZmlsZSwgaWR4IGluIGl0ZW1zOg0KICAgICAgICAgICAgICAgIHNlbGYuaW5kZXhlc1tmaWxlXSA9IGlkeA0KDQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToNCiAgICAgICAgICAgIHJhaXNlIFJ1bnRpbWVFcnJvcihmIlVuYWJsZSB0byBsb2FkIHRoZSBhcmNoaXZlIHtmaWxlbmFtZX06IHtlfSIpDQoNCg0KZGVmIGRpc2NvdmVyX2V4dGVuc2lvbnMoKToNCiAgICBleHRzID0gW10NCiAgICBpZiBoYXNhdHRyKHJlbnB5LmxvYWRlciwgImFyY2hpdmVfaGFuZGxlcnMiKToNCiAgICAgICAgZm9yIGhhbmRsZXIgaW4gcmVucHkubG9hZGVyLmFyY2hpdmVfaGFuZGxlcnM6DQogICAgICAgICAgICBpZiBoYXNhdHRyKGhhbmRsZXIsICJnZXRfc3VwcG9ydGVkX2V4dGVuc2lvbnMiKToNCiAgICAgICAgICAgICAgICBleHRzLmV4dGVuZChoYW5kbGVyLmdldF9zdXBwb3J0ZWRfZXh0ZW5zaW9ucygpKQ0KICAgICAgICAgICAgaWYgaGFzYXR0cihoYW5kbGVyLCAiZ2V0X3N1cHBvcnRlZF9leHQiKToNCiAgICAgICAgICAgICAgICBleHRzLmV4dGVuZChoYW5kbGVyLmdldF9zdXBwb3J0ZWRfZXh0KCkpDQogICAgZWxzZToNCiAgICAgICAgZXh0cy5hcHBlbmQoJy5ycGEnKQ0KDQogICAgaWYgJy5ycGMnIG5vdCBpbiBleHRzOg0KICAgICAgICBleHRzLmFwcGVuZCgnLnJwYycpDQoNCiAgICByZXR1cm4gc29ydGVkKHNldChlLmxvd2VyKCkgZm9yIGUgaW4gZXh0cykpDQoNCg0KZGVmIGRpc2NvdmVyX2FyY2hpdmVzKHNlYXJjaF9kaXI6IFBhdGgsIGV4dGVuc2lvbnMpOg0KICAgIGFyY2hpdmVzID0gW10NCiAgICBmb3Igcm9vdCwgZGlycywgZmlsZXMgaW4gb3Mud2FsayhzdHIoc2VhcmNoX2RpcikpOg0KICAgICAgICBmb3IgZmlsZSBpbiBmaWxlczoNCiAgICAgICAgICAgIHRyeToNCiAgICAgICAgICAgICAgICBiYXNlLCBleHQgPSBmaWxlLnJzcGxpdCgnLicsIDEpDQogICAgICAgICAgICAgICAgZXh0ID0gJy4nICsgZXh0Lmxvd2VyKCkNCiAgICAgICAgICAgICAgICBpZiBleHQgaW4gZXh0ZW5zaW9ucyBhbmQgJyUnIG5vdCBpbiBmaWxlOg0KICAgICAgICAgICAgICAgICAgICBhcmNoaXZlcy5hcHBlbmQoc3RyKFBhdGgocm9vdCkgLyBmaWxlKSkNCiAgICAgICAgICAgIGV4Y2VwdCBWYWx1ZUVycm9yOg0KICAgICAgICAgICAgICAgIGNvbnRpbnVlDQogICAgcmV0dXJuIGFyY2hpdmVzDQoNCg0KZGVmIGV4dHJhY3RfYXJjaGl2ZShhcmNoX3BhdGg6IFBhdGgsIG91dHB1dDogUGF0aCk6DQogICAgcHJpbnQoZicgIERlY29tcHJlc3Npb24gb2Yg4oCce2FyY2hfcGF0aH3igJ0uLi4nKQ0KICAgIGFyY2hpdmUgPSBSZW5QeUFyY2hpdmUoYXJjaF9wYXRoLCAwKQ0KICAgIGZpbGVzID0gYXJjaGl2ZS5saXN0KCkNCg0KICAgIG91dHB1dC5ta2RpcihwYXJlbnRzPVRydWUsIGV4aXN0X29rPVRydWUpDQoNCiAgICBmb3IgZmlsZW5hbWUgaW4gZmlsZXM6DQogICAgICAgIGNvbnRlbnRzID0gYXJjaGl2ZS5yZWFkKGZpbGVuYW1lKQ0KICAgICAgICBpZiBjb250ZW50cyBpcyBub3QgTm9uZToNCiAgICAgICAgICAgIG91dGZpbGUgPSBvdXRwdXQgLyBmaWxlbmFtZQ0KICAgICAgICAgICAgb3V0ZmlsZS5wYXJlbnQubWtkaXIocGFyZW50cz1UcnVlLCBleGlzdF9vaz1UcnVlKQ0KICAgICAgICAgICAgd2l0aCBvcGVuKG91dGZpbGUsICd3YicpIGFzIGY6DQogICAgICAgICAgICAgICAgZi53cml0ZShjb250ZW50cykNCg0KDQpkZWYgbWFpbigpOg0KICAgIHBhcnNlciA9IGFyZ3BhcnNlLkFyZ3VtZW50UGFyc2VyKA0KICAgICAgICBkZXNjcmlwdGlvbj0iVG9vbCBmb3Igd29ya2luZyB3aXRoIFJlbidQeSBhcmNoaXZlIGZpbGVzLiIsDQogICAgICAgIGFkZF9oZWxwPVRydWUNCiAgICApDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLXInLCBhY3Rpb249InN0b3JlX3RydWUiLCBkZXN0PSdyZW1vdmUnLA0KICAgICAgICAgICAgICAgICAgICAgICAgaGVscD0nUmVtb3ZlIGFyY2hpdmVzIGFmdGVyIGV4dHJhY3Rpb24uJykNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCcteCcsIGRlc3Q9J2FyY2hpdmUnLCB0eXBlPXN0ciwNCiAgICAgICAgICAgICAgICAgICAgICAgIGhlbHA9J1NwZWNpZmljIGFyY2hpdmUgZmlsZSB0byBleHRyYWN0IChmdWxsIHBhdGgpLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLW8nLCBkZXN0PSdvdXRwdXQnLCB0eXBlPXN0ciwgZGVmYXVsdD0nLicsDQogICAgICAgICAgICAgICAgICAgICAgICBoZWxwPSdPdXRwdXQgZGlyZWN0b3J5IGZvciBleHRyYWN0ZWQgZmlsZXMuJykNCiAgICBhcmdzID0gcGFyc2VyLnBhcnNlX2FyZ3MoKQ0KDQogICAgcmVtb3ZlID0gYXJncy5yZW1vdmUNCiAgICBvdXRwdXQgPSBQYXRoKGFyZ3Mub3V0cHV0KS5yZXNvbHZlKCkNCiAgICBhcmNoaXZlX2ZpbHRlciA9IGFyZ3MuYXJjaGl2ZQ0KDQogICAgZXh0ZW5zaW9ucyA9IGRpc2NvdmVyX2V4dGVuc2lvbnMoKQ0KDQogICAgIyAteCBtb2RlOiBleHRyYWN0IG9ubHkgdGhlIHNwZWNpZmllZCBhcmNoaXZlIChleGFjdCBwYXRoKQ0KICAgIGlmIGFyY2hpdmVfZmlsdGVyOg0KICAgICAgICB0YXJnZXQgPSBQYXRoKGFyY2hpdmVfZmlsdGVyKS5yZXNvbHZlKCkNCg0KICAgICAgICBpZiBub3QgdGFyZ2V0LmV4aXN0cygpOg0KICAgICAgICAgICAgcHJpbnQoZiIgIEFyY2hpdmUgbm90IGZvdW5kOiB7dGFyZ2V0fSIpDQogICAgICAgICAgICBzeXMuZXhpdCgxKQ0KICAgICAgICBpZiBub3QgdGFyZ2V0LmlzX2ZpbGUoKToNCiAgICAgICAgICAgIHByaW50KGYiICBOb3QgYSBmaWxlOiB7dGFyZ2V0fSIpDQogICAgICAgICAgICBzeXMuZXhpdCgxKQ0KDQogICAgICAgIF8sIGV4dCA9IG9zLnBhdGguc3BsaXRleHQodGFyZ2V0Lm5hbWUpDQogICAgICAgIGlmIGV4dC5sb3dlcigpIG5vdCBpbiBleHRlbnNpb25zOg0KICAgICAgICAgICAgcHJpbnQoZiIgIFVuc3VwcG9ydGVkIGV4dGVuc2lvbiB7ZXh0fSBmb3Ige3RhcmdldC5uYW1lfS4iKQ0KICAgICAgICAgICAgc3lzLmV4aXQoMSkNCg0KICAgICAgICBleHRyYWN0X2FyY2hpdmUodGFyZ2V0LCBvdXRwdXQpDQogICAgICAgIHByaW50KGYiICBBcmNoaXZlIHt0YXJnZXQubmFtZX0gaGFzIGJlZW4gZXh0cmFjdGVkIHRvIHtvdXRwdXR9LiIpDQoNCiAgICAgICAgaWYgcmVtb3ZlOg0KICAgICAgICAgICAgcHJpbnQoZicgIEFyY2hpdmUge3RhcmdldH0gcmVtb3ZlZC4nKQ0KICAgICAgICAgICAgb3MucmVtb3ZlKHN0cih0YXJnZXQpKQ0KICAgICAgICByZXR1cm4NCg0KICAgICMgRGVmYXVsdCBtb2RlOiBleHRyYWN0IGFsbCBhcmNoaXZlcyBmcm9tIHRoZSBjdXJyZW50IGRpcmVjdG9yeQ0KICAgIGN1cnJlbnRfZGlyID0gUGF0aCgnLicpLnJlc29sdmUoKQ0KICAgIGFyY2hpdmVzID0gZGlzY292ZXJfYXJjaGl2ZXMoY3VycmVudF9kaXIsIGV4dGVuc2lvbnMpDQoNCiAgICBpZiBub3QgYXJjaGl2ZXM6DQogICAgICAgIHByaW50KCIgIE5vIGFyY2hpdmUgZm91bmQgaW4gY3VycmVudCBkaXJlY3RvcnkuIikNCiAgICAgICAgcmV0dXJuDQoNCiAgICBmb3IgYXJjaCBpbiBhcmNoaXZlczoNCiAgICAgICAgZXh0cmFjdF9hcmNoaXZlKFBhdGgoYXJjaCksIG91dHB1dCkNCg0KICAgIHByaW50KGYiICBBbGwgYXJjaGl2ZXMgaGF2ZSBiZWVuIGV4dHJhY3RlZCB0byB7b3V0cHV0fS4iKQ0KICAgIGlmIHJlbW92ZToNCiAgICAgICAgZm9yIGFyY2ggaW4gYXJjaGl2ZXM6DQogICAgICAgICAgICBhcCA9IFBhdGgoYXJjaCkNCiAgICAgICAgICAgIHByaW50KGYnICBBcmNoaXZlIHthcH0gcmVtb3ZlZC4nKQ0KICAgICAgICAgICAgb3MucmVtb3ZlKHN0cihhcCk
        echo pDQoNCg0KaWYgX19uYW1lX18gPT0gIl9fbWFpbl9fIjoNCiAgICBtYWluKCkNCg==
    )
)
if not exist "!rpatool!.b64" (
    call :elog " %RED%!FAIL.%LNG%!%RES%!extm7.%LNG%! %YEL%!rpatool!.b64%RES%"
    goto :eof
)
if not exist "%altrpatool%.b64" (
    call :elog " %RED%!FAIL.%LNG%!%RES%!extm7.%LNG%! %YEL%!altrpatool!.b64%RES%"
    goto :eof
)

set "rpatoolps=%rpatool:[=`[%"
set "rpatoolps=%rpatoolps:]=`]%"
set "rpatoolps=%rpatoolps:^=^^%"
set "rpatoolps=%rpatoolps:&=^&%"
echo powershell.exe -nologo -noprofile -noninteractive -command "& { [IO.File]::WriteAllBytes('!rpatoolps!.tmp', [Convert]::FromBase64String([IO.File]::ReadAllText('!rpatoolps!.b64'))) }" >> "%UNRENLOG%"
powershell.exe -nologo -noprofile -noninteractive -command "& { [IO.File]::WriteAllBytes('!rpatoolps!.tmp', [Convert]::FromBase64String([IO.File]::ReadAllText('!rpatoolps!.b64'))) }"
del /f /q "%rpatoolps%.b64" %DEBUGREDIR%
if not exist "!rpatoolps!.tmp" (
    call :elog " %RED%!FAIL.%LNG%!%RES%!extm7.%LNG%! %YEL%!rpatoolps!.tmp%RES%"
    goto :eof
) else (
    move /y "!rpatoolps!.tmp" "!rpatoolps!" %DEBUGREDIR%
)
echo powershell.exe -nologo -noprofile -noninteractive -command "& { [IO.File]::WriteAllBytes('!altrpatool!.tmp', [Convert]::FromBase64String([IO.File]::ReadAllText('!altrpatool!.b64'))) }" >> "%UNRENLOG%"
powershell.exe -nologo -noprofile -noninteractive -command "& { [IO.File]::WriteAllBytes('!altrpatool!.tmp', [Convert]::FromBase64String([IO.File]::ReadAllText('!altrpatool!.b64'))) }"
del /f /q "%altrpatool%.b64" %DEBUGREDIR%
if not exist "!altrpatool!.tmp" (
    call :elog " %RED%!FAIL.%LNG%!%RES%!extm7.%LNG%! %YEL%!altrpatool!.tmp%RES%"
    goto :eof
) else (
    move /y "!altrpatool!.tmp" "!altrpatool!" %DEBUGREDIR%
)
call :elog " %GRE%!PASS.%LNG%!%RES%"

call :elog .
:: Unpack RPA
cd /d "%WORKDIR%"
for /R "game" %%f in (*.%rpaExt%) do (
    set "rpafile=%%~dpnf.%rpaExt%"
    set "relativePath=%%f"
    set "relativePath=!relativePath:%WORKDIR%\game\=!"
    set "usealt=0"

    set "extm18.en=RPA file '!rpafile!' ignored."
    set "extm18.zh=已忽略 RPA 文件 '!rpafile!'。"

    set "extm19.en=Error processing RPA !rpafile!."
    set "extm19.zh=处理 RPA 文件 !rpafile! 时出错。"

    set "extm20.en=RPA file unpacked: !relativePath!"
    set "extm20.zh=RPA 文件已解包：!relativePath!"

    set "extm21.en=Deleting RPA file '!rpafile!'"
    set "extm21.zh=正在删除 RPA 文件 '!rpafile!'"

    set "extm22.en=Moving RPA file '!rpafile!' to '!WORKDIR!\rpa'"
    set "extm22.zh=正在将 RPA 文件 '!rpafile!' 移动到 '!WORKDIR!\rpa'"

    set "extm23.en=Error moving RPA file '!rpafile!' to '!WORKDIR!\rpa'."
    set "extm23.zh=将 RPA 文件 '!rpafile!' 移动到 '!WORKDIR!\rpa' 时出错。"

    set "extm24.en=RPA file '!rpafile!' moved to '!WORKDIR!\rpa'."
    set "extm24.zh=RPA 文件 '!rpafile!' 已移动到 '!WORKDIR!\rpa'。"

    set "extm26.en=Modified %YEL%'!rpafile!'%RES% RPA archive detected, using altrpatool.py to extract."
    set "extm26.zh=检测到被修改的 %YEL%'!rpafile!'%RES% RPA 归档，使用 altrpatool.py 解包。"

    if !OPTION! EQU 7 (
        set "usealt=1"
        call :elog .
        call :elog "    !extm26.%LNG%!"
    )
    if exist "!rpafile!" if not "!relativePath!" == "saves\persistent" (
        echo "!PYTHONHOME!python.exe" !PYNOASSERT! "!detect_archive_py!" "!rpafile!" >>"%UNRENLOG%"
        "!PYTHONHOME!python.exe" !PYNOASSERT! "!detect_archive_py!" "!rpafile!" >>"%UNRENLOG%" 2>&1
        if !errorlevel! EQU 1 (
            set "usealt=1"
            call :elog .
            call :elog "    !extm26.%LNG%!"
        )
        if "%extract_all_rpa%" == "n" (
            call :elog .
            set "qmark=?"
            if "%LNG%"=="fr" set "qmark= ?"
            echo    !extm16.%LNG%! !relativePath!!qmark! >> "%UNRENLOG%"
            <nul set /p=.    !extm16.%LNG%! !relativePath!!qmark! !ENTERYN.%LNG%!
            choice /C OSJДYN /N /D N /T 5
            if errorlevel 6 (
                call :elog "    %YEL%- !extm18.%LNG%!%RES%"
            ) else (
                if !usealt! EQU 0 (
                    echo "!PYTHONHOME!python.exe" !PYNOASSERT! "!rpatool!" -o game -x "!rpafile!" >>"%UNRENLOG%"
                    "!PYTHONHOME!python.exe" !PYNOASSERT! "!rpatool!" -o game -x "!rpafile!" >>"%UNRENLOG%" 2>&1
                    set "elevel=!errorlevel!"
                ) else if !usealt! EQU 1 (
                    echo "!PYTHONHOME!python.exe" !PYNOASSERT! "!altrpatool!" -o .\game -x "!rpafile!" >>"%UNRENLOG%"
                    "!PYTHONHOME!python.exe" !PYNOASSERT! "!altrpatool!" -o .\game -x "!rpafile!" >>"%UNRENLOG%" 2>&1
                    set "elevel=!errorlevel!"
                )
                if !elevel! NEQ 0 (
                    call :elog "    %RED%- !extm19.%LNG%! %YEL%!LOGCHK!%RES%"
                ) else (
                    call :elog "    %GRE%+ !extm20.%LNG%!%RES%"
                    if "!delrpa!" == "y" (
                        call :elog "    + !extm21.%LNG%!%RES%"
                        del /f /q "!rpafile!" %DEBUGREDIR%
                    ) else (
                        call :elog "    + !extm22.%LNG%!" REM Moving RPA file '!rpafile!' to '!WORKDIR!\rpa'
                        if not exist "!WORKDIR!\rpa" (
                            mkdir "!WORKDIR!\rpa"
                        )
                        move "!rpafile!" "!WORKDIR!\rpa" %DEBUGREDIR%
                        if !errorlevel! NEQ 0 (
                            call :elog "    %RED%- !extm23.%LNG%! %YEL%!LOGCHK!%RES%"
                        ) else (
                            call :elog "    %GRE%+ !extm24.%LNG%!%RES%"
                        )
                    )
                )
            )
        ) else (
            call :elog .
            call :elog "    + !extm16.%LNG%! !relativePath!"
            set "elevel=0"
            if !usealt! EQU 0 (
                echo "!PYTHONHOME!python.exe" !PYNOASSERT! "!rpatool!" -o game -x "!rpafile!" >>"%UNRENLOG%"
                "!PYTHONHOME!python.exe" !PYNOASSERT! "!rpatool!" -o game -x "!rpafile!" >>"%UNRENLOG%" 2>&1
                set "elevel=!errorlevel!"
            ) else if !usealt! EQU 1 (
                echo "!PYTHONHOME!python.exe" !PYNOASSERT! "!altrpatool!" -o .\game -x "!rpafile!" >>"%UNRENLOG%"
                "!PYTHONHOME!python.exe" !PYNOASSERT! "!altrpatool!" -o .\game -x "!rpafile!" >>"%UNRENLOG%" 2>&1
                set "elevel=!errorlevel!"
            )
            if !elevel! NEQ 0 (
                call :elog "    %RED%- !extm19.%LNG%!%RES%"
            ) else (
                call :elog "    %GRE%+ !extm20.%LNG%!%RES%"
                if "!delrpa!" == "y" (
                    call :elog "    + !extm21.%LNG%!%RES%"
                    del /f /q "!rpafile!" %DEBUGREDIR%
                ) else (
                    call :elog "    + !extm22.%LNG%!" REM Moving RPA file '!rpafile!' to '!WORKDIR!\rpa'
                    if not exist "!WORKDIR!\rpa" (
                        mkdir "!WORKDIR!\rpa"
                    )
                    move "!rpafile!" "!WORKDIR!\rpa" %DEBUGREDIR%
                    if !errorlevel! NEQ 0 (
                        call :elog "    %RED%- !extm23.%LNG%!%RES%"
                    ) else (
                        call :elog "    %GRE%+ !extm24.%LNG%!%RES%"
                    )
                )
            )
        )
    )
)
call :elog .

:: Clean up
:rpa_cleanup
call :elog "!CLEANUP.%LNG%!"
if exist "!rpatool!.tmp" del /f /q "!rpatool!.tmp" %DEBUGREDIR%
if exist "!rpatool!" del /f /q "!rpatool!" %DEBUGREDIR%
if exist "!altrpatool!.tmp" del /f /q "!altrpatool!.tmp" %DEBUGREDIR%
if exist "!altrpatool!" del /f /q "!altrpatool!" %DEBUGREDIR%
if exist "!WORKDIR!\__pycache__" rmdir /Q /S "!WORKDIR!\__pycache__" %DEBUGREDIR%
if exist "!detect_archive_py!.tmp" del /f /q "!detect_archive_py!.tmp" %DEBUGREDIR%
if exist "!detect_archive_py!" del /f /q "!detect_archive_py!" %DEBUGREDIR%
if exist "!detect_rpa_ext_py!.tmp" del /f /q "!detect_rpa_ext_py!.tmp" %DEBUGREDIR%
if exist "!detect_rpa_ext_py!" del /f /q "!detect_rpa_ext_py!" %DEBUGREDIR%

call :elog "!DONE.%LNG%!"
timeout /t 5 /nobreak >nul
call :elog .

if "!OPTION!" == "5" call :decompile
if "!OPTION!" == "6" call :decompile

goto :eof


:: Use unrpa instead of rpatool which offer the ability to extract RPA archives with a different header.
:extract_wkey
call :elog .

:rpa_cleanup
:: Clean up
call :elog "!CLEANUP.%LNG%!"
if exist "!rpatool!.tmp" del /f /q "!rpatool!.tmp" %DEBUGREDIR%
if exist "!rpatool!" del /f /q "!rpatool!" %DEBUGREDIR%
if exist "!WORKDIR!\__pycache__" rmdir /Q /S "!WORKDIR!\__pycache__" %DEBUGREDIR%
if exist "!unrpatool!.tmp" del /f /q "!unrpatool!.tmp" %DEBUGREDIR%
cd /d "%WORKDIR%"
call :elog .
if "!OPTION!" == "5" call :decompile
if "!OPTION!" == "6" call :decompile

goto :eof


:decompile
set "decm1.en=Failed to create decomp.cab. !UNACONT.%LNG%!"
set "decm1.zh=无法创建 decomp.cab。!UNACONT.%LNG%!"

set "decm2.en=Decompilation tool created successfully."
set "decm2.zh=反编译工具创建成功。"

set "decm3.en=Overwrite RPY files after decompilation?"
set "decm3.zh=反编译后是否覆盖已有 RPY 文件？"

set "decm4.en=Existing RPY files won't be overwritten."
set "decm4.zh=不会覆盖已有 RPY 文件。"

set "decm5.en=Existing RPY files will be overwritten after decompilation."
set "decm5.zh=反编译后将覆盖已有 RPY 文件。"

set "decm6.en=Extracting decomp.cab..."
set "decm6.zh=正在解压 decomp.cab..."

set "decm7.en=Unable to find:"
set "decm7.zh=找不到："

set "decm8.en=Searching for RPYC files in the game directory..."
set "decm8.zh=正在在 game 目录中搜索 RPYC 文件..."

set "decm9.en=Decompiling file:"
set "decm9.zh=正在反编译文件："

set "decm10.en=Copy from"
set "decm10.zh=从"

set "decm10a.en=to"
set "decm10a.zh=到"

set "decm11.en=Overwriting existing RPY file:"
set "decm11.zh=覆盖已有 RPY 文件："

set "decm12.en=Skipping:"
set "decm12.zh=跳过："

set "decm12a.en=decompiled file already exists."
set "decm12a.zh=已存在反编译后的文件。"

set "decm13.en=Error processing:"
set "decm13.zh=处理出错："

:: Write to temporary file first, then convert. Needed due to binary file and avoid antivirus false positive.
set "decompcab=%WORKDIR%\decomp.cab"
set "decompilerdir=%WORKDIR%\decompiler"
set "unrpycpy=%WORKDIR%\unrpyc.py"
set "deobfuscate=%WORKDIR%\deobfuscate.py"

cd /d "%WORKDIR%"
del /f /q "%decompcab%.tmp" %DEBUGREDIR%
del /f /q "%decompcab%" %DEBUGREDIR%
rmdir /Q /S "%decompilerdir%" %DEBUGREDIR%
del /f /q "%unrpyc%.tmp" %DEBUGREDIR%
del /f /q "%unrpyc%" %DEBUGREDIR%
del /f /q "%deobfuscate%" %DEBUGREDIR%

if !RENPYVERSION! LSS 8 (
    REM unrpyc by CensoredUsername
    REM	https://github.com/CensoredUsername/unrpyc
    REM __title__ = "Unrpyc Legacy for Ren'Py v7 and lower"
    REM __version__ = 'v1.3.2'
    >"!decompcab!.tmp" (
        echo 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
        echo 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
        echo 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
        echo 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
        echo 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
        echo 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
        echo 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
        echo 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
        echo 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
        echo T1qEDRtiR2vHUiV2Zm+TVmMnO574fWNhqiD5Nj9LgL2s+KKJhXgiL67qigLtcntL3g2WRrRp5tYTGe0xqRQ2kTLguZ+9gTxUmLDkSoExTtP2wAaaGkwgavtu4bEc6eNaWdDrRl5ZyI97StdN7Sgeg8R+xZNleTZ1jwCfeUdBrlvAKNHeN/wI=
    )

    set "OFFSET=--init-offset"
) else (
    REM unrpyc by CensoredUsername
    REM	https://github.com/CensoredUsername/unrpyc
    REM __title__ = "Unrpyc Master for Ren'Py v8"
    REM __version__ = 'v2.0.2'
    REM And use the correct unrpyc version.
    >"!decompcab!.tmp" (
        echo TVNDRgAAAADopgAAAAAAACwAAAAAAAAAAwEBAAsAAACqNwAAcQEAAAYAAQChKgAAAAAAAAAA/FrqBCAAZGVvYmZ1c2NhdGUucHkAJ04AAKEqAAAAANtYMRogAHVucnB5Yy5weQDIhgAAyHgAAAAACVumFiAAX19pbml0X18ucHkA/i4AAJD/AAAAANtYMRogAGFzdGR1bXAucHkAtyEAAI4uAQAAANtYMRogAGF0bGRlY29tcGlsZXIucHkA/XQAAEVQAQAAANtYMRogAG1hZ2ljLnB5AP4zAABCxQEAAAAJW3h3IAByZW5weWNvbXBhdC5weQD8ZQAAQPkBAAAACVvJFiAAc2wyZGVjb21waWxlci5weQBkFQAAPF8CAAAA21gxGiAAdGVzdGNhc2VkZWNvbXBpbGVyLnB5AJwVAACgdAIAAADbWDEaIAB0cmFuc2xhdGUucHkApFYAADyKAgAAAAlb1RYgAHV0aWwucHkAvu81k64lAIBDS+w8a3PbtrLf9Stw5Dkj6VZhLCV1U0/dXsWWG506to8sN81JMxqKhCTWFKkSpG01k/9+9wGQICkrTjrnfor7MB/AYnexbyy9J47j9SYJFstUtL2O6O/3e0/gf8/FsYxUnEj/WskkcleysdfYE5cyWQVKBXEkAiWWMpGzjVgkbpRKvyvmiZQingtv6SYL2RVpLNxoI9YyUTAhnqVuEAXRQrjCg0UBHIxNlwBIxfP0zk0kDPeFq1TsBS5AFH7sZSsZpW6KK86DUCrRTpdSNK/0jGaHlvGlGwK8IBL41rwUd0G6jLNUJFKlSeAhlC4M8sLMRzzM6zBYBXoNnE7cUAAOAGcK6EBsu2IV+8Ecf0sibp3NwkAtu8IPEPgsS+GhwocecA6ugZancSKUDBE1gBEA9kRxgSGNwnXWyNhUs0rhk7tlvCpTEyBO8yyJYFlJs/wYWEer/iG9FJ/ghHkchvEdEujFkR8gXeqQtm8Cb91ZfCuJJN71KE4BY8YD92JdbLF+pZZuGIqZ1JyDpYMIgOFDQ1WCOKgU5CBwQ7GOE1q0Sq3DSLwaiquL08mbwXgoRlficnzx6+hkeCKagyu4b3bFm9Hk1cX1RMCI8eB88lZcnIrB+Vvxy+j8pCuGv12Oh1dX4mIMwEavL89GQ3g6Oj8+uz4Znf8sXsLM84uJOBu9Hk0A7OSCltTARsMrBPd6OD5+BbeDl6Oz0eRtF0CdjibnCPf0YiwG4nIwnoyOr88GY3F5Pb68uBoCCicA+Hx0fjqGdYavh+cTB9aFZ2L4K9yIq1eDszNcDKANroGGMWIpji8u345HP7+aiFcXZydDePhyCNgNXp4NeTEg7fhsMHrdFSeD14OfhzTrAuAghTiQcRRvXg3xIa45gH+PJ6OLcyTm+OJ8MobbLtA6nuST34yuhl0xGI+ukC2n44vXSCYyFuZcEBiYeT5kOMj08t7AELy/vhrmIMXJcHAG0K5wMhNqhjsN+EERAxlCTUXhQ4VXuRaD4ICmgGIvUGZAs0DXFzgiFTdRfIcWYp4pTyui9JZR8GcGI0E0AbCKV1KsXG8ZRDLZkKyDVqN8rQwYBxEYJDAEZqcZqYxYJzJNN0IFq3UoHVSBRLYAKKi9dBHAHShRKtcKrUcWrV3vBlWHDMF644E2JSsXQO+J8eXb4z6CdCPh4iq3Ur+F0fA/D55rosUqC9MAFkSKpbsCs5XIuUwS1lsXTF4Yp6qjdXIeJIAJYoHg5T1wCYyVxgJHgmkFaxCkXTALgbfEUX4cSQHWF39pPdMT40Q5DFhJ0tIFYuqKWRjPCFMgX4Lpk6C1aQDv/wqD2RMvXgGrFO4KqPMfGfNWJO4dYQAA27wFEoymr8Cmhrg4DUIAwgCg3YuBpgXuANrXnIpQRot0qakGU5zqzdjHJVfgbfROAD2+9JLNOmeC76Yum3dgNMJyWNJkBKhka5iRSjRKM4kzQncDhhTBzFwlD553cRvgxRMJ4rUGq7uU909k5MXoBrpl+slHyNRDFr6RYgnSB9tIphG4zXxJNhovRVvgLSULTUD7sAHaURZB4sAQahTMHfhKP16ZO0Ar81Jzh3g0aKc9MOHSYyOqXx7HGahQ0uABwB7AF9QscRIZgZzCHXBGj10H3k0op8qdy2kYu75CxRjm0iHQm7BCgD+JvNxYt+fx7I8u8TeKO+LJj0AdaBnv1wZwD4DgX90wk8MkgS3L6XWDsDH8jYwQGr0j8e59w5fzQiLb885hQ8BPMcpx12vYPnhDL0BNwbWJOaJ6wpu/E1XCrGvYgsiWcWVw56geNppgsfWdHgHXAVASrVlQNy0MQ0IVoyqrwJdaZZcuajsAkL7TOBkej99elkn1Dc45qcWoB0lFe+X7YgHx1RO1ll4wDzzhgYzBFhszAOr0NFcHuAnjBQxCzaFdBb+NIVd1ztPqDFjsf/PtsDdnits9RVvXnvPea/ybzSb9vkLVzaeiyQNjQiZeGxMddsHrDLy/ZTVLYOaOkvKmvc88IIU+godgHv02P4N9wsfvDnv778U/jsSsNR6eX74Fw3vcbzFOxL6KGLabI1BlsK0QAr0CaDJpdho0eh0rCn9god4+PSGzC7cfPvIIMKdARz7uG9Hrix+O0FC1EZVOsSrODHy0JG4CdphNGUBiFXbYc7SbP4xGIwhhiA4D9rAE/30nhwkEt7fC7YijI9He7wr810ICf2bAsZuGDYOmAmyN049b8d/OuZdJfCMjts7gopONYV3OrHeM4HsgtV3GMR9XkAd87tNjGSq5a8fsdZe0Z5qRGcb0DSMO9B7CUBQxwmYXzOuIwwiaFPgGTG3Dcqre29pIO0ZjD8v8fL9bcUK5cL3N41UHNYXnbFMSQzNIf28XrWc2BHDD4ItVtkbjr0SPQBjyd6sdPYRtL9bSI9AXOexl0CuyNPHW3ntyzc7KkYjN4/H0A59200RJLkcOGJgYdK3d2M13lhrw59Hn8B68tNLRGnj2Bdr2JYaVaFIxBQK7v4L8iB9rwXQT8DFg9R9vzKrGZ3+7rXl2IH7YpqpuV8wg6wQrApEIpNVdAUEKZJrBdnPDP7uMzrODstFx0bz0iGAfL/t0ucDLfbqcwSQPb+U227NV7xuP0ntw16EftSCgDTDV1yzOVbWwzl+N81fj/PeNM5qXLzcR88y7AVOAZSLbHuS8MAWXdRxEKUirxIwTAiJmsqsCGAxDKGdAPs1iSroIXpCSomHaClDFneRhYRzfEB63bgjGkhOrZRbdQMIXYIQTbj7bEBHHpkYOFIesPBljeNy+BG1hOxdM8UT0LOk0cVlAUdn+/XcvypKL5jyIMlmS+7aZ8j+i/+0BbBjfo5a974h/imc9AvYpSBXkTSQdaNo0b4gkQ1Eu8SiX5enFaiWfl0N6wPEVxsKyDzv8YImU0gI5AXRX0aUfyTTwuM4uZfqPFuvcoZI1lVGcLZZ6nYo/5YekWLi57zEbyDMWO38hlSGise4JuZVGpMQvDfTLYoQiMXsQB0jPt6AAbEJa3TBsk9DOmu7Mg2mDl8cnw9P9Xv/Z828PvnvxfbOQa5ru3MiNanc623F4iDhcn4jzZbsJCDVLlA3pF0rEZxHGtYDPoG2xDP64CVdRvP4zUWl2e3e/+Yvp/fnV6F+/nL0+v7j89/hqcv3rm9/e/qfgwTdPj36PmiWBtPX9b/CFSXBmB881c2q7/oW84RLNlEs0n2LRj2iH+hysBBBF7d+/2P975EXyTlvP0s5nUYAXunLU7DhUNpLtVuiCevdan0O5ocKsxEs9PFbf6/EPMi6IPJnG0aeUFtgBxH3X/7b3bb/3oteHi9738M+zXq8P/xz0Dko5wDQMwB9BtAK/rD1mg4Q1LHQ8fhugFi/UMpvPQwkY+YEnlZld9i4EuNOpg+PJ7QoQa5y8hYDfhv5uH90LAn5wEslE12Dm4wB5jzIio2wlsRpdm1sJy8qrvitDwsgrqKkIFqLa73Ji0QsWrrYM7/1nqQ5uu6uUBJ8WqGmEWVWoSzeV0GYQueHmL8m11zxgiTH2V6BmoaluY4Qd8/ERoqjrKBGYc44zTmLgNOkdVXcwz3Q3eKxHgRKeJukC7xQdHkSpasrlaKzTSn3kpqvJ8AjinDusXFGaMwsphFJ4ZIYBEYLiUjaeFdGYEbjGzAM+zbOwq3mhaL0ssirWZm1TCTcF9ThxF1x7LqKmLWGTDuzywKm333/eqYwz2stjP1Wj2jMVdk71u3REFq8kliNXjHMlrGxYc2GLsxUVsvVsQIKrmIHiCJWOIewgEXNoS6PuptsKbFso2hoLlXhbD4kM+EfHQrUIpuqYRPPEjmQKlmrmQEKcYZ6RygTPc/iIyFV5IQWlmIuzdoqkVcemZluWCoxFE8IrdcCZPD8oo78nevus1EZSvhHPwfB8rx9q6RMpSnTFeBAGdux2SoXTGMR+GSepje6Xpv1aInv7h88xz7fkyEfltTIXXYaB/7wluI+5m4V4OB611huxkBGZQ5/P2X+y2YMb07aKBjO8fH5QLSC0Nb7lBLlSUKiZ1xqHuIarj3xAzGds57oU7fIBN5GBh36cvQHKMvTVTzY3tZzPOju0wtumFhWxyIUdtd37XOSDiE9mArR1pPEkq5y8Nv9fdbCOK6W/vcdU5Sw5sPFy8PgNqWo3neanN/bB9fQBDx9bfVKDyQvi/k1dCC7mXda/exP0+IG7iCBfowChOUhTudLniNgnYs6YJW3EYVNnwoadOEnJ1KTO6BKL+gDgWhxf7UgltZBZh19dyKerG2Wdo8GysmpyAjp9EvMnHBeLGcACbW7+3qQzMR0Kx3cgHTM5x7PT9eaZ0+t3sYYJbjYDi+stk3ZH4BlvBTg5kjhLBHiZYJWtYC62l5SIMGzMD69a+vR+Iz7kpDnTKTYHTacftf09FB9w1d5+x/kjDqK2dNxkoTofWxb9Jev7RWtxTKAsoKVNdFzf1zGrnTrk761qd3Xl5iAM7TYFfeQnriMTrmh8aJebnR1ZOiRgzIN8kU6Bj21aVKdS769jdVVgtE5iP/OwOyqYzyFSiqi/CSy5csSET6bx0D+mODKvA2iZzHMLlOzcIFIFqMabrXKNtdBVqrpo93HENE/fONh72DDtlPc6xTn3tAQ9Tn5gc3C236nVYuCNE8aLB7Zli+UiOhuNL5QS29JYkvJYKSEbt5O9W4ydtmW6+6F87KAf/gChjB2lYhEJjAU2CWAEvpHpT4/af4BeazJ4eOu3pDVUmoY4d8euWoWYQuoMvYWP0JTRGUSx4ZAEA466O8DCrJQY5vk0akBxXF9GwyoM5Ef8Bp5Jt0sTrBQf9gU17rAW79aqg9tZUAlbTCWgOmSL/VzLBMMk7LESdH6FqdGHnILCllZsaP2Up46VdchR1wwTyGO5XyzhP1IGWpYrK5+nCXv/eJqp5OksiJ7K6Bb8VLqMo2fY+VBtXO31uXH1bZYE4hdHXHlLiGMjTB6qvaxd8S8Io1fezE2ir32tX/tav/a1fu1r3dXXOp2mQQq+bgo2uHkdYeWsCQ+xkAfyQI9bt31n3+m34HGWhDxymaZrdfj06QL0MZs5kMM8rVqip5mGlrcLgolZu4mS5n6BhZ2t7YJqo8wlRqRyBjat3koIyecS0zn94hJuG43ctdMQblZNYgypqbakh8YxJN3eOpuSk2toZz6it8Miw9wTr2PvBozRn1mA3XK6EQUPRKM6bAXZnHsL8VJeLMFQJ1+lXa/X93LeFF2PxZM8zKo2RhoyIEn0s9W6i0yKVLhl5LYWynYtvOmWIh4EWTziATVHuu1Hz/Al9ihP2Z/1MeLzQvAQ4NUoVD3MOTOdgnNJp9M2GNx5x47dqEAPpgiiWriOJJnXNSSLaVGQhzkY9ebFWStM1KVGcGTShGdco409L8NO5TIUKimYDMICANYxJe94xz3Q4NTvML6PPI69LDh7JimxqaAQg4SJn7R1XQrrRiAq8n4NfAKpKpBE8BQ9+BUw8c1hzmY6l2exQ3ehDbzOG+dZGG4qk2eur3uKDmkyNk1HupPdjej4HiCiZqIrB1/PVamijF6Bp26C9aGFjAUPCcDXawwFMkoXXOxTl/ewo6gk4LyxHbUElTaBmQ2mhTjWtPdBK8stBlSs1rjqXZzcYASETT/RpgyMh9o7ivKGORK+7lKd2l3YBbuaOJmozwwtwCiZTglJDYyuq6CMTNHv8lxOafVkwrQ62aBPv8uTiU16Ll1X5xo+0u9c9166/hh2M89W2vlVcbiSP9IiyFbuDiMP3dlEMlJ8P1D+UsAcz1DqQ+2/l6NyQWuKezfFrW8HEf2uFrj2xBjGKgZ/28Mo5bZfCMsePuOYEqMrOntxyy36gDabIf4mQBfiUPKoxZ+yDQ6cJJpPA7avwRaFu5mrgoJEqzHGfA9R6Ax9EqBhKvB8xYkFJjiWfdJU2+cWeD/lxp+j0vB3h9/uc+NHoOgcbAq0H4lTF3KWWuknF1qCxHXLWbM4a2iWrCs3jZvKeaBoa4F5AKGLqbJa4oYjgS59GSJ+Za5bn2jkH1GUDmcsUm2sijqrTckkMbJdTsP2LDGrsb/e+5X3P5d6ZnSbHZ2AubeS9ZWqzRYDizIoG+Ipd3CZnqFeV+zfn+qfSgkYR36yJ4/PMEqbmnfbiGpvXjXPJlyOam1EWzrxKs21ZWpQ1lFKbC7UIVZ4VGzNQ6WmrfFA8w0knaBqh2JYuMiKryOk8u2EYDylL5liCKGovASbvqW7g8Ebfal3qy3B7cykjEzrq9OsMLTSKlhvj9KdeVUl5MY8UevMs/jeM42CDOdwa3muMN2twhvXarxYNqhZ6vqBYlGKy80OJ4bEXHhMNa/cUeZu3NFfZBUcrDN63tzBVXFazD0UHwrb9dHmt2UFNGt777d0Y1vDqidA5tWnGggey93HcLZ8TFv3KuROTCMkx4Faph0x5ANxy6jmrCtzeN6kkkTAX6KlZje+kOW8xUWMAyGv72s/RzE4Cnw8N8eg37GPM77DMsbYWbgtdi82ouC5zgwxUjtoVuCgIRfN75qNxidtRmErXGznwDLvnGp5KlhEukmVihtO0cyBTC/OcmcbQ1jFYMxbNp4f9MVHpHImw/iuq+vGBJ6T1Hx0imWwFD8BjH5n0K1GzQaZwS8c/JyLMi0uRd0FVDsPuPbi8vkcltnwiJ/MKxVegvybnqqpa3KoZ8NckWZT4uIIo2bTXbXqsvaUS/4UjwGFdL6YB2FYjV+6CXUjlAMyE9RdQCysytYEvzPFDNxENbnhwVE6joJtGlxNHNPvUqyDRh+9TJe+OGVGMftm+M2CT9AwwtefKDzwAS1DHoZYvAvIkyAGD6Ux5fZi7lXWEVkM9LVbyazVwan6aamPosC9bOFdaiWzknUnP7+tBbk7Cs8M5jGRsr2rGME2TMccp/zcM0Uf/dFELgrryV0Rg/DeJUEqjygQsvfePMH8X19v88NUTEjQA5kJUQwGA6xhUsDkckScHKF1wgIu5PnxfA6GegdkFU75Yz8q4CuaC3KobdtFkTnia25BKD1BLaNdRZsh6LwM9TT/AA/oOrTOb5DhLSe9T1s6CkVjVuKbo7L5PLinno8WGaJWpw4Bnj8ewuohECuGEVuTKWMoQUPqpgyyTbJQygTyvaWoz4bkUP6t7AqUbZnnrSvM2TFL+lBe8aMjPpQA0UPhhiipyGME61iudotLxnqA7YxJdHWPewkJY0y34YH2YBsmjmNWZw0qbFtZAbaZuEZhB0qQ2RjctbrCfEh91MrS+ZMXbB3M2PJXBCXh0vjgQ2dNdau2mdXFF11bi4pLW5Xyq11WQxed+ADPlPwu+GEbmHpkMTgPakv6WVw+rsbH9FrqbF13axpcua8E5RbO25mkyeuUhcUSrfimZU6UuRw0TcM2uPBpmq0rHqz46w3UkbOi0LNoqMSqhTn8MDyhEyzp5onKwsUwDxzX2ROqI5gIm+BzESz3NYoOuWaS/xgExCrsFVcrDBMIVTr7MXVbHZL4hQaws9K0oLFDugCqkdKOI8ZWzyjjBktNzqy/KCBzppV4UYYE0qOXsdlMR8x0tfVbyrLmDq2/61AwTzGHPhTGxLFNRVlhC1VF7JyH9ZVQCaf0xzWOCg46k1yS2xqCftOlSKNTnVwMmPqBC3Rksg2IlLoMuZmIj+owNOctxUKJwCMJc3y3wpKRLsl2qaSgCyWpiKT0zTwO1fTnlmYBmXcr8uvE1GR
        echo 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
        echo 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
        echo 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
        echo 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
        echo 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
        echo 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
    )

    set "OFFSET=--no-init-offset"
)
set "decompcabps=%decompcab:[=`[%"
set "decompcabps=%decompcabps:]=`]%"
set "decompcabps=%decompcabps:^=^^%"
set "decompcabps=%decompcabps:&=^&%"
powershell.exe -nologo -noprofile -noninteractive -command "& { [IO.File]::WriteAllBytes(\"%decompcab%\", [Convert]::FromBase64String([IO.File]::ReadAllText(\"%decompcab%.tmp\")))}"
call :elog .
if not exist "!decompcab!" (
	call :elog "%RED%!decm1.%LNG%!%RES%"
	call :elog .
	call :maybe_pause
	exit
) else (
	call :elog "%GRE%!decm2.%LNG%!%RES%"
	call :elog .
)

call :elog .
call :elog "!decm3.%LNG%!"
<nul set /p="!ENTERYN.%LNG%! "
choice /C OSJДYN /N /D N /T 5
if errorlevel 6 (
	set "owrpy=n"
	call :elog "    %YEL%!decm4.%LNG%!%RES%"
	call :elog .
) else if errorlevel 1 (
	set "owrpy=y"
	call :elog "    %YEL%!decm5.%LNG%!%RES%"
	call :elog .
)

call :DisplayVars "RPYC extract phase"

call :elog .

:: Once converted, extract the cab file. Needs to be a cab file due to expand.exe
set "found=0"
echo !decm6.%LNG%! >> "%UNRENLOG%"
<nul set /p=!decm6.%LNG%!
mkdir "%decompilerdir%"  >> "%UNRENLOG%" 2>&1
expand -F:* "%decompcab%" "%decompilerdir%" >> "%UNRENLOG%" 2>&1
move /y "%decompilerdir%\unrpyc.py" "%unrpycpy%" >> "%UNRENLOG%" 2>&1
move /y "%decompilerdir%\deobfuscate.py" "%deobfuscate%" >> "%UNRENLOG%" 2>&1
if not exist "!unrpycpy!" (
    call :elog "    %RED%!decm7.%LNG%! %unrpycpy%. !UNACONT.%LNG%!%RES%"
    call :elog .
    call :maybe_pause
    exit
) else (
    set "found=1"
)
if not exist "!deobfuscate!" (
    call :elog "    %RED%!decm7.%LNG%! %deobfuscate%. !UNACONT.%LNG%!%RES%"
    call :elog .
    call :maybe_pause
    exit
) else (
    if defined found (
        call :elog "%GRE% !PASS.%LNG%!%RES%"
        call :elog .
    )
)

:: Decompile rpyc files
call :elog .
call :elog "!decm8.%LNG%!"

for /R "game" %%f in (*.rpyc) do (
    set "error=0"
	set "rpyfile=%%~dpnf.rpy"
	set "relativerpy=!rpyfile:%WORKDIR%\game\=!"
	set "relativePath=%%f"
	set "relativePath=!relativePath:%WORKDIR%\game\=!"

	if not exist !rpyfile! (
		call :elog "    + !decm9.%LNG%! %YEL%'!relativePath!'%RES%"
		if "!OPTION!" == "7" (
			echo "!PYTHONHOME!python.exe" !PYNOASSERT! "!unrpycpy!" !OFFSET! --try-harder "%%f" >>"%UNRENLOG%"
			"!PYTHONHOME!python.exe" !PYNOASSERT! "!unrpycpy!" !OFFSET! --try-harder "%%f" >>"%UNRENLOG%" 2>&1
			set "error=!errorlevel!"
		) else (
			echo "!PYTHONHOME!python.exe" !PYNOASSERT! "!unrpycpy!" !OFFSET! "%%f" >>"%UNRENLOG%"
			"!PYTHONHOME!python.exe" !PYNOASSERT! "!unrpycpy!" !OFFSET! "%%f" >>"%UNRENLOG%" 2>&1
			set "error=!errorlevel!"
		)
	) else if exist !rpyfile! if "!owrpy!" == "y" (
		if not exist "!rpyfile!.org" (
            call :elog "    + !decm10.%LNG%! %YEL%'!relativePath!'%RES% !decm10a.%LNG%! %YEL%'!relativePath!.org'%RES%"
			copy "!rpyfile!" "!rpyfile!.org" %DEBUGREDIR%
		)

		call :elog "    + !decm11.%LNG%! %YEL%!relativePath!%RES%"
		if "!OPTION!" == "4" (
			echo "!PYTHONHOME!python.exe" !PYNOASSERT! "!unrpycpy!" --clobber !OFFSET! --try-harder "%%f" >>"%UNRENLOG%"
			"!PYTHONHOME!python.exe" !PYNOASSERT! "!unrpycpy!" --clobber !OFFSET! --try-harder "%%f" >>"%UNRENLOG%" 2>&1
			set "error=!errorlevel!"
		) else (
			echo "!PYTHONHOME!python.exe" !PYNOASSERT! "!unrpycpy!" --clobber !OFFSET! "%%f" >>"%UNRENLOG%"
			"!PYTHONHOME!python.exe" !PYNOASSERT! "!unrpycpy!" --clobber !OFFSET! "%%f" >>"%UNRENLOG%" 2>&1
			set "error=!errorlevel!"
		)
	) else if exist !rpyfile! if "!owrpy!" == "n" (
		call :elog "    + !decm12.%LNG%! %YEL%!relativePath!%RES%, %RES%!decm12a.%LNG%!%RES%"
		set "error=0"
	)
	if !error! NEQ 0 (
		call :elog "    %RED%- !decm13.%LNG%! %YEL%!relativePath!. %RES%!LOGCHK!"
	)
)

call :elog .

:: Clean up
call :elog "!CLEANUP.%LNG%!"
cd /d "%WORKDIR%"
del /f /q "%unrpycpy%o" %DEBUGREDIR%
del /f /q "%unrpyc%" %DEBUGREDIR%
del /f /q "%unrpycpy%" %DEBUGREDIR%
del /f /q "%decompcab%.tmp" %DEBUGREDIR%
del /f /q "%decompcab%" %DEBUGREDIR%
del /f /q "%decompcab%.tmp" %DEBUGREDIR%
del /f /q "%deobfuscate%" %DEBUGREDIR%
del /f /q "%deobfuscate%o" %DEBUGREDIR%
rmdir /Q /S "__pycache__" %DEBUGREDIR%
rmdir /Q /S "%decompilerdir%" %DEBUGREDIR%

call :elog "!DONE.%LNG%!"
timeout /t 5 /nobreak >nul
call :elog .

goto :eof


:: Drop our console/dev mode enabler into the game folder
:console
set "unren-console=%WORKDIR%\game\unren-console.rpy"
echo %YEL%!TWADD.%LNG%! %unren-console%.%RES%
echo %YEL%!INCASEDEL.%LNG%!%RES%
echo %YEL%%unren-console%%RES%
echo %YEL%%unren-console%c%RES%
call :elog .
call :elog .
echo !choicea.%LNG%!... >> "%UNRENLOG%"
<nul set /p="!choicea.%LNG%!... "
if exist "!unren-console!" (
    call :elog "%YEL%!APRESENT.%LNG%!%RES%"
) else (
    >"!unren-console!.b64" (
        echo IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KZGVmaW5lIDk5OSBjb25maWcuY29uc29sZSA9IFRydWUNCmRlZmluZSA5OTkgY29uZmlnLmRldmVsb3BlciA9IFRydWUNCg==
    )
    powershell.exe -nologo -noprofile -noninteractive -command "[IO.File]::WriteAllText('!unren-console!.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '!unren-console!.b64'))))" %DEBUGREDIR%
    if not exist "!unren-console!.tmp" (
        call :elog "%RED%!FAIL.%LNG%!%RES%"
    ) else (
        move /y "!unren-console!.tmp" "!unren-console!" %DEBUGREDIR%
        del /f /q "!unren-console!.b64" %DEBUGREDIR%
        call :elog "%GRE%!PASS.%LNG%!%RES%"
    )
)

goto :eof


:: Drop our debug mode enabler into the game folder
:debug
set "unren-debug=%WORKDIR%\game\unren-debug.rpy"
echo %YEL%!TWADD.%LNG%! %unren-debug%.%RES%
echo %YEL%!INCASEDEL.%LNG%!%RES%
echo %YEL%%unren-debug%%RES%
echo %YEL%%unren-debug%c%RES%
call :elog .
call :elog .
echo !choiceb.%LNG%!...  >> "%UNRENLOG%"
<nul set /p="!choiceb.%LNG%!... "
if exist "%unren-debug%" (
    call :elog "%YEL%!APRESENT.%LNG%!%RES%"
) else (
    >"!unren-debug!.b64" (
        echo IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KZGVmaW5lIDk5OSBjb25maWcuZGVidWcgPSBUcnVlDQo=
    )
    powershell.exe -nologo -noprofile -noninteractive -command "[IO.File]::WriteAllText('!unren-debug!.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '!unren-debug!.b64'))))" %DEBUGREDIR%
    if not exist "!unren-debug!.tmp" (
        call :elog "%RED%!FAIL.%LNG%!%RES%"
    ) else (
        move /y "!unren-debug!.tmp" "!unren-debug!" %DEBUGREDIR%
        del /f /q "!unren-debug!.b64" %DEBUGREDIR%
        call :elog "%GRE%!PASS.%LNG%!%RES%"
    )
)

goto :eof


:: Drop our skip file into the game folder
:skip
set "unren-skip=%WORKDIR%\game\unren-skip.rpy"
echo %YEL%!TWADD.%LNG%! %unren-skip%.%RES%
echo %YEL%!INCASEDEL.%LNG%!%RES%
echo %YEL%%unren-skip%%RES%
echo %YEL%%unren-skip%c%RES%
call :elog .
call :elog .
echo !choicec.%LNG%!... >> "%UNRENLOG%"
<nul set /p="!choicec.%LNG%!... "

if exist "!unren-skip!" (
    call :elog "%YEL%!APRESENT.%LNG%!%RES%"
) else (
    >"!unren-skip!.b64" (
        echo IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KaW5pdCA5OTkgcHl0aG9uOg0KICAgIF9wcmVmZXJlbmNlcy5za2lwX3Vuc2VlbiA9IFRydWUNCiAgICBjb25maWcuYWxsb3dfc2tpcHBpbmcgPSBUcnVlDQogICAgcmVucHkuZ2FtZS5wcmVmZXJlbmNlcy5za2lwX3Vuc2VlbiA9IFRydWUNCiAgICByZW5weS5nYW1lLnByZWZlcmVuY2VzLnNraXBfYWZ0ZXJfY2hvaWNlcyA9IFRydWUNCiAgICByZW5weS5jb25maWcuZmFzdF9za2lwcGluZyA9IFRydWUNCiAgICB0cnk6DQogICAgICAgIGNvbmZpZy5rZXltYXBbJ3NraXAnXSA9IFsgJ0tfTENUUkwnLCAnS19SQ1RSTCcgXQ0KICAgIGV4Y2VwdDoNCiAgICAgICAgcGFzcw0K
    )
    powershell.exe -nologo -noprofile -noninteractive -command "[IO.File]::WriteAllText('!unren-skip!.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '!unren-skip!.b64'))))" %DEBUGREDIR%
    if not exist "!unren-skip!.tmp" (
        call :elog "%RED%!FAIL.%LNG%!%RES%"
    ) else (
        move /y "!unren-skip!.tmp" "!unren-skip!" %DEBUGREDIR%
        del /f /q "!unren-skip!.b64" %DEBUGREDIR%
        call :elog "%GRE%!PASS.%LNG%!%RES%"
    )
)

goto :eof


:: Drop our skip file into the game folder
:skipall
set "unren-skipall=%WORKDIR%\game\unren-skipall.rpy"
echo %YEL%!TWADD.%LNG%! %unren-skipall%.%RES%
echo %YEL%!INCASEDEL.%LNG%!%RES%
echo %YEL%%unren-skipall%%RES%
echo %YEL%%unren-skipall%c%RES%
call :elog .
call :elog .
echo !choiced.%LNG%!... >> "%UNRENLOG%"
<nul set /p="!choiced.%LNG%!... "

if exist "!unren-skipall!" (
    call :elog "%YEL%!APRESENT.%LNG%!%RES%"
) else (
    >"!unren-skipall!.b64" (
        echo IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KaW5pdCA5OTkgcHl0aG9uOg0KICAgIF9wcmVmZXJlbmNlcy5za2lwX3Vuc2VlbiA9IFRydWUNCiAgICBjb25maWcuYWxsb3dfc2tpcHBpbmcgPSBUcnVlDQogICAgcmVucHkuZ2FtZS5wcmVmZXJlbmNlcy5za2lwX3Vuc2VlbiA9IFRydWUNCiAgICByZW5weS5nYW1lLnByZWZlcmVuY2VzLnNraXBfYWZ0ZXJfY2hvaWNlcyA9IFRydWUNCiAgICByZW5weS5jb25maWcuZmFzdF9za2lwcGluZyA9IFRydWUNCiAgICBwcmVmZXJlbmNlcy50cmFuc2l0aW9ucyA9IDANCiAgICB0cnk6DQogICAgICAgIGNvbmZpZy5rZXltYXBbJ3NraXAnXSA9IFsgJ0tfTENUUkwnLCAnS19SQ1RSTCcgXQ0KICAgIGV4Y2VwdDoNCiAgICAgICAgcGFzcw0K
    )
    powershell.exe -nologo -noprofile -noninteractive -command "[IO.File]::WriteAllText('!unren-skipall!.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '!unren-skipall!.b64'))))" %DEBUGREDIR%
    if not exist "!unren-skipall!.tmp" (
        call :elog "%RED%!FAIL.%LNG%!%RES%"
    ) else (
        move /y "!unren-skipall!.tmp" "!unren-skipall!" %DEBUGREDIR%
        del /f /q "!unren-skipall!.b64"
        call :elog "%GRE%!PASS.%LNG%!%RES%"
    )
)

goto :eof


:: Drop our rollback file into the game folder
:rollback
set "unren-rollback=%WORKDIR%\game\unren-rollback.rpy"
echo %YEL%!TWADD.%LNG%! %unren-rollback%.%RES%
echo %YEL%!INCASEDEL.%LNG%!%RES%
echo %YEL%%unren-rollback%%RES%
echo %YEL%%unren-rollback%c%RES%
call :elog .
call :elog .
echo !choicee.%LNG%!... >> "%UNRENLOG%"
<nul set /p="!choicee.%LNG%!... "

if exist "!unren-rollback!" (
    call :elog "%YEL%!APRESENT.%LNG%!%RES%"
) else (
    > "!unren-rollback!.b64" (
        echo IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KaW5pdCA5OTkgcHl0aG9uOg0KICAgIHJlbnB5LmNvbmZpZy5yb2xsYmFja19lbmFibGVkID0gVHJ1ZQ0KICAgIHJlbnB5LmNvbmZpZy5oYXJkX3JvbGxiYWNrX2xpbWl0ID0gMjU2DQogICAgcmVucHkuY29uZmlnLnJvbGxiYWNrX2xlbmd0aCA9IDI1Ng0KICAgIGRlZiB1bnJlbl9ub2Jsb2NrKCphcmdzLCAqKmt3YXJncyk6DQogICAgICAgIHJldHVybg0KICAgIHJlbnB5LmJsb2NrX3JvbGxiYWNrID0gdW5yZW5fbm9ibG9jaw0KICAgIHRyeToNCiAgICAgICAgY29uZmlnLmtleW1hcFsncm9sbGJhY2snXSA9IFsgJ0tfUEFHRVVQJywgJ3JlcGVhdF9LX1BBR0VVUCcsICdLX0FDX0JBQ0snLCAnbW91c2Vkb3duXzQnIF0NCiAgICBleGNlcHQ6DQogICAgICAgIHBhc3MNCg==
    )
    powershell.exe -nologo -noprofile -noninteractive -command "[IO.File]::WriteAllText('!unren-rollback!.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '!unren-rollback!.b64'))))" %DEBUGREDIR%
    if not exist "!unren-rollback!.tmp" (
        call :elog "%RED%!FAIL.%LNG%!%RES%"
    ) else (
        move /y "!unren-rollback!.tmp" "!unren-rollback!" %DEBUGREDIR%
        del /f /q "!unren-rollback!.b64" %DEBUGREDIR%
        call :elog "%GRE%!PASS.%LNG%!%RES%"
    )
)

goto :eof


:: Drop our Quick Save/Load file into the game folder
:quick
set "unren-quick=%WORKDIR%\game\unren-quick.rpy"
echo %YEL%!TWADD.%LNG%! %unren-quick%.%RES%
echo %YEL%!INCASEDEL.%LNG%!%RES%
echo %YEL%%unren-quick%%RES%
echo %YEL%%unren-quick%c%RES%
call :elog .
call :elog .
echo !choicef.%LNG%!... >> "%UNRENLOG%"
<nul set /p="!choicef.%LNG%!... "

if exist "!unren-quick!" (
    call :elog "%YEL%!APRESENT.%LNG%!%RES%"
) else (
    >"!unren-quick!.b64" (
        echo IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KaW5pdCA5OTkgcHl0aG9uOg0KICAgIHRyeToNCiAgICAgICAgY29uZmlnLnVuZGVybGF5WzBdLmtleW1hcFsncXVpY2tTYXZlJ10gPSBRdWlja1NhdmUoKQ0KICAgICAgICBjb25maWcua2V5bWFwWydxdWlja1NhdmUnXSA9ICdLX0Y1Jw0KICAgICAgICBjb25maWcudW5kZXJsYXlbMF0ua2V5bWFwWydxdWlja0xvYWQnXSA9IFF1aWNrTG9hZCgpDQogICAgICAgIGNvbmZpZy5rZXltYXBbJ3F1aWNrTG9hZCddID0gJ0tfRjknDQogICAgZXhjZXB0Og0KICAgICAgICBwYXNzDQo=
    )
    powershell.exe -nologo -noprofile -noninteractive -command "[IO.File]::WriteAllText('!unren-quick!.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '!unren-quick!.b64'))))" %DEBUGREDIR%
    if not exist "!unren-quick!.tmp" (
        call :elog "%RED%!FAIL.%LNG%!%RES%"
    ) else (
        move /y "!unren-quick!.tmp" "!unren-quick!" %DEBUGREDIR%
        del /f /q "!unren-quick!.b64" %DEBUGREDIR%
        call :elog "%GRE%!PASS.%LNG%!%RES%"
    )
)

goto :eof


:: Drop our Quick Menu file into the game folder
:qmenu
set "unren-qmenu=%WORKDIR%\game\unren-qmenu.rpy"
echo %YEL%!TWADD.%LNG%! %unren-qmenu%.%RES%
echo %YEL%!INCASEDEL.%LNG%!%RES%
echo %YEL%%unren-qmenu%%RES%
echo %YEL%%unren-qmenu%c%RES%
call :elog .
call :elog .
echo !choiceg.%LNG%!... >> "%UNRENLOG%"
<nul set /p="!choiceg.%LNG%!... "

if exist "!unren-qmenu!" (
    call :elog "%YEL%!APRESENT.%LNG%!%RES%"
) else (
    >"!unren-qmenu!.b64" (
        echo IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KaW5pdCBweXRob246DQogICAgZGVmIGFsd2F5c19lbmFibGVfcXVpY2tfbWVudSgpOg0KICAgICAgICBzdG9yZS5xdWlja19tZW51ID0gVHJ1ZQ0KICAgICAgICByZW5weS5zaG93X3NjcmVlbigicXVpY2tfbWVudSIpDQogICAgY29uZmlnLm92ZXJsYXlfZnVuY3Rpb25zLmFwcGVuZChhbHdheXNfZW5hYmxlX3F1aWNrX21lbnUpDQoNCiAgICBkZWYgZm9yY2VfcXVpY2tfbWVudV9vbl9pbnRlcmFjdCgpOg0KICAgICAgICBzdG9yZS5xdWlja19tZW51ID0gVHJ1ZQ0KICAgIGNvbmZpZy5pbnRlcmFjdF9jYWxsYmFja3MuYXBwZW5kKGZvcmNlX3F1aWNrX21lbnVfb25faW50ZXJhY3Qp
    )
    powershell.exe -nologo -noprofile -noninteractive -command "[IO.File]::WriteAllText('!unren-qmenu!.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '!unren-qmenu!.b64'))))" %DEBUGREDIR%
    if not exist "!unren-qmenu!.tmp" (
        call :elog "%RED%!FAIL.%LNG%!%RES%"
    ) else (
        move /y "!unren-qmenu!.tmp" "!unren-qmenu!" %DEBUGREDIR%
        del /f /q "!unren-qmenu!.b64" %DEBUGREDIR%
        call :elog "%GRE%!PASS.%LNG%!%RES%"
    )
)

goto :eof


:: Add the Universal Gallery Unlocker to the game folder
:add_ugu
set "ugu_name=Universal_Gallery_Unlocker ZLZK"
set "url=https://attachments.f95zone.to/2024/01/3314515_Universal_Gallery_Unlocker_2024-01-24_ZLZK.zip"
set "uguzip=%TEMP%\Universal_Gallery_Unlocker.zip"
set "uguhardzip=%TEMP%\hard.zip"
set "ugusoftzip=%TEMP%\soft.zip"
set "ugudir=%WORKDIR%\game\_mods\"
del /f /q "%uguzip%" %DEBUGREDIR%
del /f /q "%uguhardzip%" %DEBUGREDIR%
del /f /q "%ugusoftzip%" %DEBUGREDIR%

echo %YEL%!TWADD.%LNG%! %ugudir%.%RES%
echo %YEL%!INCASEOF.%LNG%! %RES%
echo %MAG%https://f95zone.to/threads/universal-gallery-unlocker-2024-01-24-zlzk.136812/%RES%
echo %YEL%!INCASEDEL.%LNG%!%RES%
echo %YEL%%ugudir%\ZLZK_UGU_soft%RES%
call :elog .
call :elog .
echo !choiceh.%LNG%!... >> "%UNRENLOG%"
<nul set /p="!choiceh.%LNG%!... "

if !debuglevel! GEQ 1 (
    call :elog .
    echo powershell.exe -nologo -noprofile -noninteractive -command "(New-Object System.Net.WebClient).DownloadFile('!url!','!uguzip!')"
)
powershell.exe -nologo -noprofile -noninteractive -command "(New-Object System.Net.WebClient).DownloadFile('!url!','!uguzip!')" %DEBUGREDIR%
if !errorlevel! NEQ 0 (
    call :elog "%RED%!FAIL.%LNG%!%RES%"
) else (
    if !debuglevel! GEQ 1 (
        call :elog .
        echo powershell.exe -nologo -noprofile -noninteractive -command "Expand-Archive -Force '!uguzip!' '!TEMP!'"
    )
    powershell.exe -nologo -noprofile -noninteractive -command "Expand-Archive -Force '!uguzip!' '!TEMP!'" %DEBUGREDIR%
    if not exist "!uguhardzip!" (
        echo %RED%!FAIL.%LNG%! !MISSING.%LNG%! !uguhardzip! %RES%
        goto skip_ugu
    )
    if not exist "!ugusoftzip!" (
        echo %RED%!FAIL.%LNG%! !MISSING.%LNG%! !ugusoftzip! %RES%
        goto skip_ugu
    )
    if !debuglevel! GEQ 1 (
        call :elog .
        echo powershell.exe -nologo -noprofile -noninteractive -command "Expand-Archive -Force '!ugusoftzip!' '!WORKDIR!'"
    )
    powershell.exe -nologo -noprofile -noninteractive -command "Expand-Archive -Force '!ugusoftzip!' '!WORKDIR!'" %DEBUGREDIR%
    if !errorlevel! NEQ 0 (
        call :elog "%RED%!FAIL.%LNG%! !UNEXTRACT.%LNG%! !ugusoftzip! %RES%"
        goto skip_ucd
    ) else (
        call :elog "%GRE%!PASS.%LNG%!%RES%"
    )
    del /f /q "%ugusoftzip%" %DEBUGREDIR%
    del /f /q "%uguhardzip%" %DEBUGREDIR%
    del /f /q "%uguzip%" %DEBUGREDIR%
    del /f /q "%TEMP%\readme.txt" %DEBUGREDIR%
)

goto :eof


:: Add the Universal Choice Descriptor to the game folder
:add_ucd
set "ucd_name=Universal_Choice_Descriptor ZLZK"
set "url=https://attachments.f95zone.to/2024/01/3314453_Universal_Choice_Descriptor.zip"
set "ucdzip=%TEMP%\Universal_Choice_Descriptor.zip"
set "ucdzip_part1=%TEMP%\Universal_Choice_Descriptor_[2024-01-24]_[ZLZK].zip"
set "ucdzip_part2=%TEMP%\ZLZK_[2024-01-24]_[ZLZK].zip"

set "ucddir=%WORKDIR%\game\_mods\"
del /f /q "%ucdzip%" %DEBUGREDIR%
del /f /q "%ucdzip_part1%" %DEBUGREDIR%
del /f /q "%ucdzip_part2%" %DEBUGREDIR%
del /f /q "%TEMP%\Readme.txt" %DEBUGREDIR%

echo %YEL%!TWADD.%LNG%! %ucddir%.%RES%
echo %YEL%!INCASEOF.%LNG%! %RES%
echo %MAG%https://f95zone.to/threads/universal-gallery-unlocker-2024-01-24-zlzk.136812/%RES%
echo %YEL%!INCASEDEL.%LNG%!%RES%
echo %YEL%%ucddir%%RES%
call :elog .
call :elog .
echo !choicei.%LNG%!... >> "%UNRENLOG%"
<nul set /p="!choicei.%LNG%!... "
if !debuglevel! GEQ 1 (
    call :elog .
    echo powershell.exe -nologo -noprofile -noninteractive -command "(New-Object System.Net.WebClient).DownloadFile('!url!','!ucdzip!')"
)
powershell.exe -nologo -noprofile -noninteractive -command "(New-Object System.Net.WebClient).DownloadFile('!url!','!ucdzip!')" %DEBUGREDIR%
if not exist "!ucdzip!" (
	call :elog "%RED%!FAIL.%LNG%! !UNDWNLD.%LNG%! !url! %RES%"
	goto skip_ucd
) else (
	if !debuglevel! GEQ 1 (
        call :elog .
        echo powershell.exe -nologo -noprofile -noninteractive -command "Expand-Archive -Force '!ucdzip!' '!TEMP!'"
    )
	powershell.exe -nologo -noprofile -noninteractive -command "Expand-Archive -Force '!ucdzip!' '!TEMP!'" %DEBUGREDIR%
    if not exist "!ucdzip_part1!" (
        call :elog "%RED%!FAIL.%LNG%! !MISSING.%LNG%! !ucdzip_part1! %RES%"
        goto skip_ucd
    ) else (
        move /y "!ucdzip_part1!" !TEMP!\part1.zip %DEBUGREDIR%
    )
    if not exist "!ucdzip_part2!" (
        call :elog "%RED%!FAIL.%LNG%! !MISSING.%LNG%! !ucdzip_part2! %RES%"
        goto skip_ucd
    ) else (
        move /y "!ucdzip_part2!" !TEMP!\part2.zip %DEBUGREDIR%
    )
    if !debuglevel! GEQ 1 (
        call :elog .
        echo powershell.exe -nologo -noprofile -noninteractive -command "Expand-Archive -Force '!TEMP!\part1.zip' '!WORKDIR!'"
    )
    powershell.exe -nologo -noprofile -noninteractive -command "Expand-Archive -Force '!TEMP!\part1.zip' '!WORKDIR!'" %DEBUGREDIR%
    if !errorlevel! NEQ 0 (
        call :elog "%RED%!FAIL.%LNG%! !UNEXTRACT.%LNG%! !ucdzip_part1! %RES%"
        goto skip_ucd
    )
    if !debuglevel! GEQ 1 (
        call :elog .
        echo powershell.exe -nologo -noprofile -noninteractive -command "Expand-Archive -Force '!TEMP!\part2.zip' '!WORKDIR!'"
    )
    powershell.exe -nologo -noprofile -noninteractive -command "Expand-Archive -Force '!TEMP!\part2.zip' '!WORKDIR!'" %DEBUGREDIR%
    if !errorlevel! NEQ 0 (
        call :elog "%RED%!FAIL.%LNG%! !UNEXTRACT.%LNG%! !ucdzip_part2! %RES%"
        goto skip_ucd
    )
    call :elog "%GRE%!PASS.%LNG%!%RES%"
    :skip_ucd
	del /f /q "!ucdzip!" %DEBUGREDIR%
    del /f /q "!ucdzip_part1!" %DEBUGREDIR%
    del /f /q "!TEMP!\part1.zip" %DEBUGREDIR%
    del /f /q "!ucdzip_part2!" %DEBUGREDIR%
    del /f /q "!TEMP!\part2.zip" %DEBUGREDIR%
    del /f /q "!TEMP!\readme.txt" %DEBUGREDIR%
)

goto :eof


:: Download and install Universal Transparent Text Box Mod by Penfold Mole
:add_utbox
set "utbox_name=Universal Transparent Text Box Mod"
set "url=https://attachments.f95zone.to/2023/12/3214690_RenPy_universal_transparent_textbox_mod_v2.6.4_by_Penfold_Mole.7z"
set "utboxzip=%TEMP%\RenPy_Transparent_Text_Box_Mod.7z"
set "utbox_file=%WORKDIR%\game\y_outline.rpy"
set "utbox_tdir=%TEMP%\utbox"

:: Need 7z.exe for extraction
if not exist "!ProgramFiles!\7-Zip\7z.exe" (
    echo %RED%!FAIL.%LNG%! !MISSING.%LNG%! %YEL%%ProgramFiles%\7-Zip\7z.exe %RES%
    goto skip_utbox
)

del /f /q "!utbox_file!" %DEBUGREDIR%

echo %YEL%!TWADD.%LNG%! !utbox_file! %RES%
echo %YEL%!INCASEOF.%LNG%! %RES%
echo %MAG%https://f95zone.to/threads/renpy-transparent-text-box-mod-v2-6-4.11925/%RES%
echo %YEL%!INCASEDEL.%LNG%!%RES%
echo %YEL%!utbox_file!%RES%
call :elog .
call :elog .
echo !choicej.%LNG%!... >> "%UNRENLOG%"
<nul set /p="!choicej.%LNG%!..."

del /f /q "!utboxzip!" %DEBUGREDIR%
rd /s /q "!utbox_tdir!" %DEBUGREDIR%

if !debuglevel! GEQ 1 (
    call :elog .
    echo powershell.exe -nologo -noprofile -noninteractive -command "(New-Object System.Net.WebClient).DownloadFile('!url!','!utboxzip!')"
)
powershell.exe -nologo -noprofile -noninteractive -command "(New-Object System.Net.WebClient).DownloadFile('%url%','%utboxzip%')" %DEBUGREDIR%
if not exist "!utboxzip!" (
    echo %RED% !FAIL.%LNG%! !UNDWNLD.%LNG%! !url! %RES%
    goto skip_utbox
) else (
    if !debuglevel! GEQ 1 (
        call :elog .
        echo "!ProgramFiles!\7-Zip\7z.exe" x -y -o"!utbox_tdir!" "!utboxzip!"
    )
    "!ProgramFiles!\7-Zip\7z.exe" x -y -o"!utbox_tdir!" "!utboxzip!" %DEBUGREDIR%
    if not exist "!utbox_tdir!\game\y_outline.rpy" (
        echo %RED% !FAIL.%LNG%! !UNEXTRACT.%LNG%! "!utboxzip!" %RES%
        goto skip_utbox
    ) else (
        move /y "!utbox_tdir!\game\y_outline.rpy" "!WORKDIR!\game" %DEBUGREDIR%
        if exist "!utbox_file!" (
            echo %GRE% !PASS.%LNG%!%RES%
        ) else (
            echo %RED% !FAIL.%LNG%! !MISSING.%LNG%! %YEL%!utbox_file! %RES%
        )
    )
    :skip_utbox
    del /f /q "!utboxzip!" %DEBUGREDIR%
    rd /s /q "!utbox_tdir!" %DEBUGREDIR%
)

goto :eof


:: Download 0x52_URM and add to the game
:add_urm
set "urm_name=0x52_URM"
set "url=https://attachments.f95zone.to/2025/07/5028578_0x52_URM.zip"
set "urm_zip=%TEMP%\0x52_URM.zip"
set "urm_rpa=%WORKDIR%\game\0x52_URM.rpa"
del /f /q "%urm_zip%" %DEBUGREDIR%

echo %YEL%!TWADD.%LNG%! %urm_rpa%.%RES%
echo %YEL%!INCASEOF.%LNG%! %RES%
echo %MAG%https://f95zone.to/threads/universal-renpy-mod-urm-2-6-2-mod-any-renpy-game-yourself.48025/%RES%
echo %YEL%!INCASEDEL.%LNG%!%RES%
echo %YEL%%urm_rpa%%RES%

call :elog .
call :elog .
echo !choicek.%LNG%!... >> "%UNRENLOG%"
<nul set /p="!choicek.%LNG%!... "

if %debuglevel% GEQ 1 (
    call :elog .
    echo powershell.exe -nologo -noprofile -noninteractive -command "(New-Object System.Net.WebClient).DownloadFile('!url!','!urm_zip!.tmp')"
)
powershell.exe -nologo -noprofile -noninteractive -command "(New-Object System.Net.WebClient).DownloadFile('!url!','!urm_zip!.tmp')" %DEBUGREDIR%
if not exist "!urm_zip!.tmp" (
	echo %RED%!FAIL.%LNG%! !UNDWNLD.%LNG%! !urm_name!.zip.%RES%
) else (
    move /y "!urm_zip!.tmp" "!urm_zip!" %DEBUGREDIR%
    if !debuglevel! GEQ 1 (
        call :elog .
        echo powershell.exe -nologo -noprofile -noninteractive -command "Expand-Archive -Force '!urm_zip!' '!WORKDIR!\game'"
    )
	powershell.exe -nologo -noprofile -noninteractive -command "Expand-Archive -Force '!urm_zip!' '!WORKDIR!\game'" %DEBUGREDIR%
	if !errorlevel! NEQ 0 (
		echo %RED%!FAIL.%LNG%! !UNINSTALL.%LNG%! !urm_name! %RES%
	) else (
		echo %GRE%!PASS.%LNG%!%RES%
	)
	del /f /q "!urm_zip!" %DEBUGREDIR%
)

goto :eof


:: Replace MCName in game files
:replace_mcname
set "unr-mcchange=%WORKDIR%\game\unren-mcchange.rpy"

set "rmcname.en=Please input the new name (without quotes): "
set "rmcname.zh=请输入新名字（不含引号）： "

set "rmcname2.en=No name provided."
set "rmcname2.zh=未提供名字。"

set "rmcname3.en=Please input the old name (without quotes): "
set "rmcname3.zh=请输入旧名字（不含引号）： "

echo %YEL%!TWADD.%LNG%! %unr-mcchange%.%RES%
echo %YEL%!INCASEDEL.%LNG%!%RES%
echo %YEL%%unr-mcchange%%RES%
echo %YEL%%unr-mcchange%c%RES%

call :elog .
call :elog .
set "oldmcname="
echo oldmcname=!rmcname3.%LNG%! >> "%UNRENLOG%"
set /p "oldmcname=!rmcname3.%LNG%!"

if "!oldmcname!" == "" (
    echo %RED%!FAIL.%LNG%! !rmcname2.%LNG%!.%RES%
    goto mcend
) else (
    echo oldmcname=!oldmcname! >> "%UNRENLOG%"
)

call :elog .
set "newmcname="
echo newmcname=!rmcname.%LNG%! >> "%UNRENLOG%"
set /p "newmcname=!rmcname.%LNG%!"

if "!newmcname!" == "" (
    echo %RED%!FAIL.%LNG%! !rmcname2.%LNG%!.%RES%
    goto mcend
) else (
    echo newmcname=!newmcname! >> "%UNRENLOG%"
)

call :elog .
echo !choicel.%LNG%!... >> "%UNRENLOG%"
<nul set /p="!choicel.%LNG%!... "

>"%unr-mcchange%.b64" (
    echo IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KZGVmaW5lIDk5OSBtY25hbWUgPSAibmV3bWNuYW1lIg0KZGVmaW5lIDk5OSBNQyA9ICJuZXdtY25hbWUiDQpkZWZpbmUgOTk5IE1DX25hbWUgPSAibmV3bWNuYW1lIg0KZGVmaW5lIDk5OSBtY19uYW1lID0gIm5ld21jbmFtZSINCg0KaW5pdCA5OTkgcHl0aG9uOg0KICAgIGltcG9ydCByZQ0KDQogICAgIyBQbGFjZWhvbGRlcnMgcmVwbGFjZWQgYnkgUG93ZXJTaGVsbCBiZWZvcmUgZXhlY3V0aW9uDQogICAgT0xEID0gIm9sZG1jbmFtZSINCiAgICBORVcgPSAibmV3bWNuYW1lIg0KDQogICAgZGVmIF9jYXNlX2xpa2UocywgbW9kZWwpOg0KICAgICAgICAjIEFsaWduIHRoZSBjYXNlIG9mIHMgd2l0aCB0aGF0IG9mIG1vZGVsICh1cHBlciwgVGl0bGUsIGxvd2VyKQ0KICAgICAgICBpZiBtb2RlbC5pc3VwcGVyKCk6DQogICAgICAgICAgICByZXR1cm4gcy51cHBlcigpDQogICAgICAgIGVsaWYgbW9kZWxbOjFdLmlzdXBwZXIoKSBhbmQgbW9kZWxbMTpdLmlzbG93ZXIoKToNCiAgICAgICAgICAgIHJldHVybiBzLmNhcGl0YWxpemUoKQ0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgcmV0dXJuIHMubG93ZXIoKQ0KDQogICAgZGVmIHJlcGxhY2VfdGV4dCh0KToNCiAgICAgICAgb2xkID0gT0xEDQogICAgICAgIG5ldyA9IE5FVw0KDQogICAgICAgIG9fZXNjID0gcmUuZXNjYXBlKG9sZCkNCiAgICAgICAgZl9vbGQgPSBvbGRbOjFdDQogICAgICAgIGZfbmV3ID0gbmV3WzoxXQ0KDQogICAgICAgICMgMSkgUmVwbGFjZW1lbnQgb2YgdGhlIGVudGlyZSB3b3JkIChjYXNlLWluc2Vuc2l0aXZlKSB3aXRoIGNhc2UgcmVzdG9yYXRpb24NCiAgICAgICAgYmFzZV9wYXQgPSByZS5jb21waWxlKHJmIlxiKD9pOih7b19lc2N9KSlcYiIpDQogICAgICAgIGRlZiBiYXNlX3JlcGwobSk6DQogICAgICAgICAgICByZXR1cm4gX2Nhc2VfbGlrZShuZXcsIG0uZ3JvdXAoMSkpDQogICAgICAgIHQgPSBiYXNlX3BhdC5zdWIoYmFzZV9yZXBsLCB0KQ0KDQogICAgICAgICMgMikgU3R1dHRlcmluZyB0eXBlOiBjLWNvbm5vciDihpIgai1qb2UgKGFuZCBjYXNlIHZhcmlhbnRzKQ0KICAgICAgICBzdDFfcGF0ID0gcmUuY29tcGlsZShyZiJcYihbe2Zfb2xkLmxvd2VyKCl9e2Zfb2xkLnVwcGVyKCl9XSktKD9pOih7b19lc2N9KSlcYiIpDQogICAgICAgIGRlZiBzdDFfcmVwbChtKToNCiAgICAgICAgICAgIHByZWYgPSBtLmdyb3VwKDEpICAgICAgICMgcHJlZml4IGxldHRlciAoYy9DKQ0KICAgICAgICAgICAgb2xkX3BhcnQgPSBtLmdyb3VwKDIpICAgIyB3b3JkIChjb25ub3IvQ29ubm9yL0NPTk5PUikNCiAgICAgICAgICAgIG5ld193b3JkID0gX2Nhc2VfbGlrZShuZXcsIG9sZF9wYXJ0KQ0KICAgICAgICAgICAgbmV3X2ZpcnN0ID0gZl9uZXcudXBwZXIoKSBpZiBwcmVmLmlzdXBwZXIoKSBlbHNlIGZfbmV3Lmxvd2VyKCkNCiAgICAgICAgICAgIHJldHVybiBmIntuZXdfZmlyc3R9LXtuZXdfd29yZH0iDQogICAgICAgIHQgPSBzdDFfcGF0LnN1YihzdDFfcmVwbCwgdCkNCg0KICAgICAgICAjIDMpIFN0dXR0ZXJpbmcgdHlwZTogY28tY29ubm9yIOKGkiBqby1qb2UgKGFuZCBjYXNlIHZhcmlhbnRzKQ0KICAgICAgICBzdDJfcGF0ID0gcmUuY29tcGlsZShyZiJcYihbe2Zfb2xkLmxvd2VyKCl9e2Zfb2xkLnVwcGVyKCl9XSkoW29PXSktKD9pOih7b19lc2N9KSlcYiIpDQogICAgICAgIGRlZiBzdDJfcmVwbChtKToNCiAgICAgICAgICAgIHByZWYgPSBtLmdyb3VwKDEpICAgICAgICMgcHJlZml4IGxldHRlciAoYy9DKQ0KICAgICAgICAgICAgb2NoYXIgPSBtLmdyb3VwKDIpICAgICAgIyAnbycgb3IgJ08nDQogICAgICAgICAgICBvbGRfcGFydCA9IG0uZ3JvdXAoMykgICAjIHdvcmQgKGNvbm5vci9Db25ub3IvQ09OTk9SKQ0KICAgICAgICAgICAgbmV3X3dvcmQgPSBfY2FzZV9saWtlKG5ldywgb2xkX3BhcnQpDQogICAgICAgICAgICBuZXdfZmlyc3QgPSBmX25ldy51cHBlcigpIGlmIHByZWYuaXN1cHBlcigpIGVsc2UgZl9uZXcubG93ZXIoKQ0KICAgICAgICAgICAgIyBLZWVwIHRoZSBjYXNlIG9mIHRoZSAnbycgbGV0dGVyIGFzIGVuY291bnRlcmVkDQogICAgICAgICAgICByZXR1cm4gZiJ7bmV3X2ZpcnN0fXtvY2hhcn0te25ld193b3JkfSINCiAgICAgICAgdCA9IHN0Ml9wYXQuc3ViKHN0Ml9yZXBsLCB0KQ0KDQogICAgICAgIHJldHVybiB0DQoNCiAgICBjb25maWcucmVwbGFjZV90ZXh0ID0gcmVwbGFjZV90ZXh0DQogICAgZGVsIHJlcGxhY2VfdGV4dA0K
)
powershell.exe -nologo -noprofile -noninteractive -command "[IO.File]::WriteAllBytes('!unr-mcchange!.tmp', [Convert]::FromBase64String((Get-Content '!unr-mcchange!.b64' -Raw)))" %DEBUGREDIR%
if not exist "!unr-mcchange!.tmp" (
    echo %RED%!FAIL.%LNG%!%RES% !MISSING.%LNG%! !unr-mcchange!.tmp
    goto mcend
) else (
    del /f /q "!unr-mcchange!.b64" %DEBUGREDIR%
    powershell.exe -nologo -noprofile -noninteractive -command "(Get-Content '!unr-mcchange!.tmp') -replace 'newmcname', '!newmcname!' | Set-Content '!unr-mcchange!'" %DEBUGREDIR%
    powershell.exe -nologo -noprofile -noninteractive -command "(Get-Content '!unr-mcchange!') -replace 'oldmcname', '!oldmcname!' | Set-Content '!unr-mcchange!'" %DEBUGREDIR%
    if not exist "!unr-mcchange!" (
        echo %RED%!FAIL.%LNG%!%RES% !MISSING.%LNG%! !unr-mcchange!
        goto mcend
    )
    del /f /q "!unr-mcchange!.tmp" %DEBUGREDIR%
    echo %GRE%!PASS.%LNG%!%RES%
)

:mcend

goto :eof


:: Extract text for translation purpose
:extract_text
if "!LNG!" == "en"  set translation_lang=english
if "!LNG!" == "fr"  set translation_lang=french
if "!LNG!" == "es"  set translation_lang=spanish
if "!LNG!" == "it"  set translation_lang=italian
if "!LNG!" == "de"  set translation_lang=german
if "!LNG!" == "ru"  set translation_lang=russian

cd /d "%WORKDIR%"

set "etext1.en=Searching for game name"
set "etext1.zh=正在搜索游戏名称"

set "etext2.en=No game files found with .exe, .py or .sh extensions."
set "etext2.zh=未找到 .exe、.py 或 .sh 扩展名的游戏文件。"

set "etext3.en=Enter the target translation language (%YEL%%translation_lang%%RES% by default): "
set "etext3.zh=请输入目标翻译语言（默认 %YEL%%translation_lang%%RES%）： "

set "etext4.en=Unable to extract text for translation."
set "etext4.zh=无法提取用于翻译的文本。"

set "etext5.en=Please input the game name (without extension): "
set "etext5.zh=请输入游戏名称（不含扩展名）： "

:: find the current game name by checking the presence of same name with .exe, .py and .sh extension
call :elog .
if not "!OPTION!" == "m" echo.
<nul set /p="!etext1.%LNG%!... "

set "processed="
set "fname="

:: Do not test with sh, it can be not shipped
for %%e in (exe py) do (
    for %%f in (*.%%e) do (
        set "tempfname=%%~nf"

        :: Check if this name has already been processed
        echo !processed! | findstr /i "\!tempfname!" >nul
        if errorlevel 1 (
            :: Count how many files with this name exist
            set /a count=0
            for %%x in (exe py) do (
                if exist "%%~dpf!tempfname!.%%x" (
                    set /a count+=1
                )
            )
            if !count! EQU 2 (
                echo %YEL%!tempfname! %GRE%!PASS.%LNG%!%YEL%%RES%
                set "processed=!processed! !tempfname!"
                set "fname=!tempfname!"
                goto found_name
            )
        )
    )
)

:: If no name found, ask user to input the name
if "!fname!"  == "" (
    echo %RED%!FAIL.%LNG%! !etext2.%LNG%!%RES%
    goto input_name
)

:input_name
call :elog .
set /p "fname=!etext5.%LNG%!"
if "!fname!" == "" (
    echo %RED%!FAIL.%LNG%! !etext2.%LNG%!%RES%
    goto input_name
) else (
    REM set "fname=%fname:.=%"
    if not exist "!WORKDIR!\!fname!.exe" (
        echo %RED%!FAIL.%LNG%! !etext2.%LNG%!%RES%
        goto input_name
    )
)

:found_name
call :elog .
set /p "translation_lang=!etext3.%LNG%!"

if not defined translation_lang (
	set "translation_lang=french"
)

if not exist "!WORKDIR!\game\tl\" (
	mkdir "!WORKDIR!\game\tl"
)

call :elog .
call :elog .
echo !choicet.%LNG%!... >> "%UNRENLOG%"
<nul set /p="!choicet.%LNG%!... "

cd /d "%WORKDIR%"
if !debuglevel! GEQ 1 echo "!PYTHONHOME!python.exe" %PYNOASSERT% "!fname!.py" game translate !translation_lang!
"!PYTHONHOME!python.exe" %PYNOASSERT% "!fname!.py" game translate !translation_lang! %DEBUGREDIR%
if !errorlevel! NEQ 0 (
	echo %RED%!FAIL.%LNG%! !etext4.%LNG%!%RES%
) else (
    echo %GRE%!PASS.%LNG%!%RES%
)
call :elog .

goto :eof


:: Add entry to registry
:add_reg
set "areg1.en=This will add an entry to the right-click menu for folders."
set "areg1.zh=这将为文件夹右键菜单添加一个条目。"

set "areg2.en=When you select this option,"
set "areg2.zh=当你选择该选项时，"

set "areg2a.en=the script "%SCRIPTDIR%%SCRIPTNAME%" will be executed."
set "areg2a.zh=将执行脚本 "%SCRIPTDIR%%SCRIPTNAME%"。"

set "areg3.en=Adding the right-click menu entry to the registry... "
set "areg3.zh=正在向注册表添加右键菜单项... "

set "areg4.en=Run %SCRIPTNAME% Script"
set "areg4.zh=运行 %SCRIPTNAME% 脚本"

call :check_admin

call :elog .
echo %YEL%!areg1.%LNG%!%RES%
echo %YEL%!areg2.%LNG%!%RES%
echo %YEL%!areg2a.%LNG%!%RES%
call :elog .
echo !areg3.%LNG%! >> "%UNRENLOG%"
<nul set /p="!areg3.%LNG%!"

:: Add registry key
reg add "HKCR\Directory\shell\Run%SCRIPTNAME%" /ve /d "!areg4.%LNG%!" /f %DEBUGREDIR%
reg add "HKCR\Directory\shell\Run%SCRIPTNAME%" /v "Icon" /d "%SystemRoot%\System32\shell32.dll,-154" /f %DEBUGREDIR%
reg add "HKCR\Directory\shell\Run%SCRIPTNAME%\command" /ve /d "cmd.exe /c cd /d \"%%V\" && \"%SCRIPTDIR%%SCRIPTNAME%\" \"%%V\"" /f %DEBUGREDIR%
if !errorlevel! EQU 0 (
	echo %GRE%!PASS.%LNG%!%RES%
) else (
	echo %RED%!FAIL.%LNG%!%RES%
    call :elog .
    echo !ARIGHT.%LNG%!
    call :elog .
    call :maybe_pause

    call :exitn 3
)

goto :eof


:: Remove entry from registry
:remove_reg
set "rreg1.en=This will remove the previously added entry from the right-click menu for folders."
set "rreg1.zh=这将移除之前添加的文件夹右键菜单项。"

set "rreg2.en=Removing the right-click menu entry from the registry... "
set "rreg2.zh=正在从注册表移除右键菜单项... "

call :check_admin

call :elog .
echo %YEL%!rreg1.%LNG%!%RES%
call :elog .
echo !rreg2.%LNG%! >> "%UNRENLOG%"
<nul set /p="!rreg2.%LNG%!"
:: Remove registry key
reg delete "HKCR\Directory\shell\RunUnrenForAll" /f %DEBUGREDIR%
reg delete "HKCR\Directory\shell\Run%SCRIPTNAME%" /f %DEBUGREDIR%
if !errorlevel! EQU 0 (
	echo %GRE%!PASS.%LNG%!%RES%
) else (
	echo %RED%!FAIL.%LNG%!.%RES%
    call :elog .
    echo !ARIGHT.%LNG%!
    call :elog .
    call :maybe_pause

    call :exitn 3
)

goto :eof


:: Check for administrative privileges
:check_admin
set "admright.en=Check Admin right"
set "admright.zh=检查管理员权限"

set "admright2.en=You did not run this script with administrator privileges."
set "admright2.zh=你未以管理员权限运行该脚本。"

set "admright3.en=Restart the script with administrator rights."
set "admright3.zh=请以管理员权限重新启动该脚本。"

call :elog .
call :elog .
echo !admright.%LNG%!... >> "%UNRENLOG%"
<nul set /p="!admright.%LNG%!... "

net session %DEBUGREDIR%
if !errorlevel! EQU 0 (
    echo %GRE%!PASS.%LNG%!%RES%
) else (
	echo %RED%!FAIL.%LNG%!.%RES%
    call :elog .
    echo !admright2.%LNG%!
    echo !admright3.%LNG%!
    call :elog .
    timeout /t 2 >nul
    powershell -Command "Start-Process '%~f0' -ArgumentList '%WORKDIR%' -Verb RunAs"

    goto exitn
)

goto :eof


:: Replace batch file if updated an set relauch if needed
:update_file
set "updating.en=Updating batch file: "
set "updating.zh=正在更新批处理文件： "

set "rupdating.en=Updating the running batch file: "
set "rupdating.zh=正在更新当前运行的批处理文件： "

set "batch_name=%~1"
set "running_batch=%~nx0"

:: If no difference do nothing
fc.exe "%UPD_TDIR%\%batch_name%.bat" "%SCRIPTDIR%%batch_name%.bat" %DEBUGREDIR%
if !errorlevel! EQU 0 (
    goto :eof
)

:: Check if the new batch file is different from the running one
if "!batch_name!.bat" == "!running_batch!" goto special_upd

echo !updating.%LNG%! %YEL%%SCRIPTDIR%%batch_name%.bat %RES%
move /y "%SCRIPTDIR%%batch_name%.bat" "%SCRIPTDIR%%batch_name%.old" %DEBUGREDIR%
if !errorlevel! NEQ 0 (
    echo %RED%!FAIL.%LNG%! %RES%
    call :elog .
    call :maybe_pause

    call :exitn 2
)
copy /y "%UPD_TDIR%\%batch_name%.bat" "%SCRIPTDIR%%batch_name%.bat" %DEBUGREDIR%
if !errorlevel! NEQ 0 (
    echo %RED%!FAIL.%LNG%! %RES%
    call :elog .
    call :maybe_pause

    call :exitn 2
) else (
    echo %GRE%!PASS.%LNG%!%RES%
)

goto :eof

:special_upd
echo !rupdating.%LNG%! %YEL%%SCRIPTDIR%%batch_name%.bat %RES%
copy /y "%SCRIPTDIR%%batch_name%.bat" "%SCRIPTDIR%%batch_name%.old" %DEBUGREDIR%
if !errorlevel! NEQ 0 (
    echo %RED%!FAIL.%LNG%! %RES%
    call :elog .
    call :maybe_pause

    call :exitn 2
)
copy /y "%UPD_TDIR%\%batch_name%.bat" "%SCRIPTDIR%%batch_name%-new.bat" %DEBUGREDIR%
if !errorlevel! NEQ 0 (
    echo %RED%!FAIL.%LNG%! %RES%
    call :elog .
    call :maybe_pause

    call :exitn 2
) else (
    echo %GRE%!PASS.%LNG%!%RES%
)
set "relaunch=1"

goto :eof


:: When it's not unavailable, show message and exit
:unavailable
if "!RENPYVERSION!" == "7" (
    set "unavailable.en=This feature is unavailable in this version."
    set "unavailable.zh=此版本不支持该功能。"
)
if "!RENPYVERSION!" == "8" (
    set "unavailable.en=This feature is unavailable for now, need more coding."
    set "unavailable.zh=该功能暂不可用，需要更多代码实现。"
)

call :elog .
call :elog .
echo !unavailable.%LNG%! >> "%UNRENLOG%"
<nul set /p="%YEL%!unavailable.%LNG%!%RES%"

timeout /t 2 >nul

goto :menu

exit /b


:: Verify if an update is necessary
:check_update
:: This URL should point to a text file containing the latest version link
set "upd_url=https://github.com/Lurmel/UnRen-forall/blob/main/UnRen-link.txt?raw=true"
set "upd_link=UnRen-link"
set "upd_file=UnRen-new"
set "upd_clog=UnRen-Changelog"
set "new_upd=0"
set "relaunch=0"

set "cupd1.en=Checking for updates"
set "cupd1.zh=正在检查更新"

set "cupd2.en=No updates found."
set "cupd2.zh=未发现更新。"

set "cupd3.en=An update is available."
set "cupd3.zh=发现可用更新。"

set "cupd4.en=Downloading the latest version from:"
set "cupd4.zh=正在从以下地址下载最新版本："

set "cupd5.en=Update complete."
set "cupd5.zh=更新完成。"

set "cupd6.en=Error downloading update."
set "cupd6.zh=下载更新时出错。"

set "cupd7.en=Do you want to update now? [y/n] (default: y):"
set "cupd7.zh=现在更新吗？[y/n]（默认：y）："

set "cupd8.en=No download update link found."
set "cupd8.zh=未找到更新下载链接。"

echo !cupd1.%LNG%!... >> "%UNRENLOG%"
<nul set /p="!cupd1.%LNG%!..."
del /f /q "%TEMP%\%upd_link%.tmp" %DEBUGREDIR%
if !debuglevel! EQU 1 echo powershell.exe -nologo -noprofile -noninteractive -command "(New-Object System.Net.WebClient).DownloadFile('!upd_url!', '!TEMP!\!upd_link!.tmp')"
powershell.exe -nologo -noprofile -noninteractive -command "(New-Object System.Net.WebClient).DownloadFile('!upd_url!', '!TEMP!\!upd_link!.tmp')" %DEBUGREDIR%
if not exist "!TEMP!\!upd_link!.tmp" (
    call :elog "%RED% !FAIL.%LNG%! %YEL%!cupd6.%LNG%!%RES%"
    exit /b
) else (
    :: First time
    if not exist "!SCRIPTDIR!!upd_link!.txt" (
        copy nul "!SCRIPTDIR!!upd_link!.txt" %DEBUGREDIR%
    )
    fc.exe "!TEMP!\!upd_link!.tmp" "!SCRIPTDIR!!upd_link!.txt" %DEBUGREDIR%
    if !errorlevel! GEQ 1 (
        call :elog "%YEL% !cupd3.%LNG%!%RES%"

        :: Rename and launch %upd_link%.bat to generate UnRen-Changelog.txt
        copy /y "!TEMP!\!upd_link!.tmp" "!SCRIPTDIR!!upd_link!.bat" %DEBUGREDIR%
        set "forall_url="
        call "!SCRIPTDIR!!upd_link!.bat" %DEBUGREDIR%
        del /f /q "!SCRIPTDIR!!upd_link!.bat" %DEBUGREDIR%
        if not defined forall_url (
            call :elog "%RED% !FAIL.%LNG%! %YEL%!cupd8.%LNG%!%RES%"
            call :elog .
            timeout /t 2 >nul
            goto :eof
        )
        move /y "!SCRIPTDIR!!upd_clog!.txt" "!SCRIPTDIR!!upd_clog!.b64" %DEBUGREDIR%
        if !debuglevel! EQU 1 echo powershell.exe -nologo -noprofile -noninteractive -command "[IO.File]::WriteAllBytes('!SCRIPTDIR!!upd_clog!.tmp', [Convert]::FromBase64String((Get-Content '!SCRIPTDIR!!upd_clog!.b64' -Raw)))"
        powershell.exe -nologo -noprofile -noninteractive -command "[IO.File]::WriteAllBytes('!SCRIPTDIR!!upd_clog!.tmp', [Convert]::FromBase64String((Get-Content '!SCRIPTDIR!!upd_clog!.b64' -Raw)))" %DEBUGREDIR%
        call :elog .
        type "!SCRIPTDIR!!upd_clog!.tmp"
        call :elog .

        set "coption="
        set /p "coption=!cupd7.%LNG%! "
        echo "!coption!" | find /i "n" >nul
        if !errorlevel! EQU 0 goto :eof
        set "new_upd=1"
        del /f /q "!SCRIPTDIR!!upd_clog!.b64" %DEBUGREDIR%
        del /f /q "!SCRIPTDIR!!upd_clog!.tmp" %DEBUGREDIR%
    ) else (
        call :elog "%YEL% !cupd2.%LNG%!%RES%"

        goto :eof
    )
)

call :elog "%YEL%!INCASEOF.%LNG%! %RES%"
call :elog "%MAG%%URL_REF%%RES%"
if !new_upd! EQU 1 (
    call :elog .
    echo !cupd4.%LNG%! %YEL%%forall_url%%RES%... >> "%UNRENLOG%"
    <nul set /p="!cupd4.%LNG%! %YEL%%forall_url%%RES%... "
    if !debuglevel! EQU 1 echo powershell.exe -nologo -noprofile -noninteractive -command "(New-Object System.Net.WebClient).DownloadFile('!forall_url!','!TEMP!\!upd_file!.tmp')"
    powershell.exe -nologo -noprofile -noninteractive -command "(New-Object System.Net.WebClient).DownloadFile('!forall_url!','!TEMP!\!upd_file!.tmp')" %DEBUGREDIR%
    if not exist "!TEMP!\!upd_file!.tmp" (
        call :elog "%RED%!FAIL.%LNG%! %YEL%!cupd6.%LNG%!%RES%"
        call :elog .
        call :maybe_pause_raw

        goto :eof
    ) else (
        echo %GRE%!PASS.%LNG%!%RES%
        move /y "!TEMP!\!upd_file!.tmp" "!TEMP!\!upd_file!.zip" %DEBUGREDIR%
        if not exist "!TEMP!\!upd_file!.zip" (
            call :elog "%RED%!FAIL.%LNG%! %YEL%!cupd6.%LNG%!%RES%"
            call :elog .
            call :maybe_pause_raw

            goto :eof
        ) else (
            if not exist "!UPD_TDIR!" rd /s /q "!UPD_TDIR!" %DEBUGREDIR%
            mkdir "!UPD_TDIR!" %DEBUGREDIR%
            if !debuglevel! EQU 1 echo powershell.exe -nologo -noprofile -noninteractive -command "Expand-Archive -Path '!TEMP!\!upd_file!.zip' -DestinationPath '!UPD_TDIR!' -Force"
            powershell.exe -nologo -noprofile -noninteractive -command "Expand-Archive -Path '!TEMP!\!upd_file!.zip' -DestinationPath '!UPD_TDIR!' -Force" %DEBUGREDIR%
            if !errorlevel! NEQ 0 (
                call :elog "%RED%!FAIL.%LNG%! %YEL%!cupd6.%LNG%!%RES%"
                call :elog .
                call :maybe_pause_raw

                goto :eof
            ) else (
                del /f /q "!TEMP!\!upd_file!.zip" %DEBUGREDIR%
            )
            for %%f in (forall legacy current) do (
                call :update_file "UnRen-%%~f"
            )
            copy /y "!TEMP!\!upd_link!.tmp" "!SCRIPTDIR!!upd_link!.txt" %DEBUGREDIR%
            rd /s /q "!UPD_TDIR!" %DEBUGREDIR%
            if !relaunch! EQU 1 (
                call :elog .
                call :maybe_pause_raw
                call "!SCRIPTDIR!!BASENAME!-new.bat" "!WORKDIR!"

                call :exitn 0
            )
            call :elog .
            echo %YEL%!cupd5.%LNG%!%RES%
            call :elog .
        )
    )
)

goto :eof


:: Check if all files were downloaded successfully
:check_all_files
set "cfile.en=Verification that all files are present"
set "cfile.zh=正在验证所有文件是否齐全"

set "cdwnld.en=Download the missing file from:"
set "cdwnld.zh=请从以下地址下载缺失文件："

echo !cfile.%LNG%!... >> "%UNRENLOG%"
<nul set /p="!cfile.%LNG%!..."
for %%F in (legacy current forall) do (
    if not exist "!SCRIPTDIR!UnRen-%%~F.bat" (
        call :elog "%RED% !FAIL.%LNG%! %YEL%!MISSING.%LNG%! UnRen-%%~F %RES%"
        call :elog "!cdwnld.%LNG%! %RES%"
        call :elog "%MAG%%URL_REF% %RES%"
        call :elog .
        call :maybe_pause

        call :exitn 3
    ) else (
        <nul set /p="."
    )
)

:: Cleaning after an update
set "BASENAMENONEW=%BASENAME:-new=%"
if exist "!SCRIPTDIR!!BASENAMENONEW!-new.bat" (
    if "!SCRIPTNAME!" == "!BASENAMENONEW!-new.bat" (
        copy /y "!SCRIPTDIR!!BASENAMENONEW!-new.bat" "!SCRIPTDIR!!BASENAMENONEW!.bat" %DEBUGREDIR%
    ) else (
        del /f /q "!SCRIPTDIR!!BASENAME!-new.bat" %DEBUGREDIR%
    )
)
del /f /q "%SCRIPTDIR%%BASENAMENONEW%.old" %DEBUGREDIR%

call :elog "%GRE% !PASS.%LNG%!%RES%"

exit /b



:: RenpyBox helper: avoid hangs in headless automation
:maybe_pause
if defined UNREN_NO_PAUSE (
    timeout /t 1 >nul
) else (
    pause>nul|set/p=.      !ANYKEY.%LNG%!
)
exit /b

:maybe_pause_raw
if defined UNREN_NO_PAUSE (
    timeout /t 1 >nul
) else (
    pause
)
exit /b

:: For debugging help
:DisplayVars
set "emsg=%~1"
echo. >> "%UNRENLOG%"
echo "%emsg%" >> "%UNRENLOG%"
echo SCRIPTDIR		 = %SCRIPTDIR% >> "%UNRENLOG%"
echo WORKDIR 		 = %WORKDIR% >> "%UNRENLOG%"
echo PYTHONHOME		 = %PYTHONHOME% >> "%UNRENLOG%"
echo PYNOASSERT		 = [%PYNOASSERT%] >> "%UNRENLOG%"
echo PYTHONHOME		 = %PYTHONHOME% >> "%UNRENLOG%"
echo PYTHONPATH		 = %PYTHONPATH% >> "%UNRENLOG%"
echo PYTHONVERS		 = [%PYTHONVERS%] >> "%UNRENLOG%"
echo RPATOOL-NEW 	 = %RPATOOL-NEW% >> "%UNRENLOG%"
echo RENPYVERSION 	 = [%RENPYVERSION%] >> "%UNRENLOG%"
echo OFFSET			 = [%OFFSET%] >> "%UNRENLOG%"
echo. >> "%UNRENLOG%"

exit /b


:: Define a function to log messages
:elog
:: Display msg (%~1) to console and "%UNRENLOG%"
set "msg=%~1"
if "!msg!" == "." (
    echo.
    if defined UNRENLOG (
       echo. >> "!UNRENLOG!"
    )
) else (
    echo !msg!

    if defined UNRENLOG (
        :: Strip color variables for logging
        set "cleanmsg=!msg!"
        for %%C in (GRY RED GRE YEL MAG CYA RES) do (
            call set "cleanmsg=%%cleanmsg:!%%C!=%%"
        )
        echo !cleanmsg! >> "!UNRENLOG!"
    )
)

exit /b


:: Call :exitn for cleanup only or goto exitn for ending script
:exitn
set "val=%~1"

if !debuglevel! GEQ 1 (
    echo === Variables ===
    set
    echo === Variables ===
)

:: Restore modified configuration and we exit with the appropriate code
chcp %OLD_CP% >nul

:: Restore original console mode
if !debuglevel! EQU 0 (
    mode con: cols=!ORIG_COLS! lines=!ORIG_LINES!

    REM Remove old bug entries
    reg delete "HKCU\Console\MyScript" /f %DEBUGREDIR%
    reg delete "HKCU\Console\UnRen-forall.bat" /f %DEBUGREDIR%
)

if defined val exit !val!

exit /b 0
