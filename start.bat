@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Python was not found.
  echo  Install Python 3.10+ from https://www.python.org/downloads/
  echo  and enable "Add Python to PATH" during setup.
  echo.
  pause
  exit /b 1
)

python server.py --open
pause
