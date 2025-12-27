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
