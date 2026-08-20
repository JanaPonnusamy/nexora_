@echo off
setlocal
cd /d "%~dp0"
title Nexora Development Control
node "%~dp0scripts\dev-launcher.mjs"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%
