@echo off
cd /d "%~dp0"

echo [StudyHack Backend] Current folder:
cd

echo [StudyHack Backend] Checking Python...
python --version
if errorlevel 1 (
    echo [ERROR] Python was not found. Install Python and tick "Add python.exe to PATH".
    pause
    exit /b 1
)

if not exist ".env" (
    echo [ERROR] Missing .env. Run: copy .env.example .env
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [StudyHack Backend] Creating virtual environment...
    python -m venv .venv
)

call ".venv\Scripts\activate.bat"

echo [StudyHack Backend] Installing Python dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo [StudyHack Backend] Running FastAPI on http://127.0.0.1:8000
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000

pause
