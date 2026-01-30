from daily_extractor import run_extraction
from bot.utils.logger import logger

if __name__ == '__main__':
    logger.info("⚡ [TRIGGER] Manual run initiated.")
    run_extraction()
    logger.info("✅ Manual run completed.")
