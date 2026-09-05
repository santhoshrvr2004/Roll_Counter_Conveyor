@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo  RealSense Conveyor Counter - Setup
echo ============================================================

where python >nul 2>nul || (
  echo ERROR: Python was not found in PATH.
  pause
  exit /b 1
)
where npm >nul 2>nul || (
  echo ERROR: Node.js/npm was not found in PATH.
  pause
  exit /b 1
)

echo.
echo [1/2] Backend Python environment...
cd backend
if not exist .venv (
  python -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip || goto :error
python -m pip install -r requirements-realsense.txt || goto :error
cd ..

echo.
echo [2/2] React frontend dependencies...
cd frontend
call npm install || goto :error
cd ..

echo.
echo Setup complete.
echo Run run_all.bat to start the backend and frontend.
pause
exit /b 0

:error
echo.
echo SETUP FAILED. Check the error above.
pause
exit /b 1
