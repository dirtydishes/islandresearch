import unittest

from workers.jobs.fetch_filings import _select_missing_filings, _select_recent_accessions


class FetchFilingsTests(unittest.TestCase):
    def test_select_recent_accessions_filters_allowed_forms(self) -> None:
        submissions = {
            "filings": {
                "recent": {
                    "form": ["8-K", "10-Q", "10-K", "S-3"],
                    "accessionNumber": ["acc-1", "acc-2", "acc-3", "acc-4"],
                    "filingDate": ["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01"],
                }
            }
        }
        selected = _select_recent_accessions(submissions, limit=5)
        self.assertEqual(selected, ["acc-2", "acc-3"])

    def test_select_missing_filings_skips_existing(self) -> None:
        submissions = {
            "filings": {
                "recent": {
                    "form": ["10-Q", "10-K", "8-K", "10-Q"],
                    "accessionNumber": ["acc-1", "acc-2", "acc-3", "acc-4"],
                    "filingDate": ["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01"],
                }
            }
        }
        selected = _select_missing_filings(submissions, {"acc-1"}, limit=2)
        accessions = [acc for _, acc, _ in selected]
        self.assertEqual(accessions, ["acc-2", "acc-4"])


if __name__ == "__main__":
    unittest.main()
