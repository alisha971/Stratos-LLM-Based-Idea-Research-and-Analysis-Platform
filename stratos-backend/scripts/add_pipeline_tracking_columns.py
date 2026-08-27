"""
One-shot, idempotent schema patch for Stage 1 pipeline-robustness work
(stratos-launch-plan gap-closing plan, Stage 1).

`create_tables.py` (Base.metadata.create_all) creates missing TABLES but never
adds COLUMNS to a table that already exists, so existing dev/prod databases
need this column added by hand -- same pattern as add_competitor_columns.py.

`reports.missing_research_legs` records which of the research/trend/competitor
legs (if any) were still missing when the research_join timeout fired and
section writing proceeded anyway (see app/services/research_join_service.py,
OrchestratorService.try_advance_to_writing). Nullable JSON-encoded list of
leg names, e.g. '["trend"]', or NULL when all three legs arrived normally.

Safe to run on a database that already has the column, and safe to run on a
brand-new database where `create_tables.py` already created it.
"""

from sqlalchemy import text

from app.db.database import engine

STATEMENTS = [
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS missing_research_legs TEXT",
]

if __name__ == "__main__":
    with engine.begin() as conn:
        for statement in STATEMENTS:
            print(f"Running: {statement}")
            conn.execute(text(statement))

    print("reports table patched successfully!")
