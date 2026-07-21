@echo off
rem One-time setup: create a virtualenv and install dependencies.
cd /d "%~dp0"
py -3 -m venv .venv || goto :error
.venv\Scripts\python -m pip install --upgrade pip || goto :error
.venv\Scripts\pip install -r requirements.txt || goto :error
echo.
echo Done. Start the server with start-windows.bat
goto :eof
:error
echo Install failed. Is Python 3.11+ installed from python.org?
exit /b 1
