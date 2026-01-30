"""API module for external integrations"""

from .website_client import WebsiteAPIClient, fetch_candidates_from_api

__all__ = ['WebsiteAPIClient', 'fetch_candidates_from_api']
