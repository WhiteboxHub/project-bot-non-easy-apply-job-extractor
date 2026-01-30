import schedule
import time
import logging
from daily_extractor import run_extraction
from bot.utils.logger import logger

def start_scheduler():
    # Set the schedule time
    # This will trigger the job every day at the specified time
    schedule.every().day.at("08:37").do(run_extraction)
    
    logger.info("📅 [TRIGGER] Scheduler initialized.")
    logger.info("🕙 Next run scheduled for: 08:37 AM Daily.")
    logger.info("⚠️ Note: If you start this script AFTER the time, it will wait 24 hours.")
    logger.info("🚀 System is now 100% automatic. Keep this window open.")

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
