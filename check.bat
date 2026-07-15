@echo off
REM Stage gate (CLEANUP_SPEC 4.4): ruff + full pytest, the checks every
REM commit must pass (HANDOFF workflow). Exit nonzero on any failure.
cd /d "%~dp0"
set PYTHONUTF8=1
"%~dp0.venv\Scripts\python.exe" -m ruff check .
if %ERRORLEVEL% NEQ 0 exit /b 1
"%~dp0.venv\Scripts\python.exe" -m pytest -q
if %ERRORLEVEL% NEQ 0 exit /b 1
echo All gates green.
exit /b 0
