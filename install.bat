@echo off
setlocal EnableExtensions
title Claude Monitor - Windows installer

rem ---------------------------------------------------------------
rem  Run this once (double-click). It finds a working Python 3 and has
rem  install_windows.py create the "Claude Monitor" shortcuts
rem  (Desktop + Start Menu).
rem
rem  Keep this file ASCII-only with CRLF line endings (see .gitattributes):
rem  cmd.exe misparses UTF-8 text and LF-only batch files.
rem ---------------------------------------------------------------

set "ROOT=%~dp0"

if not exist "%ROOT%install_windows.py" (
    echo ERROR: install_windows.py was not found next to install.bat.
    echo Keep install.bat in the project's root folder.
    goto :fail
)

rem "where python" is not a reliable check: on Windows 10/11 it also matches the
rem Microsoft Store stub, which is not Python. So really run each candidate.
set "PY="
for %%C in ("py -3" "python" "python3") do (
    if not defined PY (
        %%~C -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
        if not errorlevel 1 set "PY=%%~C"
    )
)

if not defined PY (
    echo.
    echo ERROR: Python 3.8 or newer was not found.
    echo Install it from https://www.python.org/downloads/ and run this file again.
    echo ^(If Windows opened the Microsoft Store instead, that is the Store stub:
    echo  install Python from python.org, then try again.^)
    goto :fail
)

echo Using: %PY%
%PY% "%ROOT%install_windows.py"
if errorlevel 1 goto :fail

echo.
echo Done. Use the "Claude Monitor" shortcut on your Desktop or in the Start Menu.
echo The server runs hidden; its log is %%TEMP%%\claude-monitor.log
echo To stop it:  python launcher.pyw --stop
echo.
pause
exit /b 0

:fail
echo.
pause
exit /b 1
