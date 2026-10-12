@echo off
setlocal
cd /d "%~dp0"
docker compose version >nul 2>&1
if errorlevel 1 (
  echo Install Docker Desktop with Linux containers and start it first.
  if not defined POD_NO_PAUSE pause
  exit /b 1
)
docker compose up --build -d --wait --wait-timeout 180
if errorlevel 1 (
  echo Startup failed. Check Docker Desktop, port conflicts and docker compose logs.
  if not defined POD_NO_PAUSE pause
  exit /b 1
)
for /f "tokens=2 delims=:" %%P in ('docker compose port classroom 8765') do set "POD_PORT=%%P"
echo Teacher: http://localhost:%POD_PORT%/teacher
echo Projector: http://localhost:%POD_PORT%/projector
echo Keep the teacher token below private. Containers keep running after this window closes.
docker compose logs --tail 30 classroom
if not defined POD_NO_BROWSER start "" "http://localhost:%POD_PORT%/teacher"
if not defined POD_NO_PAUSE pause
