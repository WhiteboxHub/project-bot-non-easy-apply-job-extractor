@echo off
cd /d "%~dp0"

:: Set UTF-8 encoding for Python
set PYTHONIOENCODING=utf-8

:: Python will automatically log to scheduler_log.txt with a 3-day rotation
echo [%date% %time%] Script started...

:: Try to use the virtual environment Python if it exists, otherwise use global python
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe -u website_scheduler.py
) else (
    python.exe -u website_scheduler.py
)
echo [%date% %time%] Script finished with code %errorlevel%

:: Keep window open for 10 seconds to see output
timeout /t 10
