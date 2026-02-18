import time
import random
import logging
import os
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

LINKEDIN_BASE_URL = os.getenv("LINKEDIN_BASE_URL", "https://www.linkedin.com")

# from bot.application.workflow import Workflow
from bot.utils.delays import sleep_random
from bot.utils.selectors import LOCATORS
from bot.utils.selectors import LOCATORS
from bot.utils.logger import logger
from bot.utils.retry import retry
from bot.utils.stale_guard import safe_action
from bot.discovery.job_identity import JobIdentity
from bot.discovery.scroll_tracker import ScrollTracker
from bot.utils.human_interaction import HumanInteraction




class Search:
    def __init__(self, browser, workflow=None, blacklist=None, experience_level=None, phone_number=None):
        self.browser = browser.driver
        self.workflow = workflow
        self.blacklist = blacklist or []
        self.experience_level = experience_level or []
        self.locator = LOCATORS
        self.MAX_SEARCH_TIME = 60 * 60
        self.phone_number = phone_number

    def start_apply(self, positions, locations):
        # self.fill_data() # window positioning logic?
        combos = []
        while len(combos) < len(positions) * len(locations):
            position = positions[random.randint(0, len(positions) - 1)]
            location = locations[random.randint(0, len(locations) - 1)]
            combo = (position, location)
            if combo not in combos:
                combos.append(combo)
                logger.info(f"Applying to {position}: {location}", step="search_init")
                location_param = "&location=" + location

                self.applications_loop(position, location_param)
            if len(combos) > 500:
                break

    def applications_loop(self, position, location):
        jobs_per_page = 0
        start_time = time.time()
        scroll_tracker = ScrollTracker(self.browser)
        human = HumanInteraction(self.browser)

        logger.info("Looking for jobs.. Please wait..", step="job_search", event="start")

        # self.browser.maximize_window() # handled in setup
        
        self.next_jobs_page(position, location, jobs_per_page)
        logger.info("Looking for jobs.. Please wait..", step="job_search", event="page_loaded")

        while time.time() - start_time < self.MAX_SEARCH_TIME:
            try:
                logger.info(f"{(self.MAX_SEARCH_TIME - (time.time() - start_time)) // 60} minutes left in this search", step="job_search", event="timer")
                sleep_random()

                # Robust page load / scroll
                # self.load_page(sleep=0.5) # Using robust scroll tracking instead below

                if self.is_present(self.locator["search"]):
                    scrollresults = self.get_elements("search")
                    
                    # Scroll logic with stale guard if needed, but here we just scroll the container
                    # We might need to re-find 'scrollresults' if it becomes stale?
                    # Let's try to scroll efficiently.
                    
                    current_height = self.browser.execute_script("return arguments[0].scrollHeight", scrollresults[0])
                    
                    # Scroll down
                    for i in range(300, current_height, 300):
                         # self.browser.execute_script("arguments[0].scrollTo(0, {})".format(i), scrollresults[0])
                         # time.sleep(0.1)
                         # Use human scroll element instead
                         human.scroll_element(scrollresults[0])


                    if not scroll_tracker.update_scroll(current_height):
                        if scroll_tracker.should_stop():
                            logger.warning("Scroll limits reached, moving to next page", step="job_search", event="scroll_stop")
                            jobs_per_page = self.next_jobs_page(position, location, jobs_per_page)
                            continue
                
                # Extract jobs with JobIdentity
                if self.is_present(self.locator["links"]):
                    # Safe action wrap for getting elements? 
                    # Usually find_elements is safe, but iterating them is where risk is.
                    # We will re-query the list or iterate carefully.
                    
                    links = self.get_elements("links")
                    
                    for link in links:
                        # Use Stale Guard for text check or attribute get
                        try:
                             # We can use safe_action but it expects a function + locator. 
                             # Here we have an element object. safe_action is for finding + acting.
                             # For list iteration, we just need try/except stale continue or re-fetch.
                             
                             job_id = JobIdentity.extract_job_id(link)
                             if job_id and not scroll_tracker.is_processed(job_id):
                                 if 'Applied' not in link.text:
                                     if link.text not in self.blacklist:
                                         logger.info(f"Found new job: {job_id}", step="job_search", event="found_job")
                                         self.workflow.apply_to_job(job_id, self.phone_number)
                                         scroll_tracker.add_job(job_id)
                                     else:
                                         scroll_tracker.add_job(job_id) # Blacklisted but processed
                                 else:
                                     scroll_tracker.add_job(job_id) # Already applied
                        except Exception as e:
                             logger.warning(f"Error processing job card: {e}", step="job_search", event="card_error")
                             continue
                    
                    # Pagination happens if we are done with current view or stuck
                    # The outer loop and scroll tracker help decide. 
                    # If we processed all visible jobs and scroll is stuck, next page.
                    
                    if scroll_tracker.should_stop(): # We check again or rely on the scroll block above
                         jobs_per_page = self.next_jobs_page(position, location, jobs_per_page)

                else:
                    jobs_per_page = self.next_jobs_page(position, location, jobs_per_page)

            except Exception as e:
                logger.error(f"Search loop error: {e}", step="job_search", event="error", exception=e)
                break



    @retry(max_attempts=3, delay=1)
    def next_jobs_page(self, position, location, jobs_per_page):
        experience_level_str = ",".join(map(str, self.experience_level)) if self.experience_level else ""
        experience_level_param = f"&f_E={experience_level_str}" if experience_level_str else ""
        
        url = (f"{LINKEDIN_BASE_URL}/jobs/search/?f_LF=f_AL&keywords=" +
               position + location + "&start=" + str(jobs_per_page) + experience_level_param)
        
        self.browser.get(url)
        # log.info("Loading next job page?")
        self.load_page()
        return jobs_per_page + 25

    @retry(max_attempts=3, delay=1)
    def load_page(self, sleep=1):
        scroll_page = 0
        while scroll_page < 4000:
            self.browser.execute_script("window.scrollTo(0," + str(scroll_page) + " );")
            scroll_page += 500
            time.sleep(sleep)

        if sleep != 1:
            self.browser.execute_script("window.scrollTo(0,0);")
            time.sleep(sleep)

        return BeautifulSoup(self.browser.page_source, "lxml")


    def get_elements(self, type) -> list:
        elements = []
        element = self.locator[type]
        
        # Handle new selector format with primary/fallback
        if isinstance(element, dict):
            element = element.get('primary', element.get('fallback'))
        
        if self.is_present(element):
            elements = self.browser.find_elements(element[0], element[1])
        return elements

    def is_present(self, locator):
        # Handle new selector format with primary/fallback
        if isinstance(locator, dict):
            locator = locator.get('primary', locator.get('fallback'))
        
        return len(self.browser.find_elements(locator[0], locator[1])) > 0
