@echo off
REM ============================================================================
REM  Nexora production backend (Head Office).
REM  Router NAT forwards external 122.252.246.181:8443 -> this machine
REM  (192.168.10.80) INTERNAL port 8000, so the backend must listen on 8000.
REM  Serves the API + the web SPA (UNINEX_FRONTEND_DIR in backend\.env).
REM  Auto-started on logon/boot by the "NexoraBackend" scheduled task.
REM ============================================================================
cd /d E:\Nexora\backend

REM Don't start a second copy if one is already listening on 8000.
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo [%date% %time%] backend already running on :8000, skipping >> logs\prod-8000.log
    exit /b 0
)

if not exist logs mkdir logs
echo [%date% %time%] starting Nexora backend on 0.0.0.0:8000 >> logs\prod-8000.log
.venv\Scripts\python.exe -m uvicorn api.app:app --host 0.0.0.0 --port 8000 >> logs\prod-8000.log 2>&1
