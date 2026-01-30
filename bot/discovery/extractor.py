import time
import random
import logging
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By

from bot.utils.delays import sleep_random
from bot.utils.selectors import LOCATORS
from bot.utils.logger import logger
from bot.utils.retry import retry
from bot.utils.stale_guard import safe_action
from bot.discovery.job_identity import JobIdentity
from bot.discovery.search import Search
from bot.discovery.scroll_tracker import ScrollTracker
from bot.persistence.store import Store
from bot.persistence.mysql_store import MySQLStore
from bot.utils.human_interaction import HumanInteraction

import csv
import os

class JobExtractor(Search):
    def __init__(self, browser, candidate_id="default", blacklist=None, experience_level=None, csv_path=None, distance_miles=50, mysql_store=None):
        # We don't need workflow for extraction as we are not applying here
        # Passing None for workflow
        super().__init__(browser, None, blacklist, experience_level)
        self.candidate_id = candidate_id
        self.csv_path = csv_path
        self.distance_miles = distance_miles  # Distance filter: 10, 25, 50, 100 miles
        self.store = Store()
        self.mysql_store = mysql_store if mysql_store else MySQLStore()
        self.seen_jobs = self._load_seen_jobs()
        
        # Initialize CSV if provided
        if self.csv_path and not os.path.exists(self.csv_path):
            with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, quoting=csv.QUOTE_NONNUMERIC)
                writer.writerow(['job_id', 'title', 'company', 'location', 'zipcode', 'url', 'date_extracted', 'is_easy_apply'])

    def _load_seen_jobs(self):
        """Load already extracted job IDs from database to prevent duplicates"""
        try:
            res = self.store.con.execute("SELECT job_id FROM extracted_jobs").fetchall()
            return {row[0] for row in res}
        except Exception as e:
            logger.warning(f"Could not load seen jobs: {e}")
            return set()

    def start_extract(self, positions, locations, zipcode=""):
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
        for position, location in combo_list:
            logger.info(f"Extracting jobs for {position}: {location} (Zipcode: {zipcode})", step="extract_init")
            if self.csv_path:
                logger.info(f"📂 CSV file: {os.path.abspath(self.csv_path)}")
            
            # Pass a limit if needed
            remaining_limit = 15 - total_extracted
            if remaining_limit <= 0: break
            
            count = self.extraction_loop(position, location, zipcode, limit=remaining_limit)
            total_extracted += count
            if total_extracted >= 15:
                break
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

                # --- STEP 1: Scroll to load all jobs on current page ---
                time.sleep(3) 
                
                logger.info("Starting scroll routine...", step="job_extract")
                last_height = 0
                stuck_count = 0
                
                for i in range(15):
                    try:
                        self.browser.execute_script("""
                            try {
                                var selectors = ['.jobs-search-results-list', '.jobs-search-results', '.scaffold-layout__list-container', 'section.jobs-search-results-list', 'div[class*="jobs-search-results-list"]'];
                                var list = null;
                                for (var s of selectors) {
                                    list = document.querySelector(s);
                                    if (list) break;
                                }
                                
                                if (list) {
                                    list.scrollTop += 600;
                                    var items = list.querySelectorAll('li');
                                    if (items.length > 0) {
                                        items[items.length - 1].scrollIntoView({ behavior: 'smooth', block: 'end' });
                                    }
                                    return list.scrollTop + list.offsetHeight;
                                } else {
                                    window.scrollBy({ top: 800, behavior: 'smooth' });
                                    return window.pageYOffset + window.innerHeight;
                                }
                            } catch(e) { return -1; }
                        """)
                        
                        time.sleep(1.5)
                        
                        current_links = self.get_elements("links")
                        if len(current_links) >= 15:
                             break
                             
                        if len(current_links) == last_height:
                            stuck_count += 1
                        else:
                            last_height = len(current_links)
                            stuck_count = 0
                        
                        if stuck_count >= 3: break
                    except Exception: break

                logger.info("Scrolling complete.", step="job_extract")
                time.sleep(3)

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
                            if not job_id or job_id in processed_job_ids_on_page or job_id in self.seen_jobs:
                                continue
                            
                            found_new_in_iteration = True
                            processed_job_ids_on_page.add(job_id)
                            
                            is_easy = "Easy Apply" in link.text
                            self.browser.execute_script("arguments[0].click();", link)
                            time.sleep(1)
                            
                            if is_easy:
                                self.seen_jobs.add(job_id)
                                continue

                            # Save the job
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

        # f_TPR=r86400 is the filter for Past 24 Hours
        location_param = f"&location={formatted_location}"
        url = ("https://www.linkedin.com/jobs/search/?f_TPR=r86400&keywords=" +
               position + location_param + "&start=" + str(jobs_per_page) + 
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

            # Cleanup
            company = company.replace("\n", " ").strip()
            location = location.replace("\n", " ").strip()


            url = f"https://www.linkedin.com/jobs/view/{job_id}"
            
            # Database Save
            self.store.con.execute(
                 "INSERT OR REPLACE INTO extracted_jobs (id, job_id, url, title, company, location, date_extracted, candidate_id, is_easy_apply) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)",
                 [job_id, job_id, url, title, company, location, self.candidate_id, False]
             )
            self.store.con.commit()
             
            # CSV Save
            if self.csv_path:
                with open(self.csv_path, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f, quoting=csv.QUOTE_NONNUMERIC)
                    writer.writerow([job_id, title, company, location, zipcode, url, time.strftime('%Y-%m-%d %H:%M:%S'), False])
                
            # MySQL Save
            self.mysql_store.insert_position({
                'title': title,
                'company': company,
                'location': location,
                'zipcode': zipcode,
                'url': url,
                'job_id': job_id
            })
            
            logger.info(f"Saved job: {title} at {company} ({location}) - Zipcode: {zipcode}", step="extract_job")
                
        except Exception as e:
             logger.debug(f"Failed to save job {job_id}: {e}")


