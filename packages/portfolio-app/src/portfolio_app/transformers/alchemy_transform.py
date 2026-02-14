import json
import pendulum
import sys
from pathlib import Path

# Import from transform-core
repo_root = Path(__file__).parents[4]
sys.path.insert(0, str(repo_root / "packages"))
from transform_core import get_data_dir


def clean_alchemy_data(raw_data):
    """Clean and extract relevant Alchemy data."""
    assets = []

    for token in raw_data:
        balance = token.get("balance", 0)
        value_usd = token.get("value_usd", 0)

        # Only include tokens with non-zero balance
        if balance > 0:
            assets.append(
                {
                    "address": token.get("address"),
                    "network": token.get("network"),
                    "token_address": token.get("tokenAddress", "SOL"),
                    "symbol": token.get("symbol", "UNKNOWN"),
                    "name": token.get("name", "Unknown Token"),
                    "balance": balance,
                    "decimals": token.get("decimals"),
                    "value_usd": value_usd,
                }
            )

    return {
        "timestamp": pendulum.now().to_iso8601_string(),
        "total_usd": sum(asset.get("value_usd") or 0 for asset in assets),
        "assets": assets,
    }


if __name__ == "__main__":
    # Main execution
    td = pendulum.now().format("YYYY-MM-DD")
    data_dir = get_data_dir()
    raw_path = data_dir / f"{td}_raw_alchemy.json"
    curated_path = data_dir / f"{td}_curated_alchemy.json"

    try:
        with open(raw_path) as f:
            raw_data = json.load(f)

        cleaned = clean_alchemy_data(raw_data)

        with open(curated_path, "w") as f:
            json.dump(cleaned, f, indent=2)

        print(f"Cleaned Alchemy data saved to {curated_path}")
        print(f"Total USD: ${cleaned['total_usd']:.2f}")
    except FileNotFoundError:
        print(f"Alchemy data file not found: {raw_path}")
        print("Skipping Alchemy data processing.")
    except Exception as e:
        print(f"Error processing Alchemy data: {e}")
