import pytest
from datetime import datetime
from pathlib import Path
import sqlite3
from portfolio_app.snapshot_compactor import (
    classify_dates_by_retention,
    compact_local_data_dir,
    compact_sqlite_snapshots,
)


def test_classify_dates_by_retention():
    current_date = datetime(2026, 8, 24)

    # 1. Daily Tier (<= 30 days)
    # 2026-08-24, 2026-08-23, 2026-08-10, 2026-07-26 (29 days ago)
    # 2. Weekly Tier (31 to 180 days)
    # Week A: 2026-07-10 (Fri), 2026-07-12 (Sun) -> keep 2026-07-12, prune 2026-07-10
    # Week B: 2026-06-01 (Mon), 2026-06-05 (Fri) -> keep 2026-06-05, prune 2026-06-01
    # 3. Monthly Tier (> 180 days)
    # Month A (Jan 2026): 2026-01-05, 2026-01-15, 2026-01-31 -> keep 2026-01-31, prune 2026-01-05, 2026-01-15
    dates = [
        "2026-08-24",
        "2026-08-23",
        "2026-08-10",
        "2026-07-26",
        "2026-07-10",
        "2026-07-12",
        "2026-06-01",
        "2026-06-05",
        "2026-01-05",
        "2026-01-15",
        "2026-01-31",
    ]

    kept, pruned = classify_dates_by_retention(dates, current_date=current_date)

    # All daily dates kept
    assert "2026-08-24" in kept
    assert "2026-08-23" in kept
    assert "2026-08-10" in kept
    assert "2026-07-26" in kept

    # Weekly tier
    assert "2026-07-12" in kept
    assert "2026-07-10" in pruned
    assert "2026-06-05" in kept
    assert "2026-06-01" in pruned

    # Monthly tier
    assert "2026-01-31" in kept
    assert "2026-01-05" in pruned
    assert "2026-01-15" in pruned


def test_compact_local_data_dir(tmp_path: Path):
    current_date = datetime(2026, 8, 24)

    # Create dummy files
    # Daily (< 30d)
    (tmp_path / "2026-08-24_snapshot.json").write_text("{}")
    (tmp_path / "2026-08-24_raw_ksei.json").write_text("{}")
    (tmp_path / "2026-08-20_snapshot.json").write_text("{}")

    # Weekly (> 30d, <= 180d) - Same week: keep 2026-07-12, prune 2026-07-10
    (tmp_path / "2026-07-10_snapshot.json").write_text("{}")
    (tmp_path / "2026-07-12_snapshot.json").write_text("{}")
    (tmp_path / "2026-07-12_raw_ksei.json").write_text("{}") # intermediate raw on kept historical date should be pruned

    # Latest files (must NEVER be pruned)
    (tmp_path / "latest_ai_state.json").write_text("{}")
    (tmp_path / "latest_ai_digest.md").write_text("# Test")

    # Dry run
    res_dry = compact_local_data_dir(tmp_path, apply=False, current_date=current_date)
    assert res_dry["pruned_files_count"] == 2 # 2026-07-10_snapshot.json and 2026-07-12_raw_ksei.json
    assert (tmp_path / "2026-07-10_snapshot.json").exists()

    # Apply
    res_apply = compact_local_data_dir(tmp_path, apply=True, current_date=current_date)
    assert res_apply["pruned_files_count"] == 2
    assert not (tmp_path / "2026-07-10_snapshot.json").exists()
    assert not (tmp_path / "2026-07-12_raw_ksei.json").exists()
    assert (tmp_path / "2026-07-12_snapshot.json").exists()
    assert (tmp_path / "2026-08-24_snapshot.json").exists()
    assert (tmp_path / "2026-08-24_raw_ksei.json").exists()
    assert (tmp_path / "latest_ai_state.json").exists()


def test_compact_sqlite_snapshots(tmp_path: Path):
    db_file = tmp_path / "test_sansfinance.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE portfolio_snapshot_headers (
            snapshotDate INTEGER PRIMARY KEY,
            totalValueIdr INTEGER NOT NULL,
            totalValueUsd INTEGER NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE portfolio_holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date INTEGER NOT NULL,
            asset TEXT NOT NULL,
            value_idr INTEGER NOT NULL
        )
    """)

    current_date = datetime(2026, 8, 24)

    # Timestamps in ms
    ts_aug24 = int(datetime(2026, 8, 24, 12, 0).timestamp() * 1000)
    ts_jul10 = int(datetime(2026, 7, 10, 12, 0).timestamp() * 1000)
    ts_jul12 = int(datetime(2026, 7, 12, 12, 0).timestamp() * 1000)

    for ts in [ts_aug24, ts_jul10, ts_jul12]:
        cursor.execute("INSERT INTO portfolio_snapshot_headers VALUES (?, 1000, 100)", (ts,))
        cursor.execute("INSERT INTO portfolio_holdings (snapshot_date, asset, value_idr) VALUES (?, 'ST012', 1000)", (ts,))
    conn.commit()
    conn.close()

    # Dry run
    res_dry = compact_sqlite_snapshots(db_file, apply=False, current_date=current_date)
    assert res_dry["pruned_count"] == 1
    assert "2026-07-10" in res_dry["pruned_dates"]

    # Apply
    res_apply = compact_sqlite_snapshots(db_file, apply=True, current_date=current_date)
    assert res_apply["pruned_count"] == 1

    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("SELECT snapshotDate FROM portfolio_snapshot_headers")
    remaining = [r[0] for r in cursor.fetchall()]
    assert ts_aug24 in remaining
    assert ts_jul12 in remaining
    assert ts_jul10 not in remaining
    conn.close()
