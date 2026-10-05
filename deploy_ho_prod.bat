@echo off
REM ============================================================================
REM  Nexora HO production deploy — run this AT each prod HO box (.73 and .32).
REM
REM  Brings the local E:\Nexora checkout up to origin/main, reinstalls backend
REM  deps (this release adds the device-identity 'cryptography' dependency and
REM  the stock_client_ops fleet module), restarts the :8000 backend the same way
REM  the logon scheduled task does, and verifies the new fleet routes are live.
REM
REM  Usage (from an Administrator command prompt on the prod box):
REM      E:\Nexora\deploy_ho_prod.bat
REM
REM  Safe to re-run. It discards local working-tree drift on TRACKED files
REM  (e.g. the auto-written whatsapp send_log.json) so the pull is never blocked;
REM  it never touches untracked files such as backend\.env / ho.env.
REM ============================================================================
setlocal enabledelayedexpansion
set REPO=E:\Nexora
set BACKEND=%REPO%\backend
set PY=%BACKEND%\.venv\Scripts\python.exe

echo(
echo ==== Nexora HO deploy on %COMPUTERNAME% @ %date% %time% ====
cd /d "%REPO%" || (echo ERROR: %REPO% not found & exit /b 1)

echo(
echo [1/5] Fetching origin...
git fetch origin || (echo ERROR: git fetch failed & exit /b 1)

echo(
echo [2/5] Discarding tracked runtime drift + checking out main...
REM Runtime files the app rewrites (send log, etc.) would block the pull.
git checkout -- . 2>nul
git checkout main || (echo ERROR: could not switch to main & exit /b 1)
git pull --ff-only origin main || (
    echo ERROR: fast-forward pull failed. The local checkout has diverged from
    echo origin/main. Resolve manually ^(git status^) then re-run.
    exit /b 1
)
for /f "delims=" %%v in ('git rev-parse --short HEAD') do set HEAD=%%v
echo     now at main @ %HEAD%

echo(
echo [3/6] Installing backend dependencies...
"%PY%" -m pip install -r "%BACKEND%\requirements.txt" --disable-pip-version-check
if errorlevel 1 (echo ERROR: pip install failed & exit /b 1)

echo(
echo [4/6] Rebuilding HO web UI (served from frontend\dist)...
REM Best-effort: only if node/npm are present on this box. The SPA is served
REM statically from UNINEX_FRONTEND_DIR, so new pages (e.g. Backend Update)
REM appear only after this rebuild. Skipped cleanly if npm is unavailable.
where npm >nul 2>&1
if errorlevel 1 (
    echo     npm not found; skipping UI rebuild ^(backend-only deploy^).
) else (
    pushd "%REPO%\frontend"
    if not exist node_modules (
        echo     installing frontend deps ^(first run^)...
        call npm install --no-audit --no-fund
    )
    call npm run build
    if errorlevel 1 (echo     WARNING: frontend build failed; UI not updated.) else (echo     UI rebuilt.)
    popd
)

echo(
echo [5/6] Restarting backend on :8000...
REM Stop the current uvicorn (match the PID LISTENING on :8000), then relaunch
REM via the same scheduled task logon uses; fall back to the bat if no task.
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000" ^| findstr LISTENING') do (
    echo     stopping pid %%p
    taskkill /F /PID %%p >nul 2>&1
)
timeout /t 2 /nobreak >nul
schtasks /run /tn "NexoraBackend" >nul 2>&1
if errorlevel 1 (
    echo     scheduled task not found; launching start-prod-8000.bat detached
    start "nexora-backend" /min cmd /c "%BACKEND%\start-prod-8000.bat"
)

echo(
echo [6/6] Verifying fleet routes are live...
set OK=0
for /l %%i in (1,1,15) do (
    if "!OK!"=="0" (
        curl -s --max-time 3 http://127.0.0.1:8000/openapi.json | findstr /C:"stock-client-ops" >nul 2>&1
        if not errorlevel 1 (set OK=1) else (timeout /t 2 /nobreak >nul)
    )
)
if "!OK!"=="1" (
    echo     OK: /api/stock-client-ops routes are being served.
    echo(
    echo ==== DEPLOY SUCCEEDED on %COMPUTERNAME% ^(main @ !HEAD!^) ====
    exit /b 0
) else (
    echo     WARNING: backend did not report stock-client-ops routes within 30s.
    echo     Check %BACKEND%\logs\prod-8000.log and that :8000 is listening.
    exit /b 2
)
