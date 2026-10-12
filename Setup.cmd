@echo off
setlocal
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
  echo uv is required. Install from https://docs.astral.sh/uv/getting-started/installation/
  pause
  exit /b 1
)
uv sync --frozen --python 3.11
if errorlevel 1 goto :failed
docker info >nul 2>nul
if errorlevel 1 (
  echo Start Docker Desktop, wait until it is ready, then run Setup again.
  pause
  exit /b 1
)
docker build -t pod-classroom-bot:local sandbox
if errorlevel 1 goto :failed
echo.
echo Setup complete. Double-click Start-classroom.cmd.
pause
exit /b 0
:failed
echo Setup failed. Read the error above; no student code was executed.
pause
exit /b 1
