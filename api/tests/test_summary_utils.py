import sys
from pathlib import Path

# Make app module importable when running tests from repo root.
sys.path.append(str(Path(__file__).resolve().parents[1] / "app"))

import math
import unittest

from summary_utils import (
    DEFAULT_DRIVERS,
    SCENARIO_CONFIG,
    _apply_scenario,
    _avg_growth,
    _avg_margin,
    _compute_growth,
    _get_value,
    _next_period_end,
    _safe_div,
    build_forecast,
    build_forecast_summary,
    compute_backtest_metrics,
    compute_coverage,
    compute_drivers,
    compute_revenue_backtest,
    compute_tie_checks,
    filter_allowed,
)


class HelperFunctionTests(unittest.TestCase):
    def test_safe_div_normal(self) -> None:
        self.assertAlmostEqual(_safe_div(10.0, 5.0), 2.0)

    def test_safe_div_zero_denominator(self) -> None:
        self.assertIsNone(_safe_div(10.0, 0))

    def test_safe_div_none_values(self) -> None:
        self.assertIsNone(_safe_div(None, 5.0))
        self.assertIsNone(_safe_div(10.0, None))

    def test_get_value_extracts_nested(self) -> None:
        values = {"revenue": {"value": 100.0, "unit": "USD"}}
        self.assertEqual(_get_value(values, "revenue"), 100.0)

    def test_get_value_missing_key(self) -> None:
        values = {"revenue": {"value": 100.0, "unit": "USD"}}
        self.assertIsNone(_get_value(values, "missing"))

    def test_compute_growth_normal(self) -> None:
        self.assertAlmostEqual(_compute_growth(120.0, 100.0), 0.2)

    def test_compute_growth_negative(self) -> None:
        self.assertAlmostEqual(_compute_growth(80.0, 100.0), -0.2)

    def test_compute_growth_zero_previous(self) -> None:
        self.assertIsNone(_compute_growth(100.0, 0))

    def test_next_period_end_quarterly(self) -> None:
        result = _next_period_end("2024-03-31", 1)
        self.assertEqual(result, "2024-06-30")

    def test_next_period_end_multiple(self) -> None:
        result = _next_period_end("2024-03-31", 4)
        # 4 quarters (~364 days) from 2024-03-31 is approximately 2025-03-30
        self.assertTrue(result.startswith("2025-03"))


class AvgGrowthTests(unittest.TestCase):
    def test_avg_growth_multiple_periods(self) -> None:
        metrics = {
            "2024-12-31": {"values": {"revenue": {"value": 125.0, "unit": "USD"}}},
            "2024-09-30": {"values": {"revenue": {"value": 110.0, "unit": "USD"}}},
            "2024-06-30": {"values": {"revenue": {"value": 100.0, "unit": "USD"}}},
            "2024-03-31": {"values": {"revenue": {"value": 90.0, "unit": "USD"}}},
        }
        growth = _avg_growth(metrics, "revenue", periods=3)
        self.assertIsNotNone(growth)
        # Expected: avg of (125-110)/110, (110-100)/100, (100-90)/90
        expected = ((125 - 110) / 110 + (110 - 100) / 100 + (100 - 90) / 90) / 3
        self.assertAlmostEqual(growth, expected, places=4)

    def test_avg_growth_single_period(self) -> None:
        metrics = {
            "2024-12-31": {"values": {"revenue": {"value": 100.0, "unit": "USD"}}}
        }
        self.assertIsNone(_avg_growth(metrics, "revenue"))


class AvgMarginTests(unittest.TestCase):
    def test_avg_margin_multiple_periods(self) -> None:
        metrics = {
            "2024-12-31": {
                "values": {
                    "gross_profit": {"value": 50.0, "unit": "USD"},
                    "revenue": {"value": 100.0, "unit": "USD"},
                }
            },
            "2024-09-30": {
                "values": {
                    "gross_profit": {"value": 40.0, "unit": "USD"},
                    "revenue": {"value": 100.0, "unit": "USD"},
                }
            },
        }
        margin = _avg_margin(metrics, "gross_profit", "revenue", periods=2)
        self.assertIsNotNone(margin)
        self.assertAlmostEqual(margin, 0.45)  # avg of 0.5 and 0.4


