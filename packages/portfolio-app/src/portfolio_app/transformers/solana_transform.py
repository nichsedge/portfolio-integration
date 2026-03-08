import json
import pendulum
import sys
from pathlib import Path

# Import from transform-core
repo_root = Path(__file__).parents[4]
sys.path.insert(0, str(repo_root / "packages"))
from transform_core import get_data_dir


def clean_solana_data(raw_data):
    """Clean and extract relevant Solana data."""
    return {
        "timestamp": pendulum.now().to_iso8601_string(),
        "total_usd": sum(token.get("value_usd", 0) for token in raw_data),
        "assets": [
            {
                "mint": token.get("mint"),
                "symbol": token.get("symbol", "UNKNOWN"),
                "name": token.get("name", "Unknown Token"),
                "amount": token.get("amount"),
                "price": token.get("price"),
                "value_usd": token.get("value_usd"),
                "program_id": token.get("program_id"),
            }
            for token in raw_data
        ],
    }


if __name__ == "__main__":
    # Main execution
    td = pendulum.now().format("YYYY-MM-DD")
    data_dir = get_data_dir()
    raw_path = data_dir / f"{td}_raw_solana.json"
    curated_path = data_dir / f"{td}_curated_solana.json"

    try:
        with open(raw_path) as f:
            raw_data = json.load(f)

        cleaned = clean_solana_data(raw_data)

        with open(curated_path, "w") as f:
            json.dump(cleaned, f, indent=2)

        print(f"Cleaned Solana data saved to {curated_path}")
    except FileNotFoundError:
        print(f"Solana raw data not found at {raw_path}, skipping transform...")
        sys.exit(0)
    except Exception as e:
        print(f"Error processing Solana data: {e}")
        sys.exit(1)
