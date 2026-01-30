import os
import mysql.connector
from mysql.connector import Error
from bot.utils.logger import logger
from dotenv import load_dotenv

load_dotenv()

class MySQLStore:
    def __init__(self):
        self.host = os.getenv('DB_HOST', 'localhost')
        self.user = os.getenv('DB_USER', 'root')
        self.password = os.getenv('DB_PASSWORD', '')
        self.database = os.getenv('DB_NAME', '')
        self.port = int(os.getenv('DB_PORT', 3306))
        
        self.connection = None
        self.connect()

    def connect(self):
        try:
            if not self.database:
                logger.warning("DB_NAME not set in .env, skipping MySQL connection.")
                return

            self.connection = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                port=self.port
            )
            if self.connection.is_connected():
                logger.info("Connected to MySQL database")
        except Error as e:
            logger.error(f"Error connecting to MySQL: {e}")
            self.connection = None

    def insert_position(self, job_data):
        if not self.connection or not self.connection.is_connected():
            logger.error(f"Cannot save job '{job_data.get('title')}' to MySQL: No active connection. Check your .env credentials.")
            return

        query = """
        INSERT INTO position (
            title, company_name, location, city, state, zip, country,
            job_url, source, source_uid, status, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s,
            %s, 'linkedin', %s, 'open', NOW(), NOW()
        )
        ON DUPLICATE KEY UPDATE
            updated_at = NOW(),
            status = 'open'
        """
        
        # Try to parse city/state from location "City, State" or "City, Country"
        full_location = job_data.get('location', '')
        city = ''
        state = ''
        if ',' in full_location:
            parts = [p.strip() for p in full_location.split(',')]
            city = parts[0]
            state = parts[1] if len(parts) > 1 else ''
        
        # Detect Country based on Zipcode
        zipcode = str(job_data.get('zipcode', ''))
        country = "USA" if len(zipcode) == 5 else "India"

        args = (
            job_data.get('title', 'Unknown'),
            job_data.get('company', 'Unknown'),
            full_location,
            city,
            state,
            zipcode,
            country,
            job_data.get('url', ''),
            job_data.get('job_id', '')
        )

        try:
            cursor = self.connection.cursor()
            cursor.execute(query, args)
            self.connection.commit()
            logger.info(f"Saved job to MySQL: {job_data.get('title')}", step="db_save")
        except Error as e:
            logger.error(f"Failed to insert into MySQL: {e}", step="db_save")

    def close(self):
        if self.connection and self.connection.is_connected():
            self.connection.close()
