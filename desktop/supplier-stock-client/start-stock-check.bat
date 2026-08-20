@echo off
REM Launches the Nexora Stock Check desktop (Electron) client — the same app
REM as start-desktop-client.bat, but locked to the Stock Availability screen.
REM Starts the backend API first if it isn't already running, then starts the
REM client's dev server and lets it auto-launch Electron in stock-only mode.

cd /d "%~dp0"

netstat -ano | findstr ":8000" | findstr "LISTENING" >nul
if errorlevel 1 (
    echo Starting backend API...
    start "Nexora Backend" /min cmd /c "cd /d E:\Nexora\backend && .venv\Scripts\python.exe -m uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload"
    timeout /t 5 /nobreak >nul
)

echo Starting Nexora Stock Check client...
call npm run dev:stock
