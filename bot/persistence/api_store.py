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

        # Shared buffer accumulates ALL jobs across all pages/distance/keywords
        # Flushed once at the end of the entire run (or on interrupt)
        self.batch_buffer = []

        logger.info(f"Initialized APIStore for: {self.client.build_url(self.positions_endpoint)}")

    def _prepare_payload(self, job_data):
        """
        Constructs the payload for a single job matching the PositionCreate schema.
        """
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
        location_field = str(job_data.get('location', '') or '').strip().lower()

        country = None
        if zipcode_raw.isdigit():
            if len(zipcode_raw) == 5:
                country = "USA"
        
        if not country:
            if 'india' in zipcode_raw.lower() or 'india' in location_field:
                country = "India"
            elif 'united states' in location_field or 'usa' in location_field:
                country = "USA"
            elif 'remote' in location_field:
                country = "USA"

        if not country:
            country = os.getenv('DEFAULT_COUNTRY', 'USA')

        payload_zip = zipcode_raw if zipcode_raw.isdigit() else ""
        source_val = job_data.get('source_job_id') or job_data.get('job_id', '')

        payload = {
            "title": str(job_data.get('title', 'Unknown')).strip().lower(),
            "company_name": str(job_data.get('company', 'Unknown')).strip().lower(),
            "location": str(full_location).strip().lower(),
            "city": str(city).strip().lower(),
            "state": str(state).strip().lower(),
            "zip": payload_zip,
            "country": str(country).strip(),
            "job_url": job_data.get('url', ''),
            "source": "linkedin",
            "source_uid": source_val,
            "source_job_id": source_val,
            "status": "open",
        }

        # Derive zip from location if still empty
        if not payload.get('zip'):
            import re
            loc_text = (payload.get('location') or '') + ' ' + (payload.get('city') or '')
            m = re.search(r"\b(\d{5})\b", loc_text)
            if m:
                payload['zip'] = m.group(1)
        
        return payload

    def insert_position(self, job_data):
        """
        Send a single job to the API.
        """
        try:
            payload = self._prepare_payload(job_data)
            logger.info(f"Sending job to: {self.client.build_url(self.positions_endpoint)}", step="api_save")
            
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

    def insert_positions(self, jobs_list):
        """
        Send multiple jobs to the API in a single batch.
        Expected endpoint: api/positions/bulk (fallback to individual if 404)
        """
        if not jobs_list:
            return

        try:
            payloads = [self._prepare_payload(job) for job in jobs_list]
            bulk_endpoint = self.positions_endpoint.rstrip('/') + "/bulk"
            
            logger.info(f"🚀 Sending {len(payloads)} jobs in bulk to: {self.client.build_url(bulk_endpoint)}", step="api_bulk_save")
            
            # API expects {"positions": [...]} — wrap the list in the correct schema object
            bulk_payload = {"positions": payloads}
            response = self.client.post(bulk_endpoint, json=bulk_payload, timeout=30)
            
            if response.status_code in [200, 201]:
                logger.info(f"✅ Successfully bulk-inserted {len(payloads)} jobs.", step="api_bulk_save")
            elif response.status_code in [404, 405]:
                logger.warning(f"⚠️ Bulk endpoint returned {response.status_code}. Falling back to individual insertions...", step="api_bulk_save")
                for job in jobs_list:
                    self.insert_position(job)
            elif response.status_code == 422:
                logger.warning(f"⚠️ Bulk endpoint returned 422 (schema mismatch). Falling back to individual insertions...", step="api_bulk_save")
                logger.debug(f"422 detail: {response.text[:400]}", step="api_bulk_save")
                for job in jobs_list:
                    self.insert_position(job)
            else:
                logger.error(f"❌ Bulk insert failed. Status: {response.status_code}, Response: {response.text[:200]}", step="api_bulk_save")
                
        except Exception as e:
            logger.error(f"Error in bulk insertion: {e}", step="api_bulk_save")

    def flush_batches(self):
        """
        Send ALL buffered jobs to the API in one bulk request.
        Call this once at the end of the full run or on KeyboardInterrupt.
        """
        if not self.batch_buffer:
            logger.info("No buffered jobs to flush.", step="api_bulk_save")
            return

        total = len(self.batch_buffer)
        logger.info(f"📡 Final flush: sending {total} buffered jobs to API...", step="api_bulk_save")
        self.insert_positions(self.batch_buffer)
        self.batch_buffer = []

    def close(self):
        pass  # Nothing to close for separate requests
