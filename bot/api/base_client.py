"""
Shared API client for Whitebox Learning platform.
Handles base URL, auth headers, and HTTP helpers.
"""

import os
import logging
from typing import Any, Dict, Optional

import requests
import json
import time
import sys
import getpass

logger = logging.getLogger(__name__)


class BaseAPIClient:
    """Common API client using API_TOKEN + SECRET_KEY authentication."""

    def __init__(self, base_url: Optional[str] = None):
        # Allow easy local testing: if USE_LOCAL_API is set to true, prefer
        # LOCAL_WBL_API_URL (defaulting to http://localhost:8000/api).
        use_local = os.getenv("USE_LOCAL_API", "false").lower() == "true"
        if use_local:
            raw_base_url = base_url or os.getenv("LOCAL_WBL_API_URL", "http://localhost:8000/api")
            logging.info(f"Using local API for testing: {raw_base_url}")
        else:
            raw_base_url = base_url or os.getenv("WBL_API_URL", "https://api.whitebox-learning.com/api")
        self.base_url = raw_base_url.rstrip("/")
        self.api_token = (os.getenv("API_TOKEN") or "").strip()
        self.token_expiry = None
        self.secret_key = (os.getenv("SECRET_KEY") or "").strip()
        self.api_email = (os.getenv("API_EMAIL") or "").strip()
        self.api_password = (os.getenv("API_PASSWORD") or "").strip()
        # Normalize login endpoint: avoid duplicated '/api' when base_url already
        # ends with '/api'. Accepts env var like '/api/login' or 'api/login' or 'login'.
        login_endpoint_raw = os.getenv("API_LOGIN_ENDPOINT", "/api/login") or "/api/login"
        login_endpoint = str(login_endpoint_raw).strip()
        # Remove any leading slash so build_url can join cleanly
        login_endpoint = login_endpoint.lstrip('/')
        # If base already ends with 'api' and endpoint starts with 'api/', strip it
        if self.base_url.endswith('/api') and login_endpoint.startswith('api/'):
            login_endpoint = login_endpoint[len('api/') :]
        # Fallback
        self.login_endpoint = login_endpoint or 'login'

        if not self.secret_key:
            logger.error("❌ CRITICAL: SECRET_KEY missing in .env file!")
            logger.error("Missing: SECRET_KEY")

        if not self.api_token and not (self.api_email and self.api_password):
            logger.error("❌ CRITICAL: API_TOKEN missing and no API_EMAIL/API_PASSWORD provided!")
            logger.error("Provide API_TOKEN or API_EMAIL/API_PASSWORD in .env")

        # Try loading a locally saved token (persisted from prior successful auth)
        try:
            self._load_saved_token()
        except Exception:
            # Non-fatal; we'll rely on env vars or auth flow
            pass

        # If there's no token and no credentials in env, prompt interactively
        # only when running in an interactive terminal (TTY). We will not
        # persist the credentials, only the token is saved to
        # `data/.api_token.json` via `_save_token`.
        if not self.api_token and not (self.api_email and self.api_password):
            try:
                if sys.stdin and sys.stdin.isatty():
                    logger.info("No API token or credentials found in environment. Prompting for API credentials...")
                    self._prompt_for_credentials()
                else:
                    logger.info("Non-interactive environment: skipping credential prompt.")
            except Exception:
                # If anything goes wrong with prompting, skip and allow caller to handle auth
                logger.debug("Interactive prompt skipped due to non-interactive environment or error.")

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
            # If API returned expiry info, persist it. Typical keys: expires_in (seconds)
            expires_in = data.get("expires_in")
            expiry_ts = None
            if isinstance(expires_in, (int, float)):
                expiry_ts = int(time.time()) + int(expires_in)
                # store in-memory expiry for future checks
                self.token_expiry = expiry_ts

            try:
                self._save_token(token, expiry_ts)
            except Exception:
                # Non-fatal; token is still in-memory
                pass

            logger.info("✅ Successfully authenticated via /login")
            return True
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False

    def _prompt_for_credentials(self) -> bool:
        """Prompt the user for `API_EMAIL` and `API_PASSWORD` interactively.

        Returns True if authentication succeeded and token saved, False otherwise.
        """
        try:
            email = input("API Email (will not be saved): ").strip()
            if not email:
                logger.info("No email entered; skipping authentication prompt.")
                return False
            pwd = getpass.getpass("API Password (input hidden): ")
            if not pwd:
                logger.info("No password entered; skipping authentication prompt.")
                return False

            # Set on the instance (do not persist credentials to disk)
            self.api_email = email
            self.api_password = pwd

            ok = self._authenticate()
            if not ok:
                logger.error("Interactive authentication failed. Please verify credentials or provide an API_TOKEN in .env")
            return ok
        except Exception as e:
            logger.error(f"Credential prompt failed: {e}")
            return False

    def _token_file_path(self) -> str:
        """Return path to local token cache file."""
        data_dir = os.path.join(os.getcwd(), "data")
        try:
            os.makedirs(data_dir, exist_ok=True)
        except Exception:
            pass
        return os.path.join(data_dir, ".api_token.json")

    def _save_token(self, token: str, expiry_ts: Optional[int] = None) -> None:
        payload = {"access_token": token}
        if expiry_ts:
            payload["expiry_ts"] = int(expiry_ts)
        path = self._token_file_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f)
        except Exception as e:
            logger.warning(f"Could not persist token to {path}: {e}")

    def _load_saved_token(self) -> None:
        path = self._token_file_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            token = data.get("access_token")
            expiry_ts = data.get("expiry_ts")
            if token:
                # If expiry present and in the past, ignore saved token
                if expiry_ts and int(expiry_ts) < int(time.time()):
                    logger.info("Saved API token has expired; ignoring cached token.")
                    return
                self.api_token = token
                self.token_expiry = int(expiry_ts) if expiry_ts else None
                logger.info("Loaded API token from local cache.")
        except Exception as e:
            logger.warning(f"Failed to load saved API token: {e}")

    def _request_with_retry(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make a request and re-authenticate once on 401/403."""
        # If token is missing or about to expire, try to authenticate first (if creds available)
        if (not self.api_token or (self.token_expiry and int(time.time()) + 30 >= int(self.token_expiry))) and (self.api_email and self.api_password):
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
