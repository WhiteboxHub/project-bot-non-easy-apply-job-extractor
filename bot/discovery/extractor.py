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
import re
from bot.utils.selectors import LOCATORS
from bot.utils.selector_helpers import get_locator, UI_TEXT

class JobExtractor(Search):
    def __init__(self, browser, candidate_id="default", blacklist=None, experience_level=None, csv_path=None, distance_miles=50, api_store=None, search_timespan="r86400", title_filters=None, job_type_filters=None):
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
        self.title_filters = title_filters or []
        self.job_type_filters = job_type_filters or []
        
        # Load blacklist from .env if not provided (for standalone runs)
        if not blacklist:
            env_blacklist = os.getenv("BLACKLIST_WORDS", "")
            if env_blacklist:
                self.blacklist = [w.strip() for w in env_blacklist.split(",") if w.strip()]
            else:
                self.blacklist = []
        else:
            self.blacklist = blacklist
        
        # Initialize CSV if provided
        if self.csv_path and not os.path.exists(self.csv_path):
            with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, quoting=csv.QUOTE_NONNUMERIC)
                writer.writerow(['source_job_id', 'title', 'company', 'location', 'zipcode', 'linkedin_url', 'apply_url', 'date_extracted', 'is_non_easy_apply'])
        
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

        # combos = [] # Not used
        combo_list = []
        for p in positions:
            for l in locations:
                combo_list.append((p, l))

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
        self.position = position # Store current keyword for filter session tracking
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

                if UI_TEXT["no_matching_jobs"] in self.browser.page_source:
                    logger.info("No more jobs found for this search.", step="job_extract", event="no_results")
                    break

                # --- STEP 1: Optimized scroll to load all jobs on current page ---
                time.sleep(2)
                
                logger.info("Starting scroll routine...", step="job_extract")
                
                last_count = 0
                stable_iterations = 0
                max_scrolls = 20  # Maximum scrolls to prevent infinite loops
                
                for scroll_num in range(max_scrolls):
                    scroll_container = get_locator("job_search_list_container")
                    fallback_container = get_locator("job_search_list_container", use_fallback=True)
                    
                    self.browser.execute_script(f"""
                        var container = document.querySelector('{scroll_container[1]}') || 
                                        document.querySelector('{fallback_container[1]}') ||
                                        document.querySelector('.jobs-search-results-list') ||
                                        window;
                        if (container === window) {{
                            window.scrollTo(0, document.body.scrollHeight);
                        }} else {{
                            container.scrollTop = container.scrollHeight;
                        }}
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
                            
                            is_easy = UI_TEXT["easy_apply"] in link.text
                            if is_easy:
                                logger.info(f"✅ Found EASY APPLY job: {job_id}")
                            else:
                                logger.info(f"✅ Found STANDARD job: {job_id}")

                            # Apply strict title filter using word boundaries
                            if self.title_filters:
                                link_text = link.text.replace('\n', ' ')
                                matched = False
                                for f in self.title_filters:
                                    pattern = r'\b' + re.escape(f) + r'\b'
                                    if re.search(pattern, link_text, re.IGNORECASE):
                                        matched = True
                                        break
                                
                                if not matched:
                                    title_preview = link_text.split('|')[0].strip()[:50]
                                    logger.info(f"🚫 Skipping NON-MATCHING title: {title_preview} (Job ID {job_id})")
                                    self.seen_jobs.add(job_id)
                                    continue

                            # Apply Blacklist (Bad Words) filter
                            if self.blacklist:
                                link_text = link.text.replace('\n', ' ')
                                blacklisted = False
                                for word in self.blacklist:
                                    if word.lower() in link_text.lower():
                                        blacklisted = True
                                        break
                                
                                if blacklisted:
                                    title_preview = link_text.split('|')[0].strip()[:50]
                                    logger.info(f"🚫 Skipping BLACKLISTED job: {title_preview} (contains '{word}')")
                                    self.seen_jobs.add(job_id)
                                    continue

                            self.browser.execute_script("arguments[0].click();", link)
                            time.sleep(1)
                            
                            # Save the job
                            self.save_job(job_id, link, position, location, zipcode, is_easy_apply=is_easy)
                            self.seen_jobs.add(job_id)
                            extracted_on_page += 1
                            extracted_total += 1
                            
                        except Exception as e:
                            if "stale" in str(e).lower(): break 
                            continue
                    
                    if not found_new_in_iteration or extracted_total >= limit:
                        break
                    
                    # Micro-scroll to trigger lazy loading of the next batch of cards
                    self.browser.execute_script("window.scrollBy(0, 300);")
                    time.sleep(0.8)
                
                logger.info(f"Finished Page {int(jobs_per_page/25) + 1}: {extracted_on_page} NEW links saved. Total so far: {extracted_total}/{limit}", step="job_extract")
                logger.info(f"📥 Buffer now holds {len(self.api_store.batch_buffer) if self.api_store else 0} jobs total (flush at end of run)", step="job_extract")

                if extracted_total >= limit:
                    logger.info(f"Reached search limit of {limit} jobs. Breaking pagination.", step="job_extract")
                    break

                # --- STEP 3: Move to Next Page ---
                try:
                    next_button = self.browser.find_element(*get_locator("pagination_next"))
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
        # URL encode keyword and establish Smart Quoting
        encoded_keyword = position.replace(' ', '%20')
        if len(position) < 4:
            keyword_param = f"%22{encoded_keyword}%22"
        else:
            keyword_param = encoded_keyword

        # --- Filter Caching Logic ---
        # Capture and reuse numeric IDs for both Title (f_T) and Job Type (f_JT) filters
        filter_param = ""
        cached_titles = getattr(self.browser, f"f_T_cache_{position}", None)
        if cached_titles:
            filter_param += f"&f_T={cached_titles}"
            
        cached_job_types = getattr(self.browser, f"f_JT_cache_{position}", None)
        if cached_job_types:
            filter_param += f"&f_JT={cached_job_types}"
            
        url = (f"{LINKEDIN_BASE_URL}/jobs/search/?" + "keywords=" +
               keyword_param + location_param + search_time_filter + "&start=" + str(jobs_per_page) + 
               experience_level_param + distance_param + sort_param + extra_params + filter_param)
        
        logger.info(f"Navigating to: {url}", step="job_extract", event="navigation")
        self.browser.get(url)
        time.sleep(3)
        self.browser.execute_script("window.scrollTo(0, 0);")
        
        # Apply native filters (Titles + Job Type) IF they are not already cached in the URL
        if not cached_titles or not cached_job_types:
            self.apply_native_filters()

    def apply_native_filters(self):
        """Attempts to use the native LinkedIn UI to filter by Title and Job Type checkboxes."""
        if not self.title_filters and not self.job_type_filters:
            return
            
        try:
            logger.info("Applying native Title filters via UI...", step="job_extract")
            
            # Click 'All filters' button — selector managed in selectors.py
            try:
                btn_loc = get_locator("all_filters_button")
                all_filters_btn = self.browser.find_element(*btn_loc)
                if not all_filters_btn:
                    raise Exception("not found")
            except:
                try:
                    btn_loc = get_locator("all_filters_button", use_fallback=True)
                    all_filters_btn = self.browser.find_element(*btn_loc)
                except Exception:
                    logger.info("All filters button not found. Attempting Guest Mode individual pills...", step="job_extract")
                    self._apply_guest_pill_filters()
                    return
            
            self.browser.execute_script("arguments[0].click();", all_filters_btn)
            time.sleep(3)

            # --- NEW Step: Reset filters first to clear LinkedIn's 'memory' of previous runs ---
            try:
                # Optimized check: If we've already done this for this search session (per browser), skip
                session_key = f"filters_applied_{self.candidate_id}_{self.position}"
                if getattr(self.browser, session_key, False):
                    # We still check if they are visible in the URL or the modal might have closed, 
                    # but usually LinkedIn carries them in the URL once clicked.
                    # To be safe, we re-apply if it's the first page.
                    pass 

                reset_loc = get_locator("reset_filters")
                reset_btns = self.browser.find_elements(*reset_loc)
                if reset_btns and reset_btns[0].is_displayed():
                    self.browser.execute_script("arguments[0].click();", reset_btns[0])
                    logger.info("♻️ Reset existing filters.", step="job_extract")
                    time.sleep(2) # Wait for UI to update
            except Exception as ree:
                logger.debug(f"Reset filters failed (might not be visible or already clear): {ree}")
            
            clicked_any = False
            # 1. Handle TITLE Filters
            if self.title_filters:
                clicked_any |= self._apply_checkbox_section("title_filter_labels", "title_filter_show_more", self.title_filters, "Title")

            # 2. Handle JOB TYPE Filters
            if self.job_type_filters:
                clicked_any |= self._apply_checkbox_section("job_type_filter_labels", "job_type_filter_show_more", self.job_type_filters, "Job Type")
            
            if clicked_any:
                # Mark as filtered for this session to avoid redundant clicks if URL maintains state
                setattr(self.browser, f"filters_applied_{self.candidate_id}_{self.position}", True)

                # Click 'Show results' — selector managed in selectors.py
                try:
                    show_loc = get_locator("all_filters_show_results")
                    show_btn = self.browser.find_element(*show_loc)
                except:
                    try:
                        show_loc = get_locator("all_filters_show_results", use_fallback=True)
                        show_btn = self.browser.find_element(*show_loc)
                    except Exception:
                        logger.warning("Could not click 'Show results' button.")
                        show_btn = None
                if show_btn:
                    self.browser.execute_script("arguments[0].click();", show_btn)
                    time.sleep(5)
                    logger.info("Successfully applied native filters.", step="job_extract")
                    
                    # --- Capture the f_T and f_JT IDs from URL for next time ---
                    try:
                        current_url = self.browser.current_url
                        # Title IDs
                        ft_match = re.search(r'[?&]f_T=([^&]+)', current_url)
                        if ft_match:
                            ft_value = ft_match.group(1)
                            setattr(self.browser, f"f_T_cache_{self.position}", ft_value)
                            logger.info(f"💾 Cached Title Filter IDs: {ft_value}", step="job_extract")
                        
                        # Job Type IDs
                        fjt_match = re.search(r'[?&]f_JT=([^&]+)', current_url)
                        if fjt_match:
                            fjt_value = fjt_match.group(1)
                            setattr(self.browser, f"f_JT_cache_{self.position}", fjt_value)
                            logger.info(f"💾 Cached Job Type IDs: {fjt_value}", step="job_extract")
                    except Exception as e_ft:
                        logger.debug(f"Could not capture filter parameters from URL: {e_ft}")
            else:
                logger.info("No matching Title checkboxes found in the UI. Relying on code-level filter.", step="job_extract")
            # Close modal — selector managed in selectors.py
            try:
                dismiss_loc = get_locator("modal_dismiss")
                self.browser.find_element(*dismiss_loc).click()
            except:
                try:
                    dismiss_loc = get_locator("modal_dismiss", use_fallback=True)
                    self.browser.find_element(*dismiss_loc).click()
                except: pass
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Error applying native filters: {e}")

    def _apply_guest_pill_filters(self):
        """Logic for Guest View where filters are individual pills on the main page."""
        try:
            # 0. Dismiss any persistent guest modals first
            try:
                dismiss_loc = get_locator("guest_modal_dismiss")
                modal_btns = self.browser.find_elements(*dismiss_loc)
                for btn in modal_btns:
                    if btn.is_displayed():
                        self.browser.execute_script("arguments[0].click();", btn)
                        logger.info("Dismissed guest modal.", step="job_extract")
                        time.sleep(1)
            except: pass

            # 1. Job Type Pill
            if self.job_type_filters:
                pill_loc = get_locator("guest_job_type_pill")
                pills = self.browser.find_elements(*pill_loc)
                if pills and pills[0].is_displayed():
                    logger.info(f"Clicking Job Type pill for filters: {self.job_type_filters}", step="job_extract")
                    self.browser.execute_script("arguments[0].click();", pills[0])
                    time.sleep(2)
                    
                    # Guest View dropdowns are basically small modals
                    clicked = self._apply_checkbox_section("job_type_filter_labels", None, self.job_type_filters, "Job Type (Guest)")
                    
                    if clicked:
                        # Click Done/Apply in the pill dropdown
                        try:
                            # Usually there's a specific "Done" button in the dropdown
                            done_loc = (By.XPATH, "//button[contains(., 'Done') or contains(., 'Apply')]")
                            done_btn = self.browser.find_element(*done_loc)
                            self.browser.execute_script("arguments[0].click();", done_btn)
                            time.sleep(3)
                            logger.info("Applied Job Type pill filters.", step="job_extract")
                        except:
                            # If no done button, clicking the pill again might close it or just click outside
                            self.browser.execute_script("arguments[0].click();", pills[0])
                            time.sleep(2)
            
            # 2. Experience Level Pill (if needed in future)
            # ...
            
        except Exception as e:
            logger.debug(f"Guest pill filtering failed: {e}")

    def _apply_checkbox_section(self, label_locator_key, show_more_locator_key, filter_values, section_name):
        """Helper to find and click checkboxes in a specific section of the filter modal."""
        try:
            # Find labels inside the section
            labels = self.browser.find_elements(*get_locator(label_locator_key))
            if not labels:
                labels = self.browser.find_elements(*get_locator(label_locator_key, use_fallback=True))

            if not labels:
                 logger.info(f"Could not find any {section_name} filter labels in the UI.", step="job_extract")
                 return False

            # Try to expand "Show more" if it exists
            try:
                show_more_loc = get_locator(show_more_locator_key)
                show_more_btn = self.browser.find_element(*show_more_loc)
                if show_more_btn and show_more_btn.is_displayed():
                    logger.info(f"Clicking 'Show more' in {section_name} section...", step="job_extract")
                    self.browser.execute_script("arguments[0].click();", show_more_btn)
                    time.sleep(1.5)
                    # Re-fetch labels after expansion
                    labels = self.browser.find_elements(*get_locator(label_locator_key))
            except:
                pass

            clicked_any = False
            for label in labels:
                try:
                    # Scroll to element to ensure it's interactable
                    self.browser.execute_script("arguments[0].scrollIntoView({block: 'center'});", label)
                    time.sleep(0.1)
                    
                    text_content = label.text.strip()
                    first_line = text_content.split('\n')[0].strip()
                    if not first_line:
                        continue

                    for f in filter_values:
                        import re
                        pattern = r'\b' + re.escape(f.strip()) + r'\b'
                        
                        # Special guard for "AI" title filter
                        if section_name == "Title" and f.strip().lower() == "ai" and ".ai" in first_line.lower():
                            if not re.search(r'(?<!\.)\b' + re.escape(f.strip()) + r'\b', first_line, re.IGNORECASE):
                                continue

                        if re.search(pattern, first_line, re.IGNORECASE):
                            # Check if already checked (LinkedIn uses aria-checked on some inputs or just classes)
                            # Clicking usually toggles. We assume it's unchecked after 'Reset'.
                            self.browser.execute_script("arguments[0].click();", label)
                            logger.info(f"✅ Checked {section_name} filter: '{first_line}'")
                            time.sleep(0.5)
                            clicked_any = True
                            break
                except:
                    pass
            return clicked_any
        except Exception as e:
            logger.debug(f"Error in section {section_name}: {e}")
            return False

    def save_job(self, job_id, element, position, search_location, zipcode="", is_easy_apply=False):
        try:
            # Get all text lines, filtered for empty space
            all_lines = [l.strip() for l in element.text.split('\n') if l.strip()]
            
            # Remove badges/labels from lines to find real data — labels managed in selectors.py
            filter_labels = UI_TEXT["filter_out_labels"]
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
            from bot.utils.selector_helpers import get_locator
            
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


            # --- Start: ATS Link Extraction ---
            # Easy Apply jobs stay on LinkedIn — skip ATS extraction entirely for them
            linkedin_url = f"https://www.linkedin.com/jobs/view/{job_id}"
            apply_url = linkedin_url
            
            logger.info(f"🔗 LinkedIn URL: {linkedin_url}", step="extract_job")
            
            if is_easy_apply:
                # No external ATS link for Easy Apply — LinkedIn URL is correct as-is
                logger.info(f"⚡ Easy Apply job — using LinkedIn URL directly, skipping ATS extraction.", step="extract_job")
            else:
                try:
                    from bot.utils.selector_helpers import get_locator
                    from bot.utils.url_utils import decode_linkedin_redir
                    
                    # Wait longer for details pane to stabilize
                    time.sleep(5)
                    
                    print(f"\n[ATS DEBUG] ─────────────────────────────────────────")
                    print(f"[ATS DEBUG] Job ID   : {job_id}")
                    print(f"[ATS DEBUG] Job Title: {title}")
                    print(f"[ATS DEBUG] Searching for Apply button (primary selector)...")

                    # Try to find the button inside the details pane first to avoid global filter buttons — selectors managed in selectors.py
                    details_pane = None
                    for loc in get_locator("job_details_panes"):
                        try:
                            panes = self.browser.find_elements(*loc)
                            if panes and panes[0].is_displayed():
                                details_pane = panes[0]
                                break
                        except: continue

                    apply_locator = get_locator("external_apply_button")
                    if details_pane:
                        print(f"[ATS DEBUG] Searching for Apply button in details pane (primary)...")
                        apply_buttons = details_pane.find_elements(*apply_locator)
                    else:
                        print(f"[ATS DEBUG] Details pane not found, searching globally (primary)...")
                        apply_buttons = self.browser.find_elements(*apply_locator)
                    
                    print(f"[ATS DEBUG] Primary selector found: {len(apply_buttons)} element(s)")
                    
                    if not apply_buttons:
                        logger.info(f"🔍 Primary apply selector found nothing. Trying fallback...", step="extract_job")
                        print(f"[ATS DEBUG] Trying fallback selector...")
                        apply_locator = get_locator("external_apply_button", use_fallback=True)
                        if details_pane:
                            apply_buttons = details_pane.find_elements(*apply_locator)
                        else:
                            apply_buttons = self.browser.find_elements(*apply_locator)
                        print(f"[ATS DEBUG] Fallback selector found: {len(apply_buttons)} element(s)")

                    if not apply_buttons:
                        logger.info(f" No 'Apply' button found for Job {job_id} — saving LinkedIn URL instead.", step="extract_job")
                        print(f"[ATS DEBUG]  NO APPLY BUTTON FOUND — will save LinkedIn URL")
                        
                        # --- Diagnostic Capture ---
                        try:
                            debug_dir = os.path.join("logs", "debug")
                            os.makedirs(debug_dir, exist_ok=True)
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            
                            # Screenshot
                            screenshot_path = os.path.join(debug_dir, f"no_apply_{job_id}_{timestamp}.png")
                            self.browser.save_screenshot(screenshot_path)
                            
                            # HTML source
                            html_path = os.path.join(debug_dir, f"no_apply_{job_id}_{timestamp}.html")
                            with open(html_path, "w", encoding="utf-8") as f:
                                f.write(self.browser.page_source)
                                
                            print(f"[ATS DEBUG] 📸 Diagnostic capture saved to {debug_dir}")
                            logger.info(f"📸 Diagnostic capture (screenshot/HTML) saved for debugging.", step="extract_job")
                        except Exception as de:
                            print(f"[ATS DEBUG] ⚠️ Failed to save diagnostic capture: {de}")
                        # --------------------------

                    if apply_buttons:
                        btn = apply_buttons[0]
                        redir_url = btn.get_attribute("href")
                        
                        if redir_url:
                            apply_url = decode_linkedin_redir(redir_url)
                            print(f"[ATS DEBUG] ✅ Decoded URL from href: {apply_url}")
                            logger.info(f"✨ Captured ATS link: {apply_url[:60]}...", step="extract_job")
                        else:
                            print(f"[ATS DEBUG] → CASE 3: No href — will CLICK the button")
                            logger.info(f"🖱️ Clicking 'Apply' button to capture ATS link...", step="extract_job")
                            
                            try:
                                original_window = self.browser.current_window_handle
                                original_url = self.browser.current_url
                                print(f"[ATS DEBUG]   Original URL: {original_url}")
                            except Exception as ee:
                                print(f"[ATS DEBUG] ❌ Failed to get window handles: {ee}")
                                raise ee
                            
                            success = False
                            # Try all buttons found if the first one doesn't work
                            for i, candidate_btn in enumerate(apply_buttons):
                                print(f"[ATS DEBUG]   --- Click Attempt on button {i+1}/{len(apply_buttons)} ---")
                                
                                # We try two ways for each button: JS click and Native click
                                for method in ["JS", "Native"]:
                                    try:
                                        print(f"[ATS DEBUG]   Method: {method} click...")
                                        if method == "JS":
                                            self.browser.execute_script("arguments[0].click();", candidate_btn)
                                        else:
                                            candidate_btn.click()
                                        
                                        time.sleep(4)
                                        
                                        handles = self.browser.window_handles
                                        if len(handles) > 1:
                                            self.browser.switch_to.window(handles[1])
                                            apply_url = self.browser.current_url
                                            logger.info(f"✨ Captured ATS link (new tab): {apply_url[:60]}...", step="extract_job")
                                            print(f"[ATS DEBUG]   ✅ SUCCESS (New Tab): {apply_url}")
                                            self.browser.close()
                                            self.browser.switch_to.window(original_window)
                                            success = True
                                            break
                                        elif self.browser.current_url != original_url and "linkedin.com" not in self.browser.current_url:
                                            apply_url = self.browser.current_url
                                            logger.info(f"✨ Captured ATS link (same tab): {apply_url[:60]}...", step="extract_job")
                                            print(f"[ATS DEBUG]   ✅ SUCCESS (Same Tab): {apply_url}")
                                            self.browser.back()
                                            time.sleep(3)
                                            success = True
                                            break
                                    except Exception as ce:
                                        print(f"[ATS DEBUG]   {method} click failed: {ce}")
                                        try: self.browser.switch_to.window(original_window)
                                        except: pass
                                
                                if success: break

                            if not success:
                                print(f"[ATS DEBUG]   ⚠️ All click attempts failed.")
                                logger.warning("Tried clicking Apply but could not capture external URL.", step="extract_job")
                                apply_url = linkedin_url
                                
                                # --- Click Failure Diagnostic Capture ---
                                try:
                                    debug_dir = os.path.join("logs", "debug")
                                    os.makedirs(debug_dir, exist_ok=True)
                                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    screenshot_path = os.path.join(debug_dir, f"click_failed_{job_id}_{timestamp}.png")
                                    self.browser.save_screenshot(screenshot_path)
                                    html_path = os.path.join(debug_dir, f"click_failed_{job_id}_{timestamp}.html")
                                    with open(html_path, "w", encoding="utf-8") as f:
                                        f.write(self.browser.page_source)
                                    print(f"[ATS DEBUG] 📸 Click failure diagnostic saved to {debug_dir}")
                                except Exception: pass
                                 # ----------------------------------------
                    
                    print(f"[ATS DEBUG] Final Apply URL: {apply_url}")
                    print(f"[ATS DEBUG] ─────────────────────────────────────────\n")

                except Exception as e:
                    print(f"[ATS DEBUG] ❌ EXCEPTION in ATS extraction: {e}")
                    logger.debug(f"Failed to extract external apply link: {e}")
            # --- End: ATS Link Extraction ---

            # Database Save - url column stores LinkedIn URL, apply_url column stores ATS/Final URL
            self.store.con.execute(
                 "INSERT OR REPLACE INTO extracted_jobs (id, job_id, url, apply_url, title, company, location, date_extracted, candidate_id, is_easy_apply) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)",
                 [job_id, job_id, linkedin_url, apply_url, title, company, location, self.candidate_id, is_easy_apply]
             )
            self.store.con.commit()
             
            # CSV Save
            if self.csv_path:
                with open(self.csv_path, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f, quoting=csv.QUOTE_NONNUMERIC)
                    # format: source_job_id, title, company, location, zipcode, linkedin_url, apply_url, date_extracted, is_non_easy_apply
                    writer.writerow([job_id, title, company, location, zipcode, linkedin_url, apply_url, time.strftime('%Y-%m-%d %H:%M:%S'), not is_easy_apply])
                
            # API Save (Remote)
            job_data = {
                'title': title,
                'company': company,
                'location': location,
                'zipcode': zipcode,
                'url': linkedin_url,
                'apply_url': apply_url,
                'source_job_id': job_id,
                'is_easy_apply': is_easy_apply
            }
            if self.api_store:
                # Accumulate in the shared api_store buffer
                self.api_store.batch_buffer.append(job_data)
                logger.info(f"📥 Queued for bulk insert (buffer size: {len(self.api_store.batch_buffer)})", step="extract_job")
                
            # MySQL Save (Direct Database)
            if hasattr(self, 'mysql_store') and self.mysql_store:
                self.mysql_store.insert_position(job_data)
            
            logger.info(f"Saved job: {title} at {company} ({location})", step="extract_job")
                
        except Exception as e:
             logger.debug(f"Failed to save job {job_id}: {e}")


