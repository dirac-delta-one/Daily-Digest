@echo off
cd /d C:\Users\jared\Daily-Digest
call env.bat
echo [%date% %time%] Starting reply monitor >> logs\reply_monitor.log
C:\Users\jared\AppData\Local\Programs\Python\Python312\python.exe reply_monitor.py >> logs\reply_monitor.log 2>&1
echo [%date% %time%] Reply monitor stopped >> logs\reply_monitor.log
