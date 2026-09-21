@echo off
title Valkeria AI Studio (Python Core)
echo ========================================================
echo   Launching Valkeria AI Studio (Python Engine)...
echo ========================================================
cd /d "%~dp0"

:: Launch standalone App Window (Responsive Antigravity Studio Mode)
start "" msedge.exe --app="http://127.0.0.1:3000" --window-size=1080,780

:: Start Python FastAPI Engine
py server.py
pause
