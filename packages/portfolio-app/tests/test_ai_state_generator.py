"""
Unit tests for AI State and Digest Generator.
"""

import pytest
from portfolio_app.ai_state_generator import (
    calculate_passive_income,
    calculate_rebalancing_orders,
    calculate_fire_simulation,
    calculate_tax_efficiency_audit,
    generate_ai_state,
    generate_ai_digest_markdown,
)


@pytest.fixture
def sample_holdings():
    return [
        {
            "asset": "ST012T4",
            "category": "SBN",
            "asset_class": "Fixed Income",
            "source": "KSEI",
            "value_idr": 100000000.0,
            "value_usd": 6250.0,
            "currency": "IDR",
        },
        {
            "asset": "BBCA",
            "category": "Indo Stocks",
            "asset_class": "Equities",
            "source": "KSEI",
            "value_idr": 20000000.0,
            "value_usd": 1250.0,
            "currency": "IDR",
        },
        {
            "asset": "USDT",
            "category": "Stablecoin",
            "asset_class": "Cash & Equivalents",
            "source": "Binance",
            "value_idr": 10000000.0,
            "value_usd": 625.0,
            "currency": "USD",
        },
        {
            "asset": "ETH",
            "category": "Spot",
            "asset_class": "Crypto",
            "source": "Binance",
            "value_idr": 10000000.0,
            "value_usd": 625.0,
            "currency": "USD",
        },
    ]


def test_calculate_passive_income(sample_holdings):
    fx = 16000.0
    # Monthly living burn = 4,000,000 IDR
    pi = calculate_passive_income(sample_holdings, exchange_rate=fx, monthly_burn_idr=4000000.0)

    # SBN: 100m * 6.5% = 6.5m
    # BBCA: 20m * 3.5% = 0.7m
    # USDT: 10m * 4.0% = 0.4m
    # Spot ETH: 0% yield
    # Total annual = 7.6m IDR -> ~633,333 IDR/month
    assert pi["projected_annual_passive_income_idr"] == pytest.approx(7600000.0, 1.0)
    assert pi["projected_monthly_passive_income_idr"] == pytest.approx(633333.33, 1.0)
    # FI coverage: 633,333 / 4,000,000 = ~15.8% -> Accumulation (<25%)
    assert pi["fi_coverage_pct"] == pytest.approx(15.8, 0.2)
    assert pi["fi_status"] == "Accumulation (<25%)"


def test_calculate_rebalancing_orders(sample_holdings):
    fx = 16000.0
    total_assets = 140000000.0 # 100m + 20m + 10m + 10m
    # Target allocation: Fixed Income 50%, Equities 25%, Cash 10%, Crypto 10%, Commodities 5%
    rebalancing = calculate_rebalancing_orders(
        holdings=sample_holdings,
        total_assets_idr=total_assets,
        exchange_rate=fx,
        monthly_deposit_idr=5000000.0
    )

    recs = rebalancing["recommendations"]
    assert len(recs) > 0
    # Equities (20m/140m = 14.3% vs target 25%) should have the largest deposit allocation
    equities_rec = next(r for r in recs if r["asset_class"] == "Equities")
    assert equities_rec["drift_pct"] < 0
    assert equities_rec["deposit_allocation_idr"] > 0


def test_generate_ai_state_and_digest(sample_holdings):
    fx = 16000.0
    snapshot = {
        "metadata": {"date": "2026-08-18", "exchange_rate": fx},
        "totals": {
            "net_worth_idr": 140000000.0,
            "net_worth_usd": 8750.0,
            "total_assets_idr": 140000000.0,
            "total_liabilities_idr": 0.0
        },
        "allocation": {
            "by_asset_class": [
                {"asset_class": "Fixed Income", "value_idr": 100000000.0, "percentage": 71.4, "count": 1},
                {"asset_class": "Equities", "value_idr": 20000000.0, "percentage": 14.3, "count": 1},
                {"asset_class": "Cash & Equivalents", "value_idr": 10000000.0, "percentage": 7.1, "count": 1},
                {"asset_class": "Crypto", "value_idr": 10000000.0, "percentage": 7.1, "count": 1},
            ]
        },
        "holdings": sample_holdings
    }

    ai_state = generate_ai_state(snapshot)
    assert ai_state["state_date"] == "2026-08-18"
    assert ai_state["macro_metrics"]["net_worth_idr"] == 140000000.0
    assert "passive_income" in ai_state
    assert "rebalancing_plan" in ai_state

    digest_md = generate_ai_digest_markdown(ai_state)
    assert "# Financial Portfolio AI State Brief" in digest_md
    assert "Projected Passive Cashflow" in digest_md
    assert "Deposit-Only Rebalancing Guideline" in digest_md


def test_calculate_fire_simulation():
    # Net worth 400m, monthly burn 4m (annual 48m) -> FIRE number (25x) = 1.2B
    # Monthly savings 8m
    sim = calculate_fire_simulation(
        net_worth_idr=400000000.0,
        monthly_burn_idr=4000000.0,
        monthly_savings_idr=8000000.0,
        expected_real_return_pct=6.0,
        safe_withdrawal_rate_pct=4.0,
        current_age=30,
        target_retirement_age=55
    )

    assert sim["fire_number_idr"] == 1200000000.0
    assert sim["current_progress_pct"] == pytest.approx(33.3, 0.1)
    assert sim["is_coast_fire_achieved"] is True
    assert sim["projected_timeline"]["years_to_fire"] > 0
    assert sim["projected_timeline"]["years_to_fire"] < 10.0


def test_calculate_tax_efficiency_audit(sample_holdings):
    fx = 16000.0
    audit = calculate_tax_efficiency_audit(sample_holdings, exchange_rate=fx)

    assert audit["tax_efficiency_score"] >= 80.0
    assert audit["tax_efficiency_grade"] in {"A", "A+"}
    assert len(audit["buckets"]) > 0
    assert len(audit["optimization_opportunities"]) >= 0
