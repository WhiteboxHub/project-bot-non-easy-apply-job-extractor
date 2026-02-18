import os
import requests
import logging
from bot.utils.logger import logger
from dotenv import load_dotenv

from bot.api.base_client import BaseAPIClient

load_dotenv()

class APIStore:
    def __init__(self):
        self.client = BaseAPIClient()

        # Based on: app.include_router(position.router, prefix="/api")
        # If base URL already ends in /api, we just add /positions/
        if self.client.base_url.endswith('/api'):
            self.positions_endpoint = "positions/"
        else:
            self.positions_endpoint = "api/positions/"

        logger.info(f"Initialized APIStore for: {self.client.build_url(self.positions_endpoint)}")

    def insert_position(self, job_data):
        """
        Send job data to the API.
        Expected job_data keys: title, company, location, zipcode, url, job_id
        Also accepts `source_job_id` (alternate key used by some sites) and will
        prefer it when present. Both `source_uid` and `source_job_id` are sent
        in the payload for compatibility.
        """
        try:
            # 1. Parse Location (City, State)
            full_location = job_data.get('location', '')
            city = ''
            state = ''
            if full_location and ',' in full_location:
                parts = [p.strip() for p in full_location.split(',')]
                city = parts[0]
                if len(parts) > 1:
                    state = parts[1]
            
            # 2. Derive Country from Zipcode / Location
            zipcode_raw = str(job_data.get('zipcode', '') or '').strip()
            zipcode = zipcode_raw.lower()
            location_field = str(job_data.get('location', '') or '').strip().lower()

            country = None
            # If zipcode is purely numeric, use length to guess country
            if zipcode_raw.isdigit():
                if len(zipcode_raw) == 5:
                    country = "USA"
                # Do not assume 6-digit zip -> India by default. Only mark India
                # when an explicit textual cue exists in the location or zipcode.
            # If textual clues appear in zipcode or location, use them
            if not country:
                if 'india' in zipcode or 'india' in location_field:
                    country = "India"
                elif 'united states' in zipcode or 'united states' in location_field or 'usa' in zipcode or 'usa' in location_field:
                    country = "USA"
                elif 'remote' in location_field:
                    # treat remote as USA by default (adjust if needed)
                    country = "USA"

            # Fallback default
            if not country:
                country = os.getenv('DEFAULT_COUNTRY', 'USA')

            # Only include numeric zip codes in the payload; otherwise leave blank
            payload_zip = zipcode_raw if zipcode_raw.isdigit() else ""

            # 3. Construct Payload matching PositionCreate schema
            # Prefer explicit `source_job_id` if provided, otherwise fall back to `job_id`.
            source_val = job_data.get('source_job_id') or job_data.get('job_id', '')

            payload = {
                "title": job_data.get('title', 'Unknown'),
                "company_name": job_data.get('company', 'Unknown'),
                "location": full_location,
                "city": city,
                "state": state,
                "zip": payload_zip,
                "country": country,
                "job_url": job_data.get('url', ''),
                "source": "linkedin",
                "source_uid": source_val,
                # Also include `source_job_id` for APIs that expect that exact field name
                "source_job_id": source_val,
                "status": "open",
                # "position_type": "full_time", # Optional defaults
                # "employment_mode": "onsite"   # Optional defaults
            }
            
            # 4. Filter out empty values if necessary, generally API handles them or validates them.
            # Assuming the API accepts these fields.

            logger.info(f"Sending job to: {self.client.build_url(self.positions_endpoint)}", step="api_save")
            # Normalize payload to lowercase per site requirement
            try:
                payload['title'] = str(payload.get('title','')).strip().lower()
                payload['company_name'] = str(payload.get('company_name','')).strip().lower()
                payload['location'] = str(payload.get('location','')).strip().lower()
                payload['city'] = str(payload.get('city','')).strip().lower()
                payload['state'] = str(payload.get('state','')).strip().lower()
                payload['country'] = str(payload.get('country','')).strip()
            except Exception:
                pass

            # If zip is empty, attempt to extract a 5-digit ZIP from the location text
            if not payload.get('zip'):
                import re
                loc_text = (payload.get('location') or '') + ' ' + (payload.get('city') or '')
                m = re.search(r"\b(\d{5})\b", loc_text)
                if m:
                    payload['zip'] = m.group(1)
                    logger.info(f"Derived zip {payload['zip']} from location for job {payload.get('title')}", step="api_save")

            response = self.client.post(self.positions_endpoint, json=payload, timeout=15)
            
            if response.status_code in [200, 201]:
                logger.info(f"✅ Saved job to API: {job_data.get('title')}", step="api_save")
            else:
                logger.warning(
                    f"❌ Failed to save job. Status: {response.status_code}, URL: {self.client.build_url(self.positions_endpoint)}, Response: {response.text[:200]}",
                    step="api_save"
                )
                
        except Exception as e:
            logger.error(f"Error sending job to API: {e}", step="api_save")

    def close(self):
        pass  # Nothing to close for separate requests