class ApplyScenarioTests(unittest.TestCase):
    def test_base_scenario_unchanged(self) -> None:
        drivers = {"revenue_growth": {"value": 0.1}, "gross_margin": {"value": 0.4}}
        adjusted = _apply_scenario(drivers, "base")
        self.assertAlmostEqual(adjusted["revenue_growth"], 0.1)
        self.assertAlmostEqual(adjusted["gross_margin"], 0.4)

    def test_bull_scenario_boosts_growth(self) -> None:
        drivers = {"revenue_growth": {"value": 0.1}, "gross_margin": {"value": 0.4}}
        adjusted = _apply_scenario(drivers, "bull")
        self.assertAlmostEqual(adjusted["revenue_growth"], 0.15)  # 1.5x
        self.assertAlmostEqual(adjusted["gross_margin"], 0.42)  # +0.02

    def test_bear_scenario_reduces_growth(self) -> None:
        drivers = {"revenue_growth": {"value": 0.1}, "gross_margin": {"value": 0.4}}
        adjusted = _apply_scenario(drivers, "bear")
        self.assertAlmostEqual(adjusted["revenue_growth"], 0.05)  # 0.5x
        self.assertAlmostEqual(adjusted["gross_margin"], 0.38)  # -0.02

    def test_margin_bounded(self) -> None:
        drivers = {"gross_margin": {"value": 0.99}}
        adjusted = _apply_scenario(drivers, "bull")
        self.assertLessEqual(adjusted["gross_margin"], 1.0)


