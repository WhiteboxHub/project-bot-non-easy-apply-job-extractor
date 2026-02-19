import csv
import os
import sys
import logging

# Add project root to path
sys.path.append(os.getcwd())

from bot.persistence.api_store import APIStore
from bot.utils.logger import logger

def bulk_import_from_csv(csv_path):
    """
    Reads jobs from the specified CSV and sends them to the API in bulk.
    """
    if not os.path.exists(csv_path):
        logger.error(f"❌ CSV file not found: {os.path.abspath(csv_path)}")
        return

    jobs = []
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Map CSV columns to job_data expected by APIStore
                # source_job_id,title,company,location,zipcode,url,date_extracted,is_non_easy_apply
                job_data = {
                    'job_id': row.get('source_job_id'),
                    'title': row.get('title'),
                    'company': row.get('company'),
                    'location': row.get('location'),
                    'zipcode': row.get('zipcode'),
                    'url': row.get('url')
                }
                if job_data['job_id']:
                    jobs.append(job_data)
        
        if not jobs:
            logger.warning("⚠️ No valid jobs found in CSV.")
            return

        logger.info(f"📊 Loaded {len(jobs)} jobs from CSV. Starting bulk import...")
        
        store = APIStore()
        # Batch size for bulk insertions (e.g., 50)
        batch_size = 50
        for i in range(0, len(jobs), batch_size):
            batch = jobs[i:i + batch_size]
            logger.info(f"📤 Processing batch {i//batch_size + 1} ({len(batch)} jobs)...")
            store.insert_positions(batch)
        
        logger.info("✅ Bulk import process completed successfully.")

    except Exception as e:
        logger.error(f"❌ Error during bulk import: {e}")

if __name__ == "__main__":
    # Default to the extractor links CSV if no path provided
    csv_file = os.path.join("data", "exports", "extractor_job_links.csv")
    
    # Allow overriding CSV path via command line
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
        
    bulk_import_from_csv(csv_file)
