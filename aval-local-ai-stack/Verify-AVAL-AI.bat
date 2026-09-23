@echo off
REM Double-click to check the AVAL Local AI Stack on Windows.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\verify.ps1"
echo.
pause
