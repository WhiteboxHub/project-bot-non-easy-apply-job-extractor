import time
import os
import sys

# Add project root to path so 'bot' can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from selenium.webdriver.common.by import By
from bot.core.browser import Browser
from bot.utils.selectors import LOCATORS

def debug_selectors(job_url):
    print(f"--- Debugging Selectors for: {job_url} ---")
    
    profile_path = os.path.join(os.getcwd(), "data", "profiles", "debug_profile")
    browser = Browser(profile_path=profile_path)
    driver = browser.driver
    
    try:
        driver.get(job_url)
        print("Waiting 10 seconds for page to fully load...")
        time.sleep(10)
        
        # Test the external apply selector
        selector = LOCATORS["external_apply_button"]
        primary = selector["primary"]
        
        print(f"Testing primary: {primary}")
        elems = driver.find_elements(*primary)
        print(f"Found {len(elems)} elements with primary.")
        
        # Search for ANY links that look like LinkedIn Redirects
        print("Searching for ALL links containing 'redir/redirect'...")
        redir_links = driver.find_elements(By.XPATH, "//a[contains(@href, 'redir/redirect')]")
        print(f"Found {len(redir_links)} links with 'redir/redirect'.")
        for i, e in enumerate(redir_links):
            print(f"  [{i}] Text: {e.text.strip()}, Href: {e.get_attribute('href')}")

        if all_apply:
            print("\n--- Testing 'Click to Capture' ---")
            target = all_apply[1] if len(all_apply) > 1 else all_apply[0]
            print(f"Clicking element: {target.tag_name} (Text: {target.text.strip()})")
            
            # Store current handle
            original_window = driver.current_window_handle
            
            # Click it
            driver.execute_script("arguments[0].click();", target)
            time.sleep(5) # Wait for redirect/new tab
            
            # Check for new windows
            handles = driver.window_handles
            if len(handles) > 1:
                driver.switch_to.window(handles[1])
                external_url = driver.current_url
                print(f"SUCCESS! New tab URL: {external_url}")
                driver.close()
                driver.switch_to.window(original_window)
            else:
                print(f"No new tab. Current URL: {driver.current_url}")

    except Exception as e:
        print(f"Error during debug: {e}")
    finally:
        print("Debug finished. Keeping browser open for 30 seconds for manual inspection...")
        time.sleep(30)
        driver.quit()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        print("Usage: python scripts/debug_selectors.py <JOB_URL>")
        sys.exit(1)
        
    debug_selectors(url)
