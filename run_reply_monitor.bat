@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist logs mkdir logs
call "%~dp0env.bat"
echo [%date% %time%] Starting reply monitor >> logs\reply_monitor.log
"%~dp0.venv\Scripts\python.exe" reply_monitor.py >> logs\reply_monitor.log 2>&1
echo [%date% %time%] Reply monitor stopped >> logs\reply_monitor.log
