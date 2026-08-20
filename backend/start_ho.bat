@echo off
cd /d E:\Nexora\backend
set NEXORA_HO_INSTALL=E:\Nexora\backend
".venv\Scripts\python.exe" -m uvicorn api.app:app --host 0.0.0.0 --port 8000 >> logs\backend.log 2>&1
