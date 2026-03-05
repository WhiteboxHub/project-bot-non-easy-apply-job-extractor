"""
Clears all extracted jobs from the local SQLite cache so the bot will re-process them.
Use this when you want to test ATS link extraction on jobs that have already been seen.
"""
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.persistence.store import Store

store = Store()
cursor = store.con.cursor()

count = cursor.execute("SELECT COUNT(*) FROM extracted_jobs").fetchone()[0]
print(f"Found {count} cached jobs in extracted_jobs table.")

cursor.execute("DELETE FROM extracted_jobs")
store.con.commit()

remaining = cursor.execute("SELECT COUNT(*) FROM extracted_jobs").fetchone()[0]
print(f"Cleared. Remaining rows: {remaining}")
print("✅ Job cache cleared. Run daily_extractor.py again to re-extract with ATS links.")
