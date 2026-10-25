@echo off
rem Usta'yi kaldirir (yalniz eklenenler; dunyalar yedege tasinir)
chcp 65001 >nul
cd /d "%~dp0"
python scripts\kaldir.py %*
echo.
pause
