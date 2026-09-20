"""
SQLite database engine for portfolio-integration.
Canonical SSOT for multi-asset portfolio snapshots, holdings history, and AI states.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from transform_core.utils import get_data_dir


def get_db_path() -> Path:
    """Return canonical path to portfolio.db."""
    return get_data_dir() / "portfolio.db"


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Get SQLite connection configured with WAL journal mode and Row factory."""
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    """Initialize database schema if not already present."""
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    with conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (
            date TEXT PRIMARY KEY,
            net_worth_idr REAL NOT NULL,
            net_worth_usd REAL NOT NULL,
            total_assets_idr REAL NOT NULL,
            total_liabilities_idr REAL NOT NULL,
            investments_idr REAL NOT NULL,
            investments_usd REAL NOT NULL,
            bank_cash_idr REAL NOT NULL,
            bank_cash_usd REAL NOT NULL,
            exchange_rate REAL NOT NULL,
            total_items INTEGER NOT NULL,
            metadata_json TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            source TEXT NOT NULL,
            category TEXT NOT NULL,
            asset_class TEXT NOT NULL,
            ticker TEXT,
            name TEXT,
            account TEXT,
            units REAL,
            price_idr REAL,
            value_idr REAL NOT NULL,
            value_usd REAL,
            allocation_pct REAL,
            details TEXT,
            raw_json TEXT,
            FOREIGN KEY (snapshot_date) REFERENCES snapshots(date) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS categories (
            snapshot_date TEXT NOT NULL,
            category TEXT NOT NULL,
            value_idr REAL NOT NULL,
            percentage REAL NOT NULL,
            count INTEGER NOT NULL,
            PRIMARY KEY (snapshot_date, category),
            FOREIGN KEY (snapshot_date) REFERENCES snapshots(date) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS asset_classes (
            snapshot_date TEXT NOT NULL,
            asset_class TEXT NOT NULL,
            value_idr REAL NOT NULL,
            percentage REAL NOT NULL,
            count INTEGER NOT NULL,
            PRIMARY KEY (snapshot_date, asset_class),
            FOREIGN KEY (snapshot_date) REFERENCES snapshots(date) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS ai_states (
            snapshot_date TEXT PRIMARY KEY,
            state_json TEXT NOT NULL,
            digest_md TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            FOREIGN KEY (snapshot_date) REFERENCES snapshots(date) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_holdings_date ON holdings(snapshot_date);
        CREATE INDEX IF NOT EXISTS idx_holdings_source ON holdings(source);
        CREATE INDEX IF NOT EXISTS idx_holdings_category ON holdings(category);
        """)

    if close_after:
        conn.close()


def _clean_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    import re
    clean = re.sub(r"[^\d.-]", "", str(val).replace(",", "").strip())
    try:
        return float(clean) if clean else None
    except Exception:
        return None


def upsert_snapshot(
    snapshot_data: Dict[str, Any],
    conn: sqlite3.Connection | None = None,
) -> None:
    """Insert or update a comprehensive snapshot with holdings and category aggregates."""
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    init_db(conn)

    meta = snapshot_data.get("metadata", {})
    totals = snapshot_data.get("totals", {})
    alloc = snapshot_data.get("allocation", {})
    holdings = snapshot_data.get("holdings") or snapshot_data.get("data") or []
    td = meta.get("date")
    if not td:
        raise ValueError("Snapshot metadata must contain 'date'")

    exchange_rate = float(meta.get("exchange_rate", 1.0))
    net_worth_idr = float(totals.get("net_worth_idr", 0.0))
    net_worth_usd = float(totals.get("net_worth_usd", net_worth_idr / exchange_rate if exchange_rate else 0.0))
    total_assets_idr = float(totals.get("total_assets_idr", 0.0))
    total_liabilities_idr = float(totals.get("total_liabilities_idr", 0.0))
    investments_idr = float(totals.get("investments_idr", 0.0))
    investments_usd = float(totals.get("investments_usd", investments_idr / exchange_rate if exchange_rate else 0.0))
    bank_cash_idr = float(totals.get("bank_cash_idr", 0.0))
    bank_cash_usd = float(totals.get("bank_cash_usd", bank_cash_idr / exchange_rate if exchange_rate else 0.0))
    total_items = int(meta.get("total_items", len(holdings)))
    created_at = meta.get("generated_at", datetime.now(timezone.utc).isoformat())

    with conn:
        # Upsert header
        conn.execute(
            """
            INSERT INTO snapshots (
                date, net_worth_idr, net_worth_usd, total_assets_idr, total_liabilities_idr,
                investments_idr, investments_usd, bank_cash_idr, bank_cash_usd,
                exchange_rate, total_items, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                net_worth_idr=excluded.net_worth_idr,
                net_worth_usd=excluded.net_worth_usd,
                total_assets_idr=excluded.total_assets_idr,
                total_liabilities_idr=excluded.total_liabilities_idr,
                investments_idr=excluded.investments_idr,
                investments_usd=excluded.investments_usd,
                bank_cash_idr=excluded.bank_cash_idr,
                bank_cash_usd=excluded.bank_cash_usd,
                exchange_rate=excluded.exchange_rate,
                total_items=excluded.total_items,
                metadata_json=excluded.metadata_json,
                created_at=excluded.created_at
            """,
            (
                td, net_worth_idr, net_worth_usd, total_assets_idr, total_liabilities_idr,
                investments_idr, investments_usd, bank_cash_idr, bank_cash_usd,
                exchange_rate, total_items, json.dumps(meta), created_at
            )
        )

        # Clear existing holdings and categories for this date to ensure idempotency
        conn.execute("DELETE FROM holdings WHERE snapshot_date = ?", (td,))
        conn.execute("DELETE FROM categories WHERE snapshot_date = ?", (td,))
        conn.execute("DELETE FROM asset_classes WHERE snapshot_date = ?", (td,))

        # Insert categories
        by_category = alloc.get("by_category", [])
        for c in by_category:
            conn.execute(
                """
                INSERT INTO categories (snapshot_date, category, value_idr, percentage, count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (td, c.get("category", "Unknown"), float(c.get("value_idr", 0.0)), float(c.get("percentage", 0.0)), int(c.get("count", 0)))
            )

        # Insert asset classes
        by_asset_class = alloc.get("by_asset_class", [])
        for ac in by_asset_class:
            conn.execute(
                """
                INSERT INTO asset_classes (snapshot_date, asset_class, value_idr, percentage, count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (td, ac.get("asset_class", "Unknown"), float(ac.get("value_idr", 0.0)), float(ac.get("percentage", 0.0)), int(ac.get("count", 0)))
            )

        # Insert individual holdings
        for item in holdings:
            val_idr = _clean_float(item.get("value_idr")) or 0.0
            val_usd_f = _clean_float(item.get("value_usd"))
            units = _clean_float(item.get("units") if item.get("units") is not None else item.get("quantity"))
            price = _clean_float(item.get("price_idr") if item.get("price_idr") is not None else item.get("price"))
            alloc_pct = _clean_float(item.get("allocation_percentage") if item.get("allocation_percentage") is not None else item.get("allocation_pct"))
            name = item.get("name") or item.get("asset") or item.get("ticker") or item.get("account")

            conn.execute(
                """
                INSERT INTO holdings (
                    snapshot_date, source, category, asset_class, ticker, name,
                    account, units, price_idr, value_idr, value_usd,
                    allocation_pct, details, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    td,
                    str(item.get("source", "unknown")),
                    str(item.get("category", "Other")),
                    str(item.get("asset_class") or item.get("category", "Other")),
                    item.get("ticker"),
                    name,
                    item.get("account"),
                    units,
                    price,
                    val_idr,
                    val_usd_f,
                    alloc_pct,
                    item.get("details"),
                    json.dumps(item)
                )
            )

    if close_after:
        conn.close()


def upsert_ai_state(
    snapshot_date: str,
    state_json: Dict[str, Any] | str,
    digest_md: str,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Store or update AI financial state and digest for a snapshot date."""
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    init_db(conn)
    state_str = state_json if isinstance(state_json, str) else json.dumps(state_json)
    now_str = datetime.now(timezone.utc).isoformat()

    with conn:
        conn.execute(
            """
            INSERT INTO ai_states (snapshot_date, state_json, digest_md, generated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(snapshot_date) DO UPDATE SET
                state_json=excluded.state_json,
                digest_md=excluded.digest_md,
                generated_at=excluded.generated_at
            """,
            (snapshot_date, state_str, digest_md, now_str)
        )

    if close_after:
        conn.close()


def get_latest_snapshot(conn: sqlite3.Connection | None = None) -> Optional[Dict[str, Any]]:
    """Retrieve the most recent snapshot header."""
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    row = conn.execute("SELECT * FROM snapshots ORDER BY date DESC LIMIT 1").fetchone()
    res = dict(row) if row else None
    if close_after:
        conn.close()
    return res


def get_snapshot_history(limit: int = 60, conn: sqlite3.Connection | None = None) -> List[Dict[str, Any]]:
    """Retrieve chronological snapshot history."""
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    rows = conn.execute("SELECT * FROM snapshots ORDER BY date ASC LIMIT ?", (limit,)).fetchall()
    res = [dict(r) for r in rows]
    if close_after:
        conn.close()
    return res


def get_holdings_for_date(snapshot_date: str, conn: sqlite3.Connection | None = None) -> List[Dict[str, Any]]:
    """Retrieve all holdings for a given snapshot date."""
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    rows = conn.execute("SELECT * FROM holdings WHERE snapshot_date = ? ORDER BY value_idr DESC", (snapshot_date,)).fetchall()
    res = [dict(r) for r in rows]
    if close_after:
        conn.close()
    return res


def get_full_snapshot(date: Optional[str] = None, conn: sqlite3.Connection | None = None) -> Optional[Dict[str, Any]]:
    """Retrieve full snapshot dict matching the canonical JSON schema, from portfolio.db."""
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    if date:
        row = conn.execute("SELECT * FROM snapshots WHERE date = ?", (date,)).fetchone()
    else:
        row = conn.execute("SELECT * FROM snapshots ORDER BY date DESC LIMIT 1").fetchone()

    if not row:
        if close_after:
            conn.close()
        return None

    snap_date = row["date"]
    cats = conn.execute(
        "SELECT category, value_idr, percentage, count FROM categories WHERE snapshot_date = ?",
        (snap_date,)
    ).fetchall()
    acs = conn.execute(
        "SELECT asset_class, value_idr, percentage, count FROM asset_classes WHERE snapshot_date = ?",
        (snap_date,)
    ).fetchall()
    holdings_rows = conn.execute(
        "SELECT * FROM holdings WHERE snapshot_date = ? ORDER BY value_idr DESC",
        (snap_date,)
    ).fetchall()

    meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
    meta["date"] = snap_date
    meta["exchange_rate"] = row["exchange_rate"]
    meta["total_items"] = row["total_items"]

    holdings = []
    for hr in holdings_rows:
        if hr["raw_json"]:
            try:
                holdings.append(json.loads(hr["raw_json"]))
                continue
            except Exception:
                pass
        holdings.append({
            "asset": hr["name"] or hr["ticker"],
            "name": hr["name"],
            "ticker": hr["ticker"],
            "category": hr["category"],
            "asset_class": hr["asset_class"],
            "source": hr["source"],
            "account": hr["account"],
            "units": hr["units"],
            "price_idr": hr["price_idr"],
            "value_idr": hr["value_idr"],
            "value_usd": hr["value_usd"],
            "allocation_percentage": hr["allocation_pct"],
            "details": hr["details"],
        })

    snapshot = {
        "metadata": meta,
        "totals": {
            "net_worth_idr": row["net_worth_idr"],
            "net_worth_usd": row["net_worth_usd"],
            "total_assets_idr": row["total_assets_idr"],
            "total_liabilities_idr": row["total_liabilities_idr"],
            "investments_idr": row["investments_idr"],
            "investments_usd": row["investments_usd"],
            "bank_cash_idr": row["bank_cash_idr"],
            "bank_cash_usd": row["bank_cash_usd"],
        },
        "allocation": {
            "by_category": [dict(c) for c in cats],
            "by_asset_class": [dict(ac) for ac in acs],
        },
        "holdings": holdings
    }

    if close_after:
        conn.close()

    return snapshot
