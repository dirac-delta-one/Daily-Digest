@echo off
REM O4 off-box backup (2026-07-20). Copies the system's irreplaceable STATE into a
REM subfolder of the user's corporate OneDrive, which syncs it off-box to Acorn's
REM cloud (the server is kept logged-in-and-locked, so OneDrive.exe is running).
REM
REM STATE ONLY - no secrets. token.json / credentials.json / substack_cookie.txt /
REM thirteen_d_session.json / env.bat are NEVER listed here, so they never leave the
REM box (.gitignore stops git, not a file copy - this allow-list is what stops OneDrive).
REM robocopy /E = add + update, NEVER delete from the backup, so a corrupted or
REM emptied source can't propagate and wipe the history.
cd /d "%~dp0"
if not exist logs mkdir logs
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set LOGDATE=%%i
set LOGFILE=logs\backup_%LOGDATE%.log
echo [%date% %time%] Starting O4 backup >> %LOGFILE%

REM Destination = a subfolder of corporate OneDrive (per-machine env var, set by
REM the OneDrive client). Fall back to the personal-OneDrive var; abort loudly if
REM neither resolves (e.g. no one logged in / OneDrive not running) - a silent
REM local-only "backup" that never uploads is worse than a visible failure.
set "ONEDRIVE_ROOT=%OneDriveCommercial%"
if not defined ONEDRIVE_ROOT set "ONEDRIVE_ROOT=%OneDrive%"
if not exist "%ONEDRIVE_ROOT%\" (
    echo ERROR: OneDrive folder not found ^(is the user logged in / OneDrive running?^) - backup skipped. >> %LOGFILE%
    "%~dp0.venv\Scripts\python.exe" "%~dp0run_alert.py" backup >> %LOGFILE% 2>&1
    echo [%date% %time%] Backup ABORTED >> %LOGFILE%
    exit /b 0
)
set "DEST=%ONEDRIVE_ROOT%\DailyDigest-Backup"
echo   Destination: %DEST% >> %LOGFILE%

set FAIL=0
REM State trees (append-only; /E copies subdirs, never deletes from the backup).
robocopy "archive" "%DEST%\archive" /E /R:2 /W:5 /NP /NDL /NFL >> %LOGFILE% 2>&1
if %ERRORLEVEL% GEQ 8 set FAIL=1
robocopy "digests" "%DEST%\digests" /E /R:2 /W:5 /NP /NDL /NFL >> %LOGFILE% 2>&1
if %ERRORLEVEL% GEQ 8 set FAIL=1
robocopy "logs"    "%DEST%\logs"    /E /R:2 /W:5 /NP /NDL /NFL >> %LOGFILE% 2>&1
if %ERRORLEVEL% GEQ 8 set FAIL=1
REM Top-level state files ONLY - explicit list, so no secret ever gets copied.
robocopy "." "%DEST%" memory.json substack_memory.json wiltw_cache.json ishares_oas_cache.json pacer_seen.json source_counts.json alerts_config.json watchlist.json repetition_scores.json /R:2 /W:5 /NP /NDL /NFL >> %LOGFILE% 2>&1
if %ERRORLEVEL% GEQ 8 set FAIL=1

echo [%date% %time%] robocopy done ^(FAIL=%FAIL%; robocopy exit ^>=8 = real failure^) >> %LOGFILE%
if %FAIL%==1 "%~dp0.venv\Scripts\python.exe" "%~dp0run_alert.py" backup >> %LOGFILE% 2>&1

echo [%date% %time%] Backup finished >> %LOGFILE%
REM prune old backup logs (30-day, like the other wrappers)
forfiles /p logs /m *.log /d -30 /c "cmd /c del @path" 2>nul
exit /b 0
