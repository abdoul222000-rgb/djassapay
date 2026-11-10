@echo off
title CallCatch AI - SaaS US
echo ===================================================
echo   Lancement de CallCatch AI (Dashboard Artisan US)
echo ===================================================
echo.
if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe run_callcatch.py
) else (
    python run_callcatch.py
)
pause
