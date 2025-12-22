import unittest

from workers.tag_map import TAG_MAP


class TagMapTests(unittest.TestCase):
    def test_includes_common_synonyms(self) -> None:
        expected = [
            "us-gaap:TotalRevenues",
            "us-gaap:CostOfSales",
            "us-gaap:AccountsReceivableNet",
            "us-gaap:DeferredRevenueCurrent",
            "us-gaap:AccruedLiabilitiesAndOtherCurrent",
            "us-gaap:NoncontrollingInterest",
            "us-gaap:DepreciationAndAmortization",
            "us-gaap:PaymentsToAcquireBusinessesAndIntangibles",
            "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
        ]
        for tag in expected:
            self.assertIn(tag, TAG_MAP)


if __name__ == "__main__":
    unittest.main()