class ComputeDriversTests(unittest.TestCase):
    def setUp(self) -> None:
        self.metrics = {
            "2024-12-31": {
                "values": {
                    "revenue": {"value": 100.0, "unit": "USD"},
                    "gross_profit": {"value": 40.0, "unit": "USD"},
                    "cogs": {"value": 60.0, "unit": "USD"},
                    "operating_income": {"value": 20.0, "unit": "USD"},
                    "net_income": {"value": 15.0, "unit": "USD"},
                    "pre_tax_income": {"value": 19.0, "unit": "USD"},
                    "income_tax_expense": {"value": 4.0, "unit": "USD"},
                    "r_and_d": {"value": 10.0, "unit": "USD"},
                    "sga": {"value": 10.0, "unit": "USD"},
                    "cfo": {"value": 25.0, "unit": "USD"},
                    "cfi": {"value": -5.0, "unit": "USD"},
                    "capex": {"value": -5.0, "unit": "USD"},
                    "depreciation_amortization": {"value": 3.0, "unit": "USD"},
                    "accounts_receivable": {"value": 15.0, "unit": "USD"},
                    "inventory": {"value": 10.0, "unit": "USD"},
                    "accounts_payable": {"value": 8.0, "unit": "USD"},
                    "shares_diluted": {"value": 10.0, "unit": "SHARES"},
                    "debt_long_term": {"value": 50.0, "unit": "USD"},
                    "interest_expense": {"value": 2.5, "unit": "USD"},
                }
            },
            "2023-12-31": {"values": {"revenue": {"value": 80.0, "unit": "USD"}}},
        }

    def test_compute_drivers_revenue_growth(self) -> None:
        drivers = compute_drivers(self.metrics)
        self.assertAlmostEqual(drivers["revenue_growth"]["value"], 0.25)

    def test_compute_drivers_margins(self) -> None:
        drivers = compute_drivers(self.metrics)
        self.assertAlmostEqual(drivers["gross_margin"]["value"], 0.4)
        self.assertAlmostEqual(drivers["operating_margin"]["value"], 0.2)
        self.assertAlmostEqual(drivers["net_margin"]["value"], 0.15)

    def test_compute_drivers_cost_ratios(self) -> None:
        drivers = compute_drivers(self.metrics)
        self.assertAlmostEqual(drivers["cogs_pct"]["value"], 0.6)
        self.assertAlmostEqual(drivers["rd_pct"]["value"], 0.1)
        self.assertAlmostEqual(drivers["sga_pct"]["value"], 0.1)

    def test_compute_drivers_tax_rate(self) -> None:
        drivers = compute_drivers(self.metrics)
        expected_tax_rate = 4.0 / 19.0
        self.assertAlmostEqual(
            drivers["tax_rate"]["value"], expected_tax_rate, places=4
        )

    def test_compute_drivers_capex_pct(self) -> None:
        drivers = compute_drivers(self.metrics)
        self.assertAlmostEqual(drivers["capex_pct"]["value"], 0.05)

    def test_compute_drivers_da_pct(self) -> None:
        drivers = compute_drivers(self.metrics)
        self.assertAlmostEqual(drivers["da_pct"]["value"], 0.03)

    def test_compute_drivers_nwc_pct(self) -> None:
        drivers = compute_drivers(self.metrics)
        # NWC = AR + Inv - AP = 15 + 10 - 8 = 17
        # NWC % = 17 / 100 = 0.17
        self.assertAlmostEqual(drivers["nwc_pct"]["value"], 0.17)

    def test_compute_drivers_fcf_margin(self) -> None:
        drivers = compute_drivers(self.metrics)
        # FCF = CFO + Capex = 25 + (-5) = 20
        # FCF margin = 20 / 100 = 0.2
        self.assertAlmostEqual(drivers["fcf_margin"]["value"], 0.2)

    def test_compute_drivers_shares(self) -> None:
        drivers = compute_drivers(self.metrics)
        self.assertEqual(drivers["shares"]["value"], 10.0)

    def test_compute_drivers_interest_rate(self) -> None:
        drivers = compute_drivers(self.metrics)
        # Interest rate = 2.5 / 50 = 0.05
        self.assertAlmostEqual(drivers["interest_rate"]["value"], 0.05)

    def test_compute_drivers_provenance(self) -> None:
        drivers = compute_drivers(self.metrics)
        self.assertIn("sources", drivers["revenue_growth"])
        self.assertTrue(len(drivers["revenue_growth"]["sources"]) > 0)

    def test_compute_drivers_fallback_growth(self) -> None:
        metrics = {
            "2024-12-31": {"values": {"revenue": {"value": 50.0, "unit": "USD"}}}
        }
        drivers = compute_drivers(metrics)
        self.assertAlmostEqual(
            drivers["revenue_growth"]["value"], DEFAULT_DRIVERS["revenue_growth"]
        )
        self.assertTrue(
            any(
                src.get("note") == "fallback_growth"
                for src in drivers["revenue_growth"]["sources"]
            )
        )

    def test_compute_drivers_shares_fallback_order(self) -> None:
        metrics = {
            "2024-12-31": {
                "values": {
                    "revenue": {"value": 100.0, "unit": "USD"},
                    "shares_basic": {"value": 4.0, "unit": "SHARES"},
                }
            }
        }
        drivers = compute_drivers(metrics)
        self.assertEqual(drivers["shares"]["value"], 4.0)
        self.assertEqual(drivers["shares"]["sources"][0]["line_item"], "shares_basic")


