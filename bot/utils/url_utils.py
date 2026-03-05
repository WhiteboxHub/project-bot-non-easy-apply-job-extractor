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
