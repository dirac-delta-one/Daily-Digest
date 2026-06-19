@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist logs mkdir logs
call env.bat
echo [%date% %time%] Starting midday check >> logs\midday.log
"%~dp0.venv\Scripts\python.exe" midday.py >> logs\midday.log 2>&1
echo [%date% %time%] Finished >> logs\midday.log
