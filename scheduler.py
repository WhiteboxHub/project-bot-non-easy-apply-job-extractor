import schedule
import time
import logging
from daily_extractor import run_extraction
from bot.utils.logger import logger
import os
from dotenv import load_dotenv

load_dotenv()

def start_scheduler():
    # Set the schedule time from .env (default to 09:00)
    schedule_time = os.getenv("SCHEDULER_TIME", "09:00")
    
    # This will trigger the job every day at the specified time
    schedule.every().day.at(schedule_time).do(run_extraction)
    
    logger.info("[TRIGGER] Scheduler initialized.")
    logger.info(f"Next run scheduled for: {schedule_time} Daily.")
    logger.info("Note: If you start this script AFTER the time, it will wait 24 hours.")
    logger.info("System is now 100% automatic. Keep this window open.")

    # Optional: Run immediately on startup if you want to see results now
    # run_extraction()

    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == '__main__':
    try:
        start_scheduler()
    except KeyboardInterrupt:
        logger.info("🛑 Scheduler stopped by user.")
    except Exception as e:
        logger.error(f"❌ Scheduler crashed: {e}")
