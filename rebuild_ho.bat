@echo off
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean ho_setup\HO_Backend.spec || exit /b 1
python -m PyInstaller --noconfirm --clean ho_setup\HO_Deploy.spec || exit /b 1
python -m PyInstaller --noconfirm --clean ho_setup\HO_Uninstall.spec || exit /b 1
echo REBUILD_DONE
