import unittest

from workers.tag_map import TAG_MAP


class TagMapTests(unittest.TestCase):
    def test_includes_common_synonyms(self) -> None:
        expected = [
            "us-gaap:TotalRevenues",
            "us-gaap:TotalRevenue",
            "us-gaap:CostOfSales",
            "us-gaap:CostOfProductsSold",
            "us-gaap:AccountsReceivableNet",
            "us-gaap:DeferredRevenueCurrent",
            "us-gaap:AccruedLiabilitiesAndOtherCurrent",
            "us-gaap:NoncontrollingInterest",
            "us-gaap:DepreciationAndAmortization",
            "us-gaap:CashAndCashEquivalents",
            "us-gaap:CashEquivalentsAtCarryingValue",
            "us-gaap:Cash",
            "us-gaap:MarketableSecuritiesNoncurrent",
            "us-gaap:PaymentsToAcquireBusinessesAndIntangibles",
            "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
            "us-gaap:DividendsCommonStockCash",
            "us-gaap:StockRepurchasedAndRetiredDuringPeriodValue",
        ]
        for tag in expected:
            self.assertIn(tag, TAG_MAP)


if __name__ == "__main__":
    unittest.main()
