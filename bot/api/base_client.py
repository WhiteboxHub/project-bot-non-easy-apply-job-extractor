"""
Shared API client for Whitebox Learning platform.
Handles base URL, auth headers, and HTTP helpers.
"""

import os
import logging
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)


class BaseAPIClient:
    """Common API client using API_TOKEN + SECRET_KEY authentication."""

    def __init__(self, base_url: Optional[str] = None):
        raw_base_url = base_url or os.getenv("WBL_API_URL", "https://api.whitebox-learning.com/api")
        self.base_url = raw_base_url.rstrip("/")
        self.api_token = (os.getenv("API_TOKEN") or "").strip()
        self.secret_key = (os.getenv("SECRET_KEY") or "").strip()
        self.api_email = (os.getenv("API_EMAIL") or "").strip()
        self.api_password = (os.getenv("API_PASSWORD") or "").strip()
        self.login_endpoint = os.getenv("API_LOGIN_ENDPOINT", "/api/login").strip() or "/api/login"

        if not self.secret_key:
            logger.error("❌ CRITICAL: SECRET_KEY missing in .env file!")
            logger.error("Missing: SECRET_KEY")

        if not self.api_token and not (self.api_email and self.api_password):
            logger.error("❌ CRITICAL: API_TOKEN missing and no API_EMAIL/API_PASSWORD provided!")
            logger.error("Provide API_TOKEN or API_EMAIL/API_PASSWORD in .env")

    def build_url(self, endpoint: str) -> str:
        base = self.base_url.rstrip("/") + "/"
        path = endpoint.lstrip("/")
        return base + path

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "X-Secret-Key": self.secret_key,
            "Content-Type": "application/json",
        }

    def _authenticate(self) -> bool:
        """Authenticate using OAuth2PasswordRequestForm to fetch a fresh access token."""
        if not (self.api_email and self.api_password):
            logger.error("API_EMAIL/API_PASSWORD not set; cannot authenticate.")
            return False

        login_url = self.build_url(self.login_endpoint)
        form_data = {
            "username": self.api_email,
            "password": self.api_password,
            "grant_type": "password",
        }

        try:
            response = requests.post(login_url, data=form_data, timeout=15)
            if response.status_code != 200:
                logger.error(f"Login failed with status {response.status_code}")
                logger.error(f"Response: {response.text}")
                return False

            data = response.json()
            token = data.get("access_token")
            if not token:
                logger.error("No access_token in login response")
                logger.error(f"Response data: {data}")
                return False

            self.api_token = token
            logger.info("✅ Successfully authenticated via /login")
            return True
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False

    def _request_with_retry(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make a request and re-authenticate once on 401/403."""
        if not self.api_token and (self.api_email and self.api_password):
            self._authenticate()

        url = self.build_url(endpoint)
        headers = self._headers()
        response = requests.request(method, url, headers=headers, **kwargs)

        if response.status_code in [401, 403] and (self.api_email and self.api_password):
            logger.warning("Auth failed; attempting re-authentication...")
            if self._authenticate():
                headers = self._headers()
                response = requests.request(method, url, headers=headers, **kwargs)

        return response

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None, timeout: int = 10) -> requests.Response:
        return self._request_with_retry("GET", endpoint, params=params, timeout=timeout)

    def post(self, endpoint: str, json: Optional[Dict[str, Any]] = None, timeout: int = 15) -> requests.Response:
        return self._request_with_retry("POST", endpoint, json=json, timeout=timeout)

    def put(self, endpoint: str, json: Optional[Dict[str, Any]] = None, timeout: int = 15) -> requests.Response:
        return self._request_with_retry("PUT", endpoint, json=json, timeout=timeout)

    def delete(self, endpoint: str, timeout: int = 15) -> requests.Response:
        return self._request_with_retry("DELETE", endpoint, timeout=timeout)
