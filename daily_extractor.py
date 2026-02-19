import logging
import os
import time
import re
import yaml
from bot.utils.logger import logger
from bot.core.browser import Browser
from bot.core.session import Session
from bot.discovery.extractor import JobExtractor
from bot.persistence.api_store import APIStore
from dotenv import load_dotenv

# Import new utilities
from bot.utils.startup_validation import run_startup_validation
from bot.utils.metrics import metrics
from bot.utils.startup_validation import run_startup_validation

# Timespan mapping for user-friendly configuration
TIMESPAN_MAP = {
    "24h": "r86400",
    "24 hours": "r86400",
    "7d": "r604800",
    "7 days": "r604800",
    "1d": "r86400",
    "1 week": "r604800"
}

load_dotenv()

# Run startup validation
run_startup_validation(strict=True)

def load_candidates_from_yaml():
    """
    Load candidates from 'candidate.yaml'.
    """
    yaml_path = os.path.join(os.getcwd(), 'candidate.yaml')
    if not os.path.exists(yaml_path):
        logger.error(f"candidate.yaml not found at {yaml_path}")
        return [], {}

    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
            
        candidates = data.get('candidates', [])
        settings = data.get('settings', {})
        
        # Filter: Only run if run_extract_linkedin_jobs is True (default to False if missing, safety first)
        active_candidates = []
        for c in candidates:
            if c.get('run_extract_linkedin_jobs', False):
                active_candidates.append(c)
        
        logger.info(f"Loaded {len(active_candidates)} active candidates from YAML.")
        return active_candidates, settings
        
    except Exception as e:
        logger.error(f"Error loading candidate.yaml: {e}")
        return [], {}

