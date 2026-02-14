import json
import pendulum
import sys
from pathlib import Path

# Import from transform-core
repo_root = Path(__file__).parents[4]
sys.path.insert(0, str(repo_root / "packages"))
from transform_core import get_data_dir


def clean_binance_data(raw_data):
    """Clean and extract relevant Binance data."""
    return {
        "timestamp": raw_data.get("timestamp"),
        "total_usd": raw_data.get("total_usd"),
        "assets": raw_data.get("assets", []),
    }


if __name__ == "__main__":
    # Main execution
    td = pendulum.now().format("YYYY-MM-DD")
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
        print(f"Binance data file not found: {raw_path}")
        print("Skipping Binance data processing.")
    except Exception as e:
        print(f"Error processing Binance data: {e}")
