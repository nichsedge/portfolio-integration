import json
import sys
import pendulum
from pathlib import Path

# Import from transform-core
repo_root = Path(__file__).parents[4]
sys.path.insert(0, str(repo_root / "packages"))
from transform_core import get_data_dir, FILTER_THRESHOLDS


def is_valid_cash(entry):
    return entry.get("saldoIdr", 0) >= FILTER_THRESHOLDS["IDR"]


def is_valid_investment(entry):
    return entry.get("nilaiInvestasi", 0) >= FILTER_THRESHOLDS["IDR"]


def clean_json(data):
    if not isinstance(data, dict):
        return {}

    filtered = {}

    # Filter cash
    if data.get("cash") and isinstance(data["cash"], dict):
        cash_entries = data["cash"].get("data") or []
        filtered["cash"] = {
            **data["cash"],
            "data": [entry for entry in cash_entries if is_valid_cash(entry)],
        }

    # Filter equity
    if data.get("equity") and isinstance(data["equity"], dict):
        equity_entries = data["equity"].get("data") or []
        filtered["equity"] = {
            **data["equity"],
            "data": [entry for entry in equity_entries if is_valid_investment(entry)],
        }

    # Filter mutual_fund
    if data.get("mutual_fund") and isinstance(data["mutual_fund"], dict):
        mf_entries = data["mutual_fund"].get("data") or []
        filtered["mutual_fund"] = {
            **data["mutual_fund"],
            "data": [entry for entry in mf_entries if is_valid_investment(entry)],
        }

    # Filter bond
    if data.get("bond") and isinstance(data["bond"], dict):
        bond_entries = data["bond"].get("data") or []
        filtered["bond"] = {
            **data["bond"],
            "data": [entry for entry in bond_entries if is_valid_investment(entry)],
        }

    return filtered


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Date in YYYY-MM-DD format")
    args = parser.parse_args()

    # Load input from file
    td = args.date or pendulum.now().format("YYYY-MM-DD")
    data_dir = get_data_dir()
    raw_path = data_dir / f"{td}_raw_ksei.json"
    curated_path = data_dir / f"{td}_curated_ksei.json"

    try:
        with open(raw_path, "r", encoding="utf-8") as file:
            original_data = json.load(file)
    except FileNotFoundError:
        print(f"KSEI raw data not found at {raw_path}, skipping transform...")
        sys.exit(0)

    # Clean the data
    cleaned_data = clean_json(original_data)

    # Write output to file
    with open(curated_path, "w", encoding="utf-8") as file:
        json.dump(cleaned_data, file, indent=2, ensure_ascii=False)