def run_extraction():
    # Load candidates and settings from YAML
    candidates, yaml_settings = load_candidates_from_yaml()
    
    # Global Settings: YAML > ENV > Default
    env_dist = yaml_settings.get('distance_miles') or int(os.getenv("DISTANCE_MILES", 50))
    env_location = yaml_settings.get('default_location') or "United States"
    raw_timespan = yaml_settings.get('search_timespan') or "24h"
    env_timespan = TIMESPAN_MAP.get(str(raw_timespan).lower(), raw_timespan)
    
    # New settings from YAML
    env_dry_run = yaml_settings.get('dry_run')
    if env_dry_run is None:
        env_dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    
    env_default_keywords = yaml_settings.get('default_keywords') or os.getenv("DEFAULT_KEYWORDS", "").split(",")
    if isinstance(env_default_keywords, str):
        env_default_keywords = [k.strip() for k in env_default_keywords.split(",") if k.strip()]

    # Extraction limits and timing
    jobs_per_zip = yaml_settings.get('jobs_per_location_limit', 999)
    total_run_limit = yaml_settings.get('total_run_limit', 9999)
    dist_buckets = yaml_settings.get('distance_buckets', [5, 10, 25, 50, 100])
    wait_between_locs = yaml_settings.get('wait_time_between_locations', 5)
    
    logger.info(f"Using search settings: Distance={env_dist}mi, Location={env_location}, Timespan={raw_timespan} ({env_timespan}), DryRun={env_dry_run}")
    
    # Initialize stores
    api_store = APIStore()
    
    if not candidates:
        logger.error("No candidates found to process.")
        return

    browser = None
    try:
        for cand in candidates:
            try:
                candidate_id = cand.get('candidate_id', 'unknown')
                username = cand.get('linkedin_username')
                password = cand.get('linkedin_password')
                keywords = cand.get('keywords') or env_default_keywords
                locations = cand.get('locations', [])
                
                # Start metrics tracking for this candidate
                run_metrics = metrics.start_run(candidate_id, keywords, locations)
                
                # Check if login is possible
                can_login = username and password and password != "*****"
                
                logger.info(f"--- Processing Candidate: {candidate_id} ({username if username else 'No Login'}) ---")
                logger.info(f"Keywords: {keywords}")
                logger.info(f"Locations: {locations}")

                if not locations:
                    if env_location:
                        logger.info(f"Candidate {candidate_id} has no locations. Using default: {env_location}")
                        locations = [env_location]
                    else:
                        logger.warning(f"Candidate {candidate_id} has no locations and no default set. Skipping.")
                        continue

                # File setup
                exports_dir = os.path.abspath(os.path.join(os.getcwd(), "data", "exports"))
                os.makedirs(exports_dir, exist_ok=True)
                csv_filename = os.path.join(exports_dir, "extractor_job_links.csv")
                
                # Distance Logic
                total_candidate_extracted = 0
                
                # Use individual distance or global distance
                max_dist = cand.get('distance_miles') or env_dist
                dist_list = [d for d in dist_buckets if d <= max_dist]
                if not dist_list: dist_list = [max_dist]

                # Profile setup
                profile_path = os.path.join(os.getcwd(), "data", "profiles", str(candidate_id))
                
                browser = None
                remaining_locations = list(locations)
                
                while remaining_locations:
                    current_loc = str(remaining_locations[0]).strip()
                    
                    try:
                        if browser is None:
                            logger.info(f"Initializing browser for {candidate_id}...")
                            browser = Browser(profile_path=profile_path)
                            if can_login:
                                session = Session(browser.driver)
                                session.login(username, password)
                            else:
                                logger.info("Running without login (using profile or public search)...")

                        location_extraction_total = 0
                        for current_dist in dist_list:
                            if location_extraction_total >= jobs_per_zip:
                                break
                                
                            logger.info(f"  --- Distance Bucket: {current_dist} miles (Candidate Total: {total_candidate_extracted}) ---")
                            
                            extractor = JobExtractor(
                                browser, 
                                candidate_id=candidate_id, 
                                csv_path=csv_filename, 
                                distance_miles=current_dist,
                                api_store=api_store,
                                search_timespan=env_timespan
                            )
                            
                            zip_match = re.search(r'\b\d{5,6}\b', current_loc)
                            zipcode = zip_match.group(0) if zip_match else current_loc

                            logger.info(f"Starting extraction for: {current_loc} at {current_dist}mi")
                            newly_found = extractor.start_extract(keywords, locations=[current_loc], zipcode=zipcode, limit=total_run_limit)
                            location_extraction_total += newly_found
                            total_candidate_extracted += newly_found
                        
                        if remaining_locations:
                             remaining_locations.pop(0)
                        time.sleep(wait_between_locs)

                    except Exception as e:
                        err_msg = str(e).lower()
                        logger.error(f"Error processing location {current_loc}: {e}")
                        
                        if any(x in err_msg for x in ['invalid session', 'disconnected', 'no such window', 'browser_crash', 'retry_failed']):
                            if browser:
                                try: browser.driver.quit()
                                except: pass
                            browser = None
                        else:
                            if remaining_locations:
                                remaining_locations.pop(0)
                            if browser:
                                try: browser.driver.quit()
                                except: pass
                            browser = None


                if browser:
                    try: browser.driver.quit()
                    except: pass
                
                # Finalize metrics for this candidate
                metrics.end_run()
                
            except Exception as cand_e:
                logger.error(f"❌ Critical error processing candidate {cand.get('candidate_id')}: {cand_e}")
                # Finalize metrics even on error
                metrics.end_run()
                continue

    except KeyboardInterrupt:
        logger.warning("⚠️ Run interrupted by user (Ctrl+C). Flushing all buffered jobs before exit...")
    finally:
        # ✅ ONE bulk insert for the entire run — all jobs collected across all pages/distances
        buffered = len(api_store.batch_buffer)
        if buffered > 0:
            logger.info(f"📡 Final bulk insert: {buffered} jobs collected during this run.")
            api_store.flush_batches()
        else:
            logger.info("No new jobs collected — nothing to flush.")
        api_store.close()
        logger.info("✅ Daily Extraction completed.")

if __name__ == '__main__':
    run_extraction()
