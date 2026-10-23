@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0classroom.ps1" start
set "result=%errorlevel%"
if not defined POD_NO_PAUSE pause
exit /b %result%
