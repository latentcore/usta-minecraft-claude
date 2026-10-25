@echo off
rem Saglik kontrolu
chcp 65001 >nul
cd /d "%~dp0"
python scripts\durum.py
echo.
pause
