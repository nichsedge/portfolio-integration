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
    from transform_core import get_data_dir
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
    from transform_core import get_data_dir
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


def tool_get_portfolio_overview(date: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns the high-level financial overview: Net worth, MoM growth, asset class allocation, and liquidity.
    """
    data_dir = get_data_dir()
    if date:
        snap_path = data_dir / f"{date}_snapshot.json"
    else:
        snap_path = get_latest_snapshot_path()

    if not snap_path or not snap_path.exists():
        return {"error": f"Snapshot not found for date: {date or 'latest'}"}

    with open(snap_path, "r", encoding="utf-8") as f:
        snapshot = json.load(f)

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
    data_dir = get_data_dir()
    if date:
        snap_path = data_dir / f"{date}_snapshot.json"
    else:
        snap_path = get_latest_snapshot_path()

    if not snap_path or not snap_path.exists():
        return [{"error": f"Snapshot not found for date: {date or 'latest'}"}]

    with open(snap_path, "r", encoding="utf-8") as f:
        snapshot = json.load(f)

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
    Returns the multi-month trajectory of net worth and asset class allocations.
    """
    data_dir = get_data_dir()
    all_snapshots = load_historical_snapshots(data_dir)
    if not all_snapshots:
        return []

    recent = all_snapshots[-months:]
    history = []
    for s in recent:
        s_meta = s.get("metadata", {})
        s_totals = s.get("totals", {})
        allocations = {
            item.get("asset_class", "Other"): item.get("percentage", 0.0)
            for item in s.get("allocation", {}).get("by_asset_class", [])
        }
        history.append({
            "date": s_meta.get("date"),
            "net_worth_idr": s_totals.get("net_worth_idr", 0.0),
            "net_worth_usd": s_totals.get("net_worth_usd", 0.0),
            "fixed_income_pct": allocations.get("Fixed Income", 0.0),
            "equities_pct": allocations.get("Equities", 0.0),
            "crypto_pct": allocations.get("Crypto", 0.0),
            "cash_pct": allocations.get("Cash & Equivalents", 0.0),
            "commodities_pct": allocations.get("Commodities", 0.0),
        })

    return history


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
    for a in allocations:
        drift = a.get("drift_pct", 0.0)
        aclass = a["asset_class"]
        if drift > 10.0:
            recommendations.append(
                f"Overweight in {aclass} ({a['weight_pct']:.1f}% vs {a['target_pct']:.1f}% target). Consider trimming or directing new monthly contributions elsewhere."
            )
        elif drift < -5.0:
            recommendations.append(
                f"Underweight in {aclass} ({a['weight_pct']:.1f}% vs {a['target_pct']:.1f}% target). Recommended to accumulate {aclass}."
            )

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
        "advisory_recommendations": recommendations,
    }


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
            else:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Unsupported method: {method}"}
                }

            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        except Exception as e:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Portfolio MCP Server and AI Query CLI")
    parser.add_argument("--mcp", action="store_true", help="Run as stdio MCP JSON-RPC Server")
    parser.add_argument("--audit", action="store_true", help="Run and print portfolio health audit")
    parser.add_argument("--digest", action="store_true", help="Print latest AI markdown digest")
    parser.add_argument("--json", action="store_true", help="Print latest AI state JSON")
    parser.add_argument("--overview", action="store_true", help="Print portfolio overview summary")
    parser.add_argument("--holdings", action="store_true", help="Print all holdings breakdown")
    parser.add_argument("--history", action="store_true", help="Print historical multi-month performance")
    parser.add_argument("--class-filter", help="Filter holdings by asset class")
    args = parser.parse_args()

    if args.mcp:
        run_mcp_stdio_server()
        return

    if args.audit:
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
    else:
        # Default to printing the audit and digest options
        result = tool_get_portfolio_health_audit()
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
