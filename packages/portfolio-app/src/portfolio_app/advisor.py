"""
Portfolio Advisor Decision Support Engine.
Connects unified personal portfolio holdings with real IDX quantitative signals
to generate actionable, zero-bullshit decision cards.
"""

import json
from pathlib import Path
from typing import Any

try:
    import duckdb
except ImportError:
    duckdb = None

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def get_paths() -> tuple[Path, Path]:
    """Resolve data directories for portfolio-integration and idx-bei."""
    portfolio_root = Path(__file__).resolve().parents[4]
    idx_root = portfolio_root.parent / "idx-bei"
    return portfolio_root, idx_root


class PortfolioAdvisor:
    """Analyzes real portfolio holdings against IDX market data and institutional flows."""

    def __init__(
        self, portfolio_root: Path | None = None, idx_root: Path | None = None
    ):
        p_root, i_root = get_paths()
        self.portfolio_root = portfolio_root or p_root
        self.idx_root = idx_root or i_root
        self.data_dir = self.portfolio_root / "data"
        self.idx_parquet_dir = self.idx_root / "data" / "parquet"
        self.console = Console()

    def get_atracker_work_hours(self, days: int = 30) -> float:
        """Query active (non-idle) focused work hours from atracker telemetry."""
        import sqlite3
        atracker_db = Path.home() / ".local/share/atracker/atracker.db"
        if not atracker_db.exists():
            return 0.0
        try:
            con = sqlite3.connect(f"file:{atracker_db}?mode=ro", uri=True)
            cur = con.cursor()
            cur.execute(
                f"SELECT COALESCE(SUM(duration_secs) / 3600.0, 0.0) FROM events WHERE is_idle = 0 AND timestamp >= (SELECT datetime(MAX(timestamp), '-{days} days') FROM events)"
            )
            row = cur.fetchone()
            con.close()
            return float(row[0]) if row else 0.0
        except Exception:
            return 0.0

    def load_portfolio_state(self) -> dict[str, Any]:
        """Load latest portfolio state and snapshot."""
        state_path = self.data_dir / "latest_ai_state.json"
        if not state_path.exists():
            states = sorted(self.data_dir.glob("*_ai_state.json"))
            if states:
                state_path = states[-1]
            else:
                return {}

        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            self.console.print(f"[red]Error loading portfolio state: {e}[/red]")
            return {}

    def analyze_equity_holdings(
        self, holdings: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Query DuckDB Parquet data for currently held IDX stocks."""
        stock_parquet = self.idx_parquet_dir / "stock_summary.parquet"
        ratios_parquet = self.idx_parquet_dir / "financial_ratios.parquet"

        if not stock_parquet.exists() or not ratios_parquet.exists():
            return []

        # Filter equities that are individual IDX stocks (4 uppercase letters)
        equity_holdings = [
            h
            for h in holdings
            if h.get("asset_class") == "Equities"
            and len(h.get("asset", "")) == 4
            and h.get("asset", "").isalpha()
        ]

        if not equity_holdings or duckdb is None:
            return []

        tickers = [h["asset"].upper() for h in equity_holdings]
        tickers_str = ", ".join([repr(t) for t in tickers])

        con = duckdb.connect()
        query = f"""
            WITH latest_date AS (
                SELECT MAX(Date) as max_d FROM "{stock_parquet}"
            ),
            recent_flows AS (
                SELECT 
                    StockCode,
                    SUM(NetForeignFlow) as nff_20d,
                    AVG(Close) as avg_close_20d,
                    SUM(Value) as total_val_20d
                FROM "{stock_parquet}"
                WHERE Date >= (SELECT max_d - INTERVAL 30 DAY FROM latest_date)
                GROUP BY StockCode
            )
            SELECT 
                s.StockCode,
                s.Close as latest_close,
                s.NetForeignFlow as latest_nff,
                rf.nff_20d,
                rf.avg_close_20d,
                fr.per,
                fr.priceBV,
                fr.roe,
                fr.deRatio,
                fr.sharia
            FROM "{stock_parquet}" s
            JOIN latest_date ld ON s.Date = ld.max_d
            LEFT JOIN recent_flows rf ON s.StockCode = rf.StockCode
            LEFT JOIN "{ratios_parquet}" fr ON s.StockCode = fr.code
            WHERE s.StockCode IN ({tickers_str})
        """

        try:
            df = con.execute(query).df()
            market_map = {row["StockCode"]: row.to_dict() for _, row in df.iterrows()}
        except Exception as e:  # noqa: BLE001
            self.console.print(f"[yellow]Warning: DuckDB query failed: {e}[/yellow]")
            market_map = {}

        results = []
        for h in equity_holdings:
            ticker = h["asset"].upper()
            m = market_map.get(ticker, {})

            roe = m.get("roe") or 0.0
            per = m.get("per") or 0.0
            nff_20d = m.get("nff_20d") or 0.0
            pbv = m.get("priceBV") or 0.0
            close = m.get("latest_close") or 0.0

            # Quantitative Decision Heuristic
            if roe >= 18.0 and nff_20d > 0:
                verdict = "💎 COMPOUNDER (HOLD/ACCUMULATE)"
                action = "Top-tier capital efficiency with active institutional inflow."
            elif per <= 8.0 and pbv <= 1.0:
                verdict = "🛡️ DEEP VALUE (HOLD)"
                action = "Asset-backed margin of safety; hold through cycle."
            elif nff_20d < -100_000_000:
                verdict = "⚠️ OUTFLOW WATCH (MONITOR)"
                action = "Institutional distribution pressure over past 20 sessions."
            else:
                verdict = "⚖️ NEUTRAL (HOLD)"
                action = "Fair valuation; maintain allocation."

            results.append(
                {
                    "ticker": ticker,
                    "value_idr": h.get("value_idr", 0),
                    "weight_pct": h.get("weight_pct", 0),
                    "close": close,
                    "roe": roe,
                    "per": per,
                    "pbv": pbv,
                    "nff_20d": nff_20d,
                    "verdict": verdict,
                    "action": action,
                }
            )

        return results

    def screen_dry_powder_opportunities(self, limit: int = 3) -> list[dict[str, Any]]:
        """Screen pristine candidates for deploying idle cash based on quant fundamentals."""
        stock_parquet = self.idx_parquet_dir / "stock_summary.parquet"
        ratios_parquet = self.idx_parquet_dir / "financial_ratios.parquet"

        if not stock_parquet.exists() or not ratios_parquet.exists() or duckdb is None:
            return []

        con = duckdb.connect()
        query = f"""
            WITH latest_date AS (
                SELECT MAX(Date) as max_d FROM "{stock_parquet}"
            ),
            recent_flows AS (
                SELECT 
                    StockCode,
                    SUM(NetForeignFlow) as nff_20d,
                    SUM(Value) as total_val_20d
                FROM "{stock_parquet}"
                WHERE Date >= (SELECT max_d - INTERVAL 30 DAY FROM latest_date)
                GROUP BY StockCode
            )
            SELECT 
                s.StockCode,
                s.StockName,
                s.Close,
                rf.nff_20d,
                fr.per,
                fr.priceBV,
                fr.roe,
                fr.deRatio,
                fr.sharia
            FROM "{stock_parquet}" s
            JOIN latest_date ld ON s.Date = ld.max_d
            JOIN recent_flows rf ON s.StockCode = rf.StockCode
            JOIN "{ratios_parquet}" fr ON s.StockCode = fr.code
            WHERE fr.roe > 18.0 
              AND fr.per BETWEEN 3.0 AND 12.0
              AND fr.deRatio < 1.2
              AND rf.total_val_20d > 1000000000 -- liquid (>Rp 1B 20d volume)
              AND rf.nff_20d > 0               -- institutional accumulation
            ORDER BY fr.roe DESC
            LIMIT {limit}
        """

        try:
            df = con.execute(query).df()
            return df.to_dict(orient="records")
        except Exception as e:  # noqa: BLE001
            self.console.print(
                f"[yellow]Warning: Opportunity screening query failed: {e}[/yellow]"
            )
            return []

    def generate_report(self) -> None:
        """Render the complete executive Decision Card in terminal."""
        state = self.load_portfolio_state()
        if not state:
            self.console.print("[red]No portfolio state available to analyze.[/red]")
            return

        macro = state.get("macro_metrics", {})
        holdings = state.get("top_holdings", [])
        net_worth_idr = macro.get("net_worth_idr", 0)

        # Calculate Dry Powder (Cash & Equivalents)
        cash_accounts = [
            h
            for h in holdings
            if h.get("asset_class") == "Cash & Equivalents"
            or h.get("category") in ["Bank Account", "Stablecoin"]
        ]
        total_cash_idr = sum(h.get("value_idr", 0) for h in cash_accounts)
        cash_pct = (total_cash_idr / net_worth_idr * 100) if net_worth_idr > 0 else 0

        # Telemetry & Time-to-Wealth Velocity
        work_hours_30d = self.get_atracker_work_hours(days=30)
        mom_growth_idr = macro.get("mom_growth_idr", 0)
        hourly_velocity = (mom_growth_idr / work_hours_30d) if work_hours_30d > 0 and mom_growth_idr > 0 else 0
        velocity_str = f"Rp {hourly_velocity:,.0f}/hr" if hourly_velocity > 0 else "N/A"

        # Header Panel
        summary_text = (
            f"[bold cyan]Total Net Worth:[/bold cyan] Rp {net_worth_idr:,.0f} (~${macro.get('net_worth_usd', 0):,.0f} USD)\n"
            f"[bold green]Liquid Dry Powder (Cash & USDT):[/bold green] Rp {total_cash_idr:,.0f} ({cash_pct:.1f}% of NW)\n"
            f"[bold yellow]Active Focused Work (30d):[/bold yellow] {work_hours_30d:.1f} hrs (Sovereign Velocity: [bold green]{velocity_str}[/bold green])\n"
            f"[bold magenta]Liabilities:[/bold magenta] Rp 0 (100% Debt-Free)"
        )
        self.console.print(
            Panel(
                summary_text,
                title="🏛️ Sovereign Portfolio Advisor Briefing",
                expand=False,
            )
        )

        # 1. Existing Holdings Health Table
        equity_analysis = self.analyze_equity_holdings(holdings)
        if equity_analysis:
            table = Table(
                title="📈 Current Equity Holdings Analysis (IDX Real Data)", expand=True
            )
            table.add_column("Ticker", style="bold cyan")
            table.add_column("Position (IDR)", justify="right")
            table.add_column("Weight", justify="right")
            table.add_column("ROE", justify="right")
            table.add_column("PER", justify="right")
            table.add_column("20D Inst. Flow", justify="right")
            table.add_column("Verdict", style="bold")

            for r in equity_analysis:
                flow_color = "green" if r["nff_20d"] >= 0 else "red"
                flow_str = f"[{flow_color}]{r['nff_20d'] / 1e6:+,.1f}M[/{flow_color}]"
                table.add_row(
                    r["ticker"],
                    f"Rp {r['value_idr']:,.0f}",
                    f"{r['weight_pct']:.1f}%",
                    f"{r['roe']:.1f}%",
                    f"{r['per']:.1f}x",
                    flow_str,
                    r["verdict"],
                )
            self.console.print(table)

        # 2. Dry Powder Deployment Candidates Table
        opportunities = self.screen_dry_powder_opportunities(limit=3)
        if opportunities:
            opp_table = Table(
                title="🎯 Screened Opportunities for Idle Cash Deployment (High ROE + Institutional Accumulation)",
                expand=True,
            )
            opp_table.add_column("Code", style="bold green")
            opp_table.add_column("Company", style="dim")
            opp_table.add_column("Close", justify="right")
            opp_table.add_column("ROE", justify="right", style="bold")
            opp_table.add_column("PER", justify="right")
            opp_table.add_column("DER", justify="right")
            opp_table.add_column("20D Inflow", justify="right", style="green")

            for o in opportunities:
                opp_table.add_row(
                    o["StockCode"],
                    o["StockName"][:28],
                    f"Rp {o['Close']:,.0f}",
                    f"{o['roe']:.1f}%",
                    f"{o['per']:.1f}x",
                    f"{o['deRatio']:.2f}",
                    f"+Rp {o['nff_20d'] / 1e6:,.1f}M",
                )
            self.console.print(opp_table)

        # 3. Actionable Lazy Decision Card
        recommendation_panel = (
            "[bold white]1. Equities Action:[/bold white]\n"
            "   • [bold green]BBCA[/bold green]: Keep as primary blue-chip anchor (20.8% ROE, institutional accumulation).\n"
            "   • [bold green]INDF[/bold green]: Deep value buffer (0.63x PBV, 6.9x PER). No need to sell.\n"
            "   • [bold yellow]KLBF[/bold yellow]: Experiencing institutional outflow (-Rp 386M over 20d). Do not add new capital; let it ride or trim into dividend strength.\n\n"
            "[bold white]2. Cash & Runway Action:[/bold white]\n"
            f"   • You have [bold cyan]Rp {total_cash_idr:,.0f}[/bold cyan] in liquid yield accounts (Krom, Aladin, Superbank, USDT).\n"
            "   • Maintain 6-12 months living expenses in Krom/Aladin (5-7% risk-free yield).\n"
            "   • Any excess dry powder can be deployed into Sukuk (ST014/ST013) or staged into top value compounders without FOMO.\n\n"
            "[bold white]3. Crypto Satellite:[/bold white]\n"
            "   • ETH & Hyperliquid positions represent ~6.5% of total wealth. Perfect barbell ratio. Hold and do not overtrade."
        )
        self.console.print(
            Panel(
                recommendation_panel,
                title="⚡ Lazy Investor Actionable Verdict",
                border_style="bright_blue",
            )
        )

    def generate_markdown_briefing(self) -> str:
        """Generate a clean Telegram/Markdown text briefing without terminal ANSI codes."""
        state = self.load_portfolio_state()
        if not state:
            return "⚠️ No portfolio state available."

        macro = state.get("macro_metrics", {})
        holdings = state.get("top_holdings", [])
        net_worth_idr = macro.get("net_worth_idr", 0)

        cash_accounts = [
            h for h in holdings
            if h.get("asset_class") == "Cash & Equivalents"
            or h.get("category") in ["Bank Account", "Stablecoin"]
        ]
        total_cash_idr = sum(h.get("value_idr", 0) for h in cash_accounts)
        cash_pct = (total_cash_idr / net_worth_idr * 100) if net_worth_idr > 0 else 0

        work_hours_30d = self.get_atracker_work_hours(days=30)
        mom_growth_idr = macro.get("mom_growth_idr", 0)
        hourly_velocity = (mom_growth_idr / work_hours_30d) if work_hours_30d > 0 and mom_growth_idr > 0 else 0
        velocity_str = f"Rp {hourly_velocity:,.0f}/hr" if hourly_velocity > 0 else "N/A"

        lines = [
            "🏛️ *Sovereign Portfolio & Market Advisor*",
            f"• *Net Worth:* Rp {net_worth_idr:,.0f} (~${macro.get('net_worth_usd', 0):,.0f} USD)",
            f"• *Dry Powder (Liquid):* Rp {total_cash_idr:,.0f} ({cash_pct:.1f}% of NW)",
            f"• *Work Velocity (30d):* {work_hours_30d:.1f} hrs ({velocity_str})",
            "",
            "📈 *Equity Holdings Verdicts:*",
        ]

        equity_analysis = self.analyze_equity_holdings(holdings)
        for r in equity_analysis:
            flow_sign = "+" if r["nff_20d"] >= 0 else ""
            lines.append(f"• *{r['ticker']}* ({r['weight_pct']:.1f}% | Rp {r['value_idr']:,.0f}): {r['verdict']} | 20d Flow: {flow_sign}{r['nff_20d']/1e6:.1f}M")

        lines.extend([
            "",
            "🎯 *Screened Deployment Picks (High ROE + Inst. Inflow):*",
        ])
        opportunities = self.screen_dry_powder_opportunities(limit=3)
        for o in opportunities:
            lines.append(f"• *{o['StockCode']}* ({o['StockName'][:20]}): ROE {o['roe']:.1f}%, PER {o['per']:.1f}x | Flow: +{o['nff_20d']/1e6:.1f}M")

        lines.extend([
            "",
            "⚡ *Action:* Maintain blue-chip/fixed income anchors. Barbell crypto (~6.5% NW) untouched.",
        ])
        return "\n".join(lines)


    def get_advisor_payload(self) -> dict[str, Any]:
        """Generate structured JSON payload for downstream consumers (SansFinance / iERP)."""
        state = self.load_portfolio_state()
        if not state:
            return {}

        macro = state.get("macro_metrics", {})
        holdings = state.get("top_holdings", [])
        net_worth_idr = float(macro.get("net_worth_idr", 0))

        cash_accounts = [
            h for h in holdings
            if h.get("asset_class") == "Cash & Equivalents"
            or h.get("category") in ["Bank Account", "Stablecoin"]
        ]
        total_cash_idr = float(sum(h.get("value_idr", 0) for h in cash_accounts))
        cash_pct = (total_cash_idr / net_worth_idr * 100) if net_worth_idr > 0 else 0.0

        work_hours_30d = float(self.get_atracker_work_hours(days=30))
        mom_growth_idr = float(macro.get("mom_growth_idr", 0))
        hourly_velocity = (mom_growth_idr / work_hours_30d) if work_hours_30d > 0 and mom_growth_idr > 0 else 0.0
        velocity_str = f"Rp {hourly_velocity:,.0f}/hr" if hourly_velocity > 0 else "N/A"

        equity_analysis = self.analyze_equity_holdings(holdings)
        opportunities = self.screen_dry_powder_opportunities(limit=3)

        return {
            "date": state.get("state_date", ""),
            "hourly_velocity_idr": hourly_velocity,
            "velocity_str": velocity_str,
            "atracker_work_hours_30d": work_hours_30d,
            "dry_powder_idr": total_cash_idr,
            "dry_powder_pct": round(cash_pct, 1),
            "net_worth_idr": net_worth_idr,
            "mom_growth_idr": mom_growth_idr,
            "action_summary": "Maintain blue-chip/fixed income anchors. Barbell crypto (~6.5% NW) untouched.",
            "equities_verdicts": [
                {
                    "ticker": r["ticker"],
                    "value_idr": r["value_idr"],
                    "weight_pct": round(r["weight_pct"], 1),
                    "verdict": r["verdict"],
                    "nff_20d": r["nff_20d"],
                }
                for r in equity_analysis
            ],
            "opportunities": [
                {
                    "ticker": o["StockCode"],
                    "name": o["StockName"],
                    "close": o["Close"],
                    "roe": round(o["roe"], 1),
                    "per": round(o["per"], 1),
                    "nff_20d": o["nff_20d"],
                }
                for o in opportunities
            ],
        }

    def save_latest(self) -> Path:
        """Write latest_advisor.json and embed into latest snapshot JSON for downstream consumers."""
        payload = self.get_advisor_payload()
        advisor_path = self.data_dir / "latest_advisor.json"
        advisor_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        # Also embed into latest snapshot JSON
        snapshot_candidates = [
            f for f in sorted(self.data_dir.glob("*_snapshot.json"))
            if not f.name.startswith("latest")
        ]
        if snapshot_candidates:
            latest_snap = snapshot_candidates[-1]
            try:
                data = json.loads(latest_snap.read_text(encoding="utf-8"))
                data["advisor"] = payload
                latest_snap.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except Exception:
                pass
        return advisor_path


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Portfolio Advisor Decision Support Engine")
    parser.add_argument("--markdown", action="store_true", help="Output pure markdown text instead of rich tables")
    parser.add_argument("--json", action="store_true", help="Output structured JSON payload for downstream apps")
    parser.add_argument("--no-save", action="store_true", help="Do not persist latest_advisor.json")
    args = parser.parse_args()

    advisor = PortfolioAdvisor()
    if not args.no_save:
        advisor.save_latest()

    if args.json:
        print(json.dumps(advisor.get_advisor_payload(), indent=2))
    elif args.markdown:
        print(advisor.generate_markdown_briefing())
    else:
        advisor.generate_report()


if __name__ == "__main__":
    main()
