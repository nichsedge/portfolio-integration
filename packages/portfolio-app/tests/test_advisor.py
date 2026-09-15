"""Unit tests for PortfolioAdvisor."""

from portfolio_app.advisor import PortfolioAdvisor


def test_portfolio_advisor_init():
    advisor = PortfolioAdvisor()
    assert advisor.portfolio_root.exists()
    assert advisor.idx_root.exists()
    assert advisor.data_dir.exists()


def test_load_portfolio_state():
    advisor = PortfolioAdvisor()
    state = advisor.load_portfolio_state()
    assert isinstance(state, dict)
    assert "macro_metrics" in state
    assert "top_holdings" in state


def test_analyze_equity_holdings():
    advisor = PortfolioAdvisor()
    holdings = [
        {
            "asset": "BBCA",
            "asset_class": "Equities",
            "value_idr": 23865000,
            "weight_pct": 4.9,
        },
        {
            "asset": "KLBF",
            "asset_class": "Equities",
            "value_idr": 8910000,
            "weight_pct": 1.8,
        },
        {
            "asset": "ST012T4",
            "asset_class": "Fixed Income",
            "value_idr": 90000000,
            "weight_pct": 18.5,
        },
    ]
    results = advisor.analyze_equity_holdings(holdings)
    assert len(results) == 2
    tickers = [r["ticker"] for r in results]
    assert "BBCA" in tickers
    assert "KLBF" in tickers
    for r in results:
        assert "verdict" in r
        assert "action" in r
        assert "nff_20d" in r


def test_screen_dry_powder_opportunities():
    advisor = PortfolioAdvisor()
    opps = advisor.screen_dry_powder_opportunities(limit=2)
    assert len(opps) <= 2
    for o in opps:
        assert "StockCode" in o
        assert "roe" in o
        assert o["roe"] >= 18.0


def test_get_atracker_work_hours():
    advisor = PortfolioAdvisor()
    hours = advisor.get_atracker_work_hours(days=30)
    assert isinstance(hours, float)
    assert hours >= 0.0


def test_generate_markdown_briefing():
    advisor = PortfolioAdvisor()
    briefing = advisor.generate_markdown_briefing()
    assert "🏛️ *Sovereign Portfolio & Market Advisor*" in briefing
    assert "Net Worth:" in briefing
    assert "BBCA" in briefing
    assert "Sovereign Runway 3-Tier Allocation" in briefing


def test_compute_sovereign_allocation_plan_fortress():
    advisor = PortfolioAdvisor()
    # 30 months of runway (150M cash vs 5M burn)
    plan = advisor.compute_sovereign_allocation_plan(liquid_cash=150_000_000.0, monthly_burn=5_000_000.0)
    assert plan["status"] == "FORTRESS (>24m)"
    assert plan["runway_months"] == 30.0
    assert plan["tier1_operating_reserve"]["allocated_idr"] == 60_000_000.0  # 12 * 5M
    assert plan["tier2_fortress_buffer"]["allocated_idr"] == 60_000_000.0  # 12 * 5M
    assert plan["tier3_deployable_surplus"]["allocated_idr"] == 30_000_000.0  # 150M - 120M
    assert "surplus above 24 months" in plan["tactical_advice"]


def test_compute_sovereign_allocation_plan_sovereign():
    advisor = PortfolioAdvisor()
    # 18 months of runway (90M cash vs 5M burn)
    plan = advisor.compute_sovereign_allocation_plan(liquid_cash=90_000_000.0, monthly_burn=5_000_000.0)
    assert plan["status"] == "SOVEREIGN (12-24m)"
    assert plan["runway_months"] == 18.0
    assert plan["tier1_operating_reserve"]["allocated_idr"] == 60_000_000.0
    assert plan["tier2_fortress_buffer"]["allocated_idr"] == 30_000_000.0
    assert plan["tier3_deployable_surplus"]["allocated_idr"] == 0.0
    assert "Lock in state-guaranteed Sukuk yield" in plan["tactical_advice"]


def test_compute_sovereign_allocation_plan_lean():
    advisor = PortfolioAdvisor()
    # 8 months of runway (40M cash vs 5M burn)
    plan = advisor.compute_sovereign_allocation_plan(liquid_cash=40_000_000.0, monthly_burn=5_000_000.0)
    assert plan["status"] == "LEAN (<12m)"
    assert plan["runway_months"] == 8.0
    assert plan["tier1_operating_reserve"]["allocated_idr"] == 40_000_000.0
    assert plan["tier2_fortress_buffer"]["allocated_idr"] == 0.0
    assert plan["tier3_deployable_surplus"]["allocated_idr"] == 0.0
    assert "Risk-asset equity deployment is frozen" in plan["tactical_advice"]


def test_get_idx_signal_maps():
    advisor = PortfolioAdvisor()
    composite_map, audit_risk_set, stealth_map, flow_radar_map = advisor.get_idx_signal_maps()
    assert isinstance(composite_map, dict)
    assert isinstance(audit_risk_set, set)
    assert isinstance(stealth_map, dict)
    assert isinstance(flow_radar_map, dict)


def test_get_advisor_payload_sovereign():
    advisor = PortfolioAdvisor()
    payload = advisor.get_advisor_payload()
    assert "sovereign_allocation_plan" in payload
    plan = payload["sovereign_allocation_plan"]
    assert "tier1_operating_reserve" in plan
    assert "tier2_fortress_buffer" in plan
    assert "tier3_deployable_surplus" in plan
    assert "equities_verdicts" in payload
    for r in payload["equities_verdicts"]:
        assert "rsi14" in r
        assert "trend_regime" in r
    for o in payload["opportunities"]:
        assert "rsi14" in o
        assert "entry_zone" in o

