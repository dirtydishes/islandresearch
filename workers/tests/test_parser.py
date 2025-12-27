import unittest
from pathlib import Path

from workers.parser import parse_inline_xbrl


SAMPLE_INLINE = b"""
<html>
  <body>
    <xbrli:context id="D2023Q2">
      <xbrli:entity>
        <xbrli:identifier scheme="http://www.sec.gov/CIK">0000000000</xbrli:identifier>
      </xbrli:entity>
      <xbrli:period>
        <xbrli:startDate>2023-03-27</xbrli:startDate>
        <xbrli:endDate>2023-06-24</xbrli:endDate>
      </xbrli:period>
    </xbrli:context>
    <xbrli:context id="I2023">
      <xbrli:entity>
        <xbrli:identifier scheme="http://www.sec.gov/CIK">0000000000</xbrli:identifier>
      </xbrli:entity>
      <xbrli:period>
        <xbrli:instant>2023-06-24</xbrli:instant>
      </xbrli:period>
    </xbrli:context>
    <ix:nonfraction name="us-gaap:Revenues" contextref="D2023Q2" unitref="iso4217:USD" decimals="-6">9,000</ix:nonfraction>
    <ix:nonfraction name="us-gaap:GrossProfit" contextref="D2023Q2" unitref="usd" decimals="-6">3,600</ix:nonfraction>
    <ix:nonfraction name="us-gaap:Assets" contextref="I2023" unitref="iso4217:usd" scale="3">100</ix:nonfraction>
    <ix:nonfraction name="us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding" contextref="D2023Q2" unitref="shares" decimals="0">50</ix:nonfraction>
  </body>
</html>
"""

