import os
import logging
import platform
import undetected_chromedriver as uc
from selenium_stealth import stealth
from selenium.webdriver.chrome.options import Options


log = logging.getLogger(__name__)

class Browser:
    def __init__(self, profile_path=None, proxy_config=None):
        self.profile_path = profile_path
        self.proxy_config = proxy_config
        self.driver = self._setup_driver()

    def _setup_driver(self):
        options = uc.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        
        # Profile handling
        if self.profile_path:
             abs_profile_path = os.path.abspath(self.profile_path)
             log.info(f"Using absolute profile path: {abs_profile_path}")
             # Ensure the parent directory exists
             os.makedirs(os.path.dirname(abs_profile_path), exist_ok=True)
             options.add_argument(f'--user-data-dir={abs_profile_path}')
        else:
             log.info("Using guest mode")
             options.add_argument('--guest')
        
        # Proxy handling
        if self.proxy_config:
            proxy_string = self.proxy_config.get_chrome_proxy_string()
            options.add_argument(f'--proxy-server={proxy_string}')
            log.info(f"Using proxy: {self.proxy_config.name}")

        try:
            # Let undetected-chromedriver auto-detect the installed Chrome version
            # This avoids hard failures when Chrome updates.
            driver = uc.Chrome(options=options)
            log.info("Chrome initialized successfully")
        except Exception as e:
            log.error(f"Failed to initialize undetected-chromedriver: {e}")
            raise e
        
        # Apply stealth settings
        # Determine platform string for stealth match
        system_name = platform.system()
        stealth_platform = "Win32" # Default fallback
        if system_name == 'Darwin':
            stealth_platform = "MacIntel"
        elif system_name == 'Linux':
            stealth_platform = "Linux x86_64"
            
        stealth(driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform=stealth_platform,
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )
        
        return driver


