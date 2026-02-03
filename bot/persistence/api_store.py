import os
import requests
import logging
from bot.utils.logger import logger
from dotenv import load_dotenv

load_dotenv()

class APIStore:
    def __init__(self):
        # Use the specific API subdomain URL provided
        self.base_api_url = os.getenv('WBL_API_URL', 'https://api.whitebox-learning.com/api').rstrip('/')
        
        # Based on: app.include_router(position.router, prefix="/api") 
        # But if the URL already ends in /api, we just add /positions/
        if self.base_api_url.endswith('/api'):
            self.api_url = f"{self.base_api_url}/positions/"
        else:
            self.api_url = f"{self.base_api_url}/api/positions/"
        
        self.api_token = os.getenv('API_TOKEN')
        self.secret_key = os.getenv('SECRET_KEY')
        
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "X-Secret-Key": self.secret_key,
            "Content-Type": "application/json"
        }
            
        logger.info(f"Initialized APIStore for: {self.api_url}")

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

            logger.info(f"Sending job to: {self.api_url}", step="api_save")
            response = requests.post(self.api_url, json=payload, headers=self.headers, timeout=15)
            
            if response.status_code in [200, 201]:
                logger.info(f"✅ Saved job to API: {job_data.get('title')}", step="api_save")
            else:
                logger.warning(f"❌ Failed to save job. Status: {response.status_code}, URL: {self.api_url}, Response: {response.text[:200]}", step="api_save")
                
        except Exception as e:
            logger.error(f"Error sending job to API: {e}", step="api_save")

    def close(self):
        pass  # Nothing to close for separate requests