class BuildForecastTests(unittest.TestCase):
    def setUp(self) -> None:
        self.metrics = {
            "2024-12-31": {
                "values": {
                    "revenue": {"value": 100.0, "unit": "USD"},
                    "gross_profit": {"value": 40.0, "unit": "USD"},
                    "operating_income": {"value": 20.0, "unit": "USD"},
                    "net_income": {"value": 15.0, "unit": "USD"},
                    "cfo": {"value": 25.0, "unit": "USD"},
                    "capex": {"value": -5.0, "unit": "USD"},
                    "depreciation_amortization": {"value": 3.0, "unit": "USD"},
                    "cash": {"value": 50.0, "unit": "USD"},
                    "ppe": {"value": 100.0, "unit": "USD"},
                    "shares_diluted": {"value": 10.0, "unit": "SHARES"},
                }
            },
            "2023-12-31": {"values": {"revenue": {"value": 80.0, "unit": "USD"}}},
        }
        self.drivers = compute_drivers(self.metrics)

    def test_build_forecast_generates_periods(self) -> None:
        forecast = build_forecast(
            "2024-12-31",
            self.metrics["2024-12-31"]["values"],
            self.drivers,
            num_periods=4,
            include_scenarios=False,
        )
        self.assertEqual(len(forecast), 4)

    def test_build_forecast_revenue_compounds(self) -> None:
        forecast = build_forecast(
            "2024-12-31",
            self.metrics["2024-12-31"]["values"],
            self.drivers,
            num_periods=2,
            include_scenarios=False,
        )
        growth = self.drivers["revenue_growth"]["value"]
        expected_t1 = 100.0 * (1 + growth)
        expected_t2 = expected_t1 * (1 + growth)
        self.assertAlmostEqual(forecast[0]["values"]["revenue"]["value"], expected_t1)
        self.assertAlmostEqual(forecast[1]["values"]["revenue"]["value"], expected_t2)

    def test_build_forecast_includes_scenarios(self) -> None:
        forecast = build_forecast(
            "2024-12-31",
            self.metrics["2024-12-31"]["values"],
            self.drivers,
            num_periods=2,
            include_scenarios=True,
        )
        # 2 periods x 3 scenarios = 6
        self.assertEqual(len(forecast), 6)
        scenarios = {f["scenario"] for f in forecast}
        self.assertEqual(scenarios, {"base", "bull", "bear"})

    def test_build_forecast_scenario_ordering(self) -> None:
        forecast = build_forecast(
            "2024-12-31",
            self.metrics["2024-12-31"]["values"],
            self.drivers,
            num_periods=1,
            include_scenarios=True,
        )
        base = next(f for f in forecast if f["scenario"] == "base")
        bull = next(f for f in forecast if f["scenario"] == "bull")
        bear = next(f for f in forecast if f["scenario"] == "bear")
        self.assertGreater(
            bull["values"]["revenue"]["value"],
            base["values"]["revenue"]["value"],
        )
        self.assertLess(
            bear["values"]["revenue"]["value"],
            base["values"]["revenue"]["value"],
        )

    def test_build_forecast_income_statement_ties(self) -> None:
        forecast = build_forecast(
            "2024-12-31",
            self.metrics["2024-12-31"]["values"],
            self.drivers,
            num_periods=1,
            include_scenarios=False,
        )
        f = forecast[0]["values"]
        revenue = f["revenue"]["value"]
        cogs = f["cogs"]["value"]
        gross_profit = f["gross_profit"]["value"]
        if cogs and gross_profit:
            self.assertAlmostEqual(revenue - cogs, gross_profit, places=2)

    def test_build_forecast_includes_fcf(self) -> None:
        forecast = build_forecast(
            "2024-12-31",
            self.metrics["2024-12-31"]["values"],
            self.drivers,
            num_periods=1,
            include_scenarios=False,
        )
        self.assertIn("fcf", forecast[0]["values"])
        self.assertIsNotNone(forecast[0]["values"]["fcf"]["value"])

    def test_build_forecast_includes_eps(self) -> None:
        forecast = build_forecast(
            "2024-12-31",
            self.metrics["2024-12-31"]["values"],
            self.drivers,
            num_periods=1,
            include_scenarios=False,
        )
        eps = forecast[0]["values"]["eps_diluted"]["value"]
        net_income = forecast[0]["values"]["net_income"]["value"]
        shares = self.drivers["shares"]["value"]
        if eps and net_income and shares:
            self.assertAlmostEqual(eps, net_income / shares)

    def test_build_forecast_includes_assumptions(self) -> None:
        forecast = build_forecast(
            "2024-12-31",
            self.metrics["2024-12-31"]["values"],
            self.drivers,
            num_periods=1,
            include_scenarios=False,
        )
        self.assertIn("assumptions", forecast[0])
        self.assertIn("revenue_growth", forecast[0]["assumptions"])

    def test_build_forecast_includes_driver_sources(self) -> None:
        forecast = build_forecast(
            "2024-12-31",
            self.metrics["2024-12-31"]["values"],
            self.drivers,
            num_periods=1,
            include_scenarios=False,
        )
        self.assertIn("driver_sources", forecast[0])

    def test_build_forecast_cash_accumulates(self) -> None:
        forecast = build_forecast(
            "2024-12-31",
            self.metrics["2024-12-31"]["values"],
            self.drivers,
            num_periods=2,
            include_scenarios=False,
        )
        cash_t1 = forecast[0]["values"]["cash"]["value"]
        cash_t2 = forecast[1]["values"]["cash"]["value"]
        # Cash should change based on FCF
        self.assertNotEqual(cash_t1, cash_t2)

    def test_build_forecast_no_revenue_returns_empty(self) -> None:
        forecast = build_forecast(
            "2024-12-31",
            {"gross_profit": {"value": 40.0, "unit": "USD"}},
            self.drivers,
        )
        self.assertEqual(forecast, [])


