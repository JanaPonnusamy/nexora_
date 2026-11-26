@echo off
REM Launches the NexTech MediQ Workspace desktop (Electron) client.
cd /d "%~dp0"
echo Starting NexTech MediQ Workspace...
call npm run dev
