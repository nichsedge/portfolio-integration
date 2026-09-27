"""Quantitative screener and ranking engine for Indonesian Mutual Funds."""

import re
from typing import ClassVar

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models import FundProduct


def parse_aum_string(val: str | None) -> float:
    """Parse strings like '500m', '1t', '100b', '50miliar' into raw numbers."""
    if not val:
        return 0.0
    val = val.lower().strip()
    multiplier = 1.0
    if val.endswith("t") or "triliun" in val:
        multiplier = 1e12
        val = re.sub(r"[^\d.]", "", val)
    elif val.endswith("b") or "miliar" in val or "m" in val:
        multiplier = 1e9
        val = re.sub(r"[^\d.]", "", val)
    elif val.endswith("k") or "ribu" in val:
        multiplier = 1e3
        val = re.sub(r"[^\d.]", "", val)
    else:
        val = re.sub(r"[^\d.]", "", val)
    try:
        return float(val) * multiplier
    except ValueError:
        return 0.0


def format_idr_compact(amount: float) -> str:
    """Format large IDR amounts as Rp X.XX T, Rp X.XX M, etc."""
    if amount >= 1e12:
        return f"Rp {amount / 1e12:,.2f} T"
    if amount >= 1e9:
        return f"Rp {amount / 1e9:,.2f} M"
    if amount >= 1e6:
        return f"Rp {amount / 1e6:,.2f} Jt"
    return f"Rp {amount:,.0f}"


