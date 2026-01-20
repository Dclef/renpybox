@echo off
:: Get the current code page
for /f "tokens=2 delims=:" %%a in ('chcp') do set "OLD_CP=%%a"
:: Switch to code page 65001 for UTF-8
chcp 65001 >nul
setlocal EnableDelayedExpansion

:: Original Author:
:: UnRen.bat by Sam - https://f95zone.com/members/sam.7899/ & Gideon - https://f95zone.to/members/gideon.21585/
:: https://f95zone.to/threads/unren-bat-v1-0-11d-rpa-extractor-rpyc-decompiler-console-developer-menu-enabler.3083/

:: Modified by VepsrP - https://f95zone.to/members/vepsrp.329951/
:: https://f95zone.to/threads/unrengui-unren-forall-v9-4-unren-powershell-forall-v9-4-unren-old.92717/

:: Purpose:
:: This script is designed to automate the process of extracting and decompiling Ren'Py games.

:: Using:
:: rpatool - https://github.com/Shizmob/rpatool
:: unrpyc - https://github.com/CensoredUsername/unrpyc
:: altrpatool - Modified version of rpatool by JoeLurmel based on the UnRen script by VepsrP.

:: UnRen-legacy.bat - UnRen Script for Ren'Py <= 7
:: heavily modified by (SM) aka JoeLurmel @ f95zone.to
:: This script is licensed under GNU GPL v3 â€” see LICENSE for details

:: DO NOT MODIFY BELOW THIS LINE unless you know what you're doing
:: Define various global names
set "NAME=legacy"
set "VERSION=(v9.7.18a) (translated by dclef)"
title UnRen-%NAME%.bat - %VERSION%
set "URL_REF=https://f95zone.to/threads/unrengui-unren-forall-v9-4-unren-powershell-forall-v9-4-unren-old.92717/post-17110063/"
set "SCRIPTDIR=%~dp0"
set "UPD_TDIR=%TEMP%\UnRenUpdate"
set "SCRIPTNAME=%~nx0"
set "BASENAME=%SCRIPTNAME:.bat=%"
set "UNRENLOG=%TEMP%\UnRen-forall.log"
if exist "!UNRENLOG!" del /f /q "!UNRENLOG!" >nul 2>&1
:: Use wmic for older system or PowerShell for newer ones to get date and time
if exist C:\Windows\System32\wbem\wmic.exe (
    for /f "skip=1 tokens=1" %%a in ('wmic os get LocalDateTime') do (
        set "datetime=%%a"
        goto :dbreak
    )
) else (
    for /f %%a in ('powershell.exe -Command "(Get-CimInstance -ClassName Win32_OperatingSystem).LocalDateTime"') do (
        set "datetime=%%a"
        goto :dbreak
    )
)
:dbreak
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
echo UnRen-%NAME%.bat %VERSION%, started on %formatted_date% at %formatted_time% >> "%UNRENLOG%"
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
    set "CTIME=5"
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

