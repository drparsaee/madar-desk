@echo off
setlocal
echo Madar Host: one-time secure server installation.
echo Use RIGHT CLICK - Run as administrator on this file.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup-MadarHost-LAN.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" echo HOST SETUP FAILED. Existing Madar app profiles are untouched.
if "%RESULT%"=="0" echo Host setup command finished.
pause
exit /b %RESULT%
