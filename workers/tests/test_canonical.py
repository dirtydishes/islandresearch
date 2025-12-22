import unittest
from datetime import date

from workers.canonical import aggregate_canonical_rows
from workers.parser import parse_inline_xbrl


class AggregateCanonicalRowsTests(unittest.TestCase):
    def test_groups_by_period_and_normalizes_types(self) -> None:
        rows = [
            {
                "id": 2,
                "ticker": "aapl",
                "cik": "0000320193",
                "accession": "acc-1",
                "period_end": date(2023, 6, 24),
                "period_type": "duration",
                "statement": "income_statement",
                "line_item": "revenue",
                "value": 100,
                "unit": "usd",
            },
            {
                "id": 1,
                "ticker": "aapl",
                "cik": "0000320193",
                "accession": "acc-2",
                "period_end": date(2023, 6, 24),
                "period_type": "duration",
                "statement": "income_statement",
                "line_item": "revenue",
                "value": 120,
                "unit": "usd",
            },
            {
                "id": 3,
                "ticker": "aapl",
                "cik": "0000320193",
                "accession": "acc-2",
                "period_end": None,
                "period_type": None,
                "statement": "balance_sheet",
                "line_item": "cash",
                "value": 55,
                "unit": "usd",
            },
            {
                "id": 4,
                "ticker": "aapl",
                "cik": "0000320193",
                "accession": "acc-3",
                "period_end": date(2023, 6, 24),
                "period_type": "instant",
                "statement": "balance_sheet",
                "line_item": "equity",
                "value": 200,
                "unit": "usd",
            },
        ]
        aggregated = aggregate_canonical_rows(rows, default_period_end=date(2023, 6, 24))
        self.assertEqual(len(aggregated), 3)

        revenue = next(r for r in aggregated if r["line_item"] == "revenue")
        self.assertEqual(revenue["value"], 120.0)
        self.assertEqual(revenue["source_fact_id"], 1)
        self.assertEqual(revenue["period_type"], "duration")
        self.assertEqual(revenue["ticker"], "AAPL")
        self.assertEqual(revenue["unit"], "USD")

        cash = next(r for r in aggregated if r["line_item"] == "cash")
        self.assertEqual(cash["period_type"], "instant")
        self.assertEqual(cash["period_end"], date(2023, 6, 24))

        equity = next(r for r in aggregated if r["line_item"] == "equity")
        self.assertEqual(equity["value"], 200.0)
        self.assertEqual(equity["source_fact_id"], 4)

    def test_filters_unknown_statements(self) -> None:
        rows = [
            {
                "id": 1,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "acc",
                "period_end": date(2024, 12, 31),
                "period_type": "duration",
                "statement": "income_statement",
                "line_item": "revenue",
                "value": 10,
                "unit": "usd",
            },
            {
                "id": 2,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "acc",
                "period_end": date(2024, 12, 31),
                "period_type": "duration",
                "statement": "other",
                "line_item": "unknown",
                "value": 5,
                "unit": "usd",
            },
        ]
        aggregated = aggregate_canonical_rows(rows)
        self.assertEqual(len(aggregated), 1)
        self.assertEqual(aggregated[0]["line_item"], "revenue")

    def test_prefers_shorter_duration_for_income_statement(self) -> None:
        rows = [
            {
                "id": 1,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "acc",
                "period_start": date(2023, 1, 1),
                "period_end": date(2023, 6, 30),
                "period_type": "duration",
                "statement": "income_statement",
                "line_item": "revenue",
                "value": 300,
                "unit": "usd",
            },
            {
                "id": 2,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "acc",
                "period_start": date(2023, 4, 1),
                "period_end": date(2023, 6, 30),
                "period_type": "duration",
                "statement": "income_statement",
                "line_item": "revenue",
                "value": 120,
                "unit": "usd",
            },
        ]
        aggregated = aggregate_canonical_rows(rows)
        self.assertEqual(len(aggregated), 1)
        self.assertEqual(aggregated[0]["value"], 120.0)
        self.assertEqual(aggregated[0]["period_start"], date(2023, 4, 1))

    def test_adds_balance_sheet_residuals(self) -> None:
        rows = [
            {
                "id": 1,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "acc",
                "period_end": date(2024, 3, 31),
                "period_type": "instant",
                "statement": "balance_sheet",
                "line_item": "assets_current",
                "value": 100,
                "unit": "USD",
            },
            {
                "id": 2,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "acc",
                "period_end": date(2024, 3, 31),
                "period_type": "instant",
                "statement": "balance_sheet",
                "line_item": "cash",
                "value": 40,
                "unit": "USD",
            },
        ]
        aggregated = aggregate_canonical_rows(rows)
        from workers.canonical import _add_balance_sheet_residuals

        enriched = _add_balance_sheet_residuals(aggregated)
        residuals = [r for r in enriched if r.get("line_item") == "other_assets_current"]
        self.assertEqual(len(residuals), 1)
        self.assertAlmostEqual(residuals[0]["value"], 60.0)

    def test_adds_income_and_cash_flow_derivations(self) -> None:
        rows = [
            {
                "id": 1,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "acc",
                "period_start": date(2024, 1, 1),
                "period_end": date(2024, 3, 31),
                "period_type": "duration",
                "statement": "income_statement",
                "line_item": "revenue",
                "value": 100.0,
                "unit": "USD",
            },
            {
                "id": 2,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "acc",
                "period_start": date(2024, 1, 1),
                "period_end": date(2024, 3, 31),
                "period_type": "duration",
                "statement": "income_statement",
                "line_item": "gross_profit",
                "value": 60.0,
                "unit": "USD",
            },
            {
                "id": 3,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "acc",
                "period_start": date(2024, 1, 1),
                "period_end": date(2024, 3, 31),
                "period_type": "duration",
                "statement": "income_statement",
                "line_item": "operating_expenses",
                "value": 30.0,
                "unit": "USD",
            },
            {
                "id": 4,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "acc",
                "period_start": date(2024, 1, 1),
                "period_end": date(2024, 3, 31),
                "period_type": "duration",
                "statement": "income_statement",
                "line_item": "operating_income",
                "value": 20.0,
                "unit": "USD",
            },
            {
                "id": 5,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "acc",
                "period_start": date(2024, 1, 1),
                "period_end": date(2024, 3, 31),
                "period_type": "duration",
                "statement": "cash_flow",
                "line_item": "depreciation_amortization",
                "value": 5.0,
                "unit": "USD",
            },
            {
                "id": 6,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "acc",
                "period_start": date(2024, 1, 1),
                "period_end": date(2024, 3, 31),
                "period_type": "duration",
                "statement": "cash_flow",
                "line_item": "cfo",
                "value": 50.0,
                "unit": "USD",
            },
            {
                "id": 7,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "acc",
                "period_start": date(2024, 1, 1),
                "period_end": date(2024, 3, 31),
                "period_type": "duration",
                "statement": "cash_flow",
                "line_item": "cfi",
                "value": -10.0,
                "unit": "USD",
            },
            {
                "id": 8,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "acc",
                "period_start": date(2024, 1, 1),
                "period_end": date(2024, 3, 31),
                "period_type": "duration",
                "statement": "cash_flow",
                "line_item": "cff",
                "value": -5.0,
                "unit": "USD",
            },
            {
                "id": 9,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "acc",
                "period_start": date(2024, 1, 1),
                "period_end": date(2024, 3, 31),
                "period_type": "duration",
                "statement": "cash_flow",
                "line_item": "fx_on_cash",
                "value": 2.0,
                "unit": "USD",
            },
        ]
        aggregated = aggregate_canonical_rows(rows)
        from workers.canonical import _add_income_statement_derivations, _add_cash_flow_residuals

        enriched = _add_income_statement_derivations(aggregated)
        enriched = _add_cash_flow_residuals(enriched)

        def _get(statement: str, line_item: str) -> float:
            row = next(r for r in enriched if r.get("statement") == statement and r.get("line_item") == line_item)
            return float(row.get("value"))

        self.assertAlmostEqual(_get("income_statement", "cogs"), 40.0)
        self.assertAlmostEqual(_get("income_statement", "total_expenses"), 70.0)
        self.assertAlmostEqual(_get("income_statement", "ebitda"), 25.0)
        self.assertAlmostEqual(_get("cash_flow", "change_in_cash"), 37.0)


