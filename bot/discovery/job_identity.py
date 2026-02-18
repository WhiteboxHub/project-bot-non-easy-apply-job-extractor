from selenium.webdriver.common.by import By
from bot.utils.logger import logger
import re

class JobIdentity:
    @staticmethod
    def extract_job_id(element):
        """
        Extracts job ID from a job card element.
        Tries 'data-job-id' attribute explicitly.
        """
        try:
            # Primary: explicit attribute set on many LinkedIn job cards
            job_id = element.get_attribute("data-job-id")
            if job_id:
                return job_id

            # Fallback 1: href may contain '/view/<job_id>' or query param 'currentJobId'
            href = element.get_attribute("href") or element.get_attribute("data-href") or ""
            if href:
                # Try common patterns
                m = re.search(r"/view/(\d+)", href)
                if m:
                    return m.group(1)
                m = re.search(r"currentJobId=(\d+)", href)
                if m:
                    return m.group(1)

            # Fallback 2: sometimes an inner anchor contains the href
            try:
                anchors = element.find_elements(By.TAG_NAME, 'a')
                for a in anchors:
                    ahref = a.get_attribute('href') or ''
                    if ahref:
                        m = re.search(r"/view/(\d+)", ahref)
                        if m:
                            return m.group(1)
                        m = re.search(r"currentJobId=(\d+)", ahref)
                        if m:
                            return m.group(1)
            except Exception:
                pass

            # If all fail, return None so caller can skip
            return None
        except Exception as e:
            logger.debug(f"Failed to extract job ID: {e}", step="extract_job_id")
            return None
