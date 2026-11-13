@echo off
title SpeedTube - Ultra-Fast YouTube Downloader
cd /d "%~dp0"

echo ========================================================
echo   SpeedTube - Ultra-Fast YouTube Downloader
echo ========================================================

:: Check if virtual environment exists
if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo Failed to create virtual environment. Ensure Python is installed.
        pause
        exit /b 1
    )
    echo Installing dependencies...
    venv\Scripts\pip install -r requirements.txt
)

echo Starting SpeedTube Server...
venv\Scripts\python.exe run.py

pause
