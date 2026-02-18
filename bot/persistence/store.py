import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import logging
from pathlib import Path
import os
import re

log = logging.getLogger(__name__)

class Store:
    def __init__(self, db_file='data/bot_data.sqlite'):
        self.db_file = db_file
        # Ensure data directory exists
        Path(self.db_file).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.db_file, check_same_thread=False)
        self._init_db()
        self.cleanup_old_jobs(days=3)
        self._migrate_legacy_data()

    def _init_db(self):
        cursor = self.con.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                timestamp TIMESTAMP,
                job_id VARCHAR,
                job VARCHAR,
                company VARCHAR,
                attempted BOOLEAN,
                result BOOLEAN,
                candidate_id VARCHAR DEFAULT 'default',
                proxy_used VARCHAR DEFAULT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS candidates (
                candidate_id VARCHAR PRIMARY KEY,
                name VARCHAR,
                email VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                zipcode VARCHAR,
                linkedin_username VARCHAR,
                linkedin_password VARCHAR
            )
        """)

        # Add columns if missing (SQLite manual migration)
        try:
             cursor.execute("ALTER TABLE candidates ADD COLUMN zipcode VARCHAR")
        except: pass
        try:
             cursor.execute("ALTER TABLE candidates ADD COLUMN linkedin_username VARCHAR")
        except: pass
        try:
             cursor.execute("ALTER TABLE candidates ADD COLUMN linkedin_password VARCHAR")
        except: pass
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS candidate_marketing (
                candidate_id VARCHAR,
                run_extract_linkedin_jobs BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (candidate_id) REFERENCES candidates(candidate_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id VARCHAR PRIMARY KEY,
                candidate_id VARCHAR,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                applications_submitted INTEGER DEFAULT 0,
                applications_failed INTEGER DEFAULT 0,
                proxy_used VARCHAR,
                system_id VARCHAR DEFAULT 'local'
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS qa (
                question VARCHAR UNIQUE,
                answer VARCHAR
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS extracted_jobs (
                id VARCHAR PRIMARY KEY,
                job_id VARCHAR,
                url VARCHAR,
                title VARCHAR,
                company VARCHAR,
                location VARCHAR,
                date_extracted TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                candidate_id VARCHAR,
                is_easy_apply BOOLEAN
            )
        """)
        
        self.con.commit()

    def cleanup_old_jobs(self, days=3):
        """
        Deletes entries from 'extracted_jobs' that are older than the specified number of days.
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            # Use ISO format for SQLite compatibility if needed, though CURRENT_TIMESTAMP is usually handled fine.
            cursor = self.con.cursor()
            cursor.execute("DELETE FROM extracted_jobs WHERE date_extracted < ?", [cutoff_date])
            deleted_count = cursor.rowcount
            self.con.commit()
            if deleted_count > 0:
                log.info(f"🧹 Cleanup: Removed {deleted_count} jobs older than {days} days from extracted_jobs.")
            else:
                log.debug(f"Cleanup: No jobs older than {days} days found.")
        except Exception as e:
            log.error(f"Failed to cleanup old jobs: {e}")

    def _migrate_legacy_data(self):
        # Skipping CSV migration for stability in SQLite port
        pass

    def get_appliedIDs(self) -> list | None:
        try:
            two_days_ago = datetime.now() - timedelta(days=2)
            # SQLite doesn't natively support datetime object comparison directly without adapter, 
            # but usually it works if stored as ISO string. 
            # Ideally we ensure timestamp is stored as string.
            results = self.con.execute("SELECT job_id FROM applications WHERE timestamp > ?", [two_days_ago]).fetchall()
            jobIDs = [row[0] for row in results]
            log.info(f"{len(jobIDs)} jobIDs found (last 48h)")
            return jobIDs
        except Exception as e:
            log.error(f"Failed to fetch jobIDs: {e}")
            return []

    def write_to_file(self, button, jobID, browserTitle, result, candidate_id='default', proxy_used=None) -> None:
        def re_extract(text, pattern):
            target = re.search(pattern, text)
            if target:
                target = target.group(1)
            return target
            
        timestamp = datetime.now()
        attempted = True if button else False 
        
        job = re_extract(browserTitle.split(' | ')[0], r"\(?\d?\)?\s?(\w.*)")
        company = re_extract(browserTitle.split(' | ')[1], r"(\w.*)")
        
        try:
            self.con.execute("INSERT INTO applications VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                             [timestamp, jobID, job, company, attempted, result, candidate_id, proxy_used])
            self.con.commit()
        except Exception as e:
            log.error(f"Failed to write application to DB: {e}")

    def save_answer(self, question, answer):
        try:
            # SQLite uses INSERT OR REPLACE
            self.con.execute("INSERT OR REPLACE INTO qa VALUES (?, ?)", [question, answer])
            self.con.commit()
            log.info(f"Saved answer for: '{question}'")
        except Exception as e:
             log.error(f"Failed to save QA: {e}")

    def get_answer(self, question):
        try:
            res = self.con.execute("SELECT answer FROM qa WHERE question = ?", [question]).fetchone()
            return res[0] if res else None
        except Exception as e:
            log.error(f"Failed to get answer: {e}")
            return None
    
    # Execute wrapper to behave like DuckDB connection sometimes? 
    # Or exposing the connection directly which we do via self.con.
    # The calling code uses self.con.execute(). SQLite connection also has .execute(), so it should be compatible.
    # Note: SQLite execute returns a Cursor, DuckDB execute returns a specific object but it is iterable.
    # fetchall() works on both.