def _resolve_fixture_path(relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_file():
        return path
    if relative_path.startswith("storage/"):
        alt = Path("/storage") / Path(relative_path).relative_to("storage")
        if alt.is_file():
            return alt
    return path


class ParseInlineXBRLTests(unittest.TestCase):
    def test_extracts_target_facts_with_contexts_and_units(self) -> None:
        facts = parse_inline_xbrl(SAMPLE_INLINE)
        self.assertEqual(len(facts), 4)

        revenue = next(f for f in facts if f["line_item"] == "revenue")
        self.assertEqual(revenue["statement"], "income_statement")
        self.assertEqual(revenue["period_end"], "2023-06-24")
        self.assertEqual(revenue["period_type"], "duration")
        self.assertEqual(revenue["unit"], "USD")
        self.assertEqual(revenue["value"], 9000.0)

        assets = next(f for f in facts if f["line_item"] == "assets")
        self.assertEqual(assets["statement"], "balance_sheet")
        self.assertEqual(assets["period_type"], "instant")
        self.assertEqual(assets["unit"], "USD")
        self.assertEqual(assets["value"], 100000.0)

        shares = next(f for f in facts if f["line_item"] == "shares_diluted")
        self.assertEqual(shares["unit"], "SHARES")
        self.assertEqual(shares["period_type"], "duration")
        self.assertEqual(shares["value"], 50.0)

    def test_respects_ix_sign_attribute(self) -> None:
        sample = b"""
        <html>
          <body>
            <xbrli:context id="D2023Q2">
              <xbrli:entity>
                <xbrli:identifier scheme="http://www.sec.gov/CIK">0000000000</xbrli:identifier>
              </xbrli:entity>
              <xbrli:period>
                <xbrli:startDate>2023-03-27</xbrli:startDate>
                <xbrli:endDate>2023-06-24</xbrli:endDate>
              </xbrli:period>
            </xbrli:context>
            <ix:nonfraction name="us-gaap:NetCashProvidedByUsedInInvestingActivities"
              contextref="D2023Q2" unitref="usd" sign="-" decimals="0">100</ix:nonfraction>
          </body>
        </html>
        """
        facts = parse_inline_xbrl(sample)
        cfi = next(f for f in facts if f["line_item"] == "cfi")
        self.assertEqual(cfi["value"], -100.0)


    def test_normalizes_unit_ref_from_unit_definitions(self) -> None:
        sample = b"""
        <html>
          <body>
            <xbrli:unit id="usdPerShare">
              <xbrli:divide>
                <xbrli:unitNumerator><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unitNumerator>
                <xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator>
              </xbrli:divide>
            </xbrli:unit>
            <xbrli:context id="D2023Q2">
              <xbrli:entity>
                <xbrli:identifier scheme="http://www.sec.gov/CIK">0000000000</xbrli:identifier>
              </xbrli:entity>
              <xbrli:period>
                <xbrli:startDate>2023-03-27</xbrli:startDate>
                <xbrli:endDate>2023-06-24</xbrli:endDate>
              </xbrli:period>
            </xbrli:context>
            <ix:nonfraction name="us-gaap:EarningsPerShareDiluted" contextref="D2023Q2" unitref="usdPerShare" decimals="2">1.23</ix:nonfraction>
          </body>
        </html>
        """
        facts = parse_inline_xbrl(sample)
        eps = next(f for f in facts if f["line_item"] == "eps_diluted")
        self.assertEqual(eps["unit"], "USDPERSHARE")
        self.assertEqual(eps["value"], 1.23)

class ParseRealFilingTests(unittest.TestCase):
    def test_parses_real_primary_html(self) -> None:
        html_path = _resolve_fixture_path("storage/raw/0001045810/000104581025000230_primary.html")
        self.assertTrue(html_path.is_file(), "Real filing fixture missing")
        facts = parse_inline_xbrl(html_path.read_bytes())

        def find_line(line_item: str) -> dict:
            return next(f for f in facts if f["line_item"] == line_item)

        revenue = find_line("revenue")
        net_income = find_line("net_income")
        assets = find_line("assets")
        cfo = find_line("cfo")

        self.assertEqual(revenue["period_end"], "2025-10-26")
        self.assertEqual(revenue["period_type"], "duration")
        self.assertEqual(revenue["unit"], "USD")
        self.assertAlmostEqual(revenue["value"], 57006000000.0)

        self.assertEqual(net_income["period_type"], "duration")
        self.assertAlmostEqual(net_income["value"], 31910000000.0)

        self.assertEqual(assets["period_type"], "instant")
        self.assertEqual(assets["period_end"], "2025-10-26")
        self.assertAlmostEqual(assets["value"], 161148000000.0)

        self.assertEqual(cfo["period_type"], "duration")
        self.assertEqual(cfo["unit"], "USD")
        self.assertAlmostEqual(cfo["value"], 66530000000.0)

    def test_parses_second_real_filing(self) -> None:
        html_path = _resolve_fixture_path("storage/raw/0001018724/000101872425000123_primary.html")
        self.assertTrue(html_path.is_file(), "Real filing fixture missing")
        facts = parse_inline_xbrl(html_path.read_bytes())
        def find_line(line_item: str) -> dict:
            return next(f for f in facts if f["line_item"] == line_item)

        revenue_values = [f["value"] for f in facts if f["line_item"] == "revenue"]
        net_income_values = [f["value"] for f in facts if f["line_item"] == "net_income"]
        assets_values = [(f["value"], f["period_type"]) for f in facts if f["line_item"] == "assets"]

        self.assertTrue(any(v == 503538000000.0 for v in revenue_values))
        self.assertTrue(any(v == 56478000000.0 for v in net_income_values))
        self.assertTrue(any(v == 727921000000.0 and ptype == "instant" for v, ptype in assets_values))

    def test_parses_third_real_filing(self) -> None:
        html_path = _resolve_fixture_path("storage/raw/0000320193/000032019325000079_primary.html")
        self.assertTrue(html_path.is_file(), "Real filing fixture missing")
        facts = parse_inline_xbrl(html_path.read_bytes())
        revenue_values = [f["value"] for f in facts if f["line_item"] == "revenue"]
        net_income_values = [f["value"] for f in facts if f["line_item"] == "net_income"]
        assets_values = [(f["value"], f["period_type"]) for f in facts if f["line_item"] == "assets"]
        share_values = [f["value"] for f in facts if f["line_item"] == "shares_diluted"]
        cfo_values = [f["value"] for f in facts if f["line_item"] == "cfo"]
        capex_values = [f["value"] for f in facts if f["line_item"] == "capex"]

        self.assertTrue(any(v >= 80000000000.0 for v in revenue_values))
        self.assertTrue(any(v >= 20000000000.0 for v in net_income_values))
        self.assertTrue(any(ptype == "instant" for _, ptype in assets_values))
        self.assertTrue(any(v > 0 for v in share_values))
        self.assertTrue(any(v != 0 for v in capex_values))
        self.assertTrue(any(v is not None for v in cfo_values))


class ParseStatementParityTests(unittest.TestCase):
    def _assert_core_line_items(self, facts, ticker: str) -> None:
        line_items = {f["line_item"] for f in facts}
        for required in ("revenue", "operating_income", "net_income"):
            self.assertIn(required, line_items, f"{ticker} missing income statement core line item: {required}")

        self.assertIn("assets", line_items, f"{ticker} missing balance sheet core line item: assets")
        self.assertIn("equity", line_items, f"{ticker} missing balance sheet core line item: equity")
        self.assertIn("cash", line_items, f"{ticker} missing balance sheet core line item: cash")
        liabilities_ok = (
            "liabilities" in line_items
            or "liabilities_equity" in line_items
            or ("liabilities_current" in line_items and "liabilities_noncurrent" in line_items)
        )
        self.assertTrue(liabilities_ok, f"{ticker} missing balance sheet liabilities coverage")

        for required in ("cfo", "cfi", "cff", "capex", "change_in_cash"):
            self.assertIn(required, line_items, f"{ticker} missing cash flow core line item: {required}")

    def test_statement_core_line_items_for_fixtures(self) -> None:
        fixtures = {
            "AAPL": _resolve_fixture_path("storage/raw/0000320193/000032019325000079_primary.html"),
            "AMZN": _resolve_fixture_path("storage/raw/0001018724/000101872425000123_primary.html"),
            "NVDA": _resolve_fixture_path("storage/raw/0001045810/000104581025000230_primary.html"),
        }
        for ticker, path in fixtures.items():
            self.assertTrue(path.is_file(), f"Fixture missing for {ticker}: {path}")
            facts = parse_inline_xbrl(path.read_bytes())
            self._assert_core_line_items(facts, ticker)


class ParseContextsWithSegmentsTests(unittest.TestCase):
    def test_keeps_allowed_segment_dimensions_and_drops_disallowed(self) -> None:
        sample = b"""
        <html>
          <body>
            <xbrli:context id="ctxAllowed">
              <xbrli:entity>
                <xbrli:identifier scheme="http://www.sec.gov/CIK">0000000000</xbrli:identifier>
                <xbrli:segment>
                  <xbrldi:explicitMember dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonStockMember</xbrldi:explicitMember>
                </xbrli:segment>
              </xbrli:entity>
              <xbrli:period><xbrli:instant>2023-12-31</xbrli:instant></xbrli:period>
            </xbrli:context>
            <xbrli:context id="ctxBlocked">
              <xbrli:entity>
                <xbrli:identifier scheme="http://www.sec.gov/CIK">0000000000</xbrli:identifier>
                <xbrli:segment>
                  <xbrldi:explicitMember dimension="custom:BusinessSegmentAxis">custom:SegmentAMember</xbrldi:explicitMember>
                </xbrli:segment>
              </xbrli:entity>
              <xbrli:period><xbrli:instant>2023-12-31</xbrli:instant></xbrli:period>
            </xbrli:context>
            <xbrli:context id="ctxConsolidated">
              <xbrli:entity>
                <xbrli:identifier scheme="http://www.sec.gov/CIK">0000000000</xbrli:identifier>
                <xbrli:segment>
                  <xbrldi:explicitMember dimension="srt:ConsolidationItemsAxis">us-gaap:CorporateNonSegmentMember</xbrldi:explicitMember>
                </xbrli:segment>
              </xbrli:entity>
              <xbrli:period><xbrli:instant>2023-12-31</xbrli:instant></xbrli:period>
            </xbrli:context>
            <xbrli:context id="ctxSegmented">
              <xbrli:entity>
                <xbrli:identifier scheme="http://www.sec.gov/CIK">0000000000</xbrli:identifier>
                <xbrli:segment>
                  <xbrldi:explicitMember dimension="srt:ConsolidationItemsAxis">us-gaap:OperatingSegmentsMember</xbrldi:explicitMember>
                </xbrli:segment>
              </xbrli:entity>
              <xbrli:period><xbrli:instant>2023-12-31</xbrli:instant></xbrli:period>
            </xbrli:context>
            <ix:nonFraction name="us-gaap:CommonStockSharesOutstanding" contextRef="ctxAllowed" unitRef="shares" decimals="0">1,000</ix:nonFraction>
            <ix:nonFraction name="us-gaap:CashAndCashEquivalentsAtCarryingValue" contextRef="ctxBlocked" unitRef="usd" decimals="0">50</ix:nonFraction>
            <ix:nonFraction name="us-gaap:CashAndCashEquivalentsAtCarryingValue" contextRef="ctxConsolidated" unitRef="usd" decimals="0">75</ix:nonFraction>
            <ix:nonFraction name="us-gaap:CashAndCashEquivalentsAtCarryingValue" contextRef="ctxSegmented" unitRef="usd" decimals="0">125</ix:nonFraction>
          </body>
        </html>
        """
        facts = parse_inline_xbrl(sample)
        shares = [f for f in facts if f["line_item"] == "shares_outstanding"]
        cash = [f for f in facts if f["line_item"] == "cash"]
        self.assertEqual(len(shares), 1)
        self.assertEqual(shares[0]["period_end"], "2023-12-31")
        self.assertEqual(shares[0]["unit"], "SHARES")
        self.assertEqual(len(cash), 1, "Only consolidated cash context should remain")
        self.assertEqual(cash[0]["value"], 75.0)

if __name__ == "__main__":
    unittest.main()
