"""Utility to scrub local sensitive data: clears plaintext passwords in SQLite and removes cached token.

Usage:
  python scripts/scrub_sensitive.py

This script will:
 - Set `linkedin_password` to an empty string in the local `data/bot_data.sqlite` candidates table
 - Remove `data/.api_token.json` if present

Run this on the machine where the repository is used. It does not touch remote APIs.
"""

import os
import sqlite3
import argparse


def scrub_sqlite(db_path: str) -> None:
    if not os.path.exists(db_path):
        print(f"No DB found at {db_path}, skipping.")
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        # Only update if column exists
        cur.execute("PRAGMA table_info(candidates)")
        cols = [r[1] for r in cur.fetchall()]
        if 'linkedin_password' not in cols:
            print('No linkedin_password column found in candidates table; nothing to scrub.')
            return

        cur.execute("UPDATE candidates SET linkedin_password = '' WHERE linkedin_password IS NOT NULL")
        conn.commit()
        print("Cleared linkedin_password values in candidates table.")
    except Exception as e:
        print(f"Error scrubbing DB: {e}")
    finally:
        conn.close()


def remove_token_file(path: str) -> None:
    if os.path.exists(path):
        try:
            os.remove(path)
            print(f"Removed token file: {path}")
        except Exception as e:
            print(f"Failed to remove token file: {e}")
    else:
        print(f"No token file at {path}, skipping.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default=os.path.join(os.getcwd(), 'data', 'bot_data.sqlite'))
    parser.add_argument('--token', default=os.path.join(os.getcwd(), 'data', '.api_token.json'))
    args = parser.parse_args()

    print("This will scrub local sensitive files. Continue? (y/N)")
    confirm = input().strip().lower()
    if confirm != 'y':
        print('Aborted.')
        return

    scrub_sqlite(args.db)
    remove_token_file(args.token)


if __name__ == '__main__':
    main()
