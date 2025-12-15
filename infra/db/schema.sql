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
