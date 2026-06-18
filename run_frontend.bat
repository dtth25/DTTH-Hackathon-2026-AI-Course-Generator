@echo off
cd /d "%~dp0\frontend"

echo [StudyHack Frontend] Current folder:
cd

echo [StudyHack Frontend] Checking Node.js...
node --version
if errorlevel 1 (
    echo [ERROR] Node.js was not found. Install Node.js LTS first.
    pause
    exit /b 1
)

echo [StudyHack Frontend] Checking npm...
npm --version
if errorlevel 1 (
    echo [ERROR] npm was not found. Reinstall Node.js LTS.
    pause
    exit /b 1
)

echo [StudyHack Frontend] Using public npm registry...
npm config set registry https://registry.npmjs.org/

if not exist ".env.local" (
    echo [StudyHack Frontend] Creating frontend .env.local...
    copy .env.local.example .env.local
)

echo [StudyHack Frontend] Installing Next.js/MUI dependencies...
npm install

echo [StudyHack Frontend] Running Next.js on http://127.0.0.1:3000
npm run dev

pause
