@echo off
echo Creating scheduled tasks...

REM Morning digest — 8:00 AM ET, weekdays
schtasks /Create /TN "DailyDigest\MorningDigest" /TR "%~dp0run_digest.bat" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 08:00 /F /RL HIGHEST
if %errorlevel%==0 (echo   Morning digest: OK) else (echo   Morning digest: FAILED)

REM Midday alert — 1:00 PM ET, weekdays
schtasks /Create /TN "DailyDigest\MiddayAlert" /TR "%~dp0run_midday.bat" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 13:00 /F /RL HIGHEST
if %errorlevel%==0 (echo   Midday alert: OK) else (echo   Midday alert: FAILED)

REM Reply monitor — runs at startup, stays running continuously
schtasks /Create /TN "DailyDigest\ReplyMonitor" /TR "%~dp0run_reply_monitor.bat" /SC ONSTART /F /RL HIGHEST
if %errorlevel%==0 (echo   Reply monitor: OK) else (echo   Reply monitor: FAILED)

echo.
echo Done. Verify with: schtasks /Query /TN "DailyDigest\*"
echo.
echo To start the reply monitor now: schtasks /Run /TN "DailyDigest\ReplyMonitor"
pause
