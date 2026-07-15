@echo off
REM ===========================================================================
REM  Nexora - one-click DEV launcher.
REM  Starts the backend (FastAPI/uvicorn on :8000) and the frontend
REM  (Vite dev server on :5173) each in their own window, then opens the
REM  browser. Close the two server windows to stop.
REM
REM  Just double-click this file, or run  launch.bat  from a terminal.
REM ===========================================================================
setlocal
cd /d "%~dp0"
title Nexora Launcher

echo(
echo  Nexora dev launcher
echo  --------------------------------------------------
echo  Backend : http://localhost:8000   (API docs: /docs)
echo  Frontend: http://localhost:5173
echo  --------------------------------------------------
echo(

REM --- Prerequisite checks --------------------------------------------------
where python >nul 2>nul || (echo [ERROR] Python is not on PATH. Install Python 3.12 and retry. & pause & exit /b 1)
where npm    >nul 2>nul || (echo [ERROR] npm is not on PATH. Install Node.js and retry.        & pause & exit /b 1)

REM --- Backend: uvicorn on :8000 (start-in = backend\) -----------------------
REM Runs from its own venv (backend\.venv) — keeps heavy/pinned deps like
REM paddleocr/paddlepaddle isolated from the system Python and any other
REM projects on this machine. Created on first run if missing.
echo Starting backend...
if not exist "%~dp0backend\.venv\Scripts\python.exe" (
    echo Creating backend virtual environment, please wait...
    python -m venv "%~dp0backend\.venv"
    "%~dp0backend\.venv\Scripts\python.exe" -m pip install -r "%~dp0backend\requirements.txt"
)
start "Nexora Backend" /d "%~dp0backend" cmd /k .venv\Scripts\python.exe -m uvicorn api.app:app --host 127.0.0.1 --port 8000

REM --- Frontend: install deps on first run, then Vite dev on :5173 -----------
echo Starting frontend...
start "Nexora Frontend" /d "%~dp0frontend" cmd /k "if not exist node_modules (echo Installing frontend dependencies, please wait... & npm install) & npm run dev"

REM --- Open the app once the dev server has had a moment to boot -------------
echo Waiting for the dev server to come up...
timeout /t 6 /nobreak >nul
start "" "http://localhost:5173"

echo(
echo  Launched. Two windows opened (Backend + Frontend).
echo  Close those windows to stop the servers.
echo(
endlocal
