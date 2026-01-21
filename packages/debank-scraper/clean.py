import json
import re
from collections import defaultdict

def parse_usd(value):
    """Convert strings like '$494.15' or '199.8499 USDC' to float."""
    if not value:
        return 0.0
    value = str(value)
    match = re.search(r"[\d,.]+", value.replace(",", ""))
    return float(match.group().replace(",", "")) if match else 0.0

def flatten_assets(data):
    assets = defaultdict(float)

    # --- From wallets ---
    for w in data.get("wallets", []):
        token = w.get("Token")
        usd_value = parse_usd(w.get("USD Value"))
        if usd_value > 10:
            assets[token] += usd_value

    # --- From protocols ---
    for p in data.get("protocols", []):
        usd_value = parse_usd(p.get("usdValue"))
        if usd_value > 10:
            token = p.get("name")
            assets[token] += usd_value

    return dict(assets)

if __name__ == "__main__":
    # Load from JSON file
    with open("debank_raw.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    result = flatten_assets(data)

    # Pretty-print result
    print(json.dumps(result, indent=2))
