import unittest
from datetime import date
from pathlib import Path

from workers.canonical import aggregate_canonical_rows, log_tie_checks, _align_cash_flow_starts
from workers.parser import parse_inline_xbrl


def _resolve_fixture_path(relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_file():
        return path
    if relative_path.startswith("storage/"):
        alt = Path("/storage") / Path(relative_path).relative_to("storage")
        if alt.is_file():
            return alt
    return path


def _coverage_counts(html_path: Path, period_end: str, ticker: str, cik: str) -> tuple[dict[str, int], int]:
    facts = parse_inline_xbrl(html_path.read_bytes())
    rows = []
    for i, fact in enumerate(facts, start=1):
        rows.append(
            {
                "id": i,
                "ticker": ticker,
                "cik": cik,
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
    by_statement: dict[str, set[str]] = {}
    for row in aggregated:
        if row.get("period_end") != period_end:
            continue
        statement = row.get("statement")
        line_item = row.get("line_item")
        if statement and line_item:
            by_statement.setdefault(statement, set()).add(line_item)
    counts = {statement: len(items) for statement, items in by_statement.items()}
    total = sum(counts.values())
    return counts, total


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

    def test_preserves_source_tag_and_context(self) -> None:
        rows = [
            {
                "id": 1,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "0001",
                "period_start": date(2023, 1, 1),
                "period_end": date(2023, 6, 30),
                "period_type": "duration",
                "statement": "income_statement",
                "line_item": "revenue",
                "value": 100,
                "unit": "usd",
                "xbrl_tag": "us-gaap:Revenues",
                "context_ref": "D2023Q2",
            }
        ]
        aggregated = aggregate_canonical_rows(rows)
        self.assertEqual(len(aggregated), 1)
        self.assertEqual(aggregated[0]["source_xbrl_tag"], "us-gaap:Revenues")
        self.assertEqual(aggregated[0]["source_context_ref"], "D2023Q2")

    def test_prefers_latest_accession_over_shorter_duration(self) -> None:
        rows = [
            {
                "id": 1,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "0002",
                "period_start": date(2023, 1, 1),
                "period_end": date(2023, 6, 30),
                "period_type": "duration",
                "statement": "cash_flow",
                "line_item": "cfo",
                "value": 100,
                "unit": "usd",
            },
            {
                "id": 2,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "0001",
                "period_start": date(2023, 4, 1),
                "period_end": date(2023, 6, 30),
                "period_type": "duration",
                "statement": "cash_flow",
                "line_item": "cfo",
                "value": 50,
                "unit": "usd",
            },
            {
                "id": 3,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "0002",
                "period_start": date(2023, 4, 1),
                "period_end": date(2023, 6, 30),
                "period_type": "duration",
                "statement": "cash_flow",
                "line_item": "cfo",
                "value": 60,
                "unit": "usd",
            },
        ]
        aggregated = aggregate_canonical_rows(rows)
        self.assertEqual(len(aggregated), 1)
        self.assertEqual(aggregated[0]["value"], 60.0)
        self.assertEqual(aggregated[0]["accession"], "0002")
        self.assertEqual(aggregated[0]["period_start"], date(2023, 4, 1))


class TieCheckTests(unittest.TestCase):
    def test_balance_sheet_prefers_liabilities_equity(self) -> None:
        period = date(2024, 12, 31)
        aggregated = [
            {"period_end": period, "statement": "balance_sheet", "line_item": "assets", "value": 100.0},
            {"period_end": period, "statement": "balance_sheet", "line_item": "liabilities", "value": 60.0},
            {"period_end": period, "statement": "balance_sheet", "line_item": "equity", "value": 30.0},
            {"period_end": period, "statement": "balance_sheet", "line_item": "liabilities_equity", "value": 100.0},
        ]
        violations = log_tie_checks(aggregated, strict=False)
        self.assertFalse(any("Balance sheet tie off" in msg for msg in violations))

    def test_balance_sheet_fallbacks_to_liabilities_and_equity(self) -> None:
        period = date(2024, 12, 31)
        aggregated = [
            {"period_end": period, "statement": "balance_sheet", "line_item": "assets", "value": 100.0},
            {"period_end": period, "statement": "balance_sheet", "line_item": "liabilities", "value": 60.0},
            {"period_end": period, "statement": "balance_sheet", "line_item": "equity", "value": 30.0},
        ]
        violations = log_tie_checks(aggregated, strict=False)
        self.assertTrue(any("Balance sheet tie off" in msg for msg in violations))

    def test_detects_cash_flow_violation(self) -> None:
        period = date(2024, 12, 31)
        aggregated = [
            {"period_end": period, "statement": "cash_flow", "line_item": "cfo", "value": 10.0},
            {"period_end": period, "statement": "cash_flow", "line_item": "cfi", "value": -3.0},
            {"period_end": period, "statement": "cash_flow", "line_item": "cff", "value": -2.0},
            {"period_end": period, "statement": "cash_flow", "line_item": "change_in_cash", "value": 4.0},
        ]
        violations = log_tie_checks(aggregated, strict=False)
        self.assertTrue(any("Cash flow tie off" in msg for msg in violations))

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


class CashFlowAlignmentTests(unittest.TestCase):
    def test_aligns_cash_flow_items_to_cfo_period_start(self) -> None:
        period_end = date(2023, 6, 30)
        rows = [
            {
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "0002",
                "period_start": date(2023, 4, 1),
                "period_end": period_end,
                "period_type": "duration",
                "statement": "cash_flow",
                "line_item": "cfo",
                "value": 100.0,
                "unit": "USD",
                "source_fact_id": 1,
            },
            {
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "0002",
                "period_start": date(2023, 1, 1),
                "period_end": period_end,
                "period_type": "duration",
                "statement": "cash_flow",
                "line_item": "cfi",
                "value": -50.0,
                "unit": "USD",
                "source_fact_id": 2,
            },
            {
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "0002",
                "period_start": date(2023, 1, 1),
                "period_end": period_end,
                "period_type": "duration",
                "statement": "cash_flow",
                "line_item": "cff",
                "value": -30.0,
                "unit": "USD",
                "source_fact_id": 3,
            },
            {
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "0002",
                "period_start": date(2023, 1, 1),
                "period_end": period_end,
                "period_type": "duration",
                "statement": "cash_flow",
                "line_item": "change_in_cash",
                "value": 20.0,
                "unit": "USD",
                "source_fact_id": 4,
            },
        ]
        fact_rows = [
            {
                "id": 10,
                "accession": "0002",
                "period_start": date(2023, 4, 1),
                "period_end": period_end,
                "period_type": "duration",
                "statement": "cash_flow",
                "line_item": "cfi",
                "value": -40.0,
                "unit": "USD",
            },
            {
                "id": 11,
                "accession": "0002",
                "period_start": date(2023, 4, 1),
                "period_end": period_end,
                "period_type": "duration",
                "statement": "cash_flow",
                "line_item": "cff",
                "value": -20.0,
                "unit": "USD",
            },
            {
                "id": 12,
                "accession": "0002",
                "period_start": date(2023, 4, 1),
                "period_end": period_end,
                "period_type": "duration",
                "statement": "cash_flow",
                "line_item": "change_in_cash",
                "value": 40.0,
                "unit": "USD",
            },
        ]
        aligned = _align_cash_flow_starts(rows, fact_rows)
        line_map = {row["line_item"]: row for row in aligned if row["statement"] == "cash_flow"}
        self.assertEqual(line_map["cfi"]["period_start"], date(2023, 4, 1))
        self.assertEqual(line_map["cfi"]["value"], -40.0)
        self.assertEqual(line_map["cff"]["period_start"], date(2023, 4, 1))
        self.assertEqual(line_map["cff"]["value"], -20.0)
        self.assertEqual(line_map["change_in_cash"]["period_start"], date(2023, 4, 1))
        self.assertEqual(line_map["change_in_cash"]["value"], 40.0)

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

    def test_derives_gross_profit_and_operating_expenses(self) -> None:
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
                "line_item": "cogs",
                "value": 40.0,
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
                "line_item": "operating_income",
                "value": 20.0,
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
                "line_item": "total_expenses",
                "value": 70.0,
                "unit": "USD",
            },
        ]
        aggregated = aggregate_canonical_rows(rows)
        from workers.canonical import _add_income_statement_derivations

        enriched = _add_income_statement_derivations(aggregated)
        gross_profit = next(r for r in enriched if r["line_item"] == "gross_profit")
        operating_expenses = next(r for r in enriched if r["line_item"] == "operating_expenses")
        self.assertAlmostEqual(gross_profit["value"], 60.0)
        self.assertAlmostEqual(operating_expenses["value"], 30.0)

    def test_derives_liabilities_from_equity_total(self) -> None:
        rows = [
            {
                "id": 1,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "acc",
                "period_end": date(2024, 3, 31),
                "period_type": "instant",
                "statement": "balance_sheet",
                "line_item": "liabilities_equity",
                "value": 100.0,
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
                "line_item": "equity",
                "value": 30.0,
                "unit": "USD",
            },
        ]
        aggregated = aggregate_canonical_rows(rows)
        from workers.canonical import _add_balance_sheet_residuals

        enriched = _add_balance_sheet_residuals(aggregated)
        liabilities = next(r for r in enriched if r["line_item"] == "liabilities")
        self.assertAlmostEqual(liabilities["value"], 70.0)

    def test_derives_change_working_capital_from_components(self) -> None:
        rows = [
            {
                "id": 1,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "acc",
                "period_start": date(2024, 1, 1),
                "period_end": date(2024, 3, 31),
                "period_type": "duration",
                "statement": "cash_flow",
                "line_item": "cfo",
                "value": 10.0,
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
                "statement": "cash_flow",
                "line_item": "change_accounts_receivable",
                "value": -5.0,
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
                "statement": "cash_flow",
                "line_item": "change_inventory",
                "value": -2.0,
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
                "statement": "cash_flow",
                "line_item": "change_accounts_payable",
                "value": 4.0,
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
                "line_item": "change_accrued_expenses",
                "value": 1.0,
                "unit": "USD",
            },
        ]
        aggregated = aggregate_canonical_rows(rows)
        from workers.canonical import _add_cash_flow_residuals

        enriched = _add_cash_flow_residuals(aggregated)
        wc_row = next(r for r in enriched if r.get("line_item") == "change_working_capital")
        self.assertAlmostEqual(wc_row["value"], -2.0)

    def test_aligns_change_in_cash_to_cfo_start(self) -> None:
        rows = [
            {
                "id": 1,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "acc",
                "period_start": date(2025, 7, 1),
                "period_end": date(2025, 9, 30),
                "period_type": "duration",
                "statement": "cash_flow",
                "line_item": "cfo",
                "value": 10.0,
                "unit": "USD",
            },
            {
                "id": 2,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "acc",
                "period_start": date(2024, 10, 1),
                "period_end": date(2025, 9, 30),
                "period_type": "duration",
                "statement": "cash_flow",
                "line_item": "change_in_cash",
                "value": 5.0,
                "unit": "USD",
            },
            {
                "id": 3,
                "ticker": "demo",
                "cik": "0000000000",
                "accession": "acc",
                "period_start": date(2025, 7, 1),
                "period_end": date(2025, 9, 30),
                "period_type": "duration",
                "statement": "cash_flow",
                "line_item": "change_in_cash",
                "value": 8.0,
                "unit": "USD",
            },
        ]
        aggregated = aggregate_canonical_rows(rows)
        from workers.canonical import _align_cash_flow_starts

        aligned = _align_cash_flow_starts(aggregated, rows)
        change_row = next(r for r in aligned if r.get("line_item") == "change_in_cash")
        self.assertEqual(change_row["period_start"], date(2025, 7, 1))
        self.assertAlmostEqual(change_row["value"], 8.0)


class CanonicalFromRealFilingTests(unittest.TestCase):
    def test_aggregates_real_filing_facts(self) -> None:
        html_path = _resolve_fixture_path("storage/raw/0001045810/000104581025000230_primary.html")
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
        html_path = _resolve_fixture_path("storage/raw/0001018724/000101872425000123_primary.html")
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
        html_path = _resolve_fixture_path("storage/raw/0000320193/000032019325000079_primary.html")
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

    def test_real_filings_include_core_line_items(self) -> None:
        fixtures = [
            ("AAPL", "0000320193", _resolve_fixture_path("storage/raw/0000320193/000032019325000079_primary.html")),
            ("NVDA", "0001045810", _resolve_fixture_path("storage/raw/0001045810/000104581025000230_primary.html")),
            ("AMZN", "0001018724", _resolve_fixture_path("storage/raw/0001018724/000101872425000123_primary.html")),
        ]
        required_by_statement = {
            "income_statement": {"revenue", "net_income"},
            "balance_sheet": {"assets", "equity"},
            "cash_flow": {"cfo"},
        }

        for ticker, cik, html_path in fixtures:
            self.assertTrue(html_path.is_file(), "Real filing fixture missing")
            facts = parse_inline_xbrl(html_path.read_bytes())
            rows = []
            for i, fact in enumerate(facts, start=1):
                rows.append(
                    {
                        "id": i,
                        "ticker": ticker,
                        "cik": cik,
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
            by_statement = {}
            for row in aggregated:
                statement = row.get("statement")
                line_item = row.get("line_item")
                if statement and line_item:
                    by_statement.setdefault(statement, set()).add(line_item)
            for statement, required in required_by_statement.items():
                missing = required - by_statement.get(statement, set())
                self.assertFalse(missing, f"{ticker} missing {sorted(missing)} in {statement}")

    def test_regression_coverage_aapl_2023_q2_q3(self) -> None:
        cases = [
            (
                _resolve_fixture_path("storage/raw/0000320193/000032019323000064_primary.html"),
                "2023-04-01",
                {"income_statement": 15, "balance_sheet": 20, "cash_flow": 14},
                50,
            ),
            (
                _resolve_fixture_path("storage/raw/0000320193/000032019323000077_primary.html"),
                "2023-07-01",
                {"income_statement": 15, "balance_sheet": 20, "cash_flow": 15},
                50,
            ),
        ]
        for html_path, period_end, floors, total_floor in cases:
            self.assertTrue(html_path.is_file(), f"Fixture missing: {html_path}")
            counts, total = _coverage_counts(html_path, period_end, "AAPL", "0000320193")
            for statement, floor in floors.items():
                self.assertGreaterEqual(
                    counts.get(statement, 0),
                    floor,
                    f"AAPL {period_end} {statement} coverage regression",
                )
            self.assertGreaterEqual(total, total_floor, f"AAPL {period_end} total coverage regression")

    def test_regression_coverage_amzn_2023_q2(self) -> None:
        html_path = _resolve_fixture_path("storage/raw/0001018724/000101872423000012_primary.html")
        self.assertTrue(html_path.is_file(), f"Fixture missing: {html_path}")
        counts, total = _coverage_counts(html_path, "2023-06-30", "AMZN", "0001018724")
        floors = {"income_statement": 14, "balance_sheet": 19, "cash_flow": 12}
        for statement, floor in floors.items():
            self.assertGreaterEqual(
                counts.get(statement, 0),
                floor,
                f"AMZN 2023-06-30 {statement} coverage regression",
            )
        self.assertGreaterEqual(total, 47, "AMZN 2023-06-30 total coverage regression")

    def test_regression_coverage_nvda_2023_q1(self) -> None:
        html_path = _resolve_fixture_path("storage/raw/0001045810/000104581023000093_primary.html")
        self.assertTrue(html_path.is_file(), f"Fixture missing: {html_path}")
        counts, total = _coverage_counts(html_path, "2023-04-30", "NVDA", "0001045810")
        floors = {"income_statement": 15, "balance_sheet": 21, "cash_flow": 10}
        for statement, floor in floors.items():
            self.assertGreaterEqual(
                counts.get(statement, 0),
                floor,
                f"NVDA 2023-04-30 {statement} coverage regression",
            )
        self.assertGreaterEqual(total, 48, "NVDA 2023-04-30 total coverage regression")


if __name__ == "__main__":
    unittest.main()
