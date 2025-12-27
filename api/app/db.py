import os
from typing import Any, Dict, List

import psycopg
from psycopg.rows import dict_row


def get_conn():
    url = os.getenv(
        "DATABASE_URL",
        f"postgresql://{os.getenv('POSTGRES_USER', 'delta')}:{os.getenv('POSTGRES_PASSWORD', 'delta')}@{os.getenv('POSTGRES_HOST', 'db')}:{os.getenv('POSTGRES_PORT', '5432')}/{os.getenv('POSTGRES_DB', 'delta')}",
    )
    return psycopg.connect(url, row_factory=dict_row)


def ensure_schema() -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS filings (
        id SERIAL PRIMARY KEY,
        ticker TEXT NOT NULL,
        cik TEXT NOT NULL,
        accession TEXT NOT NULL UNIQUE,
        form TEXT,
        filed_at DATE,
        path TEXT,
        submissions_path TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS facts (
        id SERIAL PRIMARY KEY,
        accession TEXT NOT NULL,
        cik TEXT NOT NULL,
        ticker TEXT NOT NULL,
        period_start DATE,
        period_end DATE,
        period_type TEXT,
        statement TEXT,
        line_item TEXT,
        value NUMERIC,
        unit TEXT,
        source_path TEXT,
        xbrl_tag TEXT,
        context_ref TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS canonical_facts (
        id SERIAL PRIMARY KEY,
        ticker TEXT NOT NULL,
        cik TEXT NOT NULL,
        accession TEXT NOT NULL,
        period_start DATE,
        period_end DATE,
        period_type TEXT,
        statement TEXT,
        line_item TEXT,
        value NUMERIC,
        unit TEXT,
        source_fact_id INTEGER,
        source_xbrl_tag TEXT,
        source_context_ref TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
            cur.execute("ALTER TABLE facts ADD COLUMN IF NOT EXISTS period_start DATE;")
            cur.execute("ALTER TABLE facts ADD COLUMN IF NOT EXISTS xbrl_tag TEXT;")
            cur.execute("ALTER TABLE facts ADD COLUMN IF NOT EXISTS context_ref TEXT;")
            cur.execute("ALTER TABLE canonical_facts ADD COLUMN IF NOT EXISTS period_start DATE;")
            cur.execute("ALTER TABLE canonical_facts ADD COLUMN IF NOT EXISTS source_xbrl_tag TEXT;")
            cur.execute("ALTER TABLE canonical_facts ADD COLUMN IF NOT EXISTS source_context_ref TEXT;")
        conn.commit()


def list_filings_by_ticker(ticker: str) -> List[Dict[str, Any]]:
    ensure_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ticker, cik, accession, form, filed_at, path, submissions_path, created_at
                FROM filings
                WHERE ticker = %s
                ORDER BY filed_at DESC NULLS LAST, created_at DESC
                """,
                (ticker.upper(),),
            )
            rows = cur.fetchall()
    return [dict(row) for row in rows]


def get_filing_by_accession(accession: str) -> Dict[str, Any] | None:
    ensure_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ticker, cik, accession, form, filed_at, path, submissions_path, created_at
                FROM filings
                WHERE accession = %s
                """,
                (accession,),
            )
            row = cur.fetchone()
    return dict(row) if row else None
