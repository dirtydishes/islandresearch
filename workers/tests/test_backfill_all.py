import unittest
from unittest.mock import patch

from workers.jobs import backfill_all


class BackfillAllTests(unittest.TestCase):
    def test_uses_supported_tickers_when_none_provided(self) -> None:
        supported = {"AAPL": "0000320193", "MSFT": "0000789019"}
        with patch("workers.jobs.backfill_all.list_supported_tickers", return_value=supported), patch(
            "workers.jobs.backfill_all.backfill_ticker", return_value={"ticker": "AAPL"}
        ) as mocked:
            result = backfill_all.backfill_all(limit=2, max_tickers=1, strict_ties=False)

        mocked.assert_called_once()
        args, kwargs = mocked.call_args
        self.assertEqual(args[0], "AAPL")
        self.assertEqual(kwargs["limit"], 2)
        self.assertFalse(kwargs["strict_ties"])
        self.assertEqual(result["success"], 1)
        self.assertEqual(result["failed"], 0)

    def test_uses_explicit_tickers(self) -> None:
        with patch("workers.jobs.backfill_all.backfill_ticker", return_value={"ticker": "NVDA"}) as mocked:
            result = backfill_all.backfill_all(tickers=["nvda", "amzn"], limit=1)

        self.assertEqual(mocked.call_count, 2)
        called = [call.args[0] for call in mocked.call_args_list]
        self.assertEqual(called, ["NVDA", "AMZN"])
        self.assertEqual(result["success"], 2)
