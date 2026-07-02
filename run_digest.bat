@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist logs mkdir logs
call "%~dp0env.bat"
echo [%date% %time%] Starting morning digest >> logs\digest.log
"%~dp0.venv\Scripts\python.exe" digest.py >> logs\digest.log 2>&1
if %ERRORLEVEL% NEQ 0 "%~dp0.venv\Scripts\python.exe" "%~dp0run_alert.py" digest >> logs\digest.log 2>&1
echo [%date% %time%] Finished >> logs\digest.log
