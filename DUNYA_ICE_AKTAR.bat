@echo off
rem Bir dunyanin KOPYASINI Usta profiline alir (aslina dokunmaz)
chcp 65001 >nul
cd /d "%~dp0"
python scripts\dunya_ice_aktar.py %*
echo.
pause
