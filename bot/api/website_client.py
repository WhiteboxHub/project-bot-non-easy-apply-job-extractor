"""
API Client for fetching candidate data from whitebox-learning.com
This module fetches candidate information including zipcodes from the website's candidate management table.
"""

import os
import requests
import logging
from typing import List, Dict, Optional
from dotenv import load_dotenv

from bot.api.base_client import BaseAPIClient

load_dotenv()

logger = logging.getLogger(__name__)


class WebsiteAPIClient:
    """Client for interacting with the whitebox-learning.com API"""
    
    def __init__(self):
        self.client = BaseAPIClient()
    
    def fetch_candidates(self) -> List[Dict]:
        """
        Fetch all candidates from the candidate management table.
        First tries the website API, then falls back to local MySQL database.
        
        Returns:
            List of candidate dictionaries with their data including zipcodes
        """
        candidates = None
        
        # --- Try website API ---
        try:
            # The specific endpoint confirmed to work with Bearer+Secret
            endpoints = ["candidate/marketing/", "candidates/"]
            
            for endpoint in endpoints:
                url = self.client.build_url(endpoint)
                logger.info(f"Checking API: {url}")
                
                try:
                    response = self.client.get(endpoint, timeout=10)
                    
                    if response.status_code == 200:
                        content_type = response.headers.get('Content-Type', '')
                        if 'application/json' in content_type.lower():
                            candidates_data = response.json()
                            logger.info(f"✅ Found API at: {endpoint}")
                            
                            if isinstance(candidates_data, dict) and "data" in candidates_data:
                                candidates = candidates_data["data"]
                            else:
                                candidates = candidates_data
                            
                            # --- SYNC TO LOCAL DB ---
                            if candidates:
                                self._sync_to_local_db(candidates)
                                
                            break
                        else:
                            logger.warning(f"⚠️ API {endpoint} returned 200 but Content-Type is {content_type} (likely HTML redirect).")
                    elif response.status_code in [401, 403]:
                        logger.debug(f"❌ API {endpoint} Authentication failed ({response.status_code}).")
                    else:
                        logger.debug(f"API {endpoint} returned status {response.status_code}")
                except Exception as req_e:
                    logger.debug(f"Error connecting to {url}: {req_e}")
                    continue
            
            if candidates and isinstance(candidates, list) and len(candidates) > 0:
                return candidates
                    
        except Exception as e:
            logger.warning(f"API fetch failed: {e}")

        # --- NO LOCAL FALLBACK (PRODUCTION ONLY) ---
        logger.error("API authentication failed. No local fallback enabled; returning empty list.")
        return []

    def _sync_to_local_db(self, candidates: List[Dict]):
        """Saves/Updates remote candidates to local SQLite database for caching/fallback."""
        try:
            import sqlite3
            db_path = os.path.join(os.getcwd(), 'data', 'bot_data.sqlite')
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            for cand in candidates:
                # Handle nested candidate object if it's a marketing record
                c_obj = cand.get('candidate') if isinstance(cand.get('candidate'), dict) else cand
                
                c_id = str(cand.get('candidate_id', cand.get('id', '')))
                if not c_id: continue
                
                name = cand.get('full_name') or c_obj.get('full_name') or cand.get('name', 'Unknown')
                email = cand.get('email') or c_obj.get('email', '')
                username = cand.get('linkedin_username') or c_obj.get('linkedin_username') or email
                password = cand.get('linkedin_password') or cand.get('linkedin_passwd') or c_obj.get('linkedin_password', '')
                zipcode = cand.get('zip_code') or cand.get('zipcode') or c_obj.get('zip_code') or c_obj.get('zipcode', '')
                run_flag = cand.get('run_extract_linkedin_jobs')
                if run_flag is None: run_flag = True # Default to True
                
                # Update candidates table
                cursor.execute("""
                    INSERT INTO candidates (candidate_id, name, email, linkedin_username, linkedin_password, zipcode)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(candidate_id) DO UPDATE SET
                        name=excluded.name,
                        email=excluded.email,
                        linkedin_username=excluded.linkedin_username,
                        linkedin_password=excluded.linkedin_password,
                        zipcode=excluded.zipcode
                """, (c_id, name, email, username, password, zipcode))
                
                # Update marketing flag
                cursor.execute("""
                    INSERT INTO candidate_marketing (candidate_id, run_extract_linkedin_jobs)
                    VALUES (?, ?)
                    ON CONFLICT(candidate_id) DO UPDATE SET
                        run_extract_linkedin_jobs=excluded.run_extract_linkedin_jobs
                """, (c_id, 1 if run_flag else 0))
                
            conn.commit()
            conn.close()
            logger.info("✅ Local cache synchronized with website data.")
        except Exception as e:
            logger.warning(f"Failed to sync to local DB: {e}")

    def _fetch_from_local_db(self) -> List[Dict]:
        """Loads candidates from local SQLite when API is unavailable."""
        try:
            import sqlite3
            db_path = os.path.join(os.getcwd(), 'data', 'bot_data.sqlite')
            if not os.path.exists(db_path):
                return []
                
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = """
                SELECT c.*, m.run_extract_linkedin_jobs 
                FROM candidates c
                LEFT JOIN candidate_marketing m ON c.candidate_id = m.candidate_id
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error reading from local cache: {e}")
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
                
                # Locations/Zipcodes handling
                # Your backend uses 'zip_code' for Candidate and the marketing record might have it nested
                # Check candidate object directly or the marketing record fields
                c_obj = candidate.get('candidate', {})
                raw_locations = candidate.get('locations') or candidate.get('zipcodes') or \
                                candidate.get('zip_code') or candidate.get('zipcode') or \
                                c_obj.get('zip_code') or c_obj.get('zipcode') or []
                if isinstance(raw_locations, str) or isinstance(raw_locations, int):
                    locations = [str(raw_locations)]
                else:
                    locations = raw_locations
                
                # Credentials handling
                # Prioritize direct fields, then check nested 'candidate' object (typical for marketing records)
                username = candidate.get('linkedin_username') or candidate.get('email') or \
                           c_obj.get('linkedin_username') or c_obj.get('email', '')
                password = candidate.get('linkedin_password') or candidate.get('linkedin_passwd') or \
                           candidate.get('password') or c_obj.get('linkedin_password', '')
                
                # Keywords/Skills
                # You mentioned 'keywords' in your YAML, check for 'keywords', 'skills', or 'positions'
                keywords = candidate.get('keywords') or candidate.get('skills') or \
                           c_obj.get('keywords') or c_obj.get('skills', [])
                
                transformed_candidate = {
                    'candidate_id': str(c_id),
                    'name': candidate.get('full_name') or candidate.get('name') or c_obj.get('full_name', ''),
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



