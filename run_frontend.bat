@echo off
setlocal
cd /d "%~dp0frontend"
if not exist node_modules (
  echo Frontend node_modules not found.
  echo Run ..\setup_windows.bat first.
  pause
  exit /b 1
)
call npm start