class MutualFundScreener:
    """Screens, filters, and ranks mutual funds for optimal capital allocation."""

    TYPE_ALIASES: ClassVar[dict[str, str]] = {
        "pu": "Pasar Uang",
        "pasar_uang": "Pasar Uang",
        "money_market": "Pasar Uang",
        "ob": "Obligasi",
        "obligasi": "Obligasi",
        "fixed_income": "Obligasi",
        "sh": "Saham",
        "saham": "Saham",
        "equity": "Saham",
        "cp": "Campuran",
        "campuran": "Campuran",
        "balanced": "Campuran",
        "global": "Reksadana Global",
    }

    def __init__(self, funds: list[FundProduct], console: Console | None = None):
        self.funds = funds
        self.console = console or Console(width=max(Console().width or 120, 120))

    def filter_and_rank(
        self,
        fund_type: str | None = None,
        sharia_only: bool = False,
        min_aum: float = 0.0,
        max_drawdown_abs: float | None = None,
        query: str | None = None,
        sort_by: str = "cagr_1y",
        limit: int = 15,
    ) -> list[FundProduct]:
        """Apply filters and sorting criteria to the mutual fund universe."""
        filtered = self.funds

        # 1. Fund Type filter
        if fund_type and fund_type.lower() != "all":
            norm_type = self.TYPE_ALIASES.get(fund_type.lower(), fund_type)
            filtered = [f for f in filtered if norm_type.lower() in f.type.lower()]

        # 2. Sharia filter
        if sharia_only:
            filtered = [f for f in filtered if f.sharia]

        # 3. Min AUM filter
        if min_aum > 0:
            filtered = [f for f in filtered if f.aum_idr >= min_aum]

        # 4. Max Drawdown filter
        if max_drawdown_abs is not None:
            # max_drawdown_abs e.g. 1.0 means max 1.0% drop
            filtered = [
                f
                for f in filtered
                if abs(f.drawdown_1y_pct) <= abs(max_drawdown_abs)
            ]

        # 5. Search query (name, symbol, investment manager)
        if query:
            q = query.lower().strip()
            filtered = [
                f
                for f in filtered
                if q in f.name.lower()
                or q in f.symbol.lower()
                or q in f.investment_manager.name.lower()
            ]

        # 6. Sorting
        def get_sort_key(f: FundProduct) -> float:
            if sort_by == "cagr_1y":
                return f.cagr_1y_pct
            if sort_by == "cagr_3y":
                return f.cagr_3y_pct
            if sort_by == "cagr_5y":
                return f.cagr_5y_pct
            if sort_by == "drawdown":
                return -abs(f.drawdown_1y_pct)  # higher is closer to 0 (lowest loss)
            if sort_by == "expense_ratio":
                return -(f.expense_ratio_pct if f.expense_ratio_pct > 0 else 999.0)  # lowest fee first
            if sort_by == "aum":
                return f.aum_idr
            if sort_by == "calmar":
                return f.calmar_ratio_1y
            return f.cagr_1y_pct

        ranked = sorted(filtered, key=get_sort_key, reverse=True)
        return ranked[:limit]

    def render_table(
        self,
        funds: list[FundProduct],
        title: str = "Indonesian Mutual Fund Screener",
    ) -> None:
        """Render a clean, colorful Rich table of ranked mutual funds."""
        if not funds:
            self.console.print("[yellow]No mutual funds match the specified criteria.[/yellow]")
            return

        is_wide = self.console.width >= 105

        table = Table(title=title, show_header=True, header_style="bold cyan")
        table.add_column("#", justify="right", style="dim", width=2)
        table.add_column("Fund Name", style="bold white", min_width=18)
        table.add_column("Type", style="cyan", width=10)
        table.add_column("1Y CAGR", justify="right", width=8)
        if is_wide:
            table.add_column("3Y CAGR", justify="right", width=8)
        table.add_column("1Y MDD", justify="right", width=7)
        table.add_column("Exp.", justify="right", width=6)
        table.add_column("AUM", justify="right", width=10)
        if is_wide:
            table.add_column("Manager (MI)", style="dim", min_width=14)

        for idx, f in enumerate(funds, start=1):
            sharia_badge = " [green][S][/green]" if f.sharia else ""
            name_display = f"{f.name}{sharia_badge}"

            c1y = f.cagr_1y_pct
            c1y_str = (
                f"[green]+{c1y:.2f}%[/green]"
                if c1y > 0
                else f"[red]{c1y:.2f}%[/red]"
                if c1y < 0
                else "0.00%"
            )
            c3y = f.cagr_3y_pct
            c3y_str = (
                f"[green]+{c3y:.2f}%[/green]"
                if c3y > 0
                else f"[red]{c3y:.2f}%[/red]"
                if f.cagr.cagr_3y is not None
                else "[dim]-[/dim]"
            )
            mdd = f.drawdown_1y_pct
            mdd_str = f"[red]{mdd:.2f}%[/red]" if mdd < 0 else "0.00%"
            er = f.expense_ratio_pct
            er_str = f"{er:.2f}%" if er > 0 else "[dim]-[/dim]"
            aum_str = format_idr_compact(f.aum_idr)
            manager = f.investment_manager.name.replace("PT ", "")

            row = [
                str(idx),
                name_display,
                f.type,
                c1y_str,
            ]
            if is_wide:
                row.append(c3y_str)
            row.extend([mdd_str, er_str, aum_str])
            if is_wide:
                row.append(manager)

            table.add_row(*row)

        self.console.print(table)

    def render_detail(self, fund: FundProduct) -> None:
        """Render comprehensive deep-dive card for a single mutual fund."""
        c = self.console
        sharia_label = "[green]Yes (Sharia)[/green]" if fund.sharia else "[dim]No (Conventional)[/dim]"
        aum_str = format_idr_compact(fund.aum_idr)
        nav_val = f"Rp {fund.nav.value:,.2f}" if fund.nav.value else "-"

        info_text = (
            f"[bold cyan]Symbol:[/bold cyan] {fund.symbol}  |  "
            f"[bold cyan]Type:[/bold cyan] {fund.type}  |  "
            f"[bold cyan]Sharia:[/bold cyan] {sharia_label}\n"
            f"[bold cyan]Investment Manager:[/bold cyan] {fund.investment_manager.name} "
            f"([dim]{fund.investment_manager.ojkCode or 'N/A'}[/dim])\n"
            f"[bold cyan]Custodian Bank:[/bold cyan] {fund.custodian_bank.name}\n"
            f"[bold cyan]Current NAV:[/bold cyan] {nav_val} ([dim]{fund.nav.date or '-'}[/dim])  |  "
            f"[bold cyan]AUM:[/bold cyan] {aum_str}\n"
            f"[bold cyan]Expense Ratio:[/bold cyan] {fund.expense_ratio_pct:.2f}%  |  "
            f"[bold cyan]Risk Profile:[/bold cyan] {fund.riskprofile or 'N/A'}\n"
            f"[bold cyan]Min. Buy:[/bold cyan] Rp {fund.minbuy:,.0f}" if fund.minbuy else ""
        )

        c.print(Panel(info_text, title=f"[bold green]{fund.name}[/bold green]", expand=False))

        # Performance Table
        perf_table = Table(title="Historical Compound Annual Growth Rate (CAGR) & Drawdown", show_header=True)
        perf_table.add_column("Period", style="bold")
        perf_table.add_column("CAGR", justify="right")
        perf_table.add_column("Simple Return", justify="right")
        perf_table.add_column("Max Drawdown", justify="right")

        periods = [
            ("1-Day", None, fund.simplereturn.return_1d, None),
            ("1-Month", None, fund.simplereturn.return_1m, None),
            ("3-Month", None, fund.simplereturn.return_3m, None),
            ("YTD", None, fund.simplereturn.return_ytd, None),
            ("1-Year", fund.cagr.cagr_1y, fund.simplereturn.return_1y, fund.maxdrawdown.mdd_1y),
            ("3-Year", fund.cagr.cagr_3y, fund.simplereturn.return_3y, fund.maxdrawdown.mdd_3y),
            ("5-Year", fund.cagr.cagr_5y, fund.simplereturn.return_5y, fund.maxdrawdown.mdd_5y),
            ("All-Time", fund.cagr.all, fund.simplereturn.all if hasattr(fund.simplereturn, 'all') else None, fund.maxdrawdown.all),
        ]

        for p_name, cagr_val, ret_val, mdd_val in periods:
            cagr_s = f"{cagr_val * 100:+.2f}%" if cagr_val is not None else "[dim]-[/dim]"
            ret_s = f"{ret_val * 100:+.2f}%" if ret_val is not None else "[dim]-[/dim]"
            mdd_s = f"{mdd_val * 100:.2f}%" if mdd_val is not None else "[dim]-[/dim]"
            perf_table.add_row(p_name, cagr_s, ret_s, mdd_s)

        c.print(perf_table)

        # Asset Allocation Breakdown
        if fund.asset:
            alloc_table = Table(title="Asset Class Allocation", show_header=True)
            alloc_table.add_column("Asset Class", style="bold white")
            alloc_table.add_column("Percentage", justify="right", style="cyan")
            for a in fund.asset:
                alloc_table.add_row(a.name, f"{a.percentage:.2f}%")
            c.print(alloc_table)

        # Top 10 Underlying Holdings
        if fund.holding:
            hold_table = Table(title="Top Underlying Securities / Portfolio Holdings", show_header=True)
            hold_table.add_column("#", justify="right", style="dim", width=3)
            hold_table.add_column("Security / Holding Name", style="bold white")
            hold_table.add_column("Symbol / Ticker", style="cyan")
            hold_table.add_column("Type", style="dim")
            hold_table.add_column("Reported Date", style="dim")
            for idx, h in enumerate(fund.holding, start=1):
                hold_table.add_row(
                    str(idx),
                    h.name,
                    h.symbol or "-",
                    h.product_type or "-",
                    h.date or "-",
                )
            c.print(hold_table)
