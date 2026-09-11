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
