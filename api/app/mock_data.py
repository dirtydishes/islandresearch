from datetime import date


MOCK_MODEL = {
    "company": "deltaisland research demo",
    "as_of": date.today().isoformat(),
    "statements": [
        {
            "period": "FY22",
            "revenue": 182.4,
            "ebitda": 51.2,
            "net_income": 34.6,
            "cash": 42.0,
            "debt": 15.0,
        },
        {
            "period": "Q1'23",
            "revenue": 48.5,
            "ebitda": 12.7,
            "net_income": 8.5,
            "cash": 44.0,
            "debt": 15.2,
        },
        {
            "period": "Q2'23",
            "revenue": 51.9,
            "ebitda": 13.8,
            "net_income": 9.1,
            "cash": 45.5,
            "debt": 15.1,
        },
        {
            "period": "Q3'23",
            "revenue": 55.0,
            "ebitda": 15.3,
            "net_income": 10.0,
            "cash": 46.8,
            "debt": 14.9,
        },
    ],
    "forecast": [
        {
            "period": "Q4'23E",
            "revenue": 58.2,
            "ebitda": 16.2,
            "net_income": 10.6,
            "cash": 48.1,
            "debt": 14.7,
            "fcf": 9.4,
        },
        {
            "period": "FY23E",
            "revenue": 213.6,
            "ebitda": 57.9,
            "net_income": 38.2,
            "cash": 52.5,
            "debt": 14.3,
            "fcf": 36.0,
        },
        {
            "period": "FY24E",
            "revenue": 236.0,
            "ebitda": 65.4,
            "net_income": 43.1,
            "cash": 61.0,
            "debt": 13.5,
            "fcf": 41.6,
        },
    ],
    "valuation": {
        "enterprise_value": 420.0,
        "equity_value": 446.0,
        "shares_outstanding": 110.0,
        "implied_share_price": 4.05,
        "notes": "DCF base case with 9% WACC, 2.5% terminal growth; multiples cross-check within ±7%.",
    },
    "audit_summary": [
        "Revenue growth anchored to last 3Q CAGR with decay toward sector median.",
        "Margins bounded by historical 20th/80th percentile to prevent runaway scenarios.",
        "Cash builds from FCF after debt amortization; shares held flat for demo.",
    ],
}
