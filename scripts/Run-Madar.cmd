@echo off
setlocal
set /p MADAR_VERSION=<"%~dp0current-version.txt"
if "%MADAR_VERSION%"=="" exit /b 1
start "" "%~dp0versions\%MADAR_VERSION%\Madar-Desk.exe"
endlocal
