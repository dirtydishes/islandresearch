import unittest

from workers.tag_map import TAG_MAP


class TagMapTests(unittest.TestCase):
    def test_includes_common_synonyms(self) -> None:
        expected = [
            "us-gaap:TotalRevenues",
            "us-gaap:TotalRevenue",
            "us-gaap:CostOfSales",
            "us-gaap:CostOfProductsSold",
            "us-gaap:RevenueFromContractWithCustomer",
            "us-gaap:TotalOperatingExpenses",
            "us-gaap:IncomeLossFromOperations",
            "us-gaap:ProvisionForIncomeTaxes",
            "us-gaap:NetIncomeLossAttributableToParent",
            "us-gaap:NetIncomeLossAvailableToCommonStockholders",
            "us-gaap:AccountsReceivableNet",
            "us-gaap:DeferredRevenueCurrent",
            "us-gaap:AccruedLiabilitiesAndOtherCurrent",
            "us-gaap:AccruedExpensesAndOtherCurrentLiabilities",
            "us-gaap:OtherCurrentLiabilities",
            "us-gaap:OtherNoncurrentLiabilities",
            "us-gaap:ShortTermDebt",
            "us-gaap:LongTermDebt",
            "us-gaap:NoncontrollingInterest",
            "us-gaap:DepreciationAndAmortization",
            "us-gaap:Depreciation",
            "us-gaap:CapitalExpenditures",
            "us-gaap:CashAndCashEquivalents",
            "us-gaap:CashEquivalentsAtCarryingValue",
            "us-gaap:Cash",
            "us-gaap:MarketableSecuritiesNoncurrent",
            "us-gaap:AvailableForSaleSecuritiesNoncurrent",
            "us-gaap:PaymentsToAcquireBusinessesAndIntangibles",
            "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
            "us-gaap:DividendsCommonStockCash",
            "us-gaap:DividendsPaid",
            "us-gaap:StockRepurchasedAndRetiredDuringPeriodValue",
            "us-gaap:PaymentsForRepurchaseOfEquity",
            "us-gaap:IncreaseDecreaseInAccountsReceivable",
            "us-gaap:IncreaseDecreaseInAccountsPayable",
            "us-gaap:TreasuryStockCommonValue",
        ]
        for tag in expected:
            self.assertIn(tag, TAG_MAP)


if __name__ == "__main__":
    unittest.main()
