@echo off
REM ============================================================================
REM  Restart the HO backend on :8000 so new API routes load (the NexoraBackend
REM  task runs uvicorn WITHOUT --reload). Double-click: it asks for admin itself.
REM  Backend is down ~3-5 seconds. Does NOT pull code or rebuild anything.
REM ============================================================================
net session >nul 2>&1
if errorlevel 1 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
)

echo === Stopping backend on port 8000 ===
schtasks /end /tn NexoraBackend >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":8000 .*LISTENING"') do (
    echo   killing PID %%p
    taskkill /T /F /PID %%p >nul 2>&1
)
timeout /t 2 >nul

echo === Starting backend (NexoraBackend task) ===
schtasks /run /tn NexoraBackend
echo Waiting for it to come up...
timeout /t 10 >nul

curl -s http://127.0.0.1:8000/openapi.json | findstr /c:"\"openapi\"" >nul
if errorlevel 1 (
    echo   NOT READY yet - wait a few seconds and reopen the screen, or check backend\logs\prod-8000.log
) else (
    echo   OK - backend restarted with the new code.
)
echo(
pause
