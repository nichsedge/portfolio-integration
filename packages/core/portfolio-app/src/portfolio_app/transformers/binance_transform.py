import json
import pendulum
import sys
from pathlib import Path

# Import from transform-core
repo_root = Path(__file__).parents[4]
sys.path.insert(0, str(repo_root / "packages"))
from transform_core import get_data_dir, FILTER_THRESHOLDS


def clean_binance_data(raw_data):
    """Clean and extract relevant Binance data."""
    assets = raw_data.get("assets", [])
    threshold = FILTER_THRESHOLDS.get("USD", 5)
    filtered_assets = [a for a in assets if float(a.get("value_usd", 0)) >= threshold]

    cleaned_assets = []
    for a in filtered_assets:
        asset = a.copy()
        if "amount" in asset:
            asset["quantity"] = asset.pop("amount")
        cleaned_assets.append(asset)

    return {
        "timestamp": raw_data.get("timestamp"),
        "total_usd": sum(float(a.get("value_usd", 0)) for a in filtered_assets),
        "assets": cleaned_assets,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Date in YYYY-MM-DD format")
    args = parser.parse_args()

    td = args.date or pendulum.now().format("YYYY-MM-DD")
    data_dir = get_data_dir()
    raw_path = data_dir / f"{td}_raw_binance.json"
    curated_path = data_dir / f"{td}_curated_binance.json"

    try:
        with open(raw_path) as f:
            raw_data = json.load(f)

        cleaned = clean_binance_data(raw_data)

        with open(curated_path, "w") as f:
            json.dump(cleaned, f, indent=2)

        print(f"Cleaned Binance data saved to {curated_path}")
    except FileNotFoundError:
        print(f"Binance raw data not found at {raw_path}, skipping transform...")
        sys.exit(0)
    except Exception as e:
        print(f"Error processing Binance data: {e}")
        sys.exit(1)
