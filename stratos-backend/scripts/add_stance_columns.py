"""
One-shot, idempotent schema patch for Stages 3-5 of the gap-closing plan.

`create_tables.py` (Base.metadata.create_all) creates missing TABLES but
never adds COLUMNS to a table that already exists -- same pattern as
add_competitor_columns.py and add_pipeline_tracking_columns.py.

Adds `sources.stance` / `sources.stance_rationale` / `sources.title`
(Stage 3 + 5b, Source) and `reports.verdict` / `verdict_holding` /
`verdict_payload` / `flip_condition` / `verdict_confidence` (Stage 4,
Report) -- see app/db/models.py.

Safe to run on a database that already has the columns, and safe to run on
a brand-new database where `create_tables.py` already created them from the
updated model.
"""

from sqlalchemy import text

from app.db.database import engine

STATEMENTS = [
    "ALTER TABLE sources ADD COLUMN IF NOT EXISTS stance VARCHAR",
    "ALTER TABLE sources ADD COLUMN IF NOT EXISTS stance_rationale TEXT",
    "ALTER TABLE sources ADD COLUMN IF NOT EXISTS title VARCHAR",
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS verdict VARCHAR",
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS verdict_holding TEXT",
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS verdict_payload TEXT",
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS flip_condition TEXT",
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS verdict_confidence VARCHAR",
]

if __name__ == "__main__":
    with engine.begin() as conn:
        for statement in STATEMENTS:
            print(f"Running: {statement}")
            conn.execute(text(statement))

    print("sources/reports tables patched successfully!")
