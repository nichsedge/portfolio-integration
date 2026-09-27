"""
Unit tests for Scenario Stress Tester & Macroeconomic Crisis Simulator.
"""

import pytest
from portfolio_app.scenario_stress_tester import run_stress_test


@pytest.fixture
def sample_holdings():
    return [
        {
            "asset": "ST012T4",
            "category": "SBN",
            "asset_class": "Fixed Income",
            "source": "KSEI",
            "value_idr": 200000000.0,
            "value_usd": 12500.0,
            "currency": "IDR",
        },
        {
            "asset": "BBCA",
            "category": "Indo Stocks",
            "asset_class": "Equities",
            "source": "KSEI",
            "value_idr": 50000000.0,
            "value_usd": 3125.0,
            "currency": "IDR",
        },
        {
            "asset": "ETH",
            "category": "Spot",
            "asset_class": "Crypto",
            "source": "Binance",
            "value_idr": 30000000.0,
            "value_usd": 1875.0,
            "currency": "USD",
        },
        {
            "asset": "USDT",
            "category": "Stablecoin",
            "asset_class": "Cash & Equivalents",
            "source": "Binance",
            "value_idr": 20000000.0,
            "value_usd": 1250.0,
            "currency": "USD",
        },
    ]


def test_run_stress_test(sample_holdings):
    fx = 16000.0
    res = run_stress_test(
        holdings=sample_holdings,
        exchange_rate=fx,
        live_bank_cash_idr=50000000.0,
        monthly_burn_idr=5000000.0
    )

    # Baseline: 200m SBN + 50m Equities + 30m Crypto + 20m USDT + 50m Live bank = 350m IDR
    assert res["baseline_net_worth_idr"] == 350000000.0
    # Liquid reserves: 20m USDT + 50m Bank = 70m IDR -> 14 months runway
    assert res["total_liquid_reserves_idr"] == 70000000.0
    assert res["resilience_score"] >= 75.0
    assert res["resilience_grade"] in {"Robust (AA)", "Fortress (AAA)"}

    scenarios = res["scenarios"]
    assert len(scenarios) == 4

    # Crash scenario: Equities -30% (-15m), Crypto -60% (-18m) -> Drawdown ~33m (~9.4%)
    crash = next(s for s in scenarios if s["scenario_key"] == "market_crash_and_crypto_winter")
    assert crash["drawdown_pct"] > 0
    assert crash["survival_rating"] == "Safe"
