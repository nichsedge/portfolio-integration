"""
AI Financial State & Digest Generator
Generates token-efficient, non-redundant state representations (JSON and Markdown)
optimized for ingestion by Agentic AI systems (Hermes Agent, Claude, GPT, MCP tools).
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
import pendulum

# Import utils
try:
    from transform_core import get_data_dir, get_exchange_rate
except ImportError:
    repo_root = Path(__file__).resolve().parents[4]
    import sys
    sys.path.append(str(repo_root / "packages/transform-core/src"))
    from transform_core import get_data_dir, get_exchange_rate


# Target asset allocation benchmarks (can be customized)
DEFAULT_TARGET_ALLOCATION = {
    "Fixed Income": 50.0,
    "Equities": 25.0,
    "Cash & Equivalents": 10.0,
    "Crypto": 10.0,
    "Commodities": 5.0,
}

# Conservative baseline APY yield benchmarks for passive income forecasting
ASSET_CLASS_YIELD_BENCHMARKS = {
    "Fixed Income": 0.065,         # SBN / FR / ORI ~6.5% APY
    "Equities": 0.035,             # Stock dividend yield ~3.5% APY
    "Crypto": 0.045,               # Staking / LP yield ~4.5% APY (for yield-generating crypto)
    "Cash & Equivalents": 0.040,   # High-yield savings / Money Market ~4.0% APY
    "Commodities": 0.0,            # Gold / Silver 0.0% cash yield
}


def calculate_passive_income(
    holdings: List[Dict[str, Any]],
    exchange_rate: float,
    monthly_burn_idr: Optional[float] = None
) -> Dict[str, Any]:
    """Calculates estimated annual and monthly passive cashflow from holdings."""
    breakdown: Dict[str, Dict[str, float]] = {
        aclass: {"value_idr": 0.0, "annual_yield_idr": 0.0, "yield_rate": rate}
        for aclass, rate in ASSET_CLASS_YIELD_BENCHMARKS.items()
    }
    
    total_annual_idr = 0.0

    for h in holdings:
        val_idr = h.get("value_idr") or 0.0
        if val_idr <= 0:
            val_idr = (h.get("value_usd") or 0.0) * exchange_rate

        aclass = h.get("asset_class") or "Other"
        category = h.get("category") or ""
        
        # Determine applicable yield rate
        rate = ASSET_CLASS_YIELD_BENCHMARKS.get(aclass, 0.0)
        # Only staked or yield/LP crypto yields cashflow
        if aclass == "Crypto" and category not in {"Staked", "Yield / LP"}:
            rate = 0.0

        annual_cashflow = val_idr * rate
        total_annual_idr += annual_cashflow

        if aclass in breakdown:
            breakdown[aclass]["value_idr"] += val_idr
            breakdown[aclass]["annual_yield_idr"] += annual_cashflow

    monthly_passive_idr = total_annual_idr / 12.0
    monthly_passive_usd = monthly_passive_idr / exchange_rate if exchange_rate > 0 else 0.0

    # Calculate Financial Independence (FI) Coverage Ratio
    fi_coverage_pct = 0.0
    fi_status = "Accumulation (<25%)"
    if monthly_burn_idr and monthly_burn_idr > 0:
        fi_coverage_pct = round((monthly_passive_idr / monthly_burn_idr) * 100, 1)
        if fi_coverage_pct >= 100.0:
            fi_status = "Full Financial Independence (>=100%)"
        elif fi_coverage_pct >= 75.0:
            fi_status = "Near FI (75-99%)"
        elif fi_coverage_pct >= 50.0:
            fi_status = "Coast / Halfway FI (50-74%)"
        elif fi_coverage_pct >= 25.0:
            fi_status = "Emerging FI Buffer (25-49%)"

    return {
        "projected_annual_passive_income_idr": round(total_annual_idr, 2),
        "projected_monthly_passive_income_idr": round(monthly_passive_idr, 2),
        "projected_monthly_passive_income_usd": round(monthly_passive_usd, 2),
        "fi_coverage_pct": fi_coverage_pct,
        "fi_status": fi_status,
        "breakdown": [
            {
                "asset_class": k,
                "value_idr": round(v["value_idr"], 0),
                "annual_income_idr": round(v["annual_yield_idr"], 0),
                "monthly_income_idr": round(v["annual_yield_idr"] / 12.0, 0),
                "estimated_yield_pct": round(v["yield_rate"] * 100, 1),
            }
            for k, v in breakdown.items()
            if v["value_idr"] > 0
        ]
    }


def calculate_rebalancing_orders(
    holdings: List[Dict[str, Any]],
    total_assets_idr: float,
    exchange_rate: float,
    monthly_deposit_idr: float = 5_000_000.0,
    target_allocation: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """Calculates deposit-only rebalancing allocations to correct underweight asset classes."""
    if target_allocation is None:
        target_allocation = DEFAULT_TARGET_ALLOCATION

    if monthly_deposit_idr <= 0:
        monthly_deposit_idr = 5_000_000.0

    new_total_idr = total_assets_idr + monthly_deposit_idr

    # Calculate current class weights
    current_values: Dict[str, float] = {k: 0.0 for k in target_allocation.keys()}
    for h in holdings:
        val_idr = h.get("value_idr") or 0.0
        if val_idr <= 0:
            val_idr = (h.get("value_usd") or 0.0) * exchange_rate
        aclass = h.get("asset_class") or "Other"
        if aclass in current_values:
            current_values[aclass] += val_idr

    # Identify underweight classes and deficit amounts
    deficits: Dict[str, float] = {}
    total_deficit = 0.0

    for aclass, target_pct in target_allocation.items():
        target_val = new_total_idr * (target_pct / 100.0)
        curr_val = current_values.get(aclass, 0.0)
        deficit = max(0.0, target_val - curr_val)
        if deficit > 0:
            deficits[aclass] = deficit
            total_deficit += deficit

    # Distribute deposit
    recommendations = []
    actions_map = {
        "Fixed Income": "DCA into Government Bonds (SBN / FR / ORI) or Corporate Bonds",
        "Equities": "Accumulate Indo Value/Dividend Stocks or S&P 500 Index Funds",
        "Cash & Equivalents": "Build High-Yield Savings / Money Market Fund liquidity",
        "Crypto": "DCA into Bluechip Crypto (BTC / ETH / SOL)",
        "Commodities": "Buy Physical Gold / Gold Stablecoins (PAXG)",
    }

    for aclass, deficit in sorted(deficits.items(), key=lambda x: x[1], reverse=True):
        alloc_ratio = deficit / total_deficit if total_deficit > 0 else 0.0
        deposit_share_idr = round(monthly_deposit_idr * alloc_ratio, 0)
        curr_pct = round(current_values.get(aclass, 0.0) / total_assets_idr * 100, 1) if total_assets_idr > 0 else 0.0
        target_pct = target_allocation.get(aclass, 0.0)

        if deposit_share_idr > 0:
            recommendations.append({
                "asset_class": aclass,
                "current_weight_pct": curr_pct,
                "target_weight_pct": target_pct,
                "drift_pct": round(curr_pct - target_pct, 1),
                "deposit_allocation_idr": deposit_share_idr,
                "deposit_allocation_usd": round(deposit_share_idr / exchange_rate, 2),
                "allocation_pct_of_deposit": round(alloc_ratio * 100, 1),
                "suggested_action": actions_map.get(aclass, f"Accumulate {aclass}"),
            })

    return {
        "deposit_amount_idr": monthly_deposit_idr,
        "deposit_amount_usd": round(monthly_deposit_idr / exchange_rate, 2),
        "post_deposit_total_idr": round(new_total_idr, 0),
        "recommendations": recommendations
    }


def calculate_fire_simulation(
    net_worth_idr: float,
    monthly_burn_idr: float,
    monthly_savings_idr: float = 0.0,
    expected_real_return_pct: float = 6.0,
    safe_withdrawal_rate_pct: float = 4.0,
    current_age: int = 30,
    target_retirement_age: int = 55
) -> Dict[str, Any]:
    """
    Simulates Financial Independence / Retire Early (FIRE) metrics, milestones,
    Coast FIRE readiness, and projected timeline.
    """
    annual_burn_idr = max(monthly_burn_idr * 12.0, 1.0)
    swr = safe_withdrawal_rate_pct / 100.0
    fire_number_idr = round(annual_burn_idr / swr, 0)
    lean_fire_number_idr = round(fire_number_idr * 0.75, 0)
    fat_fire_number_idr = round(fire_number_idr * 1.50, 0)

    progress_pct = round((net_worth_idr / fire_number_idr * 100), 1) if fire_number_idr > 0 else 0.0

    # Coast FIRE calculation
    years_to_target = max(1, target_retirement_age - current_age)
    real_rate = expected_real_return_pct / 100.0
    growth_factor = (1.0 + real_rate) ** years_to_target
    coast_fire_number_idr = round(fire_number_idr / growth_factor, 0)
    is_coast_fire = net_worth_idr >= coast_fire_number_idr

    # Timeline projection month-by-month
    projected_months = 0
    projected_years = 0.0
    projected_date = "N/A"
    
    if net_worth_idr >= fire_number_idr:
        projected_years = 0.0
        projected_date = "Already Achieved"
    elif monthly_savings_idr > 0 or net_worth_idr > 0:
        current_val = net_worth_idr
        monthly_rate = real_rate / 12.0
        
        while current_val < fire_number_idr and projected_months < 600:
            current_val = current_val * (1.0 + monthly_rate) + max(0.0, monthly_savings_idr)
            projected_months += 1

        projected_years = round(projected_months / 12.0, 1)
        if projected_months < 600:
            projected_date = pendulum.now().add(months=projected_months).format("YYYY-MM")
        else:
            projected_date = "> 50 Years"

    return {
        "annual_burn_idr": round(annual_burn_idr, 0),
        "fire_number_idr": fire_number_idr,
        "lean_fire_idr": lean_fire_number_idr,
        "fat_fire_idr": fat_fire_number_idr,
        "current_progress_pct": progress_pct,
        "coast_fire_number_idr": coast_fire_number_idr,
        "is_coast_fire_achieved": is_coast_fire,
        "coast_surplus_idr": round(net_worth_idr - coast_fire_number_idr, 0),
        "assumptions": {
            "real_return_pct": expected_real_return_pct,
            "swr_pct": safe_withdrawal_rate_pct,
            "monthly_savings_idr": round(monthly_savings_idr, 0),
            "current_age": current_age,
            "target_retirement_age": target_retirement_age,
        },
        "projected_timeline": {
            "years_to_fire": projected_years,
            "estimated_fire_date": projected_date,
        }
    }


def calculate_tax_efficiency_audit(
    holdings: List[Dict[str, Any]],
    exchange_rate: float
) -> Dict[str, Any]:
    """
    Audits Indonesian tax treatment across portfolio holdings (PPh Final, Exemptions, Reinvestment).
    """
    tax_buckets: Dict[str, Dict[str, Any]] = {
        "Tax Exempt (0% PPh)": {"value_idr": 0.0, "assets": []},
        "Reinvestment 0% / Reduced (Indo Equities)": {"value_idr": 0.0, "assets": []},
        "Preferential Final 10% (SBN / Bonds)": {"value_idr": 0.0, "assets": []},
        "Domestic Crypto Final (0.1% PPh / 0.11% PPN)": {"value_idr": 0.0, "assets": []},
        "Bank Interest 20% Drag": {"value_idr": 0.0, "assets": []},
    }

    total_value_idr = 0.0

    for h in holdings:
        val_idr = h.get("value_idr") or 0.0
        if val_idr <= 0:
            val_idr = (h.get("value_usd") or 0.0) * exchange_rate
        total_value_idr += val_idr

        cat = h.get("category", "")
        aclass = h.get("asset_class", "")
        asset = h.get("asset", "")

        if cat in {"Money Market Fund", "Equity Fund", "Mutual Fund"}:
            bucket = "Tax Exempt (0% PPh)"
        elif aclass == "Equities" or cat in {"Indo Stocks"}:
            bucket = "Reinvestment 0% / Reduced (Indo Equities)"
        elif aclass == "Fixed Income" or cat in {"SBN", "Corporate Bond"}:
            bucket = "Preferential Final 10% (SBN / Bonds)"
        elif aclass == "Crypto":
            bucket = "Domestic Crypto Final (0.1% PPh / 0.11% PPN)"
        elif cat in {"Bank Account", "Digital Bank"}:
            bucket = "Bank Interest 20% Drag"
        else:
            bucket = "Tax Exempt (0% PPh)"

        tax_buckets[bucket]["value_idr"] += val_idr
        if val_idr > 5_000_000:
            tax_buckets[bucket]["assets"].append(asset)

    efficiency_score = 0.0
    if total_value_idr > 0:
        exempt_pct = tax_buckets["Tax Exempt (0% PPh)"]["value_idr"] / total_value_idr
        equity_pct = tax_buckets["Reinvestment 0% / Reduced (Indo Equities)"]["value_idr"] / total_value_idr
        sbn_pct = tax_buckets["Preferential Final 10% (SBN / Bonds)"]["value_idr"] / total_value_idr
        bank_pct = tax_buckets["Bank Interest 20% Drag"]["value_idr"] / total_value_idr

        efficiency_score = round((exempt_pct * 100 + equity_pct * 95 + sbn_pct * 85 + (1 - bank_pct) * 20), 0)
        efficiency_score = min(100.0, max(0.0, efficiency_score))

    opportunities = []
    if tax_buckets["Bank Interest 20% Drag"]["value_idr"] > 20_000_000:
        opportunities.append(
            "High liquid cash in bank accounts incurs 20% PPh withholding on interest. Consider sweeping excess liquidity into Money Market Funds (Reksa Dana Pasar Uang) for 0% tax."
        )
    if tax_buckets["Preferential Final 10% (SBN / Bonds)"]["value_idr"] > 0:
        opportunities.append(
            "SBN Sukuk / Obligasi Negara benefit from fixed 10% final PPh, significantly lower than general income tax brackets."
        )

    return {
        "tax_efficiency_score": efficiency_score,
        "tax_efficiency_grade": "A+" if efficiency_score >= 90 else "A" if efficiency_score >= 80 else "B",
        "buckets": [
            {
                "regime": k,
                "value_idr": round(v["value_idr"], 0),
                "weight_pct": round(v["value_idr"] / total_value_idr * 100, 1) if total_value_idr > 0 else 0.0,
                "major_assets": v["assets"][:4]
            }
            for k, v in tax_buckets.items()
            if v["value_idr"] > 0
        ],
        "optimization_opportunities": opportunities
    }


def load_historical_snapshots(data_dir: Path) -> List[Dict[str, Any]]:
    """Loads all snapshot files sorted chronologically."""
    snapshot_files = sorted(list(data_dir.glob("*_snapshot.json")))
    snapshots = []

    for file_path in snapshot_files:
        # Skip latest/special pointers if any
        if file_path.name.startswith("latest"):
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                snapshots.append(data)
        except Exception as e:
            print(f"⚠️ Warning: Could not read {file_path}: {e}")

    # Sort by metadata date
    snapshots.sort(key=lambda s: s.get("metadata", {}).get("date", ""))
    return snapshots


def analyze_currency_exposure(holdings: List[Dict[str, Any]], exchange_rate: float) -> Dict[str, Any]:
    """Calculate asset currency denomination exposure (IDR, USD, Native Crypto)."""
    idr_val = 0.0
    usd_val = 0.0
    crypto_val = 0.0
    total_val = 0.0

    for h in holdings:
        val_idr = h.get("value_idr") or 0.0
        if val_idr <= 0:
            val_idr = (h.get("value_usd") or 0.0) * exchange_rate

        curr = (h.get("currency") or "IDR").upper()
        aclass = h.get("asset_class") or "Other"

        total_val += val_idr
        if aclass == "Crypto" and curr not in {"USD", "USDT", "USDC", "DAI", "FDUSD", "BUSD", "PYUSD"}:
            crypto_val += val_idr
        elif curr == "USD" or h.get("category") in {"Stablecoin", "US Stocks"}:
            usd_val += val_idr
        else:
            idr_val += val_idr

    if total_val == 0:
        return {"idr_pct": 0.0, "usd_pct": 0.0, "crypto_pct": 0.0}

    return {
        "idr_pct": round(idr_val / total_val * 100, 1),
        "usd_pct": round(usd_val / total_val * 100, 1),
        "crypto_pct": round(crypto_val / total_val * 100, 1),
        "idr_val": round(idr_val, 2),
        "usd_val": round(usd_val, 2),
        "crypto_val": round(crypto_val, 2),
    }


def generate_ai_state(
    current_snapshot: Dict[str, Any],
    all_snapshots: Optional[List[Dict[str, Any]]] = None,
    target_allocation: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """
    Constructs a dense, token-efficient financial state dictionary.
    Removes repetitive boilerplate and focuses on actionable financial metrics.
    """
    if target_allocation is None:
        target_allocation = DEFAULT_TARGET_ALLOCATION

    metadata = current_snapshot.get("metadata", {})
    totals = current_snapshot.get("totals", {})
    allocation = current_snapshot.get("allocation", {})
    holdings = current_snapshot.get("holdings", [])

    date = metadata.get("date", pendulum.now().format("YYYY-MM-DD"))
    exchange_rate = metadata.get("exchange_rate") or get_exchange_rate()
    net_worth_idr = totals.get("net_worth_idr", 0.0)
    net_worth_usd = totals.get("net_worth_usd", round(net_worth_idr / exchange_rate, 2))
    total_assets_idr = totals.get("total_assets_idr", net_worth_idr)
    total_liabilities_idr = totals.get("total_liabilities_idr", 0.0)

    # 1. MoM Growth & Historical Comparison
    mom_change_idr = 0.0
    mom_change_pct = 0.0
    prev_date = None

    if all_snapshots:
        # Filter snapshots before current date
        prev_snapshots = [s for s in all_snapshots if s.get("metadata", {}).get("date", "") < date]
        if prev_snapshots:
            prev = prev_snapshots[-1]
            prev_date = prev.get("metadata", {}).get("date")
            prev_nw = prev.get("totals", {}).get("net_worth_idr", 0.0)
            if prev_nw > 0:
                mom_change_idr = net_worth_idr - prev_nw
                mom_change_pct = round((mom_change_idr / prev_nw) * 100, 2)

    # 2. Asset Allocation & Drift
    by_class_raw = allocation.get("by_asset_class", [])
    asset_allocation = []
    class_map = {}

    for item in by_class_raw:
        aclass = item.get("asset_class", "Other")
        pct = item.get("percentage", 0.0)
        val_idr = item.get("value_idr", 0.0)
        target_pct = target_allocation.get(aclass, 0.0)
        drift = round(pct - target_pct, 1)

        class_map[aclass] = pct
        asset_allocation.append({
            "asset_class": aclass,
            "weight_pct": pct,
            "target_pct": target_pct,
            "drift_pct": drift,
            "value_idr": round(val_idr, 0),
            "value_usd": round(val_idr / exchange_rate, 2),
            "count": item.get("count", 0),
        })

    # 3. Currency Exposure
    currency_exposure = analyze_currency_exposure(holdings, exchange_rate)

    # 4. Liquidity & Cash Buffer
    liquid_cash_val = sum(
        h.get("value_idr", 0.0) for h in holdings
        if h.get("asset_class") == "Cash & Equivalents"
    )
    liquid_cash_pct = round((liquid_cash_val / total_assets_idr * 100), 1) if total_assets_idr > 0 else 0.0

    # 5. Risk & Concentration Alerts
    alerts = []
    
    # Sort holdings by value descending
    sorted_holdings = sorted(
        holdings,
        key=lambda h: h.get("value_idr") or ((h.get("value_usd") or 0.0) * exchange_rate),
        reverse=True
    )

    top_holding = sorted_holdings[0] if sorted_holdings else None
    if top_holding and total_assets_idr > 0:
        top_val = top_holding.get("value_idr") or ((top_holding.get("value_usd") or 0.0) * exchange_rate)
        top_pct = round(top_val / total_assets_idr * 100, 1)
        if top_pct > 25.0:
            alerts.append(f"High concentration in single asset: {top_holding.get('asset')} ({top_pct}% of portfolio)")

    crypto_pct = class_map.get("Crypto", 0.0)
    if crypto_pct > 20.0:
        alerts.append(f"High volatile crypto exposure: {crypto_pct}% (recommended < 15%)")

    if liquid_cash_pct < 5.0:
        alerts.append(f"Low liquid cash reserve: {liquid_cash_pct}% (recommended >= 10% for liquidity buffer)")

    # 6. Dense Top Holdings (>= 1.5% weight)
    top_holdings_dense = []
    for h in sorted_holdings:
        val_idr = h.get("value_idr") or ((h.get("value_usd") or 0.0) * exchange_rate)
        pct = round((val_idr / total_assets_idr * 100), 2) if total_assets_idr > 0 else 0.0
        
        # Include if >= 1.5% or top 10
        if pct >= 1.5 or len(top_holdings_dense) < 8:
            top_holdings_dense.append({
                "asset": h.get("asset"),
                "category": h.get("category"),
                "asset_class": h.get("asset_class"),
                "source": h.get("source"),
                "weight_pct": pct,
                "value_idr": round(val_idr, 0),
                "value_usd": round(val_idr / exchange_rate, 2),
            })

    # 7. Historical Trajectory (Last 6 snapshots)
    history_trajectory = []
    if all_snapshots:
        # Take up to last 6 snapshots ending with current
        relevant = [s for s in all_snapshots if s.get("metadata", {}).get("date", "") <= date][-6:]
        for s in relevant:
            s_meta = s.get("metadata", {})
            s_totals = s.get("totals", {})
            s_alloc = {
                item.get("asset_class", "Other"): item.get("percentage", 0.0)
                for item in s.get("allocation", {}).get("by_asset_class", [])
            }
            history_trajectory.append({
                "date": s_meta.get("date"),
                "net_worth_idr": s_totals.get("net_worth_idr", 0.0),
                "net_worth_usd": s_totals.get("net_worth_usd", 0.0),
                "fixed_income_pct": s_alloc.get("Fixed Income", 0.0),
                "equities_pct": s_alloc.get("Equities", 0.0),
                "crypto_pct": s_alloc.get("Crypto", 0.0),
                "cash_pct": s_alloc.get("Cash & Equivalents", 0.0),
            })

    # 8. Sans Finance Cashflow Integration (if SQLite DB is available)
    cashflow_summary = None
    monthly_burn_for_fi = None
    try:
        from portfolio_app.cashflow_analyzer import (
            resolve_sans_finance_db,
            get_live_accounts,
            get_cashflow_metrics,
            calculate_runway,
        )
        db_path = resolve_sans_finance_db(data_dir=get_data_dir(), auto_pull_gcs=False)
        if db_path and db_path.exists():
            accounts_data = get_live_accounts(db_path, exchange_rate)
            cashflow_data = get_cashflow_metrics(db_path, months=3, exchange_rate=exchange_rate)
            total_liquid_idr = liquid_cash_val + accounts_data["total_liquid_idr"]
            runway_data = calculate_runway(total_liquid_idr, cashflow_data["avg_monthly_burn_idr"])
            monthly_burn_for_fi = cashflow_data["avg_monthly_burn_idr"]

            cashflow_summary = {
                "db_source": str(db_path.name),
                "live_bank_cash_idr": accounts_data["total_liquid_idr"],
                "live_bank_cash_usd": accounts_data["total_liquid_usd"],
                "consolidated_net_worth_idr": round(net_worth_idr + accounts_data["total_liquid_idr"], 2),
                "consolidated_net_worth_usd": round(net_worth_usd + accounts_data["total_liquid_usd"], 2),
                "monthly_income_idr": cashflow_data["avg_monthly_income_idr"],
                "monthly_burn_idr": cashflow_data["avg_monthly_burn_idr"],
                "monthly_savings_idr": cashflow_data["avg_monthly_savings_idr"],
                "savings_rate_pct": cashflow_data["overall_savings_rate_pct"],
                "runway_months": runway_data["runway_months"],
                "runway_health": runway_data["health"],
                "top_categories": cashflow_data["top_categories"],
            }
    except Exception as e:
        print(f"ℹ️ Note: Sans Finance cashflow integration skipped ({e})")

    # 9. Passive Income & Yield Projections
    passive_income = calculate_passive_income(holdings, exchange_rate, monthly_burn_idr=monthly_burn_for_fi)

    # 10. Deposit-Only Rebalancing Plan
    rebalancing_plan = calculate_rebalancing_orders(
        holdings=holdings,
        total_assets_idr=total_assets_idr,
        exchange_rate=exchange_rate,
        monthly_deposit_idr=5_000_000.0,
        target_allocation=target_allocation
    )

    return {
        "state_date": date,
        "exchange_rate": exchange_rate,
        "macro_metrics": {
            "net_worth_idr": net_worth_idr,
            "net_worth_usd": net_worth_usd,
            "total_assets_idr": total_assets_idr,
            "total_liabilities_idr": total_liabilities_idr,
            "mom_growth_pct": mom_change_pct,
            "mom_growth_idr": mom_change_idr,
            "comparison_period": f"{prev_date} → {date}" if prev_date else "N/A (Initial)"
        },
        "asset_allocation": asset_allocation,
        "currency_exposure": currency_exposure,
        "liquidity": {
            "liquid_cash_idr": round(liquid_cash_val, 0),
            "liquid_cash_usd": round(liquid_cash_val / exchange_rate, 2),
            "liquid_cash_pct": liquid_cash_pct,
        },
        "passive_income": passive_income,
        "rebalancing_plan": rebalancing_plan,
        "risk_and_alerts": {
            "crypto_exposure_pct": crypto_pct,
            "alerts": alerts,
        },
        "top_holdings": top_holdings_dense,
        "history_trajectory": history_trajectory,
        "cashflow_and_runway": cashflow_summary
    }


def generate_ai_digest_markdown(ai_state: Dict[str, Any]) -> str:
    """Renders the AI financial state as an executive markdown report for prompt injection."""
    metrics = ai_state["macro_metrics"]
    date = ai_state["state_date"]
    fx = ai_state["exchange_rate"]

    growth_sign = "+" if metrics["mom_growth_pct"] >= 0 else ""
    mom_str = f"{growth_sign}{metrics['mom_growth_pct']}% (Rp {metrics['mom_growth_idr']:+,.0f})" if metrics["comparison_period"] != "N/A (Initial)" else "Initial Baseline"

    md = []
    md.append(f"# Financial Portfolio AI State Brief — {date}")
    md.append(f"**Exchange Rate**: 1 USD = Rp {fx:,.2f} | **Generated for**: Autonomous AI Advisor Review\n")

    md.append("## 1. Executive Macro Overview")
    md.append(f"- **Net Worth**: **Rp {metrics['net_worth_idr']:,.0f}** (${metrics['net_worth_usd']:,.2f})")
    md.append(f"- **Month-over-Month Change**: **{mom_str}** ({metrics['comparison_period']})")
    md.append(f"- **Total Assets**: Rp {metrics['total_assets_idr']:,.0f}")
    if metrics["total_liabilities_idr"] > 0:
        md.append(f"- **Total Liabilities**: Rp {metrics['total_liabilities_idr']:,.0f}")
    md.append(f"- **Liquid Cash Reserve**: Rp {ai_state['liquidity']['liquid_cash_idr']:,.0f} ({ai_state['liquidity']['liquid_cash_pct']}% of portfolio)")
    md.append("")

    md.append("## 2. Asset Allocation & Target Drift")
    md.append("| Asset Class | Current Value (IDR) | Weight (%) | Target (%) | Drift (%) |")
    md.append("| :--- | :--- | :--- | :--- | :--- |")
    for item in ai_state["asset_allocation"]:
        drift_str = f"{item['drift_pct']:+0.1f}%" if item['drift_pct'] != 0 else "0.0%"
        md.append(f"| **{item['asset_class']}** | Rp {item['value_idr']:,.0f} | {item['weight_pct']:.1f}% | {item['target_pct']:.1f}% | `{drift_str}` |")
    md.append("")

    if ai_state.get("passive_income"):
        pi = ai_state["passive_income"]
        md.append("## 3. Projected Passive Cashflow & FI Status")
        md.append(f"- **Projected Annual Yield**: **Rp {pi['projected_annual_passive_income_idr']:,.0f}**")
        md.append(f"- **Projected Monthly Passive Cashflow**: **Rp {pi['projected_monthly_passive_income_idr']:,.0f}** (${pi['projected_monthly_passive_income_usd']:,.2f}/mo)")
        if pi.get("fi_coverage_pct", 0) > 0:
            md.append(f"- **Financial Independence Coverage**: **{pi['fi_coverage_pct']}%** of living burn covered (*{pi['fi_status']}*)")
        md.append("")

    md.append("## 4. Currency Exposure")
    curr = ai_state["currency_exposure"]
    md.append(f"- **IDR Assets**: {curr.get('idr_pct', 0)}% (Rp {curr.get('idr_val', 0):,.0f})")
    md.append(f"- **USD / Stablecoins**: {curr.get('usd_pct', 0)}% (Rp {curr.get('usd_val', 0):,.0f})")
    md.append(f"- **Native Crypto**: {curr.get('crypto_pct', 0)}% (Rp {curr.get('crypto_val', 0):,.0f})")
    md.append("")

    if ai_state["risk_and_alerts"]["alerts"]:
        md.append("## 5. Key Risk Alerts & Observations")
        for alert in ai_state["risk_and_alerts"]["alerts"]:
            md.append(f"- ⚠️ **{alert}**")
        md.append("")

    md.append("## 6. Top Portfolio Holdings")
    md.append("| Asset | Category | Asset Class | Platform | Value (IDR) | Weight (%) |")
    md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for h in ai_state["top_holdings"]:
        md.append(f"| {h['asset']} | {h['category']} | {h['asset_class']} | {h['source']} | Rp {h['value_idr']:,.0f} | {h['weight_pct']:.1f}% |")
    md.append("")

    if ai_state.get("rebalancing_plan") and ai_state["rebalancing_plan"].get("recommendations"):
        reb = ai_state["rebalancing_plan"]
        md.append(f"## 7. Deposit-Only Rebalancing Guideline (Based on Rp {reb['deposit_amount_idr']:,.0f} DCA)")
        md.append("| Asset Class | Current Weight | Target Weight | Drift | Suggested Allocation | Action |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for r in reb["recommendations"]:
            drift_s = f"{r['drift_pct']:+0.1f}%"
            md.append(f"| **{r['asset_class']}** | {r['current_weight_pct']:.1f}% | {r['target_weight_pct']:.1f}% | `{drift_s}` | **Rp {r['deposit_allocation_idr']:,.0f}** ({r['allocation_pct_of_deposit']}%) | {r['suggested_action']} |")
        md.append("")

    if ai_state.get("history_trajectory"):
        md.append("## 8. Historical Trajectory (Recent Snapshots)")
        md.append("| Date | Net Worth (IDR) | Fixed Income % | Equities % | Crypto % | Cash % |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for t in ai_state["history_trajectory"]:
            md.append(f"| {t['date']} | Rp {t['net_worth_idr']:,.0f} | {t['fixed_income_pct']:.1f}% | {t['equities_pct']:.1f}% | {t['crypto_pct']:.1f}% | {t['cash_pct']:.1f}% |")
        md.append("")

    if ai_state.get("cashflow_and_runway"):
        cf = ai_state["cashflow_and_runway"]
        md.append("## 9. Sans Finance Cashflow & Financial Runway")
        md.append(f"- **Consolidated True Net Worth**: **Rp {cf['consolidated_net_worth_idr']:,.0f}** (${cf['consolidated_net_worth_usd']:,.2f}) *(Investments + Live Bank Cash)*")
        md.append(f"- **Live Bank/E-Wallet Cash**: Rp {cf['live_bank_cash_idr']:,.0f}")
        md.append(f"- **Average Monthly Income**: Rp {cf['monthly_income_idr']:,.0f}")
        md.append(f"- **Average Monthly Burn (Expenses)**: Rp {cf['monthly_burn_idr']:,.0f}")
        md.append(f"- **Monthly Net Savings**: Rp {cf['monthly_savings_idr']:,.0f} (Savings Rate: **{cf['savings_rate_pct']}%**)")
        md.append(f"- **Emergency Runway**: **{cf['runway_months']} Months** ({cf['runway_health']})")
        if cf.get("top_categories"):
            md.append("\n**Top Spending Categories:**")
            for cat in cf["top_categories"][:5]:
                md.append(f"  • {cat['category']}: Rp {cat['amount_idr']:,.0f} ({cat['pct']}%)")
        md.append("")

    md.append("---")
    md.append("💡 *Ready for ingestion by Hermes Agent, Claude, or any LLM financial strategist.*")

    return "\n".join(md)


def build_and_save_ai_state(snapshot_path: Path, output_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Loads snapshot, computes AI state, and writes out both JSON and Markdown digests."""
    data_dir = get_data_dir()
    if output_dir is None:
        output_dir = data_dir

    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot file not found: {snapshot_path}")

    with open(snapshot_path, "r", encoding="utf-8") as f:
        current_snapshot = json.load(f)

    all_snapshots = load_historical_snapshots(data_dir)
    ai_state = generate_ai_state(current_snapshot, all_snapshots)
    digest_md = generate_ai_digest_markdown(ai_state)

    date = ai_state["state_date"]
    
    # Save dated and 'latest' files
    dated_json_path = output_dir / f"{date}_ai_state.json"
    latest_json_path = output_dir / "latest_ai_state.json"
    
    dated_md_path = output_dir / f"{date}_ai_digest.md"
    latest_md_path = output_dir / "latest_ai_digest.md"

    with open(dated_json_path, "w", encoding="utf-8") as f:
        json.dump(ai_state, f, indent=2)
    with open(latest_json_path, "w", encoding="utf-8") as f:
        json.dump(ai_state, f, indent=2)

    with open(dated_md_path, "w", encoding="utf-8") as f:
        f.write(digest_md)
    with open(latest_md_path, "w", encoding="utf-8") as f:
        f.write(digest_md)

    print(f"🤖 AI Financial State generated:")
    print(f"   • JSON: {dated_json_path.name} & {latest_json_path.name}")
    print(f"   • Digest: {dated_md_path.name} & {latest_md_path.name}")

    return ai_state


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate AI Financial State and Digest")
    parser.add_argument("--date", help="Date in YYYY-MM-DD format (defaults to latest available)")
    args = parser.parse_args()

    data_dir = get_data_dir()
    if args.date:
        target_file = data_dir / f"{args.date}_snapshot.json"
    else:
        snapshots = sorted([f for f in data_dir.glob("*_snapshot.json") if not f.name.startswith("latest")])
        if not snapshots:
            print("❌ No snapshots found in data directory.")
            exit(1)
        target_file = snapshots[-1]

    build_and_save_ai_state(target_file)


if __name__ == "__main__":
    main()
