"""CLI entrypoints for reksadana-fetch and reksadana-screen."""

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .client import BibitReksadanaClient
from .screener import MutualFundScreener, parse_aum_string

try:
    from transform_core import get_data_dir
except ImportError:
    def get_data_dir() -> Path:
        return Path.cwd() / "data"


def fetch_main() -> None:
    """Entry point for `reksadana-fetch`."""
    console = Console()
    console.print("[bold cyan]Fetching Indonesian Reksa Dana Universe from Bibit API...[/bold cyan]")

    client = BibitReksadanaClient()
    try:
        products = client.fetch_all()
    except Exception as e:  # noqa: BLE001
        console.print(f"[bold red]Failed to fetch mutual fund data: {e}[/bold red]")
        sys.exit(1)

    data_dir = get_data_dir()
    dated_path, canonical_path = client.save_snapshot(products, data_dir)

    console.print(f"[green]Successfully fetched {len(products)} mutual funds![/green]")
    console.print(f"  - Dated Snapshot: [dim]{dated_path}[/dim]")
    console.print(f"  - Canonical SSOT: [dim]{canonical_path}[/dim]")

    # Breakdown table
    categories: dict[str, int] = {}
    for p in products:
        categories[p.type] = categories.get(p.type, 0) + 1

    table = Table(title="Catalog Breakdown", show_header=True)
    table.add_column("Asset Category", style="cyan")
    table.add_column("Fund Count", justify="right", style="bold white")
    for cat, count in sorted(categories.items()):
        table.add_row(cat, str(count))
    console.print(table)


def screen_main() -> None:
    """Entry point for `reksadana-screen`."""
    parser = argparse.ArgumentParser(
        description="Indonesian Mutual Fund (Reksa Dana) Quantitative Screener & Ranker"
    )
    parser.add_argument(
        "--type",
        "-t",
        choices=["all", "pu", "pasar_uang", "ob", "obligasi", "sh", "saham", "cp", "campuran", "global"],
        default="all",
        help="Filter by fund category (default: all)",
    )
    parser.add_argument(
        "--sharia",
        "-s",
        action="store_true",
        help="Filter only Sharia-compliant funds",
    )
    parser.add_argument(
        "--min-aum",
        type=str,
        default=None,
        help="Minimum AUM in IDR (e.g. 500b, 1t, 100miliar)",
    )
    parser.add_argument(
        "--max-mdd",
        type=float,
        default=None,
        help="Maximum absolute 1Y drawdown percentage (e.g. 0.5 for max 0.5 percent drop)",
    )
    parser.add_argument(
        "--sort",
        choices=["cagr_1y", "cagr_3y", "cagr_5y", "drawdown", "expense_ratio", "aum", "calmar"],
        default="cagr_1y",
        help="Sorting criteria (default: cagr_1y)",
    )
    parser.add_argument(
        "--top",
        "-n",
        type=int,
        default=15,
        help="Number of results to display (default: 15)",
    )
    parser.add_argument(
        "--query",
        "-q",
        type=str,
        default=None,
        help="Keyword search on fund name, symbol, or investment manager",
    )
    parser.add_argument(
        "--detail",
        "-d",
        type=str,
        default=None,
        help="Show comprehensive deep-dive into a single fund by name or symbol",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON array instead of terminal table",
    )

    args = parser.parse_args()
    console = Console(width=max(Console().width or 120, 120))
    data_dir = get_data_dir()

    client = BibitReksadanaClient()
    funds = client.load_catalog(data_dir)

    if not funds:
        console.print("[yellow]No local mutual fund catalog found. Fetching live universe...[/yellow]")
        try:
            funds = client.fetch_all()
            client.save_snapshot(funds, data_dir)
        except Exception as e:  # noqa: BLE001
            console.print(f"[bold red]Failed to fetch mutual funds: {e}[/bold red]")
            sys.exit(1)

    screener = MutualFundScreener(funds, console=console)

    # If detail mode is requested
    if args.detail:
        query_val = args.detail.lower().strip()
        matched = [
            f for f in funds
            if query_val in f.name.lower() or query_val in f.symbol.lower()
        ]
        if not matched:
            console.print(f"[bold red]No fund found matching '{args.detail}'[/bold red]")
            sys.exit(1)
        if args.json:
            print(json.dumps([m.model_dump(mode="json") for m in matched], indent=2))
        else:
            for m in matched:
                screener.render_detail(m)
        return

    min_aum_val = parse_aum_string(args.min_aum) if args.min_aum else 0.0

    ranked = screener.filter_and_rank(
        fund_type=args.type,
        sharia_only=args.sharia,
        min_aum=min_aum_val,
        max_drawdown_abs=args.max_mdd,
        query=args.query,
        sort_by=args.sort,
        limit=args.top,
    )

    if args.json:
        payload = [f.model_dump(mode="json") for f in ranked]
        print(json.dumps(payload, indent=2))
        return

    # Title label
    cat_label = args.type.upper() if args.type != "all" else "ALL ASSET CLASSES"
    sharia_label = " [SHARIA ONLY]" if args.sharia else ""
    title = f"Top Indonesian Mutual Funds — {cat_label}{sharia_label} (Sorted by {args.sort.upper()})"
    screener.render_table(ranked, title=title)
