"""
Model Context Protocol (MCP) Server & CLI Tool for Portfolio Data
Exposes standardized tools for AI agents (Hermes Agent, Claude, Cursor, Goose, LangGraph).
Supports stdio MCP JSON-RPC 2.0 protocol and direct CLI execution.
"""

import sys
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

# Setup imports
try:
    from transform_core import get_data_dir, get_exchange_rate, get_full_snapshot
    from defillama_client import DefiLlamaClient
    from portfolio_app.ai_state_generator import (
        build_and_save_ai_state,
        generate_ai_digest_markdown,
        generate_ai_state,
        load_historical_snapshots,
    )
except ImportError:
    repo_root = Path(__file__).resolve().parents[4]
    sys.path.append(str(repo_root / "packages/portfolio-app/src"))
    sys.path.append(str(repo_root / "packages/transform-core/src"))
    sys.path.append(str(repo_root / "packages/defillama-client/src"))
    from transform_core import get_data_dir, get_exchange_rate, get_full_snapshot
    from defillama_client import DefiLlamaClient
    from portfolio_app.ai_state_generator import (
        build_and_save_ai_state,
        generate_ai_digest_markdown,
        generate_ai_state,
        load_historical_snapshots,
    )


def get_latest_snapshot_path() -> Optional[Path]:
    """Find the most recent snapshot file."""
    data_dir = get_data_dir()
    snapshots = sorted([f for f in data_dir.glob("*_snapshot.json") if not f.name.startswith("latest")])
    return snapshots[-1] if snapshots else None


