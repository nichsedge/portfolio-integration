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
        "risk_and_alerts": {
            "crypto_exposure_pct": crypto_pct,
            "alerts": alerts,
        },
        "top_holdings": top_holdings_dense,
        "history_trajectory": history_trajectory
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

    md.append("## 3. Currency Exposure")
    curr = ai_state["currency_exposure"]
    md.append(f"- **IDR Assets**: {curr.get('idr_pct', 0)}% (Rp {curr.get('idr_val', 0):,.0f})")
    md.append(f"- **USD / Stablecoins**: {curr.get('usd_pct', 0)}% (Rp {curr.get('usd_val', 0):,.0f})")
    md.append(f"- **Native Crypto**: {curr.get('crypto_pct', 0)}% (Rp {curr.get('crypto_val', 0):,.0f})")
    md.append("")

    if ai_state["risk_and_alerts"]["alerts"]:
        md.append("## 4. Key Risk Alerts & Observations")
        for alert in ai_state["risk_and_alerts"]["alerts"]:
            md.append(f"- ⚠️ **{alert}**")
        md.append("")

    md.append("## 5. Top Portfolio Holdings")
    md.append("| Asset | Category | Asset Class | Platform | Value (IDR) | Weight (%) |")
    md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for h in ai_state["top_holdings"]:
        md.append(f"| {h['asset']} | {h['category']} | {h['asset_class']} | {h['source']} | Rp {h['value_idr']:,.0f} | {h['weight_pct']:.1f}% |")
    md.append("")

    if ai_state.get("history_trajectory"):
        md.append("## 6. Historical Trajectory (Recent Snapshots)")
        md.append("| Date | Net Worth (IDR) | Fixed Income % | Equities % | Crypto % | Cash % |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for t in ai_state["history_trajectory"]:
            md.append(f"| {t['date']} | Rp {t['net_worth_idr']:,.0f} | {t['fixed_income_pct']:.1f}% | {t['equities_pct']:.1f}% | {t['crypto_pct']:.1f}% | {t['cash_pct']:.1f}% |")
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


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate AI Financial State and Digest")
    parser.add_argument("--date", help="Date in YYYY-MM-DD format (defaults to latest available)")
    args = parser.parse_args()

    data_dir = get_data_dir()
    if args.date:
        target_file = data_dir / f"{args.date}_snapshot.json"
    else:
        snapshots = sorted(list(data_dir.glob("*_snapshot.json")))
        if not snapshots:
            print("❌ No snapshots found in data directory.")
            exit(1)
        target_file = snapshots[-1]

    build_and_save_ai_state(target_file)
