"""
Smart Portfolio Snapshot Compactor & Data Retention Policy

Retention Scheme:
1. Daily Tier (<= 30 days): Keep all daily snapshots & raw data.
2. Weekly Tier (31 to 180 days): Keep 1 snapshot per week (latest day in calendar week).
3. Monthly Tier (> 180 days): Keep 1 snapshot per calendar month (latest day in month).
4. Intermediate Pruning: Clean up redundant intermediate files (raw/curated) for historical snapshots.
5. SQLite Pruning: Prunes Room/SQLite database snapshot rows and holdings matching the retention policy.
"""

import os
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple, Optional

from transform_core import get_data_dir


def parse_date(date_str: str) -> Optional[datetime]:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None


def classify_dates_by_retention(
    all_dates: List[str],
    current_date: Optional[datetime] = None
) -> Tuple[Set[str], Set[str]]:
    """
    Classifies a list of YYYY-MM-DD date strings into (kept_dates, pruned_dates).
    """
    if not all_dates:
        return set(), set()

    if current_date is None:
        current_date = datetime.now()

    # Sort dates chronologically
    sorted_dates = sorted(list(set(all_dates)))
    
    kept_dates: Set[str] = set()
    pruned_dates: Set[str] = set()

    # Groupings for weekly and monthly tiers
    # key: (year, iso_week) -> list of date_strs
    weekly_groups: Dict[Tuple[int, int], List[str]] = {}
    # key: (year, month) -> list of date_strs
    monthly_groups: Dict[Tuple[int, int], List[str]] = {}

    for d_str in sorted_dates:
        dt = parse_date(d_str)
        if not dt:
            continue

        age_days = (current_date - dt).days

        if age_days <= 30:
            # Tier 1: Daily (Keep all)
            kept_dates.add(d_str)
        elif 30 < age_days <= 180:
            # Tier 2: Weekly
            iso_year, iso_week, _ = dt.isocalendar()
            w_key = (iso_year, iso_week)
            if w_key not in weekly_groups:
                weekly_groups[w_key] = []
            weekly_groups[w_key].append(d_str)
        else:
            # Tier 3: Monthly (> 180 days)
            m_key = (dt.year, dt.month)
            if m_key not in monthly_groups:
                monthly_groups[m_key] = []
            monthly_groups[m_key].append(d_str)

    # Process weekly groups: keep the latest date in each week
    for w_key, dates in weekly_groups.items():
        dates.sort()
        kept_dates.add(dates[-1])
        for d in dates[:-1]:
            pruned_dates.add(d)

    # Process monthly groups: keep the latest date in each month
    for m_key, dates in monthly_groups.items():
        dates.sort()
        kept_dates.add(dates[-1])
        for d in dates[:-1]:
            pruned_dates.add(d)

    return kept_dates, pruned_dates