def resolve_snapshot(date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Resolve snapshot from portfolio.db SSOT, with fallback to latest_snapshot.json or legacy files."""
    try:
        snap = get_full_snapshot(date=date if date != "latest" else None)
        if snap:
            return snap
    except Exception:
        pass

    data_dir = get_data_dir()
    if not date or date == "latest":
        latest_file = data_dir / "latest_snapshot.json"
        if latest_file.exists():
            try:
                with open(latest_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

    if date and date != "latest":
        snap_path = data_dir / f"{date}_snapshot.json"
    else:
        snap_path = get_latest_snapshot_path()

    if snap_path and snap_path.exists():
        try:
            with open(snap_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return None


def tool_get_portfolio_overview(date: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns the high-level financial overview: Net worth, MoM growth, asset class allocation, and liquidity.
    """
    snapshot = resolve_snapshot(date)
    if not snapshot:
        return {"error": f"Snapshot not found for date: {date or 'latest'}"}

    data_dir = get_data_dir()
    all_snapshots = load_historical_snapshots(data_dir)
    state = generate_ai_state(snapshot, all_snapshots)

    return {
        "date": state["state_date"],
        "exchange_rate_usd_idr": state["exchange_rate"],
        "macro_metrics": state["macro_metrics"],
        "asset_allocation": state["asset_allocation"],
        "currency_exposure": state["currency_exposure"],
        "liquidity": state["liquidity"],
    }


def tool_get_holdings_breakdown(
    asset_class: Optional[str] = None,
    min_value_usd: float = 0.0,
    date: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Returns individual holdings filtered by asset class or minimum USD value.
    """
    snapshot = resolve_snapshot(date)
    if not snapshot:
        return [{"error": f"Snapshot not found for date: {date or 'latest'}"}]

    holdings = snapshot.get("holdings", [])
    fx = snapshot.get("metadata", {}).get("exchange_rate", 16000.0)

    filtered = []
    for h in holdings:
        val_usd = h.get("value_usd") or 0.0
        val_idr = h.get("value_idr") or (val_usd * fx)
        if val_usd == 0.0 and val_idr > 0:
            val_usd = val_idr / fx

        h_class = h.get("asset_class", "Other")

        if asset_class and asset_class.lower() != h_class.lower():
            continue
        if val_usd < min_value_usd:
            continue

        filtered.append({
            "asset": h.get("asset"),
            "category": h.get("category"),
            "asset_class": h_class,
            "source": h.get("source"),
            "value_idr": round(val_idr, 0),
            "value_usd": round(val_usd, 2),
            "account": h.get("account"),
        })

    filtered.sort(key=lambda x: x["value_idr"], reverse=True)
    return filtered


def tool_get_historical_performance(months: int = 6) -> List[Dict[str, Any]]:
    """
    Returns the multi-month trajectory of pure portfolio investments and True Net Worth (with reconstructed cash).
    """
    data_dir = get_data_dir()
    all_snapshots = load_historical_snapshots(data_dir)
    if not all_snapshots:
        return []

    recent = all_snapshots[-months:]

    from portfolio_app.cashflow_analyzer import resolve_sans_finance_db, reconstruct_historical_net_worth
    db_path = resolve_sans_finance_db(data_dir=data_dir, auto_pull_gcs=False)
    reconstructed_map = {}
    if db_path and db_path.exists():
        reconstructed = reconstruct_historical_net_worth(db_path, recent)
        reconstructed_map = {r["date"]: r for r in reconstructed}

    history = []
    for s in recent:
        s_meta = s.get("metadata", {})
        s_totals = s.get("totals", {})
        d_str = s_meta.get("date")
        allocations = {
            item.get("asset_class", "Other"): item.get("percentage", 0.0)
            for item in s.get("allocation", {}).get("by_asset_class", [])
        }
        rec = reconstructed_map.get(d_str, {})
        port_val_idr = s_totals.get("net_worth_idr", 0.0)
        cash_val_idr = rec.get("reconstructed_cash_idr", 0.0)
        true_nw_idr = rec.get("true_net_worth_idr", port_val_idr)
        fx = s_meta.get("exchange_rate") or get_exchange_rate()

        history.append({
            "date": d_str,
            "portfolio_value_idr": port_val_idr,
            "portfolio_value_usd": s_totals.get("net_worth_usd", round(port_val_idr / fx, 2)),
            "reconstructed_cash_idr": cash_val_idr,
            "true_net_worth_idr": true_nw_idr,
            "true_net_worth_usd": round(true_nw_idr / fx, 2),
            "fixed_income_pct": allocations.get("Fixed Income", 0.0),
            "equities_pct": allocations.get("Equities", 0.0),
            "crypto_pct": allocations.get("Crypto", 0.0),
            "cash_pct": allocations.get("Cash & Equivalents", 0.0),
            "commodities_pct": allocations.get("Commodities", 0.0),
        })

    return history


def tool_get_cashflow_analysis(months: int = 3) -> Dict[str, Any]:
    """
    Returns monthly cashflow metrics from Sans Finance: income, expenses, net savings,
    burn rate, and category breakdowns.
    """
    from portfolio_app.cashflow_analyzer import (
        resolve_sans_finance_db,
        get_cashflow_metrics,
        get_live_accounts,
    )
    data_dir = get_data_dir()
    db_path = resolve_sans_finance_db(data_dir=data_dir, auto_pull_gcs=True)
    if not db_path or not db_path.exists():
        return {"error": "Sans Finance database snapshot not found locally or in GCS."}

    fx = get_exchange_rate()
    cashflow = get_cashflow_metrics(db_path, months=months, exchange_rate=fx)
    accounts = get_live_accounts(db_path, exchange_rate=fx)

    return {
        "db_source": str(db_path.name),
        "exchange_rate": fx,
        "live_liquid_accounts": accounts,
        "cashflow_metrics": cashflow,
    }


def tool_get_unified_financial_state() -> Dict[str, Any]:
    """
    Combines investment portfolio (stocks, crypto, defi, fixed income) with live cashflow,
    bank account balances, and emergency runway from Sans Finance.
    """
    from portfolio_app.cashflow_analyzer import (
        resolve_sans_finance_db,
        get_cashflow_metrics,
        get_live_accounts,
        calculate_runway,
    )
    overview = tool_get_portfolio_overview()
    if "error" in overview:
        return overview

    data_dir = get_data_dir()
    fx = overview.get("exchange_rate_usd_idr") or get_exchange_rate()
    db_path = resolve_sans_finance_db(data_dir=data_dir, auto_pull_gcs=True)

    cashflow_info = {}
    if db_path and db_path.exists():
        accounts = get_live_accounts(db_path, fx)
        cf = get_cashflow_metrics(db_path, months=3, exchange_rate=fx)
        
        has_sansfinance = "SansFinance" in overview.get("sources", []) or "sansfinance" in overview.get("sources", [])
        portfolio_cash = overview["liquidity"]["liquid_cash_idr"]
        portfolio_nw = overview["macro_metrics"]["net_worth_idr"]

        if has_sansfinance:
            total_liquid_idr = portfolio_cash
            consolidated_nw_idr = portfolio_nw
        else:
            total_liquid_idr = portfolio_cash + accounts["total_liquid_idr"]
            consolidated_nw_idr = portfolio_nw + accounts["total_liquid_idr"]

        runway = calculate_runway(total_liquid_idr, cf["avg_monthly_burn_idr"])

        cashflow_info = {
            "sans_finance_db": str(db_path.name),
            "consolidated_net_worth_idr": consolidated_nw_idr,
            "consolidated_net_worth_usd": round(consolidated_nw_idr / fx, 2),
            "live_bank_cash_idr": accounts["total_liquid_idr"],
            "total_liquid_reserves_idr": total_liquid_idr,
            "avg_monthly_income_idr": cf["avg_monthly_income_idr"],
            "avg_monthly_burn_idr": cf["avg_monthly_burn_idr"],
            "savings_rate_pct": cf["overall_savings_rate_pct"],
            "runway_months": runway["runway_months"],
            "runway_health": runway["health"],
            "runway_desc": runway["description"],
            "top_spending_categories": cf["top_categories"][:5],
        }

    return {
        "date": overview["date"],
        "exchange_rate": fx,
        "portfolio": overview,
        "unified_summary": cashflow_info,
    }


def tool_get_rebalancing_plan(monthly_deposit_idr: float = 5_000_000.0) -> Dict[str, Any]:
    """
    Calculates a deposit-only rebalancing plan to allocate new cash across underweight
    asset classes (Fixed Income, Equities, Crypto, Commodities) without selling existing assets.
    """
    from portfolio_app.ai_state_generator import calculate_rebalancing_orders
    overview = tool_get_portfolio_overview()
    if "error" in overview:
        return overview

    holdings = tool_get_holdings_breakdown()
    total_assets_idr = overview["macro_metrics"]["total_assets_idr"]
    fx = overview.get("exchange_rate_usd_idr") or get_exchange_rate()

    plan = calculate_rebalancing_orders(
        holdings=holdings,
        total_assets_idr=total_assets_idr,
        exchange_rate=fx,
        monthly_deposit_idr=monthly_deposit_idr
    )
    return {
        "date": overview["date"],
        "exchange_rate": fx,
        "rebalancing_plan": plan
    }


def tool_get_passive_income_projection() -> Dict[str, Any]:
    """
    Calculates projected annual and monthly passive cashflow from SBN coupons, stock dividends,
    and crypto staking rewards, and compares against monthly living burn rate.
    """
    from portfolio_app.ai_state_generator import calculate_passive_income
    from portfolio_app.cashflow_analyzer import resolve_sans_finance_db, get_cashflow_metrics

    overview = tool_get_portfolio_overview()
    if "error" in overview:
        return overview

    holdings = tool_get_holdings_breakdown()
    fx = overview.get("exchange_rate_usd_idr") or get_exchange_rate()

    monthly_burn = None
    db_path = resolve_sans_finance_db(data_dir=get_data_dir(), auto_pull_gcs=False)
    if db_path and db_path.exists():
        try:
            cf = get_cashflow_metrics(db_path, months=3, exchange_rate=fx)
            monthly_burn = cf["avg_monthly_burn_idr"]
        except Exception:
            pass

    projection = calculate_passive_income(holdings, fx, monthly_burn_idr=monthly_burn)
    return {
        "date": overview["date"],
        "exchange_rate": fx,
        "passive_income_projection": projection
    }


def tool_get_fire_simulation(
    target_annual_spending_idr: Optional[float] = None,
    expected_real_return_pct: float = 6.0,
    safe_withdrawal_rate_pct: float = 4.0,
    current_age: int = 30,
    target_retirement_age: int = 55
) -> Dict[str, Any]:
    """
    Simulates Financial Independence / Retire Early (FIRE) milestones, Coast FIRE,
    and projected timeline using current net worth and cashflow burn rate.
    """
    from portfolio_app.ai_state_generator import calculate_fire_simulation
    from portfolio_app.cashflow_analyzer import resolve_sans_finance_db, get_cashflow_metrics, get_live_accounts

    overview = tool_get_portfolio_overview()
    if "error" in overview:
        return overview

    fx = overview.get("exchange_rate_usd_idr") or get_exchange_rate()
    net_worth = overview["macro_metrics"]["net_worth_idr"]
    monthly_burn = 5_000_000.0
    monthly_savings = 5_000_000.0

    db_path = resolve_sans_finance_db(data_dir=get_data_dir(), auto_pull_gcs=False)
    if db_path and db_path.exists():
        try:
            cf = get_cashflow_metrics(db_path, months=3, exchange_rate=fx)
            accs = get_live_accounts(db_path, fx)
            has_sansfinance = "SansFinance" in overview.get("sources", []) or "sansfinance" in overview.get("sources", [])
            if not has_sansfinance:
                net_worth += accs["total_liquid_idr"]
            monthly_burn = cf["avg_monthly_burn_idr"]
            monthly_savings = cf["avg_monthly_savings_idr"]
        except Exception:
            pass

    if target_annual_spending_idr and target_annual_spending_idr > 0:
        monthly_burn = target_annual_spending_idr / 12.0

    sim = calculate_fire_simulation(
        net_worth_idr=net_worth,
        monthly_burn_idr=monthly_burn,
        monthly_savings_idr=monthly_savings,
        expected_real_return_pct=expected_real_return_pct,
        safe_withdrawal_rate_pct=safe_withdrawal_rate_pct,
        current_age=current_age,
        target_retirement_age=target_retirement_age
    )

    return {
        "date": overview["date"],
        "exchange_rate": fx,
        "consolidated_net_worth_idr": net_worth,
        "fire_simulation": sim
    }


def tool_get_tax_efficiency_audit() -> Dict[str, Any]:
    """
    Audits Indonesian tax treatment (PPh Final, Exemptions, Reinvestment benefits) across portfolio holdings.
    """
    from portfolio_app.ai_state_generator import calculate_tax_efficiency_audit
    overview = tool_get_portfolio_overview()
    if "error" in overview:
        return overview

    holdings = tool_get_holdings_breakdown()
    fx = overview.get("exchange_rate_usd_idr") or get_exchange_rate()

    audit = calculate_tax_efficiency_audit(holdings, fx)
    return {
        "date": overview["date"],
        "exchange_rate": fx,
        "tax_audit": audit
    }


def tool_get_scenario_stress_test() -> Dict[str, Any]:
    """
    Simulates macroeconomic crisis stress test (Market Crash, Currency Devaluation, Zero Income, Stagflation).
    """
    from portfolio_app.scenario_stress_tester import run_stress_test
    from portfolio_app.cashflow_analyzer import resolve_sans_finance_db, get_cashflow_metrics, get_live_accounts

    overview = tool_get_portfolio_overview()
    if "error" in overview:
        return overview

    holdings = tool_get_holdings_breakdown()
    fx = overview.get("exchange_rate_usd_idr") or get_exchange_rate()

    live_cash = 0.0
    monthly_burn = 4_000_000.0

    db_path = resolve_sans_finance_db(data_dir=get_data_dir(), auto_pull_gcs=False)
    if db_path and db_path.exists():
        try:
            cf = get_cashflow_metrics(db_path, months=3, exchange_rate=fx)
            accs = get_live_accounts(db_path, fx)
            has_sansfinance = "SansFinance" in overview.get("sources", []) or "sansfinance" in overview.get("sources", [])
            if not has_sansfinance:
                live_cash = accs["total_liquid_idr"]
            monthly_burn = cf["avg_monthly_burn_idr"]
        except Exception:
            pass

    stress = run_stress_test(
        holdings=holdings,
        exchange_rate=fx,
        live_bank_cash_idr=live_cash,
        monthly_burn_idr=monthly_burn
    )

    return {
        "date": overview["date"],
        "exchange_rate": fx,
        "stress_test": stress
    }


def tool_get_portfolio_health_audit() -> Dict[str, Any]:
    """
    Performs an automated financial health audit: checks allocation drift, single-asset concentration risk,
    currency risk, liquidity runway, and generates strategic advisory recommendations.
    """
    overview = tool_get_portfolio_overview()
    if "error" in overview:
        return overview

    macro = overview["macro_metrics"]
    allocations = overview["asset_allocation"]
    curr = overview["currency_exposure"]
    liq = overview["liquidity"]

    recommendations = []
    
    # 1. Allocation Drift Audit
    drift_alerts = []
    for a in allocations:
        drift = a.get("drift_pct", 0.0)
        aclass = a["asset_class"]
        target = a.get("target_pct", 0.0)
        if drift >= 5.0:
            msg = f"OVERWEIGHT: {aclass} is +{drift:.1f}% above target ({a['weight_pct']:.1f}% vs {target:.1f}%). Pause additions or reallocate monthly DCA."
            recommendations.append(msg)
            drift_alerts.append({"asset_class": aclass, "severity": "HIGH", "message": msg})
        elif drift <= -5.0:
            msg = f"UNDERWEIGHT: {aclass} is {drift:.1f}% below target ({a['weight_pct']:.1f}% vs {target:.1f}%). Priority candidate for new DCA deposits."
            recommendations.append(msg)
            drift_alerts.append({"asset_class": aclass, "severity": "HIGH", "message": msg})
        elif abs(drift) >= 3.0:
            drift_alerts.append({"asset_class": aclass, "severity": "MEDIUM", "message": f"Moderate drift: {aclass} ({drift:+.1f}%)"})

    # 1.5. SBN Maturity & Reinvestment Audit
    sbn_maturity_alerts = []
    try:
        from portfolio_app.ai_state_generator import calculate_sukuk_and_dividend_schedule
        holdings = tool_get_holdings_breakdown()
        fx_rate = overview.get("exchange_rate_usd_idr") or 16000.0
        sukuk_data = calculate_sukuk_and_dividend_schedule(holdings, fx_rate, current_date_str=overview.get("date", ""))
        for item in sukuk_data.get("schedule", []):
            m_left = item.get("months_to_maturity", 999)
            if m_left <= 6.0:
                mat_msg = f"SBN Maturity Approaching: {item['asset']} (Rp {item['principal_idr']:,.0f}) matures in {m_left} months ({item['maturity_date']}). Plan reinvestment."
                recommendations.append(mat_msg)
                sbn_maturity_alerts.append({
                    "asset": item["asset"],
                    "principal_idr": item["principal_idr"],
                    "maturity_date": item["maturity_date"],
                    "months_left": m_left,
                    "alert": mat_msg
                })
    except Exception:
        pass

    # 2. Liquidity Audit
    if liq["liquid_cash_pct"] < 8.0:
        recommendations.append(
            f"Cash buffer is {liq['liquid_cash_pct']}%, which is below the 10% safety guideline. Increase liquid emergency fund."
        )

    # 3. Currency Risk
    if curr.get("usd_pct", 0.0) < 10.0:
        recommendations.append(
            "Low USD/hard-currency exposure. Consider allocating 15-20% to USD assets (e.g. US Stocks or Stablecoins) to hedge against IDR inflation."
        )

    # 4. Cashflow & Runway Audit (if DB available)
    try:
        from portfolio_app.cashflow_analyzer import (
            resolve_sans_finance_db,
            get_cashflow_metrics,
            get_live_accounts,
            calculate_runway,
        )
        db_path = resolve_sans_finance_db(data_dir=get_data_dir(), auto_pull_gcs=False)
        if db_path and db_path.exists():
            fx = overview.get("exchange_rate_usd_idr") or 16000.0
            cf = get_cashflow_metrics(db_path, months=3, exchange_rate=fx)
            accs = get_live_accounts(db_path, fx)
            has_sansfinance = "SansFinance" in overview.get("sources", []) or "sansfinance" in overview.get("sources", [])
            total_liquid = liq["liquid_cash_idr"] if has_sansfinance else (liq["liquid_cash_idr"] + accs["total_liquid_idr"])
            runway = calculate_runway(total_liquid, cf["avg_monthly_burn_idr"])

            if cf["overall_savings_rate_pct"] < 20.0:
                recommendations.append(
                    f"Savings rate is {cf['overall_savings_rate_pct']}%, below the healthy 20%+ target. Review top expense categories."
                )
            if runway["runway_months"] < 6.0:
                recommendations.append(
                    f"Liquid runway is {runway['runway_months']} months ({runway['health']}). Target at least 6 months of living expenses."
                )
    except Exception:
        pass

    return {
        "status": "HEALTH_CHECK_COMPLETE",
        "date": overview["date"],
        "net_worth_idr": macro["net_worth_idr"],
        "net_worth_usd": macro["net_worth_usd"],
        "mom_growth_pct": macro["mom_growth_pct"],
        "liquidity_status": "Adequate" if liq["liquid_cash_pct"] >= 8.0 else "Low Buffer",
        "drift_summary": [
            {"asset_class": a["asset_class"], "drift": f"{a['drift_pct']:+0.1f}%"}
            for a in allocations if abs(a["drift_pct"]) >= 2.0
        ],
        "drift_alerts": drift_alerts,
        "sbn_maturity_alerts": sbn_maturity_alerts,
        "advisory_recommendations": recommendations,
    }


def tool_get_upcoming_cashflow() -> Dict[str, Any]:
    """
    Get schedule of upcoming fixed-income cashflow: monthly Sukuk SBN coupon payouts (paid on the 10th of every month).
    """
    from portfolio_app.ai_state_generator import calculate_sukuk_and_dividend_schedule
    overview = tool_get_portfolio_overview()
    if "error" in overview:
        return overview

    holdings = tool_get_holdings_breakdown()
    fx = overview.get("exchange_rate_usd_idr") or get_exchange_rate()

    schedule = calculate_sukuk_and_dividend_schedule(holdings, fx, current_date_str=overview.get("date", ""))
    return {
        "date": overview["date"],
        "exchange_rate": fx,
        "upcoming_cashflow": schedule
    }


def tool_crypto_get_token_prices(coins: list[str]) -> dict[str, Any]:
    """Fetch spot multi-chain token prices by address or coingecko ID via DefiLlama free API."""
    with DefiLlamaClient() as client:
        return client.get_token_prices(coins)


def tool_crypto_screen_yields(
    min_tvl_usd: float = 5_000_000.0,
    chain: str | None = None,
    project: str | None = None,
    stablecoin_only: bool = True,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Screen DeFi yield pools across chains using DefiLlama free API."""
    with DefiLlamaClient() as client:
        return client.get_pools(
            min_tvl=min_tvl_usd,
            chain=chain,
            project=project,
            stablecoin_only=stablecoin_only,
            limit=limit,
        )


def tool_crypto_audit_protocol(protocol_slug: str) -> dict[str, Any]:
    """Audit protocol TVL, category, audits, and chain distribution via DefiLlama free API."""
    with DefiLlamaClient() as client:
        return client.get_protocol(protocol_slug)


def tool_crypto_stablecoin_summary(top_n: int = 10) -> list[dict[str, Any]]:
    """Get market cap and supply growth metrics for top stablecoins via DefiLlama free API."""
    with DefiLlamaClient() as client:
        return client.get_stablecoins(limit=top_n)


def tool_crypto_analyze_orderbook(
    symbol: str = "PAXG/USDT",
    exchange: str = "tokocrypto",
    budget_usd: float = 50.0,
    limit: int = 100,
) -> dict[str, Any]:
    """Analyze real-time exchange orderbook depth, slippage for DCA budget, bid walls, and optimal limit order entry levels."""
    try:
        from binance_client.orderbook import analyze_orderbook, fetch_24h_ticker, fetch_orderbook
    except ImportError:
        repo_root = Path(__file__).resolve().parents[4]
        sys.path.append(str(repo_root / "packages/binance-client/src"))
        from binance_client.orderbook import analyze_orderbook, fetch_24h_ticker, fetch_orderbook

    orderbook = fetch_orderbook(symbol=symbol, exchange=exchange, limit=limit)
    ticker = fetch_24h_ticker(symbol=symbol)
    rate = get_exchange_rate() or 17915.0
    return analyze_orderbook(orderbook, budget_usd=budget_usd, ticker=ticker, usd_idr_rate=rate)


# MCP Server Definitions
TOOLS_SCHEMA = [
    {
        "name": "get_portfolio_overview",
        "description": "Get overall net worth in IDR/USD, MoM percentage change, asset class breakdown, and liquid cash reserve.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Optional snapshot date (YYYY-MM-DD). Defaults to latest."}
            }
        }
    },
    {
        "name": "get_holdings_breakdown",
        "description": "Get detailed holdings filtered by asset class or minimum USD balance.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset_class": {"type": "string", "description": "Asset class (e.g., 'Equities', 'Fixed Income', 'Crypto', 'Cash & Equivalents', 'Commodities')"},
                "min_value_usd": {"type": "number", "description": "Minimum value in USD (default 0)"},
                "date": {"type": "string", "description": "Optional snapshot date (YYYY-MM-DD)"}
            }
        }
    },
    {
        "name": "get_historical_performance",
        "description": "Get historical trajectory of net worth and asset class allocations over recent months.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "months": {"type": "integer", "description": "Number of recent snapshots/months to retrieve (default 6)"}
            }
        }
    },
    {
        "name": "get_portfolio_health_audit",
        "description": "Run an automated comprehensive financial health check: evaluates allocation drift, concentration risk, liquidity runway, and returns advisory recommendations.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_cashflow_analysis",
        "description": "Get daily cashflow analysis from Sans Finance: monthly income, expenses, burn rate, savings rate, and category breakdowns.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "months": {"type": "integer", "description": "Number of months to analyze (default 3)"}
            }
        }
    },
    {
        "name": "get_unified_financial_state",
        "description": "Get complete 360° financial overview unifying investment portfolios with live bank balances, monthly burn rate, and liquid emergency runway.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_rebalancing_plan",
        "description": "Get a deposit-only rebalancing plan to allocate monthly investment cash across underweight asset classes without selling.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "monthly_deposit_idr": {"type": "number", "description": "New deposit amount in IDR to allocate (default 5,000,000)"}
            }
        }
    },
    {
        "name": "get_passive_income_projection",
        "description": "Get projected annual and monthly passive cashflow from SBN coupons, dividends, and crypto staking, compared with living burn rate.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_fire_simulation",
        "description": "Simulate Financial Independence / Retire Early (FIRE) milestones, Coast FIRE, and timeline.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "current_age": {"type": "integer", "description": "Current age (default 30)"},
                "target_retirement_age": {"type": "integer", "description": "Target retirement age (default 55)"},
                "expected_real_return_pct": {"type": "number", "description": "Expected real rate of return above inflation in % (default 6.0)"},
                "safe_withdrawal_rate_pct": {"type": "number", "description": "Safe withdrawal rate in % (default 4.0)"}
            }
        }
    },
    {
        "name": "get_tax_efficiency_audit",
        "description": "Audits Indonesian tax treatment (PPh Final, Exemptions, Reinvestment benefits) across portfolio holdings.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_upcoming_cashflow",
        "description": "Get schedule of upcoming fixed-income cashflow: monthly Sukuk SBN coupon payouts (paid on the 10th of each month).",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_scenario_stress_test",
        "description": "Simulate macroeconomic crisis stress test (Market Crash, Currency Devaluation, Zero Income, Stagflation) on portfolio and cashflow.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "crypto_get_token_prices",
        "description": "Fetch real-time spot prices for crypto tokens across chains (e.g. coingecko:ethereum, ethereum:0x...) via DefiLlama free API.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "coins": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Token identifiers (e.g. ['coingecko:ethereum', 'coingecko:bitcoin'])"
                }
            },
            "required": ["coins"]
        }
    },
    {
        "name": "crypto_screen_yields",
        "description": "Screen DeFi yield pools and lending APYs across chains (filtered by TVL, chain, and stablecoin flag) via DefiLlama free API.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_tvl_usd": {"type": "number", "description": "Minimum pool TVL in USD (default 5,000,000)"},
                "chain": {"type": "string", "description": "Optional chain filter (e.g. arbitrum, ethereum, solana)"},
                "project": {"type": "string", "description": "Optional protocol filter (e.g. aave-v3, pendle)"},
                "stablecoin_only": {"type": "boolean", "description": "Whether to only return stablecoin pools (default true)"},
                "limit": {"type": "integer", "description": "Max number of pools to return (default 20)"}
            }
        }
    },
    {
        "name": "crypto_audit_protocol",
        "description": "Audit counterparty risk, TVL, and audits for a DeFi protocol via DefiLlama free API.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "protocol_slug": {"type": "string", "description": "Protocol slug (e.g. aave-v3, uniswap, lido)"}
            },
            "required": ["protocol_slug"]
        }
    },
    {
        "name": "crypto_stablecoin_summary",
        "description": "Fetch macro stablecoin supply, market cap, and 7d growth metrics via DefiLlama free API.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "top_n": {"type": "integer", "description": "Number of top stablecoins to return (default 10)"}
            }
        }
    },
    {
        "name": "crypto_analyze_orderbook",
        "description": "Analyze real-time orderbook depth, slippage for DCA budget, bid walls, and optimal limit order entry levels for Tokocrypto and Binance.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Trading pair symbol, e.g. PAXG/USDT, XAUT/USDT (default PAXG/USDT)"},
                "exchange": {"type": "string", "enum": ["tokocrypto", "binance"], "description": "Exchange to query (default tokocrypto)"},
                "budget_usd": {"type": "number", "description": "DCA purchase budget in USD to simulate slippage and fees (default 50.0)"},
                "limit": {"type": "integer", "description": "Orderbook depth levels to inspect (default 100)"}
            }
        }
    }
]


