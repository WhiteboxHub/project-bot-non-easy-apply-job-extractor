"""
API Client for fetching candidate data from whitebox-learning.com
This module fetches candidate information including zipcodes from the website's candidate management table.
"""

import os
import requests
import logging
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class WebsiteAPIClient:
    """Client for interacting with the whitebox-learning.com API"""
    
    def __init__(self):
        self.base_url = os.getenv("WEBSITE_URL", "https://whitebox-learning.com/")
        self.api_token = os.getenv("API_TOKEN")
        self.secret_key = os.getenv("SECRET_KEY")
        
        if not self.api_token:
            raise ValueError("API_TOKEN not found in environment variables")
        
        # Ensure base URL ends with /
        if not self.base_url.endswith('/'):
            self.base_url += '/'
        
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "X-Secret-Key": self.secret_key,
            "X-API-Key": self.secret_key
        }
    
    def fetch_candidates(self) -> List[Dict]:
        """
        Fetch all candidates from the candidate management table.
        First tries the website API, then falls back to local MySQL database.
        
        Returns:
            List of candidate dictionaries with their data including zipcodes
        """
        candidates = None
        
        # --- Try website API first ---
        try:
            # Try different possible API endpoints
            endpoints = [
                "api/candidates",
                "api/candidate-management",
                "api/v1/candidates",
                "api/marketing/candidates",
                "api/job-automation/candidates",
                "candidates"
            ]
            
            for endpoint in endpoints:
                url = f"{self.base_url}{endpoint}"
                logger.debug(f"Attempting to fetch candidates from API: {url}")
                
                try:
                    response = requests.get(url, headers=self.headers, timeout=10)
                    
                    if response.status_code == 200:
                        candidates = response.json()
                        logger.info(f"✅ Successfully fetched candidates from API: {endpoint}")
                        break
                    elif response.status_code in [401, 403]:
                        logger.warning(f"❌ API Authentication failed for {endpoint} (Status {response.status_code}). Check your token/secret key.")
                    else:
                        logger.debug(f"API {endpoint} returned status {response.status_code}")
                except requests.exceptions.RequestException as req_e:
                    logger.debug(f"Connection error to {url}: {req_e}")
                    continue
            
            if candidates:
                # Handle different response formats
                if isinstance(candidates, dict):
                    candidates = candidates.get('data', candidates.get('candidates', []))
                
                if isinstance(candidates, list) and len(candidates) > 0:
                    return candidates
                    
        except Exception as e:
            logger.warning(f"API fetch failed, will try local database: {e}")

        # --- Fallback to local MySQL database if API fails or returns no data ---
        logger.info("Fetching candidates from local MySQL management tables...")
        try:
            from bot.persistence.mysql_store import MySQLStore
            import re
            
            mysql_store = MySQLStore()
            if not mysql_store.connection:
                return []
                
            cursor = mysql_store.connection.cursor(dictionary=True)
            
            # 1. Fetch from 'candidate' joined with 'candidate_marketing'
            # Including run_extract_linkedin_jobs flag
            query_main = """
            SELECT c.id, c.full_name, c.email, c.address, cm.linkedin_username, cm.linkedin_passwd, cm.notes, cm.run_extract_linkedin_jobs
            FROM candidate c
            JOIN candidate_marketing cm ON c.id = cm.candidate_id
            WHERE cm.status = 'active'
            """
            cursor.execute(query_main)
            main_results = cursor.fetchall()
            
            # 2. Fetch from 'xxx_candidate_old'
            query_old = """
            SELECT candidateid, name, email, zip, city, state, address, linkedin
            FROM xxx_candidate_old
            """
            cursor.execute(query_old)
            old_results = cursor.fetchall()

            candidates_map = {} # Use a map to merge by name/email
            zip_pattern = re.compile(r'\b\d{5}(?:-\d{4})?\b')
            india_zip_pattern = re.compile(r'\b\d{6}\b')
            
            def extract_zips(text):
                if not text: return []
                zips = zip_pattern.findall(str(text))
                zips.extend(india_zip_pattern.findall(str(text)))
                return zips

            # Process Main Results
            for row in main_results:
                email = row.get('linkedin_username') or row.get('email')
                name = row.get('full_name')
                cid = f"candidate_{row['id']}"
                
                zips = extract_zips(row.get('address')) + extract_zips(row.get('notes'))
                
                candidates_map[cid] = {
                    'id': str(row['id']),
                    'candidate_id': cid,
                    'full_name': name,
                    'linkedin_username': email,
                    'linkedin_password': row.get('linkedin_passwd') or '',
                    'zipcodes': list(set(zips)),
                    'keywords': [],
                    'run_extract_linkedin_jobs': row.get('run_extract_linkedin_jobs', True)
                }
            
            # Process Old Results (Merge or Add)
            for row in old_results:
                name = row.get('name')
                email = row.get('linkedin') or row.get('email')
                cid = f"candidate_{row['candidateid']}"
                
                zips = []
                if row.get('zip'): zips.append(str(row['zip']))
                zips += extract_zips(row.get('address'))

                # Try to find existing by name or email
                existing_key = None
                for k, v in candidates_map.items():
                    if (email and v['linkedin_username'] == email) or (name and v['full_name'] == name):
                        existing_key = k
                        break
                
                if existing_key:
                    candidates_map[existing_key]['zipcodes'] = list(set(candidates_map[existing_key]['zipcodes'] + zips))
                else:
                    candidates_map[cid] = {
                        'id': str(row['candidateid']),
                        'candidate_id': cid,
                        'full_name': name,
                        'linkedin_username': email,
                        'linkedin_password': '',
                        'zipcodes': list(set(zips)),
                        'keywords': [],
                        'run_extract_linkedin_jobs': True # Default for old candidates if used
                    }
            
            mysql_store.close()
            final_list = list(candidates_map.values())
            logger.info(f"Successfully loaded/merged {len(final_list)} candidates from local MySQL database")
            return final_list
            
        except Exception as e:
            logger.error(f"Error fetching candidates from local database: {e}")
            return []

    def get_candidate_zipcodes(self, candidate_id: str) -> List[str]:
        # Zipcodes are now bundled in the candidates fetch
        return []

    def transform_to_yaml_format(self, api_candidates: List[Dict]) -> List[Dict]:
        """
        Transform candidate data (from API or DB) to the format expected by the extraction script.
        """
        transformed = []
        
        for candidate in api_candidates:
            try:
                # Handle both API format and our DB-fallback format
                c_id = candidate.get('candidate_id', candidate.get('id', 'unknown'))
                username = candidate.get('linkedin_username', candidate.get('email', ''))
                password = candidate.get('linkedin_password', candidate.get('password', ''))
                
                # Zipcodes/Locations field name mapping
                locations = candidate.get('locations', candidate.get('zipcodes', []))
                
                # Keywords field name mapping
                keywords = candidate.get('keywords', candidate.get('skills', []))
                
                transformed_candidate = {
                    'candidate_id': str(c_id),
                    'name': candidate.get('full_name') or candidate.get('name', ''),
                    'full_name': candidate.get('full_name') or candidate.get('name', ''),
                    'linkedin_username': username,
                    'linkedin_password': password,
                    'keywords': keywords,
                    'locations': locations,
                    'run_extract_linkedin_jobs': candidate.get('run_extract_linkedin_jobs', True)
                }
                
                # Cleanup lists if they are strings
                for field in ['keywords', 'locations']:
                    if isinstance(transformed_candidate[field], str):
                        transformed_candidate[field] = [i.strip() for i in transformed_candidate[field].split(',') if i.strip()]
                
                # If no keywords found, try to fetch some default ones (could be expanded)
                if not transformed_candidate['keywords']:
                    transformed_candidate['keywords'] = ["Software Engineer"]

                # Ensure we have locations to search
                if transformed_candidate['locations']:
                    transformed.append(transformed_candidate)
                else:
                    logger.debug(f"Candidate {c_id} has no zipcodes/locations, skipping.")
                    
            except Exception as e:
                logger.error(f"Error transforming candidate data: {e}")
                continue
        
        return transformed


def fetch_candidates_from_api() -> List[Dict]:
    """
    Convenience function to fetch and transform candidates.
    """
    try:
        client = WebsiteAPIClient()
        raw_candidates = client.fetch_candidates()
        
        if not raw_candidates:
            return []
        
        return client.transform_to_yaml_format(raw_candidates)
    except Exception as e:
        logger.error(f"Error in fetch_candidates_from_api: {e}")
        return []


if __name__ == "__main__":
    # Test the client
    logging.basicConfig(level=logging.INFO)
    candidates = fetch_candidates_from_api()
    print(f"\nTotal Candidates Ready: {len(candidates)}")
    for c in candidates[:3]:
        print(f"- {c['candidate_id']}: {c['linkedin_username']} | Zips: {c['locations']}")

