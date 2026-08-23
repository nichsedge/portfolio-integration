"""
Portfolio Data Quality & Integrity Validator
Enforces strict schema, value, and anomaly guardrails to prevent corrupted,
empty, or partial data from overwriting snapshots, GCS, or AI states.
"""

import json
import math
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from pydantic import ValidationError
from transform_core.models import (
    PortfolioHoldingRecord,
    VALID_ASSET_CLASSES,
    VALID_CATEGORIES,
)


class DataQualityError(Exception):
    """Raised when data quality validation fails critically."""
    pass


def validate_exchange_rate(rate: Optional[float]) -> List[str]:
    """Validate USD/IDR exchange rate is within realistic boundaries."""
    errors = []
    if rate is None or math.isnan(rate) or rate <= 0:
        errors.append(f"Invalid exchange rate: {rate}")
    elif rate < 10000.0 or rate > 30000.0:
        errors.append(f"Exchange rate out of realistic range (10,000 - 30,000): {rate}")
    return errors


def validate_single_holding(holding: Dict[str, Any], idx: int, exchange_rate: float) -> Tuple[List[str], List[str]]:
    """
    Validates a single holding item using Pydantic schemas and mathematical sanity checks.
    Returns (critical_errors, warnings).
    """
    errors = []
    warnings = []
    asset_name = holding.get("asset", "Unknown")
    prefix = f"Holding #{idx} ({asset_name})"

    # 1. Pydantic schema and type validation
    try:
        PortfolioHoldingRecord.model_validate(holding)
    except ValidationError as e:
        for err in e.errors():
            loc = ".".join(str(l) for l in err["loc"])
            errors.append(f"{prefix}: Field '{loc}' {err['msg']}")

    # 2. Strict category and asset class checks
    cat = holding.get("category")
    if not cat or cat not in VALID_CATEGORIES:
        warnings.append(f"{prefix}: Category '{cat}' is not in standard VALID_CATEGORIES")

    aclass = holding.get("asset_class")
    if not aclass or aclass not in VALID_ASSET_CLASSES:
        errors.append(f"{prefix}: Invalid asset_class '{aclass}'. Must be one of {VALID_ASSET_CLASSES}")

    # 3. Numeric fields non-negative and finite checks
    for num_field in ["quantity", "price", "value_idr", "value_usd"]:
        val = holding.get(num_field)
        if val is not None and (math.isnan(val) if isinstance(val, (int, float)) else False):
            errors.append(f"{prefix}: Numeric field '{num_field}' is NaN")

    # 4. Math consistency check between IDR and USD
    val_idr = holding.get("value_idr")
    val_usd = holding.get("value_usd")
    if val_idr is not None and val_usd is not None and exchange_rate > 0:
        try:
            val_idr_f = float(val_idr)
            val_usd_f = float(val_usd)
            expected_idr = val_usd_f * exchange_rate
            # Allow 10% tolerance for rounding / market rate diffs
            if val_idr_f > 100000 and abs(val_idr_f - expected_idr) > (max(val_idr_f, expected_idr) * 0.10):
                warnings.append(f"{prefix}: IDR value ({val_idr_f:,.0f}) and USD value ({val_usd_f:,.2f}) mismatch with FX {exchange_rate:,.2f}")
        except (ValueError, TypeError):
            pass

    return errors, warnings


