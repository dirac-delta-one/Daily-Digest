@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist logs mkdir logs
call "%~dp0env.bat"
echo [%date% %time%] Starting morning digest >> logs\digest.log
"%~dp0.venv\Scripts\python.exe" digest.py >> logs\digest.log 2>&1
echo [%date% %time%] Finished >> logs\digest.log
