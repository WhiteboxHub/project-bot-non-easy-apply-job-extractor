from urllib.parse import urlparse, parse_qs, unquote

def decode_linkedin_redir(redir_url):
    """
    Decodes LinkedIn redirect URLs to get the actual target ATS link.
    If the URL is not a LinkedIn redirect, it returns it as-is.
    """
    if not redir_url or not isinstance(redir_url, str):
        return redir_url
        
    if "linkedin.com/redir/redirect" in redir_url:
        try:
            parsed = urlparse(redir_url)
            queries = parse_qs(parsed.query)
            if 'url' in queries:
                ats_link = queries['url'][0]
                return unquote(ats_link)
        except Exception:
            pass
    return redir_url

KNOWN_ATS_DOMAINS = [
    "greenhouse.io", "lever.co", "myworkdayjobs.com", "ashbyhq.com", 
    "bamboohr.com", "smartrecruiters.com", "icims.com", "workable.com", 
    "breezy.hr", "gohiresolutions.com", "taleo.net"
]

def get_job_url_type(apply_url: str, is_easy_apply: bool) -> str:
    """
    Categorizes the exact type of URL that was extracted.
    """
    if is_easy_apply:
        return "Easy Apply"
    
    if not apply_url:
        return "Unknown"
        
    try:
        parsed = urlparse(apply_url)
        domain = parsed.netloc.lower()
        
        # Check if it's a known ATS
        for ats in KNOWN_ATS_DOMAINS:
            if ats in domain:
                return "ATS"
                
        # If it's a standard LinkedIn link but not easy apply
        if "linkedin.com" in domain:
            if "/jobs/view" in apply_url or "/jobs/collections" in apply_url:
                 return "LinkedIn Login Required"
            return "LinkedIn Login Required"
            
        return "Company Website"
        
    except Exception:
        return "Unknown"
