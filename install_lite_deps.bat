@echo off
cd /d "%~dp0"
python -m pip install --upgrade pip || exit /b 1
python -m pip install -r ho_setup\requirements.txt || exit /b 1
python -m pip install -r C:\Users\Pharma\AppData\Local\Temp\claude\e--Nexora\89f22b19-29e1-474c-bfd7-cb9efcf8b7e2\scratchpad\backend_requirements_lite.txt || exit /b 1
echo INSTALL_DONE
