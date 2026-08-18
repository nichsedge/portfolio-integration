"""
Executive 360° Financial Terminal Dashboard
Renders a live, visual Bloomberg-style intelligence dashboard in the terminal using Rich.
"""

import os
import sys
import pendulum
from pathlib import Path
from typing import Dict, Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.text import Text
from rich import box

from portfolio_app.mcp_server import (
    tool_get_portfolio_overview,
    tool_get_holdings_breakdown,
    tool_get_unified_financial_state,
    tool_get_passive_income_projection,
    tool_get_fire_simulation,
)
from portfolio_app.scenario_stress_tester import run_stress_test


def render_dashboard():
    console = Console()
    unified = tool_get_unified_financial_state()
    if "error" in unified:
        console.print(f"[red]Error loading unified state: {unified['error']}[/red]")
        return

    portfolio = unified["portfolio"]
    summary = unified.get("unified_summary", {})
    macro = portfolio["macro_metrics"]
    fx = portfolio.get("exchange_rate_usd_idr", 17831.0)
    date = portfolio["date"]

    passive = tool_get_passive_income_projection().get("passive_income_projection", {})
    fire = tool_get_fire_simulation().get("fire_simulation", {})
    holdings = tool_get_holdings_breakdown()
    stress = run_stress_test(
        holdings=holdings,
        exchange_rate=fx,
        live_bank_cash_idr=summary.get("live_bank_cash_idr", 0.0),
        monthly_burn_idr=summary.get("avg_monthly_burn_idr", 4000000.0)
    )

    console.clear()

    # 1. Main Header Banner
    nw_idr = summary.get("consolidated_net_worth_idr", macro["net_worth_idr"])
    nw_usd = summary.get("consolidated_net_worth_usd", macro["net_worth_usd"])

    header_text = Text()
    header_text.append("🏛️  SANS FINANCE & PORTFOLIO INTELLIGENCE — EXECUTIVE DASHBOARD\n", style="bold cyan")
    header_text.append(f"Snapshot Date: {date}  |  Exchange Rate: 1 USD = Rp {fx:,.2f}  |  Status: LIVE / VERIFIED", style="dim")

    console.print(Panel(header_text, box=box.HEAVY, style="cyan"))

    # 2. Key Metrics Bar (3 Cards)
    macro_table = Table.grid(expand=True, padding=(0, 2))
    macro_table.add_column(justify="left", ratio=1)
    macro_table.add_column(justify="left", ratio=1)
    macro_table.add_column(justify="left", ratio=1)

    # Card 1: True Net Worth
    c1 = Panel(
        f"[bold green]Rp {nw_idr:,.0f}[/]\n"
        f"[bold cyan]${nw_usd:,.2f}[/]\n"
        f"[dim]Investments: Rp {macro['net_worth_idr']:,.0f}\n"
        f"Bank Cash: Rp {summary.get('live_bank_cash_idr', 0.0):,.0f}[/]",
        title="[bold]💰 CONSOLIDATED TRUE NET WORTH[/]",
        border_style="green",
        box=box.ROUNDED
    )

    # Card 2: Cashflow & Emergency Runway
    runway_health = summary.get("runway_health", "Strong")
    health_color = "green" if runway_health == "Fortress" else "yellow" if runway_health == "Strong" else "red"
    c2 = Panel(
        f"[{health_color} bold]{summary.get('runway_months', 0.0)} Months[/] [dim]({runway_health})[/]\n"
        f"Monthly Burn: [red]Rp {summary.get('avg_monthly_burn_idr', 0.0):,.0f}[/]\n"
        f"Monthly Income: [green]Rp {summary.get('avg_monthly_income_idr', 0.0):,.0f}[/]\n"
        f"Savings Rate: [bold cyan]{summary.get('savings_rate_pct', 0.0)}%[/]",
        title="[bold]🛡️ EMERGENCY RUNWAY & BURN[/]",
        border_style=health_color,
        box=box.ROUNDED
    )

    # Card 3: FIRE & Passive Yield
    c3 = Panel(
        f"[bold yellow]Progress: {fire.get('current_progress_pct', 0.0)}%[/] [dim]({fire.get('projected_timeline', {}).get('estimated_fire_date', 'N/A')})[/]\n"
        f"Passive Cashflow: [green]Rp {passive.get('projected_monthly_passive_income_idr', 0.0):,.0f}/mo[/]\n"
        f"FI Burn Coverage: [bold]{passive.get('fi_coverage_pct', 0.0)}%[/]\n"
        f"Coast FIRE: [{'green' if fire.get('is_coast_fire_achieved') else 'red'} bold]{'ACHIEVED ✓' if fire.get('is_coast_fire_achieved') else 'PENDING'}[/]",
        title="[bold]🔥 FIRE & PASSIVE CASHFLOW[/]",
        border_style="yellow",
        box=box.ROUNDED
    )

    macro_table.add_row(c1, c2, c3)
    console.print(macro_table)
    console.print("")

    # 3. Asset Allocation & Macro Stress Test Tables Side-by-Side
    split_table = Table.grid(expand=True, padding=(0, 2))
    split_table.add_column(ratio=1)
    split_table.add_column(ratio=1)

    # Left: Asset Class Allocation
    alloc_table = Table(title="📊 Asset Allocation & Target Drift", box=box.SIMPLE_HEAVY)
    alloc_table.add_column("Asset Class", style="bold")
    alloc_table.add_column("Value (IDR)", justify="right", style="green")
    alloc_table.add_column("Weight", justify="right")
    alloc_table.add_column("Target", justify="right", style="dim")
    alloc_table.add_column("Drift", justify="right")

    for item in portfolio.get("asset_allocation", []):
        drift = item["drift_pct"]
        drift_str = f"[{'green' if drift >= 0 else 'red'}]{drift:+0.1f}%[/]" if drift != 0 else "[dim]0.0%[/]"
        alloc_table.add_row(
            item["asset_class"],
            f"Rp {item['value_idr']:,.0f}",
            f"{item['weight_pct']:.1f}%",
            f"{item['target_pct']:.1f}%",
            drift_str
        )

    # Right: Stress Test Scenarios
    stress_table = Table(title=f"⚡ Macro Stress Test ([bold]{stress['resilience_grade']}[/])", box=box.SIMPLE_HEAVY)
    stress_table.add_column("Scenario", style="bold")
    stress_table.add_column("Drawdown", justify="right", style="red")
    stress_table.add_column("Post-Crash NW", justify="right", style="green")
    stress_table.add_column("Runway", justify="right")

    for sc in stress.get("scenarios", []):
        stress_table.add_row(
            sc["scenario_name"][:28],
            f"-{sc['drawdown_pct']:.1f}%",
            f"Rp {sc['post_shock_net_worth_idr']:,.0f}",
            f"{sc['liquid_runway_months']:.1f} mo"
        )

    split_table.add_row(alloc_table, stress_table)
    console.print(split_table)
    console.print("")

    # 4. Top Holdings Table
    holdings_table = Table(title="💎 Top Portfolio Holdings", box=box.ROUNDED, expand=True)
    holdings_table.add_column("Asset", style="bold cyan")
    holdings_table.add_column("Category", style="yellow")
    holdings_table.add_column("Asset Class")
    holdings_table.add_column("Platform", style="dim")
    holdings_table.add_column("Value (IDR)", justify="right", style="green")
    holdings_table.add_column("Weight (%)", justify="right", style="bold")

    for h in holdings[:8]:
        holdings_table.add_row(
            h["asset"][:38],
            h["category"],
            h["asset_class"],
            h["source"],
            f"Rp {h['value_idr']:,.0f}",
            f"{(h['value_idr'] / macro['net_worth_idr'] * 100):.1f}%"
        )

    console.print(holdings_table)
    console.print("")
    console.print(f"[dim]💡 Run [bold cyan]uv run portfolio-mcp --help[/bold cyan] for stdio MCP server, automated audit, rebalancing, and tax tools.[/dim]\n")


def main():
    render_dashboard()


if __name__ == "__main__":
    main()
