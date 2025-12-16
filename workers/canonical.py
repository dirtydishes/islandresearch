from typing import Any, Dict, List

from .db import ensure_schema, get_conn


def materialize_canonical_for_ticker(ticker: str) -> int:
    """
    Aggregate facts by period and line item so each period has a single summed value per tag.
    """
    ensure_schema()
    inserted = 0
    t = ticker.upper()
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Clear prior canonical rows for this ticker.
            cur.execute("DELETE FROM canonical_facts WHERE ticker = %s", (t,))
            # Aggregate by period/tag/unit and keep a representative accession/source_fact_id.
            cur.execute(
                """
                INSERT INTO canonical_facts (ticker, cik, accession, period_end, period_type, statement, line_item, value, unit, source_fact_id)
                WITH normalized AS (
                  SELECT
                    ticker,
                    cik,
                    accession,
                    period_end,
                    CASE
                      WHEN statement IN ('income_statement','cash_flow') THEN 'duration'
                      WHEN statement = 'balance_sheet' THEN 'instant'
                      ELSE COALESCE(period_type, 'unknown')
                    END AS norm_period_type,
                    statement,
                    line_item,
                    value,
                    UPPER(unit) AS unit_norm,
                    id
                  FROM facts
                  WHERE ticker = %s
                    AND value IS NOT NULL
                    AND period_end IS NOT NULL
                    AND statement IS NOT NULL
                    AND line_item IS NOT NULL
                )
                SELECT
                    ticker,
                    cik,
                    MAX(accession) AS accession,
                    period_end,
                    norm_period_type AS period_type,
                    statement,
                    line_item,
                    MAX(value) AS value,
                    unit_norm AS unit,
                    MIN(id) AS source_fact_id
                FROM normalized
                GROUP BY ticker, cik, period_end, norm_period_type, statement, line_item, unit_norm;
                """,
                (t,),
            )
            inserted = cur.rowcount
            # Simple backfill: if no rows for this ticker, try to fill a default period_end from the latest accession.
            if inserted == 0:
                cur.execute(
                    """
                    WITH latest AS (
                      SELECT accession, MAX(created_at) AS created_at
                      FROM facts
                      WHERE ticker = %s
                      GROUP BY accession
                      ORDER BY created_at DESC
                      LIMIT 1
                    ),
                    inferred_period AS (
                      SELECT COALESCE(MAX(period_end), MAX(filed_at)) AS period_end
                      FROM filings f
                      JOIN latest l ON f.accession = l.accession
                      WHERE f.ticker = %s
                    )
                    , normalized AS (
                      SELECT
                        ff.ticker,
                        ff.cik,
                        ff.accession,
                        ip.period_end,
                        CASE
                          WHEN ff.statement IN ('income_statement','cash_flow') THEN 'duration'
                          WHEN ff.statement = 'balance_sheet' THEN 'instant'
                          ELSE 'unknown'
                        END AS period_type,
                        ff.statement,
                        ff.line_item,
                        ff.value,
                        UPPER(ff.unit) AS unit_norm,
                        ff.id
                      FROM facts ff
                      CROSS JOIN inferred_period ip
                      WHERE ff.ticker = %s
                        AND ff.value IS NOT NULL
                        AND ff.statement IS NOT NULL
                        AND ff.line_item IS NOT NULL
                    )
                    INSERT INTO canonical_facts (ticker, cik, accession, period_end, period_type, statement, line_item, value, unit, source_fact_id)
                    SELECT
                      ticker,
                      cik,
                      MAX(accession),
                      period_end,
                      period_type,
                      statement,
                      line_item,
                      MAX(value),
                      unit_norm,
                      MIN(id)
                    FROM normalized
                    GROUP BY ticker, cik, period_end, period_type, statement, line_item, unit_norm;
                    """,
                    (t, t, t),
                )
                inserted = cur.rowcount
        conn.commit()
    return inserted
