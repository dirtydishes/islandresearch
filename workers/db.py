import os
from typing import Any, Dict, List, Optional

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - optional for non-DB unit tests
    psycopg = None
    dict_row = None  # type: ignore


def get_conn():
    if psycopg is None:
        raise ImportError("psycopg is required to connect to Postgres. Install workers/requirements.txt.")
    url = os.getenv(
        "DATABASE_URL",
        f"postgresql://{os.getenv('POSTGRES_USER', 'delta')}:{os.getenv('POSTGRES_PASSWORD', 'delta')}@{os.getenv('POSTGRES_HOST', 'db')}:{os.getenv('POSTGRES_PORT', '5432')}/{os.getenv('POSTGRES_DB', 'delta')}",
    )
    return psycopg.connect(url, row_factory=dict_row)


def ensure_schema() -> None:
    if psycopg is None:
        raise ImportError("psycopg is required to manage schema. Install workers/requirements.txt.")
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
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
            cur.execute("ALTER TABLE facts ADD COLUMN IF NOT EXISTS period_start DATE;")
            cur.execute("ALTER TABLE canonical_facts ADD COLUMN IF NOT EXISTS period_start DATE;")
        conn.commit()


def upsert_filing(
    ticker: str,
    cik: str,
    accession: str,
    form: Optional[str],
    filed_at: Optional[str],
    path: Optional[str],
    submissions_path: Optional[str],
) -> None:
    ensure_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO filings (ticker, cik, accession, form, filed_at, path, submissions_path)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (accession) DO UPDATE
                SET form = EXCLUDED.form,
                    filed_at = EXCLUDED.filed_at,
                    path = COALESCE(EXCLUDED.path, filings.path),
                    submissions_path = COALESCE(EXCLUDED.submissions_path, filings.submissions_path);
                """,
                (ticker.upper(), cik, accession, form, filed_at, path, submissions_path),
            )
        conn.commit()


def list_filing_accessions(ticker: str) -> List[str]:
    ensure_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT accession
                FROM filings
                WHERE ticker = %s
                """,
                (ticker.upper(),),
            )
            rows = cur.fetchall()
    return [row["accession"] for row in rows]
