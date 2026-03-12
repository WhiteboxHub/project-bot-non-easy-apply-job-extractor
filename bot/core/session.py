import time
from bot.utils.logger import logger

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException
from bot.utils.selector_helpers import get_locator



class Session:
    def __init__(self, browser):
        self.browser = browser

    def login(self, username, password):
        logger.info("Checking login status...", step="login", event="start")
        # First go to homepage to see if session is active
        self.browser.get("https://www.linkedin.com/feed/")
        time.sleep(3)
        
        if "feed" in self.browser.current_url:
             logger.info("Already logged in.", step="login", event="success")
             return

        logger.info("Not logged in, navigating to login page...", step="login")
        self.browser.get("https://www.linkedin.com/login?trk=guest_homepage-basic_nav-header-signin")
        
        try:
            # Check if we are already logged in (redirected)
            if "feed" in self.browser.current_url:
                logger.info("Already logged in.", step="login", event="success")
                return

            if not username or not password:
                logger.warning("No credentials provided and not logged in.", step="login")
                logger.info("Please log in manually in the browser window now. Waiting 60 seconds...", step="login")
                time.sleep(60)
                if "feed" in self.browser.current_url:
                     logger.info("Manual login successful!", step="login", event="success")
                     return
                else:
                     logger.error("Manual login failed or timed out.", step="login", event="failure")
                     return

            user_field_loc = get_locator("login_username")
            user_field = self.browser.find_element(*user_field_loc)
            
            pw_field_loc = get_locator("login_password")
            pw_field = self.browser.find_element(*pw_field_loc)
            
            login_btn_loc = get_locator("login_submit")
            login_button = self.browser.find_element(*login_btn_loc)
            
            user_field.send_keys(username)
            user_field.send_keys(Keys.TAB)
            time.sleep(2)
            pw_field.send_keys(password)
            time.sleep(2)
            login_button.click()
            time.sleep(15)
        except TimeoutException:
            logger.info("TimeoutException! Username/password field or login button not found", step="login", event="failure", exception_type="TimeoutException")
        except Exception as e:
            # If we fail here, we might actually be logged in or facing a captcha
            if "feed" in self.browser.current_url or "checkpoint" in self.browser.current_url:
                 logger.warning(f"Login interrupted but might be okay or captcha: {e}")
            else:
                 logger.error(f"Login failed: {e}", step="login", event="failure", exception=e)

        # Post-login verification
        logger.info("Validating login state...", step="login")
        current_url = self.browser.current_url
        page_title = self.browser.title
        
        if "feed" in current_url:
            logger.info("Login confirmed! Redirected to feed.", step="login", event="success")
            return

        if "checkpoint" in current_url or "challenge" in current_url:
            logger.warning("Login found security checkpoint/captcha. Please handle manually in the browser if visible.", step="login", event="challenge")
            return
            
        # Check for common error messages
        try:
            # Typical LinkedIn error IDs
            error_msg = ""
            try: 
                error_elem = self.browser.find_element(*get_locator("login_error_password"))
                error_msg = f"Password Error: {error_elem.text}"
            except: pass
            
            if not error_msg:
                try: 
                    error_elem = self.browser.find_element(*get_locator("login_error_username"))
                    error_msg = f"Username Error: {error_elem.text}"
                except: pass

            if not error_msg:
                 # Check for alert-content or similar
                 try:
                     alert = self.browser.find_element(*get_locator("login_alert"))
                     error_msg = f"Alert: {alert.text}"
                 except: pass

            if error_msg:
                logger.error(f"Login failed with message: {error_msg}", step="login", event="failure")
            else:
                logger.error(f"Login flow finished but not on feed. Current URL: {current_url} | Title: {page_title}. Possible captcha or unknown error.", step="login", event="failure")
                
        except Exception as e:
            logger.error(f"Error checking login status: {e}")


