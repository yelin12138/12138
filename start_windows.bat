@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title MotorLab v0.4 - SVPWM and 3D Motor
echo MotorLab v0.4.0 - starting THIS extracted folder
echo %CD%
echo.
if exist ".venv\Scripts\python.exe" goto dependencies
where py >nul 2>nul
if errorlevel 1 goto use_python
py -3 -m venv .venv
if errorlevel 1 goto failed
goto dependencies
:use_python
python -m venv .venv
if errorlevel 1 goto failed
:dependencies
".venv\Scripts\python.exe" -c "import numpy, matplotlib" >nul 2>nul
if not errorlevel 1 goto launch
echo Installing dependencies on first launch. Please wait...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
:launch
".venv\Scripts\python.exe" run_workbench.py --open
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo Startup failed. Please keep the error above.
echo Python 3.10 or newer is required. First setup needs internet access.
pause
exit /b 1
