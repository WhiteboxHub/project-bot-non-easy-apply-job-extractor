from selenium.webdriver.common.by import By

# Enhanced selector registry with fallback support
# Each selector can have a primary and optional fallback locator

LOCATORS = {
    "next": {
        "primary": (By.CSS_SELECTOR, "button[aria-label='Continue to next step']"),
        "fallback": (By.XPATH, "//button[contains(text(), 'Next') or contains(text(), 'Continue')]")
    },
    
    "review": {
        "primary": (By.CSS_SELECTOR, "button[aria-label='Review your application']"),
        "fallback": (By.XPATH, "//button[contains(text(), 'Review')]")
    },
    
    "submit": {
        "primary": (By.CSS_SELECTOR, "button[aria-label='Submit application']"),
        "fallback": (By.XPATH, "//button[contains(text(), 'Submit')]")
    },
    
    "error": {
        "primary": (By.CLASS_NAME, "artdeco-inline-feedback__message"),
        "fallback": (By.CSS_SELECTOR, ".artdeco-inline-feedback")
    },
    
    "upload_resume": {
        "primary": (By.XPATH, "//*[contains(@id, 'jobs-document-upload-file-input-upload-resume')]"),
        "fallback": (By.CSS_SELECTOR, "input[type='file'][id*='resume']")
    },
    
    "upload_cv": {
        "primary": (By.XPATH, "//*[contains(@id, 'jobs-document-upload-file-input-upload-cover-letter')]"),
        "fallback": (By.CSS_SELECTOR, "input[type='file'][id*='cover']")
    },
    
    "follow": {
        "primary": (By.CSS_SELECTOR, "label[for='follow-company-checkbox']"),
        "fallback": (By.XPATH, "//label[contains(text(), 'Follow')]")
    },
    
    "upload": {
        "primary": (By.NAME, "file"),
        "fallback": (By.CSS_SELECTOR, "input[type='file']")
    },
    
    "search": {
        "primary": (By.CLASS_NAME, "jobs-search-results-list"),
        "fallback": (By.XPATH, "//div[contains(@class, 'jobs-search-results-list')]")
    },
    
    "links": {
        "primary": (By.XPATH, "//div[contains(@class, 'job-card-container') or @data-job-id]"),
        "fallback": (By.CSS_SELECTOR, ".job-card-list__entity-lockup")
    },
    
    "fields": {
        "primary": (By.CLASS_NAME, "jobs-easy-apply-form-section__grouping"),
        "fallback": (By.CSS_SELECTOR, ".jobs-easy-apply-form-element")
    },
    
    "radio_select": {
        "primary": (By.CSS_SELECTOR, "input[type='radio']"),
        "fallback": (By.XPATH, "//input[@type='radio']")
    },
    
    "multi_select": {
        "primary": (By.XPATH, "//*[contains(@id, 'text-entity-list-form-component')]"),
        "fallback": (By.CSS_SELECTOR, "[id*='text-entity-list']")
    },
    
    "text_select": {
        "primary": (By.CLASS_NAME, "artdeco-text-input--input"),
        "fallback": (By.CSS_SELECTOR, "input[type='text']")
    },
    
    "2fa_oneClick": {
        "primary": (By.ID, 'reset-password-submit-button'),
        "fallback": (By.CSS_SELECTOR, "button[type='submit']")
    },
    
    "easy_apply_button": {
        "primary": (By.XPATH, '//button[contains(@class, "jobs-apply-button")]'),
        "fallback": (By.CSS_SELECTOR, "button[aria-label*='Easy Apply']")
    },
    
    "company": {
        "primary": (By.CSS_SELECTOR, ".job-card-container__primary-description, .job-card-list__entity-lockup_subtitle, .artdeco-entity-lockup__subtitle"),
        "fallback": (By.CSS_SELECTOR, ".job-card-container__company-name, .job-card-list__company-name, [class*='company-name']")
    },
    
    "location": {
        "primary": (By.CSS_SELECTOR, ".job-card-container__metadata-item, .job-card-container__metadata-wrapper, .artdeco-entity-lockup__caption"),
        "fallback": (By.CSS_SELECTOR, ".job-card-container__location, .job-card-list__metadata-item")
    },
    
    "external_apply_button": {
        "primary": (By.XPATH, "//a[contains(@href, 'redir/redirect')] | //a[contains(@aria-label, 'Apply on company website')]"),
        "fallback": (By.XPATH, "//button[contains(@aria-label, 'Apply') and not(contains(@aria-label, 'filter'))] | //a[contains(@aria-label, 'Apply') and not(contains(@aria-label, 'filter'))] | //button[.//span[text()='Apply']] | //a[.//span[text()='Apply']] | //button[@id='jobs-apply-button-id']")
    },

    "all_filters_button": {
        "primary": (By.XPATH, "//button[contains(@class, 'search-reusables__all-filters-pill-button')]"),
        "fallback": (By.XPATH, "//button[contains(@aria-label, 'All filters') or contains(text(), 'All filters')]")
    },

    "title_filter_labels": {
        # Scoped to the Title section container only — tries fieldset, section, li containers with a 'Title' heading
        "primary": (By.XPATH,
            "//fieldset[.//legend[normalize-space(text())='Title']]//label"
            " | //fieldset[.//h3[normalize-space(text())='Title']]//label"
            " | //section[.//h3[normalize-space(text())='Title']]//label"
            " | //li[.//h3[normalize-space(text())='Title']]//label"
        ),
        "fallback": (By.XPATH, "//div[contains(@class, 'artdeco-modal')]//label")
    },

    "all_filters_show_results": {
        "primary": (By.XPATH, "//button[contains(@aria-label, 'Apply current filters') or contains(@data-control-name, 'all_filters_apply')]"),
        "fallback": (By.XPATH, "//span[contains(text(), 'Show') and contains(text(), 'results')]/ancestor::button")
    },

    "modal_dismiss": {
        "primary": (By.XPATH, "//button[contains(@class, 'artdeco-modal__dismiss')]"),
        "fallback": (By.XPATH, "//button[contains(@aria-label, 'Dismiss')]")
    }
}


def get_locator(key: str, use_fallback: bool = False):
    """
    Get a locator by key, optionally returning the fallback.
    
    Args:
        key: The selector key
        use_fallback: If True, return fallback locator if available
    
    Returns:
        Tuple of (By, selector) or the original value if not dict
    """
    locator = LOCATORS.get(key)
    
    if not locator:
        return None
    
    # If it's a dict with primary/fallback
    if isinstance(locator, dict):
        if use_fallback and "fallback" in locator:
            return locator["fallback"]
        return locator.get("primary", locator.get("fallback"))
    
    # Legacy format (direct tuple)
    return locator


def has_fallback(key: str) -> bool:
    """Check if a selector has a fallback defined"""
    locator = LOCATORS.get(key)
    return isinstance(locator, dict) and "fallback" in locator
