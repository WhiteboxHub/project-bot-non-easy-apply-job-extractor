import yaml
import logging
import os
import time
import re
from bot.utils.logger import logger
from bot.core.browser import Browser
from bot.core.session import Session
from bot.discovery.extractor import JobExtractor
from bot.persistence.store import Store
from bot.persistence.mysql_store import MySQLStore
from bot.api.website_client import fetch_candidates_from_api
from dotenv import load_dotenv

load_dotenv()

def load_candidates_with_enrichment():
    """
    Primary Source: YAML.
    Secondary Source: Dynamic (API/DB) for enriching missing locations.
    """
    yaml_candidates = []
    global_settings = {}
    
    # 1. Load YAML data
    try:
        yaml_path = "candidate_marketing.yaml"
        if os.path.exists(yaml_path):
            with open(yaml_path, 'r') as stream:
                data = yaml.safe_load(stream)
                yaml_candidates = data.get('candidates', [])
                global_settings = data.get('settings', {})
                logger.info(f"Loaded {len(yaml_candidates)} candidates from {yaml_path}")
        else:
            logger.warning(f"{yaml_path} not found. Will attempt to load all from dynamic source.")
    except Exception as e:
        logger.error(f"Error reading YAML: {e}")

    # 2. Fetch Dynamic Data for enrichment/fallback
    dynamic_candidates = []
    try:
        dynamic_candidates = fetch_candidates_from_api()
        logger.info(f"Loaded {len(dynamic_candidates)} dynamic candidates for enrichment.")
    except Exception as e:
        logger.warning(f"Could not load dynamic candidates: {e}")

    # 3. Merging Logic
    final_candidates = []
    processed_emails = set()
    processed_cids = set()
    
    # First, add candidates from YAML
    for cand in yaml_candidates:
        # Prioritize YAML Keywords
        if not cand.get('keywords'):
            cand['keywords'] = global_settings.get('positions', ["Software Engineer"])
        
        # Prioritize YAML Locations, fallback to Dynamic
        locs = cand.get('locations', []) or cand.get('zipcodes', []) or []
        target_username = (cand.get('linkedin_username') or '').lower().strip()
        target_name = (cand.get('name') or '').lower().strip()
        
        # Try to find match in dynamic candidates for enrichment
        match = None
        for dc in dynamic_candidates:
            dc_email = (dc.get('linkedin_username') or '').lower().strip()
            dc_name = (dc.get('full_name') or dc.get('name') or '').lower().strip()
            
            if (target_username and dc_email == target_username) or \
               (cand.get('candidate_id') == dc.get('candidate_id')):
                match = dc
                break
            if target_name and dc_name and (target_name in dc_name or dc_name in target_name):
                match = dc
                break
        
        if match:
            # Enrich keywords if missing
            if not cand['keywords'] and match.get('keywords'):
                cand['keywords'] = match['keywords']
            # Enrich locations if missing
            if not locs and match.get('locations'):
                locs = match['locations']
                logger.info(f"✅ Enriched YAML candidate {cand.get('candidate_id')} ('{cand.get('name')}') with {len(locs)} locations from DB.")
        
        cand['locations'] = locs
        final_candidates.append(cand)
        if target_username: processed_emails.add(target_username)
        processed_cids.add(cand.get('candidate_id'))

    # Second, add any dynamic candidates that weren't in YAML
    new_from_dynamic = 0
    for dc in dynamic_candidates:
        dc_email = (dc.get('linkedin_username') or '').lower().strip()
        dc_cid = dc.get('candidate_id')
        
        if dc_email not in processed_emails and dc_cid not in processed_cids:
            if not dc.get('keywords'):
                dc['keywords'] = global_settings.get('positions', ["Software Engineer"])
            
            # Only add if they have locations, otherwise we can't extract anyway
            if dc.get('locations'):
                final_candidates.append(dc)
                new_from_dynamic += 1
                if dc_email: processed_emails.add(dc_email)

    if new_from_dynamic > 0:
        logger.info(f"➕ Added {new_from_dynamic} additional candidates from database to the run.")

    return final_candidates, global_settings

