@echo off
setlocal
set "PYTHONUTF8=1"
title Synopsis
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 goto run_py
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 goto run_python
echo Synopsis needs Python 3.11 or newer.
echo Install Python from https://www.python.org/downloads/ and try again.
echo No npm, pip packages or Docker are required.
set "synopsis_exit=2"
goto finish

:run_py
py -3 "%~dp0start.py" %*
set "synopsis_exit=%errorlevel%"
goto finish

:run_python
python "%~dp0start.py" %*
set "synopsis_exit=%errorlevel%"

:finish
if "%synopsis_exit%"=="0" exit /b 0
if not "%~1"=="" exit /b %synopsis_exit%
echo.
pause
exit /b %synopsis_exit%
