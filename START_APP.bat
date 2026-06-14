@echo off
cd /d "%~dp0"
title Dar al Sultan CFO Application
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 server.py
  goto end
)
where python >nul 2>nul
if %errorlevel% equ 0 (
  python server.py
  goto end
)
echo.
echo Python 3 is not installed or is not available in PATH.
echo Install Python 3 and select the option "Add Python to PATH".
echo.
:end
pause