def run_mcp_stdio_server():
    """Implements standard JSON-RPC 2.0 MCP server over stdio."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            req_id = req.get("id")
            method = req.get("method")

            if method == "initialize":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {"name": "portfolio-mcp-server", "version": "1.0.0"},
                        "capabilities": {"tools": {}}
                    }
                }
            elif method in ("notifications/initialized", "initialized", "notifications/cancelled"):
                continue
            elif method == "ping":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {}
                }
            elif method == "tools/list":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": TOOLS_SCHEMA}
                }
            elif method == "tools/call":
                params = req.get("params", {})
                tool_name = params.get("name")
                args = params.get("arguments", {})

                if tool_name == "get_portfolio_overview":
                    result = tool_get_portfolio_overview(args.get("date"))
                elif tool_name == "get_holdings_breakdown":
                    result = tool_get_holdings_breakdown(
                        args.get("asset_class"),
                        args.get("min_value_usd", 0.0),
                        args.get("date")
                    )
                elif tool_name == "get_historical_performance":
                    result = tool_get_historical_performance(args.get("months", 6))
                elif tool_name == "get_portfolio_health_audit":
                    result = tool_get_portfolio_health_audit()
                elif tool_name == "get_cashflow_analysis":
                    result = tool_get_cashflow_analysis(args.get("months", 3))
                elif tool_name == "get_unified_financial_state":
                    result = tool_get_unified_financial_state()
                elif tool_name == "get_rebalancing_plan":
                    result = tool_get_rebalancing_plan(args.get("monthly_deposit_idr", 5_000_000.0))
                elif tool_name == "get_passive_income_projection":
                    result = tool_get_passive_income_projection()
                elif tool_name == "get_upcoming_cashflow":
                    result = tool_get_upcoming_cashflow()
                elif tool_name == "get_fire_simulation":
                    result = tool_get_fire_simulation(
                        target_annual_spending_idr=args.get("target_annual_spending_idr"),
                        expected_real_return_pct=args.get("expected_real_return_pct", 6.0),
                        safe_withdrawal_rate_pct=args.get("safe_withdrawal_rate_pct", 4.0),
                        current_age=args.get("current_age", 30),
                        target_retirement_age=args.get("target_retirement_age", 55)
                    )
                elif tool_name == "get_tax_efficiency_audit":
                    result = tool_get_tax_efficiency_audit()
                elif tool_name == "get_scenario_stress_test":
                    result = tool_get_scenario_stress_test()
                elif tool_name == "crypto_get_token_prices":
                    result = tool_crypto_get_token_prices(args.get("coins", []))
                elif tool_name == "crypto_screen_yields":
                    result = tool_crypto_screen_yields(
                        min_tvl_usd=args.get("min_tvl_usd", 5_000_000.0),
                        chain=args.get("chain"),
                        project=args.get("project"),
                        stablecoin_only=args.get("stablecoin_only", True),
                        limit=args.get("limit", 20),
                    )
                elif tool_name == "crypto_audit_protocol":
                    result = tool_crypto_audit_protocol(args.get("protocol_slug", ""))
                elif tool_name == "crypto_stablecoin_summary":
                    result = tool_crypto_stablecoin_summary(top_n=args.get("top_n", 10))
                elif tool_name == "crypto_analyze_orderbook":
                    result = tool_crypto_analyze_orderbook(
                        symbol=args.get("symbol", "PAXG/USDT"),
                        exchange=args.get("exchange", "tokocrypto"),
                        budget_usd=args.get("budget_usd", 50.0),
                        limit=args.get("limit", 100),
                    )
                else:
                    resp = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
                    }
                    sys.stdout.write(json.dumps(resp) + "\n")
                    sys.stdout.flush()
                    continue

                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
                    }
                }
            elif req_id is None:
                # Per JSON-RPC 2.0: The Server MUST NOT reply to a Notification
                continue
            else:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Unsupported method: {method}"}
                }

            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        except Exception as e:
            req_id_val = req.get("id") if "req" in locals() and isinstance(req, dict) else None
            if req_id_val is not None:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": req_id_val,
                    "error": {"code": -32603, "message": f"Internal error: {e!s}"}
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Portfolio MCP Server and AI Query CLI")
    parser.add_argument("--mcp", action="store_true", help="Run as stdio MCP JSON-RPC Server (default when no action specified)")
    parser.add_argument("--dashboard", action="store_true", help="Launch executive visual terminal dashboard")
    parser.add_argument("--audit", action="store_true", help="Run and print portfolio health audit")
    parser.add_argument("--unified", action="store_true", help="Print unified 360° financial state (portfolio + cashflow)")
    parser.add_argument("--cashflow", action="store_true", help="Print cashflow analysis from Sans Finance")
    parser.add_argument("--rebalance", action="store_true", help="Print deposit-only portfolio rebalancing plan")
    parser.add_argument("--passive-income", action="store_true", help="Print projected passive income and FI coverage")
    parser.add_argument("--fire", action="store_true", help="Print FIRE simulation and milestones")
    parser.add_argument("--tax", action="store_true", help="Print tax efficiency audit")
    parser.add_argument("--stress-test", action="store_true", help="Run macroeconomic crisis stress tests")
    parser.add_argument("--prune", action="store_true", help="Prune historical snapshots to keep only the latest per month")
    parser.add_argument("--apply-prune", action="store_true", help="Execute actual deletion during pruning")
    parser.add_argument("--deposit", type=float, default=5_000_000.0, help="Monthly deposit amount in IDR for rebalancing")
    parser.add_argument("--digest", action="store_true", help="Print latest AI markdown digest")
    parser.add_argument("--json", action="store_true", help="Print latest AI state JSON")
    parser.add_argument("--overview", action="store_true", help="Print portfolio overview summary")
    parser.add_argument("--holdings", action="store_true", help="Print all holdings breakdown")
    parser.add_argument("--history", action="store_true", help="Print historical multi-month performance")
    parser.add_argument("--class-filter", help="Filter holdings by asset class")
    parser.add_argument("--crypto-yields", action="store_true", help="Query top DeFi yield pools via DefiLlama")
    parser.add_argument("--crypto-stables", action="store_true", help="Query top stablecoins by market cap via DefiLlama")
    parser.add_argument("--crypto-protocol", help="Audit protocol TVL & info via DefiLlama slug (e.g. aave-v3)")
    parser.add_argument("--crypto-prices", nargs="+", help="Query token prices via DefiLlama (e.g. coingecko:ethereum)")
    parser.add_argument("--orderbook", nargs="?", const="PAXG/USDT", help="Analyze real-time orderbook (default: PAXG/USDT)")
    parser.add_argument("--exchange", default="tokocrypto", choices=["tokocrypto", "binance"], help="Exchange for orderbook query")
    parser.add_argument("--budget", type=float, default=50.0, help="DCA budget in USD (default: 50.0)")
    args = parser.parse_args()

    if args.mcp:
        run_mcp_stdio_server()
        return

    if args.dashboard:
        from portfolio_app.dashboard import render_dashboard
        render_dashboard()
    elif args.prune:
        from portfolio_app.snapshot_pruner import prune_local_files, prune_sqlite_snapshots
        from portfolio_app.cashflow_analyzer import resolve_sans_finance_db
        apply = args.apply_prune
        data_dir = get_data_dir()
        db_path = resolve_sans_finance_db(data_dir=data_dir, auto_pull_gcs=False)

        res_files = prune_local_files(data_dir, apply=apply)
        res_db = prune_sqlite_snapshots(db_path, apply=apply) if db_path else {}
        print(json.dumps({
            "mode": "APPLY" if apply else "DRY_RUN",
            "local_files": res_files,
            "sqlite_db": res_db
        }, indent=2))
    elif args.unified:
        print(json.dumps(tool_get_unified_financial_state(), indent=2))
    elif args.cashflow:
        print(json.dumps(tool_get_cashflow_analysis(), indent=2))
    elif args.rebalance:
        print(json.dumps(tool_get_rebalancing_plan(monthly_deposit_idr=args.deposit), indent=2))
    elif args.passive_income:
        print(json.dumps(tool_get_passive_income_projection(), indent=2))
    elif args.fire:
        print(json.dumps(tool_get_fire_simulation(), indent=2))
    elif args.tax:
        print(json.dumps(tool_get_tax_efficiency_audit(), indent=2))
    elif args.stress_test:
        print(json.dumps(tool_get_scenario_stress_test(), indent=2))
    elif args.audit:
        result = tool_get_portfolio_health_audit()
        print(json.dumps(result, indent=2))
    elif args.digest:
        latest_md = get_data_dir() / "latest_ai_digest.md"
        if latest_md.exists():
            print(latest_md.read_text(encoding="utf-8"))
        else:
            print("No latest_ai_digest.md found. Run generator first.")
    elif args.json:
        latest_json = get_data_dir() / "latest_ai_state.json"
        if latest_json.exists():
            print(latest_json.read_text(encoding="utf-8"))
        else:
            print("No latest_ai_state.json found. Run generator first.")
    elif args.overview:
        print(json.dumps(tool_get_portfolio_overview(), indent=2))
    elif args.holdings:
        print(json.dumps(tool_get_holdings_breakdown(asset_class=args.class_filter), indent=2))
    elif args.history:
        print(json.dumps(tool_get_historical_performance(), indent=2))
    elif args.crypto_yields:
        print(json.dumps(tool_crypto_screen_yields(), indent=2))
    elif args.crypto_stables:
        print(json.dumps(tool_crypto_stablecoin_summary(), indent=2))
    elif args.crypto_protocol:
        print(json.dumps(tool_crypto_audit_protocol(args.crypto_protocol), indent=2))
    elif args.crypto_prices:
        print(json.dumps(tool_crypto_get_token_prices(args.crypto_prices), indent=2))
    elif args.orderbook:
        print(json.dumps(tool_crypto_analyze_orderbook(
            symbol=args.orderbook,
            exchange=args.exchange,
            budget_usd=args.budget,
        ), indent=2))
    else:
        # Default to running the MCP stdio server
        run_mcp_stdio_server()


if __name__ == "__main__":
    main()

