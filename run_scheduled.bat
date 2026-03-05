@echo off
cd /d "%~dp0"

:: Set UTF-8 encoding for Python
set PYTHONIOENCODING=utf-8

:: Create a log file to see what happened
echo [%date% %time%] Script started > scheduler_log.txt

:: Run the script using the full Python path to avoid "Choose an app" issue
:: Replace C:\Python313\python.exe with your actual Python path if different
echo Running python script... >> scheduler_log.txt
C:\Python313\python.exe website_scheduler.py >> scheduler_log.txt 2>&1

echo [%date% %time%] Script finished with code %errorlevel% >> scheduler_log.txt

:: Keep window open for 10 seconds to see output
timeout /t 10