class BuildForecastSummaryTests(unittest.TestCase):
    def test_summary_aggregates_scenarios(self) -> None:
        forecasts = [
            {
                "period_end": "2025-03-31",
                "scenario": "base",
                "values": {"revenue": {"value": 110}},
            },
            {
                "period_end": "2025-03-31",
                "scenario": "bull",
                "values": {"revenue": {"value": 120}},
            },
            {
                "period_end": "2025-03-31",
                "scenario": "bear",
                "values": {"revenue": {"value": 100}},
            },
        ]
        summary = build_forecast_summary(forecasts)
        self.assertIn("2025-03-31", summary)
        rev = summary["2025-03-31"]["revenue"]
        self.assertEqual(rev["low"], 100)
        self.assertEqual(rev["high"], 120)
        self.assertEqual(rev["scenarios"], 3)

    def test_summary_empty_returns_empty(self) -> None:
        self.assertEqual(build_forecast_summary([]), {})


class FilterAllowedTests(unittest.TestCase):
    def test_filter_allowed_removes_unknown(self) -> None:
        noisy = {
            "2024-12-31": {
                "values": {
                    "revenue": {"value": 100.0, "unit": "USD"},
                    "unknown_metric": {"value": 5.0, "unit": "USD"},
                },
                "sources": {
                    "revenue": {"line_item": "revenue", "period_end": "2024-12-31"},
                    "unknown_metric": {
                        "line_item": "unknown_metric",
                        "period_end": "2024-12-31",
                    },
                },
            },
            "2023-12-31": {"values": {"unknown_metric": {"value": 5.0, "unit": "USD"}}},
        }
        filtered = filter_allowed(noisy)
        self.assertIn("revenue", filtered["2024-12-31"]["values"])
        self.assertNotIn("unknown_metric", filtered["2024-12-31"]["values"])
        self.assertIn("revenue", filtered["2024-12-31"]["sources"])
        self.assertNotIn("2023-12-31", filtered)