def run_extraction():
    store = Store()
    mysql_store = MySQLStore()
    
    candidates, global_settings = load_candidates_with_enrichment()
    
    if not candidates:
        logger.error("No candidates found to process.")
        return

    for cand in candidates:
        candidate_id = cand.get('candidate_id', 'unknown')
        
        # Respect the flag (Checking YAML flag or Database flag)
        run_flag = cand.get('run_extract_linkedin_jobs')
        if run_flag is False or str(run_flag).lower() == 'false':
            logger.info(f"⏭️ Skipping {candidate_id} - 'run_extract_linkedin_jobs' flag is disabled.")
            continue

        username = cand.get('linkedin_username')
        password = cand.get('linkedin_password')
        keywords = cand.get('keywords', ["Software Engineer"])
        locations = cand.get('locations', [])
        
        # Check if login is possible
        can_login = username and password and password != "*****"
        
        logger.info(f"--- Processing Candidate: {candidate_id} ({username if username else 'No Login'}) ---")
        logger.info(f"Keywords: {keywords}")
        logger.info(f"Locations: {locations}")

        if not locations:
            logger.warning(f"Candidate {candidate_id} has no locations. Skipping.")
            continue

        # File setup
        # Use a single centralized CSV file name as requested by the user
        exports_dir = os.path.abspath(os.path.join(os.getcwd(), "data", "exports"))
        os.makedirs(exports_dir, exist_ok=True)
        csv_filename = os.path.join(exports_dir, "extractor_job_links.csv")
        
        # Distance settings
        use_ladder = global_settings.get('distance_ladder', True)
        if use_ladder:
            dist_list = [5, 10, 25, 50, 100]
            max_dist = global_settings.get('distance_miles', 50)
            dist_list = [d for d in dist_list if d <= max_dist]
        else:
            dist_list = [global_settings.get('distance_miles', 50)]

        # Profile setup
        profile_path = os.path.join(os.getcwd(), "data", "profiles", candidate_id)
        
        browser = None
        remaining_locations = list(locations)
        
        while remaining_locations:
            current_loc = remaining_locations[0].strip()
            
            try:
                if browser is None:
                    logger.info(f"Initializing browser for {candidate_id}...")
                    browser = Browser(profile_path=profile_path)
                    if can_login:
                        session = Session(browser.driver)
                        session.login(username, password)
                    else:
                        logger.info("Running without login (using profile or public search)...")

                # Track newly extracted jobs for this location across all distance buckets (5mi, 10mi, 25mi...)
                location_extraction_total = 0
                
                # Iterate through distance buckets for "pseudo-sorting"
                for current_dist in dist_list:
                    # User requested limit: move to next ZIP once 15 jobs are found for this location
                    if location_extraction_total >= 15:
                        logger.info(f"✅ Reached 15-job limit for {current_loc}. Skipping remaining distance buckets.")
                        break
                        
                    logger.info(f"  --- Distance Bucket: {current_dist} miles (Current Total for {current_loc}: {location_extraction_total}/15) ---")
                    
                    extractor = JobExtractor(
                        browser, 
                        candidate_id=candidate_id, 
                        csv_path=csv_filename, 
                        distance_miles=current_dist,
                        mysql_store=mysql_store
                    )
                    
                    zip_match = re.search(r'\b\d{5,6}\b', current_loc)
                    zipcode = zip_match.group(0) if zip_match else current_loc

                    logger.info(f"Starting extraction for: {current_loc} at {current_dist}mi")
                    # Pass the REMAINING limit to the extractor
                    newly_found = extractor.start_extract(keywords, locations=[current_loc], zipcode=zipcode)
                    location_extraction_total += newly_found
                
                # Success for this location -> Next location
                remaining_locations.pop(0)
                time.sleep(5)

            except Exception as e:
                err_msg = str(e).lower()
                logger.error(f"Error processing location {current_loc}: {e}")
                
                # Restart browser on session errors
                if any(x in err_msg for x in ['invalid session', 'disconnected', 'no such window', 'browser_crash', 'retry_failed']):
                    logger.warning("Session issues detected. Restarting browser...")
                    if browser:
                        try: browser.driver.quit()
                        except: pass
                    browser = None
                else:
                    # Logical error -> Skip to next
                    logger.warning(f"Skipping {current_loc} due to logical error.")
                    remaining_locations.pop(0)
                    if browser:
                        try: browser.driver.quit()
                        except: pass
                    browser = None

        if browser:
            try: browser.driver.quit()
            except: pass

    mysql_store.close()
    logger.info("Daily Extraction completed.")

if __name__ == '__main__':
    # When run directly, it executes once.
    run_extraction()

