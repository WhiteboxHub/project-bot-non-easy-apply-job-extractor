@echo off
cd /d "%~dp0"

:: Set UTF-8 encoding for Python
set PYTHONIOENCODING=utf-8

:: Python will automatically log to scheduler_log.txt with a 3-day rotation
echo [%date% %time%] Script started...

:: Run the script using the full Python path to avoid "Choose an app" issue
:: Added -u flag to ensure live output to the CMD screen (no buffering)
C:\Python313\python.exe -u website_scheduler.py

echo [%date% %time%] Script finished with code %errorlevel%

:: Keep window open for 10 seconds to see output
timeout /t 10
