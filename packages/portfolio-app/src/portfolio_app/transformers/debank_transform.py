import json
import pendulum
import sys
from pathlib import Path

# Import from transform-core
repo_root = Path(__file__).parents[4]
sys.path.insert(0, str(repo_root / "packages"))
from transform_core import get_data_dir, parse_usd, FILTER_THRESHOLDS


def clean_wallets(wallets):
    threshold = FILTER_THRESHOLDS["debank_usd"]
    return [w for w in wallets if parse_usd(w.get("USD Value")) >= threshold]


def clean_protocols(protocols):
    cleaned = []
    threshold = FILTER_THRESHOLDS["debank_usd"]
    for proto in protocols:
        total_value = parse_usd(proto.get("usdValue"))
        if total_value < threshold:
            continue
        # Filter protocol data entries with USD Value < threshold
        data = proto.get("data", [])
        valid_data = [
            entry for entry in data if parse_usd(entry.get("USD Value")) >= threshold
        ]
        # Include protocol if it has valid data entries OR if the protocol itself has value
        if valid_data or total_value >= threshold:
            proto["data"] = valid_data
            cleaned.append(proto)
    return cleaned


def clean_data(data):
    data["wallets"] = clean_wallets(data.get("wallets", []))
    data["protocols"] = clean_protocols(data.get("protocols", []))
    return data


def extract_relevant(data):
    return {
        "wallets": clean_wallets(data.get("wallets", [])),
        "protocols": clean_protocols(data.get("protocols", [])),
        "timestamp": data.get("timestamp"),
    }


if __name__ == "__main__":
    # Example usage
    td = pendulum.now().format("YYYY-MM-DD")
    data_dir = get_data_dir()
    raw_path = data_dir / f"{td}_raw_debank.json"
    curated_path = data_dir / f"{td}_curated_debank.json"

    with open(raw_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    cleaned_data = extract_relevant(raw_data)

    with open(curated_path, "w", encoding="utf-8") as f:
        json.dump(cleaned_data, f, indent=2)
