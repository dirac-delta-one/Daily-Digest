@echo off
cd /d C:\Users\jared\Daily-Digest
call env.bat
echo [%date% %time%] Starting midday check >> logs\midday.log
C:\Users\jared\AppData\Local\Programs\Python\Python312\python.exe midday.py >> logs\midday.log 2>&1
echo [%date% %time%] Finished >> logs\midday.log
