@echo off
rem Usta kurulumu (Fabric + ayri profil + modlar + kopru + MCP kaydi)
chcp 65001 >nul
cd /d "%~dp0"
rem Python 3.12+ bul: once 3.13, sonra PATH'teki python, sonra py baslaticisi
set "PY="
py -3.13 --version >nul 2>&1 && set "PY=py -3.13"
if not defined PY python --version >nul 2>&1 && set "PY=python"
if not defined PY py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
  echo [EKSIK] Python bulunamadi. Python 3.13 kur: https://www.python.org/downloads/
  echo         Kurarken "Add python.exe to PATH" kutusunu isaretle, sonra KUR.bat'i tekrar calistir.
  echo.
  pause
  exit /b 1
)
%PY% scripts\kur.py %*
echo.
pause
