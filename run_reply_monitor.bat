@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist logs mkdir logs
call "%~dp0env.bat"
REM O1: date-stamped log (named by START date; the daemon's log rotates on restart)
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set LOGDATE=%%i
set LOGFILE=logs\reply_monitor_%LOGDATE%.log
echo [%date% %time%] Starting reply monitor >> %LOGFILE%
REM -u (unbuffered) so the daemon's log streams in real time. Python block-buffers
REM stdout when redirected to a file and only flushes on exit; the reply monitor
REM NEVER exits, so without -u its log stays empty (just this wrapper line) and a
REM future "why isn't the bot answering?" debug has nothing to read. The other three
REM wrappers run to completion (flush on exit), so they don't need this. (2026-07-20)
"%~dp0.venv\Scripts\python.exe" -u reply_monitor.py >> %LOGFILE% 2>&1
REM The reply monitor is a daemon - ANY exit is abnormal, so alert on every exit.
"%~dp0.venv\Scripts\python.exe" "%~dp0run_alert.py" reply_monitor >> %LOGFILE% 2>&1
echo [%date% %time%] Reply monitor stopped >> %LOGFILE%
REM O1: prune logs older than ~30 days (forfiles errors when nothing matches - ignored)
forfiles /p logs /m *.log /d -30 /c "cmd /c del @path" 2>nul
REM Exit 0 on clean runs: forfiles above exits 1 when nothing is >30d old (alerting is keyed off python's exit inline)
exit /b 0
