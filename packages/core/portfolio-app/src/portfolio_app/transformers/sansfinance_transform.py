"""Sans Finance transformer: extract cash / P2P lending accounts from the app DB.

Reads ``{date}_raw_sansfinance.json`` (produced by ``sansfinance-fetch``) and
emits curated account records. Portfolio holdings from the APK are intentionally
NOT emitted here — they originate from KSEI/Binance/DeBank/Alchemy in this same
pipeline, so re-importing them would double-count. Only accounts unique to the
APK (bank cash, wallet cash, P2P lending) are curated.
"""

import json
import sys
from pathlib import Path

import pendulum

# Import from transform-core
repo_root = Path(__file__).parents[4]
sys.path.insert(0, str(repo_root / "packages"))
from transform_core import get_data_dir


def clean_sansfinance_data(raw_data):
    """Keep only non-zero IDR/USD cash & P2P accounts."""
    kept = []
    for acc in raw_data.get("accounts", []):
        balance = float(acc.get("balance") or 0)
        if abs(balance) < 1:  # ignore zero/negligible balances
            continue
        kept.append(acc)
    return {
        "timestamp": raw_data.get("timestamp"),
        "exchange_rate_usd": raw_data.get("exchange_rate_usd"),
        "portfolio_value_idr": raw_data.get("portfolio_value_idr"),
        "latest_snapshot_date": raw_data.get("latest_snapshot_date"),
        "accounts": kept,
    }


def to_curated_records(cleaned):
    """Map cleaned accounts into pipeline-style records for reference/debug."""
    records = []
    for acc in cleaned.get("accounts", []):
        category = "P2P Lending" if acc["type"] == "P2P Lending" else "Bank Account"
        records.append(
            {
                "source": "sansfinance",
                "category": category,
                "asset": acc["name"],
                "currency": acc["currency"],
                "quantity": 0,
                "price": 1.0,
                **({"value_idr": acc["balance"]} if acc["currency"] == "IDR" else {"value_usd": acc["balance"]}),
                "account": acc["name"],
                "details": f"Type: {acc['type']}",
            }
        )
    return records


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Date in YYYY-MM-DD format")
    args = parser.parse_args()

    td = args.date or pendulum.now().format("YYYY-MM-DD")
    data_dir = get_data_dir()
    raw_path = data_dir / f"{td}_raw_sansfinance.json"
    curated_path = data_dir / f"{td}_curated_sansfinance.json"

    try:
        with open(raw_path) as f:
            raw_data = json.load(f)
    except FileNotFoundError:
        print(f"No raw sansfinance data at {raw_path}; skipping.")
        sys.exit(0)

    cleaned = clean_sansfinance_data(raw_data)
    cleaned["records"] = to_curated_records(cleaned)

    with open(curated_path, "w") as f:
        json.dump(cleaned, f, indent=2)

    total_idr = sum(a["balance"] for a in cleaned["accounts"] if a["currency"] == "IDR")
    print(f"Wrote {len(cleaned['accounts'])} accounts (Rp {total_idr:,.0f}) to {curated_path}")
