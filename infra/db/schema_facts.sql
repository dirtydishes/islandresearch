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
    xbrl_tag TEXT,
    context_ref TEXT,
    source_path TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
