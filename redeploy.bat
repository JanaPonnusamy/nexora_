@echo off
setlocal enabledelayedexpansion
REM ============================================================================
REM  Nexora HO redeploy: rebuild the SPA and restart the backend so new API
REM  routes and UI actually load. The backend runs elevated, so this MUST be
REM  run as Administrator:  right-click redeploy.bat -> "Run as administrator".
REM ============================================================================
cd /d "%~dp0"

echo(
echo === [1/3] Stopping backend listening on port 8000 ===
set "KILLED="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":8000 .*LISTENING"') do (
    echo   killing PID %%p
    taskkill /F /PID %%p >nul 2>&1
    set "KILLED=1"
)
if not defined KILLED echo   (nothing was listening on 8000)

echo(
echo === [2/3] Building frontend (frontend\dist) ===
pushd "%~dp0frontend"
call npm run build
if errorlevel 1 (
    echo   FRONTEND BUILD FAILED - aborting so the old build is not left half-updated.
    popd
    pause
    exit /b 1
)
popd

echo(
echo === [3/3] Starting backend ===
start "Nexora HO Backend" cmd /c "%~dp0backend\start_ho.bat"

echo(
echo Waiting for the backend to come up...
timeout /t 7 >nul

echo(
echo === Verifying new routes are live ===
curl -s http://127.0.0.1:8000/openapi.json | findstr /c:"db/health" >nul
if errorlevel 1 (
    echo   NOT FOUND: /api/legacy-order/db/health is missing.
    echo   The backend may still be starting, or an old process is still bound to 8000.
    echo   Check backend\logs\backend.log
) else (
    echo   OK: /api/legacy-order/db/health is registered. New code is live.
    echo   Now hard-refresh the browser (Ctrl+Shift+R) on the Legacy Order page.
)
echo(
pause
