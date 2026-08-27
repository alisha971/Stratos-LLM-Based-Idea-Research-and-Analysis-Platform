"""
One-shot, idempotent schema patch for the competitor worker.

`create_tables.py` (Base.metadata.create_all) creates missing TABLES but never
adds COLUMNS to a table that already exists. `competitors` predates the
competitor worker and ships with only id/report_id/name/website/summary, so
existing dev/prod databases need these columns added by hand.

Safe to run on a database that already has the columns (Postgres >= 9.6
supports `ADD COLUMN IF NOT EXISTS`), and safe to run on a brand-new database
where `create_tables.py` already created them from the updated model.
"""

from sqlalchemy import text

from app.db.database import engine

STATEMENTS = [
    "ALTER TABLE competitors ADD COLUMN IF NOT EXISTS tagline VARCHAR",
    "ALTER TABLE competitors ADD COLUMN IF NOT EXISTS target_customer VARCHAR",
    "ALTER TABLE competitors ADD COLUMN IF NOT EXISTS pricing_model VARCHAR",
    "ALTER TABLE competitors ADD COLUMN IF NOT EXISTS pricing_signal TEXT",
    "ALTER TABLE competitors ADD COLUMN IF NOT EXISTS source_id VARCHAR REFERENCES sources(id)",
    "ALTER TABLE competitors ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT now()",
]

if __name__ == "__main__":
    with engine.begin() as conn:
        for statement in STATEMENTS:
            print(f"Running: {statement}")
            conn.execute(text(statement))

    print("competitors table patched successfully!")
