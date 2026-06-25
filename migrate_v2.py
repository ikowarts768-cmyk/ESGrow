"""
ESGrow Database Migration v2
Adds report_year and updated_at columns to indicator_scores,
and creates the fetch_log table.

Run: python migrate_v2.py
Safe to run multiple times — skips columns/tables that already exist.
"""

from database import engine, init_db
from sqlalchemy import text

MIGRATIONS = [
    ("indicator_scores", "report_year", "ALTER TABLE indicator_scores ADD COLUMN report_year INTEGER"),
    ("indicator_scores", "updated_at", "ALTER TABLE indicator_scores ADD COLUMN updated_at TIMESTAMP"),
]


def run_migration():
    print("ESGrow Migration v2")
    print("=" * 40)

    # Create any brand-new tables (like fetch_log)
    init_db()
    print("[OK] All new tables created (fetch_log, etc.)")

    # Add columns to existing tables
    with engine.connect() as conn:
        for table, column, sql in MIGRATIONS:
            try:
                conn.execute(text(sql))
                conn.commit()
                print(f"[OK] Added {table}.{column}")
            except Exception as e:
                error_msg = str(e).lower()
                if "duplicate" in error_msg or "already exists" in error_msg:
                    print(f"[SKIP] {table}.{column} already exists")
                else:
                    print(f"[WARN] {table}.{column}: {e}")

    print("=" * 40)
    print("Migration complete!")


if __name__ == "__main__":
    run_migration()
