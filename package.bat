@echo off
REM ===========================================================================
REM  UniNex HO - package the built installer for distribution.
REM  Produces release\UniNex_HO_<version>.zip and SHA256SUMS.txt next to
REM  release\HO_Setup.exe. Run build.bat first.
REM ===========================================================================
setlocal
cd /d "%~dp0"

if not exist "release\HO_Setup.exe" (
  echo ERROR: release\HO_Setup.exe not found. Run build.bat first.
  exit /b 1
)

echo Generating SHA-256 checksum...
powershell -NoProfile -Command ^
  "(Get-FileHash 'release\HO_Setup.exe' -Algorithm SHA256).Hash + '  HO_Setup.exe' | Set-Content -Encoding ascii 'release\SHA256SUMS.txt'" || exit /b 1

echo Creating distribution zip...
powershell -NoProfile -Command ^
  "Compress-Archive -Path 'release\HO_Setup.exe','release\SHA256SUMS.txt' -DestinationPath 'release\UniNex_HO_Installer.zip' -Force" || exit /b 1

echo(
echo Done:
echo   release\HO_Setup.exe
echo   release\SHA256SUMS.txt
echo   release\UniNex_HO_Installer.zip
exit /b 0