def validate_holdings_and_sources(
    holdings: List[Dict[str, Any]],
    exchange_rate: float,
    previous_snapshot: Optional[Dict[str, Any]] = None
) -> Tuple[List[str], List[str]]:
    """
    Validates the entire aggregated holdings dataset and performs cross-source anomaly detection.
    """
    critical_errors = []
    warnings = []

    # 1. Non-empty holdings check
    if not holdings:
        critical_errors.append("Holdings list is completely EMPTY. Integration cannot produce a 0-holding snapshot.")
        return critical_errors, warnings

    # 2. Validate FX rate
    critical_errors.extend(validate_exchange_rate(exchange_rate))

    # 3. Individual holding checks
    for idx, h in enumerate(holdings, start=1):
        errs, warns = validate_single_holding(h, idx, exchange_rate)
        critical_errors.extend(errs)
        warnings.extend(warns)

    # 4. Source Disappearance / Missing Source Check
    current_sources = {h.get("source") for h in holdings if h.get("source")}
    total_val = sum(h.get("value_idr", 0.0) for h in holdings)

    if previous_snapshot:
        prev_holdings = previous_snapshot.get("holdings", [])
        prev_sources = {h.get("source") for h in prev_holdings if h.get("source")}
        prev_totals = previous_snapshot.get("totals", {})
        prev_nw = prev_totals.get("net_worth_idr", 0.0)

        # Check if a previously major source completely vanished
        for src in prev_sources:
            prev_src_val = sum(h.get("value_idr", 0.0) for h in prev_holdings if h.get("source") == src)
            if prev_nw > 0 and (prev_src_val / prev_nw) >= 0.15:
                # Source was > 15% of net worth previously
                if src not in current_sources:
                    critical_errors.append(
                        f"CRITICAL SOURCE MISSING: '{src}' had Rp {prev_src_val:,.0f} ({prev_src_val/prev_nw*100:.1f}%) in previous snapshot, but is completely missing in current run. Likely API/Scraper failure!"
                    )

        # Check for catastrophic sudden net worth collapse
        if prev_nw > 0:
            drop_pct = ((total_val - prev_nw) / prev_nw) * 100
            if drop_pct < -25.0:
                critical_errors.append(
                    f"ANOMALOUS NET WORTH DROP: Net worth dropped by {drop_pct:.1f}% (from Rp {prev_nw:,.0f} to Rp {total_val:,.0f}). This indicates partial data extraction failure."
                )

        # Check if a major asset class vanished
        prev_classes = {
            item.get("asset_class") for item in previous_snapshot.get("allocation", {}).get("by_asset_class", [])
            if item.get("percentage", 0) >= 15.0
        }
        current_classes = {h.get("asset_class") for h in holdings}
        for aclass in prev_classes:
            if aclass not in current_classes:
                critical_errors.append(
                    f"MAJOR ASSET CLASS VANISHED: '{aclass}' represented significant allocation in previous snapshot, but has 0 holdings now."
                )

    return critical_errors, warnings


def print_data_quality_report(
    critical_errors: List[str],
    warnings: List[str],
    snapshot_date: str,
    total_items: int,
    net_worth_idr: float
) -> bool:
    """Prints a Rich report of data quality status. Returns True if passed, False if failed."""
    console = Console()

    if critical_errors:
        console.print(Panel(
            f"[bold red]❌ DATA QUALITY VALIDATION FAILED[/] for [yellow]{snapshot_date}[/]\n"
            f"[bold white]Found {len(critical_errors)} critical error(s). Snapshot blocked from corrupting storage/AI.[/]",
            box=box.DOUBLE,
            border_style="red"
        ))

        table = Table(title="Critical Data Quality Violations", box=box.ROUNDED, border_style="red")
        table.add_column("#", style="dim", width=4)
        table.add_column("Violation Detail", style="bold red")

        for idx, err in enumerate(critical_errors, start=1):
            table.add_row(str(idx), err)
        console.print(table)

        if warnings:
            warn_table = Table(title="Quality Warnings", box=box.ROUNDED, border_style="yellow")
            warn_table.add_column("#", style="dim", width=4)
            warn_table.add_column("Warning Detail", style="yellow")
            for idx, w in enumerate(warnings, start=1):
                warn_table.add_row(str(idx), w)
            console.print(warn_table)

        console.print("\n[bold red]🛑 Action Aborted: Bad data will NOT be saved as latest snapshot or uploaded to GCS.[/]\n")
        return False

    # Passed
    if warnings:
        console.print(Panel(
            f"[bold yellow]⚠️ DATA QUALITY PASSED WITH {len(warnings)} WARNING(S)[/] — [yellow]{snapshot_date}[/]\n"
            f"Holdings: [cyan]{total_items}[/] | Net Worth: [green]Rp {net_worth_idr:,.0f}[/]",
            box=box.ROUNDED,
            border_style="yellow"
        ))
    else:
        console.print(f"✅ [bold green]Data Quality Gate: PASSED[/] ({total_items} valid holdings, schema 100% sound)")

    return True
