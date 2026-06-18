@echo off
cd /d "%~dp0"

if not exist ".env" (
    echo [ERROR] Missing .env. Run this first:
    echo copy .env.example .env
    echo notepad .env
    pause
    exit /b 1
)

start "StudyHack Backend" cmd /k ""%~dp0run_backend.bat""
start "StudyHack Frontend" cmd /k ""%~dp0run_frontend.bat""

echo Open http://127.0.0.1:3000 after both terminals finish installing.
pause