class BacktestMetricsTests(unittest.TestCase):
    def test_compute_backtest_metrics_basic(self) -> None:
        actuals = [100.0, 120.0, 80.0]
        forecasts = [90.0, 130.0, 70.0]
        lower = [80.0, 110.0, 60.0]
        upper = [110.0, 140.0, 90.0]
        metrics = compute_backtest_metrics(actuals, forecasts, lower, upper)
        self.assertAlmostEqual(metrics["mae"], 10.0)
        self.assertAlmostEqual(
            metrics["mape"], (0.1 + (10.0 / 120.0) + (10.0 / 80.0)) / 3
        )
        self.assertAlmostEqual(metrics["directional_accuracy"], 1.0)
        self.assertAlmostEqual(metrics["interval_coverage"], 1.0)

    def test_backtest_metrics_len_mismatch(self) -> None:
        with self.assertRaises(ValueError):
            compute_backtest_metrics([1.0], [1.0, 2.0])

    def test_compute_revenue_backtest(self) -> None:
        metrics = {
            "2023-12-31": {"values": {"revenue": {"value": 80.0, "unit": "USD"}}},
            "2024-12-31": {"values": {"revenue": {"value": 100.0, "unit": "USD"}}},
            "2025-12-31": {"values": {"revenue": {"value": 120.0, "unit": "USD"}}},
        }
        backtest = compute_revenue_backtest(metrics)
        self.assertIsNotNone(backtest)
        assert backtest is not None
        self.assertEqual(backtest["samples"], 2)
        self.assertTrue(backtest["mae"] >= 0)


class TieChecksTests(unittest.TestCase):
    def test_tie_checks_quarterizes_ytd_cash_flows(self) -> None:
        metrics = {
            "2024-07-27": {
                "values": {
                    "cfo": {"value": 100.0, "unit": "USD", "start": "2024-01-29"},
                    "cfi": {"value": -30.0, "unit": "USD", "start": "2024-01-29"},
                    "cff": {"value": -10.0, "unit": "USD", "start": "2024-01-29"},
                    "cash": {"value": 140.0, "unit": "USD"},
                    "change_in_cash": {"value": 25.0, "unit": "USD"},
                }
            },
            "2024-04-27": {
                "values": {
                    "cfo": {"value": 60.0, "unit": "USD", "start": "2024-01-29"},
                    "cfi": {"value": -20.0, "unit": "USD", "start": "2024-01-29"},
                    "cff": {"value": -5.0, "unit": "USD", "start": "2024-01-29"},
                    "cash": {"value": 100.0, "unit": "USD"},
                    "change_in_cash": {"value": 10.0, "unit": "USD"},
                }
            },
        }
        ties = compute_tie_checks(metrics)
        latest = ties["2024-07-27"]
        self.assertAlmostEqual(latest["cf_sum"], 25.0)
        self.assertAlmostEqual(latest["cash_delta"], 25.0)
        self.assertAlmostEqual(latest["cf_tie"], 0.0)


class CoverageTests(unittest.TestCase):
    def test_compute_coverage_uses_applicable_items(self) -> None:
        metrics = {
            "2024-12-31": {
                "period_end": "2024-12-31",
                "values": {
                    "revenue": {"value": 100.0, "unit": "USD"},
                    "cogs": {"value": 60.0, "unit": "USD"},
                },
            }
        }
        applicable = {
            "2024-12-31": {
                "income_statement": {"revenue", "cogs", "net_income"},
                "balance_sheet": set(),
                "cash_flow": set(),
            }
        }
        coverage = compute_coverage(metrics, applicable)
        income = coverage["2024-12-31"]["by_statement"]["income_statement"]
        self.assertEqual(income["expected"], 3)
        self.assertEqual(income["found"], 2)
        missing = coverage["2024-12-31"]["missing"]["income_statement"]
        self.assertIn("net_income", missing)

    def test_compute_coverage_counts_multi_statement_items(self) -> None:
        metrics = {
            "2024-12-31": {
                "period_end": "2024-12-31",
                "values": {"net_income": {"value": 50.0, "unit": "USD"}},
            }
        }
        applicable = {
            "2024-12-31": {
                "income_statement": {"net_income"},
                "balance_sheet": set(),
                "cash_flow": {"net_income"},
            }
        }
        coverage = compute_coverage(metrics, applicable)
        income = coverage["2024-12-31"]["by_statement"]["income_statement"]
        cash_flow = coverage["2024-12-31"]["by_statement"]["cash_flow"]
        self.assertEqual(income["found"], 1)
        self.assertEqual(cash_flow["found"], 1)
        self.assertNotIn("net_income", coverage["2024-12-31"]["missing"]["cash_flow"])


if __name__ == "__main__":
    unittest.main()
