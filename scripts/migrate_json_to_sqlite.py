#!/usr/bin/env python3
"""
Migration utility: Ingest all historical JSON snapshots & AI states into portfolio.db (SQLite).
Optionally archive historical JSON files into data/archive_legacy/.
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

# Add workspace packages to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages" / "transform-core" / "src"))

from transform_core.db import (
    get_connection,
    get_db_path,
    init_db,
    upsert_ai_state,
    upsert_snapshot,
)
from transform_core.utils import get_data_dir


def migrate_snapshots(data_dir: Path, conn) -> int:
    date_regex = re.compile(r"^(\d{4}-\d{2}-\d{2})_snapshot\.json$")
    snapshot_files = sorted([f for f in data_dir.glob("*_snapshot.json") if date_regex.match(f.name)])

    print(f"📦 Found {len(snapshot_files)} historical snapshot JSON files.")
    count = 0
    for f in snapshot_files:
        try:
            data = json.loads(f.read_text())
            td = data.get("metadata", {}).get("date") or f.name.split("_")[0]
            if "metadata" not in data:
                data["metadata"] = {}
            data["metadata"]["date"] = td
            upsert_snapshot(data, conn)
            count += 1
            print(f"  ✓ Ingested snapshot: {td} ({len(data.get('data', []))} holdings)")
        except Exception as e:
            print(f"  ❌ Failed to ingest {f.name}: {e}")

    return count


def migrate_ai_states(data_dir: Path, conn) -> int:
    date_regex = re.compile(r"^(\d{4}-\d{2}-\d{2})_ai_state\.json$")
    state_files = sorted([f for f in data_dir.glob("*_ai_state.json") if date_regex.match(f.name)])

    print(f"\n🤖 Found {len(state_files)} historical AI state files.")
    count = 0
    for f in state_files:
        try:
            m = date_regex.match(f.name)
            td = m.group(1)
            state_data = json.loads(f.read_text())
            digest_file = data_dir / f"{td}_ai_digest.md"
            digest_text = digest_file.read_text() if digest_file.exists() else ""
            upsert_ai_state(td, state_data, digest_text, conn)
            count += 1
            print(f"  ✓ Ingested AI state: {td}")
        except Exception as e:
            print(f"  ❌ Failed to ingest {f.name}: {e}")

    return count


def verify_database(conn) -> None:
    print("\n🔍 --- Database Verification ---")
    snapshots = conn.execute("SELECT date, net_worth_idr, total_items FROM snapshots ORDER BY date ASC").fetchall()
    print(f"Total Snapshots in DB: {len(snapshots)}")
    for s in snapshots:
        print(f"  • {s['date']}: Rp {s['net_worth_idr']:,.0f} ({s['total_items']} items)")

    holdings_count = conn.execute("SELECT count(*) FROM holdings").fetchone()[0]
    categories_count = conn.execute("SELECT count(*) FROM categories").fetchone()[0]
    ai_states_count = conn.execute("SELECT count(*) FROM ai_states").fetchone()[0]

    print(f"Total Holdings Records:   {holdings_count}")
    print(f"Total Category Rows:      {categories_count}")
    print(f"Total AI State Records:   {ai_states_count}")


def archive_legacy_files(data_dir: Path) -> None:
    archive_dir = data_dir / "archive_legacy"
    archive_dir.mkdir(parents=True, exist_ok=True)

    date_regex = re.compile(r"^\d{4}-\d{2}-\d{2}_.*")
    files_to_archive = [
        f for f in data_dir.iterdir()
        if f.is_file() and date_regex.match(f.name) and f.name != "portfolio.db"
    ]

    print(f"\n📦 Archiving {len(files_to_archive)} historical dated files to {archive_dir.name}/...")
    for f in files_to_archive:
        dest = archive_dir / f.name
        shutil.move(f, dest)

    print(f"✅ Archived {len(files_to_archive)} files. Clean directory state preserved.")


def main():
    parser = argparse.ArgumentParser(description="Migrate historical JSON snapshots to SQLite")
    parser.add_argument("--archive", action="store_true", help="Move dated JSON files to data/archive_legacy/ after migration")
    parser.add_argument("--verify", action="store_true", help="Verify database contents only")
    args = parser.parse_args()

    data_dir = get_data_dir()
    db_path = get_db_path()
    print(f"📂 Data Directory: {data_dir}")
    print(f"🏛️ SQLite Database: {db_path}\n")

    conn = get_connection(db_path)
    init_db(conn)

    if not args.verify:
        s_count = migrate_snapshots(data_dir, conn)
        ai_count = migrate_ai_states(data_dir, conn)
        print(f"\n🎉 Successfully migrated {s_count} snapshots and {ai_count} AI states to {db_path.name}.")

    verify_database(conn)

    if args.archive:
        archive_legacy_files(data_dir)

    conn.close()


if __name__ == "__main__":
    main()
