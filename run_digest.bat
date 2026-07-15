@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist logs mkdir logs
call "%~dp0env.bat"
REM O1: date-stamped log (via PowerShell; %date% parsing is locale-fragile)
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set LOGDATE=%%i
set LOGFILE=logs\digest_%LOGDATE%.log
echo [%date% %time%] Starting morning digest >> %LOGFILE%
"%~dp0.venv\Scripts\python.exe" digest.py >> %LOGFILE% 2>&1
if %ERRORLEVEL% NEQ 0 "%~dp0.venv\Scripts\python.exe" "%~dp0run_alert.py" digest >> %LOGFILE% 2>&1
echo [%date% %time%] Finished >> %LOGFILE%
REM O1: prune logs older than ~30 days (forfiles errors when nothing matches - ignored)
forfiles /p logs /m *.log /d -30 /c "cmd /c del @path" 2>nul
REM Exit 0 on clean runs: forfiles above exits 1 when nothing is >30d old (alerting is keyed off python's exit inline)
exit /b 0
