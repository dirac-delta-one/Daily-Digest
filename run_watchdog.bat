@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist logs mkdir logs
call "%~dp0env.bat"
REM O1: date-stamped log (via PowerShell; %date% parsing is locale-fragile)
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set LOGDATE=%%i
set LOGFILE=logs\watchdog_%LOGDATE%.log
echo [%date% %time%] Watchdog check >> %LOGFILE%
REM O2: alert if today's digest never completed (hung / never started)
"%~dp0.venv\Scripts\python.exe" "%~dp0run_alert.py" digest --check-completed >> %LOGFILE% 2>&1
REM O1: prune logs older than ~30 days (forfiles errors when nothing matches - ignored)
forfiles /p logs /m *.log /d -30 /c "cmd /c del @path" 2>nul
