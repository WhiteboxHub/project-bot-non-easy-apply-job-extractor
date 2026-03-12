from selenium.webdriver.common.by import By
from bot.utils.logger import logger
from bot.utils.selector_helpers import get_locator
import re

class JobIdentity:
    @staticmethod
    def extract_job_id(element):
        """
        Extracts job ID from a job card element.
        Tries 'data-job-id' attribute, then href patterns (view/ID, currentJobId=ID, or dash-suffix).
        """
        try:
            # 1. Primary: Explicit attribute
            job_id = element.get_attribute("data-job-id")
            if job_id and job_id.isdigit():
                return job_id

            # 2. Check inner text for clues if ID is missing (sometimes ID is in a nested data attr)
            # but usually href is the best secondary source
            hrefs = []
            
            # Direct href on the element itself
            h = element.get_attribute("href") or element.get_attribute("data-href")
            if h: hrefs.append(h)
            
            # Hrefs on child anchors
            anchors = element.find_elements(By.TAG_NAME, "a")
            for a in anchors:
                h = a.get_attribute("href")
                if h: hrefs.append(h)

            for href in hrefs:
                # Pattern A: /view/12345
                m = re.search(r"/view/(\d+)", href)
                if m: return m.group(1)
                
                # Pattern B: currentJobId=12345
                m = re.search(r"currentJobId=(\d+)", href)
                if m: return m.group(1)
                
                # Pattern C: Guest Mode dash-suffix (e.g., ...-at-company-12345678)
                # Matches digits at the end of the URL path before query params
                path = href.split('?')[0]
                m = re.search(r"-(\d+)$", path)
                if m: return m.group(1)

            return None
        except Exception as e:
            logger.debug(f"Failed to extract job ID: {e}", step="extract_job_id")
            return None
