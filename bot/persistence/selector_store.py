"""
SelectorStore - Syncs CSS/XPath selectors from selectors.py into a DuckDB table.

On every bot startup, call SelectorStore().sync() to keep the DB in sync with code.
The DuckDB file is stored at data/selectors.duckdb and can be opened with any DuckDB viewer.

Table schema:
  CREATE TABLE selectors (
    name         VARCHAR,
    strategy     VARCHAR,   -- e.g. 'css selector', 'xpath'
    primary_value VARCHAR,
    fallback_value VARCHAR,
    last_synced  TIMESTAMP
  )
"""
import duckdb
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

SELECTORS_DB_PATH = "data/selectors.duckdb"


class SelectorStore:
    def __init__(self, db_path: str = SELECTORS_DB_PATH):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(db_path)
        self._init_db()

    def _init_db(self):
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS selectors (
                name          VARCHAR PRIMARY KEY,
                strategy      VARCHAR,
                primary_value VARCHAR,
                fallback_value VARCHAR,
                last_synced   TIMESTAMP
            )
        """)
        self.con.commit()

    def sync(self):
        """
        Read all selectors from bot.utils.selectors.LOCATORS and upsert into DuckDB.
        Call this on every bot startup so the DB always mirrors the code.
        """
        from bot.utils.selectors import LOCATORS

        now = datetime.now()
        count = 0

        for name, locator in LOCATORS.items():
            if isinstance(locator, dict):
                primary = locator.get("primary", (None, None))
                fallback = locator.get("fallback", (None, None))
                strategy = primary[0] if primary else None
                primary_val = primary[1] if primary else None
                fallback_val = fallback[1] if fallback else None
            elif isinstance(locator, tuple):
                # Legacy plain tuple
                strategy = locator[0]
                primary_val = locator[1]
                fallback_val = None
            else:
                continue

            self.con.execute("""
                INSERT INTO selectors (name, strategy, primary_value, fallback_value, last_synced)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (name) DO UPDATE SET
                    strategy      = excluded.strategy,
                    primary_value = excluded.primary_value,
                    fallback_value = excluded.fallback_value,
                    last_synced   = excluded.last_synced
            """, [name, str(strategy), primary_val, fallback_val, now])
            count += 1

        self.con.commit()
        log.info(f"✅ Selector sync complete: {count} selectors written to DuckDB ({SELECTORS_DB_PATH})")
        return count

    def get_all(self):
        """Return all selectors from DuckDB as a list of dicts."""
        rows = self.con.execute("SELECT * FROM selectors ORDER BY name").fetchall()
        cols = ["name", "strategy", "primary_value", "fallback_value", "last_synced"]
        return [dict(zip(cols, row)) for row in rows]