def compact_local_data_dir(
    data_dir: Optional[Path] = None,
    apply: bool = False,
    current_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Applies the retention policy to local files in the data directory.
    Prunes redundant snapshot and raw files for pruned dates, and cleans up
    raw/curated intermediate files for dates older than 30 days.
    """
    if data_dir is None:
        data_dir = get_data_dir()

    if not data_dir.exists():
        return {"kept_files": 0, "pruned_files": 0, "pruned_file_list": []}

    date_regex = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.*)")
    all_files = [f for f in data_dir.iterdir() if f.is_file()]

    dated_files: Dict[str, List[Path]] = {}
    for f in all_files:
        # Never prune pointer files or non-dated files
        if f.name.startswith("latest") or f.name.startswith("."):
            continue
        m = date_regex.match(f.name)
        if m:
            d_str = m.group(1)
            if d_str not in dated_files:
                dated_files[d_str] = []
            dated_files[d_str].append(f)

    all_dates = list(dated_files.keys())
    kept_dates, pruned_dates = classify_dates_by_retention(all_dates, current_date=current_date)

    files_to_keep: List[Path] = []
    files_to_delete: List[Path] = []

    now = current_date or datetime.now()

    for d_str, files in dated_files.items():
        dt = parse_date(d_str)
        age_days = (now - dt).days if dt else 0

        if d_str in pruned_dates:
            # Delete all files for pruned dates
            files_to_delete.extend(files)
        else:
            # Kept date
            for f in files:
                # For historical kept dates older than 30 days, prune intermediate raw/curated scrapers
                if age_days > 30 and ("_raw_" in f.name or "_curated_" in f.name):
                    files_to_delete.append(f)
                else:
                    files_to_keep.append(f)

    deleted_names = [f.name for f in files_to_delete]

    if apply:
        for f in files_to_delete:
            try:
                f.unlink()
            except Exception as e:
                print(f"⚠️ Warning: Could not delete {f.name}: {e}")

    return {
        "apply": apply,
        "total_dates_found": len(all_dates),
        "kept_dates_count": len(kept_dates),
        "pruned_dates_count": len(pruned_dates),
        "kept_files_count": len(files_to_keep),
        "pruned_files_count": len(files_to_delete),
        "pruned_files": deleted_names
    }


def compact_sqlite_snapshots(
    db_path: Path,
    apply: bool = False,
    current_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Applies the retention policy to Sans Finance SQLite database snapshot tables:
    `portfolio_snapshot_headers` and `portfolio_holdings`.
    """
    if not db_path.exists():
        return {"kept_count": 0, "pruned_count": 0, "pruned_dates": []}

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT snapshotDate FROM portfolio_snapshot_headers ORDER BY snapshotDate ASC")
        rows = cursor.fetchall()
    except Exception as e:
        conn.close()
        return {"error": str(e)}

    if not rows:
        conn.close()
        return {"kept_count": 0, "pruned_count": 0, "pruned_dates": []}

    ts_to_date: Dict[int, str] = {}
    date_to_ts: Dict[str, List[int]] = {}

    for (ts,) in rows:
        dt = datetime.fromtimestamp(ts / 1000.0) if ts > 10000000000 else datetime.fromtimestamp(ts)
        d_str = dt.strftime("%Y-%m-%d")
        ts_to_date[ts] = d_str
        if d_str not in date_to_ts:
            date_to_ts[d_str] = []
        date_to_ts[d_str].append(ts)

    all_dates = list(date_to_ts.keys())
    kept_dates, pruned_dates = classify_dates_by_retention(all_dates, current_date=current_date)

    ts_to_keep: Set[int] = set()
    ts_to_delete: Set[int] = set()

    for d_str, ts_list in date_to_ts.items():
        if d_str in pruned_dates:
            ts_to_delete.update(ts_list)
        else:
            # For a kept date, keep only the latest timestamp if there are intra-day duplicates
            ts_list.sort()
            ts_to_keep.add(ts_list[-1])
            if len(ts_list) > 1:
                ts_to_delete.update(ts_list[:-1])

    if apply and ts_to_delete:
        del_list = list(ts_to_delete)
        placeholders = ",".join("?" * len(del_list))
        cursor.execute(f"DELETE FROM portfolio_holdings WHERE snapshot_date IN ({placeholders})", del_list)
        cursor.execute(f"DELETE FROM portfolio_snapshot_headers WHERE snapshotDate IN ({placeholders})", del_list)
        conn.commit()

    conn.close()
    return {
        "apply": apply,
        "kept_count": len(ts_to_keep),
        "pruned_count": len(ts_to_delete),
        "pruned_dates": sorted(list({ts_to_date[ts] for ts in ts_to_delete}))
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Smart Portfolio Snapshot Compactor & Retention Utility")
    parser.add_argument("--apply", action="store_true", help="Execute deletion (default is dry-run)")
    parser.add_argument("--db", type=str, default=None, help="Path to Sans Finance SQLite database to compact")
    parser.add_argument("--dir", type=str, default=None, help="Path to local data directory (defaults to PORTFOLIO_DATA_DIR)")

    args = parser.parse_args()

    data_dir = Path(args.dir) if args.dir else get_data_dir()
    print(f"🧹 Scanning local data directory: {data_dir}")
    file_result = compact_local_data_dir(data_dir=data_dir, apply=args.apply)
    mode = "EXECUTED" if args.apply else "DRY RUN"
    print(f"[{mode}] Files to keep: {file_result['kept_files_count']}, to prune: {file_result['pruned_files_count']}")
    if file_result["pruned_files"]:
        print(f"Pruned files: {file_result['pruned_files']}")

    if args.db:
        db_path = Path(args.db)
        if db_path.exists():
            print(f"🧹 Scanning SQLite DB: {db_path}")
            db_result = compact_sqlite_snapshots(db_path=db_path, apply=args.apply)
            print(f"[{mode}] DB Snapshots to keep: {db_result['kept_count']}, to prune: {db_result['pruned_count']}")


if __name__ == "__main__":
    main()
