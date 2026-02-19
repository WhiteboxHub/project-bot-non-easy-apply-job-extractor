import time
import random
import logging
import os
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from dotenv import load_dotenv

load_dotenv()

LINKEDIN_BASE_URL = os.getenv("LINKEDIN_BASE_URL", "https://www.linkedin.com")

from bot.utils.delays import sleep_random
from bot.utils.selectors import LOCATORS
from bot.utils.logger import logger
from bot.utils.retry import retry
from bot.utils.stale_guard import safe_action
from bot.discovery.job_identity import JobIdentity
from bot.discovery.search import Search
from bot.discovery.scroll_tracker import ScrollTracker
from bot.persistence.store import Store
from bot.persistence.api_store import APIStore
from bot.utils.human_interaction import HumanInteraction

import csv
import os

class JobExtractor(Search):
    def __init__(self, browser, candidate_id="default", blacklist=None, experience_level=None, csv_path=None, distance_miles=50, api_store=None, search_timespan="r86400"):
        # We don't need workflow for extraction as we are not applying here
        # Passing None for workflow
        super().__init__(browser, None, blacklist, experience_level)
        self.candidate_id = candidate_id
        self.csv_path = csv_path
        self.distance_miles = distance_miles  # Distance filter: 10, 25, 50, 100 miles
        self.store = Store()
        self.api_store = api_store if api_store else APIStore()
        self.mysql_store = None # Will be set by caller or during extraction
        self.search_timespan = search_timespan
        self.seen_jobs = self._load_seen_jobs()
        
        # Initialize CSV if provided
        if self.csv_path and not os.path.exists(self.csv_path):
            with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, quoting=csv.QUOTE_NONNUMERIC)
                writer.writerow(['source_job_id', 'title', 'company', 'location', 'zipcode', 'url', 'date_extracted', 'is_non_easy_apply'])
        
        # batch_buffer lives on api_store now (shared across all distance buckets)

    # flush_batches() has been moved to APIStore.flush_batches()
    # Jobs accumulate in api_store.batch_buffer across ALL pages/distances
    # and are flushed once at the end of the full run in daily_extractor.py

    def _load_seen_jobs(self):
        """Load already extracted job IDs from database to prevent duplicates"""
        try:
            res = self.store.con.execute("SELECT job_id FROM extracted_jobs").fetchall()
            return {row[0] for row in res}
        except Exception as e:
            logger.warning(f"Could not load seen jobs: {e}")
            return set()

    def start_extract(self, positions, locations, zipcode="", limit=15):
        combos = []
        # Ensure lists
        positions = [positions] if isinstance(positions, str) else positions
        locations = [locations] if isinstance(locations, str) else locations

        # Randomize combinations
        combo_list = []
        for p in positions:
            for l in locations:
                combo_list.append((p, l))
        random.shuffle(combo_list)

        total_extracted = 0
        try:
            for position, location in combo_list:
                logger.info(f"Extracting jobs for {position}: {location} (Zipcode: {zipcode})", step="extract_init")
                if self.csv_path:
                    logger.info(f"📂 CSV file: {os.path.abspath(self.csv_path)}")
                
                remaining_limit = limit - total_extracted
                if remaining_limit <= 0: break
                
                count = self.extraction_loop(position, location, zipcode, limit=remaining_limit)
                total_extracted += count
                if total_extracted >= limit:
                    break
        finally:
            pass  # Final flush is handled by daily_extractor.py (once for the whole run)
            
        return total_extracted

    def extraction_loop(self, position, location, zipcode="", limit=15):
        jobs_per_page = 0
        start_time = time.time()
        human = HumanInteraction(self.browser)
        
        # Initial Load
        self.next_jobs_page(position, location, jobs_per_page)
        time.sleep(5)

        extracted_total = 0
        
        while time.time() - start_time < self.MAX_SEARCH_TIME:
            try:
                # Timer log
                mins_left = (self.MAX_SEARCH_TIME - (time.time() - start_time)) // 60
                logger.info(f"Page {int(jobs_per_page/25) + 1} | {mins_left}m left", step="job_extract")
                
                # ... [Browser Health Check omitted for brevity in chunking, but kept in file] ...
                try:
                    _ = self.browser.title
                except Exception:
                    logger.error("Browser session lost during loop.", step="job_extract")
                    raise Exception("INVALID_SESSION_RESTART")

                if "No matching jobs found" in self.browser.page_source:
                    logger.info("No more jobs found for this search.", step="job_extract", event="no_results")
                    break

                # --- STEP 1: Optimized scroll to load all jobs on current page ---
                time.sleep(2)
                
                logger.info("Starting scroll routine...", step="job_extract")
                
                last_count = 0
                stable_iterations = 0
                max_scrolls = 20  # Maximum scrolls to prevent infinite loops
                
                for scroll_num in range(max_scrolls):
                    # Scroll to bottom
                    self.browser.execute_script("""
                        var list = document.querySelector('.jobs-search-results-list') || 
                                   document.querySelector('.scaffold-layout__list-container') ||
                                   document.querySelector('.jobs-search__results-list');
                        if (list) {
                            list.scrollTop = list.scrollHeight;
                        } else {
                            window.scrollTo(0, document.body.scrollHeight);
                        }
                    """)
                    time.sleep(1.2)  # Balanced wait time
                    
                    new_count = len(self.get_elements("links"))
                    
                    # If count hasn't changed for 2 consecutive checks, we're done
                    if new_count == last_count:
                        stable_iterations += 1
                        if stable_iterations >= 2:
                            break
                    else:
                        stable_iterations = 0
                    
                    last_count = new_count
                    
                    # Early exit if we have a full page (25 jobs)
                    if last_count >= 25:
                        break

                logger.info(f"✅ Scrolling complete. Found {last_count} job cards to inspect.", step="job_extract")
                time.sleep(1)

                # --- STEP 2: Extract all jobs on this page ---
                processed_job_ids_on_page = set()
                iteration = 0
                extracted_on_page = 0
                
                while iteration < 50:
                    if extracted_total >= limit:
                        break
                        
                    iteration += 1
                    
                    if not self.is_present(self.locator["links"]):
                        break
                    
                    links = self.get_elements("links")
                    found_new_in_iteration = False
                    
                    for link in links:
                        if extracted_total >= limit: break
                        
                        try:
                            _ = link.text
                        except: break

                        try:
                            job_id = JobIdentity.extract_job_id(link)
                            
                            # Log each job found for debugging
                            link_text_preview = link.text[:100].replace('\n', ' | ')
                            logger.info(f"🔍 Job Check: ID={job_id} | Text={link_text_preview}")
                            
                            if not job_id:
                                logger.info(f"❌ Skipping - no job ID found")
                                continue
                            
                            if job_id in processed_job_ids_on_page:
                                logger.info(f"⏭️ Skipping {job_id} - already processed on this page")
                                continue
                                
                            if job_id in self.seen_jobs:
                                logger.info(f"⏭️ Skipping {job_id} - already seen (duplicate)")
                                continue
                            
                            found_new_in_iteration = True
                            processed_job_ids_on_page.add(job_id)
                            
                            is_easy = "Easy Apply" in link.text
                            if is_easy:
                                logger.info(f"🚫 Skipping EASY APPLY job: {job_id}")
                                self.seen_jobs.add(job_id)
                                continue

                            self.browser.execute_script("arguments[0].click();", link)
                            time.sleep(1)
                            
                            # Save the job (Only Non-Easy Apply jobs reach this point)
                            self.save_job(job_id, link, position, location, zipcode)
                            self.seen_jobs.add(job_id)
                            extracted_on_page += 1
                            extracted_total += 1
                            
                        except Exception as e:
                            if "stale" in str(e).lower(): break 
                            continue
                    
                    if not found_new_in_iteration or extracted_total >= limit:
                        break
                    
                    time.sleep(0.5)
                
                logger.info(f"Finished Page {int(jobs_per_page/25) + 1}: {extracted_on_page} NEW links saved. Total so far: {extracted_total}/{limit}", step="job_extract")
                logger.info(f"📥 Buffer now holds {len(self.api_store.batch_buffer) if self.api_store else 0} jobs total (flush at end of run)", step="job_extract")

                if extracted_total >= limit:
                    logger.info(f"Reached search limit of {limit} jobs. Breaking pagination.", step="job_extract")
                    break

                # --- STEP 3: Move to Next Page ---
                try:
                    next_button = self.browser.find_element(By.XPATH, "//button[@aria-label='Next' or contains(@class, 'pagination__button--next')]")
                    if next_button and next_button.is_enabled():
                        logger.info("Clicking NEXT button...", step="job_extract")
                        self.browser.execute_script("arguments[0].click();", next_button)
                        jobs_per_page += 25
                        time.sleep(5)
                        continue
                except:
                    pass

                logger.info("Next button not found, using URL pagination...", step="job_extract")
                jobs_per_page += 25
                if jobs_per_page >= 1000: break
                self.next_jobs_page(position, location, jobs_per_page)
                time.sleep(5)

            except Exception as e:
                err_msg = str(e).lower()
                if "invalid_session_restart" in err_msg or "invalid session id" in err_msg or "disconnected" in err_msg:
                    raise e
                break
        
        return extracted_total

    @retry(max_attempts=3, delay=2)
    def next_jobs_page(self, position, location, jobs_per_page):
        # Refresh session if it's dead
        try:
            if not self.browser.service.process or not self.browser.session_id:
                raise Exception("Browser died")
        except:
             logger.warning("Session lost before navigation. Attempting recovery...")
             # Re-navigation will happen if this is caught or if the getter fails
        
        experience_level_str = ",".join(map(str, self.experience_level)) if self.experience_level else ""
        experience_level_param = f"&f_E={experience_level_str}" if experience_level_str else ""
        
        # Distance filter mapping: 10, 25, 50, 100 miles
        # We use both f_D and distance parameters for maximum compatibility
        distance_param = f"&f_D={self.distance_miles}&distance={self.distance_miles}" if self.distance_miles else ""
        
        # Sort by Date (DD) - LinkedIn's parameter for most recent
        sort_param = "&sortBy=DD"
        
        # Add origin and refresh for better recognition
        extra_params = "&origin=JOB_SEARCH_PAGE_LOCATION_AUTOCOMPLETE&refresh=true"
        
        # Improve location recognition for raw zipcodes
        # 6 digits -> India, 5 digits -> US
        if location.isdigit():
            if len(location) == 6:
                 formatted_location = f"{location}, India"
            elif len(location) == 5:
                 formatted_location = f"{location}, United States"
            else:
                 formatted_location = location
        else:
             formatted_location = location

        # f_TPR filter for search timespan (e.g., r86400 for 24h, r604800 for 7d)
        search_time_filter = f"&f_TPR={self.search_timespan}" 
        location_param = f"&location={formatted_location}"
        # Wrap keyword in quotes (%22) for strict phrase matching to avoid broad matches like UI for AI searches
        keyword_param = f"%22{position}%22"
        url = (f"{LINKEDIN_BASE_URL}/jobs/search/?" + "keywords=" +
               keyword_param + location_param + search_time_filter + "&start=" + str(jobs_per_page) + 
               experience_level_param + distance_param + sort_param + extra_params)
        
        logger.info(f"Navigating to: {url}", step="job_extract", event="navigation")
        self.browser.get(url)
        time.sleep(3)
        self.browser.execute_script("window.scrollTo(0, 0);")

    def save_job(self, job_id, element, position, search_location, zipcode=""):
        try:
            # Get all text lines, filtered for empty space
            all_lines = [l.strip() for l in element.text.split('\n') if l.strip()]
            
            # Remove badges/labels from lines to find real data
            filter_labels = ["Easy Apply", "Promoted", "Actively recruiting", "Be an early applicant", "1 week ago", "2 weeks ago", "days ago", "hours ago"]
            clean_lines = []
            for line in all_lines:
                if not any(label in line for label in filter_labels):
                    clean_lines.append(line)
            
            # Heuristic for LinkedIn Job Card
            # Text usually looks like:
            # "Job Title"
            # "Company Name"
            # "Location"
            # "Active 3 days ago"
            
            title = clean_lines[0] if len(clean_lines) > 0 else "Unknown"
            
            # Remove Title from lines to find Company/Location
            remaining_lines = clean_lines[1:]
            
            # Initialize with fallbacks to avoid UnboundLocalError
            company = "Unknown"
            location = search_location
            
            # Fallback for Company/Location: Look for aria-labels in child elements for better precision
            from bot.utils.selectors import get_locator
            
            try:
                # Try primary and fallback for company
                for use_fb in [False, True]:
                    comp_loc = get_locator("company", use_fallback=use_fb)
                    elems = element.find_elements(*comp_loc)
                    if elems:
                        company = elems[0].text.split('\n')[0].strip()
                        break
                
                # Secondary Fallback: If still unknown, use the text-line heuristic
                if company == "Unknown" and len(remaining_lines) > 0:
                    company = remaining_lines[0]
                
                # Try primary and fallback for location
                for use_fb in [False, True]:
                    loc_loc = get_locator("location", use_fallback=use_fb)
                    elems = element.find_elements(*loc_loc)
                    if elems:
                        location = elems[0].text.split('\n')[0].strip()
                        break
                
                # Secondary Fallback: if location is generic, use the 2nd text line
                if (location == search_location or location == "Unknown") and len(remaining_lines) > 1:
                    raw_loc = remaining_lines[1]
                    if "ago" not in raw_loc and "Apply" not in raw_loc:
                        location = raw_loc
            except:
                pass

            # Cleanup and Lowercase
            company = company.replace("\n", " ").strip().lower()
            location = location.replace("\n", " ").strip().lower()
            title = title.lower()
            job_id = str(job_id).lower() if job_id else ""
            zipcode = str(zipcode).lower()


            url = f"https://www.linkedin.com/jobs/view/{job_id}"
            
            # Database Save
            self.store.con.execute(
                 "INSERT OR REPLACE INTO extracted_jobs (id, job_id, url, title, company, location, date_extracted, candidate_id, is_easy_apply) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)",
                 [job_id, job_id, url, title, company, location, self.candidate_id, True]
             )
            self.store.con.commit()
             
            # CSV Save
            if self.csv_path:
                with open(self.csv_path, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f, quoting=csv.QUOTE_NONNUMERIC)
                    writer.writerow([job_id, title, company, location, zipcode, url, time.strftime('%Y-%m-%d %H:%M:%S'), True])
                
            # API Save (Remote)
            job_data = {
                'title': title,
                'company': company,
                'location': location,
                'zipcode': zipcode,
                'url': url,
                'source_job_id': job_id
            }
            if self.api_store:
                # Accumulate in the shared api_store buffer (flushed once at end of full run)
                self.api_store.batch_buffer.append(job_data)
                logger.info(f"📥 Queued for bulk insert (buffer size: {len(self.api_store.batch_buffer)})", step="extract_job")
                
            # MySQL Save (Direct Database)
            if hasattr(self, 'mysql_store') and self.mysql_store:
                self.mysql_store.insert_position(job_data)
            
            logger.info(f"Saved job: {title} at {company} ({location}) - Zipcode: {zipcode}", step="extract_job")
                
        except Exception as e:
             logger.debug(f"Failed to save job {job_id}: {e}")


