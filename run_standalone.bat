@echo off
setlocal
title Fusion Frame - Run (standalone test mode)

echo ============================================================
echo  Fusion Frame - standalone launch
echo ============================================================
echo.
echo IMPORTANT: This only opens the window to check layout/styling.
echo It will NOT have access to DaVinci Resolve (Grab Clip, import,
echo etc. will not work) - that is a deliberate restriction of the
echo Resolve Free version, not a bug.
echo.
echo To use Fusion Frame WITH Resolve, you must launch it from inside
echo Resolve instead:
echo   1. Open a clip on the Fusion page
echo   2. Scripts -^> Comp -^> FusionFrame
echo.
echo (Run install.bat first if you have not already, so that menu
echo  item exists.)
echo.
pause

rem ---------------------------------------------------------------
rem Use the same Python that install.bat installed PySide6 into.
rem We re-detect it the same way so run.bat works independently.
rem Skips the Windows Store "python.exe" stub, which exists on PATH
rem on many machines but does not run real Python (it just opens
rem the Store and exits with code 0 - looks like success but isn't).
rem ---------------------------------------------------------------
setlocal enabledelayedexpansion

set "RESOLVE_PY="
set "CANDIDATE1=C:\Program Files\Blackmagic Design\DaVinci Resolve\python.exe"

if exist "%CANDIDATE1%" set "RESOLVE_PY=%CANDIDATE1%"

if not defined RESOLVE_PY (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        if not defined RESOLVE_PY (
            echo %%P | findstr /i "WindowsApps" >nul
            if errorlevel 1 set "RESOLVE_PY=%%P"
        )
    )
)

if not defined RESOLVE_PY (
    echo.
    echo Could not find a real Python install ^(only the Windows Store
    echo stub was found, if anything^). Run install.bat first, or paste
    echo the Python path Resolve uses below.
    echo.
    set /p RESOLVE_PY=Python path ^(or press Enter to cancel^):
    if not defined RESOLVE_PY (
        pause
        exit /b 1
    )
)

if not exist "!RESOLVE_PY!" (
    echo.
    echo ERROR: "!RESOLVE_PY!" does not exist.
    pause
    exit /b 1
)

set "PLUGIN_ROOT=%~dp0"
if "%PLUGIN_ROOT:~-1%"=="\" set "PLUGIN_ROOT=%PLUGIN_ROOT:~0,-1%"
set "PLUGIN_SRC=%PLUGIN_ROOT%\src"

echo Using Python: !RESOLVE_PY!
echo.

"!RESOLVE_PY!" -c "import sys; sys.path.insert(0, r'%PLUGIN_SRC%'); from fusion_frame import run; run(None)"
set "PYEXIT=!errorlevel!"

if not "!PYEXIT!"=="0" (
    echo.
    echo Window did not launch ^(exit code !PYEXIT!^). Common causes:
    echo   - PySide6 not installed for this Python -^> run install.bat
    echo   - This is not the Python Resolve actually uses
    echo.
    echo To check PySide6 manually, run:
    echo   "!RESOLVE_PY!" -m pip show PySide6
    pause
) else (
    echo.
    echo Window closed normally.
)
pause
