@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist logs mkdir logs
call "%~dp0env.bat"
echo [%date% %time%] Starting midday check >> logs\midday.log
"%~dp0.venv\Scripts\python.exe" midday.py >> logs\midday.log 2>&1
if %ERRORLEVEL% NEQ 0 "%~dp0.venv\Scripts\python.exe" "%~dp0run_alert.py" midday >> logs\midday.log 2>&1
echo [%date% %time%] Finished >> logs\midday.log
