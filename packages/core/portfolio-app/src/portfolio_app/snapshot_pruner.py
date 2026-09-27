"""
Monthly Portfolio Snapshot Pruner
Keeps only the latest snapshot per calendar month, removing intermediate duplicate snapshots.
"""

import os
import re
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime

from transform_core import get_data_dir


def prune_local_files(data_dir: Path, apply: bool = False) -> Dict[str, Any]:
    """Prunes local dated snapshot files (*_snapshot.json and *_portfolio.csv)."""
    if not data_dir.exists():
        return {"kept": 0, "pruned": 0, "pruned_files": []}

    date_regex = re.compile(r"^(\d{4}-\d{2}-\d{2})_.*")
    files = [f for f in data_dir.iterdir() if f.is_file() and date_regex.match(f.name)]

    month_to_files: Dict[str, Dict[str, List[Path]]] = {}
    for f in files:
        m = date_regex.match(f.name)
        if not m:
            continue
        d_str = m.group(1)
        m_str = d_str[:7]
        if m_str not in month_to_files:
            month_to_files[m_str] = {}
        if d_str not in month_to_files[m_str]:
            month_to_files[m_str][d_str] = []
        month_to_files[m_str][d_str].append(f)

    to_keep: List[Path] = []
    to_delete: List[Path] = []

    for m_str, d_dict in sorted(month_to_files.items()):
        sorted_dates = sorted(d_dict.keys())
        latest_date = sorted_dates[-1]
        to_keep.extend(d_dict[latest_date])

        for d in sorted_dates[:-1]:
            to_delete.extend(d_dict[d])

    deleted_names = [f.name for f in to_delete]
    if apply:
        for f in to_delete:
            try:
                f.unlink()
            except Exception as e:
                print(f"⚠️ Warning: Could not delete {f}: {e}")

    return {
        "apply": apply,
        "kept_count": len(to_keep),
        "pruned_count": len(to_delete),
        "pruned_files": deleted_names
    }


def prune_sqlite_snapshots(db_path: Path, apply: bool = False) -> Dict[str, Any]:
    """Prunes snapshot rows in SQLite DB keeping only the latest per month."""
    if not db_path.exists():
        return {"kept": 0, "pruned": 0, "pruned_dates": []}

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
        return {"kept": 0, "pruned": 0, "pruned_dates": []}

    month_to_ts: Dict[str, List[Tuple[int, str]]] = {}
    for (ts,) in rows:
        dt = datetime.fromtimestamp(ts / 1000.0) if ts > 10000000000 else datetime.fromtimestamp(ts)
        m_str = dt.strftime("%Y-%m")
        d_str = dt.strftime("%Y-%m-%d")
        if m_str not in month_to_ts:
            month_to_ts[m_str] = []
        month_to_ts[m_str].append((ts, d_str))

    keep_ts = set()
    delete_ts: List[Tuple[str, str, int]] = []

    for m_str, items in sorted(month_to_ts.items()):
        items.sort(key=lambda x: x[0])
        latest_item = items[-1]
        keep_ts.add(latest_item[0])

        for ts, d_str in items[:-1]:
            delete_ts.append((m_str, d_str, ts))

    if apply and delete_ts:
        ts_del_list = [ts for _, _, ts in delete_ts]
        placeholders = ",".join("?" * len(ts_del_list))

        cursor.execute(f"DELETE FROM portfolio_holdings WHERE snapshot_date IN ({placeholders})", ts_del_list)
        cursor.execute(f"DELETE FROM portfolio_snapshot_headers WHERE snapshotDate IN ({placeholders})", ts_del_list)
        conn.commit()

    conn.close()
    return {
        "apply": apply,
        "kept_count": len(keep_ts),
        "pruned_count": len(delete_ts),
        "pruned_dates": [d_str for _, d_str, _ in delete_ts]
    }
