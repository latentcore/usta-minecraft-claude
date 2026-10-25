@echo off
rem Tarayici panelini acar (yalniz bu bilgisayar)
chcp 65001 >nul
cd /d "%~dp0"
set "UPY=%USERPROFILE%\UstaOyun\bridge\venv\Scripts\python.exe"
if exist "%UPY%" (
  pushd "%USERPROFILE%\UstaOyun\bridge"
  "%UPY%" -m usta.panel --open
  popd
) else (
  pushd bridge
  ".venv\Scripts\python.exe" -m usta.panel --open
  popd
)
echo.
pause
