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
            
            # 2. Derive Country from Zipcode
            zipcode = str(job_data.get('zipcode', ''))
            country = "USA" if len(zipcode) == 5 else "India"

            # 3. Construct Payload matching PositionCreate schema
            payload = {
                "title": job_data.get('title', 'Unknown'),
                "company_name": job_data.get('company', 'Unknown'),
                "location": full_location,
                "city": city,
                "state": state,
                "zip": zipcode,
                "country": country,
                "job_url": job_data.get('url', ''),
                "source": "linkedin",
                "source_uid": job_data.get('job_id', ''),
                "status": "open",
                # "position_type": "full_time", # Optional defaults
                # "employment_mode": "onsite"   # Optional defaults
            }
            
            # 4. Filter out empty values if necessary, generally API handles them or validates them.
            # Assuming the API accepts these fields.

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

    def close(self):
        pass  # Nothing to close for separate requests
