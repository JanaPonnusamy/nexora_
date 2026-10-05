@echo off
REM Launches the Nexora Supplier Stock desktop (Electron) client.
REM Starts the backend API first if it isn't already running, then
REM starts the client's dev server and lets it auto-launch Electron.

cd /d "%~dp0"

netstat -ano | findstr ":8000" | findstr "LISTENING" >nul
if errorlevel 1 (
    echo Starting backend API...
    start "Nexora Backend" /min cmd /c "cd /d E:\Nexora\backend && .venv\Scripts\python.exe -m uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload"
)

echo Starting Nexora Supplier Stock client...
REM scripts/wait-and-launch.mjs now waits for both Vite and API health. A fixed
REM sleep was unreliable on cold starts and opened the UI before data was ready.
call npm run dev
