@echo off
REM ===========================================================================
REM  UniNex HO - one-command build.
REM  build.bat  ->  frontend build -> PyInstaller (3 exes) -> Inno Setup
REM             ->  release\HO_Setup.exe
REM
REM  Run from the repository root on a Windows build machine.
REM  Prerequisites: Python 3.12 (64-bit), Node.js + npm, Inno Setup 6 (ISCC),
REM                 ODBC Driver 17, and ho_setup\assets\NEXORA_PLATFORM.bak.
REM ===========================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo(
echo [1/6] Database backup ^(optional for this developer build^)...
if not exist "ho_setup\assets\NEXORA_PLATFORM.bak" (
  echo   NOTE: ho_setup\assets\NEXORA_PLATFORM.bak not present.
  echo         App-only build - the installer will NOT restore a database.
)

echo(
echo [2/6] Building the frontend...
if not exist "frontend\dist\index.html" (
  pushd frontend
  call npm install || ( popd & goto :fail )
  call npm run build || ( popd & goto :fail )
  popd
) else (
  echo   frontend\dist already present - skipping ^(delete it to force a rebuild^).
)

echo(
echo [3/6] Installing Python build dependencies...
python -m pip install -r ho_setup\requirements.txt || goto :fail
python -m pip install -r backend\requirements.txt || goto :fail

echo(
echo [4/6] Building executables with PyInstaller...
python -m PyInstaller --noconfirm --clean ho_setup\HO_Backend.spec   || goto :fail
python -m PyInstaller --noconfirm --clean ho_setup\HO_Deploy.spec    || goto :fail
python -m PyInstaller --noconfirm --clean ho_setup\HO_Uninstall.spec || goto :fail

echo(
echo   Verifying the backend bundle is self-contained...
"dist\HO_Backend\HO_Backend.exe" selftest || (
  echo   ERROR: HO_Backend selftest failed - a backend module was not bundled.
  goto :fail
)

echo(
echo [5/6] Locating Inno Setup compiler (ISCC)...
set "ISCC="
where ISCC >nul 2>nul && set "ISCC=ISCC"
if not defined ISCC if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  echo   ERROR: Inno Setup 6 ^(ISCC.exe^) not found. Install from https://jrsoftware.org/
  goto :fail
)

echo(
echo [6/6] Compiling the installer...
if not exist "release" mkdir "release"
"%ISCC%" "installer\HO_Setup.iss" || goto :fail

echo(
echo ===========================================================================
echo  BUILD SUCCEEDED
echo  Output: release\HO_Setup.exe
echo ===========================================================================
exit /b 0

:fail
echo(
echo ===========================================================================
echo  BUILD FAILED
echo ===========================================================================
exit /b 1
