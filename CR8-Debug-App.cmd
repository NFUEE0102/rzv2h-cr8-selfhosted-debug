@echo off
rem CR8 Debug App (Windows): one window - board IP/user/password, install, start, e2 studio.
rem Prefers CR8DebugApp.exe (from the Releases page, placed next to this file); otherwise runs
rem the Python source, which needs Python 3 from python.org and:  py -3 -m pip install paramiko
setlocal
cd /d "%~dp0"
if exist "%~dp0CR8DebugApp.exe" (
    start "" "%~dp0CR8DebugApp.exe"
    exit /b 0
)
where py >nul 2>nul
if errorlevel 1 (
    echo Neither CR8DebugApp.exe ^(download it from the Releases page into this folder^)
    echo nor Python 3 ^(python.org, "py" launcher^) was found.
    pause
    exit /b 1
)
py -3 -c "import paramiko" 2>nul || py -3 -m pip install paramiko
start "" pythonw -3 "%~dp0e2studio\windows\cr8_debug_app.py" 2>nul || py -3 "%~dp0e2studio\windows\cr8_debug_app.py"
endlocal
