@echo off

:: Get the current code page
for /f "tokens=2 delims=:" %%a in ('%SYSTEMROOT%\System32\chcp.com') do set "OLD_CP=%%a"
:: Switch to code page 65001 for UTF-8
%SYSTEMROOT%\System32\chcp.com 65001 >nul
setlocal EnableDelayedExpansion

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

:: UnRen-legacy.bat - UnRen Script for Ren'Py <= 7
:: heavily modified by (SM) aka JoeLurmel @ f95zone.to
:: This script is licensed under GNU GPL v3 — see LICENSE for details

:: DO NOT MODIFY BELOW THIS LINE unless you know what you're doing
:: Define various global names
set "NAME=legacy"
set "VERSION=(v9.7.31) (03/03/26)"
title UnRen-%NAME%.bat - %VERSION%
set "URL_REF=https://f95zone.to/threads/unrengui-unren-forall-v9-4-unren-powershell-forall-v9-4-unren-old.92717/post-17110063/"
set "SCRIPTDIR=%~dp0"
set "UPD_TDIR=%TEMP%\UnRenUpdate"
set "SCRIPTNAME=%~nx0"
set "BASENAME=%SCRIPTNAME:.bat=%"
set "UNRENLOG=%TEMP%\UnRen-forall.log"
if exist "%UNRENLOG%" del /f /q "%UNRENLOG%" >nul 2>&1
:: Use wmic for older system or PowerShell for newer ones to get date and time
if exist "!SYSTEMROOT!\System32\wbem\wmic.exe" (
    for /f "skip=1 tokens=1" %%a in ('"!SYSTEMROOT!\System32\wbem\wmic.exe" os get LocalDateTime') do (
        set "datetime=%%a"
        goto :dbreak
    )
) else (
    for /f %%a in ("'!SYSTEMROOT!\system32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -Command "(Get-CimInstance -ClassName Win32_OperatingSystem).LocalDateTime"') do (
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

:: Set default values
set "MDEFS=acefg"
set "MDEFS2=12acefg"
set "CTIME=5"
:: External configuration file for LNG, MDEFS, MDEFS2 and CTIME.
set "UNREN_CFG=%SCRIPTDIR%UnRen-cfg.bat"
:: Load external configuration
if exist "%UNREN_CFG%" (
    call "%UNREN_CFG%"
)

:: Set the cmd screen size with backup of old settings
set "count=0"
:: Read the lines of mode con
for /f "tokens=*" %%A in ('%SYSTEMROOT%\System32\mode.com con') do (
    :: Split the line into tokens
    for %%B in (%%A) do (
        set "val=%%B"
        :: Check if it's a number
        echo !val! | findstr /r "[0-9][0-9]" >nul
        if !ERRORLEVEL! EQU 0 (
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
%SYSTEMROOT%\System32\mode.com con: cols=%NEW_COLS% lines=200 %DEBUGREDIR%
%SYSTEMROOT%\System32\mode.com con: cols=%NEW_COLS% lines=62 %DEBUGREDIR%

if defined LNG goto lngtest

:: Clean retrieval of language code via WMIC or PowerShell
if exist "%SYSTEMROOT%\System32\wbem\wmic.exe" (
    for /f "skip=1 tokens=1" %%l in ('%SYSTEMROOT%\System32\wbem\wmic.exe os get oslanguage') do (
        set LNGID=%%l
        goto found_lcid
    )
) else (
    for /f %%l in ('%SYSTEMROOT%\system32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -Command "Get-CimInstance -ClassName Win32_OperatingSystem | Select-Object -ExpandProperty OSLanguage"') do (
        set LNGID=%%l
        goto found_lcid
    )
)

:found_lcid
:: LCID correspondences
if "!LNGID!" == "1033" set "LNG=en"
if "!LNGID!" == "1036" set "LNG=fr"
if "!LNGID!" == "3082" set "LNG=es"
if "!LNGID!" == "1040" set "LNG=it"
if "!LNGID!" == "1031" set "LNG=de"
if "!LNGID!" == "1049" set "LNG=ru"
if "!LNGID!" == "2052" set "LNG=zh"

if not defined LNG set "LNG=en"

:lngtest
:: Language support test
set "SUPPORTED= de es en fr it ru zh "
set "FIND= %LNG% "
echo %SUPPORTED% | find /i "%FIND%" >nul
if %ERRORLEVEL% NEQ 0 set "LNG=en"

:: To be able to take screenshots for F95zone
if not "%~2" == "" (
    set "LNG=%~2"
)

:: Definition of reusable texts
set "ANYKEY.en=Press any key to exit..."
set "ANYKEY.fr=Appuyez sur une touche pour quitter..."
set "ANYKEY.es=Presione cualquier tecla para salir..."
set "ANYKEY.it=Premere un tasto per uscire..."
set "ANYKEY.de=Drücken Sie eine beliebige Taste, um zu beenden..."
set "ANYKEY.ru=Нажмите любую клавишу для выхода..."
set "ANYKEY.zh=按任意键退出..."

set "ARIGHT.en=Please run this script as an administrator to add the entry."
set "ARIGHT.fr=Veuillez exécuter ce script en tant qu'administrateur pour ajouter l'entrée."
set "ARIGHT.es=Por favor, ejecute este script como administrador para agregar la entrada."
set "ARIGHT.it=Per favore, esegui questo script come amministratore per aggiungere la voce."
set "ARIGHT.de=Bitte führen Sie dieses Skript als Administrator aus, um den Eintrag hinzuzufügen."
set "ARIGHT.ru=Пожалуйста, запустите этот скрипт от имени администратора, чтобы добавить элемент."
set "ARIGHT.zh=请以管理员身份运行此脚本以添加条目。"

set "PASS.en=Pass"
set "PASS.fr=Réussi"
set "PASS.es=Paso"
set "PASS.it=Passato"
set "PASS.de=Bestanden"
set "PASS.ru=Успех"
set "PASS.zh=通过"

set "FAIL.en=Fail"
set "FAIL.fr=Échoué"
set "FAIL.es=Fallo"
set "FAIL.it=Fallito"
set "FAIL.de=Fehlgeschlagen"
set "FAIL.ru=Ошибка"
set "FAIL.zh=失败"

set "APRESENT.en=Option already presented."
set "APRESENT.fr=Option déjà présentée."
set "APRESENT.it=Opzione già presentata."
set "APRESENT.es=Opción ya presentada."
set "APRESENT.de=Option bereits präsentiert."
set "APRESENT.ru=Опция уже представлена."
set "APRESENT.zh=选项已存在。"

set "TWADD.en=This will add:"
set "TWADD.fr=Cela ajoutera:"
set "TWADD.it=Questo aggiungerà:"
set "TWADD.es=Esto añadirá:"
set "TWADD.de=Dies wird hinzufügen:"
set "TWADD.ru=Это добавит:"
set "TWADD.zh=这将添加："

set "INCASEOF.en=In case of problem, please refer to:"
set "INCASEOF.fr=En cas de problème, veuillez vous référer à :"
set "INCASEOF.it=In caso di problemi, si prega di fare riferimento a:"
set "INCASEOF.es=En caso de problemas, consulte:"
set "INCASEOF.de=Im Falle von Problemen wenden Sie sich bitte an:"
set "INCASEOF.ru=В случае проблемы обратитесь к:"
set "INCASEOF.zh=如果出现问题，请参考："

set "INCASEDEL.en=In case of problem, delete the following files/dirs:"
set "INCASEDEL.fr=En cas de problème, supprimez le.s fichier.s/répertoire.s suivants :"
set "INCASEDEL.it=In caso di problemi, eliminare i seguenti file/directory:"
set "INCASEDEL.es=En caso de problemas, elimine los siguientes archivos/directorios:"
set "INCASEDEL.de=Im Falle von Problemen löschen Sie die folgenden Dateien/Verzeichnisse:"
set "INCASEDEL.ru=В случае проблемы удалите следующие файлы/каталоги:"
set "INCASEDEL.zh=如果出现问题，请删除以下文件/目录："

set "UNDWNLD.en=Unable to download:"
set "UNDWNLD.fr=Impossible de télécharger :"
set "UNDWNLD.es=No se puede descargar:"
set "UNDWNLD.it=Impossibile scaricare:"
set "UNDWNLD.de=Download nicht möglich:"
set "UNDWNLD.ru=Не удалось загрузить:"
set "UNDWNLD.zh=无法下载："

set "UNINSTALL.en=Unable to install:"
set "UNINSTALL.fr=Impossible d'installer :"
set "UNINSTALL.es=No se puede instalar:"
set "UNINSTALL.it=Impossibile installare:"
set "UNINSTALL.de=Installation nicht möglich:"
set "UNINSTALL.ru=Не удалось установить:"
set "UNINSTALL.zh=无法安装："

set "UNEXTRACT.en=Unable to extract:"
set "UNEXTRACT.fr=Impossible d'extraire :"
set "UNEXTRACT.es=No se puede extraer:"
set "UNEXTRACT.it=Impossibile estrarre:"
set "UNEXTRACT.de=Fehler beim Herunterladen von:"
set "UNEXTRACT.ru=Не удалось извлечь:"
set "UNEXTRACT.zh=无法提取："

set "MISSING.en=File not found:"
set "MISSING.fr=Fichier introuvable :"
set "MISSING.es=Archivo no encontrado:"
set "MISSING.it=File non trovato:"
set "MISSING.de=Datei nicht gefunden:"
set "MISSING.ru=Файл не найден:"
set "MISSING.zh=找不到文件："

set "ENTERYN.en=Enter [y/n] (default n):"
set "ENTERYN.fr=Entrez [o/n] (par défaut n) :"
set "ENTERYN.es=Ingrese [s/n] (predeterminado n):"
set "ENTERYN.it=Inserisci [s/n] (predefinito n):"
set "ENTERYN.de=Geben Sie [j/n] ein (Standard n):"
set "ENTERYN.ru=Введите [y/n] (по умолчанию n):"
set "ENTERYN.zh=输入 [y/n]（默认 n）："

set "CLEANUP.en=Cleaning up temporary files..."
set "CLEANUP.fr=Nettoyage des fichiers temporaires..."
set "CLEANUP.es=Limpiando archivos temporales..."
set "CLEANUP.it=Pulizia dei file temporanei..."
set "CLEANUP.de=Bereinigen temporärer Dateien..."
set "CLEANUP.ru=Очистка временных файлов..."
set "CLEANUP.zh=清理临时文件..."

set "UNACONT.en=Unable to continue."
set "UNACONT.fr=Impossible de continuer."
set "UNACONT.es=No se puede continuar."
set "UNACONT.it=Impossibile continuare."
set "UNACONT.de=Kann nicht fortgesetzt werden."
set "UNACONT.ru=Не удалось продолжить."
set "UNACONT.zh=无法继续。"

set "LOGCHK.en=Please check the "%UNRENLOG%" for details."
set "LOGCHK.fr=Veuillez consulter le "%UNRENLOG%" pour plus de détails."
set "LOGCHK.es=Por favor, consulte el "%UNRENLOG%" para más detalles."
set "LOGCHK.it=Controlla il "%UNRENLOG%" per ulteriori dettagli."
set "LOGCHK.de=Bitte überprüfen Sie das "%UNRENLOG%" auf Einzelheiten."
set "LOGCHK.ru=Пожалуйста, проверьте "%UNRENLOG%" для получения дополнительных сведений."
set "LOGCHK.zh=请查看 "%UNRENLOG%" 以了解详情。"

set "DONE.en=Operation completed."
set "DONE.fr=Opération terminée."
set "DONE.es=Operación completada."
set "DONE.it=Operazione completata."
set "DONE.de=Vorgang abgeschlossen."
set "DONE.ru=Операция завершена."
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


set "INITIALIZED=0"
set "NOCLS=0"
:menu
:: Splash screen
if "!NOCLS!" == "0" cls
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

if "!INITIALIZED!" == "1" goto skipInit

:: Initializing debug mode
set "DEBUGREDIR=>nul 2>&1"
set "DEBUGLEVEL=0"
set "NOCLS=0"

:: We need PowerShell for later, make sure it exists
set "pshell.en=Checking for availability of PowerShell... "
set "pshell.fr=Vérification de la disponibilité de PowerShell... "
set "pshell.es=Comprobando la disponibilidad de PowerShell... "
set "pshell.it=Verifica della disponibilità di PowerShell... "
set "pshell.de=Überprüfung der Verfügbarkeit von PowerShell... "
set "pshell.ru=Проверка доступности PowerShell... "
set "pshell.zh=检查 PowerShell 是否可用... "

set "pshell1.en=Powershell is required."
set "pshell1.fr=Erreur Powershell est requis."
set "pshell1.es=Error Se requiere Powershell."
set "pshell1.it=Errore Powershell è richiesto."
set "pshell1.de=Fehler Powershell ist erforderlich."
set "pshell1.ru=Ошибка требуется PowerShell."
set "pshell1.zh=需要 PowerShell。"

set "pshell2.en=This is included in Windows 7, 8 and 10. XP/Vista users can"
set "pshell2.fr=Ce programme est inclus dans Windows 7, 8 et 10. Les utilisateurs de XP/Vista peuvent"
set "pshell2.es=Esto está incluido en Windows 7, 8 y 10. Los usuarios de XP/Vista pueden"
set "pshell2.it=Questo programma è incluso in Windows 7, 8 e 10. Gli utenti di XP/Vista possono"
set "pshell2.de=Dieses Programm ist in Windows 7, 8 und 10 enthalten. XP/Vista-Benutzer können"
set "pshell2.ru=Это включено в Windows 7, 8 и 10. Пользователи XP/Vista могут"
set "pshell2.zh=Windows 7、8 和 10 包含此组件。XP/Vista 用户可以"

set "pshell3.en=download it here: %MAG%https://learn.microsoft.com/en-us/powershell/scripting/install/installing-powershell-on-windows?view=powershell-7.5%RES%"
set "pshell3.fr=le télécharger ici : %MAG%https://learn.microsoft.com/fr-fr/powershell/scripting/install/installing-powershell-on-windows?view=powershell-7.5%RES%"
set "pshell3.es=descargarlo aquí: %MAG%https://learn.microsoft.com/es-es/powershell/scripting/install/installing-powershell-on-windows?view=powershell-7.5%RES%"
set "pshell3.it=scaricarlo qui: %MAG%https://learn.microsoft.com/it-it/powershell/scripting/install/installing-powershell-on-windows?view=powershell-7.5%RES%"
set "pshell3.de=es hier herunterladen: %MAG%https://learn.microsoft.com/de-de/powershell/scripting/install/installing-powershell-on-windows?view=powershell-7.5%RES%"
set "pshell3.ru=скачать его здесь: %MAG%https://learn.microsoft.com/ru-ru/powershell/scripting/install/installing-powershell-on-windows?view=powershell-7.5%RES%"
set "pshell3.zh=在此下载：%MAG%https://learn.microsoft.com/en-us/powershell/scripting/install/installing-powershell-on-windows?view=powershell-7.5%RES%"

echo !pshell.%LNG%! >> "%UNRENLOG%"
<nul set /p=!pshell.%LNG%!
set "PWRSHELL=%SYSTEMROOT%\system32\WindowsPowerShell\v1.0\powershell.exe"
for /f "delims=" %%A in ('"!SYSTEMROOT!\System32\where.exe" pwsh.exe 2^>nul') do (
    if not "%%A" == "" set "PWRSHELL=%%A"
)
if not exist "%PWRSHELL%" (
    call :elog "%RED%!FAIL.%LNG%!%RES%"
    call :elog .
    call :elog "    !pshell1.%LNG%! !UNACONT.%LNG%!"
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
    set "DEBUGLEVEL=1"
    set "NOCLS=1"
    "%PWRSHELL%" -NoProfile -Command "$h = Get-Host; $h.UI.RawUI.BufferSize = New-Object Management.Automation.Host.Size(!NEW_COLS!,5000)"
)
if /i "%~3" == "-dd" (
    echo on
    set "DEBUGREDIR="
    set "DEBUGLEVEL=2"
    set "NOCLS=1"
    "%PWRSHELL%" -NoProfile -Command "$h = Get-Host; $h.UI.RawUI.BufferSize = New-Object Management.Automation.Host.Size(!NEW_COLS!,9000)"
)


:: Set the working directory
set "setpath1.en=Enter the path to the game, drag'n'drop it here,"
set "setpath1.fr=Entrez le chemin vers le jeu, faites-le glisser ici,"
set "setpath1.es=Introduzca la ruta al juego, arrástrelo aquí,"
set "setpath1.it=Inserisci il percorso del gioco, trascinalo qui,"
set "setpath1.de=Geben Sie den Pfad zum Spiel ein, ziehen Sie es hierher,"
set "setpath1.ru=Введите путь к игре, перетащите его сюда,"
set "setpath1.zh=输入游戏路径，将其拖放到此处，"

set "setpath2.en=or press Enter if this tool is already in the desired folder."
set "setpath2.fr=ou appuyez sur Entrée si cet outil se trouve déjà dans le dossier souhaité."
set "setpath2.es=o presione Entrar si esta herramienta ya se encuentra en la carpeta deseada."
set "setpath2.it=oppure premi Invio se questo strumento si trova già nella cartella desiderata."
set "setpath2.de=oder drücken Sie die Eingabetaste, wenn sich dieses Tool bereits im gewünschten Ordner befindet."
set "setpath2.ru=или нажмите Enter, если этот инструмент уже находится в нужной папке."
set "setpath2.zh=或者如果此工具已在所需文件夹中，请按 Enter 键。"

set "setpath3.en=If drag'n'drop does not work, please copy/paste the path instead: "
set "setpath3.fr=Si le glisser-déposer ne fonctionne pas, veuillez copier/coller le chemin à la place : "
set "setpath3.es=Si arrastrar y soltar no funciona, copie/pegue la ruta en su lugar: "
set "setpath3.it=Se il trascinamento della selezione non funziona, copia/incolla il percorso invece: "
set "setpath3.de=Wenn das Ziehen und Ablegen nicht funktioniert, kopieren Sie den Pfad bitte stattdessen hierher: "
set "setpath3.ru=Если перетаскивание не работает, пожалуйста, скопируйте/вставьте путь вместо этого: "
set "setpath3.zh=如果拖放不起作用，请复制/粘贴路径："

:: Check if game path is provided and set it
set "WORKDIR="
setlocal disabledelayedexpansion
if "%~1" == "" (
    setlocal enabledelayedexpansion
    call :elog .
    call :elog "!setpath1.%LNG%!"
    call :elog "!setpath2.%LNG%!"
    call :elog .
    set /p "WORKDIR=!setpath3.%LNG%!"
    setlocal disabledelayedexpansion
    if not defined WORKDIR (
        set "WORKDIR=%cd%"
    )
) else (
    set "WORKDIR=%~1"
    if "%WORKDIR%" == "." (
        set "WORKDIR=%cd%"
    )
)
:: Remove surrounding quotes if any
set "WORKDIR=%WORKDIR:"=%"

:: Normalize WORKDIR to an absolute path
for %%A in ("%WORKDIR%") do set "WORKDIR=%%~fA"

set "invchars.en=Invalid character detected in the path..."
set "invchars.fr=Caractère invalide détecté dans le chemin..."
set "invchars.es=Se ha detectado un carácter no válido en la ruta de acceso..."
set "invchars.it=Carattere non valido rilevato nel percorso di accesso..."
set "invchars.de=Ungültiges Zeichen im Pfad gefunden..."
set "invchars.ru=Обнаружен недействительный символ в пути доступа..."
set "invchars.zh=路径中检测到无效字符..."
set "HAS_BAD="
:: Characters that CAN appear in a valid Windows path but WILL break batch logic:
for %%C in ("&" "!" "(" ")" "=" ";" "'" "`" "[" "]" "{" "}" "+" "~") do (
    echo "%WORKDIR%" | find "%%~C" >nul && (
        if not defined HAS_BAD (
            rem Premier caractère trouvé
            call set "HAS_BAD=%%~C"
        ) else (
            rem On ajoute à la liste existante
            call set "HAS_BAD=%%HAS_BAD%%,%%~C"
        )
    )
)

setlocal enabledelayedexpansion
if defined HAS_BAD (
    echo.
    echo !invchars.%LNG%! '%RED%!HAS_BAD!%RES%' !UNACONT.%LNG%!
    echo.
    pause>nul|set/p=.      !ANYKEY.%LNG%!

    call :exitn 3
)

set "wdir1.en=Error The specified directory does not exist."
set "wdir1.fr=Erreur Le répertoire spécifié n'existe pas."
set "wdir1.es=Error El directorio especificado no existe."
set "wdir1.it=Errore la directory specificata non esiste."
set "wdir1.de=Fehler Das angegebene Verzeichnis existiert nicht."
set "wdir1.ru=Ошибка Указанный каталог не существует."
set "wdir1.zh=错误：指定的目录不存在。"

set "wdir2.en=Are you sure we're in the game's root directory?"
set "wdir2.fr=Êtes-vous sûr que nous sommes dans le répertoire racine du jeu ?"
set "wdir2.es=¿Está seguro de que estamos en el directorio raíz del juego?"
set "wdir2.it=Sei sicuro che siamo nella directory principale del gioco?"
set "wdir2.de=Sind Sie sicher, dass wir uns im Stammverzeichnis des Spiels befinden?"
set "wdir2.ru=Вы уверены, что находимся в корневом каталоге игры?"
set "wdir2.zh=确定我们在游戏根目录中吗？"

set "wdir3.en=Testing write access to game directory"
set "wdir3.fr=Test de l'accès en écriture au répertoire du jeu"
set "wdir3.es=Prueba de acceso de escritura al directorio del juego"
set "wdir3.it=Verifica l'accesso in scrittura alla directory di gioco"
set "wdir3.de=Testen des Schreibzugriffs auf das Spieledirectory"
set "wdir3.ru=Проверка доступа на запись в каталог игры"
set "wdir3.zh=测试对游戏目录的写入权限"

set "wdir4.en=You can't write in game directory."
set "wdir4.fr=Vous ne pouvez pas écrire dans le répertoire du jeu."
set "wdir4.es=No puedes escribir en el directorio del juego."
set "wdir4.it=Non puoi scrivere nella directory di gioco."
set "wdir4.de=Sie können nicht im Spieledirectory schreiben."
set "wdir4.ru=Вы не можете писать в каталоге игры."
set "wdir4.zh=无法写入游戏目录。"

cd /d "%WORKDIR%"
if %ERRORLEVEL% NEQ 0 (
    call :elog .
    call :elog "    %RED%!wdir1.%LNG%!%RES%"
    call :elog "    !wdir2.%LNG%!"
    call :elog .
    pause>nul|set/p=.      !ANYKEY.%LNG%!

    call :exitn 3
)


set "reqdir1.en=Checking if game, lib, renpy directories exist..."
set "reqdir1.fr=Vérification de l'existence des répertoires game, lib et renpy..."
set "reqdir1.es=Comprobando si existen los directorios game, lib, renpy..."
set "reqdir1.it=Controllo dell'esistenza delle directory game, lib, renpy..."
set "reqdir1.de=Überprüfung der Existenz der Verzeichnisse game, lib, renpy..."
set "reqdir1.ru=Проверка наличия каталогов game, lib, renpy..."
set "reqdir1.zh=检查 game、lib、renpy 目录是否存在..."

set "reqdir2.en=Cannot locate game, lib or renpy directories."
set "reqdir2.fr=Erreur Impossible de localiser les répertoires game, lib ou renpy."
set "reqdir2.es=Error No se pueden localizar los directorios game, lib o renpy."
set "reqdir2.it=Errore Impossibile localizzare le directory game, lib o renpy."
set "reqdir2.de=Fehler Unmöglich, die Verzeichnisse game, lib oder renpy zu finden."
set "reqdir2.ru=Ошибка Не удалось найти каталоги game, lib или renpy."
set "reqdir2.zh=找不到 game、lib 或 renpy 目录。"

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
    call :elog "    !reqdir2.%LNG%! !UNACONT.%LNG%!"
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
if %ERRORLEVEL% NEQ 0 (
    call :elog "%RED%!FAIL.%LNG%! %YEL%!wdir4.%LNG%!%RES%"
    call :elog .
    call :elog "    !wdir2.%LNG%!"
    call :elog .
    pause>nul|set/p=.      !ANYKEY.%LNG%!

    call :exitn 3
) else (
    del /f /q "%WORKDIR%\game\test.txt" %DEBUGREDIR%
    call :elog "%GRE%!PASS.%LNG%!%RES%"
)


:: Set UNRENLOG for debugging purpose
If exist "%TEMP%\UnRen-forall.log" (
    :: Move the temporary log file to the working directory
    move /y "%TEMP%\UnRen-forall.log" "%WORKDIR%\UnRen-forall.log" %DEBUGREDIR%
)
set "UNRENLOG=%WORKDIR%\UnRen-forall.log"
set "UNRENLOG=%UNRENLOG:"=%"

:: Check for Python
set "python1.en=Checking if Python is available..."
set "python1.fr=Vérification de la disponibilité de Python..."
set "python1.es=Comprobando si Python está disponible..."
set "python1.it=Controllo della disponibilità di Python..."
set "python1.de=Überprüfung der Verfügbarkeit von Python..."
set "python1.ru=Проверка наличия Python..."
set "python1.zh=检查 Python 是否可用..."

set "python2.en=Cannot locate python directory."
set "python2.fr=Impossible de localiser le répertoire python."
set "python2.es=No se puede localizar el directorio de Python."
set "python2.it=Impossibile localizzare la directory di Python."
set "python2.de=Python-Verzeichnis kann nicht gefunden werden."
set "python2.ru=Не удалось найти каталог Python."
set "python2.zh=找不到 python 目录。"

echo !python1.%LNG%! >> "%UNRENLOG%"
<nul set /p=!python1.%LNG%!

:: Doublecheck to avoid issues with Milfania games
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

:: Set the PYNOASSERT according to “%PYTHONHOME%Lib”.
if exist "%PYTHONHOME%Lib" (
    set "PYNOASSERT=-O"
) else (
    set "PYNOASSERT="
)

set "PYTHONPATH=%PYTHONHOME%"
set "latest="
set "latestver="

:: Priority to Python 2.7 if present
if exist "%WORKDIR%\lib\pythonlib2.7" (
    <nul set /p=.
    set "PYTHONPATH=%WORKDIR%\lib\pythonlib2.7"
    set "PYVERS=2.7"
    goto pyend
) else if exist "%WORKDIR%\lib\python2.7" (
    <nul set /p=.
    set "PYTHONPATH=%WORKDIR%\lib\python2.7"
    set "PYVERS=2.7"
    goto pyend
)

:: Searching for the latest version of Python 3.x
for /D %%D in ("%WORKDIR%\lib\python3.*") do (
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
if not exist "%PYTHONHOME%\python.exe" (
    call :elog " %RED%!FAIL.%LNG%!%RES%"
    call :elog .
    call :elog "    %RED%!python2.%LNG%!%RES% !UNACONT.%LNG%!"
    call :elog "    !wdir2.%LNG%!"
    call :elog .
    pause>nul|set/p=.      !ANYKEY.%LNG%!

    call :exitn 3
) else (
    call :elog " %GRE%!PASS.%LNG%!%YEL% Python %PYVERS%%RES%"
)

echo Check Python Version... >> "%UNRENLOG%"
for /f "tokens=2 delims= " %%a in ('"%PYTHONHOME%\python.exe" -V 2^>^&1') do set PYTHONVERS=%%a
:: Extraction of major and minor versions
for /f "tokens=1,2 delims=." %%b in ("%PYTHONVERS%") do (
    set PYTHONMAJOR=%%b
    set PYTHONMINOR=%%c
)

:: Check if Python ^>= 3.8
if %PYTHONMAJOR% GEQ 3 (
	if %PYTHONMINOR% GEQ 8 (
		echo Python version is %PYTHONVERS%, which is upper or equal to 3.8 >> "%UNRENLOG%"
    	set "RPATOOL-NEW=y"
	) else (
		echo Python version is %PYTHONVERS%, which is lower than 3.8 >> "%UNRENLOG%"
		set "RPATOOL-NEW=n"
	)
) else (
	echo Python version is %PYTHONVERS%, which is lower than 3 >> "%UNRENLOG%"
    set "RPATOOL-NEW=n"
)

:: Check for Ren'Py version
set "renpyvers1.en=Ren'Py version found: "
set "renpyvers1.fr=Version Ren'Py trouvée : "
set "renpyvers1.es=Versión de Ren'Py encontrada: "
set "renpyvers1.it=Versione Ren'Py rilevata: "
set "renpyvers1.de=Ren'Py-Version gefunden: "
set "renpyvers1.ru=Найдена версия Ren'Py: "
set "renpyvers1.zh=检测到的 Ren'Py 版本："

set "renpyvers2.en=Failed to create detect_renpy_version.py."
set "renpyvers2.fr=Erreur Impossible de créer detect_renpy_version.py."
set "renpyvers2.es=Error No se pudo crear detect_renpy_version.py."
set "renpyvers2.it=Errore Impossibile creare detect_renpy_version.py."
set "renpyvers2.de=Fehler Die Erstellung von detect_renpy_version.py ist fehlgeschlagen."
set "renpyvers2.ru=Ошибка Не удалось создать detect_renpy_version.py."
set "renpyvers2.zh=无法创建 detect_renpy_version.py。"

set "renpyvers3.en=Unable to detect Ren'Py version,"
set "renpyvers3.fr=Impossible de détecter la version de Ren'Py,"
set "renpyvers3.es=No se puede detectar la versión de Ren'Py,"
set "renpyvers3.it=Impossibile rilevare la versione di Ren'Py,"
set "renpyvers3.de=Unmöglich, die Ren'Py-Version zu erkennen, bitte sicherstellen,"
set "renpyvers3.ru=Не удалось обнаружить версию Ren'Py, пожалуйста,"
set "renpyvers3.zh=无法检测 Ren'Py 版本，"

set "renpyvers4.en=        please ensure the game is compatible with UnRen."
set "renpyvers4.fr=        es-tu sûr que le jeu est compatible avec UnRen ?"
set "renpyvers4.es=        asegúrese de que el juego sea compatible con UnRen."
set "renpyvers4.it=        assicurati che il gioco sia compatibile con UnRen."
set "renpyvers4.de=        dass das Spiel mit UnRen kompatibel ist."
set "renpyvers4.ru=        убедитесь, что игра совместима с UnRen."
set "renpyvers4.zh=        请确保游戏与 UnRen 兼容。"

echo !renpyvers1.%LNG%! >> "%UNRENLOG%"
<nul set /p=!renpyvers1.%LNG%!

cd /d "%WORKDIR%"
set "detect_renpy_version_py=detect_renpy_version.py"
del /f /q "%detect_renpy_version_py%" %DEBUGREDIR%
>"%detect_renpy_version_py%.b64" (
    echo IyEvdXNyL2Jpbi9lbnYgcHl0aG9uCiMgLSotIGNvZGluZzogdXRmLTggLSotCgppbXBvcnQgb3MKaW1wb3J0IHN5cwppbXBvcnQgcmUKI2ltcG9ydCBzdHJ1Y3QKCgppbXBvcnQgb3MsIHJlCgpkZWYgZGV0ZWN0X2Zyb21fc2NyaXB0X3ZlcnNpb24oZ2FtZV9kaXIpOgogICAgIyAxKSBSZW4nUHkgNy84IDogc2NyaXB0X3ZlcnNpb24udHh0CiAgICBwYXRoID0gb3MucGF0aC5qb2luKGdhbWVfZGlyLCAic2NyaXB0X3ZlcnNpb24udHh0IikKICAgIGlmIG9zLnBhdGguaXNmaWxlKHBhdGgpOgogICAgICAgIHRyeToKICAgICAgICAgICAgd2l0aCBvcGVuKHBhdGgsICJyIikgYXMgZjoKICAgICAgICAgICAgICAgIGNvbnRlbnQgPSBmLnJlYWQoKS5zdHJpcCgpCgogICAgICAgICAgICAjIFR1cGxlIGZvcm1hdCA6ICg4LCAxLCAwKQogICAgICAgICAgICBtID0gcmUuc2VhcmNoKHInXChccyooXGQrKVxzKiwnLCBjb250ZW50KQogICAgICAgICAgICBpZiBtOgogICAgICAgICAgICAgICAgcmV0dXJuIGludChtLmdyb3VwKDEpKQoKICAgICAgICAgICAgIyBTaW1wbGUgZm9ybWF0IDogOC4xLjAgb3UgOAogICAgICAgICAgICBtID0gcmUubWF0Y2gocidccyooXGQrKScsIGNvbnRlbnQpCiAgICAgICAgICAgIGlmIG06CiAgICAgICAgICAgICAgICByZXR1cm4gaW50KG0uZ3JvdXAoMSkpCgogICAgICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgICAgIHBhc3MKCiAgICAjIDIpIFJlbidQeSA2IDogcmVucHkvdmVyc2lvbi5weQogICAgdmVyc2lvbl9weSA9IG9zLnBhdGguam9pbihnYW1lX2RpciwgInJlbnB5IiwgInZlcnNpb24ucHkiKQogICAgaWYgb3MucGF0aC5pc2ZpbGUodmVyc2lvbl9weSk6CiAgICAgICAgdHJ5OgogICAgICAgICAgICB3aXRoIG9wZW4odmVyc2lvbl9weSwgInIiKSBhcyBmOgogICAgICAgICAgICAgICAgY29udGVudCA9IGYucmVhZCgpCgogICAgICAgICAgICAjIHZlcnNpb24gPSAiNi45OS4xNCIKICAgICAgICAgICAgbSA9IHJlLnNlYXJjaChyJ3ZlcnNpb25ccyo9XHMqIihcZCspJywgY29udGVudCkKICAgICAgICAgICAgaWYgbToKICAgICAgICAgICAgICAgIHJldHVybiBpbnQobS5ncm91cCgxKSkKCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICAgICAgcGFzcwoKICAgIHJldHVybiBOb25lCgoKZGVmIGRldGVjdF9mcm9tX3JweWMoZ2FtZV9kaXIpOgogICAgIiIiCiAgICBSZWFkcyB0aGUgbWFnaWMgbnVtYmVyIG9mIC5ycHljIC8gLnJweW1jIGZpbGVzLgogICAgUmVuJ1B5IDY6IG1hZ2ljIOKAnFJFTlBZIFJQQzHigJ0gIC0+IG1ham9yIDYgKGFuZCBzb21lIGVhcmx5IDcpCiAgICBSZW4nUHkgNzogbWFnaWMg4oCcUkVOUFkgUlBDMuKAnSAgLT4gbWFqb3IgNwogICAgUmVuJ1B5IDg6IG1hZ2ljIOKAnFJFTlBZIFJQQzLigJ0gIHdpdGggUHl0aG9uIDMgKGNhbm5vdCBiZSBlYXNpbHkgZGlzdGluZ3Vpc2hlZAogICAgICAgICAgICAgICAgZnJvbSA3IHVzaW5nIG1hZ2ljIGFsb25lLCBvdGhlciBtZXRob2RzIGFyZSB1c2VkIHRvIGNvbXBsZXRlIHRoZSBwcm9jZXNzKQogICAgTm90ZTogc29tZSBlYXJseSBSZW4nUHkgNyBtYXkgc3RpbGwgdXNlIOKAnFJFTlBZIFJQQzHigJ0gbWFnaWMsIGJ1dCB0aGV5IGFyZSByYXJlIGFuZCB3ZSBwcmlvcml0aXplIHRoZSBtb3JlIGNvbW1vbiBjYXNlLgogICAgIiIiCiAgICBtYWdpY19tYXAgPSB7CiAgICAgICAgYiJSRU5QWSBSUEMxIjogNiwKICAgICAgICBiIlJFTlBZIFJQQzIiOiA3LCAgIyBjYW4gYWxzbyBiZSA4CiAgICB9CiAgICBmb3Igcm9vdCwgZGlycywgZmlsZXMgaW4gb3Mud2FsayhnYW1lX2Rpcik6CiAgICAgICAgZm9yIGZuYW1lIGluIGZpbGVzOgogICAgICAgICAgICBpZiBmbmFtZS5lbmRzd2l0aCgiLnJweWMiKSBvciBmbmFtZS5lbmRzd2l0aCgiLnJweW1jIik6CiAgICAgICAgICAgICAgICBmcGF0aCA9IG9zLnBhdGguam9pbihyb290LCBmbmFtZSkKICAgICAgICAgICAgICAgIHRyeToKICAgICAgICAgICAgICAgICAgICB3aXRoIG9wZW4oZnBhdGgsICJyYiIpIGFzIGY6CiAgICAgICAgICAgICAgICAgICAgICAgIGhlYWRlciA9IGYucmVhZCgxMCkKICAgICAgICAgICAgICAgICAgICBmb3IgbWFnaWMsIG1ham9yIGluIG1hZ2ljX21hcC5pdGVtcygpOgogICAgICAgICAgICAgICAgICAgICAgICBpZiBoZWFkZXIuc3RhcnRzd2l0aChtYWdpYyk6CiAgICAgICAgICAgICAgICAgICAgICAgICAgICByZXR1cm4gbWFqb3IKICAgICAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgICAgICAgICAgICAgY29udGludWUKICAgIHJldHVybiBOb25lCgoKZGVmIGRldGVjdF9mcm9tX2V4ZWN1dGFibGUoZ2FtZV9kaXIpOgogICAgIiIiCiAgICBMb29rIGZvciB2ZXJzaW9uIGNsdWVzIGluIHRoZSBleGVjdXRhYmxlcy9saWJzIHByZXNlbnQKICAgIGluIHRoZSBnYW1lIGZvbGRlciAoc3RyaW5ncyDigJw3LuKAnSBvciDigJw4LuKAnSBjbG9zZSB0byDigJxSZW4nUHnigJ0pLgogICAgIiIiCiAgICBiYXNlID0gb3MucGF0aC5kaXJuYW1lKGdhbWVfZGlyKSAgIyBwYXJlbnQgZm9sZGVyIG9mIHRoZSBnYW1lLyBmb2xkZXIKICAgIHNlYXJjaF9kaXJzID0gW2Jhc2UsIGdhbWVfZGlyXQogICAgcGF0dGVybnMgPSBbCiAgICAgICAgKHJlLmNvbXBpbGUociJSZW4uP1B5XHMrKFxkKVwuXGQiKSwgTm9uZSksCiAgICAgICAgKHJlLmNvbXBpbGUociJyZW5weVtfXC1dKFxkKVwuXGQiKSwgcmUuSUdOT1JFQ0FTRSksCiAgICBdCiAgICBmb3Igc2RpciBpbiBzZWFyY2hfZGlyczoKICAgICAgICBmb3IgZm5hbWUgaW4gb3MubGlzdGRpcihzZGlyKToKICAgICAgICAgICAgZnBhdGggPSBvcy5wYXRoLmpvaW4oc2RpciwgZm5hbWUpCiAgICAgICAgICAgIGlmIG5vdCBvcy5wYXRoLmlzZmlsZShmcGF0aCk6CiAgICAgICAgICAgICAgICBjb250aW51ZQogICAgICAgICAgICAjIE9ubHkgc21hbGwgdGV4dCBvciBsb2cgZmlsZXMgYXJlIHJlYWQuCiAgICAgICAgICAgIGlmIGZuYW1lLmVuZHN3aXRoKCgiLnR4dCIsICIubG9nIiwgIi5pbmkiLCAiLmNmZyIsICIuanNvbiIpKToKICAgICAgICAgICAgICAgIHRyeToKICAgICAgICAgICAgICAgICAgICB3aXRoIG9wZW4oZnBhdGgsICJyIikgYXMgZjoKICAgICAgICAgICAgICAgICAgICAgICAgY29udGVudCA9IGYucmVhZCg0MDk2KQogICAgICAgICAgICAgICAgICAgIGZvciBwYXQsIGZsYWdzIGluIHBhdHRlcm5zOgogICAgICAgICAgICAgICAgICAgICAgICBtID0gcGF0LnNlYXJjaChjb250ZW50KQogICAgICAgICAgICAgICAgICAgICAgICBpZiBtOgogICAgICAgICAgICAgICAgICAgICAgICAgICAgbWFqb3IgPSBpbnQobS5ncm91cCgxKSkKICAgICAgICAgICAgICAgICAgICAgICAgICAgIGlmIG1ham9yIGluICg2LCA3LCA4KToKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICByZXR1cm4gbWFqb3IKICAgICAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgICAgICAgICAgICAgcGFzcwogICAgcmV0dXJuIE5vbmUKCgpkZWYgZGV0ZWN0X2Zyb21fYXJjaGl2ZShnYW1lX2Rpcik6CiAgICAiIiIKICAgIEluc3BlY3QgdGhlIC5ycGEgYXJjaGl2ZXMgdG8gZGV0ZWN0IHRoZSB2ZXJzaW9uLgogICAgUlBBLTEuMCAtPiBSZW4nUHkgNiBlYXJseQogICAgUlBBLTIuMCAtPiBSZW4nUHkgNgogICAgUlBBLTMuMCAtPiBSZW4nUHkgNi83CiAgICBSUEFOMy4wIC0+IFJlbidQeSA4IChuZXcgbmV1dHJvbiBhcmNoaXZlKQogICAgWmlYLTEyQSAtPiBSZW4nUHkgOCAobmV3IG5ldXRyb24gYXJjaGl2ZSkKICAgIFppWC0xMkIgLT4gUmVuJ1B5IDggKG5ldyBuZXV0cm9uIGFyY2hpdmUpCiAgICAiIiIKICAgIHJwYV9tYWpvcl9tYXAgPSB7CiAgICAgICAgYiJSUEEtMS4wIjogNiwKICAgICAgICBiIlJQQS0yLjAiOiA2LAogICAgICAgIGIiUlBBLTMuMCI6IDcsICAgIyBNYXliZSA2IGFzIHdlbGwsIGJ1dCB3ZSdsbCByZWZpbmUgaXQgbGF0ZXIuCiAgICAgICAgYiJSUEFOMy4wIjogOCwKICAgICAgICBiIlppWC0xMkEiOiA4LAogICAgICAgIGIiWmlYLTEyQiI6IDgsCiAgICB9CiAgICBmb3VuZCA9IE5vbmUKICAgIGZvciBmbmFtZSBpbiBvcy5saXN0ZGlyKGdhbWVfZGlyKToKICAgICAgICBpZiBub3QgZm5hbWUuZW5kc3dpdGgoIi5ycGEiKToKICAgICAgICAgICAgY29udGludWUKICAgICAgICBmcGF0aCA9IG9zLnBhdGguam9pbihnYW1lX2RpciwgZm5hbWUpCiAgICAgICAgdHJ5OgogICAgICAgICAgICB3aXRoIG9wZW4oZnBhdGgsICJyYiIpIGFzIGY6CiAgICAgICAgICAgICAgICBoZWFkZXIgPSBmLnJlYWQoOCkKICAgICAgICAgICAgZm9yIG1hZ2ljLCBtYWpvciBpbiBycGFfbWFqb3JfbWFwLml0ZW1zKCk6CiAgICAgICAgICAgICAgICBpZiBoZWFkZXIuc3RhcnRzd2l0aChtYWdpYyk6CiAgICAgICAgICAgICAgICAgICAgIyBXZSBrZWVwIHRoZSBoaWdoZXN0IG1ham9yIGZvdW5kLgogICAgICAgICAgICAgICAgICAgIGlmIGZvdW5kIGlzIE5vbmUgb3IgbWFqb3IgPiBmb3VuZDoKICAgICAgICAgICAgICAgICAgICAgICAgZm91bmQgPSBtYWpvcgogICAgICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgICAgIHBhc3MKICAgIHJldHVybiBmb3VuZAoKCmRlZiBkZXRlY3RfcmVucHlfbWFqb3IoZ2FtZV9wYXRoKToKICAgICIiIgogICAgRGV0ZWN0cyB0aGUgbWFqb3IgUmVuJ1B5IHZlcnNpb24gKDYsIDcsIG9yIDgpIGZyb20gdGhlIGdhbWUgcGF0aC4KICAgIGdhbWVfcGF0aCBjYW4gYmUgdGhlIGdhbWUncyByb290IGZvbGRlciBvciB0aGUg4oCcZ2FtZS/igJ0gc3ViZm9sZGVyLgogICAgIiIiCiAgICAjIE5vcm1hbGl6ZTogd2Ugd2FudCB0aGUg4oCcZ2FtZS/igJ0gZm9sZGVyCiAgICBpZiBvcy5wYXRoLmJhc2VuYW1lKGdhbWVfcGF0aCkgPT0gImdhbWUiOgogICAgICAgIGdhbWVfZGlyID0gZ2FtZV9wYXRoCiAgICBlbHNlOgogICAgICAgIGNhbmRpZGF0ZSA9IG9zLnBhdGguam9pbihnYW1lX3BhdGgsICJnYW1lIikKICAgICAgICBpZiBvcy5wYXRoLmlzZGlyKGNhbmRpZGF0ZSk6CiAgICAgICAgICAgIGdhbWVfZGlyID0gY2FuZGlkYXRlCiAgICAgICAgZWxzZToKICAgICAgICAgICAgZ2FtZV9kaXIgPSBnYW1lX3BhdGggICMgd2UgdHJ5IGRpcmVjdGx5CgogICAgaWYgbm90IG9zLnBhdGguaXNkaXIoZ2FtZV9kaXIpOgogICAgICAgIHByaW50KCJFUlJPUjogZGlyZWN0b3J5IG5vdCBmb3VuZDoge30iLmZvcm1hdChnYW1lX2RpcikpCiAgICAgICAgc3lzLmV4aXQoMSkKCiAgICAjIDEuIHNjcmlwdF92ZXJzaW9uLnR4dCAocHJpb3JpdHkgYnV0IG9wdGlvbmFsKQogICAgbWFqb3IgPSBkZXRlY3RfZnJvbV9zY3JpcHRfdmVyc2lvbihnYW1lX2RpcikKICAgIGlmIG1ham9yIGlzIG5vdCBOb25lOgogICAgICAgIHJldHVybiBtYWpvcgoKICAgICMgMi4gQXJjaGl2ZXMgLnJwYSAoUmVsaWFibGUgc2lnbmF0dXJlcyBmb3IgUmVuJ1B5IDgpCiAgICBtYWpvciA9IGRldGVjdF9mcm9tX2FyY2hpdmUoZ2FtZV9kaXIpCiAgICBpZiBtYWpvciBpcyBub3QgTm9uZToKICAgICAgICAjIFJQQS0zLjAgY2FuIGJlIDYgb3IgNzsgd2UgcmVmaW5lIGl0IHdpdGggdGhlIC5ycHljIGZpbGVzLgogICAgICAgIGlmIG1ham9yID09IDc6CiAgICAgICAgICAgIHJweWNfbWFqb3IgPSBkZXRlY3RfZnJvbV9ycHljKGdhbWVfZGlyKQogICAgICAgICAgICBpZiBycHljX21ham9yIGlzIG5vdCBOb25lOgogICAgICAgICAgICAgICAgcmV0dXJuIHJweWNfbWFqb3IKICAgICAgICByZXR1cm4gbWFqb3IKCiAgICAjIDMuIC5ycHljIGZpbGVzICh2ZXJ5IHJlbGlhYmxlIGZvciBSZW4nUHkgNiBhbmQgNywgYnV0IGRvIG5vdCBkaXN0aW5ndWlzaCBiZXR3ZWVuIDcgYW5kIDgpOgogICAgbWFqb3IgPSBkZXRlY3RfZnJvbV9ycHljKGdhbWVfZGlyKQogICAgaWYgbWFqb3IgaXMgbm90IE5vbmU6CiAgICAgICAgcmV0dXJuIG1ham9yCgogICAgIyA0LiBUZXh0IGZpbGVzIGluIHRoZSByb290IGZvbGRlciAobWF5IGNvbnRhaW4gdmVyc2lvbiBpbmZvLCBlc3BlY2lhbGx5IGZvciBSZW4nUHkgOCk6CiAgICBtYWpvciA9IGRldGVjdF9mcm9tX2V4ZWN1dGFibGUoZ2FtZV9kaXIpCiAgICBpZiBtYWpvciBpcyBub3QgTm9uZToKICAgICAgICByZXR1cm4gbWFqb3IKCiAgICByZXR
    echo 1cm4gTm9uZQoKCmRlZiBtYWluKCk6CiAgICBpZiBsZW4oc3lzLmFyZ3YpIDwgMjoKICAgICAgICBwcmludCgiVXNhZ2U6IHt9IDxnYW1lX3BhdGg+Ii5mb3JtYXQoc3lzLmFyZ3ZbMF0pKQogICAgICAgIHN5cy5leGl0KDEpCgogICAgZ2FtZV9wYXRoID0gc3lzLmFyZ3ZbMV0KCiAgICBtYWpvciA9IGRldGVjdF9yZW5weV9tYWpvcihnYW1lX3BhdGgpCgogICAgaWYgbWFqb3IgaXMgTm9uZToKICAgICAgICBwcmludCgiRVJST1I6IGltcG9zc2libGUgdG8gZGV0ZWN0IFJlbidQeSB2ZXJzaW9uIGluIDoge30iLmZvcm1hdChnYW1lX3BhdGgpKQogICAgICAgIHN5cy5leGl0KDEpCgogICAgaWYgbWFqb3Igbm90IGluICg2LCA3LCA4KToKICAgICAgICBwcmludCgiRVJST1I6IHVuZXhwZWN0ZWQgUmVuJ1B5IHZlcnNpb24gZGV0ZWN0ZWQgOiB7fSIuZm9ybWF0KG1ham9yKSkKICAgICAgICBzeXMuZXhpdCgxKQoKICAgIHByaW50KG1ham9yKQoKCmlmIF9fbmFtZV9fID09ICJfX21haW5fXyI6CiAgICBtYWluKCkK
)
echo "%PWRSHELL%" -NoProfile -Command "[IO.File]::WriteAllText('%detect_renpy_version_py%.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '%detect_renpy_version_py%.b64'))))" >> "%UNRENLOG%"
"%PWRSHELL%" -NoProfile -Command "[IO.File]::WriteAllText('%detect_renpy_version_py%.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '%detect_renpy_version_py%.b64'))))" %DEBUGREDIR%
if exist "%detect_renpy_version_py%.tmp" (
    del /f /q "%detect_renpy_version_py%.b64" %DEBUGREDIR%
    move /y "%detect_renpy_version_py%.tmp" "%detect_renpy_version_py%" %DEBUGREDIR%
) else (
    call :elog "%RED%!FAIL.%LNG%!%RES%"
    call :elog .
    call :elog "!renpyvers2.%LNG%! !UNACONT.%LNG%!"
    call :elog .
    pause>nul|set/p=.      !ANYKEY.%LNG%!

    call :exitn 3
)

if not exist "%detect_renpy_version_py%" (
    call :elog "%RED%!FAIL.%LNG%!%RES%"
    call :elog .
    call :elog "!renpyvers2.%LNG%! !UNACONT.%LNG%!"
    call :elog .
    pause>nul|set/p=.      !ANYKEY.%LNG%!

    call :exitn 3
) else (
    for /f "delims=" %%A in ('"%PYTHONHOME%\python.exe" %PYNOASSERT% %detect_renpy_version_py% .') do (
        echo %%A | findstr /r "[0-9]" >nul
        if !ERRORLEVEL! EQU 0 (
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

set "renpyvers5.en=You have launched %SCRIPTNAME% but Ren'Py %RENPYVERSION% is found. Please use UnRen-legacy.bat instead."
set "renpyvers5.fr=Vous avez lancé %SCRIPTNAME% mais Ren'Py %RENPYVERSION% a été trouvé. Veuillez utiliser UnRen-legacy.bat à la place."
set "renpyvers5.es=Ha iniciado %SCRIPTNAME% pero se ha encontrado Ren'Py %RENPYVERSION%. Utilice UnRen-legacy.bat en su lugar."
set "renpyvers5.it=Hai avviato %SCRIPTNAME% ma è stato trovato Ren'Py %RENPYVERSION%. Usa invece UnRen-legacy.bat."
set "renpyvers5.de=Sie haben %SCRIPTNAME% gestartet, aber Ren'Py %RENPYVERSION% wurde gefunden. Bitte verwenden Sie stattdessen UnRen-legacy.bat."
set "renpyvers5.ru=Вы запустили %SCRIPTNAME%, но найден Ren'Py %RENPYVERSION%. Пожалуйста, используйте UnRen-legacy.bat вместо этого."
set "renpyvers5.zh=您已启动 %SCRIPTNAME% 但检测到 Ren'Py %RENPYVERSION%。请改用 UnRen-legacy.bat。"

set "renpyvers6.en=You have launched %SCRIPTNAME% but Ren'Py %RENPYVERSION% is found. Please use UnRen-current.bat instead."
set "renpyvers6.fr=Vous avez lancé %SCRIPTNAME% mais Ren'Py %RENPYVERSION% a été trouvé. Veuillez utiliser UnRen-current.bat à la place."
set "renpyvers6.es=Ha iniciado %SCRIPTNAME% pero se ha encontrado Ren'Py %RENPYVERSION%. Utilice UnRen-current.bat en su lugar."
set "renpyvers6.it=Hai avviato %SCRIPTNAME% ma è stato trovato Ren'Py %RENPYVERSION%. Usa invece UnRen-current.bat."
set "renpyvers6.de=Sie haben %SCRIPTNAME% gestartet, aber Ren'Py %RENPYVERSION% wurde gefunden. Bitte verwenden Sie stattdessen UnRen-current.bat."
set "renpyvers6.ru=Вы запустили %SCRIPTNAME%, но найден Ren'Py %RENPYVERSION%. Пожалуйста, используйте UnRen-current.bat вместо этого."
set "renpyvers6.zh=您已启动 %SCRIPTNAME% 但检测到 Ren'Py %RENPYVERSION%。请改用 UnRen-current.bat。"
:: Check to ensure you are using the correct UnRen version
if %RENPYVERSION% GEQ 8 (
    call :elog .
    call :elog "!renpyvers6.%LNG%!"
    call :elog .

    timeout /t 2 /nobreak >nul

    call :exitn 3
)

call :DisplayVars "Init phase"

set "def=5"
set "INITIALIZED=1"

:SkipInit
set "mtitle.en=Working directory: "
set "mtitle.fr=Répertoire de travail : "
set "mtitle.es=Directorio de trabajo: "
set "mtitle.it=Directory di lavoro: "
set "mtitle.de=Aktuelles Verzeichnis: "
set "mtitle.ru=Рабочий каталог: "
set "mtitle.zh=工作目录："

set "choice1.en=Unpack RPA packages."
set "choice1.fr=Décompresser les paquets RPA."
set "choice1.es=Descomprimir paquetes RPA."
set "choice1.it=Decomprimere pacchetti RPA."
set "choice1.de=RPA-Pakete entpacken."
set "choice1.ru=Распаковать пакеты RPA."
set "choice1.zh=解包 RPA 包。"

set "choice2.en=Decompile RPYC files."
set "choice2.fr=Décompiler les fichiers RPYC."
set "choice2.es=Descompilar archivos RPYC."
set "choice2.it=Decompilare i file RPYC."
set "choice2.de=RPYC-Dateien dekompilieren."
set "choice2.ru=Декомпилировать файлы RPYC."
set "choice2.zh=反编译 RPYC 文件。"

set "choice3.en=Deobfuscate when unpacking RPA files %YEL%(Use basic code)."
set "choice3.fr=Déobfusquer lors de la décompression des fichiers RPA %YEL%(Utilise le code de base)."
set "choice3.es=Desofuscar al descomprimir archivos RPA %YEL%(Usar código básico)."
set "choice3.it=Deoffuscare durante la decompressione dei file RPA %YEL%(Utilizzare codice di base)."
set "choice3.de=Deobfuscate beim Entpacken von RPA-Dateien %YEL%(Basiscode verwenden)."
set "choice3.ru=Деобфусцировать при распаковке файлов RPA %YEL%(Использовать базовый код)."
set "choice3.zh=解包 RPA 文件时进行反混淆 %YEL%（使用基础代码）"

set "choice4.en=Deobfuscate when decompile RPYC files %YEL%(Use basic code)."
set "choice4.fr=Déobfusquer lors de la décompilation des fichiers RPYC %YEL%(Utilise le code de base)."
set "choice4.es=Desofuscar al descompilar archivos RPYC %YEL%(Usar código básico)."
set "choice4.it=Deoffuscare durante la decompilazione dei file RPYC %YEL%(Utilizzare codice di base)."
set "choice4.de=Deobfuscate beim Dekompilieren von RPYC-Dateien %YEL%(Basiscode verwenden)."
set "choice4.ru=Деобфусцировать при декомпиляции файлов RPYC %YEL%(Использовать базовый код)."
set "choice4.zh=反编译 RPYC 文件时进行反混淆 %YEL%（使用基础代码）"

set "choice5.en=Unpack and decompile (RPA and RPYC)."
set "choice5.fr=Décompresser et décompiler (RPA et RPYC)."
set "choice5.es=Descomprimir y descompilar (RPA y RPYC)."
set "choice5.it=Decomprimere e decompilare (RPA e RPYC)."
set "choice5.de=RPA- und RPYC-Dateien entpacken und dekompilieren.."
set "choice5.ru=Распаковать и декомпилировать (RPA и RPYC)."
set "choice5.zh=解包并反编译（RPA 和 RPYC）"

set "choice6.en=Deobfuscate, unpack and decompile for both RPA and RPYC files %YEL%(Use basic code)."
set "choice6.fr=Déobfusquer, décompresser et décompiler les fichiers RPA et RPYC %YEL%(Utilise le code de base)."
set "choice6.es=Desofuscar, descomprimir y descompilar archivos RPA y RPYC. %YEL%(Usar código básico)."
set "choice6.it=Deoffuscare, decomprimere e decompilare sia i file RPA che RPYC %YEL%(Utilizzare codice di base)."
set "choice6.de=Entschlüsseln, entpacken und dekompilieren Sie sowohl RPA- als auch RPYC-Dateien. %YEL%(Basiscode verwenden)."
set "choice6.ru=Деобфускация, распаковка и декомпиляция файлов RPA и RPYC %YEL%(Использовать базовый код)."
set "choice6.zh=对 RPA 和 RPYC 文件进行反混淆、解包和反编译 %YEL%（使用基础代码）"

set "choice7.en=Unpack RPA packages using alternative method."
set "choice7.fr=Décompresser les paquets RPA en utilisant une méthode alternative."
set "choice7.es=Descomprimir paquetes RPA utilizando un método alternativo."
set "choice7.it=Decomprimere i pacchetti RPA utilizzando un metodo alternativo."
set "choice7.de=RPA-Pakete mit alternativer Methode entpacken."
set "choice7.ru=Распаковать пакеты RPA с использованием альтернативного метода."
set "choice7.zh=使用替代方法解包 RPA 包。"

set "minfo1.en=The following options are independent of the Ren'Py version."
set "minfo1.fr=Les options suivantes sont indépendantes de la version de Ren'Py."
set "minfo1.es=Las siguientes opciones son independientes de la versión de Ren'Py."
set "minfo1.it=Le seguenti opzioni sono indipendenti dalla versione di Ren'Py."
set "minfo1.de=Die folgenden Optionen sind unabhängig von der Ren'Py-Version."
set "minfo1.ru=Следующие параметры независимы от версии Ren'Py."
set "minfo1.zh=以下选项与 Ren'Py 版本无关。"

set "choicea.en=Enable Console (Shift+O) and Developer menu (Shift+D)."
set "choicea.fr=Activer la Console (Maj+O) et le menu Développeur (Maj+D)."
set "choicea.es=Activar la Consola (Mayús+O) y el menú de desarrollador (Mayús+D)."
set "choicea.it=Attiva la Console (Maiusc+O) e il menu sviluppatore (Maiusc+D)."
set "choicea.de=Aktiviert die Konsole (Umschalt+O) und das Entwicklermenü (Umschalt+D)."
set "choicea.ru=Активируйте консоль (Shift+O) и меню «Разработчик» (Shift+D)."
set "choicea.zh=启用控制台（Shift+O）和开发者菜单（Shift+D）"

set "choiceb.en=Enable debug mode %RED%(Can break your game)."
set "choiceb.fr=Activer le mode debug %RED%(peut casser le jeu)."
set "choiceb.es=Activar el modo debug %RED%(puede romper el juego)."
set "choiceb.it=Attiva la modalità debug %RED%(può rompere il gioco)."
set "choiceb.de=Aktiviert Sie den Debug-Modus %RED%(kann Ihr Spiel beschädigen)."
set "choiceb.ru=Включить режим отладки %RED%(может сломать игру)."
set "choiceb.zh=启用调试模式 %RED%（可能破坏游戏）"

set "choicec.en=Force Skip (Unseen Text, After Choices)."
set "choicec.fr=Forcer Skip (Unseen Text, After Choices)."
set "choicec.es=Forzar Skip (Unseen Text, After Choices)."
set "choicec.it=Forza Skip (Unseen Text, After Choices)."
set "choicec.de=Zwangsweise überspringen (Unseen Text, After Choices)."
set "choicec.ru=Принудить Skip (Unseen Text, After Choices)."
set "choicec.zh=强制跳过（未读文本、选择后）"

set "choiced.en=Force all Skip (Unseen Text, After Choices, Transitions)."
set "choiced.fr=Forcer tous les Skip (Unseen Text, After Choices, Transitions)."
set "choiced.es=Forzar todos los Skip (Unseen Text, After Choices, Transitions)."
set "choiced.it=Forza tutti gli Skip (Unseen Text, After Choices, Transitions)."
set "choiced.de=Zwangsweise überspringen (Unseen Text, After Choices, Transitions)."
set "choiced.ru=Принудить все пропуски (Unseen Text, After Choices, Transitions)."
set "choiced.zh=强制全部跳过（未读文本、选择后、过渡）"

set "choicee.en=Force enable rollback (scroll wheel)."
set "choicee.fr=Activer le "Rollback" (molette de défilement)."
set "choicee.es=Forzar la activación del "Rollback" (rueda de desplazamiento)."
set "choicee.it=Forza l'attivazione del "Rollback" (rotella di scorrimento)."
set "choicee.de=Aktivieren Sie "Rollback" (Scrollrad)."
set "choicee.ru=Принудить активацию "Rollback" (колесо прокрутки)."
set "choicee.zh=强制启用回滚（鼠标滚轮）"

set "choicef.en=Enable Quick Save and Quick Load (Shift+S F5, Shift+L F9)."
set "choicef.fr=Activer "Quick Save" et "Quick Load" (Maj+S F5, Maj+L F9)."
set "choicef.es=Activar "Quick Save" y "Quick Load" (Mayús+S F5, Mayús+L F9)."
set "choicef.it=Attiva "Quick Save" e "Quick Load" (Maiusc+S F5, Maiusc+L F9)."
set "choicef.de=Aktivieren Sie "Quick Save" und "Quick Load" (Umschalt+S F5, Umschalt+L F9)."
set "choicef.ru=Включить "Quick Save" и "Quick Load" (Shift+S F5, Shift+L F9)."
set "choicef.zh=启用快速保存和快速加载（Shift+S F5、Shift+L F9）"

set "choiceg.en=Try forcing the Quick Menu to display.."
set "choiceg.fr=Essayer de forcer l'affichage du "Quick Menu"."
set "choiceg.es=Intenta forzar la visualización del "Quick Menu"."
set "choiceg.it=Prova a forzare la visualizzazione del "Quick Menu"."
set "choiceg.de=Versuche, die Anzeige des "Quick Menu" zu erzwingen."
set "choiceg.ru=Попробуй заставить отобразиться "Quick Menu"."
set "choiceg.zh=尝试强制显示快速菜单。"

set "choicel.en=Rename MC name with a new name."
set "choicel.fr=Renommer le MC name avec un nouveau nom."
set "choicel.es=Renombrar el nombre de MC con un nuevo nombre."
set "choicel.it=Rinomina il nome di MC con un nuovo nome."
set "choicel.de=Den MC-Namen mit einem neuen Namen umbenennen."
set "choicel.ru=Переименовать имя MC с новым именем."
set "choicel.zh=用新名称重命名 MC 名称"

set "choicet.en=Extract text for translation purposes."
set "choicet.fr=Extraire le texte à des fins de traduction."
set "choicet.es=Extraer texto con fines de traducción."
set "choicet.it=Estrai il testo a scopo di traduzione."
set "choicet.de=Text zum Übersetzen extrahieren."
set "choicet.ru=Извлечь текст для перевода."
set "choicet.zh=提取文本用于翻译目的"

set "minfo2.en=The following choices require administrative privileges."
set "minfo2.fr=Les choix suivants nécessitent des privilèges administrateurs."
set "minfo2.es=Las siguientes opciones requieren privilegios administrativos."
set "minfo2.it=Le seguenti opzioni richiedono privilegi amministrativi."
set "minfo2.de=Die folgenden Optionen erfordern administrative Berechtigungen."
set "minfo2.ru=Следующие варианты требуют административных прав."
set "minfo2.zh=以下选项需要管理员权限。"

set "choice+.en=Add a right-click menu entry for folders to run the script."
set "choice+.fr=Ajouter une entrée de menu contextuel pour les dossiers afin d'exécuter le script."
set "choice+.es=Agregar una entrada de menú contextual para las carpetas para ejecutar el script."
set "choice+.it=Aggiungere una voce al menu contestuale delle cartelle per eseguire lo script."
set "choice+.de=Einträge im Kontextmenü für Ordner hinzufügen, um das Skript auszuführen."
set "choice+.ru=Добавить элемент контекстного меню для папок для запуска скрипта."
set "choice+.zh=为文件夹添加右键菜单项以运行脚本。"

set "choice-.en=Remove the right-click menu entry from the registry."
set "choice-.fr=Supprimer l'entrée de menu contextuel du registre."
set "choice-.es=Eliminar la entrada de menú contextual del registro."
set "choice-.it=Rimuovi la voce del menu contestuale dal registro."
set "choice-.de=Einträge im Kontextmenü aus der Registrierung entfernen."
set "choice-.ru=Удалить элемент контекстного меню из реестра."
set "choice-.zh=从注册表中移除右键菜单项。"

set "mquest.en=Your choice (1-7,a-g,l,t,+,- by default [%MDEFS2%]): "
set "mquest.fr=Votre choix (1-7, a-g, l, t, +, -, par défaut [%MDEFS2%]) : "
set "mquest.es=Su elección (1-7,a-g,l,t,+,- por defecto [%MDEFS2%]): "
set "mquest.it=La tua scelta (1-7,a-g,l,t,+,- predefinito [%MDEFS2%]): "
set "mquest.de=Ihre Wahl (1-7,a-g,l,t,+,- für Standard [%MDEFS2%]): "
set "mquest.ru=Ваш выбор (1-7,a-g,l,t,+,- по умолчанию [%MDEFS2%]): "
set "mquest.zh=您的选择（1-7, a-g, l, t, +, -，默认 [%MDEFS2%]）："

set "choicex.en=Exit"
set "choicex.fr=Quitter"
set "choicex.es=Salir"
set "choicex.it=Esci"
set "choicex.de=Beenden"
set "choicex.ru=Выход"
set "choicex.zh=退出"

set "uchoice.en=Unknown choice:"
set "uchoice.fr=Choix inconnu :"
set "uchoice.es=Opción desconocida:"
set "uchoice.it=Scelta sconosciuta:"
set "uchoice.de=Unbekannte Wahl:"
set "uchoice.ru=Неизвестный выбор:"
set "uchoice.zh=未知选择："

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
set "VALID=1234567abctdefglt+-x"

:: Dispatch table: OPTION → LABEL
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
set "extm1.fr=Supprimer les archives RPA après extraction ? Entrer [o/n] (par défaut n) : "
set "extm1.es=¿Eliminar los archivos RPA después de la extracción? Ingrese [s/n] (predeterminado n): "
set "extm1.it=Rimuovere gli archivi RPA dopo l'estrazione? Inserisci [s/n] (predefinito n): "
set "extm1.de=RPA-Archive nach der Extraktion entfernen? Geben Sie [y/n] ein (Standard n): "
set "extm1.ru=Удалить архивы RPA после извлечения? Введите [y/n] (по умолчанию n): "
set "extm1.zh=提取后是否删除 RPA 存档？输入 [y/n]（默认 n）："

set "extm2.en=RPA archives will be moved to %WORKDIR%\rpa."
set "extm2.fr=Les archives RPA seront déplacées vers %WORKDIR%\rpa."
set "extm2.es=Los archivos RPA se moverán a %WORKDIR%\rpa."
set "extm2.it=Gli archivi RPA verranno spostati in %WORKDIR%\rpa."
set "extm2.de=RPA-Archive werden nach %WORKDIR%\rpa verschoben."
set "extm2.ru=Архивы RPA будут перемещены в %WORKDIR%\rpa."
set "extm2.zh=RPA 存档将被移动到 %WORKDIR%\rpa。"

set "extm3.en=RPA archives will be deleted after extraction."
set "extm3.fr=Les archives RPA seront supprimées après extraction."
set "extm3.es=Los archivos RPA se eliminarán después de la extracción."
set "extm3.it=Gli archivi RPA verranno eliminati dopo l'estrazione."
set "extm3.de=RPA-Archive werden nach der Extraktion gelöscht."
set "extm3.ru=Архивы RPA будут удалены после извлечения."
set "extm3.zh=RPA 存档将在提取后被删除。"

set "extm4.en=Unpack all or select RPA archives? Enter [a/s] (default a): "
set "extm4.fr=Décompresser toutes les archives RPA ou sélectionner ? Entrer [t/s] (par défaut t) : "
set "extm4.es=¿Descomprimir todos o seleccionar archivos RPA? Ingrese [t/s] (predeterminado t): "
set "extm4.it=Decomprimere tutti o selezionare gli archivi RPA? Inserisci [t/s] (predefinito t): "
set "extm4.de=Alle oder ausgewählte RPA-Archive entpacken? Geben Sie [a/s] ein (Standard a): "
set "extm4.ru=Извлечь все или выбрать архивы RPA? Введите [a/s] (по умолчанию a): "
set "extm4.zh=解包全部还是选择 RPA 存档？输入 [a/s]（默认 a）："

set "extm5.en=You will select the RPA archives to unpack."
set "extm5.fr=Vous allez sélectionner les archives RPA à décompresser."
set "extm5.es=Seleccionará los archivos RPA para descomprimir."
set "extm5.it=Selezionerai gli archivi RPA da decomprimere."
set "extm5.de=Sie werden die RPA-Archive zum Entpacken auswählen."
set "extm5.ru=Вы выберете архивы RPA для распаковки."
set "extm5.zh=您将选择要解包的 RPA 存档。"

set "extm6.en=All RPA archives will be unpacked."
set "extm6.fr=Toutes les archives RPA seront décompressées."
set "extm6.es=Se descomprimirán todos los archivos RPA."
set "extm6.it=Verranno decompressi tutti gli archivi RPA."
set "extm6.de=Alle RPA-Archive werden entpackt."
set "extm6.ru=Все архивы RPA будут распакованы."
set "extm6.zh=所有 RPA 存档将被解包。"

set "extm7.en=Failed to create:"
set "extm7.fr=Impossible de créer :"
set "extm7.es=No se pudo crear:"
set "extm7.it=Impossibile creare:"
set "extm7.de=Die Erstellung von ist fehlgeschlagen:"
set "extm7.ru=Не удалось создать:"
set "extm7.zh=创建失败："

set "extm8.en=Searching for RPA files in the game directory..."
set "extm8.fr=Recherche de fichiers RPA dans le répertoire du jeu..."
set "extm8.es=Buscando archivos RPA en el directorio del juego..."
set "extm8.it=Cercando file RPA nella directory di gioco..."
set "extm8.de=Suche nach RPA-Dateien im Spieledirectory..."
set "extm8.ru=Поиск файлов RPA в каталоге игры..."
set "extm8.zh=在游戏目录中搜索 RPA 文件..."

set "extm9.en=Creating rpatool and altrpatool..."
set "extm9.fr=Création de rpatool et de altrpatool..."
set "extm9.es=Creando rpatool y altrpatool..."
set "extm9.it=Creazione di rpatool e altrpatool..."
set "extm9.de=Erstellen von rpatool und altrpatool..."
set "extm9.ru=Создание rpatool и altrpatool..."
set "extm9.zh=正在创建 rpatool 和 altrpatool..."

set "extm10.en=RPA extension renamed to:"
set "extm10.fr=Extension RPA renommée en :"
set "extm10.es=Extensión RPA renombrada a:"
set "extm10.it=Estensione RPA rinominata in:"
set "extm10.de=RPA-Erweiterung umbenannt in:"
set "extm10.ru=Расширение RPA переименовано в:"
set "extm10.zh=RPA 扩展名已重命名为："

set "extm11.en=No RPA archive detected."
set "extm11.fr=Aucune archive RPA détectée."
set "extm11.es=No se detectó ningún archivo RPA."
set "extm11.it=Nessun archivio RPA rilevato."
set "extm11.de=Kein RPA-Archiv erkannt."
set "extm11.ru=Архив RPA не обнаружен."
set "extm11.zh=未检测到 RPA 存档。"

set "extm12.en=Error processing RPA files in"
set "extm12.fr=Erreur lors du traitement des fichiers RPA dans"
set "extm12.es=Error al procesar archivos RPA en"
set "extm12.it=Errore durante l'elaborazione dei file RPA in"
set "extm12.de=Fehler beim Verarbeiten von RPA-Dateien in"
set "extm12.ru=Ошибка при обработке файлов RPA в"
set "extm12.zh=处理 RPA 文件时出错："

:: set extm13 to extm16 are set later in the code because of the dynamic variables.

set "extm16.en=Unpacking file:"
set "extm16.fr=Décompression du fichier :"
set "extm16.es=Descomprimiendo archivo:"
set "extm16.it=Decompressione del file:"
set "extm16.de=Entpacken der Datei:"
set "extm16.ru=Распаковка файла:"
set "extm16.zh=正在解包文件："

set "extm17.en=Do you want to unpack the RPA archive:"
set "extm17.fr=Voulez-vous décompresser l'archive RPA :"
set "extm17.es=¿Quieres descomprimir el archivo RPA:"
set "extm17.it=Vuoi decomprimere l'archivio RPA:"
set "extm17.de=Möchten Sie das RPA-Archiv entpacken:"
set "extm17.ru=Вы хотите распаковать архив RPA:"
set "extm17.zh=是否要解包 RPA 存档："

:: set extm18 to extm24 are set later in the code because of the dynamic variables.

set "extm25.en=Extension found:"
set "extm25.fr=Extension trouvée :"
set "extm25.es=Extensión encontrada:"
set "extm25.it=Estensione trovata:"
set "extm25.de=Erweiterung gefunden:"
set "extm25.ru=Найдено расширение:"
set "extm25.zh=找到扩展名："

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
    echo "%PWRSHELL%" -NoProfile -Command "& { [IO.File]::WriteAllBytes('!detect_rpa_ext_py!.tmp', [Convert]::FromBase64String([IO.File]::ReadAllText('!detect_rpa_ext_py!.b64')))}" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "& { [IO.File]::WriteAllBytes('!detect_rpa_ext_py!.tmp', [Convert]::FromBase64String([IO.File]::ReadAllText('!detect_rpa_ext_py!.b64')))}" %DEBUGREDIR%
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
    if !ERRORLEVEL! GEQ 1 (
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
call :choiceEx "!extm4.%LNG%! " "ATS" "A" "%CTIME%" "-rawMsg"
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
:: Creating rpatool...
echo !extm9.%LNG%! >> "%UNRENLOG%"
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
del /f /q "%detect_archive_py%.tmp" %DEBUGREDIR%
del /f /q "%detect_archive_py%.b64" %DEBUGREDIR%
del /f /q "%detect_archive_py%" %DEBUGREDIR%
>"%detect_archive_py%.b64" (
    echo IyEvdXNyL2Jpbi9lbnYgcHl0aG9uDQppbXBvcnQgc3lzDQoNCmRlZiBkZXRlY3RfYXJjaGl2ZV90eXBlKHBhdGgpOg0KICAgIHRyeToNCiAgICAgICAgd2l0aCBvcGVuKHBhdGgsICJyYiIpIGFzIGY6DQogICAgICAgICAgICBoZWFkZXIgPSBmLnJlYWQoOCkNCiAgICAgICAgICAgICMgU3RhbmRhcmQgUlBBIGFyY2hpdmVzIHN0YXJ0IHdpdGggIlJQQS0zLjAiIG9yICJSUEEtMi4wIiBvciAiU1ZBQy0xLjAiDQogICAgICAgICAgICBpZiBoZWFkZXIuc3RhcnRzd2l0aChiIlJQQS0iKSBvciBoZWFkZXIuc3RhcnRzd2l0aChiIlNWQUMtIik6DQogICAgICAgICAgICAgICAgcmV0dXJuIDAgICMgc3RhbmRhcmQNCiAgICAgICAgICAgIGVsc2U6DQogICAgICAgICAgICAgICAgcmV0dXJuIDEgICMgbW9kaWZpZWQgLyB1bmtub3duDQogICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOg0KICAgICAgICAjIFB5dGhvbiAyIGRvZXNuJ3Qgc3VwcG9ydCBmLXN0cmluZ3MsIHNvIHdlIHVzZSBmb3JtYXQoKQ0KICAgICAgICBzeXMuc3RkZXJyLndyaXRlKCJFcnJvcjoge31cbiIuZm9ybWF0KGUpKQ0KICAgICAgICByZXR1cm4gMSAgIyBieSBkZWZhdWx0LCB3ZSBjb25zaWRlciBtb2RpZmllZA0KDQppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOg0KICAgIGlmIGxlbihzeXMuYXJndikgPCAyOg0KICAgICAgICBwcmludCgiVXNhZ2U6IGRldGVjdF9hcmNoaXZlLnB5IDxhcmNoaXZlX2ZpbGU+IikNCiAgICAgICAgc3lzLmV4aXQoMSkNCg0KICAgIGFyY2hpdmVfZmlsZSA9IHN5cy5hcmd2WzFdDQogICAgcmVzdWx0ID0gZGV0ZWN0X2FyY2hpdmVfdHlwZShhcmNoaXZlX2ZpbGUpDQogICAgc3lzLmV4aXQocmVzdWx0KQ0K
)
if not exist "!detect_archive_py!.b64" (
    call :elog " %RED%!FAIL.%LNG%!%RES%!extm7.%LNG%! %YEL%!detect_archive_py!.b64%RES%"
    goto rpa_cleanup
) else (
    echo "%PWRSHELL%" -NoProfile -Command "& { [IO.File]::WriteAllBytes('!detect_archive_py!.tmp', [Convert]::FromBase64String([IO.File]::ReadAllText('!detect_archive_py!.b64')))}" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "& { [IO.File]::WriteAllBytes('!detect_archive_py!.tmp', [Convert]::FromBase64String([IO.File]::ReadAllText('!detect_archive_py!.b64')))}" %DEBUGREDIR%
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
::  Include SVAC-1.0 decoder by JoeLurmel@f95zone
if "!RPATOOL-NEW!" == "y" (
    >"!rpatool!.b64" (
        echo IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMw0KDQpmcm9tIF9fZnV0dXJlX18gaW1wb3J0IHByaW50X2Z1bmN0aW9uDQoNCmltcG9ydCBzeXMNCmltcG9ydCBvcw0KaW1wb3J0IGNvZGVjcw0KaW1wb3J0IHBpY2tsZQ0KaW1wb3J0IGVycm5vDQppbXBvcnQgcmFuZG9tDQp0cnk6DQogICAgaW1wb3J0IHBpY2tsZTUgYXMgcGlja2xlDQpleGNlcHQ6DQogICAgaW1wb3J0IHBpY2tsZQ0KICAgIGlmIHN5cy52ZXJzaW9uX2luZm8gPCAoMywgOCk6DQogICAgICAgIHByaW50KCd3YXJuaW5nOiBwaWNrbGU1IG1vZHVsZSBjb3VsZCBub3QgYmUgbG9hZGVkIGFuZCBQeXRob24gdmVyc2lvbiBpcyA8IDMuOCwnLCBmaWxlPXN5cy5zdGRlcnIpDQogICAgICAgIHByaW50KCcgICAgICAgICBuZXdlciBSZW5cJ1B5IGdhbWVzIG1heSBmYWlsIHRvIHVucGFjayEnLCBmaWxlPXN5cy5zdGRlcnIpDQogICAgICAgIGlmIHN5cy52ZXJzaW9uX2luZm8gPj0gKDMsIDUpOg0KICAgICAgICAgICAgcHJpbnQoJyAgICAgICAgIGlmIHRoaXMgb2NjdXJzLCBmaXggaXQgYnkgaW5zdGFsbGluZyBwaWNrbGU1OicsIGZpbGU9c3lzLnN0ZGVycikNCiAgICAgICAgICAgIHByaW50KCcgICAgICAgICAgICAge30gLW0gcGlwIGluc3RhbGwgcGlja2xlNScuZm9ybWF0KHN5cy5leGVjdXRhYmxlKSwgZmlsZT1zeXMuc3RkZXJyKQ0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgcHJpbnQoJyAgICAgICAgIGlmIHRoaXMgb2NjdXJzLCBwbGVhc2UgdXBncmFkZSB0byBhIG5ld2VyIFB5dGhvbiAoPj0gMy41KS4nLCBmaWxlPXN5cy5zdGRlcnIpDQogICAgICAgIHByaW50KGZpbGU9c3lzLnN0ZGVycikNCg0KDQppZiBzeXMudmVyc2lvbl9pbmZvWzBdID49IDM6DQogICAgZGVmIF91bmljb2RlKHRleHQpOg0KICAgICAgICByZXR1cm4gdGV4dA0KDQogICAgZGVmIF9wcmludGFibGUodGV4dCk6DQogICAgICAgIHJldHVybiB0ZXh0DQoNCiAgICBkZWYgX3VubWFuZ2xlKGRhdGEpOg0KICAgICAgICBpZiB0eXBlKGRhdGEpID09IGJ5dGVzOg0KICAgICAgICAgICAgcmV0dXJuIGRhdGENCiAgICAgICAgZWxzZToNCiAgICAgICAgICAgIHJldHVybiBkYXRhLmVuY29kZSgnbGF0aW4xJykNCg0KICAgIGRlZiBfdW5waWNrbGUoZGF0YSk6DQogICAgICAgICMgU3BlY2lmeSBsYXRpbjEgZW5jb2RpbmcgdG8gcHJldmVudCByYXcgYnl0ZSB2YWx1ZXMgZnJvbSBjYXVzaW5nIGFuIEFTQ0lJIGRlY29kZSBlcnJvci4NCiAgICAgICAgcmV0dXJuIHBpY2tsZS5sb2FkcyhkYXRhLCBlbmNvZGluZz0nbGF0aW4xJykNCmVsaWYgc3lzLnZlcnNpb25faW5mb1swXSA9PSAyOg0KICAgIGRlZiBfdW5pY29kZSh0ZXh0KToNCiAgICAgICAgaWYgaXNpbnN0YW5jZSh0ZXh0LCB1bmljb2RlKToNCiAgICAgICAgICAgIHJldHVybiB0ZXh0DQogICAgICAgIHJldHVybiB0ZXh0LmRlY29kZSgndXRmLTgnKQ0KDQogICAgZGVmIF9wcmludGFibGUodGV4dCk6DQogICAgICAgIHJldHVybiB0ZXh0LmVuY29kZSgndXRmLTgnKQ0KDQogICAgZGVmIF91bm1hbmdsZShkYXRhKToNCiAgICAgICAgcmV0dXJuIGRhdGENCg0KICAgIGRlZiBfdW5waWNrbGUoZGF0YSk6DQogICAgICAgIHJldHVybiBwaWNrbGUubG9hZHMoZGF0YSkNCg0KY2xhc3MgUmVuUHlBcmNoaXZlOg0KICAgIGZpbGUgPSBOb25lDQogICAgaGFuZGxlID0gTm9uZQ0KDQogICAgZmlsZXMgPSB7fQ0KICAgIGluZGV4ZXMgPSB7fQ0KDQogICAgdmVyc2lvbiA9IE5vbmUNCiAgICBwYWRsZW5ndGggPSAwDQogICAga2V5ID0gTm9uZQ0KICAgIHZlcmJvc2UgPSBGYWxzZQ0KDQogICAgUlBBMl9NQUdJQyA9ICdSUEEtMi4wICcNCiAgICBSUEEzX01BR0lDID0gJ1JQQS0zLjAgJw0KICAgIFJQQTNfMl9NQUdJQyA9ICdSUEEtMy4yICcNCiAgICBTVkFDMV9NQUdJQyA9ICdTVkFDLTEuMCAnDQoNCiAgICAjIEZvciBiYWNrd2FyZCBjb21wYXRpYmlsaXR5LCBvdGhlcndpc2UgUHl0aG9uMy1wYWNrZWQgYXJjaGl2ZXMgd29uJ3QgYmUgcmVhZCBieSBQeXRob24yDQogICAgUElDS0xFX1BST1RPQ09MID0gMg0KDQogICAgZGVmIF9faW5pdF9fKHNlbGYsIGZpbGUgPSBOb25lLCB2ZXJzaW9uID0gMywgcGFkbGVuZ3RoID0gMCwga2V5ID0gMHhERUFEQkVFRiwgdmVyYm9zZSA9IEZhbHNlKToNCiAgICAgICAgc2VsZi5wYWRsZW5ndGggPSBwYWRsZW5ndGgNCiAgICAgICAgc2VsZi5rZXkgPSBrZXkNCiAgICAgICAgc2VsZi52ZXJib3NlID0gdmVyYm9zZQ0KDQogICAgICAgIGlmIGZpbGUgaXMgbm90IE5vbmU6DQogICAgICAgICAgICBzZWxmLmxvYWQoZmlsZSkNCiAgICAgICAgZWxzZToNCiAgICAgICAgICAgIHNlbGYudmVyc2lvbiA9IHZlcnNpb24NCg0KICAgIGRlZiBfX2RlbF9fKHNlbGYpOg0KICAgICAgICBpZiBzZWxmLmhhbmRsZSBpcyBub3QgTm9uZToNCiAgICAgICAgICAgIHNlbGYuaGFuZGxlLmNsb3NlKCkNCg0KICAgICMgRGV0ZXJtaW5lIGFyY2hpdmUgdmVyc2lvbi4NCiAgICBkZWYgZ2V0X3ZlcnNpb24oc2VsZik6DQogICAgICAgIHNlbGYuaGFuZGxlLnNlZWsoMCkNCiAgICAgICAgbWFnaWMgPSBzZWxmLmhhbmRsZS5yZWFkbGluZSgpLmRlY29kZSgndXRmLTgnKQ0KDQogICAgICAgIGlmIG1hZ2ljLnN0YXJ0c3dpdGgoc2VsZi5TVkFDMV9NQUdJQyk6DQogICAgICAgICAgICBwYXJ0cyA9IG1hZ2ljLnNwbGl0KCkNCiAgICAgICAgICAgIGlmIGxlbihwYXJ0cykgPT0gNDoNCiAgICAgICAgICAgICAgICByZXR1cm4gNCAgICAgICMgdHJ1ZSBTVkFDLTEuMCBhcmNoaXZlDQogICAgICAgICAgICBlbHNlOg0KICAgICAgICAgICAgICAgIHJldHVybiAzICAgICMgZmFsc2UgU1ZBQywgYWN0dWFsbHkgUlBBLTMuMCB3aXRoIGEgY3VzdG9tIGhlYWRlcg0KICAgICAgICBlbGlmIG1hZ2ljLnN0YXJ0c3dpdGgoc2VsZi5SUEEzXzJfTUFHSUMpOg0KICAgICAgICAgICAgcmV0dXJuIDMuMg0KICAgICAgICBlbGlmIG1hZ2ljLnN0YXJ0c3dpdGgoc2VsZi5SUEEzX01BR0lDKToNCiAgICAgICAgICAgIHJldHVybiAzDQogICAgICAgIGVsaWYgbWFnaWMuc3RhcnRzd2l0aChzZWxmLlJQQTJfTUFHSUMpOg0KICAgICAgICAgICAgcmV0dXJuIDINCiAgICAgICAgZWxpZiBzZWxmLmZpbGUuZW5kc3dpdGgoJy5ycGknKToNCiAgICAgICAgICAgIHJldHVybiAxDQoNCiAgICAgICAgcmFpc2UgVmFsdWVFcnJvcigndGhlIGdpdmVuIGZpbGUgaXMgbm90IGEgdmFsaWQgUmVuXCdQeSBhcmNoaXZlLCBvciBhbiB1bnN1cHBvcnRlZCB2ZXJzaW9uJykNCg0KICAgICMgRXh0cmFjdCBmaWxlIGluZGV4ZXMgZnJvbSBvcGVuZWQgYXJjaGl2ZS4NCiAgICBkZWYgZXh0cmFjdF9pbmRleGVzKHNlbGYpOg0KICAgICAgICBzZWxmLmhhbmRsZS5zZWVrKDApDQogICAgICAgIGluZGV4ZXMgPSBOb25lDQoNCiAgICAgICAgaWYgc2VsZi52ZXJzaW9uIGluIFsyLCAzLCAzLjJdOg0KICAgICAgICAgICAgIyBGZXRjaCBtZXRhZGF0YS4NCiAgICAgICAgICAgIG1ldGFkYXRhID0gc2VsZi5oYW5kbGUucmVhZGxpbmUoKQ0KICAgICAgICAgICAgdmFscyA9IG1ldGFkYXRhLnNwbGl0KCkNCiAgICAgICAgICAgIG9mZnNldCA9IGludCh2YWxzWzFdLCAxNikNCiAgICAgICAgICAgIGlmIHNlbGYudmVyc2lvbiA9PSAzOg0KICAgICAgICAgICAgICAgIHNlbGYua2V5ID0gMA0KICAgICAgICAgICAgICAgIGZvciBzdWJrZXkgaW4gdmFsc1syOl06DQogICAgICAgICAgICAgICAgICAgIHNlbGYua2V5IF49IGludChzdWJrZXksIDE2KQ0KICAgICAgICAgICAgZWxpZiBzZWxmLnZlcnNpb24gPT0gMy4yOg0KICAgICAgICAgICAgICAgIHNlbGYua2V5ID0gMA0KICAgICAgICAgICAgICAgIGZvciBzdWJrZXkgaW4gdmFsc1szOl06DQogICAgICAgICAgICAgICAgICAgIHNlbGYua2V5IF49IGludChzdWJrZXksIDE2KQ0KDQogICAgICAgICAgICAjIExvYWQgaW4gaW5kZXhlcy4NCiAgICAgICAgICAgIHNlbGYuaGFuZGxlLnNlZWsob2Zmc2V0KQ0KICAgICAgICAgICAgY29udGVudHMgPSBjb2RlY3MuZGVjb2RlKHNlbGYuaGFuZGxlLnJlYWQoKSwgJ3psaWInKQ0KICAgICAgICAgICAgaW5kZXhlcyA9IF91bnBpY2tsZShjb250ZW50cykNCg0KICAgICAgICAgICAgIyBEZW9iZnVzY2F0ZSBpbmRleGVzLg0KICAgICAgICAgICAgaWYgc2VsZi52ZXJzaW9uIGluIFszLCAzLjJdOg0KICAgICAgICAgICAgICAgIG9iZnVzY2F0ZWRfaW5kZXhlcyA9IGluZGV4ZXMNCiAgICAgICAgICAgICAgICBpbmRleGVzID0ge30NCiAgICAgICAgICAgICAgICBmb3IgaSBpbiBvYmZ1c2NhdGVkX2luZGV4ZXMua2V5cygpOg0KICAgICAgICAgICAgICAgICAgICBpZiBsZW4ob2JmdXNjYXRlZF9pbmRleGVzW2ldWzBdKSA9PSAyOg0KICAgICAgICAgICAgICAgICAgICAgICAgaW5kZXhlc1tpXSA9IFsgKG9mZnNldCBeIHNlbGYua2V5LCBsZW5ndGggXiBzZWxmLmtleSkgZm9yIG9mZnNldCwgbGVuZ3RoIGluIG9iZnVzY2F0ZWRfaW5kZXhlc1tpXSBdDQogICAgICAgICAgICAgICAgICAgIGVsc2U6DQogICAgICAgICAgICAgICAgICAgICAgICBpbmRleGVzW2ldID0gWyAob2Zmc2V0IF4gc2VsZi5rZXksIGxlbmd0aCBeIHNlbGYua2V5LCBwcmVmaXgpIGZvciBvZmZzZXQsIGxlbmd0aCwgcHJlZml4IGluIG9iZnVzY2F0ZWRfaW5kZXhlc1tpXSBdDQogICAgICAgIGVsc2U6DQogICAgICAgICAgICBpbmRleGVzID0gcGlja2xlLmxvYWRzKGNvZGVjcy5kZWNvZGUoc2VsZi5oYW5kbGUucmVhZCgpLCAnemxpYicpKQ0KDQogICAgICAgIHJldHVybiBpbmRleGVzDQoNCiAgICAjIEdlbmVyYXRlIHBzZXVkb3JhbmRvbSBwYWRkaW5nIChmb3Igd2hhdGV2ZXIgcmVhc29uKS4NCiAgICBkZWYgZ2VuZXJhdGVfcGFkZGluZyhzZWxmKToNCiAgICAgICAgbGVuZ3RoID0gcmFuZG9tLnJhbmRpbnQoMSwgc2VsZi5wYWRsZW5ndGgpDQoNCiAgICAgICAgcGFkZGluZyA9ICcnDQogICAgICAgIHdoaWxlIGxlbmd0aCA+IDA6DQogICAgICAgICAgICBwYWRkaW5nICs9IGNocihyYW5kb20ucmFuZGludCgxLCAyNTUpKQ0KICAgICAgICAgICAgbGVuZ3RoIC09IDENCg0KICAgICAgICByZXR1cm4gYnl0ZXMocGFkZGluZywgJ3V0Zi04JykNCg0KICAgICMgQ29udmVydHMgYSBmaWxlbmFtZSB0byBhcmNoaXZlIGZvcm1hdC4NCiAgICBkZWYgY29udmVydF9maWxlbmFtZShzZWxmLCBmaWxlbmFtZSk6DQogICAgICAgIChkcml2ZSwgZmlsZW5hbWUpID0gb3MucGF0aC5zcGxpdGRyaXZlKG9zLnBhdGgubm9ybXBhdGgoZmlsZW5hbWUpLnJlcGxhY2Uob3Muc2VwLCAnLycpKQ0KICAgICAgICByZXR1cm4gZmlsZW5hbWUNCg0KICAgICMgRGVidWcgKHZlcmJvc2UpIG1lc3NhZ2VzLg0KICAgIGRlZiB2ZXJib3NlX3ByaW50KHNlbGYsIG1lc3NhZ2UpOg0KICAgICAgICBpZiBzZWxmLnZlcmJvc2U6DQogICAgICAgICAgICBwcmludChtZXNzYWdlKQ0KDQoNCiAgICAjIExpc3QgZmlsZXMgaW4gYXJjaGl2ZSBhbmQgY3VycmVudCBpbnRlcm5hbCBzdG9yYWdlLg0KICAgIGRlZiBsaXN0KHNlbGYpOg0KICAgICAgICByZXR1cm4gbGlzdChzZWxmLmluZGV4ZXMua2V5cygpKSArIGxpc3Qoc2VsZi5maWxlcy5rZXlzKCkpDQoNCiAgICAjIENoZWNrIGlmIGEgZmlsZSBleGlzdHMgaW4gdGhlIGFyY2hpdmUuDQogICAgZGVmIGhhc19maWxlKHNlbGYsIGZpbGVuYW1lKToNCiAgICAgICAgZmlsZW5hbWUgPSBfdW5pY29kZShmaWxlbmFtZSkNCiAgICAgICAgcmV0dXJuIGZpbGVuYW1lIGluIHNlbGYuaW5kZXhlcy5rZXlzKCkgb3IgZmlsZW5hbWUgaW4gc2VsZi5maWxlcy5rZXlzKCkNCg0KICAgICMgUmVhZCBmaWxlIGZyb20gYXJjaGl2ZSBvciBpbnRlcm5hbCBzdG9yYWdlLg0KICAgIGRlZiByZWFkKHNlbGYsIGZpbGVuYW1lKToNCiAgICAgICAgZmlsZW5hbWUgPSBzZWxmLmNvbnZlcnRfZmlsZW5hbWUoX3VuaWNvZGUoZmlsZW5hbWUpKQ0KDQogICAgICAgICMgQ2hlY2sgaWYgdGhlIGZpbGUgZXhpc3RzIGluIG91ciBpbmRleGVzLg0KICAgICAgICBpZiBmaWxlbmFtZSBub3QgaW4gc2VsZi5maWxlcyBhbmQgZmlsZW5hbWUgbm90IGluIHNlbGYuaW5kZXhlczoNCiAgICAgICAgICAgIHJhaXNlIElPRXJyb3IoZXJybm8uRU5PRU5ULCAndGhlIHJlcXVlc3RlZCBmaWxlIHswfSBkb2VzIG5vdCBleGlzdCBpbiB0aGUgZ2l2ZW4gUmVuXCdQeSBhcmN
        echo oaXZlJy5mb3JtYXQoDQogICAgICAgICAgICAgICAgX3ByaW50YWJsZShmaWxlbmFtZSkpKQ0KDQogICAgICAgICMgSWYgaXQncyBpbiBvdXIgb3BlbmVkIGFyY2hpdmUgaW5kZXgsIGFuZCBvdXIgYXJjaGl2ZSBoYW5kbGUgaXNuJ3QgdmFsaWQsIHNvbWV0aGluZyBpcyBvYnZpb3VzbHkgd3JvbmcuDQogICAgICAgIGlmIGZpbGVuYW1lIG5vdCBpbiBzZWxmLmZpbGVzIGFuZCBmaWxlbmFtZSBpbiBzZWxmLmluZGV4ZXMgYW5kIHNlbGYuaGFuZGxlIGlzIE5vbmU6DQogICAgICAgICAgICByYWlzZSBJT0Vycm9yKGVycm5vLkVOT0VOVCwgJ3RoZSByZXF1ZXN0ZWQgZmlsZSB7MH0gZG9lcyBub3QgZXhpc3QgaW4gdGhlIGdpdmVuIFJlblwnUHkgYXJjaGl2ZScuZm9ybWF0KA0KICAgICAgICAgICAgICAgIF9wcmludGFibGUoZmlsZW5hbWUpKSkNCg0KICAgICAgICAjIENoZWNrIG91ciBzaW1wbGlmaWVkIGludGVybmFsIGluZGV4ZXMgZmlyc3QsIGluIGNhc2Ugc29tZW9uZSB3YW50cyB0byByZWFkIGEgZmlsZSB0aGV5IGFkZGVkIGJlZm9yZSB3aXRob3V0IHNhdmluZywgZm9yIHNvbWUgdW5ob2x5IHJlYXNvbi4NCiAgICAgICAgaWYgZmlsZW5hbWUgaW4gc2VsZi5maWxlczoNCiAgICAgICAgICAgIHNlbGYudmVyYm9zZV9wcmludCgnUmVhZGluZyBmaWxlIHswfSBmcm9tIGludGVybmFsIHN0b3JhZ2UuLi4nLmZvcm1hdChfcHJpbnRhYmxlKGZpbGVuYW1lKSkpDQogICAgICAgICAgICByZXR1cm4gc2VsZi5maWxlc1tmaWxlbmFtZV0NCiAgICAgICAgIyBXZSBuZWVkIHRvIHJlYWQgdGhlIGZpbGUgZnJvbSBvdXIgb3BlbiBhcmNoaXZlLg0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgIyBSZWFkIG9mZnNldCBhbmQgbGVuZ3RoLCBzZWVrIHRvIHRoZSBvZmZzZXQgYW5kIHJlYWQgdGhlIGZpbGUgY29udGVudHMuDQogICAgICAgICAgICBpZiBsZW4oc2VsZi5pbmRleGVzW2ZpbGVuYW1lXVswXSkgPT0gMzoNCiAgICAgICAgICAgICAgICAob2Zmc2V0LCBsZW5ndGgsIHByZWZpeCkgPSBzZWxmLmluZGV4ZXNbZmlsZW5hbWVdWzBdDQogICAgICAgICAgICBlbHNlOg0KICAgICAgICAgICAgICAgIChvZmZzZXQsIGxlbmd0aCkgPSBzZWxmLmluZGV4ZXNbZmlsZW5hbWVdWzBdDQogICAgICAgICAgICAgICAgcHJlZml4ID0gJycNCg0KICAgICAgICAgICAgc2VsZi52ZXJib3NlX3ByaW50KCdSZWFkaW5nIGZpbGUgezB9IGZyb20gZGF0YSBmaWxlIHsxfS4uLiAob2Zmc2V0ID0gezJ9LCBsZW5ndGggPSB7M30gYnl0ZXMpJy5mb3JtYXQoDQogICAgICAgICAgICAgICAgX3ByaW50YWJsZShmaWxlbmFtZSksIHNlbGYuZmlsZSwgb2Zmc2V0LCBsZW5ndGgpKQ0KICAgICAgICAgICAgc2VsZi5oYW5kbGUuc2VlayhvZmZzZXQpDQogICAgICAgICAgICByZXR1cm4gX3VubWFuZ2xlKHByZWZpeCkgKyBzZWxmLmhhbmRsZS5yZWFkKGxlbmd0aCAtIGxlbihwcmVmaXgpKQ0KDQogICAgIyBNb2RpZnkgYSBmaWxlIGluIGFyY2hpdmUgb3IgaW50ZXJuYWwgc3RvcmFnZS4NCiAgICBkZWYgY2hhbmdlKHNlbGYsIGZpbGVuYW1lLCBjb250ZW50cyk6DQogICAgICAgIGZpbGVuYW1lID0gX3VuaWNvZGUoZmlsZW5hbWUpDQoNCiAgICAgICAgIyBPdXIgJ2NoYW5nZScgaXMgYmFzaWNhbGx5IHJlbW92aW5nIHRoZSBmaWxlIGZyb20gb3VyIGluZGV4ZXMgZmlyc3QsIGFuZCB0aGVuIHJlLWFkZGluZyBpdC4NCiAgICAgICAgc2VsZi5yZW1vdmUoZmlsZW5hbWUpDQogICAgICAgIHNlbGYuYWRkKGZpbGVuYW1lLCBjb250ZW50cykNCg0KICAgICMgQWRkIGEgZmlsZSB0byB0aGUgaW50ZXJuYWwgc3RvcmFnZS4NCiAgICBkZWYgYWRkKHNlbGYsIGZpbGVuYW1lLCBjb250ZW50cyk6DQogICAgICAgIGZpbGVuYW1lID0gc2VsZi5jb252ZXJ0X2ZpbGVuYW1lKF91bmljb2RlKGZpbGVuYW1lKSkNCiAgICAgICAgaWYgZmlsZW5hbWUgaW4gc2VsZi5maWxlcyBvciBmaWxlbmFtZSBpbiBzZWxmLmluZGV4ZXM6DQogICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCdmaWxlIHswfSBhbHJlYWR5IGV4aXN0cyBpbiBhcmNoaXZlJy5mb3JtYXQoX3ByaW50YWJsZShmaWxlbmFtZSkpKQ0KDQogICAgICAgIHNlbGYudmVyYm9zZV9wcmludCgnQWRkaW5nIGZpbGUgezB9IHRvIGFyY2hpdmUuLi4gKGxlbmd0aCA9IHsxfSBieXRlcyknLmZvcm1hdCgNCiAgICAgICAgICAgIF9wcmludGFibGUoZmlsZW5hbWUpLCBsZW4oY29udGVudHMpKSkNCiAgICAgICAgc2VsZi5maWxlc1tmaWxlbmFtZV0gPSBjb250ZW50cw0KDQogICAgIyBSZW1vdmUgYSBmaWxlIGZyb20gYXJjaGl2ZSBvciBpbnRlcm5hbCBzdG9yYWdlLg0KICAgIGRlZiByZW1vdmUoc2VsZiwgZmlsZW5hbWUpOg0KICAgICAgICBmaWxlbmFtZSA9IF91bmljb2RlKGZpbGVuYW1lKQ0KICAgICAgICBpZiBmaWxlbmFtZSBpbiBzZWxmLmZpbGVzOg0KICAgICAgICAgICAgc2VsZi52ZXJib3NlX3ByaW50KCdSZW1vdmluZyBmaWxlIHswfSBmcm9tIGludGVybmFsIHN0b3JhZ2UuLi4nLmZvcm1hdChfcHJpbnRhYmxlKGZpbGVuYW1lKSkpDQogICAgICAgICAgICBkZWwgc2VsZi5maWxlc1tmaWxlbmFtZV0NCiAgICAgICAgZWxpZiBmaWxlbmFtZSBpbiBzZWxmLmluZGV4ZXM6DQogICAgICAgICAgICBzZWxmLnZlcmJvc2VfcHJpbnQoJ1JlbW92aW5nIGZpbGUgezB9IGZyb20gYXJjaGl2ZSBpbmRleGVzLi4uJy5mb3JtYXQoX3ByaW50YWJsZShmaWxlbmFtZSkpKQ0KICAgICAgICAgICAgZGVsIHNlbGYuaW5kZXhlc1tmaWxlbmFtZV0NCiAgICAgICAgZWxzZToNCiAgICAgICAgICAgIHJhaXNlIElPRXJyb3IoZXJybm8uRU5PRU5ULCAndGhlIHJlcXVlc3RlZCBmaWxlIHswfSBkb2VzIG5vdCBleGlzdCBpbiB0aGlzIGFyY2hpdmUnLmZvcm1hdChfcHJpbnRhYmxlKGZpbGVuYW1lKSkpDQoNCiAgICAjIExvYWQgYXJjaGl2ZS4NCiAgICBkZWYgbG9hZChzZWxmLCBmaWxlbmFtZSk6DQogICAgICAgIGZpbGVuYW1lID0gX3VuaWNvZGUoZmlsZW5hbWUpDQoNCiAgICAgICAgaWYgc2VsZi5oYW5kbGUgaXMgbm90IE5vbmU6DQogICAgICAgICAgICBzZWxmLmhhbmRsZS5jbG9zZSgpDQogICAgICAgIHNlbGYuZmlsZSA9IGZpbGVuYW1lDQogICAgICAgIHNlbGYuZmlsZXMgPSB7fQ0KICAgICAgICBzZWxmLmhhbmRsZSA9IG9wZW4oc2VsZi5maWxlLCAncmInKQ0KICAgICAgICBzZWxmLnZlcnNpb24gPSBzZWxmLmdldF92ZXJzaW9uKCkNCiAgICAgICAgaWYgc2VsZi52ZXJzaW9uIGluIFsxLCAyLCAzLCAzLjJdOg0KICAgICAgICAgICAgc2VsZi5pbmRleGVzID0gc2VsZi5leHRyYWN0X2luZGV4ZXMoKQ0KICAgICAgICBlbGlmIHNlbGYudmVyc2lvbiA9PSA0Og0KICAgICAgICAgICAgc2VsZi5pbmRleGVzID0gc2VsZi5leHRyYWN0X3N2YWMxX2luZGV4ZXMoKQ0KICAgICAgICBlbHNlOg0KICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcigndW5zdXBwb3J0ZWQgUmVuXCdQeSBhcmNoaXZlIHZlcnNpb24nKQ0KDQogICAgIyBFeHRyYWN0IGZpbGUgaW5kZXhlcyBmcm9tIG9wZW5lZCBTVkFDLTEuMCBhcmNoaXZlLg0KICAgIGRlZiBleHRyYWN0X3N2YWMxX2luZGV4ZXMoc2VsZik6DQogICAgICAgIGltcG9ydCBqc29uLCB6bGliDQoNCiAgICAgICAgc2VsZi5oYW5kbGUuc2VlaygwKQ0KICAgICAgICBoZWFkZXIgPSBzZWxmLmhhbmRsZS5yZWFkbGluZSgpLmRlY29kZSgndXRmLTgnKQ0KICAgICAgICBwYXJ0cyA9IGhlYWRlci5zcGxpdCgpDQoNCiAgICAgICAgIyBwYXJ0c1sxXSA9IG9mZnNldCBoZXgNCiAgICAgICAgaW5kZXhfb2Zmc2V0ID0gaW50KHBhcnRzWzFdLCAxNikNCg0KICAgICAgICAjIEdvIHRvIHRoZSBPZ2dTIGJsb2NrIGNvbnRhaW5pbmcgdGhlIGNvbXByZXNzZWQgSlNPTiBkYXRhLA0KICAgICAgICAjIHJlYWQgaXQgYW5kIHRyeSB0byBkZWNvZGUgaXQgYXMgemxpYiBmaXJzdCwgaWYgdGhhdCBmYWlscywNCiAgICAgICAgIyBkZWNvZGUgaXQgYXMgT2dnIGVuY2Fwc3VsYXRlZCBWb3JiaXMgY29tbWVudHMuDQogICAgICAgIHNlbGYuaGFuZGxlLnNlZWsoaW5kZXhfb2Zmc2V0KQ0KICAgICAgICBjb21wcmVzc2VkID0gc2VsZi5oYW5kbGUucmVhZCgpDQoNCiAgICAgICAgdHJ5Og0KICAgICAgICAgICAgIyBWYXJpYW50IEI6IERpcmVjdCB6bGliIHN0cmVhbSwgbm8gT2dnIGVuY2Fwc3VsYXRpb24NCiAgICAgICAgICAgIGpzb25fZGF0YSA9IHpsaWIuZGVjb21wcmVzcyhjb21wcmVzc2VkKS5kZWNvZGUoInV0Zi04IikNCiAgICAgICAgZXhjZXB0Og0KICAgICAgICAgICAgIyBWYXJpYW50IEE6IEVuY2Fwc3VsYXRlZCBPZ2cgc3RyZWFtLCBkZWNvZGUgaXQgdG8gZXh0cmFjdCB0aGUgSlNPTiBmcm9tIFZvcmJpcyBjb21tZW50cw0KICAgICAgICAgICAganNvbl9kYXRhID0gc2VsZi5kZWNvZGVfc3ZhYzFfb2dnKGNvbXByZXNzZWQpDQoNCiAgICAgICAgIyBEZWNvZGUgVm9yYmlzIHN0cmVhbSDihpIgSlNPTiBkYXRhDQogICAgICAgIGpzb25fZGF0YSA9IHNlbGYuZGVjb2RlX3N2YWMxX29nZyhvZ2dfZGF0YSkNCg0KICAgICAgICAjIExvYWQgSlNPTiBkYXRhIGludG8gYSBQeXRob24gZGljdA0KICAgICAgICByYXcgPSBqc29uLmxvYWRzKGpzb25fZGF0YSkNCg0KICAgICAgICAjIENvbnZlcnQgdG8gaW50ZXJuYWwgaW5kZXggZm9ybWF0DQogICAgICAgIGluZGV4ZXMgPSB7fQ0KICAgICAgICBmb3IgbmFtZSwgaW5mbyBpbiByYXdbImZpbGVzIl0uaXRlbXMoKToNCiAgICAgICAgICAgIG9mZnNldCwgbGVuZ3RoID0gaW5mbw0KICAgICAgICAgICAgaW5kZXhlc1tuYW1lXSA9IFsob2Zmc2V0LCBsZW5ndGgpXQ0KDQogICAgICAgIHJldHVybiBpbmRleGVzDQoNCiAgICBkZWYgZGVjb2RlX3N2YWMxX29nZyhzZWxmLCBkYXRhKToNCiAgICAgICAgIyBTZWFyY2ggZm9yIHBhY2tldCB0eXBlIDMg4oCcdm9yYmlz4oCdLCB3aGljaCBjb250YWlucyB0aGUgY29tbWVudHMgd2l0aCB0aGUgSlNPTiBkYXRhLg0KICAgICAgICBtYXJrZXIgPSBiIlx4MDN2b3JiaXMiDQogICAgICAgIHBvcyA9IGRhdGEuZmluZChtYXJrZXIpDQogICAgICAgIGlmIHBvcyA9PSAtMToNCiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoIlNWQUMtMS4wOiBWb3JiaXMgcGFja2FnZSAodHlwZSAzKSBub3QgZm91bmQgaW4gT2dnIHN0cmVhbSIpDQoNCiAgICAgICAgIyBBZnRlciB0aGUgbWFya2VyLCB0aGVyZSBpcyBhIOKAnHZlbmRvcl9sZW5ndGjigJ0gZmllbGQgKDQgbGl0dGxlLWVuZGlhbiBieXRlcykuDQogICAgICAgIHZlbmRvcl9sZW4gPSBpbnQuZnJvbV9ieXRlcyhkYXRhW3Bvcys3OnBvcysxMV0sICJsaXR0bGUiKQ0KDQogICAgICAgICMgU2tpcCB0aGUgdmVuZG9yIHN0cmluZyAodmVuZG9yX2xlbmd0aCBieXRlcykgdG8gZ2V0IHRvIHRoZSBjb21tZW50IGxpc3QuDQogICAgICAgIGNvbW1lbnRfc3RhcnQgPSBwb3MgKyAxMSArIHZlbmRvcl9sZW4NCg0KICAgICAgICAjIFJlYWQgdGhlIG51bWJlciBvZiBjb21tZW50cyAoNCBieXRlcyBMRSkNCiAgICAgICAgY29tbWVudF9jb3VudCA9IGludC5mcm9tX2J5dGVzKGRhdGFbY29tbWVudF9zdGFydDpjb21tZW50X3N0YXJ0KzRdLCAibGl0dGxlIikNCiAgICAgICAgcCA9IGNvbW1lbnRfc3RhcnQgKyA0DQoNCiAgICAgICAgIyBCcm93c2UgVm9yYmlzIGNvbW1lbnRzIHRvIGZpbmQgdGhlIG9uZSBzdGFydGluZyB3aXRoICJKU09OPSIsIHdoaWNoIGNvbnRhaW5zIHRoZSBKU09OIGRhdGEuDQogICAgICAgIGZvciBfIGluIHJhbmdlKGNvbW1lbnRfY291bnQpOg0KICAgICAgICAgICAgbGVuZ3RoID0gaW50LmZyb21fYnl0ZXMoZGF0YVtwOnArNF0sICJsaXR0bGUiKQ0KICAgICAgICAgICAgcCArPSA0DQogICAgICAgICAgICBjb21tZW50ID0gZGF0YVtwOnArbGVuZ3RoXQ0KICAgICAgICAgICAgcCArPSBsZW5ndGgNCg0KICAgICAgICAgICAgIyBUaGUgSlNPTiBpcyBpbiBhIGNvbW1lbnQuDQogICAgICAgICAgICBpZiBjb21tZW50LnN0YXJ0c3dpdGgoYiJKU09OPSIpOg0KICAgICAgICAgICAgICAgIHJldHVybiBjb21tZW50WzU6XS5kZWNvZGUoInV0Zi04IikNCg0KICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJTVkFDLTEuMDogSlNPTiBub3QgZm91bmQgaW4gVm9yYmlzIGNvbW1lbnRzLiIpDQoNCiAgICAjIFNhdmUgY3VycmVudCBzdGF0ZSBpbnRvIGEgbmV3IGZpbG
        echo UsIG1lcmdpbmcgYXJjaGl2ZSBhbmQgaW50ZXJuYWwgc3RvcmFnZSwgcmVidWlsZGluZyBpbmRleGVzLCBhbmQgb3B0aW9uYWxseSBzYXZpbmcgaW4gYW5vdGhlciBmb3JtYXQgdmVyc2lvbi4NCiAgICBkZWYgc2F2ZShzZWxmLCBmaWxlbmFtZSA9IE5vbmUpOg0KICAgICAgICBmaWxlbmFtZSA9IF91bmljb2RlKGZpbGVuYW1lKQ0KDQogICAgICAgIGlmIGZpbGVuYW1lIGlzIE5vbmU6DQogICAgICAgICAgICBmaWxlbmFtZSA9IHNlbGYuZmlsZQ0KICAgICAgICBpZiBmaWxlbmFtZSBpcyBOb25lOg0KICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignbm8gdGFyZ2V0IGZpbGUgZm91bmQgZm9yIHNhdmluZyBhcmNoaXZlJykNCiAgICAgICAgaWYgc2VsZi52ZXJzaW9uICE9IDIgYW5kIHNlbGYudmVyc2lvbiAhPSAzOg0KICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignc2F2aW5nIGlzIG9ubHkgc3VwcG9ydGVkIGZvciB2ZXJzaW9uIDIgYW5kIDMgYXJjaGl2ZXMnKQ0KDQogICAgICAgIHNlbGYudmVyYm9zZV9wcmludCgnUmVidWlsZGluZyBhcmNoaXZlIGluZGV4Li4uJykNCiAgICAgICAgIyBGaWxsIG91ciBvd24gZmlsZXMgc3RydWN0dXJlIHdpdGggdGhlIGZpbGVzIGFkZGVkIG9yIGNoYW5nZWQgaW4gdGhpcyBzZXNzaW9uLg0KICAgICAgICBmaWxlcyA9IHNlbGYuZmlsZXMNCiAgICAgICAgIyBGaXJzdCwgcmVhZCBmaWxlcyBmcm9tIHRoZSBjdXJyZW50IGFyY2hpdmUgaW50byBvdXIgZmlsZXMgc3RydWN0dXJlLg0KICAgICAgICBmb3IgZmlsZSBpbiBsaXN0KHNlbGYuaW5kZXhlcy5rZXlzKCkpOg0KICAgICAgICAgICAgY29udGVudCA9IHNlbGYucmVhZChmaWxlKQ0KICAgICAgICAgICAgIyBSZW1vdmUgZnJvbSBpbmRleGVzIGFycmF5IG9uY2UgcmVhZCwgYWRkIHRvIG91ciBvd24gYXJyYXkuDQogICAgICAgICAgICBkZWwgc2VsZi5pbmRleGVzW2ZpbGVdDQogICAgICAgICAgICBmaWxlc1tmaWxlXSA9IGNvbnRlbnQNCg0KICAgICAgICAjIFByZWRpY3QgaGVhZGVyIGxlbmd0aCwgd2UnbGwgd3JpdGUgdGhhdCBvbmUgbGFzdC4NCiAgICAgICAgb2Zmc2V0ID0gMA0KICAgICAgICBpZiBzZWxmLnZlcnNpb24gPT0gMzoNCiAgICAgICAgICAgIG9mZnNldCA9IDM0DQogICAgICAgIGVsaWYgc2VsZi52ZXJzaW9uID09IDI6DQogICAgICAgICAgICBvZmZzZXQgPSAyNQ0KICAgICAgICBhcmNoaXZlID0gb3BlbihmaWxlbmFtZSwgJ3diJykNCiAgICAgICAgYXJjaGl2ZS5zZWVrKG9mZnNldCkNCg0KICAgICAgICAjIEJ1aWxkIG91ciBvd24gaW5kZXhlcyB3aGlsZSB3cml0aW5nIGZpbGVzIHRvIHRoZSBhcmNoaXZlLg0KICAgICAgICBpbmRleGVzID0ge30NCiAgICAgICAgc2VsZi52ZXJib3NlX3ByaW50KCdXcml0aW5nIGZpbGVzIHRvIGFyY2hpdmUgZmlsZS4uLicpDQogICAgICAgIGZvciBmaWxlLCBjb250ZW50IGluIGZpbGVzLml0ZW1zKCk6DQogICAgICAgICAgICAjIEdlbmVyYXRlIHJhbmRvbSBwYWRkaW5nLCBmb3Igd2hhdGV2ZXIgcmVhc29uLg0KICAgICAgICAgICAgaWYgc2VsZi5wYWRsZW5ndGggPiAwOg0KICAgICAgICAgICAgICAgIHBhZGRpbmcgPSBzZWxmLmdlbmVyYXRlX3BhZGRpbmcoKQ0KICAgICAgICAgICAgICAgIGFyY2hpdmUud3JpdGUocGFkZGluZykNCiAgICAgICAgICAgICAgICBvZmZzZXQgKz0gbGVuKHBhZGRpbmcpDQoNCiAgICAgICAgICAgIGFyY2hpdmUud3JpdGUoY29udGVudCkNCiAgICAgICAgICAgICMgVXBkYXRlIGluZGV4Lg0KICAgICAgICAgICAgaWYgc2VsZi52ZXJzaW9uID09IDM6DQogICAgICAgICAgICAgICAgaW5kZXhlc1tmaWxlXSA9IFsgKG9mZnNldCBeIHNlbGYua2V5LCBsZW4oY29udGVudCkgXiBzZWxmLmtleSkgXQ0KICAgICAgICAgICAgZWxpZiBzZWxmLnZlcnNpb24gPT0gMjoNCiAgICAgICAgICAgICAgICBpbmRleGVzW2ZpbGVdID0gWyAob2Zmc2V0LCBsZW4oY29udGVudCkpIF0NCiAgICAgICAgICAgIG9mZnNldCArPSBsZW4oY29udGVudCkNCg0KICAgICAgICAjIFdyaXRlIHRoZSBpbmRleGVzLg0KICAgICAgICBzZWxmLnZlcmJvc2VfcHJpbnQoJ1dyaXRpbmcgYXJjaGl2ZSBpbmRleCB0byBhcmNoaXZlIGZpbGUuLi4nKQ0KICAgICAgICBhcmNoaXZlLndyaXRlKGNvZGVjcy5lbmNvZGUocGlja2xlLmR1bXBzKGluZGV4ZXMsIHNlbGYuUElDS0xFX1BST1RPQ09MKSwgJ3psaWInKSkNCiAgICAgICAgIyBOb3cgd3JpdGUgdGhlIGhlYWRlci4NCiAgICAgICAgc2VsZi52ZXJib3NlX3ByaW50KCdXcml0aW5nIGhlYWRlciB0byBhcmNoaXZlIGZpbGUuLi4gKHZlcnNpb24gPSBSUEF2ezB9KScuZm9ybWF0KHNlbGYudmVyc2lvbikpDQogICAgICAgIGFyY2hpdmUuc2VlaygwKQ0KICAgICAgICBpZiBzZWxmLnZlcnNpb24gPT0gMzoNCiAgICAgICAgICAgIGFyY2hpdmUud3JpdGUoY29kZWNzLmVuY29kZSgne317OjAxNnh9IHs6MDh4fVxuJy5mb3JtYXQoc2VsZi5SUEEzX01BR0lDLCBvZmZzZXQsIHNlbGYua2V5KSkpDQogICAgICAgIGVsc2U6DQogICAgICAgICAgICBhcmNoaXZlLndyaXRlKGNvZGVjcy5lbmNvZGUoJ3t9ezowMTZ4fVxuJy5mb3JtYXQoc2VsZi5SUEEyX01BR0lDLCBvZmZzZXQpKSkNCiAgICAgICAgIyBXZSdyZSBkb25lLCBjbG9zZSBpdC4NCiAgICAgICAgYXJjaGl2ZS5jbG9zZSgpDQoNCiAgICAgICAgIyBSZWxvYWQgdGhlIGZpbGUgaW4gb3VyIGlubmVyIGRhdGFiYXNlLg0KICAgICAgICBzZWxmLmxvYWQoZmlsZW5hbWUpDQoNCmlmIF9fbmFtZV9fID09ICJfX21haW5fXyI6DQogICAgaW1wb3J0IGFyZ3BhcnNlDQoNCiAgICBwYXJzZXIgPSBhcmdwYXJzZS5Bcmd1bWVudFBhcnNlcigNCiAgICAgICAgZGVzY3JpcHRpb249J0EgdG9vbCBmb3Igd29ya2luZyB3aXRoIFJlblwnUHkgYXJjaGl2ZSBmaWxlcy4nLA0KICAgICAgICBlcGlsb2c9J1RoZSBGSUxFIGFyZ3VtZW50IGNhbiBvcHRpb25hbGx5IGJlIGluIEFSQ0hJVkU9UkVBTCBmb3JtYXQsIG1hcHBpbmcgYSBmaWxlIGluIHRoZSBhcmNoaXZlIGZpbGUgc3lzdGVtIHRvIGEgZmlsZSBvbiB5b3VyIHJlYWwgZmlsZSBzeXN0ZW0uIEFuIGV4YW1wbGUgb2YgdGhpczogcnBhdG9vbCAteCB0ZXN0LnJwYSBzY3JpcHQucnB5Yz0vaG9tZS9mb28vdGVzdC5ycHljJywNCiAgICAgICAgYWRkX2hlbHA9RmFsc2UpDQoNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCdhcmNoaXZlJywgbWV0YXZhcj0nQVJDSElWRScsIGhlbHA9J1RoZSBSZW5cJ3B5IGFyY2hpdmUgZmlsZSB0byBvcGVyYXRlIG9uLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnZmlsZXMnLCBtZXRhdmFyPSdGSUxFJywgbmFyZ3M9JyonLCBhY3Rpb249J2FwcGVuZCcsIGhlbHA9J1plcm8gb3IgbW9yZSBmaWxlcyB0byBvcGVyYXRlIG9uLicpDQoNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctbCcsICctLWxpc3QnLCBhY3Rpb249J3N0b3JlX3RydWUnLCBoZWxwPSdMaXN0IGZpbGVzIGluIGFyY2hpdmUgQVJDSElWRS4nKQ0KICAgIHBhcnNlci5hZGRfYXJndW1lbnQoJy14JywgJy0tZXh0cmFjdCcsIGFjdGlvbj0nc3RvcmVfdHJ1ZScsIGhlbHA9J0V4dHJhY3QgRklMRXMgZnJvbSBBUkNISVZFLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLWMnLCAnLS1jcmVhdGUnLCBhY3Rpb249J3N0b3JlX3RydWUnLCBoZWxwPSdDcmVhdGl2ZSBBUkNISVZFIGZyb20gRklMRXMuJykNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctZCcsICctLWRlbGV0ZScsIGFjdGlvbj0nc3RvcmVfdHJ1ZScsIGhlbHA9J0RlbGV0ZSBGSUxFcyBmcm9tIEFSQ0hJVkUuJykNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctYScsICctLWFwcGVuZCcsIGFjdGlvbj0nc3RvcmVfdHJ1ZScsIGhlbHA9J0FwcGVuZCBGSUxFcyB0byBBUkNISVZFLicpDQoNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctMicsICctLXR3bycsIGFjdGlvbj0nc3RvcmVfdHJ1ZScsIGhlbHA9J1VzZSB0aGUgUlBBdjIgZm9ybWF0IGZvciBjcmVhdGluZy9hcHBlbmRpbmcgdG8gYXJjaGl2ZXMuJykNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctMycsICctLXRocmVlJywgYWN0aW9uPSdzdG9yZV90cnVlJywgaGVscD0nVXNlIHRoZSBSUEF2MyBmb3JtYXQgZm9yIGNyZWF0aW5nL2FwcGVuZGluZyB0byBhcmNoaXZlcyAoZGVmYXVsdCkuJykNCg0KICAgIHBhcnNlci5hZGRfYXJndW1lbnQoJy1rJywgJy0ta2V5JywgbWV0YXZhcj0nS0VZJywgaGVscD0nVGhlIG9iZnVzY2F0aW9uIGtleSB1c2VkIGZvciBjcmVhdGluZyBSUEF2MyBhcmNoaXZlcywgaW4gaGV4YWRlY2ltYWwgKGRlZmF1bHQ6IDB4REVBREJFRUYpLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLXAnLCAnLS1wYWRkaW5nJywgbWV0YXZhcj0nQ09VTlQnLCBoZWxwPSdUaGUgbWF4aW11bSBudW1iZXIgb2YgYnl0ZXMgb2YgcGFkZGluZyB0byBhZGQgYmV0d2VlbiBmaWxlcyAoZGVmYXVsdDogMCkuJykNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctbycsICctLW91dGZpbGUnLCBoZWxwPSdBbiBhbHRlcm5hdGl2ZSBvdXRwdXQgYXJjaGl2ZSBmaWxlIHdoZW4gYXBwZW5kaW5nIHRvIG9yIGRlbGV0aW5nIGZyb20gYXJjaGl2ZXMsIG9yIG91dHB1dCBkaXJlY3Rvcnkgd2hlbiBleHRyYWN0aW5nLicpDQoNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctaCcsICctLWhlbHAnLCBhY3Rpb249J2hlbHAnLCBoZWxwPSdQcmludCB0aGlzIGhlbHAgYW5kIGV4aXQuJykNCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctdicsICctLXZlcmJvc2UnLCBhY3Rpb249J3N0b3JlX3RydWUnLCBoZWxwPSdCZSBhIGJpdCBtb3JlIHZlcmJvc2Ugd2hpbGUgcGVyZm9ybWluZyBvcGVyYXRpb25zLicpDQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLVYnLCAnLS12ZXJzaW9uJywgYWN0aW9uPSd2ZXJzaW9uJywgdmVyc2lvbj0ncnBhdG9vbCB2MC44JywgaGVscD0nU2hvdyB2ZXJzaW9uIGluZm9ybWF0aW9uLicpDQogICAgYXJndW1lbnRzID0gcGFyc2VyLnBhcnNlX2FyZ3MoKQ0KDQogICAgIyBEZXRlcm1pbmUgUlBBIHZlcnNpb24uDQogICAgaWYgYXJndW1lbnRzLnR3bzoNCiAgICAgICAgdmVyc2lvbiA9IDINCiAgICBlbHNlOg0KICAgICAgICB2ZXJzaW9uID0gMw0KDQogICAgIyBEZXRlcm1pbmUgUlBBdjMga2V5Lg0KICAgIGlmICdrZXknIGluIGFyZ3VtZW50cyBhbmQgYXJndW1lbnRzLmtleSBpcyBub3QgTm9uZToNCiAgICAgICAga2V5ID0gaW50KGFyZ3VtZW50cy5rZXksIDE2KQ0KICAgIGVsc2U6DQogICAgICAgIGtleSA9IDB4REVBREJFRUYNCg0KICAgICMgRGV0ZXJtaW5lIHBhZGRpbmcgYnl0ZXMuDQogICAgaWYgJ3BhZGRpbmcnIGluIGFyZ3VtZW50cyBhbmQgYXJndW1lbnRzLnBhZGRpbmcgaXMgbm90IE5vbmU6DQogICAgICAgIHBhZGRpbmcgPSBpbnQoYXJndW1lbnRzLnBhZGRpbmcpDQogICAgZWxzZToNCiAgICAgICAgcGFkZGluZyA9IDANCg0KICAgICMgRGV0ZXJtaW5lIG91dHB1dCBmaWxlL2RpcmVjdG9yeSBhbmQgaW5wdXQgYXJjaGl2ZQ0KICAgIGlmIGFyZ3VtZW50cy5jcmVhdGU6DQogICAgICAgIGFyY2hpdmUgPSBOb25lDQogICAgICAgIG91dHB1dCA9IF91bmljb2RlKGFyZ3VtZW50cy5hcmNoaXZlKQ0KICAgIGVsc2U6DQogICAgICAgIGFyY2hpdmUgPSBfdW5pY29kZShhcmd1bWVudHMuYXJjaGl2ZSkNCiAgICAgICAgaWYgJ291dGZpbGUnIGluIGFyZ3VtZW50cyBhbmQgYXJndW1lbnRzLm91dGZpbGUgaXMgbm90IE5vbmU6DQogICAgICAgICAgICBvdXRwdXQgPSBfdW5pY29kZShhcmd1bWVudHMub3V0ZmlsZSkNCiAgICAgICAgZWxzZToNCiAgICAgICAgICAgICMgRGVmYXVsdCBvdXRwdXQgZGlyZWN0b3J5IGZvciBleHRyYWN0aW9uIGlzIHRoZSBjdXJyZW50IGRpcmVjdG9yeS4NCiAgICAgICAgICAgIGlmIGFyZ3VtZW50cy5leHRyYWN0Og0KICAgICAgICAgICAgICAgIG91dHB1dCA9ICcuJw0KICAgICAgICAgICAgZWxzZToNCiAgICAgICAgICAgICAgICBvdXRwdXQgPSBfdW5pY29kZShhcmd1bWVudHMuYXJjaGl2ZSkNCg0KICAgICMgTm9ybWFsaXplIGZpbGVzLg0KICAgIGlmIGxlbihhcmd1bWVudHMuZmlsZXMpID4gMCBhbmQgaXNpbnN0YW5jZShhcmd1bWVudHMuZmlsZXNbMF0sIGxpc3QpOg0KICAgICAgICBhcmd1bWVudHMuZmlsZXMgPSBhcmd1bWVudHMuZmlsZ
        echo XNbMF0NCg0KICAgIHRyeToNCiAgICAgICAgYXJjaGl2ZSA9IFJlblB5QXJjaGl2ZShhcmNoaXZlLCBwYWRsZW5ndGg9cGFkZGluZywga2V5PWtleSwgdmVyc2lvbj12ZXJzaW9uLCB2ZXJib3NlPWFyZ3VtZW50cy52ZXJib3NlKQ0KICAgIGV4Y2VwdCBJT0Vycm9yIGFzIGU6DQogICAgICAgIHByaW50KCdDb3VsZCBub3Qgb3BlbiBhcmNoaXZlIGZpbGUgezB9IGZvciByZWFkaW5nOiB7MX0nLmZvcm1hdChhcmNoaXZlLCBlKSwgZmlsZT1zeXMuc3RkZXJyKQ0KICAgICAgICBzeXMuZXhpdCgxKQ0KDQogICAgaWYgYXJndW1lbnRzLmNyZWF0ZSBvciBhcmd1bWVudHMuYXBwZW5kOg0KICAgICAgICAjIFdlIG5lZWQgdGhpcyBzZXBlcmF0ZSBmdW5jdGlvbiB0byByZWN1cnNpdmVseSBwcm9jZXNzIGRpcmVjdG9yaWVzLg0KICAgICAgICBkZWYgYWRkX2ZpbGUoZmlsZW5hbWUpOg0KICAgICAgICAgICAgIyBJZiB0aGUgYXJjaGl2ZSBwYXRoIGRpZmZlcnMgZnJvbSB0aGUgYWN0dWFsIGZpbGUgcGF0aCwgYXMgZ2l2ZW4gaW4gdGhlIGFyZ3VtZW50LA0KICAgICAgICAgICAgIyBleHRyYWN0IHRoZSBhcmNoaXZlIHBhdGggYW5kIGFjdHVhbCBmaWxlIHBhdGguDQogICAgICAgICAgICBpZiBmaWxlbmFtZS5maW5kKCc9JykgIT0gLTE6DQogICAgICAgICAgICAgICAgKG91dGZpbGUsIGZpbGVuYW1lKSA9IGZpbGVuYW1lLnNwbGl0KCc9JywgMikNCiAgICAgICAgICAgIGVsc2U6DQogICAgICAgICAgICAgICAgb3V0ZmlsZSA9IGZpbGVuYW1lDQoNCiAgICAgICAgICAgIGlmIG9zLnBhdGguaXNkaXIoZmlsZW5hbWUpOg0KICAgICAgICAgICAgICAgIGZvciBmaWxlIGluIG9zLmxpc3RkaXIoZmlsZW5hbWUpOg0KICAgICAgICAgICAgICAgICAgICAjIFdlIG5lZWQgdG8gZG8gdGhpcyBpbiBvcmRlciB0byBtYWludGFpbiBhIHBvc3NpYmxlIEFSQ0hJVkU9UkVBTCBtYXBwaW5nIGJldHdlZW4gZGlyZWN0b3JpZXMuDQogICAgICAgICAgICAgICAgICAgIGFkZF9maWxlKG91dGZpbGUgKyBvcy5zZXAgKyBmaWxlICsgJz0nICsgZmlsZW5hbWUgKyBvcy5zZXAgKyBmaWxlKQ0KICAgICAgICAgICAgZWxzZToNCiAgICAgICAgICAgICAgICB0cnk6DQogICAgICAgICAgICAgICAgICAgIHdpdGggb3BlbihmaWxlbmFtZSwgJ3JiJykgYXMgZmlsZToNCiAgICAgICAgICAgICAgICAgICAgICAgIGFyY2hpdmUuYWRkKG91dGZpbGUsIGZpbGUucmVhZCgpKQ0KICAgICAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToNCiAgICAgICAgICAgICAgICAgICAgcHJpbnQoJ0NvdWxkIG5vdCBhZGQgZmlsZSB7MH0gdG8gYXJjaGl2ZTogezF9Jy5mb3JtYXQoZmlsZW5hbWUsIGUpLCBmaWxlPXN5cy5zdGRlcnIpDQoNCiAgICAgICAgIyBJdGVyYXRlIG92ZXIgdGhlIGdpdmVuIGZpbGVzIHRvIGFkZCB0byBhcmNoaXZlLg0KICAgICAgICBmb3IgZmlsZW5hbWUgaW4gYXJndW1lbnRzLmZpbGVzOg0KICAgICAgICAgICAgYWRkX2ZpbGUoX3VuaWNvZGUoZmlsZW5hbWUpKQ0KDQogICAgICAgICMgU2V0IHZlcnNpb24gZm9yIHNhdmluZywgYW5kIHNhdmUuDQogICAgICAgIGFyY2hpdmUudmVyc2lvbiA9IHZlcnNpb24NCiAgICAgICAgdHJ5Og0KICAgICAgICAgICAgYXJjaGl2ZS5zYXZlKG91dHB1dCkNCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOg0KICAgICAgICAgICAgcHJpbnQoJ0NvdWxkIG5vdCBzYXZlIGFyY2hpdmUgZmlsZTogezB9Jy5mb3JtYXQoZSksIGZpbGU9c3lzLnN0ZGVycikNCiAgICBlbGlmIGFyZ3VtZW50cy5kZWxldGU6DQogICAgICAgICMgSXRlcmF0ZSBvdmVyIHRoZSBnaXZlbiBmaWxlcyB0byBkZWxldGUgZnJvbSB0aGUgYXJjaGl2ZS4NCiAgICAgICAgZm9yIGZpbGVuYW1lIGluIGFyZ3VtZW50cy5maWxlczoNCiAgICAgICAgICAgIHRyeToNCiAgICAgICAgICAgICAgICBhcmNoaXZlLnJlbW92ZShmaWxlbmFtZSkNCiAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToNCiAgICAgICAgICAgICAgICBwcmludCgnQ291bGQgbm90IGRlbGV0ZSBmaWxlIHswfSBmcm9tIGFyY2hpdmU6IHsxfScuZm9ybWF0KGZpbGVuYW1lLCBlKSwgZmlsZT1zeXMuc3RkZXJyKQ0KDQogICAgICAgICMgU2V0IHZlcnNpb24gZm9yIHNhdmluZywgYW5kIHNhdmUuDQogICAgICAgIGFyY2hpdmUudmVyc2lvbiA9IHZlcnNpb24NCiAgICAgICAgdHJ5Og0KICAgICAgICAgICAgYXJjaGl2ZS5zYXZlKG91dHB1dCkNCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOg0KICAgICAgICAgICAgcHJpbnQoJ0NvdWxkIG5vdCBzYXZlIGFyY2hpdmUgZmlsZTogezB9Jy5mb3JtYXQoZSksIGZpbGU9c3lzLnN0ZGVycikNCiAgICBlbGlmIGFyZ3VtZW50cy5leHRyYWN0Og0KICAgICAgICAjIEVpdGhlciBleHRyYWN0IHRoZSBnaXZlbiBmaWxlcywgb3IgYWxsIGZpbGVzIGlmIG5vIGZpbGVzIGFyZSBnaXZlbi4NCiAgICAgICAgaWYgbGVuKGFyZ3VtZW50cy5maWxlcykgPiAwOg0KICAgICAgICAgICAgZmlsZXMgPSBhcmd1bWVudHMuZmlsZXMNCiAgICAgICAgZWxzZToNCiAgICAgICAgICAgIGZpbGVzID0gYXJjaGl2ZS5saXN0KCkNCg0KICAgICAgICAjIENyZWF0ZSBvdXRwdXQgZGlyZWN0b3J5IGlmIG5vdCBwcmVzZW50Lg0KICAgICAgICBpZiBub3Qgb3MucGF0aC5leGlzdHMob3V0cHV0KToNCiAgICAgICAgICAgIG9zLm1ha2VkaXJzKG91dHB1dCkNCg0KICAgICAgICAjIEl0ZXJhdGUgb3ZlciBmaWxlcyB0byBleHRyYWN0Lg0KICAgICAgICBmb3IgZmlsZW5hbWUgaW4gZmlsZXM6DQogICAgICAgICAgICBpZiBmaWxlbmFtZS5maW5kKCc9JykgIT0gLTE6DQogICAgICAgICAgICAgICAgKG91dGZpbGUsIGZpbGVuYW1lKSA9IGZpbGVuYW1lLnNwbGl0KCc9JywgMikNCiAgICAgICAgICAgIGVsc2U6DQogICAgICAgICAgICAgICAgb3V0ZmlsZSA9IGZpbGVuYW1lDQoNCiAgICAgICAgICAgIHRyeToNCiAgICAgICAgICAgICAgICBjb250ZW50cyA9IGFyY2hpdmUucmVhZChmaWxlbmFtZSkNCg0KICAgICAgICAgICAgICAgICMgQ3JlYXRlIG91dHB1dCBkaXJlY3RvcnkgZm9yIGZpbGUgaWYgbm90IHByZXNlbnQuDQogICAgICAgICAgICAgICAgaWYgbm90IG9zLnBhdGguZXhpc3RzKG9zLnBhdGguZGlybmFtZShvcy5wYXRoLmpvaW4ob3V0cHV0LCBvdXRmaWxlKSkpOg0KICAgICAgICAgICAgICAgICAgICBvcy5tYWtlZGlycyhvcy5wYXRoLmRpcm5hbWUob3MucGF0aC5qb2luKG91dHB1dCwgb3V0ZmlsZSkpKQ0KDQogICAgICAgICAgICAgICAgd2l0aCBvcGVuKG9zLnBhdGguam9pbihvdXRwdXQsIG91dGZpbGUpLCAnd2InKSBhcyBmaWxlOg0KICAgICAgICAgICAgICAgICAgICBmaWxlLndyaXRlKGNvbnRlbnRzKQ0KICAgICAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOg0KICAgICAgICAgICAgICAgIHByaW50KCdDb3VsZCBub3QgZXh0cmFjdCBmaWxlIHswfSBmcm9tIGFyY2hpdmU6IHsxfScuZm9ybWF0KGZpbGVuYW1lLCBlKSwgZmlsZT1zeXMuc3RkZXJyKQ0KICAgIGVsaWYgYXJndW1lbnRzLmxpc3Q6DQogICAgICAgICMgUHJpbnQgdGhlIHNvcnRlZCBmaWxlIGxpc3QuDQogICAgICAgIGxpc3QgPSBhcmNoaXZlLmxpc3QoKQ0KICAgICAgICBsaXN0LnNvcnQoKQ0KICAgICAgICBmb3IgZmlsZSBpbiBsaXN0Og0KICAgICAgICAgICAgcHJpbnQoZmlsZSkNCiAgICBlbHNlOg0KICAgICAgICBwcmludCgnTm8gb3BlcmF0aW9uIGdpdmVuIDooJykNCiAgICAgICAgcHJpbnQoJ1VzZSB7MH0gLS1oZWxwIGZvciB1c2FnZSBkZXRhaWxzLicuZm9ybWF0KHN5cy5hcmd2WzBdKSkNCg0K
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
echo "%PWRSHELL%" -NoProfile -Command "& { [IO.File]::WriteAllBytes('!rpatoolps!.tmp', [Convert]::FromBase64String([IO.File]::ReadAllText('!rpatoolps!.b64'))) }" >> "%UNRENLOG%"
"%PWRSHELL%" -NoProfile -Command "& { [IO.File]::WriteAllBytes('!rpatoolps!.tmp', [Convert]::FromBase64String([IO.File]::ReadAllText('!rpatoolps!.b64'))) }" %DEBUGREDIR%
del /f /q "%rpatoolps%.b64" %DEBUGREDIR%
if not exist "!rpatoolps!.tmp" (
    call :elog " %RED%!FAIL.%LNG%!%RES%!extm7.%LNG%! %YEL%!rpatoolps!.tmp%RES%"
    goto :eof
) else (
    move /y "!rpatoolps!.tmp" "!rpatoolps!" %DEBUGREDIR%
)
echo "%PWRSHELL%" -NoProfile -Command "& { [IO.File]::WriteAllBytes('!altrpatool!.tmp', [Convert]::FromBase64String([IO.File]::ReadAllText('!altrpatool!.b64'))) }" >> "%UNRENLOG%"
"%PWRSHELL%" -NoProfile -Command "& { [IO.File]::WriteAllBytes('!altrpatool!.tmp', [Convert]::FromBase64String([IO.File]::ReadAllText('!altrpatool!.b64'))) }" %DEBUGREDIR%
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
    set "extm18.fr=fichier RPA '!rpafile!' ignoré."
    set "extm18.es=RPA archivo '!rpafile!' ignorado."
    set "extm18.it=RPA file '!rpafile!' ignorato."
    set "extm18.de=RPA Datei '!rpafile!' ignoriert."
    set "extm18.ru=RPA файл '!rpafile!' проигнорирован."
    set "extm18.zh=RPA 文件 '!rpafile!' 被忽略。"

    set "extm19.en=Error processing RPA !rpafile!."
    set "extm19.fr=Erreur lors du traitement du fichier RPA !rpafile!."
    set "extm19.es=Error al procesar el archivo RPA !rpafile!."
    set "extm19.it=Errore durante l'elaborazione del file RPA !rpafile!."
    set "extm19.de=Fehler beim Verarbeiten der RPA !rpafile!."
    set "extm19.ru=Ошибка при обработке файла RPA !rpafile!."
    set "extm19.zh=处理 RPA 文件 !rpafile! 时出错。"

    set "extm20.en=RPA file unpacked: !relativePath!"
    set "extm20.fr=Fichier RPA décompressé : !relativePath!"
    set "extm20.es=Archivo RPA descomprimido: !relativePath!"
    set "extm20.it=File RPA decompresso: !relativePath!"
    set "extm20.de=RPA-Datei entpackt: !relativePath!"
    set "extm20.ru=Распакованный файл RPA: !relativePath!"
    set "extm20.zh=RPA 文件已解包: !relativePath!"

    set "extm21.en=Deleting RPA file '!rpafile!'"
    set "extm21.fr=Suppression de RPA fichier '!rpafile!'"
    set "extm21.es=Eliminando RPA archivo '!rpafile!'"
    set "extm21.it=Eliminazione di RPA file '!rpafile!'"
    set "extm21.de=Löschen von RPA Datei '!rpafile!'"
    set "extm21.ru=Удаление RPA файл '!rpafile!'"
    set "extm21.zh=正在删除 RPA 文件 '!rpafile!'"

    set "extm22.en=Moving RPA file '!rpafile!' to '%WORKDIR%\rpa'"
    set "extm22.fr=Déplacement de RPA fichier '!rpafile!' vers '%WORKDIR%\rpa'"
    set "extm22.es=Moviendo RPA archivo '!rpafile!' a '%WORKDIR%\rpa'"
    set "extm22.it=Spostamento di RPA file '!rpafile!' in '%WORKDIR%\rpa'"
    set "extm22.de=Verschieben von RPA Datei '!rpafile!' nach '%WORKDIR%\rpa'"
    set "extm22.ru=Перемещение RPA файл '!rpafile!' в '%WORKDIR%\rpa'"
    set "extm22.zh=正在移动 RPA 文件 '!rpafile!' 到 '%WORKDIR%\rpa'"

    set "extm23.en=Error moving RPA file '!rpafile!' to '%WORKDIR%\rpa'."
    set "extm23.fr=Erreur lors du déplacement de RPA fichier '!rpafile!' vers '%WORKDIR%\rpa'."
    set "extm23.es=Error al mover RPA archivo '!rpafile!' a '%WORKDIR%\rpa'."
    set "extm23.it=Errore durante lo spostamento di RPA file '!rpafile!' in '%WORKDIR%\rpa'."
    set "extm23.de=Fehler beim Verschieben von RPA Datei '!rpafile!' nach '%WORKDIR%\rpa'."
    set "extm23.ru=Ошибка при перемещении RPA файл '!rpafile!' в '%WORKDIR%\rpa'."
    set "extm23.zh=移动 RPA 文件 '!rpafile!' 到 '%WORKDIR%\rpa' 时出错。"

    set "extm24.en=RPA file '!rpafile!' moved to '%WORKDIR%\rpa'."
    set "extm24.fr=RPA fichier '!rpafile!' déplacé vers '%WORKDIR%\rpa'."
    set "extm24.es=RPA archivo '!rpafile!' movido a '%WORKDIR%\rpa'."
    set "extm24.it=RPA file '!rpafile!' spostato in '%WORKDIR%\rpa'."
    set "extm24.de=RPA Datei '!rpafile!' nach '%WORKDIR%\rpa' verschoben."
    set "extm24.ru=RPA файл '!rpafile!' перемещен в '%WORKDIR%\rpa'."
    set "extm24.zh=RPA 文件 '!rpafile!' 已移动到 '%WORKDIR%\rpa'。"

    set "extm26.en=Modified %YEL%'!rpafile!'%RES% RPA archive detected, using altrpatool.py to extract."
    set "extm26.fr=Archive %YEL%'!rpafile!'%RES% RPA modifiée détectée, utilisation de altrpatool.py pour l'extraction."
    set "extm26.es=Archivo %YEL%'!rpafile!'%RES% RPA modificado detectado, usando altrpatool.py para extraer."
    set "extm26.it=Archivio %YEL%'!rpafile!'%RES% RPA modificato rilevato, utilizzando altrpatool.py per estrarre."
    set "extm26.de=Modifizierte %YEL%'!rpafile!'%RES% RPA-Archiv erkannt, Verwendung von altrpatool.py zum Extrahieren."
    set "extm26.ru=Обнаружен измененный архив %YEL%'!rpafile!'%RES% RPA, используется altrpatool.py для извлечения."
    set "extm26.zh=检测到修改过的 %YEL%'!rpafile!'%RES% RPA 存档，使用 altrpatool.py 进行提取。"

    if !OPTION! EQU 7 (
        set "usealt=1"
        call :elog .
        call :elog "    !extm26.%LNG%!"
    )
    if exist "!rpafile!" if not "!relativePath!" == "saves\persistent" (
        echo "%PYTHONHOME%python.exe" %PYNOASSERT% "!detect_archive_py!" "!rpafile!" >>"%UNRENLOG%"
        "%PYTHONHOME%python.exe" %PYNOASSERT% "!detect_archive_py!" "!rpafile!" >>"%UNRENLOG%" 2>&1
        if !ERRORLEVEL! EQU 1 (
            set "usealt=1"
            call :elog .
            call :elog "    !extm26.%LNG%!"
        )
        if "!extract_all_rpa!" == "n" (
            call :elog .
            set "qmark=?"
            if "!LNG!"=="fr" set "qmark= ?"
            echo    !extm16.%LNG%! !relativePath!!qmark! >> "%UNRENLOG%"
            call :choiceEx "    !extm16.%LNG%! !relativePath!!qmark! !ENTERYN.%LNG%!" "OSJYN" "N" "%CTIME%" "-rawMsg"
            if errorlevel 5 (
                call :elog "    %YEL%- !extm18.%LNG%!%RES%"
            ) else (
                if !usealt! EQU 0 (
                    echo "%PYTHONHOME%python.exe" %PYNOASSERT% "!rpatool!" -o game -x "!rpafile!" >>"%UNRENLOG%"
                    "%PYTHONHOME%python.exe" %PYNOASSERT% "!rpatool!" -o game -x "!rpafile!" >>"%UNRENLOG%" 2>&1
                    set "elevel=!ERRORLEVEL!"
                ) else if !usealt! EQU 1 (
                    echo "%PYTHONHOME%python.exe" %PYNOASSERT% "!altrpatool!" -o .\game -x "!rpafile!" >>"%UNRENLOG%"
                    "%PYTHONHOME%python.exe" %PYNOASSERT% "!altrpatool!" -o .\game -x "!rpafile!" >>"%UNRENLOG%" 2>&1
                    set "elevel=!ERRORLEVEL!"
                )
                if !elevel! NEQ 0 (
                    call :elog "    %RED%- !extm19.%LNG%! %YEL%!LOGCHK!%RES%"
                ) else (
                    call :elog "    %GRE%+ !extm20.%LNG%!%RES%"
                    if "!delrpa!" == "y" (
                        call :elog "    + !extm21.%LNG%!%RES%"
                        del /f /q "!rpafile!" %DEBUGREDIR%
                    ) else (
                        call :elog "    + !extm22.%LNG%!" REM Moving RPA file '!rpafile!' to '%WORKDIR%\rpa'
                        if not exist "%WORKDIR%\rpa" (
                            mkdir "%WORKDIR%\rpa"
                        )
                        move "!rpafile!" "%WORKDIR%\rpa" %DEBUGREDIR%
                        if !ERRORLEVEL! NEQ 0 (
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
                echo "%PYTHONHOME%python.exe" %PYNOASSERT% "!rpatool!" -o game -x "!rpafile!" >>"%UNRENLOG%"
                "%PYTHONHOME%python.exe" %PYNOASSERT% "!rpatool!" -o game -x "!rpafile!" >>"%UNRENLOG%" 2>&1
                set "elevel=!ERRORLEVEL!"
            ) else if !usealt! EQU 1 (
                echo "%PYTHONHOME%python.exe" %PYNOASSERT% "!altrpatool!" -o .\game -x "!rpafile!" >>"%UNRENLOG%"
                "%PYTHONHOME%python.exe" %PYNOASSERT% "!altrpatool!" -o .\game -x "!rpafile!" >>"%UNRENLOG%" 2>&1
                set "elevel=!ERRORLEVEL!"
            )
            if !elevel! NEQ 0 (
                call :elog "    %RED%- !extm19.%LNG%!%RES%"
            ) else (
                call :elog "    %GRE%+ !extm20.%LNG%!%RES%"
                if "!delrpa!" == "y" (
                    call :elog "    + !extm21.%LNG%!%RES%"
                    del /f /q "!rpafile!" %DEBUGREDIR%
                ) else (
                    call :elog "    + !extm22.%LNG%!" REM Moving RPA file '!rpafile!' to '%WORKDIR%\rpa'
                    if not exist "%WORKDIR%\rpa" (
                        mkdir "%WORKDIR%\rpa"
                    )
                    move "!rpafile!" "%WORKDIR%\rpa" %DEBUGREDIR%
                    if !ERRORLEVEL! NEQ 0 (
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
if not "%rpatool%" == "" del /f /q "%rpatool%" %DEBUGREDIR%
if not "%altrpatool%" == "" del /f /q "%altrpatool%" %DEBUGREDIR%
if exist "%WORKDIR%\__pycache__" rmdir /Q /S "%WORKDIR%\__pycache__" %DEBUGREDIR%
if not "%detect_archive_py%" == "" del /f /q "%detect_archive_py%" %DEBUGREDIR%
if not "%detect_rpa_ext_py%" == "" del /f /q "%detect_rpa_ext_py%" %DEBUGREDIR%

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
set "decm1.en=Failed to create decomp.cab."
set "decm1.fr=Échec de la création de decomp.cab."
set "decm1.es=Error al crear decomp.cab."
set "decm1.it=Impossibile creare decomp.cab."
set "decm1.de=Dekompilierung.cab konnte nicht erstellt werden."
set "decm1.ru=Не удалось создать decomp.cab."
set "decm1.zh=无法创建 decomp.cab。"

set "decm2.en=Decompilation tool created successfully."
set "decm2.fr=Outil de décompilation créé avec succès."
set "decm2.es=Herramienta de descompilación creada con éxito."
set "decm2.it=Strumento di decompilazione creato con successo."
set "decm2.de=Dekompilierungswerkzeug erfolgreich erstellt."
set "decm2.ru=Инструмент декомпиляции успешно создан."
set "decm2.zh=反编译工具创建成功。"

set "decm3.en=Overwrite RPY files after decompilation?"
set "decm3.fr=Écraser les fichiers RPY après la décompilation ?"
set "decm3.es=¿Sobrescribir archivos RPY después de la descompilación?"
set "decm3.it=Sovrascrivere i file RPY dopo la decompilazione?"
set "decm3.de=RPY-Dateien nach der Dekompilierung überschreiben?"
set "decm3.ru=Перезаписать файлы RPY после декомпиляции?"
set "decm3.zh=反编译后是否覆盖 RPY 文件？"

set "decm4.en=Existing RPY files won't be overwritten."
set "decm4.fr=Les fichiers RPY existants ne seront pas écrasés."
set "decm4.es=Los archivos RPY existentes no se sobrescribirán."
set "decm4.it=I file RPY esistenti non verranno sovrascritti."
set "decm4.de=Vorhandene RPY-Dateien werden nicht überschrieben."
set "decm4.ru=Существующие файлы RPY не будут перезаписаны."
set "decm4.zh=现有的 RPY 文件不会被覆盖。"

set "decm5.en=Existing RPY files will be overwritten after decompilation."
set "decm5.fr=Les fichiers RPY existants seront écrasés après la décompilation."
set "decm5.es=Los archivos RPY existentes se sobrescribirán después de la descompilación."
set "decm5.it=I file RPY esistenti verranno sovrascritti dopo la decompilazione."
set "decm5.de=Vorhandene RPY-Dateien werden nach der Dekompilierung überschrieben."
set "decm5.ru=Существующие файлы RPY будут перезаписаны после декомпиляции."
set "decm5.zh=反编译后将覆盖现有的 RPY 文件。"

set "decm6.en=Extracting decomp.cab..."
set "decm6.fr=Extraction de decomp.cab..."
set "decm6.es=Extrayendo decomp.cab..."
set "decm6.it=Estrazione di decomp.cab..."
set "decm6.de=Extrahieren von decomp.cab..."
set "decm6.ru=Извлечение decomp.cab..."
set "decm6.zh=正在提取 decomp.cab..."

set "decm7.en=Unable to find:"
set "decm7.fr=Impossible de trouver :"
set "decm7.es=No se puede encontrar:"
set "decm7.it=Impossibile trovare:"
set "decm7.de=Nicht gefunden:"
set "decm7.ru=Не удалось найти:"
set "decm7.zh=找不到："

set "decm8.en=Searching for RPYC files in the game directory..."
set "decm8.fr=Recherche de fichiers RPYC dans le répertoire du jeu..."
set "decm8.es=Buscando archivos RPYC en el directorio del juego..."
set "decm8.it=Cercando file RPYC nella directory di gioco..."
set "decm8.de=Suche nach RPYC-Dateien im Spieledirectory..."
set "decm8.ru=Поиск файлов RPYC в каталоге игры..."
set "decm8.zh=在游戏目录中搜索 RPYC 文件..."

set "decm9.en=Decompiling file:"
set "decm9.fr=Décompilation du fichier :"
set "decm9.es=Descompilando archivo:"
set "decm9.it=Decompilazione del file:"
set "decm9.de=Dekompilierung der Datei:"
set "decm9.ru=Декомпиляция файла:"
set "decm9.zh=正在反编译文件："

set "decm10.en=Copy from"
set "decm10.fr=Copie de"
set "decm10.es=Copiar de"
set "decm10.it=Copia da"
set "decm10.de=Kopieren von"
set "decm10.ru=Копировать из"
set "decm10.zh=从复制"

set "decm10a.en=to"
set "decm10a.fr=vers"
set "decm10a.es=a"
set "decm10a.it=a"
set "decm10a.de=nach"
set "decm10a.ru=в"
set "decm10a.zh=到"

set "decm11.en=Overwriting existing RPY file:"
set "decm11.fr=Écrasement du fichier RPY existant :"
set "decm11.es=Sobrescribiendo el archivo RPY existente:"
set "decm11.it=Sovrascrittura del file RPY esistente:"
set "decm11.de=Überschreiben der vorhandenen RPY-Datei:"
set "decm11.ru=Перезапись существующего файла RPY:"
set "decm11.zh=正在覆盖现有的 RPY 文件："

set "decm12.en=Skipping:"
set "decm12.fr=Ignore :"
set "decm12.es=Saltando:"
set "decm12.it=Ignorando:"
set "decm12.de=Überspringen:"
set "decm12.ru=Пропуск:"
set "decm12.zh=正在跳过："

set "decm12a.en=decompiled file already exists."
set "decm12a.fr=le fichier décompilé existe déjà."
set "decm12a.es=el archivo descompilado ya existe."
set "decm12a.it=il file decompilato esiste già."
set "decm12a.de=die dekompilierte Datei existiert bereits."
set "decm12a.ru=декомпилированный файл уже существует."
set "decm12a.zh=反编译的文件已存在。"

set "decm13.en=Error processing:"
set "decm13.fr=Erreur lors du traitement de :"
set "decm13.es=Error al procesar:"
set "decm13.it=Errore durante l'elaborazione di:"
set "decm13.de=Fehler bei der Verarbeitung von:"
set "decm13.ru=Ошибка при обработке:"
set "decm13.zh=处理时出错："

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

if %RENPYVERSION% LSS 8 (
    REM unrpyc by CensoredUsername
    REM	https://github.com/CensoredUsername/unrpyc
    REM __title__ = "Unrpyc Legacy for Ren'Py v7 and lower"
    REM __version__ = 'v1.3.2'
    >"!decompcab!.tmp" (
        echo TVNDRgAAAACO2AAAAAAAACwAAAAAAAAAAwEBAA0AAABRQwAAsAEAAAgAAQDwJwAAAAAAAAAAK1vCdCAAZGVvYmZ1c2NhdGUucHkADE8AAPAnAAAAACtbwnQgAHVucnB5Yy5weQBriAAA/HYAAAAAIlwtaSAAX19pbml0X18ucHkAoiwAAGf/AAAAACtbwnQgAGFzdGR1bXAucHkA0SEAAAksAQAAACtbwnQgAGF0bGRlY29tcGlsZXIucHkAq5MAANpNAQAAACtbwnQgAGNvZGVnZW4ucHkAXXUAAIXhAQAAACtbwnQgAG1hZ2ljLnB5ABISAADiVgIAAAArW8J0IAByZW5weWNvbXBhdC5weQC4dgAA9GgCAAAAK1vCdCAAc2NyZWVuZGVjb21waWxlci5weQCfZwAArN8CAAAAK1vCdCAAc2wyZGVjb21waWxlci5weQD5FAAAS0cDAAAAK1vCdCAAdGVzdGNhc2VkZWNvbXBpbGVyLnB5AIoVAABEXAMAAAArW8J0IAB0cmFuc2xhdGUucHkAxVUAAM5xAwAAACtbwnQgAHV0aWwucHkANGK2ZOgkAIBDS+w8a3fbNrLf/Suw8ukxdcswtpumXd+6u4qtNNo6tq/sNM12c1SKhCTWFKkSpG21p//9zgMAQYpWnO7e+yk+bSyBwGBmMG8MvStO8tW6SOaLUnhRXxzuHx48gX+eiROZqbyQ8Rsliyxcyp3dnV1xKYtlolSSZyJRYiELOV2LeRFmpYx9MSukFPlMRIuwmEtflLkIs7VYyULBgnxahkmWZHMRigg2BXAwt1wAIJXPyruwkDA9FqFSeZSEAFHEeVQtZVaGJe44S1KphFcupOhd6RW9Pm0TyzAFeEkm8Kl5KO6ScpFXpSikKoskQig+TIrSKkY8zOM0WSZ6D1xO3FAADgBXCuhAbH2xzONkhr8lEbeqpmmiFr6IEwQ+rUoYVDgYAefgM9DyNC+EkimiBjASwJ4orjGkWbjPChlbalYpHLlb5MsmNQniNKuKDLaVtCrOgXW06y8yKnEEF8zyNM3vkMAoz+IE6VJHdHzX8DSc5reSSOJTz/ISMGY88CxW9RHrR2oRpqmYSs052DrJABgOGqoKxEGVIAdJmIpVXtCmbWoDRuLVUFxdvLx+OxgPxehKXI4vfhidDk9Fb3AF33u+eDu6fnXx5lrAjPHg/PqduHgpBufvxPej81NfDH+8HA+vrsTFGICNXl+ejYYwOjo/OXtzOjr/TryAlecX1+Js9Hp0DWCvL2hLDWw0vEJwr4fjk1fwdfBidDa6fucDqJej63OE+/JiLAbicjC+Hp28ORuMxeWb8eXF1RBQOAXA56Pzl2PYZ/h6eH4dwL4wJoY/wBdx9WpwdoabAbTBG6BhjFiKk4vLd+PRd6+uxauLs9MhDL4YAnaDF2dD3gxIOzkbjF774nTwevDdkFZdABykECcyjuLtqyEO4p4D+O/kenRxjsScXJxfj+GrD7SOr+3it6OroS8G49EVsuXl+OI1komMhTUXBAZWng8ZDjK9eTYwBb+/uRpakOJ0ODgDaFe4mAk104Md+EERAxlCTUXhQ4VXVotBcEBTQLHnKDOgWaDrc5xRipssv0MLMatUpBVRRoss+bWCmSiaKl9KsQyjRZLJYs26WYJWo3wtDZgAERgUMAlWlxWpjFgVsizXQiXLVSoDVIFC7gFQUHsZIoA7UKJSrhRajypbhdENqg4ZgtU6Am0qliGA3hXjy3cnhwgyzESIu9xK/RRmwz8RjGuixbJKywQ2RIpluASzVciZLArW2xBMXpqXqq91cpYUgAligeDlPXAJjJXGAmeCaQVrkJQ+mIUkWuCsOM+kAOuLv7Se6YV5oQIGrCRp6RwxDcU0zaeEKZAvwfRJ0Noygee/pcn0SZQvgVUKTwXU+ZeKeSuK8I4wAIAeH4IEoxkrsKkpbk6TEIAwAOj0cqBpjieA9tVSkcpsXi401WCKS30Y+7jlEryNPgmgJ5ZRsV5ZJsRhGbJ5B0YjrIAlTWaASrWCFaVEozSVuCIN12BIEcw0VPL5Mx+PAR48kSBeK7C6C3n/RGZRjm7Ab9JPPkKWEbLwrRQLkD44RjKNwG3mS7HWeCk6gmghWWgSOoc10I6yCBIHhlCjYL7lynwClKqoNN8Qhx065QjMt4zYgOqHJ3kF6lPwc+AMoAoaVgSFzEBE4RswRU9dJdFNKicqnMlJmoexIq0cWskQ6ElYGcCXZJE11N4sn/7iE2+zvC+efAuUgYbxWa1BDhIg9ocwreSwKOC4LK1hku4MfyQDhAbvWPz0fieWs1oavVn/aEfATz0rCFcrODp4Qg9ARcGtiRmiesoHvxVVwsw3bEFkm7gyuHNUDRdNsNb6m54BnxOgJFuxkK73MARJVY5qrJJYanVdhKjpAEDGwc7p8GT87rJJamxwtqTWsx4kFW1VHIs5xFZP1EpGySyJRATyBWdsTACo0lOrCvAlzecwCbWGThUMI4Zb7TVP2ytgs7/b43APZ4LHPUE758347DX+vV6Pfl+h2tqlaO7AkJB514ZEh1zwuALP71jMBphZoKS88faZB6TMxzAIpjH2eAzOCYd/OjrYfy/+ciyme+Ph+eU7MLonh3uME7GvJYZebwRqDHYVwp9XAE0Wvf4OzV7likIf2Ohgn0bI5MLX3//gGWBKgQ4773NxcCi+OUYj5SEq/XpXXJnEaEXCAmwwmzGAxCocsNfwet+MRiMIX4gOC/aoucP7voUKJHudkPvi+Fh4+77A/xw08GcKPLvZcWHQUoCtsfq2k4Ju3r0o8huZsW0GB12sDfMsu35iBN8DsV4TRzuvJg84fUjDMlVy25m5+y7o1DQrK4zod4xA0HMIQlHICJttMN9kHETQoiQ2YDaOzFL13tVHOjPm5FGLo++3K08q52G0frz6oLbwmi5FMVSDBhxso/bMhQBuGHyxqlboAZQ4IBCGAdtVjwbh4Ou99Az0RwG7GvSKLE98uPeRXLHDCiRi83g84ySm8zRRUsiRAwYmBl3nPLbzneUG/Hn2MbwHL610tAaefY72fYGBJZpVjjMhDrnVw1o0wwL8DFj+xxu0tgHa77Y3XzwX33Qpa+hP/ciPfenP/Lm/8JNuU8M/2w3OF8+bBidE03JApMb48ZA+zvHjPn2cwqIIv8oOu/Pf3Uq/8yilB2+dxtkexLIJZvmau1ZPa+P8yTZ/ss3/GduM1uXPW4hZFd2AJcAqkWsOLDdMvWWVJ1kJEisx4aTkKlQJROtkWnNOGZBT05xyLoKXlKRtmLUCVHEneVqa5zeEx22Ygq3kvGpRZTeQ7yUY5KTrj7ZDxLGJkQTFUSsvxjAeD7BAU+hZ0RRPxIEjnyY0Sygw6/3r/quve03pRXueZJVsyL6XF7GnF/bFf4nDL5/DudWDqHLv+33xmfjiAAHvfwhmixATWCeaTs0nIs9QZ+UfpbS5vN6t4f4spAd8oDUeR4612OISG6Q0NrAE0LeWZn1LhoLn9bep1j+1iFvfStZVZnk1X+h9Wq6VB0nN8KDfY3JgExg3nSH1IaKxBAqplkakwS8N9M+FC3We9iAOkKl3oABsQlrDNPVIgHvhNIJVgxcnp8OX+weHXzz78vlXX/+1V4s4rQ5u5Fp5/X43Cg/RhtsTbbH0eoBPr0HYkH6hQHwUXVwVeDxp80Xyy026zPLVr4Uqq9u7+/VvTO53r0b/+P7s9fnF5f+Mr67f/PD2x3f/rFnw+dPjf2X/GT4wysH0+TPNjI1D/pO84OLMhIsz21mC5iPpoyPdvz/kiEUPfQMjX+//e4Rm8k6b0MaZN4pHH3X6BnsDlwE/PFd/1/NBM5FNoVISLFeiJhmG0anO11vObJCF6fo3ycU266JyDPkUYJ+acibGVTnfFyCvdPKcgdKyZznNpWJ2U0qPiUW4xnscco14faArehM0axCZqAnXH7EwJ/Udiy4fwhB4tjt0jOE0lcYjKrwjQReIoLh2iZcD9HgEBrCKIqlmVeprfijar8qcEqXZ25Q+TQU1L8I5FxtrP9nhKLUrt67yYP/wWb81zxwez/1QYWLXlFQ5t/PpTiRfSqxBLRnnViCx46yFI66WVLnUqwEJLl0limMSqju7YQEmTY5fuJt0VVU6KOr0eA3ebjo+A/7RHm/TT5267qnmoOaFL6YVhpKlLLBez1cAobKJMgotF+DcKFhri4v8TlcuAoxEb8pboaV49ryJ7q442Odyp5GMz8UzCFn+qge1tInSSnELBZfSl1Qdy0HMF5COu/h+bF6nJe9g/wgwft93BSZGLXWCUp1gw//RAuzqLKxSvPbM9lZrMZeZLOg+lW5Q/+byBY/Ec5LCKX589rydIHpzwMYXSTP7aSWM7ZRmkzVcodPFfJDnKRs0n4IXvrokMvA6hwNzQFmmsfqby0Yt0NP+FvGPuuS/JQ9WqlGto49FPsm48J6ASLBqk5RyXtL7f1W2TVwpszl4TL3FkQMXrwAvVpAqrxf0PnywD+6ny/d8K/Fh3UV3h+c3CVWJSRsp3r2JA+IknGcQflOQ3xuUpVzqGyLsADC3h5IO4qinkxzDTlykZGmyIvR9deoHuNaXE1syAy1kztWGD6lS+6CcWxLYtlVIsUSY8L+nL0XX4jOljdwRfOxBYuTZjYLJBJswJhNfyAD9Cbi5vrNxw959eBt2sbTH5hb9linX/AvCONYhnxuV2edOCXFj70Gaune/+i5FvMnQoOLxaSyIwb3+lnwHgtngF0i4PbtJv8bH1WrVbxVRN7G6qjFaFXlcRdhyksxmEI1k1DQCRlQF4pqv+/AmNadYz2ZUWhxs+IZCZW0R5dUbvOkUKawxLUvlo8nFGRMbGXNA9bBN+DhRq0XnUZIDh4Kr4v5GNgtPgjSfP3AcHcaC6NvZ+ZPS4Sq3IyGPlQ4yK1vZ2mFftPnQV8nNGq4e/AbCBjcCxDQc4l28dsXodi3Lvz3q3AH6xrXtw0fekXJQqQ9iyC2n6uSytbQZemuzrCmjqm594JBJAY76utXBrPaxIH82t0PJr+8/m2g4GZa9MzXwTNLXWOBkT3AuqGlNgJ31lW4WtCIFk2S1p2zK50oWGJhgv4qguwDMOthCWyoesJ51WfhhvJyy8ebeJm7GAqpYwP+kDrQpJ6kfpwu7f3laqeLpNMmeyuxWrCCry7NDvExu9wEeHHIf4LuqSMT3gbiKFhA8Zhirt1sDffEPCF6X0TQssk9tgp/aBD+1CX5qE9zSJjiZlEkJzm4CRrj3JsOyVA8Gb0GoQRxoeO/2IPgiONyD4apIeeaiLFfq6OnTOahjNQ0gb3jaNkRPKw3NNl+BhVmFhZLmOxb0ItuCNccaiv6cgGuDrD1V3GWVrzBnRmdmHy/nsrRdWLltzoIcENT7Lkxvuju71NruhzGunIKtbHR97djYgCBz62CRY4BOhR+eegm4gY1ZVRPykjs6GhjR02GdFe6K13l0A7bs1yrB/iXdFoD3U9kmbAUZWHgLAZetbGCsZHfxNiunB5a3dSNaPWLjtHavmiEDEru4Wq585EWm0o6ZXV1t3kZ85DdCJgRZD9EEjPuiFLwEeDYKWI8seZMJOJhyMvHA6M76bgQHppoqkhDbwudMkoldFUlW1rdQsAZjX1v+dIJFXcwDZyZNkMZV0DyKKmz+bEKhXN7kDy4EMJElucg77isFz36H4X0WcQjmANo1OYlLBsUZJBI84umKEFZs4MDl/Qr8AMhGjSWCpxAiboHJb45soEKXnSw86DO0lde55KxK03Vr8RQyeS5QHdFibETNdHdwmNGdKEBE/UR/Dg6f60F1pboFT90kqyMHGQceEoCPVxgPVJQ1hNj7K+/hSFHUwYNjm18DKp0CMxsMDHGs556DFvlbjKpYOXHXu7y4wTAI2ymydRMYTzVHagQOUyV87AuTfx09LE8m9LOpmgWjZDkhJDUw+twGZYSKfjfXEqV6LX1urzWsoN/NtZwN68VEZXuxIZ1+W+V7EcZjOE2btHj2U31/YYe0CLKtusPwQ7eMkIzUPdnN7mtzA0IZELVVXo6apaQJnt0Ej95LMvrdLi3tijHMVQz+9gBDldvDWlh2cYwDSwyx6HojbLY9A9psfrjPWpfAUPKobZqSDo6eJBpBA/ZQg61LZtNQJTWJTreB6TGvdYbarDVMBf6vvhTAPMcxUJpq92oAv0+4m+K4Mf2noy/332+UeKx00hJdGqzr+L2GGeWmW1ObThQdITAJAPiYGasFHiwSElJXvfiBueu0t9sG9MY9h0OSi1RX0X/XEZoNZm42yNgu0UYrge5Goiuj8Fay9lHV9mUIuzUTYGNWJ9zmkol77qs48MX+/Vcv+adVS8WpH+xd4tuAxhnZLoSNDqZ29kzIHG+0V3T0K7X6D5vkoOiiLLhs2ITYYtJ14fZvdBWQNh6SSXgLiSRozpEY1h6v5boIKXueEGCX9LJHDnENFY3g1CEB7gZvxH+zo2cBXmQqZWa6A4Nei6GthqrNthHdv9TWKTrhju6lVgn+gG6uCc5RZ9GtNuN7tXPd63dcvm0Y3g1e9OoCm7UinOwRc2GYKlnW71mvHOiXVmoObjK6t4Wp4mW91JS6a3PkcNxRd83cg/cdLavOtPZlinn0oUv7x/L3Mbxt3nVuugnyD6ZdjAM7LdWBGPIlsmM9LfeaPO5RnSHht3VKcxz/LtMn2yqSTV42C7vkbiE/oosb62Ox5roIC7rgbfpb47MvINRRTenCV7MwpzJOywoiztJuEsgeXF0HpmOg3geNAFodn17S4hsicZdwYWIJtFPNBAI43dX7wDtnDHmYYoEmIcuCGDwUpTZb8uguENLHrObDXjHd6+NaPdK4mq6Rb6o8vpx27KZUgb0Z2whitlQXGcxjIiH3WDFC2TFNOpyYcdsJvSxDC7nypxf7Iof8/a6ANPmYXKN7+GYEszT9ucsw1ztxWdIso1SwQFNlRrIcpoDSFPVenEzmxTFG3p3gy3A+gSQA3+uZgApGN2YxJYP5bAa6b4ZUOuG3aqioqwgoSK4O2i7qVAIf821wYwS7GUgOAmCaoHsUrG3YwItrBjCOigafA7VKE+Rji7/1uzHAuvpcc2cK3nlriOBYekF5X/Z0OJTMeAvIbRCPZdR7HAic2+sIqT6wptcIGq08UOhARFIupjwXTH/TBGNYsHeFqRwGz5+pAC8swxQlGFmJIII9vBxti2IDbn+bacdE0TXqJPO6i9TF4lRLJCOCpgP+DYJHb8+6V5vF5oIu67hTmxAuVQVkSfLGwr27PV+Y1xeP96py9uRrti9mXrN5tyE7Gi8cDFZU2rDQfXzgb+phe6ChkvXHTq174KfWYPtpmxHTNQ6+NjJ1ogse9OCojp1js0HXoyhxLEf98SMo2bQqGyNNC+N83rQzre+t4NOhvfvkNJv6TVF2BD+/2TP3oVzFmJSpFxbzSVmtWp65fpGbWjiWFGDVrXaYbJvCvWEc3b7I0Abk8xCDGXDIZ08o/TWRJMHn2o31oYouaMBJ03vh07X29sslFqcIVbq3MEVDfREb1wrKTljTgiYZ6QKoViUDSPHrbkLGDba6PnNeLpaWaQ1eNCGBFOptXDbTBSl96nytqmFXhs4b3jXvFDMILB5bmKYT2LQntUFA/IKHzQkhk07oTfvjmofBtRV4T0PQT3yKofrtxfWESZyEQEklPUCk0ZhGl0O6vxRjUD5UzPwFFr7N5dMSax26luhT9qwz/1JkUsZmHQeh+t0rs4G0DW78uDDFRF1/mYU3cI5YfaK6SsHvTfj0bleYcU+rfa07LAV3n3a5C1302qg0e57hiOGDb3nEzcKqv9UD9fIbk1m2c5JWH4e7lmt/sv+AUFHhj/VCbhewbulyodmbioBrbBNA0+u3XiTg+U17wir7oE1BBeO2ZL6qCbZrLBkhrf4UxXNJpE54wjro8ncaNpL+WgKGHhyE4ApdAgbRotd0SDTUCi8/gU8YqDWDefrQxumxyo/FYVen3Ka91oM62eI8q/W48yXNZlDe8BIdsTlBjCDtnKJxcALzDcNBITqN0i3Nztb4nOdtuNTat9ME+9VvVTRsCMHo1XGE65RbzGjC2HS+PH27B6Y5rhtuVeSaLplmtwbtggd02P9TGtxzNThuhJ5Hvf8DjS2qbMK6pTxzp8HqO2GhhxjjFo29/gank6aQVahlS63HVWa1FM26ngi
        echo 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
        echo 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
        echo 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
        echo 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
        echo TZLkCr2dyIHFWdjtoAfRfFdnRUCu/h/A1aV810RHsuljuwsF7wGlCDg4KLveMDfnYdSJqRncVIfoZgov4Oy5k+3tA18k8kWdoyWJBika6msH5CX1GDlYqQL0vhzDyL0f5WUDd597LvACufWPsiGhJJ2m+GfBJH3OScgkYOFJ1MweCxoZToQ5bZ/nKeZbB4RY6KmwH/nj97KNMzoNTZkOkEAxjWEDfLwNwWA3gUAGwtbHcY32E9GsMkd7YLrynKe4jaZPIvrwk8lGg6AoJPUGOftnOJPMtOxlSj1zmT8UZpb4X1bXVeBQYS+t7UwBdhkQKfwRZEpRT4kJjqx3Y8tDV4TBYzcdoiMTVzdmUE+SQ4xeqy7LGbhZijt/Ndqbwq1936+YzhN2jzrygsn9u7j/q5s6x6qtt5ByrFHyBWjxPv6dNz8LM33zPH2+wBaGKizzklURolRei2J9794+6d52b6j/a6ItCvxsAgENL7V1tbxtHkv7OX0HQCDTU0QN7sYddEKfDKo6T6M67NizfHQ4+gRyKQ2kiisObGUpmAv/3q7furu7pIUXHcRyc8iEWyZl+qe6urpenqr7CQ6V9DIl3noyRXn5EQd0J3WSTP2vYVNMSydmOXohHdAUfb83mQAVm3he3M9uAHPsKjGURk4Pk/Zpg3q/6BJUMqYDHbO7EifpqTcxM8L9jr4VjZWHEXHkYTTKjClMr47n3vArsDnDvNDRzt+0xqkhlJgNCbCpjraSGNlZKQ9ffZV6ja4NMdqCxGRutGLCMhwKUsOty7ngFIQasqURoWSvXB4U6bdEsRy4VGYPrOnV76Ngjn0eOwNxkFTamgbHRGd3Uc91A9yoLA86SUCTl6qmXt80jbXuUTBgZ0abeEAQYu8zR72870NojL/105H0pwuIUT7b+nu+TKfajyeclVxwj8cdTuR/YxWC/c9x5ahZJqEN16tAXlDWZM6CL57fGXXPrLac4jqGVjDEEQG28283e4VfYtF3Y/JyXyzyr+tflPT1Dfbn1w7jeimzqc7XepzUH0mXoDRmxrr8St1do5BcYoRgf3ZFGLR7NEmKsXJTlSNdsgumj/TJTdGoqRyJ5xNQNn04Hs+znwXQ6Hns5cIyfoUrcugYXvpcTh25L7Ce0SLVtZ9Sh15nHE9CBDP1eKKItCQiF4dJcM2RLVMswhdMs96V99k50OJGMEWU83tm7b1a5tLayUf/SmYD4A7N4/tsY2lQ4puZ8dCmEfeH7SZIU6vVRv3DWOfgwdJl+vLeHYUVFrnB64nPkIMkgC6OXGVzK8OQvHzWjvyT/vWcY5jF1sPK3Ysg2+CXZM1Rd4Vp7jJyfCI7aMbZ8rI4EcRl+lZiayAKwsCQNLFxjlqtjnEFW84EhvCA2LMcBJO/La3cgSJrQ3qGQ41pnB18lrC6Sh0NyewUdqJG/kFfady66GonIcwQ3UUUHvMKtYTRKzyf9Fy4f2dFdTlpG46jDDdrHb8QIGK5repXDluLB8joOjW9Ji8nGMRd3u8hRvfG3kNeltxl3dBo6BaiRUGQ0vA4jifN7R1HhVuILrR0vN9vd8UuvRTNSDpOmvZzoYzIS86j1J4xleT8Ou0/Me3+C6IO68Xr2qSYIDePh6oRosPOa8Bl1yh/etbEapysDcGCSiLu2Fmdt5m9PPmW4vvaMyEmS4ZAXRAkbcA+kAwI0UBy97LNsub7OKKatuMRL0AkvrxHuXiD2TnJV6MbRJTufs0iC6Cn+GkGXeHtyaCj7uAlElNMFDAcFS6F8v6no/MNucZOgI6xGTviMWlCwzMIMViP/UGBlwEJk42wDIpxBdzl/Pb8ZwxCkzrNM4dUo4gEf2FQ1Xz8buGmWKtyVh9eU66ccCyWjFBeFdYarh1c8RrynvDU7WxB2lXa0nS7zEsY7zZUl3jr04TLEifJyeZOdBe+NUUIZT9WCGKDJv1F2wbrj2iRiirui1h5BZJW9UASMYTZGCjTgoKIxIM9nhfA8GBq0F9Az9jE3+7A0HcCdva20XHWPUB2HR/kVSJ2zJrhBNERE81wFF9nhc9f2nw3wiMTNa0SXxtC52YPyI+7svcdfLuQy9UEMsPQItm8VZWEeMuHr7PK6WM7pb0Sgwj9pxQkg4XVKLum9avGm+j8YJPFfGKZqum2gFN514g1fveFnrNSQ02gr6s7r7BaOIXn++QE9W6GwFlwxmV2nK3zwL7Ipjn559vGonyB7Hf5raKSNOMOj2ozv+JaOh4HJEEceCNIckOOlYVgIbMzdmYZb3+c24oO/ossO6AAiJMe6unXwc6VQ7MzKtz+17ILahqYf5B05UutjQv2brvcldYd6Y+irkf1ID+mEZxVG0fpPwUah1jVt55i0MaCtjzo5YG7jTxgnlpmLPKnGKK8E28ZXm/CJ2rvGu+5noj/e5rXV5rmDKZqdQFpQjGj21E2ujmsYVpFsbL5GZ6bEtHDJMJKuoIukxS56tmlaxAjaTdjiwqe6Yj3emb34gpAkeklYbgdi6CDUUqy9PTJAr4MVBcIEhU/9DmCjR1DRrwQVObVQ4hSS1hGzGmFUrrLzYTVxmf1cWMXHl/Clg6mgjY04hoF2Ta0t3EaJIZN2hVkva2fVJE0pX9Wbinha1pAS4+C7JuBOqYbI2Iu54h09Z7qUvEE2FoEz0vWzq4wqI/mwI02NyWSdNdccf3LRadbq9kmaSCLoB+hFGhqJplzZNeuviktQJHLEdvRv0aJ+lRNhdFGU8jZHmxVMncVawnFlejUjcNAQhspyin5HtBdjdYZG0UnSIcJ4p+IqIoyoOcOaCPfxuYhhPSsja8vDvghINh9pImJhwufF8Tg+SBaVJocPkip5VPq8xF+PuvlaU3ovL1+E7AK+j5xNjiGKu+3gdDZ5dTueLumhaQi0M6evb6gp6bbEbsJ6tZIIYCVph0+taYMPnXfm8ts1xWQyLXsyRzx3x1VZNsfkAW5qbV6AY7tZNjXD7NXAbJADrDKq0NYu6o62RdB7OlWLtTRdHMKMluphKQsPNeeNu8dLER/pSAYiBgYgzaZmgxR0JfMmuwvro5cNauMSNYYexFxzMhuwMINLEO1ii2JFy0dev75ZzX1qIvYaxpjjd1hYAP4x8GqyUCznBi+KjTuzEGwJ7FwkAuuxyfo8BmNol6Y4BkQMSv2zlViOM7ZEZA3bAtGqJdykoRuQGGvqeIbqUaay2CyXfMRx+4WgcixiIg/QbWonisXT5Acqd9PUuIMS9wAxmW4Y934MtsNbMCHRcNxFyLNG0c/FRwppQIJR7Qh53T5nh6cyxYf0QlN4lFojqTP9RajmppW4UbCyfBAtZf7iURU3MEVqKhuvIgH+FN8ybbFLM2r7VM/ayjcm6nGHuTwEWvIbafB1wI3pO75r51aeqWzcCdV9udZ5KyRCHj9bvyy11EYQkJCCFczRfN02NcHNNZ7GBxmYmzhAtzXTPJwjW8cRNE4JU+THif21dRPBLIA9KPc+KBRowd+sqB5GTp7/Kl8ARYxFruXTEimx7Ug3Lhoy7CMxscosInOKLniKsgxSwQEDUFg4dwmN4brkMDnKrZf2zwUvBP2SZZ9jQrNLfJ0vmpIyBFjDObQ/2xRLuBlqtmGzv8PLRIcJF4QmcBdsasoBAbeu8aNgmLj1o8iNPisoKwf+NOUGaiAhekLcVZJTIu9yBVeNKZPmUIIo0R6zFiOuwWOQSammEyWrQDcpSZr1Me+Q4OG2lLxqqnJpoQiUTQFttjHHJDUo3s4UzVDC3qZTZAJsLW4hkxDpo7A906n1m+IYjJl1Zevac1zZDhLY2R5709UzM2tqMgjb6TkuISuKuThYQPF2poZQ2FzG1OqfRsY9za4SarlU7fz16Yw2Gp0Mqxtpcg2obtfA7HJqFjkh71cMINsSOohu21rU7nuU9a1ryklA8xzz5pmtTluqsJn0nO+E7/gu0ikY126rd8hNpmk/UWvHFx1KTCQqSXai6bTFZ6bTocdomCn5udgCuQjPzKjv7Wa6G0d9M6kTIeyIda36ZMCJVMJLL5xEGuspAt/2+gZxzP+so/zM3udG/KvzN50aOxWUE4GbXhQfREmSUnOqZfOHbZr/+Uzz96UddhjxpD2H+Hi/rkgPf1ZVEe0iB2qK4nyIvvxwPRH+vWhDI0TjxsaN7b8bexEB5d4wsrrTrhpBfcjaJR5kJ+pNUYOidoa9DugCXxxeHorEk0haIgbm7NDSxVn35c9VS0EFjEgcZqfZCysmcSiQgKAJQOS4EUnABCjnHxrO+iW64xXmTNpibT3rPFX3CI6ecy+h/Qtkot9XFKAMKLLX8DOMa0L5k/KrY8Y2dVwC6a8SFVrUJxzT5xIV5DLDpvwJmjFK6xn9US7k+iXUlujAuHfhdHgQWLO+WYWWE0QA42LOtlpUUNL6iECevAdQK5Z9Kuls5Lp2CW8aFXiPhzSHGx7GI4JFC6DMxaItziBbrxGxWHrtsvFXJj9M/dVlAynanWGUthIICUAkiiwYME/CrzMU4b61G75uIV7tT+4cJCbRGctGtKVhSOOpDGSqjEfDR/nua5TvSC/Hot2krwbn3Co1Pi8z+bCsNU/wcD2L+bWiAGnJwUFFQx5MacsDC/ctCSXpl5M9TU8Ox4aZL+Z9W0s1axwAy20qa55nu+MKWBla+w2SzHNdMMGsmAM0Zn3+1DzEerzVhtjC4KUniZLBu0z3WhO7RUu9PBiO0XZKqUVqSY0PkEe9gab7x3WITPoE5QZm9UZnZ86O1465kvHMBRhqNWeShJpEfxWgCtT84WH16XCpVqUrWbWH4stpe4TUbokyEvRkHMokvg0kz9pgSIVqBPEBP6XyQ1t87ZRN2374OO5Xe2Z3yZyWotDTxF46QtRLP+2qKd+rVqTDA683YGfDD0zZ4Y9+YJuaYCMTndKFWgVyy9gGQy0Vv/Htcm92WOXedAjMhhs5t2eVC8sWC71BsSG3UgFRcuNYwDpIOp6gzgz4O07VA89QnrbN6mZV3q9GcknW5iL1zawm9z4QgNCyBo6eyc3khETDnhlujwfXXCgyeIf+zzjHRZCBxfoaTZVwsquzjc95jWQEtTHFGny+8WHMYeRFs9WSmfxEmEv8iUNs8BiRoMaJr4AVSydOdMPLGfbIHWXCWXkorPIOWFfBF7gJo6GLdkG1ooRcdXZnJek8FksHD+STq2U5y5YGizH7iU+isHP0SkV8BUo/pDc8wGUbseMZYSJZemVr/vDq9benr6LlluW/f8IB+pgULGZsv7fuYi4j7yvS5oCD3N1Qzsw/dwwKyZL4HQ33PmmAJvunef7u9MW/T3iyD86icDChkkMolbI8mAw2zeLpXwexLAO3+W0JSiQ2O4xwMw8w2lpvny2lO/bdzsokYoba+XqPfWYIm+ifvjnr9YxHKPkUexj/OwiY5Vs82pnMam5OOIIv89qlajY6T7nGXHisl4uWjkOR16aix1sPRKWimGBV4JwVzaaZu34smFjxNHIeFcBOnR4oDW53Gd9h0Bg+cJunNnUd8KkCtDxExoouN/WFQ6LjMCWSDm1qyF/lYDj+Gj0Mv3wc9Y9Y/jx69C/88fTPw5xr+njHBL3k01QLOSaOC4FETzT+PIzovLj9qVhmFU5sjDNndA9s6BkWJIIJUHiPt7gJr1Oh9y78pL6QahiYtwbVxKLCYByhtZZssh1c7QEUNZmahSLDkLrd99thZLeJnZOHq60RLbXXMYY//p1BeevxBfb1bp3txWOks61nWhwxhArfQeqR0Nth4ky95KjeDQOc17fqf77b5Y9ss+64fB4t1o8W60eJ4f+HxTq4O9tcsiWN6I68G+zzX6W7xZjDb9NPkXwCwceO7WuVfvwV3Cf9fKnVxLIWbMThPUXWkctyeSI6+49nP/z48vzd5M3b1+9ev3j9qmU3hMsQjlxB1TftUbqvgG8jvZVxknzw5gm4Y3gFmblLZzgYf5mVbdMf3zA1Iw9nU/N0fveJ1F77tD1ObHkSAfE8bH5qE+FDaHSma80spC47kigfgen77wiqrE1VAI00d1yMDPeSC0WQ59mG8wTvQ/LTSyMvBZWX2oFLI1mPCjJ2mU22P/7HoDmNXbi2Qdcu1txkbIqGM6gCHxy7w9BWye/ABNgXOO6izjElF0mA81xuHdUZptoywDM3/1oKS+VFpWlkLdbs7JsHJQR0zPts6yIKoiR7JSEdjmg4K8Jn8+o4fCviQVgOaozUwjyuXnN6+miMRxoJq+KdIBev3hCUyiNYcKqd206qQULT7lVrDND5EgVpX3DUWSnqIAeaxIWpXBa7tn/ttj/Jj0ug93wrwh7oSeigKgnRrxth+YsbYuvQLeGXvcU0OP+9c7WpiAIMo42iVplLaC1VIGwYxz/S+zIS0xg+H4EUCuz+JBJgFEkiYLZKyjsseTaSBlrJppUnUky2yMMiFZRirMwFK+eR5RTqo2HTS+skRTCqG9Ziab8vy5KQVwb81ZplHZwGOggcGSi7Bg40nTGRd2X7sEIOw7SVpm2MPBGo/w9QJjyhGP29NCOXteUhG4V6chlY1mUhiIGmyrA+GLuHGlORUNxz7syMYsOMTjicksfJ0v7poqGzXNQ+25NUKO4QGZv0bVnZvDle1hSLwJOJwQ1UMbM1b9kEM0ZvBa11hhsA7swlZb91Jx5ObHuPCO0koDIT/MR/4n3agZ0ICrb8kDeSQYdb5TwId0WmsiL4p1WCKfjxNgw1RGVSBW6JzgxBqByd6UZLVUK8Sfo3OmagXmAdz2hpkHYS07UJYetgH63u37l7HvuS+BWf10b7ftI/dVKFpJVQ0U4ur4ThLL2e40qUFq9Qiej0g4GHshi1zzYnkigkBI7zlTAPxCZlCMXK9Dbu4HWSPsAwOpkX8ygV+uHfiLRF0IceTZ0hJFOpCaTVs0bEgrKuC8xJCmS7YVlKo1bVAWQ9iEo3VJlJf0MVRwvJOEQ1ZYJcTrkx5LgyfiK/uCmY4DQ8T1xBEAM/bZWaWVXewD+bdfpYXPWxuOpjcdXH4qq/RXHV63I5rynHgcvGqWrb1NewS65JRLKqOiX9ljo3Jcqcq/WW1cIGWGrRbFPexJRYwmQexCyBHJxpBIMlB1mCVDLfYJWxjA9+TTobZsZd56s5cGTcuiY3GTMXTNNB5z67K4t5n8vPPy0XT8k8IME0qS3cepthiSv6f+pJxgMa+mBoHuSZUKm1/816AoKoWQaYW7IQfMgjGNJnaaTgjc3dKNeL+JKQv2MPR9DF6fk7gSs9EVtH3Tt/8/LF2emrCeyx83PYXHA1U9Y6eOxnZFXNRa/3t+ChNFsjkQTC9mb78sO6SniiOr+vGHlFAtGFtPpMgjSrm0FHrbyabVosXmE5eK4Gj5izENMkBQCkO78MWgjgNG3C8+ZP/wHXFTziPgSVzTHWab3dl/Af5EMYCqYGaae7sYCm7d68qTIxbmHkz2MUjnpkmt2PYTyo3d7+bfACGwu3wQGrv7c+AtDMr3MQgMCSiQy7LjfVpZ1Dac84YaFwS0ZLYrilpQD2bvo9uB+7GO0O6Qe0ZxMrMvUe9tD4HBGKq3wZOWxe2pAYtfmBwY7SlIrS8DBmkaJX4vU0EImm8gWGRwF+7jHPR05mvDLL4o6MITwidliR/W/bp/wEqP3DfDNxSzHDykhBFRaGGQwoE7JhY5vG5urYrIDnY0/o4iVrI1n6SQ1VtSVXIglB4yRcqRbkfc4NgvdhWbEfaJ2XcDuY1OqSyh8bWJVz9kjI+OimSPcs49scNPwGGfUrEA8jiwmy466lZMINYivZthZhW/4S7ttlbnjfYULx9vDmu8/1QcPDtj51eOd5bHTARj7X4KCpYGyHcauuki2RbIG6LMj7Zxcmgd4uRGX4Gqe++BZ0Fi6G8pf0n9ni4h+7ytJvJBUCWZ0sQUv/bfet6/mr3bsHD/FL79+DB/jH28NEtcn3oLO8fvvfWJrXksiD2QREHvVbokePrdMs6k6U/3u2WSxsFIVJykVvtx4a9b3hUKJ3FFwomIOMlqicDD7GOmOH5p7OvIc6GrFjKTcNYax2NdZ62G90HwV2TH4Yswj9+dEi9GgRerQIPVqEDrYIkc16Mlls0AANd5yYQ0QtnSypgNey7jk7ifkLGDC/zUUVysq8C6/cgtYNL/LvpAl8aJbFzDwh39xmq+wKtVr2VGEVBnnguxxtSsA7qm8p3d1/ldX8RblChN4Kuxppy8
        echo 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
        echo yJIejysxJJ5jPJZg/YP0KCdwx4/cX7iWMSfvKbyETmqmH/DOli1ltN0MeQJ36a9yGFc/PC9zuCO6TRM6Y29gFebl6qEXcoMBK59T+q+V6kUAbqH57iMLDH7y+ddlT0fU7fPGWfltItrACbq2xofWzi1/hXrrEb7iQXSPWhWB+He3Xcc7OYu07v+MjF7rGfVepoXyIsdbTuNZOGymzem3fsbMgawh2bglPO9tywcWDgDR1zsET8nuiRPOH3K2B1ONubcxYY8s4pBPmeDtfDnyjGN74LoXi+415rZvJIXNjNyIgNyFJDGTx4w0cJYQY3zj1srymtWJgGxSTYPhg3Upa4DGKWD5m+8gZDcv3/d2knxFyXmrOcPtaKIn2vYfq5h+7mG7ecati+vYcu/70/7s4Vrz5ekxcoll9ShlS0VnqJ252rQmmK7h5WpbaRnxy58vNhWAVtdiy8VGOT4608nUDrKjxhJw18x0kV8U3D0p/0KpLBVfQL2eY/JfVYL2ZY/6/bqrwqzTdSrVcJwC4V62zWgMEKBIDQudhDuZGykv5GyuteX1NV9QSndHxKldK/71tJ9+/Jautd9a+k+s07t9WWFanuW7f0OdurjV+3FDI14Cv3q9gaZvdwSilExG5hbUVrPk46dXEqYfhtATigTN20fey5TZqxSDOy796mXW+GSqnf/8Q4PuTxf/vGfserir1RW8RWPh2VTpWhsFSQTEolnJhsFGgwU7nOVEkYBZo+JRewtySOQ+cakMqPR0F2b3kW9qmI6FJ2Ut9vRAGM5L/v3W7JzWT3bQ9etxmLebiCB+HDz/BDzJaelBG44CbHPmrAKRu5m/7AsU3GZfkFTuCogzbxXjOkSOEr0X1h1B1PQFBwp1K3Y1XRNjjuvHvTMjEAVPtvlMP/s1FDhBGkCiUnuOxL8nLmqx4BGOURYUMQSMumsTlJdROeDFjgI1FFMxdEUIE/On8APZSnycA9NUnhnnjaToGHwAfPCS17gPdrx5MnVAaQfTBjmV0SBrMEAZmxy8VCQnFvPzYwxMR4J+OzVCiFNXw/1JqV9iGLevJHkFcUmijX+yDnkKdsF6vQhwksRDj/pR6xnPrk6QBr2tstxJ6dSJ2wimNfMwBKncb4ODAOxMwMTqCgOB8Sm0Ff4Wwe3+wpY+Kitm8Zfj/GMKD0tyg9gD1k63usVuphZ5SRcb54RqzZF7jJAnIp3pHxW+nLpZyBqE+xkFLIYxpSw1KmiwMGFbzD8h1I4Vo9Vq1HjLArJDVdu5kbRk+yc0Nlm74Jiyoo/OqDcurG4B1EmoiVyd/SAzhUOUMy2HHdCbkuiTzzzmrfNNwVQgaZGVYRitDBgCS328UkCfJHK+kZXwKsPjsLY7OGu+b9ju2sWH4dmhrfE+7e44Tan7q3fC3BSQPwGH5O0+lr93zxNFXQH8rTWK/Ttm8ijVMPOG2Kuyf2PHNPUPWFWxc0H6V+0T1I0V3HseUIMKUKSAbQ+CSZvvwMo+xWl3bbzn7EMPHrPAYEiSQoJMshLe0gFhU4+GDS3FzmNXhWvi3ryMIFcqTM1n1krkuq64baIKE521JoSO8icRuqFHVTr7cGmSvDieb9XTCzo4DDcD2aEEbas3+StYPMQUM6Tz0VjfW6IMby9LYY04aFfn1u3oNK1/ErB8CDK2N7dvPmDVyKNG/r98vGi3mj6nxWnhqOEnH3GGZyRToLa7VRO1AZtigru/id6DYcIcQ9DhMka44YK61VNotDpV/tvSc0TOVO9ERMDxUESoQHPevDaYpqq0YGoKVlTuR1UtJuCP4OkA5Q+h1isrnyn33WQ9lQbhO1jnfPvaTk7K3Dq7nkk8S2UPvBHxnoIzxwW++bHpNdY5pK75kYV5/bHD1SfAZkJSs6HYfqon8MfXQRAmiP0DG4POlslCREC6qZ5IqpHsjDUut17fsaTgnIUuC1eW7xkC0FS6Qav5vXAywEiC21C0QCPNDCQuOPu2exqL0uUFksl6flI5N/kaxFKm78XiqQFt0L9liBZb9GoFtny85f0PPH8r32TDpwPZ+LExWtOcC9V3phFEcxAhjvH7H3wFzBDaf1b//jkoRuDjJVGAgU7qnrceFrgV6z5Gb7rJFqkJC/TJynwv9VjcQoHXwaMh/06yaXx+IZ9r1E44iDTzF+yQ+mg0q2gbYt+1KxQDe0k2oXL77oDIJIQY6QckqSAaNplLyYmoUZzoH8/D+bLM1G3BZB/G99TWG4+ZDp8Izqa9zkPNowELsaSO0qR98QCrDAZLMJ+khJ7LhwsAtWR35Gjaw4ntwY9lmyCXGfL9hFyvnZHKVai0l5WvpMQIY3zpl6d/r/dPP4dy8vcakcYAIBDS+1d628jR3L/zr9iwMWBQyw9ke0kNoiTA/vW5ziws4Z3D/6gE6ghOZQmS5E8DrlawvD/nnr1u3s4pOTzJtDCsKSZ6Vd1d3V1PX4lsUnLpXs3Z0Xa7rCsXEma7eXWzZ3TIxAtreJMTio/dGK4vl7N/2KkTa2+l2IE0dCQHh/qdfeHX1plXtO+FmIPgUma8J2fa/PdrMVj3yjLS44F21a3IJxVWwlU2rE1RXctCB6LjCTRAxqPR6BiQu/8nA7Wnp5X0/1t3n+D5vl6t8f7y+DX3wYoKJALGvaZxE5r0n79rV+gTbDc5V4XtXuU9fmwE4FTEMslRpEaxc7Q6YiLS1xOYXH6GMaLkn3xx5Im0oxKFMt2feS4JEY6ZW47LH2wYKVd3JYErbuGW+NKx94V2X+uHzBUDOmAG+K+JIgYDmlTi8HCZ7LNGWVG05HBbDbl7bHFkOvFjzHwcEMdHJnlHpoMfym36GQzzr5dzdb7FS/FMqk900pHXBVM3L/Bgb3d7VcU/jtyCJrUwamjC8/+7dxcksUAOSfnHa7+r4Q+8yC4U4el1E6rUgGtN2a5cqG3a7Pj1PzozJ7Qnbm0Bk+aDSpXYTLYMK42JFypba5KzKoAeqmVHlXlpPlR8Lk7N9aeyNmTSl3DhphAzZ3r7geQa6xT9rd1U7OtqmsGDbeUvYHL3XKifQKgp8BzLHHCeTsY0cYeeuiV6Psqd1fSVImOUyzhD3cVbypGILKDTO1jBxVdaEhWuJMoaDKXPlAqWg9/PZdAnsXaRubXyQ8wnlXOqHsGtl6w6vZBZdrQl22oX0+UDYKm4MUFlpyUCDNU4lYMheJkM6qd7AeSDpGu8qjtl4sbATXxwYG+x0uJ0ybFLuXdsNedcyST2p0Bo7A+c78XSKgwBUYtXxHDXUj0Gc61bVTSs85gR6SGVrmfyoWkmpAxhLITOiM7bu8h1I5lBSAH5OgXS1Y7F9Z2SX3qXR9m9hnVKmb5FQXaNH9f2h/TKLGE0KiXCMgjqnO6xrv1fr7EZTZFdJcZMv/tgRU6lLgGJuUWtwt8sF2/A+oobXwvgWrIR4N8RQl1P722Lw+tCI3BcC3DXPZVFtYcS5Dt8Lo4VXOXl4gc0EuM6Ein7KrwneDhuYmxHmnnIIWtfngZhgs+gZXCMsx9dIaIVr+ZxNw8IopaRX/2niL005aFrKtTwBc8+rel9XphuPWY6A5Cy0hJmXCwaZst8tJ3KILIzejpFuWTL79IxHXnFXXCago1KB8XGSJuOB/Xlgwus0CoX41Eqbw6i6+hcz/Vs3d4HVHKif5wDJ/0ES9rQ6/6qPkfRUp/Q/g6UJKBdqggf6KepErCkYpO4t9o71K78bw/59dQ/CJa/HvEGSNLD/w0zWLD/ChV8EdEAsNB4wdjO5Slr0HCuhQmwXV8SuHXq2/fE76n2y4WJjodKeU2eKTUWwQq8yZUShGGmV9QufMWr+AXLAc/+h556Jk3nV45v4/dyn2HwachRXVcal9fXq0a6vuCQltjg9QrAT/wh8p+zcV3W8wQ28ew3LAgPY21KoV/hObqb9YfRpji80Nl15DLk26lMe7XXb30pFvh90Hh90cK/zes0J/pwhsQLe+v4CVed/y5UmX3y2WC2FAWXiYI/aZGV58+xjCHhKanLR3+hbCzkMzo4+k1ys/ivdUFGX3LJZM880qya3vxVgmJUFgLjFw+tx54hZvlHJ3ty/k8uguoMLz0aSTFpuU2XQxeJoq9T5fDtZAuJ5hluIbkV0Wg3DyJj/D95pZ3Dv/irb9NcudgZELxFv6HZIUf/UiX6bnXZSOzpyamZVb2dTFpmZLUrGAxBmTELUq/eN3N1eN4SQTy4qL4m7ds1dNIXy2ITTzb8K+JOVmFoemD9SJa/L7cqLLwq8OZ9MPYBGEFhHHcQit4H2uXgDuhUfoZTGwuzyMFDeZmRISQBZEerl36IrGcgtK/WXlq0iKjCRtN+DiGl72IOWW9FSQz7RaOsn725gfLIEJue3hN0PC6cV9HHQdufDew/mquK7edGG0fALS4w9VZEghi868cfWSmAgzoEp35TqNOZdqLEMP81jXKJVq5S3oQDNbUakHLRLz284OT4mrqJpXB1OA7lSdQhybYmipUT0zJ0Z7iF+bZoXKS32RxV0ny5GQRHmq4E38w8d00GdXditz5HWev1pJ4sSHERKM0U/EqtYoI8lH1Glu1R6BPknZ9Xu5K1JCtKtRvK1cPnDHf0RrFd4rc9XVGlsvU1TWZxN1+s3czFQ0Wle03pIkgWj8GCBTtnQDKy0oz+J0WPiiqMreSR9TFuJhI2jsZgHX171mQbdud+S53yr0EPpmFvok8MPvLnuvgzgpfNxTDJ+tkV95aOmre8P0dCazEBwmijxWXBF+q9kpQUdmE9SibbrqyVxG7XkqBLpU6r62aeU1h/DTOGM1KLckEOLknpnISMijn4INgiNmUCzSHaHqqsi+KL/7ly+KzscWnNCIOszW6wc4ka5VaFyvNA7RuWfJRIdLk+h3CJ+JVGZdUESz6yfQwEfiUq9xC6OAlCmuC8fhpJbBff1+K9r23fdaLAr3EmGLH6VtPCEhehen3nGRd3uZRD5w+cjp7a4lDj+hZX8w33KCo0le6EqcpSuCqzYAmDI5RJ7dz1snzfAMra4qMLgXoeqonB9fA7TpwT+f1QJkbpOXCMZqIsRS9eSjEziSJ3m33ikGsB5hVAW2fYgVBQ8Ueg20REFNZMZsdWuIkjVmzqRFSlu2XM8pzXbsWfUokGz0DaQM3+81mLXx2yooSIoTxj0MWQhlKH1TqZBxJM4NLgkqw65hYKAg/3qLO/iFmFWqqmtPB6yS15nNYsiWTEXQUBpypB5N6NeFOO8kU/LVebNE27ICq+Ust8gn7dwf7xh6VeujrKD2LwVhhYOFprA5826qliIxLjImIVjG1jSvkFu/r9d6SaKqyqZcH36/K7yzZCi6u05E2ASFVzoWAhJjFwtfIkaI21eafAyrJm6fvRXPKyIKZ9+uMz7vvc3luj7n29gV0ft/VHkS75s6yHtaLQA+OdmrfFhT3c8PPtCARM/r0At11DYeC2sMT+G9IKaPhkKEMWnkwwDgqocktb9vQ7P78Wb6J63UV1E8dR69DZ+QOK0nVwrhpfsd7R2aO5TyF5JObvrPcAYeYQ9EwNu3t61evx3CI7Mk/gtwtSFgUY7FrPYYq+2rp/ocTWCuyBDAY4PVycZEbhIYmcb6nteYGMzlczauc+baGC4MrCxKipmRNNlg9ii/QawviwKpnNtvf75eEOrGgmxN12qrX8O/9lnCLlKwo4oIBLRJvA7gN6NBVrCiPnywF/LN9JkwSefjMlttE9LCfqL5FH05wjqMvRHoKzzRS0FZzPtKcoE+r87rrtLOCZRcA9kXplTwWUAihxEoy3Pj28nusuJTuppHTpK+xvIumLSVnJlqLz7hpTM/DKLuSBq/bG5QpOHd0/lRCu9ddx4rL4tHtMv9wG+3C0B41u7F5GJ4yY0mHg3PW0yMWVGJXSOLktnMlNbirz641laSHvTMSZD6e8o/YL7/DhklQObqDEmRt21adj4PT9uEjl8epu/jMgZ+zz/7A1Zfs01NyvpbjLi7gnjZkN9kL6RnxZkvgnrIuGoWy510ElZpPK/kIuiX7BrEgbvdVo/ET9IXPKOysZverJX7r6AyrDzUDL4kvIqUkIYdMo5At35f1kvxsHdWsxlUEmey2yh05VyjiA0jq64D/4VV9bSPy4r/dIfFdiLfp8m3NFtgHUV8G2q+yicY+v+7FDsIaQZAv4ruhZZDZJxnfcl9G3CDT+0vXaGtne71jGwH6H+XcUcGjGYZK293D2qxBWnjQC0XQFftaa8gUXJO2UD6fi+2BQHnI5faL4vNsv3koSdJHfS/cK9iOwGle5hEQhya7YUSfG88jGMNZKM0Lp7GxtWesZZVtuGQcNSWYS3al6ZpRXm7K5oZvh9kN9OhGe8vWVk/Eg2fq6MmoJNkulB7ZC72AMXKVFFzO6GB2L+GCASO4dWBXXsAKYVXetoI92OAAy2WGweqHjL2sLD0Q6xGVAqh8V3Fen1X1IN9y1IozL6p+y87AoRtq4G6lnlap3jlVYf2Dshno7zes4w7sOTiPDwieGWqdUPE/DpFi4Olkvd+hW8LEQIrMdvV77p2oM7FBXElq4eAGcdmUtOZE4wSVx3IpRelEMzFS46R5ivEHzsjr3cwYf8fdohfEDr5ydnZHOUlUBBejLLdLeyJaLjYUi9rD65gEnBiw3v+5clZXpJ9WQ3/eedNESEKyU2Lwly5fY01p5NNPr52IZj3IYTd6YRVG0I6RJUoUE5NE8fqE4nFkqCk2/nvO4AubbRhMET1BOXIbOKaBV0EL+9u7YXKvjnytdDUrOVpAoNUU1K4yQipZgjefYBwUZN8g1leuauBeDfAnr2bOvZPmGaifotMiVB/HNtj46ImoZ983a55Hch19YvdatGOaZx3jGG1b46vM72iHMVqr6imGGV/PGGNywNOU4rVE40ZHhCu0OucIbRsvnE5JkoSj4iilkrMqPJZKpLkC8RH+BigJ4ppNjPQ9hkscYxSp0qwcjlArzjwK9t+4J/BmxJ7eb6eW6b8Rm/GgidQILaGSFKF0KMkU2SoZVWg1rXYP5JuhAzd3gznF4pWLWDI9RAtQHPyJGNpjl54lIJTNuBuvi3GSxOWl5Zw+gY20cu2yscZXNv8/GUiHQQoL4MSxzgwZaY3JUO44C2NjZu2EkbaLUGcfvkdH+H+VQZ7CA30iPHPA32NVeXGnIYuLCGvKIwwRS/UtkfIo0IVws11jjCL62aHtv9o6iL8RYL8Tby6t52pXzuJR59o1TQueuAkBmmiGT9kXJ4Gfh5SIdHkUPkTsIw+wI4jmYSdUhLJ3QpH8HESB52lTbTQuK4ZtA8lNcXGHghH3ndA5re3B9mytGGnE6KFtO283y3gIYjkV/+w6mibLz3plutoBFzaWUDKBsRVx9JJuJWPegZD5cNg7DtzquJTFiOTogj2HhYZ2khP5jNYjVlI5t5uooqr0vCfoy/6ZQ7JrGvuRlfSh5X936eYyKATuPx72Z+DiieqfX48c5cioLQpUQfN7HRi1xnn20tAKR8JDaT8dW6oJ7e+Za0logikvnVasfcvR/umMcDKDOGuR9Dz/zul5TDKeUZCq5zk9z3N6nuf0PM/peZ4gPc/RlDtHkuWM0EwB63tSNbNyU7nZbhor202DHlMfReKZt9AXNGP+odlnIp146hQ0O2nCjm5RVf6h+V9kMTxhBpgAC9FMzmDYQTilZDG6yO+YK0aGXjwSjvY0oFcxogz+vhqMPwoYV7xTPQ2Uq6Ln1ySa+/Rkgf08ZMqBSPt/agaCvolIj8kO/BewC7/5/0EWcl7jWNRq2kEfDRv/C+yvAMkZnp3ZOG3Xzo1/TdwjID09PbMD2/2qK91/QtNTCOCbws093jaV7dr6Dxgu67dOMbRntk5lrdYZAy7R+ltgQAEgq2JK3dpGb3gB4YL7Eea1ZQyu5HYcEH4gIt5iF52zPx8MDOIc1jbsuse5UjNq1ZUw+RSGLnUDgh9k6ut4Z636hi2ovSpE1sLVVY+6dmPdWENThZOTijAbAUAsPDtzQWFRp/maXHk8wnLsNSrrWmY+k6/+NFe18YM/ZpoYnLHaNNTri5YG+CvTa/o7Sf8f4Urm0/8enp1Jfywanf5/Gs1SZwZcjgMQ/hk+PI19nNz5U+a5nWtQbwctm5fXpw2J/WTr/J/FJZJNcuif1SA/aGlClUitiDez7TqUIxp6eubq58KPWaZ/w9tUgIqPDztcBApSq7ReB8jZ1vKcBQE6Axne
        echo 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
        echo XJKLHoy+7/uVKUVY+sqmT1qEDRtiS2vHUiV2Zd8krmMnO574bWNgKRJ+mB2nwlxUfFNEwr4TFdV1RwF2uT+m7wbzIFo2+WkLjPSa1ogZaJlyX03ewpyoTlh4JUKYplv2wAaaGkwgC301ctiUdPGtLO53IpWXciDd07fSekgAE/xFLlsuriXMM+MQ7CnrNEl6BcNf4Lw==
    )

    set "OFFSET=--init-offset"
) else (
    REM unrpyc by CensoredUsername
    REM	https://github.com/CensoredUsername/unrpyc
    REM __title__ = "Unrpyc Master for Ren'Py v8"
    REM __version__ = 'v2.0.4'
    REM Modified to include Inceton + Version display.
    >"!decompcab!.tmp" (
        echo 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
        echo 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
        echo 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
        echo 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
        echo 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
        echo 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
        echo 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
        echo S7oWyhzcJgIJ6u9j8HeRyHicRcvF/XyRm4PI/0IKmY3hDDW65uLct6FyoWe+WasZozJyOYZft5R9EhU7ewG/yWUbAkMReCYEM0Ax/Yy+H1y+B2mfFciSOd4oUldQahrctLDDEBhgFBItHXjXVh1RwGSBGVANDTycANbCjoX8zxhm9fPotN+KBfgvLMArPiIYhRiL7QPGtenSA8MAWifBSw8d0QBGbO7QCQaFYRtU99sM4Gij/Yd9U0L5W2HaMTeSS4eJKyc5saIF/hgn9K2K7xu6MYoKKGJtJyaUBh2JpjOPdpUFQWIl6KgMbHSgtADyFqBxTBSYVL4ZkxRsfv4v1vH0aopqJZvHLU4ukif7fQLBJoVsdt9gLQHtV7Supnaaj+20zMhPpwdAWuC3w9aTxDi1Afsgw8qzploQXkXNcm3YkFbmHDTHgFd2S/6xMO6whAAvkWRRI0993TfjK3utI615UB1B0LgpLhsIGCH1hmi6giN/jpvikuVuhTil/Ee/g9aBtMsbdIYQ8P5N4m9pRUprCWqRdeM8GSnTQ20m8zLGiOwhGLpCKY8g1cghBGeu2a38Tv/xjShrawvs20Z08yCfoxGTvvmTdnmZajrKywBZ05+n7UAuOxJG3UTxoJUENJy0yZmclrzpm0wmYC5BuxJg9j5fEHPF57HA359oD0XRwExqHCSP34xDuKA7vLgT21dXorXIAIXUjNMgEEfavJpuk5Uvg+CDdEA9xkXCS7ezLzEd5qqynnMVteldldyp4XFwqNuxBHn41LHTj0nV3sWdV5hC+osUc3SvkpgoyqrtFpPndW5HnsrltfFf9CtxgY/LnLKpWYBK4ugbQHSAgMeb8XRgfBplrV9Ld2dwdShaRO3rQVGEc0bAijTy0ap5DR0Tv4XpSzd+vuIrV6cAcV+q6UOgAMyeUpmrCSzZ3Hi7msHDa2rHU+d3BWZ2b3aZLIR+HcDi1uN0WfJYRL8cUnHSTC2s6y4rUoMYMzkWX43uMnTRS2vi8Agj15DeAVpuARJs5RsieiZOm+6QRbUG85O0PjdNMu27AfP2pKuI/rSUt7XG6p2Op3pBLT5h1OyaK6nzjbAE28r8DVLdgWa58X/Aw==
    )

    set "OFFSET="
)
set "decompcabps=%decompcab:[=`[%"
set "decompcabps=%decompcabps:]=`]%"
set "decompcabps=%decompcabps:^=^^%"
set "decompcabps=%decompcabps:&=^&%"
echo "%PWRSHELL%" -NoProfile -Command "& { [IO.File]::WriteAllBytes(\"%decompcab%\", [Convert]::FromBase64String([IO.File]::ReadAllText(\"%decompcab%.tmp\")))}" >> "%UNRENLOG%"
"%PWRSHELL%" -NoProfile -Command "& { [IO.File]::WriteAllBytes(\"%decompcab%\", [Convert]::FromBase64String([IO.File]::ReadAllText(\"%decompcab%.tmp\")))}" %DEBUGREDIR%
call :elog .
if not exist "!decompcab!" (
	call :elog "%RED%!decm1.%LNG%!%RES% !UNACONT.%LNG%!"
	call :elog .
	pause>nul|set/p=.			!ANYKEY.%LNG%!
	call :exitn 3
) else (
    del /f /q "%decompcab%.tmp" %DEBUGREDIR%
	call :elog "%GRE%!decm2.%LNG%!%RES%"
	call :elog .
)

call :elog .
call :elog "!decm3.%LNG%!"
call :choiceEx "!ENTERYN.%LNG%! " "OSJYN" "N" "%CTIME%" "-rawMsg"
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
if not exist "%unrpycpy%" (
    call :elog "    %RED%!decm7.%LNG%! %unrpycpy%. !UNACONT.%LNG%!%RES%"
    call :elog .
    pause>nul|set/p=.			!ANYKEY.%LNG%!
    exit
) else (
    set "found=1"
)
if not exist "%deobfuscate%" (
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
			echo "%PYTHONHOME%python.exe" %PYNOASSERT% "%unrpycpy%" !OFFSET! --try-harder "%%f" >>"%UNRENLOG%"
			"%PYTHONHOME%python.exe" %PYNOASSERT% "%unrpycpy%" !OFFSET! --try-harder "%%f" >>"%UNRENLOG%" 2>&1
			set "error=!ERRORLEVEL!"
		) else (
			echo "%PYTHONHOME%python.exe" %PYNOASSERT% "%unrpycpy%" !OFFSET! "%%f" >>"%UNRENLOG%"
			"%PYTHONHOME%python.exe" %PYNOASSERT% "%unrpycpy%" !OFFSET! "%%f" >>"%UNRENLOG%" 2>&1
			set "error=!ERRORLEVEL!"
		)
	) else if exist !rpyfile! if "!owrpy!" == "y" (
		if not exist "!rpyfile!.org" (
            call :elog "    + !decm10.%LNG%! %YEL%'!relativePath!'%RES% !decm10a.%LNG%! %YEL%'!relativePath!.org'%RES%"
			copy "!rpyfile!" "!rpyfile!.org" %DEBUGREDIR%
		)

		call :elog "    + !decm11.%LNG%! %YEL%!relativePath!%RES%"
        if "!OPTION!" == "6" set "OPTION=4"
		if "!OPTION!" == "4" (
			echo "%PYTHONHOME%python.exe" %PYNOASSERT% "%unrpycpy%" --clobber !OFFSET! --try-harder "%%f" >>"%UNRENLOG%"
			"%PYTHONHOME%python.exe" %PYNOASSERT% "%unrpycpy%" --clobber !OFFSET! --try-harder "%%f" >>"%UNRENLOG%" 2>&1
			set "error=!ERRORLEVEL!"
		) else (
			echo "%PYTHONHOME%python.exe" %PYNOASSERT% "%unrpycpy%" --clobber !OFFSET! "%%f" >>"%UNRENLOG%"
			"%PYTHONHOME%python.exe" %PYNOASSERT% "%unrpycpy%" --clobber !OFFSET! "%%f" >>"%UNRENLOG%" 2>&1
			set "error=!ERRORLEVEL!"
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
if not "%unrpycpy%" == "" (
    del /f /q "%unrpycpy%o" %DEBUGREDIR%
    del /f /q "%unrpycpy%" %DEBUGREDIR%
)
if not "%decompcab%" == "" del /f /q "%decompcab%" %DEBUGREDIR%
if not "%deobfuscate%" == "" (
    del /f /q "%deobfuscate%" %DEBUGREDIR%
    del /f /q "%deobfuscate%o" %DEBUGREDIR%
)
rmdir /Q /S "__pycache__" %DEBUGREDIR%
if not "%decompilerdir%" == "" rmdir /Q /S "%decompilerdir%" %DEBUGREDIR%

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
if exist "%unren-console%" (
    call :elog "%YEL%!APRESENT.%LNG%!%RES%"
) else (
    >"%unren-console%.b64" (
        echo IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KZGVmaW5lIDk5OSBjb25maWcuY29uc29sZSA9IFRydWUNCmRlZmluZSA5OTkgY29uZmlnLmRldmVsb3BlciA9IFRydWUNCg==
    )
    echo "%PWRSHELL%" -NoProfile -Command "[IO.File]::WriteAllText('%unren-console%.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '%unren-console%.b64'))))" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "[IO.File]::WriteAllText('%unren-console%.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '%unren-console%.b64'))))" %DEBUGREDIR%
    if not exist "%unren-console%.tmp" (
        call :elog "%RED%!FAIL.%LNG%!%RES%"
    ) else (
        move /y "%unren-console%.tmp" "%unren-console%" %DEBUGREDIR%
        del /f /q "%unren-console%.b64" %DEBUGREDIR%
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
if exist "%unren-console%" (
    call :elog "%YEL%!APRESENT.%LNG%!%RES%"
) else (
    >"%unren-debug%.b64" (
        echo IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KZGVmaW5lIDk5OSBjb25maWcuZGVidWcgPSBUcnVlDQo=
    )
    echo "%PWRSHELL%" -NoProfile -Command "[IO.File]::WriteAllText('%unren-debug%.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '%unren-debug%.b64'))))" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "[IO.File]::WriteAllText('%unren-debug%.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '%unren-debug%.b64'))))" %DEBUGREDIR%
    if not exist "%unren-debug%.tmp" (
        call :elog "%RED%!FAIL.%LNG%!%RES%"
    ) else (
        move /y "%unren-debug%.tmp" "%unren-debug%" %DEBUGREDIR%
        del /f /q "%unren-debug%.b64" %DEBUGREDIR%
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

if exist "%unren-skip%" (
    call :elog "%YEL%!APRESENT.%LNG%!%RES%"
) else (
    >"%unren-skip%.b64" (
        echo IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KaW5pdCA5OTkgcHl0aG9uOg0KICAgIF9wcmVmZXJlbmNlcy5za2lwX3Vuc2VlbiA9IFRydWUNCiAgICBjb25maWcuYWxsb3dfc2tpcHBpbmcgPSBUcnVlDQogICAgcmVucHkuZ2FtZS5wcmVmZXJlbmNlcy5za2lwX3Vuc2VlbiA9IFRydWUNCiAgICByZW5weS5nYW1lLnByZWZlcmVuY2VzLnNraXBfYWZ0ZXJfY2hvaWNlcyA9IFRydWUNCiAgICByZW5weS5jb25maWcuZmFzdF9za2lwcGluZyA9IFRydWUNCiAgICB0cnk6DQogICAgICAgIGNvbmZpZy5rZXltYXBbJ3NraXAnXSA9IFsgJ0tfTENUUkwnLCAnS19SQ1RSTCcgXQ0KICAgIGV4Y2VwdDoNCiAgICAgICAgcGFzcw0K
    )
    echo "%PWRSHELL%" -NoProfile -Command "[IO.File]::WriteAllText('%unren-skip%.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '%unren-skip%.b64'))))" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "[IO.File]::WriteAllText('%unren-skip%.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '%unren-skip%.b64'))))" %DEBUGREDIR%
    if not exist "%unren-skip%.tmp" (
        call :elog "%RED%!FAIL.%LNG%!%RES%"
    ) else (
        move /y "%unren-skip%.tmp" "%unren-skip%" %DEBUGREDIR%
        del /f /q "%unren-skip%.b64" %DEBUGREDIR%
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

if exist "%unren-skipall%" (
    call :elog "%YEL%!APRESENT.%LNG%!%RES%"
) else (
    >"%unren-skipall%.b64" (
        echo IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KaW5pdCA5OTkgcHl0aG9uOg0KICAgIF9wcmVmZXJlbmNlcy5za2lwX3Vuc2VlbiA9IFRydWUNCiAgICBjb25maWcuYWxsb3dfc2tpcHBpbmcgPSBUcnVlDQogICAgcmVucHkuZ2FtZS5wcmVmZXJlbmNlcy5za2lwX3Vuc2VlbiA9IFRydWUNCiAgICByZW5weS5nYW1lLnByZWZlcmVuY2VzLnNraXBfYWZ0ZXJfY2hvaWNlcyA9IFRydWUNCiAgICByZW5weS5jb25maWcuZmFzdF9za2lwcGluZyA9IFRydWUNCiAgICBwcmVmZXJlbmNlcy50cmFuc2l0aW9ucyA9IDANCiAgICB0cnk6DQogICAgICAgIGNvbmZpZy5rZXltYXBbJ3NraXAnXSA9IFsgJ0tfTENUUkwnLCAnS19SQ1RSTCcgXQ0KICAgIGV4Y2VwdDoNCiAgICAgICAgcGFzcw0K
    )
    echo "%PWRSHELL%" -NoProfile -Command "[IO.File]::WriteAllText('%unren-skipall%.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '%unren-skipall%.b64'))))" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "[IO.File]::WriteAllText('%unren-skipall%.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '%unren-skipall%.b64'))))" %DEBUGREDIR%
    if not exist "%unren-skipall%.tmp" (
        call :elog "%RED%!FAIL.%LNG%!%RES%"
    ) else (
        move /y "%unren-skipall%.tmp" "%unren-skipall%" %DEBUGREDIR%
        del /f /q "%unren-skipall%.b64" %DEBUGREDIR%
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

if exist "%unren-rollback%" (
    call :elog "%YEL%!APRESENT.%LNG%!%RES%"
) else (
    > "%unren-rollback%.b64" (
        echo IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KaW5pdCA5OTkgcHl0aG9uOg0KICAgIHJlbnB5LmNvbmZpZy5yb2xsYmFja19lbmFibGVkID0gVHJ1ZQ0KICAgIHJlbnB5LmNvbmZpZy5oYXJkX3JvbGxiYWNrX2xpbWl0ID0gMjU2DQogICAgcmVucHkuY29uZmlnLnJvbGxiYWNrX2xlbmd0aCA9IDI1Ng0KICAgIGRlZiB1bnJlbl9ub2Jsb2NrKCphcmdzLCAqKmt3YXJncyk6DQogICAgICAgIHJldHVybg0KICAgIHJlbnB5LmJsb2NrX3JvbGxiYWNrID0gdW5yZW5fbm9ibG9jaw0KICAgIHRyeToNCiAgICAgICAgY29uZmlnLmtleW1hcFsncm9sbGJhY2snXSA9IFsgJ0tfUEFHRVVQJywgJ3JlcGVhdF9LX1BBR0VVUCcsICdLX0FDX0JBQ0snLCAnbW91c2Vkb3duXzQnIF0NCiAgICBleGNlcHQ6DQogICAgICAgIHBhc3MNCg==
    )
    echo "%PWRSHELL%" -NoProfile -Command "[IO.File]::WriteAllText('%unren-rollback%.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '%unren-rollback%.b64'))))" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "[IO.File]::WriteAllText('%unren-rollback%.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '%unren-rollback%.b64'))))" %DEBUGREDIR%
    if not exist "%unren-rollback%.tmp" (
        call :elog "%RED%!FAIL.%LNG%!%RES%"
    ) else (
        move /y "%unren-rollback%.tmp" "%unren-rollback%" %DEBUGREDIR%
        del /f /q "%unren-rollback%.b64" %DEBUGREDIR%
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

if exist "%unren-quick%" (
    call :elog "%YEL%!APRESENT.%LNG%!%RES%"
) else (
    >"%unren-quick%.b64" (
        echo IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KaW5pdCA5OTkgcHl0aG9uOg0KICAgIHRyeToNCiAgICAgICAgY29uZmlnLnVuZGVybGF5WzBdLmtleW1hcFsncXVpY2tTYXZlJ10gPSBRdWlja1NhdmUoKQ0KICAgICAgICBjb25maWcua2V5bWFwWydxdWlja1NhdmUnXSA9ICdLX0Y1Jw0KICAgICAgICBjb25maWcudW5kZXJsYXlbMF0ua2V5bWFwWydxdWlja0xvYWQnXSA9IFF1aWNrTG9hZCgpDQogICAgICAgIGNvbmZpZy5rZXltYXBbJ3F1aWNrTG9hZCddID0gJ0tfRjknDQogICAgZXhjZXB0Og0KICAgICAgICBwYXNzDQo=
    )
    echo "%PWRSHELL%" -NoProfile -Command "[IO.File]::WriteAllText('%unren-quick%.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '%unren-quick%.b64'))))" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "[IO.File]::WriteAllText('%unren-quick%.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '%unren-quick%.b64'))))" %DEBUGREDIR%
    if not exist "%unren-quick%.tmp" (
        call :elog "%RED%!FAIL.%LNG%!%RES%"
    ) else (
        move /y "%unren-quick%.tmp" "%unren-quick%" %DEBUGREDIR%
        del /f /q "%unren-quick%.b64" %DEBUGREDIR%
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

if exist "%unren-qmenu%" (
    call :elog "%YEL%!APRESENT.%LNG%!%RES%"
) else (
    >"%unren-qmenu%.b64" (
        echo IyBNYWRlIGJ5IChTTSkgYWthIEpvZUx1cm1lbCBAIGY5NXpvbmUudG8NCg0KaW5pdCBweXRob246DQogICAgZGVmIGFsd2F5c19lbmFibGVfcXVpY2tfbWVudSgpOg0KICAgICAgICBzdG9yZS5xdWlja19tZW51ID0gVHJ1ZQ0KICAgICAgICByZW5weS5zaG93X3NjcmVlbigicXVpY2tfbWVudSIpDQogICAgY29uZmlnLm92ZXJsYXlfZnVuY3Rpb25zLmFwcGVuZChhbHdheXNfZW5hYmxlX3F1aWNrX21lbnUpDQoNCiAgICBkZWYgZm9yY2VfcXVpY2tfbWVudV9vbl9pbnRlcmFjdCgpOg0KICAgICAgICBzdG9yZS5xdWlja19tZW51ID0gVHJ1ZQ0KICAgIGNvbmZpZy5pbnRlcmFjdF9jYWxsYmFja3MuYXBwZW5kKGZvcmNlX3F1aWNrX21lbnVfb25faW50ZXJhY3Qp
    )
    echo "%PWRSHELL%" -NoProfile -Command "[IO.File]::WriteAllText('%unren-qmenu%.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '%unren-qmenu%.b64'))))" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "[IO.File]::WriteAllText('%unren-qmenu%.tmp', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content '%unren-qmenu%.b64'))))" %DEBUGREDIR%
    if not exist "%unren-qmenu%.tmp" (
        call :elog "%RED%!FAIL.%LNG%!%RES%"
    ) else (
        move /y "%unren-qmenu%.tmp" "%unren-qmenu%" %DEBUGREDIR%
        del /f /q "%unren-qmenu%.b64" %DEBUGREDIR%
        call :elog "%GRE%!PASS.%LNG%!%RES%"
    )
)

goto :eof


:: Replace MCName in game files
:replace_mcname
set "unr-mcchange=%WORKDIR%\game\unren-mcchange.rpy"

set "rmcname.en=Please input the new name (without quotes): "
set "rmcname.fr=Veuillez saisir le nouveau nom (sans guillemets) : "
set "rmcname.es=Por favor ingrese el nuevo nombre (sin comillas): "
set "rmcname.it=Si prega di inserire il nuovo nome (senza virgolette): "
set "rmcname.de=Bitte geben Sie den neuen Namen (ohne Anführungszeichen) ein: "
set "rmcname.ru=Пожалуйста, введите новое имя (без кавычек): "
set "rmcname.zh=请输入新名称（不带引号）："

set "rmcname2.en=No name provided."
set "rmcname2.fr=Aucun nom fourni."
set "rmcname2.es=No se proporcionó ningún nombre."
set "rmcname2.it=Nome non fornito."
set "rmcname2.de=Kein Name angegeben."
set "rmcname2.ru=Имя не указано."
set "rmcname2.zh=未提供名称。"

set "rmcname3.en=Please input the old name (without quotes): "
set "rmcname3.fr=Veuillez saisir l'ancien nom (sans guillemets) : "
set "rmcname3.es=Por favor ingrese el nombre antiguo (sin comillas): "
set "rmcname3.it=Si prega di inserire il vecchio nome (senza virgolette): "
set "rmcname3.de=Bitte geben Sie den alten Namen (ohne Anführungszeichen) ein: "
set "rmcname3.ru=Пожалуйста, введите старое имя (без кавычек): "
set "rmcname3.zh=请输入旧名称（不带引号）："

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
echo "%PWRSHELL%" -NoProfile -Command "[IO.File]::WriteAllBytes('!unr-mcchange!.tmp', [Convert]::FromBase64String((Get-Content '!unr-mcchange!.b64' -Raw)))" >> "%UNRENLOG%"
"%PWRSHELL%" -NoProfile -Command "[IO.File]::WriteAllBytes('!unr-mcchange!.tmp', [Convert]::FromBase64String((Get-Content '!unr-mcchange!.b64' -Raw)))" %DEBUGREDIR%
if not exist "!unr-mcchange!.tmp" (
    echo %RED%!FAIL.%LNG%!%RES% !MISSING.%LNG%! !unr-mcchange!.tmp
    goto mcend
) else (
    del /f /q "!unr-mcchange!.b64" %DEBUGREDIR%
    echo "%PWRSHELL%" -NoProfile -Command "(Get-Content '!unr-mcchange!.tmp') -replace 'newmcname', '!newmcname!' | Set-Content '!unr-mcchange!'" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "(Get-Content '!unr-mcchange!.tmp') -replace 'newmcname', '!newmcname!' | Set-Content '!unr-mcchange!'" %DEBUGREDIR%
    echo "%PWRSHELL%" -NoProfile -Command "(Get-Content '!unr-mcchange!') -replace 'oldmcname', '!oldmcname!' | Set-Content '!unr-mcchange!'" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "(Get-Content '!unr-mcchange!') -replace 'oldmcname', '!oldmcname!' | Set-Content '!unr-mcchange!'" %DEBUGREDIR%
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
if "%LNG%" == "en"  set translation_lang=english
if "%LNG%" == "fr"  set translation_lang=french
if "%LNG%" == "es"  set translation_lang=spanish
if "%LNG%" == "it"  set translation_lang=italian
if "%LNG%" == "de"  set translation_lang=german
if "%LNG%" == "ru"  set translation_lang=russian
if "%LNG%" == "zh"  set translation_lang=chinese

cd /d "%WORKDIR%"

set "etext1.en=Searching for game name"
set "etext1.fr=Recherche du nom du jeu"
set "etext1.es=Buscando el nombre del juego"
set "etext1.it=Cercando il nome del gioco"
set "etext1.de=Suche nach dem Spieletitel"
set "etext1.ru=Поиск названия игры"
set "etext1.zh=正在搜索游戏名称"

set "etext2.en=No game files found with .exe, .py or .sh extensions."
set "etext2.fr=Aucun fichier de jeu trouvé avec les extensions .exe, .py ou .sh."
set "etext2.es=No se encontraron archivos de juego con las extensiones .exe, .py o .sh."
set "etext2.it=Nessun file di gioco trovato con le estensioni .exe, .py o .sh."
set "etext2.de=Keine Spieldateien mit den Erweiterungen .exe, .py oder .sh gefunden."
set "etext2.ru=Не найдено игровых файлов с расширениями .exe, .py или .sh."
set "etext2.zh=未找到带有 .exe、.py 或 .sh 扩展名的游戏文件。"

set "etext3.en=Enter the target translation language (%YEL%%translation_lang%%RES% by default): "
set "etext3.fr=Entrez la langue de traduction cible (%YEL%%translation_lang%%RES% par défaut) : "
set "etext3.es=Ingrese el idioma de traducción objetivo (%YEL%%translation_lang%%RES% por defecto): "
set "etext3.it=Inserisci la lingua di traduzione di destinazione (%YEL%%translation_lang%%RES% per impostazione predefinita): "
set "etext3.de=Geben Sie die Zielsprache für die Übersetzung ein (%YEL%%translation_lang%%RES% standardmäßig): "
set "etext3.ru=Введите целевой язык перевода (%YEL%%translation_lang%%RES% по умолчанию): "
set "etext3.zh=输入目标翻译语言（默认 %YEL%%translation_lang%%RES%）："

set "etext4.en=Unable to extract text for translation."
set "etext4.fr=Impossible d'extraire le texte pour la traduction."
set "etext4.es=No se pudo extraer el texto para la traducción."
set "etext4.it=Impossibile estrarre il testo per la traduzione."
set "etext4.de=Fehler beim Extrahieren des Textes für die Übersetzung."
set "etext4.ru=Не удалось извлечь текст для перевода."
set "etext4.zh=无法提取文本用于翻译。"

set "etext5.en=Please input the game name (without extension): "
set "etext5.fr=Veuillez saisir le nom du jeu (sans extension) : "
set "etext5.es=Por favor, ingrese el nombre del juego (sin extensión): "
set "etext5.it=Si prega di inserire il nome del gioco (senza estensione): "
set "etext5.de=Bitte geben Sie den Namen des Spiels ein (ohne Erweiterung): "
set "etext5.ru=Пожалуйста, введите название игры (без расширения): "
set "etext5.zh=请输入游戏名称（不带扩展名）："

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
if "%fname%"  == "" (
    echo %RED%!FAIL.%LNG%! !etext2.%LNG%!%RES%
    goto input_name
)

:input_name
call :elog .
set /p "fname=!etext5.%LNG%!"
if "%fname%" == "" (
    echo %RED%!FAIL.%LNG%! !etext2.%LNG%!%RES%
    goto input_name
) else (
    REM set "fname=%fname:.=%"
    if not exist "%WORKDIR%\%fname%.exe" (
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

if not exist "%WORKDIR%\game\tl\" (
	mkdir "%WORKDIR%\game\tl"
)

call :elog .
call :elog .
echo !choicet.%LNG%!... >> "%UNRENLOG%"
<nul set /p="!choicet.%LNG%!... "

cd /d "%WORKDIR%"
echo "%PYTHONHOME%python.exe" %PYNOASSERT% "%fname%.py" game translate %translation_lang% >> "%UNRENLOG%"
"%PYTHONHOME%python.exe" %PYNOASSERT% "%fname%.py" game translate %translation_lang% %DEBUGREDIR%
if %ERRORLEVEL% NEQ 0 (
	echo %RED%!FAIL.%LNG%! !etext4.%LNG%!%RES%
) else (
    echo %GRE%!PASS.%LNG%!%RES%
)
call :elog .

goto :eof


:: Add entry to registry
:add_reg
set "areg1.en=This will add an entry to the right-click menu for folders."
set "areg1.fr=Cela ajoutera une entrée au menu contextuel pour les dossiers."
set "areg1.es=Esto añadirá una entrada al menú contextual para las carpetas."
set "areg1.it=Questo aggiungerà una voce al menu contestuale per le cartelle."
set "areg1.de=Dies wird einen Eintrag zum Rechtsklick-Menü für Ordner hinzufügen."
set "areg1.ru=Это добавит элемент в контекстное меню для папок."
set "areg1.zh=这将为文件夹添加右键菜单项。"

set "areg2.en=When you select this option,"
set "areg2.fr=Lorsque vous sélectionnez cette option,"
set "areg2.es=Cuando seleccione esta opción,"
set "areg2.it=Quando selezioni questa opzione,"
set "areg2.de=Wenn Sie diese Option auswählen,"
set "areg2.ru=Когда вы выберете эту опцию,"
set "areg2.zh=当您选择此选项时，"

set "areg2a.en=the script "%SCRIPTDIR%%SCRIPTNAME%" will be executed."
set "areg2a.fr=le script "%SCRIPTDIR%%SCRIPTNAME%" sera exécuté."
set "areg2a.es=se ejecutará el script "%SCRIPTDIR%%SCRIPTNAME%"."
set "areg2a.it=verrà eseguito lo script "%SCRIPTDIR%%SCRIPTNAME%"."
set "areg2a.de=wird das Skript "%SCRIPTDIR%%SCRIPTNAME%" ausgeführt."
set "areg2a.ru=будет выполнен скрипт "%SCRIPTDIR%%SCRIPTNAME%"."
set "areg2a.zh=脚本 "%SCRIPTDIR%%SCRIPTNAME%" 将被执行。"

set "areg3.en=Adding the right-click menu entry to the registry... "
set "areg3.fr=Ajout de l'entrée de menu contextuel au registre... "
set "areg3.es=Adding the right-click menu entry to the registry... "
set "areg3.it=Aggiunta della voce del menu contestuale al registro... "
set "areg3.de=Hinzufügen des Rechtsklick-Menüeintrags zur Registrierung... "
set "areg3.ru=Добавление элемента контекстного меню в реестр... "
set "areg3.zh=正在向注册表添加右键菜单项... "

set "areg4.en=Run %SCRIPTNAME% Script"
set "areg4.fr=Exécuter le script %SCRIPTNAME%"
set "areg4.es=Ejecutar el script %SCRIPTNAME%"
set "areg4.it=Esegui lo script %SCRIPTNAME%"
set "areg4.de=Führen Sie das Skript %SCRIPTNAME% aus"
set "areg4.ru=Запустить скрипт %SCRIPTNAME%"
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
reg add "HKCR\Directory\shell\Run%SCRIPTNAME%" /v "Icon" /d "%SYSTEMROOT%\System32\shell32.dll,-154" /f %DEBUGREDIR%
reg add "HKCR\Directory\shell\Run%SCRIPTNAME%\command" /ve /d "%SYSTEMROOT%\System32\cmd.exe /c cd /d \"%%V\" && \"%SCRIPTDIR%%SCRIPTNAME%\" \"%%V\"" /f %DEBUGREDIR%
if %ERRORLEVEL% EQU 0 (
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
set "rreg1.fr=Cela supprimera l'entrée précédemment ajoutée du menu contextuel pour les dossiers."
set "rreg1.es=Esto eliminará la entrada previamente añadida del menú contextual para las carpetas."
set "rreg1.it=Questo rimuoverà la voce precedentemente aggiunta dal menu contestuale per le cartelle."
set "rreg1.de=Dies wird den zuvor hinzugefügten Eintrag aus dem Rechtsklick-Menü für Ordner entfernen."
set "rreg1.ru=Это удалит ранее добавленный элемент из контекстного меню для папок."
set "rreg1.zh=这将移除先前为文件夹添加的右键菜单项。"

set "rreg2.en=Removing the right-click menu entry from the registry... "
set "rreg2.fr=Suppression de l'entrée de menu contextuel du registre... "
set "rreg2.es=Eliminando la entrada del menú contextual del registro... "
set "rreg2.it=Rimozione della voce del menu contestuale dal registro... "
set "rreg2.de=Entfernen des Rechtsklick-Menüeintrags aus der Registrierung... "
set "rreg2.ru=Удаление элемента контекстного меню из реестра... "
set "rreg2.zh=正在从注册表中移除右键菜单项... "

call :check_admin

call :elog .
echo %YEL%!rreg1.%LNG%!%RES%
call :elog .
echo !rreg2.%LNG%! >> "%UNRENLOG%"
<nul set /p="!rreg2.%LNG%!"
:: Remove registry key
reg delete "HKCR\Directory\shell\RunUnrenForAll" /f %DEBUGREDIR%
reg delete "HKCR\Directory\shell\Run%SCRIPTNAME%" /f %DEBUGREDIR%
if %ERRORLEVEL% EQU 0 (
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
set "admright.fr=Vérification des droits administrateur"
set "admright.es=Comprobando derechos de administrador"
set "admright.it=Controllo dei diritti di amministratore"
set "admright.de=Überprüfung der Administratorrechte"
set "admright.ru=Проверка прав администратора"
set "admright.zh=检查管理员权限"

set "admright2.en=You did not run this script with administrator privileges."
set "admright2.fr=Vous n'avez pas lancé ce script avec des droits administrateur."
set "admright2.es=No ha iniciado este script con derechos de administrador."
set "admright2.it=Non hai avviato questo script con diritti di amministratore."
set "admright2.de=Sie haben dieses Skript nicht mit Administratorrechten gestartet."
set "admright2.ru=Вы не запустили этот скрипт с правами администратора."
set "admright2.zh=您没有以管理员权限运行此脚本。"

set "admright3.en=Restart the script with administrator rights."
set "admright3.fr=Relance du script avec des droits administrateur."
set "admright3.es=Reinicie el script con derechos de administrador."
set "admright3.it=Riavvia lo script con diritti di amministratore."
set "admright3.de=Starten Sie das Skript mit Administratorrechten neu."
set "admright3.ru=Перезапустите скрипт с правами администратора."
set "admright3.zh=请以管理员权限重新启动脚本。"

call :elog .
call :elog .
echo !admright.%LNG%!... >> "%UNRENLOG%"
<nul set /p="!admright.%LNG%!... "

net session %DEBUGREDIR%
if %ERRORLEVEL% EQU 0 (
    echo %GRE%!PASS.%LNG%!%RES%
) else (
	echo %RED%!FAIL.%LNG%!.%RES%
    call :elog .
    echo !admright2.%LNG%!
    echo !admright3.%LNG%!
    call :elog .
    timeout /t 2 >nul
    echo "%PWRSHELL%" -NoProfile -Command "Start-Process '%~f0' -ArgumentList '%WORKDIR%' -Verb RunAs" >> "%UNRENLOG%"
    "%PWRSHELL%" -NoProfile -Command "Start-Process '%~f0' -ArgumentList '%WORKDIR%' -Verb RunAs"

    goto exitn
)

goto :eof


:: When it's not unavailable, show message and exit
:unavailable
if "%RENPYVERSION%" == "7" (
    set "unavailable.en=This feature is unavailable in this version."
    set "unavailable.fr=Cette fonctionnalité n'est pas disponible dans cette version."
    set "unavailable.es=Esta función no está disponible en esta versión."
    set "unavailable.it=Questa funzione non è disponibile in questa versione."
    set "unavailable.de=Diese Funktion ist in dieser Version nicht verfügbar."
    set "unavailable.ru=Эта функция недоступна в этой версии."
    set "unavailable.zh=此功能在此版本中不可用。"
)
if "%RENPYVERSION%" == "8" (
    set "unavailable.en=This feature is unavailable for now, need more coding."
    set "unavailable.fr=Cette fonctionnalité n'est pas disponible pour le moment, nécessite plus de codage."
    set "unavailable.es=Esta función no está disponible por ahora, necesita más codificación."
    set "unavailable.it=Questa funzione non è disponibile per ora, necessita di più codice."
    set "unavailable.de=Diese Funktion ist derzeit nicht verfügbar, es wird mehr Programmierung benötigt."
    set "unavailable.ru=Эта функция недоступна, требуется больше кода."
    set "unavailable.zh=此功能暂不可用，需要更多编码。"
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
set "cfile.fr=Vérification que tous les fichiers sont présents"
set "cfile.es=Verificación de que todos los archivos están presentes"
set "cfile.it=Verifica che tutti i file siano presenti"
set "cfile.de=Überprüfung, ob alle Dateien vorhanden sind"
set "cfile.ru=Проверка наличия всех файлов"
set "cfile.zh=验证所有文件是否存在"

set "cdwnld.en=Download the missing file from:"
set "cdwnld.fr=Télécharger le fichier manquant depuis :"
set "cdwnld.es=Descargar el archivo faltante de:"
set "cdwnld.it=Scarica il file mancante da:"
set "cdwnld.de=Fehlende Datei herunterladen von:"
set "cdwnld.ru=Скачать недостающий файл с:"
set "cdwnld.zh=从以下位置下载缺失的文件："

echo !cfile.%LNG%!... >> "%UNRENLOG%"
<nul set /p="!cfile.%LNG%!..."
for %%F in (legacy current) do (
    if not exist "%SCRIPTDIR%UnRen-%%~F.bat" (
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
if exist "%SCRIPTDIR%%BASENAMENONEW%-new.bat" (
    if "!SCRIPTNAME!" == "%BASENAMENONEW%-new.bat" (
        copy /y "%SCRIPTDIR%%BASENAMENONEW%-new.bat" "%SCRIPTDIR%%BASENAMENONEW%.bat" %DEBUGREDIR%
    ) else (
        del /f /q "%SCRIPTDIR%%BASENAME%-new.bat" %DEBUGREDIR%
    )
)
del /f /q "%SCRIPTDIR%%BASENAMENONEW%.old" %DEBUGREDIR%

call :elog "%GRE% !PASS.%LNG%!%RES%"

exit /b


:: Params:
:: 1 - Message to display
:: 2 - Choices list (e.g. "YN" for Yes/No)
:: 3 - Default choice (e.g. "N" for No)
:: 4 - Timeout in seconds (e.g. "10" for 10 seconds)
:: 5 - Additional options (optional) (e.g. "-rawMsg" to not encapsulate the default choice in the choice list)
:choiceEx
    set "choiceEx_py=%TEMP%\choiceEx.py"
    del /f /q "%choiceEx_py%" %DEBUGREDIR%
    if not exist "%choiceEx_py%" (
        >"%choiceEx_py%.b64" (
            echo IyEvdXNyL2Jpbi9lbnYgcHl0aG9uDQojIC0qLSBjb2Rpbmc6IHV0Zi04IC0qLQ0KDQppbXBvcnQgc3lzDQppbXBvcnQgdGltZQ0KaW1wb3J0IG1zdmNydA0KaW1wb3J0IGNvZGVjcw0KDQppZiBzeXMudmVyc2lvbl9pbmZvWzBdIDwgMzoNCiAgICBpbXBvcnQgY3R5cGVzDQogICAgIyBGb3JjZSBsYSBjb25zb2xlIFdpbmRvd3MgZW4gVVRGLTgNCiAgICBjdHlwZXMud2luZGxsLmtlcm5lbDMyLlNldENvbnNvbGVDUCg2NTAwMSkNCiAgICBjdHlwZXMud2luZGxsLmtlcm5lbDMyLlNldENvbnNvbGVPdXRwdXRDUCg2NTAwMSkNCg0KICAgICMgQ1JVQ0lBTDogRW52ZWxvcHBlIHN0ZG91dCBhdmVjIHVuIHdyaXRlciBVVEYtOA0KICAgIHN5cy5zdGRvdXQgPSBjb2RlY3MuZ2V0d3JpdGVyKCd1dGYtOCcpKHN5cy5zdGRvdXQpDQogICAgc3lzLnN0ZGVyciA9IGNvZGVjcy5nZXR3cml0ZXIoJ3V0Zi04Jykoc3lzLnN0ZGVycikNCg0KIyBHw6hyZSBsZXMgZGV1eCBQeXRob24gMiBldCAzDQppZiBzeXMudmVyc2lvbl9pbmZvWzBdIDwgMzoNCiAgICBtc2cgPSBzeXMuYXJndlsxXS5kZWNvZGUoJ2xhdGluLTEnKSBpZiBpc2luc3RhbmNlKHN5cy5hcmd2WzFdLCBzdHIpIGVsc2Ugc3lzLmFyZ3ZbMV0NCmVsc2U6DQogICAgbXNnID0gc3lzLmFyZ3ZbMV0NCg0KY2hvaWNlcyAgICAgPSBzeXMuYXJndlsyXQ0KZGVmYXVsdCAgICAgPSBzeXMuYXJndlszXQ0KdGltZW91dCAgICAgPSBpbnQoc3lzLmFyZ3ZbNF0pDQpyYXcgICAgICAgICA9IChsZW4oc3lzLmFyZ3YpID4gNSBhbmQgc3lzLmFyZ3ZbNV0gPT0gIi1yYXdNc2ciKQ0KDQppZiByYXc6DQogICAgZGlzcGxheSA9IG1zZw0KZWxzZToNCiAgICBkaXNwID0gWyJbJXNdIiAlIGMgaWYgYyA9PSBkZWZhdWx0IGVsc2UgYyBmb3IgYyBpbiBjaG9pY2VzXQ0KICAgIGRpc3BsYXkgPSAiJXMgKCVzLCB0aW1lb3V0ICVzcykgOiAiICUgKG1zZywgJy8nLmpvaW4oZGlzcCksIHRpbWVvdXQpDQoNCnN5cy5zdGRvdXQud3JpdGUoZGlzcGxheSkNCnN5cy5zdGRvdXQuZmx1c2goKQ0KDQplbmQgPSB0aW1lLnRpbWUoKSArIHRpbWVvdXQNCnJlc3VsdCA9IGRlZmF1bHQNCg0Kd2hpbGUgdGltZS50aW1lKCkgPCBlbmQ6DQogICAgaWYgbXN2Y3J0LmtiaGl0KCk6DQogICAgICAgIGtleSA9IG1zdmNydC5nZXR3Y2goKQ0KICAgICAgICBpZiBrZXkgPT0gIlxyIjogICMgRW50ZXINCiAgICAgICAgICAgIGJyZWFrDQogICAgICAgIGtleSA9IGtleS51cHBlcigpDQogICAgICAgIGlmIGtleSBpbiBjaG9pY2VzOg0KICAgICAgICAgICAgcmVzdWx0ID0ga2V5DQogICAgICAgICAgICBicmVhaw0KICAgIHRpbWUuc2xlZXAoMC4wNSkNCg0Kc3lzLnN0ZG91dC53cml0ZShyZXN1bHQpDQpzeXMuc3Rkb3V0LndyaXRlKCJcbiIpDQpzeXMuZXhpdChjaG9pY2VzLmluZGV4KHJlc3VsdCkgKyAxKQ==
        )
        "%PWRSHELL%" -NoProfile -Command "& { [IO.File]::WriteAllBytes('%choiceEx_py%.tmp', [Convert]::FromBase64String([IO.File]::ReadAllText('%choiceEx_py%.b64')))}"
        move /y "%choiceEx_py%.tmp" "%choiceEx_py%" %DEBUGREDIR%
        del /f /q "%choiceEx_py%.b64" %DEBUGREDIR%
    )
    echo "%PYTHONHOME%\python.exe" %PYNOASSERT% "%choiceEx_py%" "%~1" "%~2" "%~3" "%~4" "%~5" >> "%UNRENLOG%"
    "%PYTHONHOME%\python.exe" %PYNOASSERT% "%choiceEx_py%" "%~1" "%~2" "%~3" "%~4" "%~5"

    exit /b %ERRORLEVEL%


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
       echo. >> "%UNRENLOG%"
    )
) else (
    echo !msg!

    if defined UNRENLOG (
        :: Strip color variables for logging
        set "cleanmsg=!msg!"
        for %%C in (GRY RED GRE YEL MAG CYA RES) do (
            call set "cleanmsg=%%cleanmsg:!%%C!=%%"
        )
        echo !cleanmsg! >> "%UNRENLOG%"
    )
)

exit /b


:: Call :exitn for cleanup only or goto exitn for ending script
:exitn
set "val=%~1"

if %DEBUGLEVEL% GEQ 1 (
    echo === Variables ===
    set
    echo === Variables ===
)

:: Restore modified configuration and we exit with the appropriate code
%SYSTEMROOT%\System32\chcp.com %OLD_CP% >nul

:: Restore original console mode
if %DEBUGLEVEL% EQU 0 (
    %SYSTEMROOT%\System32\mode.com con: cols=!ORIG_COLS! lines=!ORIG_LINES!

    REM Remove old bug entries
    reg delete "HKCU\Console\MyScript" /f %DEBUGREDIR%
    reg delete "HKCU\Console\UnRen-forall.bat" /f %DEBUGREDIR%
)

if defined val exit !val!

exit /b 0
