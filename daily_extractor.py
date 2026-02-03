import logging
import os
import time
import re
from bot.utils.logger import logger
from bot.core.browser import Browser
from bot.core.session import Session
from bot.discovery.extractor import JobExtractor
from bot.persistence.api_store import APIStore
from bot.api.website_client import fetch_candidates_from_api
from dotenv import load_dotenv

load_dotenv()

def get_env_keywords():
    kw_str = os.getenv("DEFAULT_KEYWORDS", "AI/ML Engineer, MLOps, Gen AI")
    return [k.strip() for k in kw_str.split(',') if k.strip()]

def load_candidates_from_db():
    """
    Primary Source: Website API / Local DB Cache.
    Settings: Loaded from .env.
    """
    dynamic_candidates = []
    try:
        dynamic_candidates = fetch_candidates_from_api()
        # Filter: Only run if the database flag run_extract_linkedin_jobs is True
        dynamic_candidates = [c for c in dynamic_candidates if c.get('run_extract_linkedin_jobs', True)]
        logger.info(f"Loaded {len(dynamic_candidates)} candidates from Database/API with 'Run' flag enabled.")
    except Exception as e:
        logger.warning(f"Could not load dynamic candidates: {e}")

    final_candidates = []
    default_keywords = get_env_keywords()
    
    for dc in dynamic_candidates:
        if not isinstance(dc, dict): continue
        
        # --- SMART PARSER FOR COMBINED STRINGS ---
        # Handles: "keywords:K1,K2|560100,500032" OR ["keywords:...|..."] 
        raw_val = dc.get('locations') or dc.get('zipcode') or dc.get('zip_code') or []
        
        # Normalize to list of strings
        if isinstance(raw_val, str):
            raw_val = [raw_val]
        
        final_locs = []
        parsed_keywords = []
        
        if isinstance(raw_val, list):
            for item in raw_val:
                if isinstance(item, str) and '|' in item:
                    logger.info(f"🔍 Splitting combined data for {dc.get('candidate_id', 'unknown')}...")
                    parts = item.split('|')
                    # Extract Keywords
                    kw_part = parts[0].replace('keywords:', '').strip()
                    if kw_part:
                        parsed_keywords.extend([k.strip() for k in kw_part.split(',') if k.strip()])
                    # Extract Zipcodes
                    loc_part = parts[1].replace('zipcode:', '').strip()
                    if loc_part:
                        zips = [z.strip() for z in loc_part.split(',') if z.strip()]
                        final_locs.extend(zips)
                else:
                    final_locs.append(str(item))
        
        dc['locations'] = final_locs
        if parsed_keywords:
            dc['keywords'] = parsed_keywords

        # Fallback to .env settings if missing
        if not dc.get('keywords'):
            dc['keywords'] = default_keywords
        
        if dc.get('locations'):
            final_candidates.append(dc)
        else:
            logger.warning(f"No location data for candidate {dc.get('candidate_id')}")

    return final_candidates

def run_extraction():
    # Load global settings from .env
    env_dist = int(os.getenv("DISTANCE_MILES", 50))
    env_max_apps = int(os.getenv("MAX_APPLICATIONS_PER_RUN", 50))
    
    # Initialize stores
    api_store = APIStore()
    
    # Load primary candidates from DB/API
    candidates = load_candidates_from_db()
    
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
                keywords = cand.get('keywords')
                locations = cand.get('locations', [])
                
                # Check if login is possible
                can_login = username and password and password != "*****"
                
                # Use individual or env limit
                max_total_limit = cand.get('max_applications_per_run') or env_max_apps
                
                logger.info(f"--- Processing Candidate: {candidate_id} ({username if username else 'No Login'}) ---")
                logger.info(f"Keywords: {keywords}")
                logger.info(f"Locations: {locations}")

                if not locations:
                    logger.warning(f"Candidate {candidate_id} has no locations. Skipping.")
                    continue

                # File setup
                exports_dir = os.path.abspath(os.path.join(os.getcwd(), "data", "exports"))
                os.makedirs(exports_dir, exist_ok=True)
                csv_filename = os.path.join(exports_dir, "extractor_job_links.csv")
                
                # Distance Logic
                jobs_per_zip = 999 
                total_candidate_extracted = 0
                
                # Use env distance
                max_dist = cand.get('distance_miles') or env_dist
                dist_list = [5, 10, 25, 50, 100]
                dist_list = [d for d in dist_list if d <= max_dist]
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
                            # Exit if we hit the TOTAL CANDIDATE limit
                            if total_candidate_extracted >= max_total_limit:
                                logger.info(f"✅ Reached TOTAL candidate limit of {max_total_limit}. Stopping all extractions.")
                                remaining_locations = []
                                break
                            
                            if location_extraction_total >= jobs_per_zip:
                                break
                            
                            remaining_for_cand = max_total_limit - total_candidate_extracted
                                
                            logger.info(f"  --- Distance Bucket: {current_dist} miles (Candidate Total: {total_candidate_extracted}/{max_total_limit}) ---")
                            
                            extractor = JobExtractor(
                                browser, 
                                candidate_id=candidate_id, 
                                csv_path=csv_filename, 
                                distance_miles=current_dist,
                                api_store=api_store
                            )
                            
                            zip_match = re.search(r'\b\d{5,6}\b', current_loc)
                            zipcode = zip_match.group(0) if zip_match else current_loc

                            logger.info(f"Starting extraction for: {current_loc} at {current_dist}mi")
                            newly_found = extractor.start_extract(keywords, locations=[current_loc], zipcode=zipcode, limit=remaining_for_cand)
                            location_extraction_total += newly_found
                            total_candidate_extracted += newly_found
                        
                        remaining_locations.pop(0)
                        time.sleep(5)

                    except Exception as e:
                        err_msg = str(e).lower()
                        logger.error(f"Error processing location {current_loc}: {e}")
                        
                        if any(x in err_msg for x in ['invalid session', 'disconnected', 'no such window', 'browser_crash', 'retry_failed']):
                            if browser:
                                try: browser.driver.quit()
                                except: pass
                            browser = None
                        else:
                            remaining_locations.pop(0)
                            if browser:
                                try: browser.driver.quit()
                                except: pass
                            browser = None

                if browser:
                    try: browser.driver.quit()
                    except: pass
            except Exception as cand_e:
                logger.error(f"❌ Critical error processing candidate {cand.get('candidate_id')}: {cand_e}")
                continue

    finally:
        api_store.close()
        logger.info("Daily Extraction completed.")

if __name__ == '__main__':
    run_extraction()