:: Clean retrieval of language code via WMIC or PowerShell
if exist C:\Windows\System32\wbem\wmic.exe (
    for /f "skip=1 tokens=1" %%l in ('wmic os get oslanguage') do (
        set LNGID=%%l
        goto found_lcid
    )
) else (
    for /f %%l in ('powershell.exe -Command "Get-CimInstance -ClassName Win32_OperatingSystem | Select-Object -ExpandProperty OSLanguage"') do (
        set LNGID=%%l
        goto found_lcid
    )
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
echo           %YEL%       Modified by VepsrP @ www.f95zone.to%RES%
echo           %YEL%       Modified by joelurmel @ f95zone.to%RES%
echo           %YEL%       汉化 by dclef https://github.com/Dclef/renpybox
echo.
echo           %YEL%  !INCASEOF.%LNG%!%RES%
echo           %MAG%  %URL_REF%%RES%
echo.
set /a rand=%random% %%17
if !rand! == 0 echo           %GRY%  "Hack the planet!" â€“ Dade Murphy%RES%
if !rand! == 1 echo           %GRY%  "Resistance is futile." â€“ Borg%RES%
if !rand! == 2 echo           %GRY%  "There is no spoon." â€“ Neo%RES%
if !rand! == 3 echo           %GRY%  "I'm in." â€“ Mr. Robot%RES%
if !rand! == 4 echo           %GRY%  "All your base are belong to us." â€“ CATS%RES%
if !rand! == 5 echo           %GRY%  "Would you like to know more?" â€“ Various%RES%
if !rand! == 6 echo           %GRY%  "This message will self-destruct in 5... 4... 3..."%RES%
if !rand! == 7 echo           %GRY%  "If you're reading this, you're already better than 90%% of users..."%RES%
if !rand! == 8 echo           %GRY%  "I'm not a hacker. I'm a code poet."%RES%
if !rand! == 9 echo           %GRY%  "Welcome to the command line. Abandon all GUIs, ye who enter here."%RES%
if !rand! == 10 echo          %GRY%  "rm -rf / â€” because chaos is an art form."%RES%
if !rand! == 11 echo          %GRY%  "This script runs faster than your Wi-Fi on a Monday."%RES%
if !rand! == 12 echo          %GRY%  "The cake is a lie." â€“ Portal%RES%
if !rand! == 13 echo          %GRY%  "I am Groot." â€“ Groot%RES%
if !rand! == 14 echo          %GRY%  "Do or do not. There is no try." â€“ Yoda%RES%
if !rand! == 15 echo          %GRY%  "I know kung fu." â€“ Neo%RES%
if !rand! == 16 echo          %GRY%  "You have been recruited by the Star League to defend the frontier." â€“ The Last Starfighter%RES%
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
    pause>nul|set/p=.      !ANYKEY.%LNG%!

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
for %%C in ("(" ")" "=" ";" "'" "`" "[" "]" "{" "}" "+" "~") do (
    echo "!WORKDIR!" | find "%%~C" >nul && set "HAS_BAD=%%~C"
)

if defined HAS_BAD (
    call :elog .
    call :elog "%RED%'!HAS_BAD!' - !invchars.%LNG%!%RES% !UNACONT.%LNG%!"
    call :elog .
    pause>nul|set/p=.      !ANYKEY.%LNG%!

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
    pause>nul|set/p=.      !ANYKEY.%LNG%!

    call :exitn 3
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
    pause>nul|set/p=.      !ANYKEY.%LNG%!

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
    pause>nul|set/p=.      !ANYKEY.%LNG%!

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

:: Set the PYNOASSERT according to â€œ!PYTHONHOME!Libâ€�.
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
    pause>nul|set/p=.      !ANYKEY.%LNG%!

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
    pause>nul|set/p=.      !ANYKEY.%LNG%!

    call :exitn 3
)

if not exist "!detect_renpy_version_py!" (
    call :elog "%RED%!FAIL.%LNG%!%RES%"
    call :elog .
    call :elog "!renpyvers2.%LNG%!"
    call :elog .
    pause>nul|set/p=.      !ANYKEY.%LNG%!

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

set "renpyvers5.en=You have launched %SCRIPTNAME% but Ren'Py !RENPYVERSION! is found. Please use UnRen-legacy.bat instead."
set "renpyvers5.zh=你启动了 %SCRIPTNAME%，但检测到 Ren'Py !RENPYVERSION!。请改用 UnRen-legacy.bat。"

set "renpyvers6.en=You have launched %SCRIPTNAME% but Ren'Py !RENPYVERSION! is found. Please use UnRen-current.bat instead."
set "renpyvers6.zh=你启动了 %SCRIPTNAME%，但检测到 Ren'Py !RENPYVERSION!。请改用 UnRen-current.bat。"
:: Check to ensure you are using the correct UnRen version
if !RENPYVERSION! GEQ 8 (
    call :elog .
    call :elog "!renpyvers6.%LNG%!"
    call :elog .

    timeout /t 2 /nobreak >nul

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

set "mquest.en=Your choice (1-7,a-l,t,+,- by default [%MDEFS2%]): "
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
echo        6) %GRE%!choice6.%LNG%!%RES%
echo        7) %GRE%!choice7.%LNG%!%RES%
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
set /p "OPTIONS=!mquest.%LNG%!"
if not defined OPTIONS set "OPTIONS=!MDEFS2!"
set "OPTIONS=%OPTIONS: =%"

:: List of valid characters
set "VALID=1234567abctdefghijklt+-x"

:: Dispatch table: OPTION â†’ LABEL
set "ACT.1=extract"
set "ACT.2=decompile"
set "ACT.3=unavailable"
set "ACT.4=decompile"
set "ACT.5=extract"
set "ACT.6=extract"
set "ACT.7=extract"

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
set "ACT.l=replace_mcname"
set "ACT.t=extract_text"

set "ACT.+=add_reg"
set "ACT.-=remove_reg"
set "ACT.x=exitn"

:: Loop through each character in the input
:: First, check for invalid characters
:: Process each character in input, in order
for /L %%I in (0,1,15) do (
    set "OPTION=!OPTIONS:~%%I,1!"
    if "!OPTION!"=="" goto end_process

    :: Check validity
    echo "!VALID!" | findstr /C:"!OPTION!" >nul || (
        echo.
        echo.
        echo %RED%!uchoice.%LNG%! %YEL%!OPTION!%RES%
        timeout /t 2 >nul
        echo.
        goto end_process
    )

    set "LABEL="
    :: Indirection: building ACT.<OPTION> properly
    for %%# in (!OPTION!) do set "LABEL=!ACT.%%#!"

    if defined LABEL (
        if /i "!LABEL!"=="exitn" goto exitn
        call :!LABEL!
    )
)

:end_process
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
    echo IyEvdXNyL2Jpbi9lbnYgcHl0aG9uDQojIC0qLSBjb2Rpbmc6IHV0Zi04IC0qLQ0KDQojIFdyaXR0ZW4gYnkgU00gYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCiMgVmVyc2lvbiAwLjQgLSAyMDI1LTEyLTI2DQoNCmZyb20gX19mdXR1cmVfXyBpbXBvcnQgcHJpbnRfZnVuY3Rpb24NCmltcG9ydCBvcw0KaW1wb3J0IHN5cw0KDQoNCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tDQojIE5vcm1hbGl6ZSBpbnB1dCBwYXRoDQojIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQ0KZGVmIG5vcm1hbGl6ZV9wYXRoKGFyZyk6DQogICAgcCA9IGFyZy5zdHJpcCgpLnN0cmlwKCdcJyInKQ0KICAgIHJldHVybiBwDQoNCg0KaWYgbGVuKHN5cy5hcmd2KSA+IDE6DQogICAgcmF3ID0gc3lzLmFyZ3ZbMV0NCiAgICBnYW1lX2RpciA9IG5vcm1hbGl6ZV9wYXRoKHJhdykNCmVsc2U6DQogICAgZ2FtZV9kaXIgPSBvcy5nZXRjd2QoKQ0KDQpnYW1lX2RpciA9IG9zLnBhdGguYWJzcGF0aChnYW1lX2RpcikNCm9zLmNoZGlyKGdhbWVfZGlyKQ0KDQoNCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tDQojIFRyeSB0byBsb2FkIFJlbidQeSBhcmNoaXZlIGhhbmRsZXJzIHNhZmVseQ0KIyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0NCmRlZiB0cnlfcmVucHlfaGFuZGxlcnMoKToNCiAgICB0cnk6DQogICAgICAgIGltcG9ydCByZW5weS5vYmplY3QNCiAgICAgICAgaW1wb3J0IHJlbnB5LmxvYWRlcg0KDQogICAgICAgIHRyeToNCiAgICAgICAgICAgIGltcG9ydCByZW5weS5lcnJvcg0KICAgICAgICAgICAgaW1wb3J0IHJlbnB5LmNvbmZpZw0KICAgICAgICBleGNlcHQgRXhjZXB0aW9uOg0KICAgICAgICAgICAgcGFzcw0KDQogICAgICAgIHRyeToNCiAgICAgICAgICAgIGFoID0gcmVucHkubG9hZGVyLmFyY2hpdmVfaGFuZGxlcnMNCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoNCiAgICAgICAgICAgIHJldHVybiBOb25lDQoNCiAgICAgICAgaGFuZGxlcnMgPSBnZXRhdHRyKGFoLCAiaGFuZGxlcnMiLCBhaCkNCg0KICAgICAgICBleHRzID0gW10NCiAgICAgICAgdHJ5Og0KICAgICAgICAgICAgZm9yIGggaW4gaGFuZGxlcnM6DQogICAgICAgICAgICAgICAgaWYgaGFzYXR0cihoLCAiZ2V0X3N1cHBvcnRlZF9leHRlbnNpb25zIik6DQogICAgICAgICAgICAgICAgICAgIGV4dHMuZXh0ZW5kKGguZ2V0X3N1cHBvcnRlZF9leHRlbnNpb25zKCkpDQogICAgICAgICAgICAgICAgZWxpZiBoYXNhdHRyKGgsICJnZXRfc3VwcG9ydGVkX2V4dCIpOg0KICAgICAgICAgICAgICAgICAgICBleHRzLmV4dGVuZChoLmdldF9zdXBwb3J0ZWRfZXh0KCkpDQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb246DQogICAgICAgICAgICByZXR1cm4gTm9uZQ0KDQogICAgICAgIGV4dHMgPSBzb3J0ZWQoc2V0KGUgZm9yIGUgaW4gZXh0cyBpZiBpc2luc3RhbmNlKGUsIChzdHIsIGJ5dGVzKSkpKQ0KICAgICAgICByZXR1cm4gZXh0cyBvciBOb25lDQoNCiAgICBleGNlcHQgRXhjZXB0aW9uOg0KICAgICAgICByZXR1cm4gTm9uZQ0KDQoNCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tDQojIERldGVjdCByZWFsIFJQQSBhcmNoaXZlcyBieSByZWFkaW5nIHRoZSBoZWFkZXINCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tDQpkZWYgaXNfcnBhX2ZpbGUocGF0aCk6DQogICAgdHJ5Og0KICAgICAgICB3aXRoIG9wZW4ocGF0aCwgInJiIikgYXMgZjoNCiAgICAgICAgICAgIHNpZyA9IGYucmVhZCg4KQ0KICAgICAgICByZXR1cm4gc2lnLnN0YXJ0c3dpdGgoYiJSUEEtIikNCiAgICBleGNlcHQgRXhjZXB0aW9uOg0KICAgICAgICByZXR1cm4gRmFsc2UNCg0KDQpkZWYgc2Nhbl9wcmVzZW50X2FyY2hpdmVzKGJhc2VfZGlyKToNCiAgICBleHRzID0gc2V0KCkNCg0KICAgIGRlZiBzY2FuKGQpOg0KICAgICAgICB0cnk6DQogICAgICAgICAgICBmb3IgbmFtZSBpbiBvcy5saXN0ZGlyKGQpOg0KICAgICAgICAgICAgICAgIGZ1bGwgPSBvcy5wYXRoLmpvaW4oZCwgbmFtZSkNCiAgICAgICAgICAgICAgICBpZiBub3Qgb3MucGF0aC5pc2ZpbGUoZnVsbCk6DQogICAgICAgICAgICAgICAgICAgIGNvbnRpbnVlDQoNCiAgICAgICAgICAgICAgICBpZiBpc19ycGFfZmlsZShmdWxsKToNCiAgICAgICAgICAgICAgICAgICAgXywgZXh0ID0gb3MucGF0aC5zcGxpdGV4dChuYW1lKQ0KICAgICAgICAgICAgICAgICAgICBpZiBleHQ6DQogICAgICAgICAgICAgICAgICAgICAgICBleHRzLmFkZChleHQubG93ZXIoKSkNCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoNCiAgICAgICAgICAgIHBhc3MNCg0KICAgIHNjYW4oYmFzZV9kaXIpDQoNCiAgICBnYW1lX3N1YiA9IG9zLnBhdGguam9pbihiYXNlX2RpciwgImdhbWUiKQ0KICAgIGlmIG9zLnBhdGguaXNkaXIoZ2FtZV9zdWIpOg0KICAgICAgICBzY2FuKGdhbWVfc3ViKQ0KDQogICAgcmV0dXJuIHNvcnRlZChleHRzKQ0KDQoNCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tDQojIEh5YnJpZCBkZXRlY3Rpb24gc3RyYXRlZ3kNCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tDQpkZWYgZGV0ZWN0X2FyY2hpdmVfZXh0ZW5zaW9ucyhiYXNlX2Rpcik6DQogICAgZXh0cyA9IHRyeV9yZW5weV9oYW5kbGVycygpDQogICAgaWYgZXh0czoNCiAgICAgICAgcmV0dXJuIGV4dHMNCg0KICAgIGV4dHMgPSBzY2FuX3ByZXNlbnRfYXJjaGl2ZXMoYmFzZV9kaXIpDQogICAgaWYgZXh0czoNCiAgICAgICAgcmV0dXJuIGV4dHMNCg0KICAgIHJldHVybiBbIi5ycGEiXQ0KDQoNCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tDQojIE1haW4gZW50cnkgcG9pbnQNCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tDQpkZWYgbWFpbigpOg0KICAgIGV4dHMgPSBkZXRlY3RfYXJjaGl2ZV9leHRlbnNpb25zKGdhbWVfZGlyKQ0KDQogICAgdHJ5Og0KICAgICAgICBvdXQgPSBzeXMuc3Rkb3V0DQogICAgICAgIGlmIGhhc2F0dHIob3V0LCAiYnVmZmVyIik6DQogICAgICAgICAgICBvdXQuYnVmZmVyLndyaXRlKChyZXByKGV4dHMpICsgIlxuIikuZW5jb2RlKCJ1dGYtOCIsICJyZXBsYWNlIikpDQogICAgICAgIGVsc2U6DQogICAgICAgICAgICBwcmludChyZXByKGV4dHMpKQ0KICAgIGV4Y2VwdCBFeGNlcHRpb246DQogICAgICAgIHByaW50KGV4dHMpDQoNCiAgICBzeXMuZXhpdCgwIGlmIGV4dHMgZWxzZSAxKQ0KDQoNCmlmIF9fbmFtZV9fID09ICJfX21haW5fXyI6DQogICAgbWFpbigp
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
%SystemRoot%\System32\choice.exe /C OSJYN /N /D N /T %CTIME%
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
if /i "!extans!" == "n" (
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
%SystemRoot%\System32\choice.exe /C ATS /N /D A /T %CTIME%
if errorlevel 3 (
    set "extans=s"
) else if errorlevel 2 (
    set "extans=a"
) else if errorlevel 1 (
    set "extans=a"
)
set "extans=%extans: =%"
if /i "!extans!" == "s" (
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
        echo IyEvdXNyL2Jpbi9lbnYgcHl0aG9uDQoNCiMgTWFkZSBieSAoU00pIGFrYSBKb2VMdXJtZWwgQCBmOTV6b25lLnRvDQojIFRoaXMgc2NyaXB0IGlzIGxpY2Vuc2VkIHVuZGVyIEdOVSBHUEwgdjMg4oCUIHNlZSBMSUNFTlNFIGZvciBkZXRhaWxzDQoNCmZyb20gX19mdXR1cmVfXyBpbXBvcnQgcHJpbnRfZnVuY3Rpb24NCmltcG9ydCBzeXMNCmltcG9ydCBvcw0KZnJvbSBwYXRobGliIGltcG9ydCBQYXRoDQppbXBvcnQgYXJncGFyc2UNCg0Kc3lzLnBhdGguYXBwZW5kKCcuLicpDQp0cnk6DQogICAgaW1wb3J0IG1haW4gICMgbm9xYTogRjQwMQ0KZXhjZXB0Og0KICAgIHBhc3MNCg0KaW1wb3J0IHJlbnB5Lm9iamVjdCAgIyBub3FhOiBGNDAxDQppbXBvcnQgcmVucHkuY29uZmlnDQppbXBvcnQgcmVucHkubG9hZGVyDQp0cnk6DQogICAgaW1wb3J0IHJlbnB5LnV0aWwgICMgbm9xYTogRjQwMQ0KZXhjZXB0Og0KICAgIHBhc3MNCg0KDQpjbGFzcyBSZW5QeUFyY2hpdmU6DQogICAgZGVmIF9faW5pdF9fKHNlbGYsIGZpbGVfcGF0aCwgaW5kZXg9MCk6DQogICAgICAgIHNlbGYuZmlsZSA9IHN0cihmaWxlX3BhdGgpDQogICAgICAgIHNlbGYuaW5kZXhlcyA9IHt9DQogICAgICAgIHNlbGYubG9hZChzZWxmLmZpbGUsIGluZGV4KQ0KDQogICAgZGVmIGNvbnZlcnRfZmlsZW5hbWUoc2VsZiwgZmlsZW5hbWUpOg0KICAgICAgICBkcml2ZSwgZmlsZW5hbWUgPSBvcy5wYXRoLnNwbGl0ZHJpdmUoDQogICAgICAgICAgICBvcy5wYXRoLm5vcm1wYXRoKGZpbGVuYW1lKS5yZXBsYWNlKG9zLnNlcCwgJy8nKQ0KICAgICAgICApDQogICAgICAgIHJldHVybiBmaWxlbmFtZQ0KDQogICAgZGVmIGxpc3Qoc2VsZik6DQogICAgICAgIHJldHVybiBsaXN0KHNlbGYuaW5kZXhlcykNCg0KICAgIGRlZiByZWFkKHNlbGYsIGZpbGVuYW1lKToNCiAgICAgICAgZmlsZW5hbWUgPSBzZWxmLmNvbnZlcnRfZmlsZW5hbWUoZmlsZW5hbWUpDQogICAgICAgIGlkeCA9IHNlbGYuaW5kZXhlcy5nZXQoZmlsZW5hbWUpDQogICAgICAgIGlmIGZpbGVuYW1lICE9ICcuJyBhbmQgaXNpbnN0YW5jZShpZHgsIGxpc3QpOg0KICAgICAgICAgICAgaWYgaGFzYXR0cihyZW5weS5sb2FkZXIsICJsb2FkX2Zyb21fYXJjaGl2ZSIpOg0KICAgICAgICAgICAgICAgIHN1YmZpbGUgPSByZW5weS5sb2FkZXIubG9hZF9mcm9tX2FyY2hpdmUoZmlsZW5hbWUpDQogICAgICAgICAgICBlbHNlOg0KICAgICAgICAgICAgICAgIHN1YmZpbGUgPSByZW5weS5sb2FkZXIubG9hZF9jb3JlKGZpbGVuYW1lKQ0KICAgICAgICAgICAgcmV0dXJuIHN1YmZpbGUucmVhZCgpDQogICAgICAgIHJldHVybiBOb25lDQoNCiAgICBkZWYgbG9hZChzZWxmLCBmaWxlbmFtZSwgaW5kZXgpOg0KICAgICAgICBzZWxmLmhhbmRsZSA9IG9wZW4oZmlsZW5hbWUsICdyYicpDQoNCiAgICAgICAgYmFzZSA9IG9zLnBhdGguc3BsaXRleHQob3MucGF0aC5iYXNlbmFtZShmaWxlbmFtZSkpWzBdDQoNCiAgICAgICAgaWYgYmFzZSBub3QgaW4gcmVucHkuY29uZmlnLmFyY2hpdmVzOg0KICAgICAgICAgICAgcmVucHkuY29uZmlnLmFyY2hpdmVzLmFwcGVuZChiYXNlKQ0KDQogICAgICAgIGFyY2hpdmVfZGlyID0gb3MucGF0aC5kaXJuYW1lKG9zLnBhdGgucmVhbHBhdGgoZmlsZW5hbWUpKQ0KICAgICAgICByZW5weS5jb25maWcuc2VhcmNocGF0aCA9IFthcmNoaXZlX2Rpcl0NCiAgICAgICAgcmVucHkuY29uZmlnLmJhc2VkaXIgPSBvcy5wYXRoLmRpcm5hbWUocmVucHkuY29uZmlnLnNlYXJjaHBhdGhbMF0pDQogICAgICAgIHJlbnB5LmxvYWRlci5pbmRleF9hcmNoaXZlcygpDQoNCiAgICAgICAgaXRlbXMgPSByZW5weS5sb2FkZXIuYXJjaGl2ZXNbaW5kZXhdWzFdLml0ZW1zKCkNCg0KICAgICAgICBmb3IgZiwgaWR4IGluIGl0ZW1zOg0KICAgICAgICAgICAgc2VsZi5pbmRleGVzW2ZdID0gaWR4DQoNCg0KIyAtLS0gaWRlbnRpY2FsIGhlbHBlciBmdW5jdGlvbnMgKHNhbWUgYXMgUlA4IHZlcnNpb24pIC0tLQ0KIyBkaXNjb3Zlcl9leHRlbnNpb25zKCkNCiMgZGlzY292ZXJfYXJjaGl2ZXMoKQ0KIyBleHRyYWN0X2FyY2hpdmUoKQ0KDQojIChJIGtlZXAgdGhlbSBpZGVudGljYWwgZm9yIHBlcmZlY3QgaGFybW9uaXNhdGlvbikNCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0NCg0KZGVmIGRpc2NvdmVyX2V4dGVuc2lvbnMoKToNCiAgICBleHRzID0gW10NCiAgICBpZiBoYXNhdHRyKHJlbnB5LmxvYWRlciwgImFyY2hpdmVfaGFuZGxlcnMiKToNCiAgICAgICAgZm9yIGhhbmRsZXIgaW4gcmVucHkubG9hZGVyLmFyY2hpdmVfaGFuZGxlcnM6DQogICAgICAgICAgICBpZiBoYXNhdHRyKGhhbmRsZXIsICJnZXRfc3VwcG9ydGVkX2V4dGVuc2lvbnMiKToNCiAgICAgICAgICAgICAgICBleHRzLmV4dGVuZChoYW5kbGVyLmdldF9zdXBwb3J0ZWRfZXh0ZW5zaW9ucygpKQ0KICAgICAgICAgICAgaWYgaGFzYXR0cihoYW5kbGVyLCAiZ2V0X3N1cHBvcnRlZF9leHQiKToNCiAgICAgICAgICAgICAgICBleHRzLmV4dGVuZChoYW5kbGVyLmdldF9zdXBwb3J0ZWRfZXh0KCkpDQogICAgZWxzZToNCiAgICAgICAgZXh0cy5hcHBlbmQoJy5ycGEnKQ0KDQogICAgaWYgJy5ycGMnIG5vdCBpbiBleHRzOg0KICAgICAgICBleHRzLmFwcGVuZCgnLnJwYycpDQoNCiAgICByZXR1cm4gc29ydGVkKHNldChlLmxvd2VyKCkgZm9yIGUgaW4gZXh0cykpDQoNCg0KZGVmIGRpc2NvdmVyX2FyY2hpdmVzKHNlYXJjaF9kaXIsIGV4dGVuc2lvbnMpOg0KICAgIGFyY2hpdmVzID0gW10NCiAgICBmb3Igcm9vdCwgZGlycywgZmlsZXMgaW4gb3Mud2FsayhzdHIoc2VhcmNoX2RpcikpOg0KICAgICAgICBmb3IgZmlsZSBpbiBmaWxlczoNCiAgICAgICAgICAgIHRyeToNCiAgICAgICAgICAgICAgICBiYXNlLCBleHQgPSBmaWxlLnJzcGxpdCgnLicsIDEpDQogICAgICAgICAgICAgICAgZXh0ID0gJy4nICsgZXh0Lmxvd2VyKCkNCiAgICAgICAgICAgICAgICBpZiBleHQgaW4gZXh0ZW5zaW9ucyBhbmQgJyUnIG5vdCBpbiBmaWxlOg0KICAgICAgICAgICAgICAgICAgICBhcmNoaXZlcy5hcHBlbmQoUGF0aChyb290KSAvIGZpbGUpDQogICAgICAgICAgICBleGNlcHQgVmFsdWVFcnJvcjoNCiAgICAgICAgICAgICAgICBjb250aW51ZQ0KICAgIHJldHVybiBhcmNoaXZlcw0KDQoNCmRlZiBleHRyYWN0X2FyY2hpdmUoYXJjaF9wYXRoLCBvdXRwdXQsIGFyY2hpdmVfY2xhc3MpOg0KICAgIHByaW50KGYnICBVbnBhY2tpbmcgInthcmNoX3BhdGh9IicpDQogICAgYXJjaGl2ZSA9IGFyY2hpdmVfY2xhc3MoYXJjaF9wYXRoLCAwKQ0KICAgIGZpbGVzID0gYXJjaGl2ZS5saXN0KCkNCg0KICAgIG91dHB1dC5ta2RpcihwYXJlbnRzPVRydWUsIGV4aXN0X29rPVRydWUpDQoNCiAgICBmb3IgZmlsZW5hbWUgaW4gZmlsZXM6DQogICAgICAgIGNvbnRlbnRzID0gYXJjaGl2ZS5yZWFkKGZpbGVuYW1lKQ0KICAgICAgICBpZiBjb250ZW50cyBpcyBub3QgTm9uZToNCiAgICAgICAgICAgIG91dGZpbGUgPSBvdXRwdXQgLyBmaWxlbmFtZQ0KICAgICAgICAgICAgb3V0ZmlsZS5wYXJlbnQubWtkaXIocGFyZW50cz1UcnVlLCBleGlzdF9vaz1UcnVlKQ0KICAgICAgICAgICAgd2l0aCBvcGVuKG91dGZpbGUsICd3YicpIGFzIGY6DQogICAgICAgICAgICAgICAgZi53cml0ZShjb250ZW50cykNCg0KDQpkZWYgbWFpbigpOg0KICAgIHBhcnNlciA9IGFyZ3BhcnNlLkFyZ3VtZW50UGFyc2VyKCkNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctcicsIGFjdGlvbj0ic3RvcmVfdHJ1ZSIsIGRlc3Q9J3JlbW92ZScpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLXgnLCBkZXN0PSdhcmNoaXZlJywgdHlwZT1zdHIpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLW8nLCBkZXN0PSdvdXRwdXQnLCB0eXBlPXN0ciwgZGVmYXVsdD0nLicpDQogICAgYXJncyA9IHBhcnNlci5wYXJzZV9hcmdzKCkNCg0KICAgIG91dHB1dCA9IFBhdGgoYXJncy5vdXRwdXQpLnJlc29sdmUoKQ0KICAgIGFyY2hpdmVfZmlsdGVyID0gYXJncy5hcmNoaXZlDQogICAgcmVtb3ZlID0gYXJncy5yZW1vdmUNCg0KICAgIGV4dGVuc2lvbnMgPSBkaXNjb3Zlcl9leHRlbnNpb25zKCkNCg0KICAgICMgTW9kZSAteA0KICAgIGlmIGFyY2hpdmVfZmlsdGVyOg0KICAgICAgICB0YXJnZXQgPSBQYXRoKGFyY2hpdmVfZmlsdGVyKS5yZXNvbHZlKCkNCiAgICAgICAgaWYgbm90IHRhcmdldC5leGlzdHMoKToNCiAgICAgICAgICAgIGJhc2VuYW1lID0gb3MucGF0aC5iYXNlbmFtZShhcmNoaXZlX2ZpbHRlcikNCiAgICAgICAgICAgIGZvdW5kID0gTm9uZQ0KICAgICAgICAgICAgZm9yIHJvb3QsIGRpcnMsIGZpbGVzIGluIG9zLndhbGsoJy4nKToNCiAgICAgICAgICAgICAgICBpZiBiYXNlbmFtZSBpbiBmaWxlczoNCiAgICAgICAgICAgICAgICAgICAgZm91bmQgPSBQYXRoKHJvb3QpIC8gYmFzZW5hbWUNCiAgICAgICAgICAgICAgICAgICAgYnJlYWsNCiAgICAgICAgICAgIGlmIGZvdW5kIGlzIE5vbmU6DQogICAgICAgICAgICAgICAgcHJpbnQoZidBcmNoaXZlICJ7YXJjaGl2ZV9maWx0ZXJ9IiBub3QgZm91bmQuJykNCiAgICAgICAgICAgICAgICBzeXMuZXhpdCgxKQ0KICAgICAgICAgICAgdGFyZ2V0ID0gZm91bmQucmVzb2x2ZSgpDQoNCiAgICAgICAgZXh0cmFjdF9hcmNoaXZlKHRhcmdldCwgb3V0cHV0LCBSZW5QeUFyY2hpdmUpDQoNCiAgICAgICAgaWYgcmVtb3ZlOg0KICAgICAgICAgICAgb3MucmVtb3ZlKHN0cih0YXJnZXQpKQ0KICAgICAgICByZXR1cm4NCg0KICAgICMgTW9kZSBkw6lmYXV0DQogICAgYXJjaGl2ZXMgPSBkaXNjb3Zlcl9hcmNoaXZlcyhQYXRoKCcuJyksIGV4dGVuc2lvbnMpDQoNCiAgICBpZiBub3QgYXJjaGl2ZXM6DQogICAgICAgIHByaW50KCJObyBhcmNoaXZlcyBmb3VuZC4iKQ0KICAgICAgICByZXR1cm4NCg0KICAgIGZvciBhcmNoIGluIGFyY2hpdmVzOg0KICAgICAgICBleHRyYWN0X2FyY2hpdmUoYXJjaCwgb3V0cHV0LCBSZW5QeUFyY2hpdmUpDQoNCiAgICBpZiByZW1vdmU6DQogICAgICAgIGZvciBhcmNoIGluIGFyY2hpdmVzOg0KICAgICAgICAgICAgb3MucmVtb3ZlKHN0cihhcmNoKSkNCg0KDQppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOg0KICAgIG1haW4oKQ0K
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
        echo IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMw0KDQojIE1hZGUgYnkgKFNNKSBha2EgSm9lTHVybWVsIEAgZjk1em9uZS50bw0KIyBUaGlzIHNjcmlwdCBpcyBsaWNlbnNlZCB1bmRlciBHTlUgR1BMIHYzIOKAlCBzZWUgTElDRU5TRSBmb3IgZGV0YWlscw0KDQpmcm9tIF9fZnV0dXJlX18gaW1wb3J0IHByaW50X2Z1bmN0aW9uDQppbXBvcnQgc3lzDQppbXBvcnQgb3MNCmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aA0KaW1wb3J0IGFyZ3BhcnNlDQoNCnN5cy5wYXRoLmFwcGVuZCgnLi4nKQ0KdHJ5Og0KICAgIGltcG9ydCBtYWluICAjIG5vcWE6IEY0MDENCmV4Y2VwdDoNCiAgICBwYXNzDQoNCmltcG9ydCByZW5weS5vYmplY3QgICMgbm9xYTogRjQwMQ0KaW1wb3J0IHJlbnB5LmNvbmZpZw0KaW1wb3J0IHJlbnB5LmxvYWRlcg0KdHJ5Og0KICAgIGltcG9ydCByZW5weS51dGlsICAjIG5vcWE6IEY0MDENCmV4Y2VwdDoNCiAgICBwYXNzDQoNCg0KY2xhc3MgUmVuUHlBcmNoaXZlOg0KICAgIGRlZiBfX2luaXRfXyhzZWxmLCBmaWxlX3BhdGgsIGluZGV4PTApOg0KICAgICAgICBzZWxmLmZpbGUgPSBzdHIoZmlsZV9wYXRoKQ0KICAgICAgICBzZWxmLmluZGV4ZXMgPSB7fQ0KICAgICAgICBzZWxmLmxvYWQoc2VsZi5maWxlLCBpbmRleCkNCg0KICAgIGRlZiBjb252ZXJ0X2ZpbGVuYW1lKHNlbGYsIGZpbGVuYW1lKToNCiAgICAgICAgZHJpdmUsIGZpbGVuYW1lID0gb3MucGF0aC5zcGxpdGRyaXZlKA0KICAgICAgICAgICAgb3MucGF0aC5ub3JtcGF0aChmaWxlbmFtZSkucmVwbGFjZShvcy5zZXAsICcvJykNCiAgICAgICAgKQ0KICAgICAgICByZXR1cm4gZmlsZW5hbWUNCg0KICAgIGRlZiBsaXN0KHNlbGYpOg0KICAgICAgICByZXR1cm4gbGlzdChzZWxmLmluZGV4ZXMpDQoNCiAgICBkZWYgcmVhZChzZWxmLCBmaWxlbmFtZSk6DQogICAgICAgIGZpbGVuYW1lID0gc2VsZi5jb252ZXJ0X2ZpbGVuYW1lKGZpbGVuYW1lKQ0KICAgICAgICBpZHggPSBzZWxmLmluZGV4ZXMuZ2V0KGZpbGVuYW1lKQ0KICAgICAgICBpZiBmaWxlbmFtZSAhPSAnLicgYW5kIGlzaW5zdGFuY2UoaWR4LCBsaXN0KToNCiAgICAgICAgICAgIGlmIGhhc2F0dHIocmVucHkubG9hZGVyLCAibG9hZF9mcm9tX2FyY2hpdmUiKToNCiAgICAgICAgICAgICAgICBzdWJmaWxlID0gcmVucHkubG9hZGVyLmxvYWRfZnJvbV9hcmNoaXZlKGZpbGVuYW1lKQ0KICAgICAgICAgICAgZWxzZToNCiAgICAgICAgICAgICAgICBzdWJmaWxlID0gcmVucHkubG9hZGVyLmxvYWRfY29yZShmaWxlbmFtZSkNCiAgICAgICAgICAgIHJldHVybiBzdWJmaWxlLnJlYWQoKQ0KICAgICAgICByZXR1cm4gTm9uZQ0KDQogICAgZGVmIGxvYWQoc2VsZiwgZmlsZW5hbWUsIGluZGV4KToNCiAgICAgICAgYmFzZSA9IG9zLnBhdGguc3BsaXRleHQob3MucGF0aC5iYXNlbmFtZShmaWxlbmFtZSkpWzBdDQoNCiAgICAgICAgaWYgYmFzZSBub3QgaW4gcmVucHkuY29uZmlnLmFyY2hpdmVzOg0KICAgICAgICAgICAgcmVucHkuY29uZmlnLmFyY2hpdmVzLmFwcGVuZChiYXNlKQ0KDQogICAgICAgIGFyY2hpdmVfZGlyID0gb3MucGF0aC5kaXJuYW1lKG9zLnBhdGgucmVhbHBhdGgoZmlsZW5hbWUpKQ0KICAgICAgICByZW5weS5jb25maWcuc2VhcmNocGF0aCA9IFthcmNoaXZlX2Rpcl0NCiAgICAgICAgcmVucHkuY29uZmlnLmJhc2VkaXIgPSBvcy5wYXRoLmRpcm5hbWUocmVucHkuY29uZmlnLnNlYXJjaHBhdGhbMF0pDQogICAgICAgIHJlbnB5LmxvYWRlci5pbmRleF9hcmNoaXZlcygpDQoNCiAgICAgICAgYXJjaGl2ZXNfb2JqID0gcmVucHkubG9hZGVyLmFyY2hpdmVzDQoNCiAgICAgICAgaWYgaXNpbnN0YW5jZShhcmNoaXZlc19vYmosIGRpY3QpOg0KICAgICAgICAgICAgaXRlbXMgPSBhcmNoaXZlc19vYmpbYmFzZV1bMV0uaXRlbXMoKQ0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgaXRlbXMgPSBhcmNoaXZlc19vYmpbaW5kZXhdWzFdLml0ZW1zKCkNCg0KICAgICAgICBmb3IgZiwgaWR4IGluIGl0ZW1zOg0KICAgICAgICAgICAgc2VsZi5pbmRleGVzW2ZdID0gaWR4DQoNCg0KZGVmIGRpc2NvdmVyX2V4dGVuc2lvbnMoKToNCiAgICBleHRzID0gW10NCiAgICBpZiBoYXNhdHRyKHJlbnB5LmxvYWRlciwgImFyY2hpdmVfaGFuZGxlcnMiKToNCiAgICAgICAgZm9yIGhhbmRsZXIgaW4gcmVucHkubG9hZGVyLmFyY2hpdmVfaGFuZGxlcnM6DQogICAgICAgICAgICBpZiBoYXNhdHRyKGhhbmRsZXIsICJnZXRfc3VwcG9ydGVkX2V4dGVuc2lvbnMiKToNCiAgICAgICAgICAgICAgICBleHRzLmV4dGVuZChoYW5kbGVyLmdldF9zdXBwb3J0ZWRfZXh0ZW5zaW9ucygpKQ0KICAgICAgICAgICAgaWYgaGFzYXR0cihoYW5kbGVyLCAiZ2V0X3N1cHBvcnRlZF9leHQiKToNCiAgICAgICAgICAgICAgICBleHRzLmV4dGVuZChoYW5kbGVyLmdldF9zdXBwb3J0ZWRfZXh0KCkpDQogICAgZWxzZToNCiAgICAgICAgZXh0cy5hcHBlbmQoJy5ycGEnKQ0KDQogICAgaWYgJy5ycGMnIG5vdCBpbiBleHRzOg0KICAgICAgICBleHRzLmFwcGVuZCgnLnJwYycpDQoNCiAgICByZXR1cm4gc29ydGVkKHNldChlLmxvd2VyKCkgZm9yIGUgaW4gZXh0cykpDQoNCg0KZGVmIGRpc2NvdmVyX2FyY2hpdmVzKHNlYXJjaF9kaXIsIGV4dGVuc2lvbnMpOg0KICAgIGFyY2hpdmVzID0gW10NCiAgICBmb3Igcm9vdCwgZGlycywgZmlsZXMgaW4gb3Mud2FsayhzdHIoc2VhcmNoX2RpcikpOg0KICAgICAgICBmb3IgZmlsZSBpbiBmaWxlczoNCiAgICAgICAgICAgIHRyeToNCiAgICAgICAgICAgICAgICBiYXNlLCBleHQgPSBmaWxlLnJzcGxpdCgnLicsIDEpDQogICAgICAgICAgICAgICAgZXh0ID0gJy4nICsgZXh0Lmxvd2VyKCkNCiAgICAgICAgICAgICAgICBpZiBleHQgaW4gZXh0ZW5zaW9ucyBhbmQgJyUnIG5vdCBpbiBmaWxlOg0KICAgICAgICAgICAgICAgICAgICBhcmNoaXZlcy5hcHBlbmQoUGF0aChyb290KSAvIGZpbGUpDQogICAgICAgICAgICBleGNlcHQgVmFsdWVFcnJvcjoNCiAgICAgICAgICAgICAgICBjb250aW51ZQ0KICAgIHJldHVybiBhcmNoaXZlcw0KDQoNCmRlZiBleHRyYWN0X2FyY2hpdmUoYXJjaF9wYXRoLCBvdXRwdXQsIGFyY2hpdmVfY2xhc3MpOg0KICAgIHByaW50KGYnICBVbnBhY2tpbmcgInthcmNoX3BhdGh9IicpDQogICAgYXJjaGl2ZSA9IGFyY2hpdmVfY2xhc3MoYXJjaF9wYXRoLCAwKQ0KICAgIGZpbGVzID0gYXJjaGl2ZS5saXN0KCkNCg0KICAgIG91dHB1dC5ta2RpcihwYXJlbnRzPVRydWUsIGV4aXN0X29rPVRydWUpDQoNCiAgICBmb3IgZmlsZW5hbWUgaW4gZmlsZXM6DQogICAgICAgIGNvbnRlbnRzID0gYXJjaGl2ZS5yZWFkKGZpbGVuYW1lKQ0KICAgICAgICBpZiBjb250ZW50cyBpcyBub3QgTm9uZToNCiAgICAgICAgICAgIG91dGZpbGUgPSBvdXRwdXQgLyBmaWxlbmFtZQ0KICAgICAgICAgICAgb3V0ZmlsZS5wYXJlbnQubWtkaXIocGFyZW50cz1UcnVlLCBleGlzdF9vaz1UcnVlKQ0KICAgICAgICAgICAgd2l0aCBvcGVuKG91dGZpbGUsICd3YicpIGFzIGY6DQogICAgICAgICAgICAgICAgZi53cml0ZShjb250ZW50cykNCg0KDQpkZWYgbWFpbigpOg0KICAgIHBhcnNlciA9IGFyZ3BhcnNlLkFyZ3VtZW50UGFyc2VyKCkNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctcicsIGFjdGlvbj0ic3RvcmVfdHJ1ZSIsIGRlc3Q9J3JlbW92ZScpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLXgnLCBkZXN0PSdhcmNoaXZlJywgdHlwZT1zdHIpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLW8nLCBkZXN0PSdvdXRwdXQnLCB0eXBlPXN0ciwgZGVmYXVsdD0nLicpDQogICAgYXJncyA9IHBhcnNlci5wYXJzZV9hcmdzKCkNCg0KICAgIG91dHB1dCA9IFBhdGgoYXJncy5vdXRwdXQpLnJlc29sdmUoKQ0KICAgIGFyY2hpdmVfZmlsdGVyID0gYXJncy5hcmNoaXZlDQogICAgcmVtb3ZlID0gYXJncy5yZW1vdmUNCg0KICAgIGV4dGVuc2lvbnMgPSBkaXNjb3Zlcl9leHRlbnNpb25zKCkNCg0KICAgICMgTW9kZSAteA0KICAgIGlmIGFyY2hpdmVfZmlsdGVyOg0KICAgICAgICB0YXJnZXQgPSBQYXRoKGFyY2hpdmVfZmlsdGVyKS5yZXNvbHZlKCkNCiAgICAgICAgaWYgbm90IHRhcmdldC5leGlzdHMoKToNCiAgICAgICAgICAgIGJhc2VuYW1lID0gb3MucGF0aC5iYXNlbmFtZShhcmNoaXZlX2ZpbHRlcikNCiAgICAgICAgICAgIGZvdW5kID0gTm9uZQ0KICAgICAgICAgICAgZm9yIHJvb3QsIGRpcnMsIGZpbGVzIGluIG9zLndhbGsoJy4nKToNCiAgICAgICAgICAgICAgICBpZiBiYXNlbmFtZSBpbiBmaWxlczoNCiAgICAgICAgICAgICAgICAgICAgZm91bmQgPSBQYXRoKHJvb3QpIC8gYmFzZW5hbWUNCiAgICAgICAgICAgICAgICAgICAgYnJlYWsNCiAgICAgICAgICAgIGlmIGZvdW5kIGlzIE5vbmU6DQogICAgICAgICAgICAgICAgcHJpbnQoZidBcmNoaXZlICJ7YXJjaGl2ZV9maWx0ZXJ9IiBub3QgZm91bmQuJykNCiAgICAgICAgICAgICAgICBzeXMuZXhpdCgxKQ0KICAgICAgICAgICAgdGFyZ2V0ID0gZm91bmQucmVzb2x2ZSgpDQoNCiAgICAgICAgZXh0cmFjdF9hcmNoaXZlKHRhcmdldCwgb3V0cHV0LCBSZW5QeUFyY2hpdmUpDQoNCiAgICAgICAgaWYgcmVtb3ZlOg0KICAgICAgICAgICAgb3MucmVtb3ZlKHN0cih0YXJnZXQpKQ0KICAgICAgICByZXR1cm4NCg0KICAgICMgTW9kZSBkw6lmYXV0DQogICAgYXJjaGl2ZXMgPSBkaXNjb3Zlcl9hcmNoaXZlcyhQYXRoKCcuJyksIGV4dGVuc2lvbnMpDQoNCiAgICBpZiBub3QgYXJjaGl2ZXM6DQogICAgICAgIHByaW50KCJObyBhcmNoaXZlcyBmb3VuZC4iKQ0KICAgICAgICByZXR1cm4NCg0KICAgIGZvciBhcmNoIGluIGFyY2hpdmVzOg0KICAgICAgICBleHRyYWN0X2FyY2hpdmUoYXJjaCwgb3V0cHV0LCBSZW5QeUFyY2hpdmUpDQoNCiAgICBpZiByZW1vdmU6DQogICAgICAgIGZvciBhcmNoIGluIGFyY2hpdmVzOg0KICAgICAgICAgICAgb3MucmVtb3ZlKHN0cihhcmNoKSkNCg0KDQppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOg0KICAgIG1haW4oKQ0K
    )
)
if not exist "!rpatool!.b64" (
    call :elog " %RED%!FAIL.%LNG%!%RES%!extm7.%LNG%! %YEL%!rpatool!.b64%RES%"
    goto :eof
)
if not exist "!altrpatool!.b64" (
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
        if "!extract_all_rpa!" == "n" (
            call :elog .
            set "qmark=?"
            if "!LNG!"=="fr" set "qmark= ?"
            echo    !extm16.%LNG%! !relativePath!!qmark! >> "%UNRENLOG%"
            <nul set /p=.    !extm16.%LNG%! !relativePath!!qmark! !ENTERYN.%LNG%!
            !SystemRoot!\System32\choice.exe /C OSJYN /N /D N /T !CTIME!
            if errorlevel 5 (
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
del /f /q "%rpatool%.tmp" %DEBUGREDIR%
del /f /q "%rpatool%" %DEBUGREDIR%
del /f /q "%altrpatool%.tmp" %DEBUGREDIR%
del /f /q "%altrpatool%" %DEBUGREDIR%
rmdir /Q /S "%WORKDIR%\__pycache__" %DEBUGREDIR%
del /f /q "%detect_archive_py%.tmp" %DEBUGREDIR%
del /f /q "%detect_archive_py%" %DEBUGREDIR%
del /f /q "%detect_rpa_ext_py%.tmp" %DEBUGREDIR%
del /f /q "%detect_rpa_ext_py%" %DEBUGREDIR%

call :elog "!DONE.%LNG%!"
timeout /t 2 /nobreak >nul
call :elog .

if "!OPTION!" == "5" call :decompile
if "!OPTION!" == "6" call :decompile

goto :eof


:: Use unrpa instead of rpatool which offer the ability to extract RPA archives with a different header.
:extract_wkey
call :elog .

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
del /f /q "%unrpycpy%.tmp" %DEBUGREDIR%
del /f /q "%unrpycpy%" %DEBUGREDIR%
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
        echo htVkxRD5vOJEIoojKtkqhu+E83Oxk8xeViEfuvi7NV6EqD+DxgHtRKsUuz+yqQ96cksfY4YHisB6qARSGJsqut1mqKX0nca6T9HdByqOz2BGtM4G3tuOiH2xtqhnw5ji8zkB+bOG81nD+azhPEHDaWsum/IwgYvqBBUFKoU3acJ0Qm/g0nfLempeciW4PFUlxCuUjg7taxQ2mrPuTc6OSIpmlecZtkf5Hs+4nZTFlRkx+6J1TKWGvtSlPR4b1oQu/uFTrxgdsgQi+ZuvyCqX69t9FXlVIyevFzV6VCBMZ3Cgl0s8p8udG/4EK29eUp40IuTP1Wrw0wHOt58rHR27Lfar+h/7amKa0EQM3mhqEkrVvL6t/NOdL8jRaI0p6jovpVSLCCnfUU3FtqLIgrxfoJ190qdcZxMEUJd6TONQ5sLKu71Y1Bi+rZSpJggfT0APrdiMEEpQ+y+lhp7vcWZ9yhhGwQSFireIT02dvfShtE2XJ79emKwPtWXHFA25NVXdp5lxnvTCrPQs+y9kkjntjDO5qWU/jph4EUPpRfZKXIvvSY4caUFqQNBXWz6YOE0fCL98ZGPoB0yBGfX9/N+AKsIcCvjLd0agKKaINddNa1RLxsKChOnyMIw5mZG+1uZUSP/Ahy1VKxqA3yhtfrr+ugh8GeMuStuyhrX4LQHqo7qu/8pk4LjDtA1rAsECqXS9Qh2uZDqjGHrWysICYJ14PfRs5kDHYr+ZMy7DvCqqFQ23v98tPvmS9tm0//ct5h0zxOY9ByPAwnfVB/47H16Nv7Q9WuzdRGsmzkgKl48kOR4I0PPc/O3a9T3ul0azsBhkW5/0d2G/kn3TZdpuxnEOTX5BaufNdcZW5zwgw4Y9fmv4eVBYeK9cPFWjbl86tRgZFXprJNqL8gBOPmCyBVUPuj0Lt2e95BhL7QxD3xC4eQh2v2B8emIVXlfcLmBjJS1WlBlC6Gp577rhuF0JvufICPGqlAqGPnfWHxrz2EO5dJI9L1y+6iZPGGW54SjfrxB6zPz9A28Z8+CXO7KLmgdKKoo/JERCP6xzYecZSzE66pmp8UegkV+NYsWUCw2YYBMFIaivPrtO71PTp9rxczvSne8XbZ2JpkdXrXyqPIW6HaMST6TnVq/Cido9MtM6a8bY2QA2zGBmNgG5M8qz8HDT2Im9rgccmz7GqeC2XKlhoNDgDpiLaKrqAv8YJn2SazJ5OB7JkzZX5EA45QrOCFA3J0Z7LUdE4g7ijJ/QpI7upDckxyuqmdvCpXt9SJhh5RZwVRfAcq55RNVDLxbfcLQnSVMvcp1afPvCZRqRa9opcvIgVUswSnN88WDjaWks9WBNOlSZQb04Oxz0qR7oonYHHicu0p5Vx0Ed+tTvlupgDWRsKhqWsBlEUX3YYcW75TDess8t9DTaNFRNYjCGJqP98PiwumHLUKn4VJxOh1No0UqPoKLIsOKdp4TNp/Q71l+qxP0s2lWdF2WMq9OuKeaC+q/sguq7nY6eFbTPCtpnBe2zgvZpXVCV+vbQ+IpZFoG+f62Kqr+V2naFuPHLemqUt/TkvlyBzLBVatzXpNtAn8qjaly2aNHev+yTr+Qog/P9koH2Y4ZP5hOXdklPzbu+1YDf+LvKQUvBPfBA9dL1/jzaU+WxeslgyuK2emmNdegg3HNUGCLkCnO4E1BoExWCdW72lBu8Fw0Iwfur+hX3+KEBMXPuJhF+5fqibiIKanmItXmvX0jU57ZmYGL0xKIrSoq47hwo9A77854Djk1Q2siiNB7Lu6oiZ1c4eTnBl0ZTL7eV1zEBjJFQTdIxotUTihe9dOTNhVeL3WdyJZaqymhuavY29qopCSq/Klc8jYK+2VQ7HdZH4PSwFdj1drfOlJleAeNTSCAKAjpihb+w4aCaarFfIkFWCreTUxRge7jV6tW+igY6CXY40spByEfUH8dUzTlgKfJ3hs+Xku91gcZvkBtWt+Li7KHVdwoLOmnmH9iUj7SGRcBKJJ6X2ltzHJgIp5uvZtKz9sF+6wD6rLd4uyEVE0hCzW6/WDhTKGkViOaEXWQSTk/hLvTOjVGX7sBzDnv8x74i486VFbA4d3xQR0/gRW97peO/X4joDiuZm8zh2if9Bpq/YbRuAkcHKVkyBUt2Zp1EeMXaEAvMyW4utjfsP1t2YkTxdmQhHQtYC2/QrF/b7TeoNEP4Wl8XxirDK/hxnXKTaPKY2s8bjzjMeEeemnbfW1tWwD0mib78NH6UCTlfXsp3lv744I7hUFcWhu+iJhCvca81JjD7RNdr1JYSb4d9Y66fWGNv7uB4x5AHFVRAwQTMe7MbLnqjBV4br95ZOnywXCoRJJc2k0vm5aWUKSi7do4e9J0dYdzYROcgVYGG0rxLD+U7z5ZQyljYtvGqcnanUxIyqpdFB32pUcR6uINCzaacVZ8QMBmViFZvpzp0kxz+L5wBdYtiEZNHQ0vVHV1z28bxXb8CgZoBQFOw5DhxqhGtpJYfMnVrT5w004oqByIgCWOSUAFSshL7v3c/7g6Lwx1Jye40ebBJEYe9vb29vb29/ZB5tCmwIFoXC2BRzX/G37qYqKydiMWBQEBOKMaFozE8LKS9u/QuTm+kHkZhq15sxcOum/F+zGt/PYitY9jbLobeOFpbxCde9UwryHFfeuCQWpqBoIatRlBtyC08xHtBzc2OzLesGVE+X0dIgRq1ktHq9mLoLJDLYkkx2jIQ16eLtqNCZ0O0nW89rh/ROxHfCLiIxKbx/F4ZQtO3JYXtE9iKE+UPKA8HP6hcElTpBTQTrruk04/ckj1HGRiwHnhVLThfH8iIFSUvaZWT4U4vwUlOroyL6jbdqLkAVeFQGM+y+XmeBfPDYB4LlDcuB21hFiL8SIzZ9vx8u6yuKaGMrtxNZUmIt0kTsVVnVlaZsKyVZirLhu3t+fdqyXVMXCiNpCaCGT+HrPUS+FujTXG2DrX/2Mn7SUtujLrfrGrVn28/QqcHrPtUqMyVpHM2ReoNuxovwmAQxB1M7ZEA7okQxHk1QcV10k6QYru5Z/mdVJSQUrObOrJg2VNirtLirTSYt7kFMVBRBRjSURbIgLk22x0XDiBwJkH/2VifIPRJi6aQ+qwStrnpkm2AP5cwUN43S0rES4SuV+1BgEq4p3791GZRbRWeC2oJzew+Ws/1qrliq2n/8MZDUpl+8cSjfg+6mvHbYklNfbxC6fwa4n+lTGAGHhPNiaY/qlyWK+dgM4etuZlfvSoUP/PLzkEqFXqdJPX7tINmgZ5Utilg0JeczljSRp6MgPXqTPU+2u/IR1puujpfW5WCQIhmb8hJG89td91zrz+KUnbqClQVG4TmIXeNbLFv6Ib7ibOACo9Dlk3putD7wGKZHWfRE9vJe9EGanrHQgVm1o+Cm/ApRxdBM3NIsOy1Iw9KojNE3AeHOlwHxyKADw5bO2xAKrrORiiBXemJ05+lk8fcO5wnZ6d93J6c9dIU5cX5SseNzYumgROiffLTJrNZdWlklGppH0susnIG28x6eLJjA2jreJHwGi2hu8HR0dGL1z+/OiHD/cnLF6//9uaHVy8Pgy+b58+fo9dZH8dOBLYzNITUnFusgkeHOSqwSb6fV9UsZ29LvMehNZyB0lPz5RQJV2UuE80d6BsKhT8zGsH3b3+i5XZoO8shZsn24e3spgdKhcklUOQv67qiEHk2H3MOqY7VeJeSBlwsiwUbvUSUlkqlJ3KFoTuNeotLBFagG7WbMxbSxLscjHPhLSCvcEMmydjG8ZOl7abEi03MN5Y1d92sBd3Mi1PMPKYzBqDyoxM0UPlPTOxGVrLVeVPALrrQbwDw9mztMI3fFc2EDg8jXUdU/el0wzatQbaZ790mGgDVxXQ14PGo2BeBFm6DCi2Hoyu95ZD5GpovuZGF9xqXQNneYE5pN+rC2NkmpChhuvbYfFPYlheB+anvh6egawfo+gbtWmEc8hGvk9oMfauHJomZ8CAw4OFpW412gqaJsLN2QbxG13fBs/TrvWfpN7Qsv033975ND7AubjPDy8vZnTqh5gHV81zQLv0sfUrNOS96uy9lM9iJ87sJMBXJg1w5vlOF3DYFmaqijjumQTa1UE38QLUL7DZQTVq5DsiKFFIsWdl5NdmIo9Z/yZ5O/SuH8h6SZ67ca9sM3GK3G72HOFJotQ85pt3y7jC9rXO7aWGEozBZ81jTqOOD8XlHET2Okg1ko5n7g5KIFFOg04PQDweh71G/B8sF070cHo7Gtpz9yb39Tubs3e0DabX1nL27VQh0fMGkJNdT6xHhWh7PqltQuCjvTPAElKM7YbcXpclB9JWtp6pPwJVUkNQtq1qjI04S2b23BKpFpgsWncaNkaHT6EFTYGB1Ul/IWaaHB2fbcxOrnfLd5H+y3EU/nrWttqD+6lLn/02obERngwTqTZYbm3t245+ye0/bp03dw1e9c+rEEpc6pVjDVGKcHfTQgyztFrnUSxcJPAweDzu/1Tqv8TAYmBzHqulgMOhWM2+mBVpblevYY6QhnCDLKTkEnt/ZnZka5lgHBw8udnlaB9BBEBMTBgN4uUmoiLV6rdedxBb7srpJe1dIB9BjvA9felQ54B8fA8ghiL9RB7a1b3XFjENYpaTbN3ZWrrVsINkzfYfG1pGzZlVvRvsWIDXY/Z1t1kra3yl76Gy1b25YMml/u1zrYKxG4a3btasNAYoTL9g7A23UPi5Uh47U7UCuWWTTwB6HyYYmanbX01RP8YFveM5FuqHnTbP68Jl92Ox29cjOuJ/4xj1oB752op5smqiBjaNI37UFgl/5EJSSwUdhw70HfnJ2OHigODgvc5P9JGMZqM/K3vCXtQTZsBPfj4P/sNz21Mttg3UrS5P2q428to7ZRLtEn4GMuYaTtNU3Sd8UBJNPhiD12ZqB1A+fxwhkJ+ph2PAIo77qIqf7kPeF7/jwdat2DIM3L98ET59+iw4N1zM0+exY1x1txnerWLzqNjUawz33TrKobKuJf9mMcLL6XMthh2SVUfhYRDi8j5bbh8YF3u8F038QRCKuVwu3OdpRyfHurPTm4v8xFY5xdrn/85ySbGD+nj5VqbeAJfcWDd18XbBA8C709clrWNeqIg8SXV+Qg0zDe/p3fMWSFxNMc6B87pBhbk1lIgp7Mqk3ovE4GgbwP3wmruchPw7dT8cLfrzwPF7y46V6rG3imJrZVNqh+xFQ75mPowalKmyUO399+c9fXv948laZhk+jPyEwKmgZZQT4vLiCRYXf0NiPn5gwtKCImUiHvvZLJkTlBT4tqU05zy4L/rMkoJj9FT9hKazwE/b97K6oXXB4jWEjHhh+w+MNwQOc6eOqusVPvIZ2waC0JdjgVyAGdqOi+jBBSITBy2QYq4tLGBpQIjrN9n79fu9fk/Fqfz/b3xuvLi4u8rPT/b0/Ox8MIsVNJd5eTVr6TDCVWh435r7qLVYnpQsn8i7CMC6+O8cjWbO6htVSaBcEmiGctB0pgmDqXoGEq9NeZ3yfNF2uqCYQ1+xQr0poQblMg4vyEh1q0G9Sc7kqoEyJQ7QTvrl1mGPB1UVWogZ1fV1X6JJ5W61yCpPC/NdXhQpG3eWKh+h/2XBdExKYzaquyZUK/qYBxwnJtQLvu7JajxGHwC4sKOmoQ8HyuNTMlTm8TYQA6vZpETsuux1yXYuF+MsmoetLNY+OrM5NN8V627Wjrbmz5FbWnaW+aZzhQ6aWjT5PhdpzbjNNnQu8LwOaXWZYBLZBpkHFNscbIaBuoypOUivW+FUr30VizyWZr7irppsJiJyiisXlEtOX032/y63YOB/zF+G0qO98eYF1dB4lZ9XSm1Ne9AaLyAiQpxqrs7RbHqrkyptDdgan46hu2veYU/iPTBO/f0KbN0elbIcDrnL8jxlTHEt68vqn71+9SlJqFQuEh6aPxPYCorZb9Cwmgl5JcT/r+bzyI4qHNc4wSPGimtl3srtBoeKhyAWt9ZLmarO4fnWxZNjd8jZU1ebNLoowt3UYj5tHH2BzWySPQrdXP47k+UjORItsSz43h+Cit/HlieHWD0Ko1jMpfRRop1Ebuk5BgS6Fk7Z3unHv4EeCNdA5ybrrNog58Sa3yaupaoZX9sH5YzJ2XdQVXvxjCGuRJ3K+8nJ5SMkz6fVGvA+HAdB2pyCZ0UHB+LXCKC5hY0Tln8vYc6hXFEX8nv6IIhTeIsABN5dGXRiVTbMqOuvHpoH/Cp6nsg7DMF4dx8dvjrLnYXx8GIbJ8YcIvkRRcpykA3h0NDr993h8lsCPqBYlA2g9ypIEXk22vO+nmf7EnqS/+ALDtVUSo/4MN8JXBLS/WaV2UywgD3sZrJzfPkYggbUlw+EyqHugzHXhb+FhEH7E8+IpfjvDbzF+S8KPPemFCzrZQmxMdbi9LTk786nvfFqMNvtqmWVMWdc6HbZgTqdndq444/roGALhMvJg7PHXMyj0DkCta407T0l3edOUcWYCM/OJu2gmRgE6vP36xOhNCTIWexJ7uSozOXgvZhX6LKFQWAYx7uRUgg7rRebBrJL7rWPNRfEYRN5echyP80fj9HicDz6MU/iOjH9avDw73Xt0dox/H0fS862q8zW4daw4/V6F2ixg4sFzA8xgtYAze8M5h4ET9TEkldejwai/ndPL6nfCvXtVTI8FvEP3tNG9xObVpH4kIrTBOD1dszdUrgt0ISq86ohfktIMIXBtqdRYDFsA5S1aFMU0YQwwXpLz2VQp//cQH/1AUtqqDGz2alPBm3gA5FqYbEtdqjwQDUD7D2wayyK39J3Ys/J2XEtbrRTvc7FQvSCQ9ZKthuoWT84yy3j5dVOCgk0TyOkmWPrDllsthyq2RHruEyNycuty6RRHet2O08ifZEoMymdtVdpGgd6SnKIkDX7gWrMNhn9Ms1ruQpsJs170tdshJv4ATeZitaBEI+wSz8EGwLpLzMQpkrDKoT9A4joSgO7SoRnj2JddrbXor7BjpxCjORcr23Xss9c2NcJFTB6bUw4e5FesUMNdVqDPC1wspEiXs6yeUcQQHxvVaVEtMnIQ5biDTiT8ss7KGa7F8aJTIbWxwq81VfPuPSXJFEuaWovAyMUjqaFblWy9moVzS6fABWQFXU2XMcNfYsPY2KXehS2wGHlDtXXRdubgEiJAaywUANRwDw2CiavYMTAJoahsqiLTiwpN4jD1XpbRzXqIi97b8TjRDhCIoxgtVKf432+RZ4kwPd0YrMVvU98JdnuG/31U2a5Md+sw2fusmCAH7fqCbtEBHXT6xZnr4s0L1LET2e7SWyh9eOiIxrePPgSPPoDgxn25WjSruZb5Q3lSBd7G4Lvmbn5ezfo5V5EwX4wMw3Tx2MzgZz19kOXPzm7wD9DFdUIiTsKIDvh4uq+Cb9KDZ1Tp28gVifFCiFIA1LdMSY941AAwiI+M4+QgUt9waB/HwTMMAR7vESuAcz4rUmUi+wWI9qJaoP/JYqtE5GSNnxA8tBeQQRezsLmd39n63c9iIaBQujDzl21NMPDJDGT+EnGo7RQNlYONCwedz0wFgHJSG2otdiC6nOg70xuBSZCcyk0U9dhL4k4mWAMB43w42AmWWRB50n6+r9GuGJv4Hno14XDOPfrn1ltEPyV384WjGweFJLPzLxghVSbuW3DWCMxyyZrlxD4c0EDd/DDPrnUQ7vvD4P3pIeIJyL8XdOEMRu+HEiC2S3b8yBs8xOLEG+MY4WniSOajPqIIs0VDk9RwgCL3Oq6tbwR1bVlQ36AgOCmnS4wv4bVGaVlATb8qluXUlKTE6FtKRPSdqEyZZ8ssodhm9ZtO4iSalNYyFcEgQ759bKecTCyzCsN4Y9QYHaGAp/gKBuDhcxePd37XFe4ZJo5VKcLqqEXlQ1HxJXuofV1nzPk6UPMltaDTGb+vFAFOIW+uz5QwBUCi5mjaLTravZ4Lx2O07KDpKUyczxf8fOF5HKrXQ/EcdHyYVDz0Hx+NgiTgC0D8aKwLT3gN40cx5/8YEfRl6H2b3aWmtATnnBAZ3FViHbyt69abvZFpGFWtrNurStyw3IioTnzUj5BR1Z7MYVJWfGpPmM7Lb4CuxGq3ta8T3K2qOqvvJs7uXI+9Hes75u+khbmDjwucSZS8wKXFqVUnvCfgTjIrObvJqrHdXPoszATNlkk7WkSUUkdj9F82XRoNnOfOif+i0q1Dgxzs93C6g01
        echo XJKLHoy+7/uVKUVY+sqmT1qEDRtiS2vHUiV2Zd8krmMnO574bWNgKRJ+mB2nwlxUfFNEwr4TFdV1RwF2uT+m7wbzIFo2+WkLjPSa1ogZaJlyX03ewpyoTlh4JUKYplv2wAaaGkwgC301ctiUdPGtLO53IpWXciDd07fSekgAE/xFLlsuriXMM+MQ7CnrNEl6BcNf4Lw==
    )

    set "OFFSET=--init-offset"
) else (
    REM unrpyc by CensoredUsername
    REM	https://github.com/CensoredUsername/unrpyc
    REM __title__ = "Unrpyc Master for Ren'Py v8"
    REM __version__ = 'v2.0.2'
    REM Modified to include PR# 248, 266 + Inceton.
    >"!decompcab!.tmp" (
        echo TVNDRgAAAAAhqQAAAAAAACwAAAAAAAAAAwEBAAsAAACqNwAAcQEAAAYAAQChKgAAAAAAAAAAIVzLoyAAZGVvYmZ1c2NhdGUucHkAU1IAAKEqAAAAACNcpwogAHVucnB5Yy5weQCfiAAA9HwAAAAAI1w5CyAAX19pbml0X18ucHkAGS8AAJMFAQAAACNckAkgAGFzdGR1bXAucHkAtyEAAKw0AQAAACpbG74gAGF0bGRlY29tcGlsZXIucHkA/XQAAGNWAQAAACpbG74gAG1hZ2ljLnB5ABQ0AABgywEAAAAhXAuuIAByZW5weWNvbXBhdC5weQD8ZQAAdP8BAAAAIVySniAAc2wyZGVjb21waWxlci5weQBkFQAAcGUCAAAAKlsbviAAdGVzdGNhc2VkZWNvbXBpbGVyLnB5AJwVAADUegIAAAAqWxu+IAB0cmFuc2xhdGUucHkAS1cAAHCQAgAAACNcNQogAHV0aWwucHkAQcR6fzsmAIBDS+w8bVPbRrff/Su2Zu7YvjUCOylNmdJeB0zjpwS4BprmSTMeWVrbKrLkRysBTib//Z6XXWklGYekM/dTaFL0snv2vO85Z4+yI47j1ToJ5otUtL2O6O/3e7vwv+fiWEYqTqR/o2QSuUvZ2GnsiEuZLAOlgjgSgRILmcjpWswTN0ql3xWzREoRz4S3cJO57Io0Fm60FiuZKJgQT1M3iIJoLlzhwaIADsamCwCk4ll67yYShvvCVSr2AhcgCj/2sqWMUjfFFWdBKJVopwspmld6RrNDy/jSDQFeEAl8a16K+yBdxFkqEqnSJPAQShcGeWHmIx7mdRgsA70GTiduKAAHgDMFdCC2XbGM/WCGvyURt8qmYaAWXeEHCHyapfBQ4UMPOAfXQMtenAglQ0QNYASAPVFcYEijcJ0VMjbVrFL45H4RL8vUBIjTLEsiWFbSLD8G1tGqf0svxSc4YRaHYXyPBHpx5AdIlzok8V3DW3ca30kiiaUexSlgzHigLFaFiPUrtXDDUEyl5hwsHUQADB8aqhLEQaWgB4EbilWc0KJVah1G4tVQXF2cXr8ZjIdidCUuxxd/jE6GJ6I5uIL7Zle8GV2/uri5FjBiPDi/fisuTsXg/K34fXR+0hXDPy/Hw6srcTEGYKPXl2ejITwdnR+f3ZyMzn8TL2Hm+cW1OBu9Hl0D2OsLWlIDGw2vENzr4fj4FdwOXo7ORtdvuwDqdHR9jnBPL8ZiIC4H4+vR8c3ZYCwub8aXF1dDQOEEAJ+Pzk/HsM7w9fD82oF14ZkY/gE34urV4OwMFwNogxugYYxYiuOLy7fj0W+vrsWri7OTITx8OQTsBi/PhrwYkHZ8Nhi97oqTwevBb0OadQFwkEIcyDiKN6+G+BDXHMCf4+vRxTkSc3xxfj2G2y7QOr7OJ78ZXQ27YjAeXSFbTscXr5FMZCzMuSAwMPN8yHCQ6WXZwBC8v7ka5iDFyXBwBtCucDITaoY7DfhBFQMdQktF5UODV7kVg+KApYBhz1FnwLLA1uc4IhW3UXyPHmKWKU8bovQWUfCfDEaCagJgFS+lWLreIohksiZdB6tG/VoaMA4iMEhgCMxOMzIZsUpkmq6FCparUDpoAolsAVAwe+kigHswolSuFHqPLFq53i2aDjmC1doDa0qWLoDeEePLt8d9BOlGwsVV7qR+C6Phfx4810SLZRamASyIFEt3CW4rkTOZJGy3Lri8ME5VR9vkLEgAE8QCwcsH4BI4K40FjgTXCt4gSLvgFgJvgaP8OJICvC/+0namJ8aJchiwkmSlc8TUFdMwnhKmQL4E1yfBatMA3n8Ig+muFy+BVQqlAub8d8a8FYl7TxgAwDaLQILT9BX41BAXp0EIQBgAJL0YaJqjBNC/5lSEMpqnC001uOJUC2Mfl1zCbqMlAfT40kvWq5wJvpu67N6B0QjLYU2TEaCSrWBGKtEpTSXOCN01OFIEM3WVPHjeRTHAi10J6rUCr7uQD7sy8mLcBrpl+mmPkKmHLHwjxQK0D8RIrhG4zXxJ1hovRSLwFpKVJiA5rIF21EXQOHCEGgVzB3ulHy/NHaCVeam5QzwaJGkPXLj02Inql8dxBiaUNHgAsAfwBTNLnERGoKdwB5zRY1eBdxvKiXJnchLGrq/QMIa5dgjcTdggYD+JvNxZt2fx9O8u8TeKO2L3F6AOrIzltQbcAyD4DzfM5DBJQGQ5vW4QNoZ/khNCp3ck3r1v+HJWaGR71jlsCPgpRjnuagXigzf0AswUtjYxQ1RPWPhbUSXMuoYtiGwZVwZ3juZhowkeW9/pEXAdACXRihV13cIwJFQxmrIKfKlNduGitQMA6TuNk+Hx+O1lmVTf4JyTWox6lFT0V74v5hBf7aqV9IJZ4AkPdAxEbNwAmNNebg5wE8ZzGISWQ1KFfRtDruqcveoMWOx/cnHYwpmguCfo69ozlr3Gv9ls0u8rNN18Kro8cCbk4rUz0WEXvM5g97e8ZgnMzFFS3rb3mQdk0EfwENyj3+ZnICd8/O6wt/9efHckpq3x8PzyLTje436LcSL2VdSw3RyBKYNvhRDoFUCTSbPToNGrWFH4Awv19ukJuV24/fiJR4A7BTrycd+LXl/8fISOqo2odIpVcWbgoydxE/DD7MoAEpuwwztHu/nzaDSCEIboMGAPS/Dfd3KYQHB7I9yOODoS7f2uwD8WEvgzBY7dNmwYNBVga5x+2Yj/Zs69TOJbGbF3hi06WRvW5cx6xwi+B1LbZRzzcQV5wOc+PZahktskZq+7IJlpRmYY0zeMOtB7CENRxQibbTBvIg4jaFLgGzA1geVUvbetkSRGYw/L/Hy/3XBCOXe99dNNBy2F52wyEkMzaH9vG61nNgTYhmEvVtkKnb8SPQJhyN9udvQQxF6spUfgXuTwLoO7ImsTi/bBkyverByJ2DwdTz/wSZomSnI5csDAxKBrSWM731lrYD+PvoT3sEsrHa3Bzj5H377AsBJdKqZA4PeXkB/xY62YbgJ7DHj9pzuzqvPZ3+xrnh2InzeZqtsVU8g6wYtAJAJpdVdAkAKZZrDZ3fDPNqfz7KDsdFx0Lz0i2MfLPl3O8XKfLqcwycNbucn3bLT7xpPsHrbr0I9aENAGmOprFuemWnjnb875m3P+584Z3cvXu4hZ5t2CK8Ayke0Pcl6YgssqDqIUtFVixgkBETPZVQEMhiGUMyCfpjElXQQvSMnQMG0FqOJe8rAwjm8Jjzs3BGfJidUii24h4QswwgnXX+yIiGMToweKQ1aejDE8ii9BX9jOFVPsip6lnSYuCygq23/48UVZc9GdB1EmS3rfNlP+W/R/OACB8T1a2fuO+C/xrEfAPgepgryJpANNm+YNkWQoyjUe9bI8vVittOflkB7Z+ApnYfmHLftgiZTSAjkBdFexpV/INfC4zjZj+rdW63xDJW8qozibL/Q6lf2UH5JhoXDfYzaQZyx2/kImQ0Rj3RNyK41IiV8a6NfFCEVi9igOkJ5vQAHYhLS6YdgmpZ023akH0wYvj0+Gp/u9/rPnPxz8+OKnZqHXNN25lWvV7nQ24/AYcbg+EefLdhMQapYoG9Iv1IgvIoxrAV9A23wR/H0bLqN49Z9Epdnd/cP6A9P726vRv34/e31+cfm/46vrmz/e/Pn23wUPvt87+itqlhTStvd/wBcmwZkePNfMqUn9K3nDJZoJl2g+x6Jf0A/1OVgJIIraf3ix/8/Ii+S99p4lyWdRgBe6ctTsOFQ2ku1W6IJ591pfQrmhwqzESz0+Vt/r8Y8yLog8mcbR54wW2AHE/dj/ofdDv/ei14eL3k/w37Nerw//HfQOSjnAJAxgP4JoBX5ZMmaHhDUs3Hj8NkAtXqhFNpuFEjDyA08qM7u8uxDgTqcOjie3K0CscfIOAn4b+rt93F4Q8KOTSCe6BjMfB8gH1BEZZUuJ1eja3EpYVl71XRkSRl5BzUSwENV+lxOLu2Cx1Zbhvf8i00Gxu0pJ2NMCNYkwqwp16aYS2gwiN1x/kFx7zQOWGGN/BWYWmuo2RtgxHx8hirqOEoE75zjjJAZOk91RdQfzTHeNx3oUKOFpki7wTnDDgyhVTbgcjXVaqY/cdDUZHkGcc4+VK0pzpiGFUAqPzDAgQlBcysazIhozgq0x84BPsyzsal4oWi+LrIq1WdtUwk1BPU7cOdeei6hpQ9ikA7s8cOrt9593KuOM9fLYz9WodkyFnVP9Lh2RxUuJ5cgl41wJKxvWXBBxtqRCtp4NSHAVM1AcodIxhB0kYg5tWdT9ZFOBbQNFG2OhEm/rIZEB/+RYqBbBVDcm0TyxI5mCpZo5kBBnmGekMsHzHD4iclVeSEEt5uKsnSJp07Gp2ZSlAmPRhfBKHdhMnh+U0d8RvX02aqMp34vn4Hh+0g+19okUNbriPAgDO3Y7pcJpDGq/iJPURvdr036tkb39w+eY51t65KPxWpmLLsPAX28B28fMzUI8HI9aq7WYy4jcoc/n7L/a7EHBtK2iwRQvnx9UCwhtjW85Qa4UFGrutcYhruHqIx9Q8yn7uS5Fu3zATWTgoR9nb4CyDH31q81NrefTzhar8DaZRUUtcmVHa/e+FPkg4pOZAH0dWTzpKievzf9XG6zjSulv7ylVOUsPbLwcPH5DqtpNp/l5wT66nj7g4WOrz1ow7YIov4kLwcWsy/b3YIIeP3DnEeRrFCA0B2kql/ocEftEzBmzJEEcNnUmbNiJk5RMTeqMW2JRHwBci+OrLamkVjLr8KsL+XRVUNY5Giwrqy4noNMnMdvluFhMARZYc/OvJp2J6VA4vgftmMoZnp2u1s+cXr+LNUzYZjPwuN4iaXcEnvFWgNNGEmeJgF0mWGZLmIvtJSUiDBvzw6uWPr1fi485ac5kgs1Bk8kn7X8PxUdctbffcf6Og6gtHTeZq86nlkV/yft+1VocEygLaEmIjuv7Oma1U4f8vVXtrq7cHISh3aagj/zETWTCFY0PSbnZ2ZKlQwLGPMgX6RT42K5FdSr1/jpWVwVGqyT2Mw+7o4LZDCKliPqbwJMrR1zzyTQe+scUR+Z1AK2TeW6Bmp07RKoA1XizUa+xFrpMVRf9Po6Y5OkbB3uPO6at+l6nOOee1qCn6Q8IB2f7nVotBt44YTx/RCwbPBfR2Wh8pZbYnsbSlKdqCfm4rezd4Oy0L9PdD+VjB/3wZwhl7CgVi0jgLLBJACPwtUx/fZL8AXqtyeBx0W9Ia6g0DXHuFqlahZhC6wy9xR6hKaMziELgkAQDjro7wMKslBjm+TRaQHFcX0bDKgzkR/wGnkm3SxOsFB/kghZ3WIt3a9XBzSyohC2mElAdssF/rmSCYRL2WAk6v8LU6GNOQeFLKz60fspTx8o65KhbhgnksdwvFvCXjIGW5crKl1nCznd7mUr2pkG0J6M72KfSRRw9w86HauNqr8+Nq2+zJBC/O+LKW0AcG2HyUO1l7Yp/QRi99KZuEn3ra/3W1/qtr/VbX+u2vtbJJA1S2Osm4IObNxFWzprwEAt5oA/0uHXXd/adfgseZ0nIIxdpulKHe3tzsMds6kAOs1f1RHuZhpa3C4KLWbmJkuZ+joWdje2Caq3MJUakcgo+rd5KCMnnAtM5/eISbhuNfGvXqYDykgD8MyYF2EjJzblUJL0LkjhaUm2NDzi5szWJMf7WhSjKRe4gBMrrHztoOlM6RgZHrFt1YV/E09FiqPYSC1gwry5i2gIOA7sqYZdJ2a2exd6thjuVnqvHhO6HAGZQ7AH3ShzvIgsk+lqCi6UO8gVg42T70ZzLgMSYGiHMIFyrKy7jOAQHucomtMHDZZZgqD3RE3hT+ADhD3fdcFjPECYVyPQOwWJWqSOiEQ0dFml6LkFnBeleOoFxbdwYjkDKjkp98Oe8b9LrdhNdXpUC8ORZKGsSKWTxnbjE0TLfJUwtOF1gPg0yt4+MmqbJlLYQ3XB7H7DPVOCKHdixdUS1I14DgXwa7iZciK2iZwrAESDAwQPEuDmL2/WDmp6BjTNYIT0XZL+SMZYLUA1W6758kKYPOQWp5ZDLArLBU9zJx8chXJKwi7emgk5VdE6Qwfczo3ZzRi2RXL0PVAh1EB6DdkpQi/wO0JtMAHI6mbRhI511hZ4u1REGjLibB7jnBB9kYj3BTIhuOxsi6RJ4QHqlQWPfLEyHOJiNjs+CAfJRr1OtOowicUkhlnhG7dlimgVhuosd7QCvk1fgXbS+NQOFcLJbAZN3qcsHF3sW4IFL7kVLEnb0JQQnHmypceggrs6m0B/XLGPfKVPphbGSROZnGUKR5ZNGTib4sUKiRbO5rIVvarMeLHmC/U7SNfaa49Udli/p0XTj8tpzFF3dxZM8jaw2fht344J3yJarLrqQSIUbRm5qEW/X0rduKaNDkMUjHlBLFDb96Bm+xG8wJhyv9zGjZVs75lT8sLHRDjp2bkoHkGBikLXDdSQpfCT3Vxw4whzM6vPDJysN1kcpEKhLk36yC4o9cuZ+GQqVTE2FxAIA0V9K0f89f+MBTuce6xeRx7mlBWfHFF1sKiiFIj/PT9q67o51cZFF8mEFfAKTKJBE8JQd+RUw8e1hzmbytOwzMBzWAayui80y2Eork6eur3smD2kyfhQS6S913Ijak8h302c5aOBcdS+OCSvw1G2wOrSQseAhAfh6halORuUQF7/DAQNRtKPDZobt9iWoJARmNoROxLGmLQdteHeYMPIGjqvex8ktZnjY1Bity8B4qC1R1DesAbGJ4jmcO7ddaU2dTFZrhhZglIQ9mvJWbe94XQVldIp+l+dyyU5PJkyrkw369Ls8mdik59J1da7hI/3Obe+l649Bmnk1pp1fFYfH+SOtghj1UYnIM52bpCPF91HlL6HM5sluDfOFy1G5YD9B2U1Q9O0got/VAv6OGEsM6Qj8XQ/Dl7t+oSw7+IxzZswe6WzZLX+CBGizG+JvnvRBA2oefcJE1RQdeqL7NGD7GmxxMDF1VVCQaDX+me+9CpuhT540TAWRfXEiiwUcyz9pqu1zWbyfcGPjUWn4u8Mf9rmxLVB0zj8B2o/EqRsqWStt50pLkPhcZtoszlKbJe/KH8WYk8FAkWiBeRKjXYiu1QIFjgS69OWb+IO5bn2Cln8kVjp8tki1sSrOkWxKrhOj2+Uy046lZjX213tb8+87Sj2Buo2YTvjdO8n2SqdpFgOLYx52xBPuUDU9kb2u2H841T+VvRtHfrbnmM9oS0LNuwlFtfe4WkckXI5qbZIbOo0rHw+UqUFdRy2xuVCHWOFRIZrHSukb44HmGzdBUzsUw2KLrOx1hFQuTkeMKDYEZig6J0Whb+heY/DGXurduAvYdqZSRqa132lWGFppha63f+rO46oRcuOxqHUeW3zvmUZohnO48fihcN2tYjeunWFhWbTmqesNE8VRQ+52uPBFzIXHVNPPN8p8G3f0F6cFB+uMnjW3cFWcFnMPxcfCd32y+W15Ac3a3vsNX5tYw6on3ObV5xqknsrdp3C23IZS31VoOzGN3hwHap12xJAbfiynmrOuzOFZk0quAX9pmxppfCXLWcRFjAMhr+/rfY5icFT4eGbaPH7kPc7sHZYzxs7pTbF7IYiC57ryhZHaQbMCBx25aP7YbDQ+6zMKX+FiuxoeY83orEIF80g34VN9yima1ZDpRa/KdG0IqziMWcvG86O++ES1EBnG9119LkbguQiXj8Y0W6b4iXP0F4NuNWo+yAx+4eDnqkWdhCsk/GE1bp7cf4DHCNjCRO6VCstB/s1i1dU1OdSzYXIZixIXRxgzm2w7iytbT/lIk+IxoJD6J/IgDE8bF25C3VblgMwEdRcQC6uyN8Hv6LHCaKKa3PHgKB1HgZgGV9eO6ecr1kGnj7tMl76oZ0blBaYlKDudF0CErz/BeuQfCGDIwxAPJwLaSRCDx9KY8ucT/C2GjshioK/dSqatDk7VT0t9YgXuZQ/vUquslaw7eX9KLcjdcrDGYJ4SKdtSxQi2YTqCOeXnnlD6qJkm8qGXntwVMSjvfRKk8ogCIVv25gnm//p60z5MxQSqyJgJUQwOA7xhUsDkckRsF7Am8WwGjnoLZBVO+GNmOqDMq13at10UmSO+5har0hO0MpIq+gxB/QBop/kHxkDXoXU+jQxvOelD2tJRKDqzEt8clc1mwQP1tLXIEbU6dQjw/OkQlo+BWDKM2JpMGUMJGlI
        echo 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
        echo 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
        echo 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
        echo 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
        echo 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
        echo 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
        echo AEEfYmTz9NNokp+UOYQLec+p0aCmzezNPG9pqpyKbP1TaldltxrkbHwqBt0xCW51LFTL8vVnkWdd9gCOktUs7WvE9ioyiqtNlNnd67H3o7lffGfdLOxgY8LnPKpWcLKouy2kNUCYx7vxNGBUtSsavteusvBRNC0idvRAqKY0BtiKNNZo1Rymjon/stStm4dfsRWL86AYr/VqgfAAZlcJTNWktm5OHHT2gFDI7XjqRO7IjPJqzGTnYR/P7Cw1RB9kRwnwb+t6DgJ1naWFXdViTGMmTzL7we3ebqs5X0RWOTRbQjvIA2fIGmXkiMRlKnzphtnQdRwEkHDdxuX7UgHz9qSviP60lL+11u6dnqd6QA0/kOWLJqbqXMM8MQ7CnzNkl2B5nrxfw==
    )

    set "OFFSET="
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
	pause>nul|set/p=.			!ANYKEY.%LNG%!
	exit
) else (
	call :elog "%GRE%!decm2.%LNG%!%RES%"
	call :elog .
)

call :elog .
call :elog "!decm3.%LNG%!"
<nul set /p="!ENTERYN.%LNG%! "
%SystemRoot%\System32\choice.exe /C OSJYN /N /D N /T %CTIME%
if errorlevel 5 (
	set "owrpy=n"
	call :elog "    %YEL%!decm4.%LNG%!%RES%"
	call :elog .
) else (
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
    pause>nul|set/p=.			!ANYKEY.%LNG%!
    exit
) else (
    set "found=1"
)
if not exist "!deobfuscate!" (
    call :elog "    %RED%!decm7.%LNG%! %deobfuscate%. !UNACONT.%LNG%!%RES%"
    call :elog .
    pause>nul|set/p=.			!ANYKEY.%LNG%!
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
        if "!OPTION!" == "6" set "OPTION=4"
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
del /f /q "%unrpycpy%" %DEBUGREDIR%
del /f /q "%decompcab%.tmp" %DEBUGREDIR%
del /f /q "%decompcab%" %DEBUGREDIR%
del /f /q "%deobfuscate%" %DEBUGREDIR%
del /f /q "%deobfuscate%o" %DEBUGREDIR%
rmdir /Q /S "__pycache__" %DEBUGREDIR%
rmdir /Q /S "%decompilerdir%" %DEBUGREDIR%

call :elog "!DONE.%LNG%!"
timeout /t 2 /nobreak >nul
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
if exist "!unren-debug!" (
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

if !debuglevel! GEQ 1 (
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
if "!LNG!" == "zh"  set translation_lang=chinese

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
	set "translation_lang=chinese"
)

if not exist "!WORKDIR!\game\tl\" (
	mkdir "!WORKDIR!\game\tl"
)

call :elog .
call :elog .
echo !choicet.%LNG%!... >> "%UNRENLOG%"
<nul set /p="!choicet.%LNG%!... "

cd /d "%WORKDIR%"
if !debuglevel! GEQ 1 echo "!PYTHONHOME!python.exe" !PYNOASSERT! "!fname!.py" game translate !translation_lang!
"%PYTHONHOME%python.exe" %PYNOASSERT% "%fname%.py" game translate %translation_lang% %DEBUGREDIR%
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
    pause>nul|set/p=.      !ANYKEY.%LNG%!

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
    pause>nul|set/p=.      !ANYKEY.%LNG%!

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


:: When it's not unavailable, show message and exit
:unavailable
if "!RENPYVERSION!" == "7" (
    set "unavailable.en=This feature is unavailable in this version."
    set "unavailable.zh=该功能暂不可用，需要更多代码实现。"
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


:: Check if all files were downloaded successfully
:check_all_files
set "cfile.en=Verification that all files are present"
set "cfile.zh=正在验证所有文件是否齐全"

set "cdwnld.en=Download the missing file from:"
set "cdwnld.zh=请从以下地址下载缺失文件："

echo !cfile.%LNG%!... >> "%UNRENLOG%"
<nul set /p="!cfile.%LNG%!..."
for %%F in (legacy current) do (
    if not exist "!SCRIPTDIR!UnRen-%%~F.bat" (
        call :elog "%RED% !FAIL.%LNG%! %YEL%!MISSING.%LNG%! UnRen-%%~F %RES%"
        call :elog "!cdwnld.%LNG%! %RES%"
        call :elog "%MAG%%URL_REF% %RES%"
        call :elog .
        pause>nul|set/p=.      !ANYKEY.%LNG%!

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
