@echo off
rem One-time Windows host setup (asks for the board address, installs paramiko, builds the demo
rem firmware with headless e2 studio, imports it, puts the shortcuts on the Desktop).
rem Needs: e2 studio 2025-01 + FSP 3.1.0 under C:\Renesas, Python 3 from python.org.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0e2studio\windows\install-host.ps1" %*
pause
