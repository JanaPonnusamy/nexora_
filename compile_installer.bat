@echo off
cd /d "%~dp0"
set "ISCC="
where ISCC >nul 2>nul && set "ISCC=ISCC"
if not defined ISCC if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  echo ISCC_NOT_FOUND
  exit /b 1
)
if not exist "release" mkdir "release"
"%ISCC%" /F"HO_Setup_v2" "installer\HO_Setup.iss"
if errorlevel 1 (
  echo COMPILE_FAILED
  exit /b 1
)
echo COMPILE_DONE
