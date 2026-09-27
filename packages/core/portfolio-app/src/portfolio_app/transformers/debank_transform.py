import json
import pendulum
import sys
from pathlib import Path

# Import from transform-core
repo_root = Path(__file__).parents[4]
sys.path.insert(0, str(repo_root / "packages"))
from transform_core import get_data_dir, parse_usd, FILTER_THRESHOLDS


def clean_tokens(tokens):
    threshold = FILTER_THRESHOLDS["USD"]
    aggregated = {}
    for token in tokens:
        symbol = token.get("symbol")
        if not symbol:
            continue
        
        val = parse_usd(token.get("value") or "0")
        amount_str = token.get("amount") or "0"
        if isinstance(amount_str, str):
            amount_str = amount_str.replace(",", "")
        
        try:
            amount = float(amount_str)
        except ValueError:
            amount = 0.0
            
        if symbol not in aggregated:
            aggregated[symbol] = {
                "symbol": symbol,
                "price": token.get("price"),
                "amount": 0.0,
                "value_usd": 0.0
            }
        
        aggregated[symbol]["amount"] += amount
        aggregated[symbol]["value_usd"] += val
        
    cleaned = []
    for data in aggregated.values():
        if data["value_usd"] >= threshold:
            # Reconstruct token object
            cleaned.append({
                "symbol": data["symbol"],
                "price": data["price"],
                "quantity": str(data["amount"]),
                "value": f"${data['value_usd']:,.2f}"
            })
    return cleaned


def clean_protocols(protocols):
    cleaned = []
    threshold = FILTER_THRESHOLDS["USD"]
    for proto in protocols:
        positions = proto.get("positions", [])
        
        # Calculate total value, prioritizing the top-level value if present
        if proto.get("value"):
            val = parse_usd(proto.get("value"))
        elif positions:
            # Sum up position values if top-level is missing
            val = sum(parse_usd(pos.get("value") or "0") for pos in positions)
        else:
            val = 0.0

        if val >= threshold:
            # If we have positions, we might want to filter them too, 
            # but for now we keep the protocol object and let the integrator handle it.
            cleaned.append(proto)
    return cleaned


def clean_data(data):
    data["tokens"] = clean_tokens(data.get("tokens", []))
    data["protocols"] = clean_protocols(data.get("protocols", []))
    return data


def extract_relevant(data):
    return {
        "wallet": data.get("wallet", {}),
        "social": data.get("social", {}),
        "chains": data.get("chains", []),
        "tokens": clean_tokens(data.get("tokens", [])),
        "protocols": clean_protocols(data.get("protocols", [])),
        "nfts": data.get("nfts", []),
        "timestamp": data.get("timestamp"),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Date in YYYY-MM-DD format")
    args = parser.parse_args()

    td = args.date or pendulum.now().format("YYYY-MM-DD")
    data_dir = get_data_dir()
    raw_path = data_dir / f"{td}_raw_debank.json"
    curated_path = data_dir / f"{td}_curated_debank.json"

    if raw_path.exists():
        with open(raw_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        cleaned_data = extract_relevant(raw_data)

        with open(curated_path, "w", encoding="utf-8") as f:
            json.dump(cleaned_data, f, indent=2)
        print(f"Curated data saved to {curated_path}")
    else:
        print(f"DeBank raw data not found at {raw_path}, skipping transform...")
        sys.exit(0)