class CanonicalFromRealFilingTests(unittest.TestCase):
    def test_aggregates_real_filing_facts(self) -> None:
        from pathlib import Path

        html_path = Path("storage/raw/0001045810/000104581025000230_primary.html")
        self.assertTrue(html_path.is_file(), "Real filing fixture missing")
        facts = parse_inline_xbrl(html_path.read_bytes())
        rows = []
        for i, fact in enumerate(facts, start=1):
            rows.append(
                {
                    "id": i,
                    "ticker": "aapl",
                    "cik": "0001045810",
                    "accession": "acc-real",
                    "period_end": fact.get("period_end"),
                    "period_type": fact.get("period_type"),
                    "statement": fact.get("statement"),
                    "line_item": fact.get("line_item"),
                    "value": fact.get("value"),
                    "unit": fact.get("unit"),
                }
            )
        aggregated = aggregate_canonical_rows(rows)
        self.assertTrue(aggregated, "Aggregated facts should not be empty")

        revenue_rows = [r for r in aggregated if r["line_item"] == "revenue"]
        self.assertTrue(revenue_rows)
        latest_revenue = max(revenue_rows, key=lambda r: r["period_end"])
        self.assertEqual(latest_revenue["period_end"], "2025-10-26")
        self.assertEqual(latest_revenue["period_type"], "duration")
        self.assertAlmostEqual(latest_revenue["value"], 147811000000.0)

        asset_rows = [r for r in aggregated if r["line_item"] == "assets"]
        self.assertTrue(asset_rows)
        latest_assets = max(asset_rows, key=lambda r: r["period_end"])
        self.assertEqual(latest_assets["period_type"], "instant")
        self.assertEqual(latest_assets["period_end"], "2025-10-26")
        self.assertAlmostEqual(latest_assets["value"], 161148000000.0)

    def test_aggregates_second_filing(self) -> None:
        from pathlib import Path

        html_path = Path("storage/raw/0001018724/000101872425000123_primary.html")
        self.assertTrue(html_path.is_file(), "Real filing fixture missing")
        facts = parse_inline_xbrl(html_path.read_bytes())
        rows = []
        for i, fact in enumerate(facts, start=1):
            rows.append(
                {
                    "id": i,
                    "ticker": "amzn",
                    "cik": "0001018724",
                    "accession": "acc-real",
                    "period_end": fact.get("period_end"),
                    "period_type": fact.get("period_type"),
                    "statement": fact.get("statement"),
                    "line_item": fact.get("line_item"),
                    "value": fact.get("value"),
                    "unit": fact.get("unit"),
                }
            )
        aggregated = aggregate_canonical_rows(rows)
        revenue_rows = [r for r in aggregated if r["line_item"] == "revenue"]
        assets_rows = [r for r in aggregated if r["line_item"] == "assets"]
        self.assertTrue(revenue_rows and assets_rows)
        latest_rev = max(revenue_rows, key=lambda r: r["period_end"])
        latest_assets = max(assets_rows, key=lambda r: r["period_end"])
        self.assertEqual(latest_rev["period_end"], "2025-09-30")
        self.assertAlmostEqual(latest_rev["value"], 503538000000.0)
        self.assertEqual(latest_assets["period_type"], "instant")
        self.assertEqual(latest_assets["period_end"], "2025-09-30")
        self.assertAlmostEqual(latest_assets["value"], 727921000000.0)

    def test_aggregates_third_filing(self) -> None:
        from pathlib import Path

        html_path = Path("storage/raw/0000320193/000032019325000079_primary.html")
        self.assertTrue(html_path.is_file(), "Real filing fixture missing")
        facts = parse_inline_xbrl(html_path.read_bytes())
        rows = []
        for i, fact in enumerate(facts, start=1):
            rows.append(
                {
                    "id": i,
                    "ticker": "aapl",
                    "cik": "0000320193",
                    "accession": "acc-real",
                    "period_end": fact.get("period_end"),
                    "period_type": fact.get("period_type"),
                    "statement": fact.get("statement"),
                    "line_item": fact.get("line_item"),
                    "value": fact.get("value"),
                    "unit": fact.get("unit"),
                }
            )
        aggregated = aggregate_canonical_rows(rows)
        revenue_rows = [r for r in aggregated if r["line_item"] == "revenue"]
        self.assertTrue(revenue_rows)
        latest_rev = max(revenue_rows, key=lambda r: r["period_end"])
        self.assertEqual(latest_rev["period_type"], "duration")
        self.assertGreater(latest_rev["value"], 80000000000.0)
        shares_rows = [r for r in aggregated if r["line_item"] == "shares_diluted"]
        cfo_rows = [r for r in aggregated if r["line_item"] == "cfo"]
        self.assertTrue(any(r["value"] for r in shares_rows))
        self.assertTrue(any(r["value"] is not None for r in cfo_rows))


if __name__ == "__main__":
    unittest.main()
