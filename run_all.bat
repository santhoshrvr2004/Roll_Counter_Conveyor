@echo off
setlocal
cd /d "%~dp0"
start "RealSense Counter Backend" cmd /k call "%~dp0run_backend.bat"
timeout /t 2 /nobreak >nul
start "RealSense Counter Frontend" cmd /k call "%~dp0run_frontend.bat"
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:3000
