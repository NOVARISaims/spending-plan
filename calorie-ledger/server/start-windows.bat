@echo off
rem Start Calorie Ledger on this PC (loopback only; expose via `tailscale serve`).
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run install-windows.bat first.
  exit /b 1
)
.venv\Scripts\python run.py
