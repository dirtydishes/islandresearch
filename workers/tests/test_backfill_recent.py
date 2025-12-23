import unittest
from unittest.mock import patch

from workers.jobs import backfill_recent


class BackfillRecentTests(unittest.TestCase):
    def test_skips_materialization_when_no_new_filings(self) -> None:
        supported = {"AAPL": "0000320193"}
        fetch_result = {"ticker": "AAPL", "cik": "0000320193", "saved": []}
        with patch("workers.jobs.backfill_recent.list_supported_tickers", return_value=supported), patch(
            "workers.jobs.backfill_recent.fetch_missing_filings", return_value=fetch_result
        ), patch("workers.jobs.backfill_recent.parse_filing") as mocked_parse, patch(
            "workers.jobs.backfill_recent.run_materialization"
        ) as mocked_materialize:
            result = backfill_recent.backfill_recent(limit=2)

        mocked_parse.assert_not_called()
        mocked_materialize.assert_not_called()
        self.assertEqual(result["success"], 1)
        self.assertEqual(result["failed"], 0)

    def test_parses_new_filings_and_materializes(self) -> None:
        saved = [{"accession": "0001", "primary_path": "/tmp/a.html"}]
        fetch_result = {"ticker": "AAPL", "cik": "0000320193", "saved": saved}
        with patch("workers.jobs.backfill_recent.fetch_missing_filings", return_value=fetch_result), patch(
            "workers.jobs.backfill_recent.parse_filing", return_value={"inserted": 10, "dropped": 2}
        ) as mocked_parse, patch(
            "workers.jobs.backfill_recent.run_materialization", return_value={"inserted": 5}
        ) as mocked_materialize:
            result = backfill_recent.backfill_recent(tickers=["aapl"], limit=1, strict_ties=True)

        mocked_parse.assert_called_once_with("0001", "0000320193", "AAPL", "/tmp/a.html")
        mocked_materialize.assert_called_once_with("AAPL", strict_ties=True)
        self.assertEqual(result["success"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["results"][0]["canonical_inserted"], 5)
