@echo off
setlocal
title HAND FX STUDIO
cd /d "%~dp0"

rem The virtual environment lives outside OneDrive so syncing never locks files.
set "VENV=%LOCALAPPDATA%\HandFXStudio\venv"
set "PY=%VENV%\Scripts\python.exe"

if exist "%PY%" goto check_deps

echo.
echo  ==============================================
echo    HAND FX STUDIO - first time setup
echo  ==============================================
echo.
where py >nul 2>nul
if errorlevel 1 (
    echo  Python was not found.
    echo  Please install Python 3.12 from https://www.python.org/downloads/
    echo  and tick "Add python.exe to PATH" during installation.
    pause
    exit /b 1
)
py -3.12 --version >nul 2>nul
if errorlevel 1 (
    echo  Python 3.12 is required but was not found.
    echo  Install it from https://www.python.org/downloads/release/python-3125/
    pause
    exit /b 1
)
echo  Creating virtual environment...
py -3.12 -m venv "%VENV%"
if errorlevel 1 (
    echo  Could not create the virtual environment.
    pause
    exit /b 1
)

:check_deps
"%PY%" -c "import mediapipe, moderngl, PySide6, cv2, imageio_ffmpeg" >nul 2>nul
if errorlevel 1 (
    echo  Installing dependencies - this can take a few minutes the first time...
    "%PY%" -m pip install --upgrade pip
    "%PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo  Dependency installation failed. Check your internet connection and try again.
        pause
        exit /b 1
    )
)

echo  Starting HAND FX STUDIO...
"%PY%" main.py %*
if errorlevel 1 (
    echo.
    echo  HAND FX STUDIO exited with an error. See the message above,
    echo  or the log file: hand_fx_studio.log
    pause
)
endlocal
