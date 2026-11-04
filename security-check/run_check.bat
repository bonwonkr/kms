@echo off
chcp 65001 >nul
echo Node.js / Java / Synology security check (read-only)
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check.ps1"
echo.
pause
