@echo off
cd /d C:\Users\jared\Daily-Digest
call env.bat
echo [%date% %time%] Starting morning digest >> logs\digest.log
C:\Users\jared\AppData\Local\Programs\Python\Python312\python.exe digest.py >> logs\digest.log 2>&1
echo [%date% %time%] Finished >> logs\digest.log
