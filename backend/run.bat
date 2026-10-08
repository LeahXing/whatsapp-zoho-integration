@echo off
setlocal
title WhatsApp Scraper Backend
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON=py -3"
) else (
    set "PYTHON=python"
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    %PYTHON% -m venv .venv
    if errorlevel 1 goto :error
)

echo Installing backend dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo Installing Playwright Chromium...
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto :error

echo Starting the backend API at http://127.0.0.1:8009
".venv\Scripts\python.exe" server.py
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo Backend startup failed. Review the error above, then retry.
pause
exit /b 1
