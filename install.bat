@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title Claude Monitor - Installer

REM ============================================================
REM  نصب میان‌بر دسکتاپ برای «کلاد مانیتور» روی ویندوز
REM  این فایل را یک‌بار با دابل‌کلیک اجرا کن.
REM  بعدش یه میان‌بر به اسم "Claude Monitor" روی دسکتاپ پیدا می‌کنی
REM  که با کلیک روش، سرور بی‌صدا (بدون پنجره‌ی سیاه) روشن میشه
REM  و داشبورد توی مرورگر پیش‌فرضت باز میشه.
REM ============================================================

set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"
set "SERVER_DIR=%DIR%\server"
set "ICON=%DIR%\assets\claude-monitor.png"
set "LAUNCH_VBS=%DIR%\claude-monitor-launch.vbs"
set "LAUNCH_BAT=%DIR%\claude-monitor-launch.bat"
set "PORT=8765"

echo در حال بررسی پایتون...
where python >nul 2>nul
if errorlevel 1 (
    where python3 >nul 2>nul
    if errorlevel 1 (
        echo.
        echo خطا: پایتون پیدا نشد.
        echo لطفاً از https://www.python.org/downloads/ نصبش کن
        echo و حتماً هنگام نصب گزینه‌ی "Add python.exe to PATH" را فعال کن.
        echo.
        pause
        exit /b 1
    )
    set "PYCMD=python3"
) else (
    set "PYCMD=python"
)
echo پایتون پیدا شد: %PYCMD%

REM ---------- ساخت اسکریپت لانچر (bat) که سرور را بالا می‌آورد ----------
> "%LAUNCH_BAT%" (
    echo @echo off
    echo setlocal
    echo set "PORT=%PORT%"
    echo set "SERVER_DIR=%SERVER_DIR%"
    echo set "PYCMD=%PYCMD%"
    echo REM اگه سرور از قبل روشنه، دوباره بالاش نیار
    echo powershell -NoProfile -Command "try { (New-Object Net.WebClient^).DownloadString('http://localhost:%PORT%/'^) ^| Out-Null; exit 0 } catch { exit 1 }" ^>nul 2^>nul
    echo if not "%%errorlevel%%"=="0" ^(
    echo     cd /d "%%SERVER_DIR%%"
    echo     start "" /min cmd /c "%%PYCMD%% server.py ^>^> "%%TEMP%%\claude-monitor.log" 2^>^&1"
    echo     for /l %%%%i in ^(1,1,10^) do ^(
    echo         powershell -NoProfile -Command "try { (New-Object Net.WebClient^).DownloadString('http://localhost:%%PORT%%/'^) ^| Out-Null; exit 0 } catch { exit 1 }" ^>nul 2^>nul
    echo         if "%%errorlevel%%"=="0" goto :serverup
    echo         timeout /t 1 /nobreak ^>nul
    echo     ^)
    echo     :serverup
    echo ^)
    echo start "" "http://localhost:%%PORT%%/"
)

REM ---------- ساخت VBS برای اجرای بی‌صدای bat بالا (بدون پنجره‌ی سیاه) ----------
> "%LAUNCH_VBS%" (
    echo Set WshShell = CreateObject^("WScript.Shell"^)
    echo WshShell.Run chr^(34^) ^& "%LAUNCH_BAT%" ^& chr^(34^), 0
    echo Set WshShell = Nothing
)

echo لانچر ساخته شد.

REM ---------- ساخت میان‌بر روی دسکتاپ که به VBS بالا اشاره می‌کنه ----------
set "DESKTOP=%USERPROFILE%\Desktop"
set "SHORTCUT=%DESKTOP%\Claude Monitor.lnk"

powershell -NoProfile -Command ^
    "$ws = New-Object -ComObject WScript.Shell;" ^
    "$sc = $ws.CreateShortcut('%SHORTCUT%');" ^
    "$sc.TargetPath = '%LAUNCH_VBS%';" ^
    "$sc.WorkingDirectory = '%DIR%';" ^
    "$sc.IconLocation = '%ICON%';" ^
    "$sc.Description = 'Claude Monitor';" ^
    "$sc.Save()"

if exist "%SHORTCUT%" (
    echo.
    echo نصب کامل شد.
    echo میان‌بر «Claude Monitor» روی دسکتاپ ساخته شد.
    echo با دابل‌کلیک روش، سرور بی‌صدا اجرا میشه و داشبورد باز میشه.
    echo ^(لاگ سرور توی %%TEMP%%\claude-monitor.log نوشته میشه.^)
) else (
    echo.
    echo هشدار: میان‌بر ساخته نشد. می‌تونی مستقیم "%LAUNCH_VBS%" رو دابل‌کلیک کنی.
)

echo.
pause
