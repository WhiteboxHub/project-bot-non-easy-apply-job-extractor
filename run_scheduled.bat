@echo off
cd /d "%~dp0"

:: Create a log file to see what happened
echo [%date% %time%] Script started > scheduler_log.txt

:: Activate virtual environment if it exists
if exist venv\Scripts\activate.bat (
    echo Activating venv... >> scheduler_log.txt
    call venv\Scripts\activate.bat
) else (
    echo No venv found, using system python >> scheduler_log.txt
)

:: Run the script and capture ALL output to the log
echo Running python script... >> scheduler_log.txt
python run_now.py >> scheduler_log.txt 2>&1

echo [%date% %time%] Script finished with code %errorlevel% >> scheduler_log.txt
