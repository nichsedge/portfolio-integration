import json
import csv
import pendulum
from typing import List, Dict, Any
import os
from pathlib import Path

# Import cleaning functions from existing modules
import sys
from pathlib import Path

# Setup paths for monorepo imports
file_path = Path(__file__).resolve()
# Current file: packages/portfolio-app/src/portfolio_app/integrators/portfolio_integration.py
repo_root = file_path.parents[5]
sys.path.append(str(repo_root / "packages/portfolio-app/src"))
sys.path.append(str(repo_root / "packages/transform-core/src"))

from portfolio_app.transformers.ksei_transform import clean_json
from portfolio_app.transformers.debank_transform import extract_relevant
from transform_core import get_data_dir, parse_usd


STABLE_COINS = {"USDT", "USDC", "DAI", "FDUSD", "TUSD", "BUSD", "PYUSD", "USDP"}
GOLD_ASSETS = {"PAXG", "XAUT"}


def get_standard_category(category: str, asset: str) -> str:
    """Return the correct category, separating stablecoins and gold from crypto/defi."""
    if category in ["Cryptocurrency", "DeFi Protocol"]:
        if asset in STABLE_COINS:
            return "USD/stables"
        if asset in GOLD_ASSETS:
            return "Gold"
    return category


def standardize_ksei_data(ksei_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert KSEI data to standardized format."""
    standardized = []

    # Process cash
    if "cash" in ksei_data:
        for entry in ksei_data["cash"].get("data", []):
            currency = entry.get("currCode", "IDR")
            if currency == "IDR":
                value_idr = entry.get("saldoIdr", 0)
                value_usd = None
            else:
                value_idr = None
                value_usd = entry.get(
                    "saldo", 0
                )  # For non-IDR currencies, use original saldo as USD

            standardized.append(
                {
                    "source": "KSEI",
                    "category": "Cash",
                    "asset": entry.get("bank", "Unknown"),
                    "currency": currency,
                    "amount": entry.get("saldo", 0),
                    "value_idr": value_idr,
                    "value_usd": value_usd,
                    "account": entry.get("rekening", ""),
                    "details": f"Bank: {entry.get('bank', '')}, Account: {entry.get('rekening', '')}",
                }
            )

    # Process equity
    if "equity" in ksei_data:
        for entry in ksei_data["equity"].get("data", []):
            standardized.append(
                {
                    "source": "KSEI",
                    "category": "Equity",
                    "asset": entry.get("efek", "Unknown").split(" - ")[0],
                    "currency": "IDR",
                    "amount": entry.get("jumlah", 0),
                    "value_idr": entry.get("nilaiInvestasi", 0),
                    "value_usd": None,
                    "account": entry.get("rekening", ""),
                    "details": f"Stock: {entry.get('efek', '')}, Broker: {entry.get('partisipan', '')}, Price: {entry.get('harga', 0)}",
                }
            )

    # Process mutual funds
    if "mutual_fund" in ksei_data:
        for entry in ksei_data["mutual_fund"].get("data", []):
            standardized.append(
                {
                    "source": "KSEI",
                    "category": "Mutual Fund",
                    "asset": entry.get("efek", "Unknown"),
                    "currency": "IDR",
                    "amount": entry.get("jumlah", 0),
                    "value_idr": entry.get("nilaiInvestasi", 0),
                    "value_usd": None,
                    "account": entry.get("rekening", ""),
                    "details": f"Fund: {entry.get('efek', '')}, Manager: {entry.get('partisipan', '')}",
                }
            )

    # Process bonds
    if "bond" in ksei_data:
        for entry in ksei_data["bond"].get("data", []):
            standardized.append(
                {
                    "source": "KSEI",
                    "category": "Bond",
                    "asset": entry.get("efek", "Unknown"),
                    "currency": "IDR",
                    "amount": entry.get("jumlah", 0),
                    "value_idr": entry.get("nilaiInvestasi", 0),
                    "value_usd": None,
                    "account": entry.get("rekening", ""),
                    "details": f"Bond: {entry.get('efek', '')}, Issuer: {entry.get('partisipan', '')}",
                }
            )

    return standardized


def standardize_debank_data(debank_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert DeBank data to standardized format."""
    standardized = []

    # Process wallet tokens (aggregated by symbol)
    token_aggregation = {}
    for token in debank_data.get("tokens", []):
        usd_value = parse_usd(token.get("value") or "0")
        if usd_value > 0:
            symbol = token.get("symbol", "Unknown")
            amount_str = token.get("amount") or "0"
            if isinstance(amount_str, str):
                amount_str = amount_str.replace(",", "")
            
            try:
                amount = float(amount_str)
            except ValueError:
                amount = 0.0

            if symbol not in token_aggregation:
                token_aggregation[symbol] = {
                    "source": "DeBank",
                    "category": get_standard_category("Cryptocurrency", symbol),
                    "asset": symbol,
                    "currency": "USD",
                    "amount": 0.0,
                    "value_idr": None,
                    "value_usd": 0.0,
                    "account": "DeBank Wallet",
                    "details": f"Price: {token.get('price', '')}",
                }
            
            token_aggregation[symbol]["amount"] += amount
            token_aggregation[symbol]["value_usd"] += usd_value

    for aggregated_token in token_aggregation.values():
        standardized.append(aggregated_token)

    # Process protocols
    for protocol in debank_data.get("protocols", []):
        protocol_name = protocol.get("name", "Unknown")
        positions = protocol.get("positions", [])

        if positions:
            for pos in positions:
                usd_value = parse_usd(pos.get("value") or "0")
                if usd_value > 0:
                    pool = pos.get("pool", "Unknown Pool")
                    pos_type = pos.get("type", "Protocol")
                    
                    # Differentiate category based on type
                    category = "DeFi Protocol"
                    if pos_type == "Yield": category = "DeFi Yield"
                    elif pos_type == "Staked": category = "DeFi Staked"
                    elif pos_type == "Lending": category = "DeFi Lending"
                    elif pos_type == "Borrow": category = "DeFi Debt"
                    elif pos_type == "Rewards": category = "DeFi Rewards"
                    elif pos_type == "Deposit": category = "DeFi Deposit"

                    # Construct detailed asset name
                    asset_name = f"{protocol_name} - {pool}"
                    if pos_type and pos_type not in ["Other", "Protocol"]:
                        asset_name = f"{protocol_name} ({pos_type}) - {pool}"

                    # Clean up pool name if it contains too much noise (e.g. newline)
                    asset_name = asset_name.replace("\n", " ").strip()

                    # Construct details from tokens
                    tokens = pos.get("tokens", [])
                    token_list = [t.get("balance", "").replace("\n", " ").strip() for t in tokens if t.get("balance")]
                    token_details = ", ".join(token_list)

                    standardized.append(
                        {
                            "source": "DeBank",
                            "category": category,
                            "asset": asset_name,
                            "currency": "USD",
                            "amount": 1.0,
                            "value_idr": None,
                            "value_usd": usd_value,
                            "account": "DeBank Protocol",
                            "details": f"Protocol: {protocol_name}, Position: {pos_type}, Tokens: {token_details}",
                        }
                    )
        else:
            # Fallback to summary if no positions extracted
            usd_value = parse_usd(protocol.get("value") or "0")
            if usd_value > 0:
                standardized.append(
                    {
                        "source": "DeBank",
                        "category": "DeFi Protocol",
                        "asset": protocol_name,
                        "currency": "USD",
                        "amount": 1.0,
                        "value_idr": None,
                        "value_usd": usd_value,
                        "account": "DeBank Protocol",
                        "details": f"Protocol: {protocol_name} (Summary)",
                    }
                )

    # Process NFTs (minimal summary)
    for nft in debank_data.get("nfts", []):
        avg_price = parse_usd(nft.get("avg_price") or "0")
        amount_str = nft.get("amount") or "1"
        if not amount_str.strip():
            amount_str = "1"
        
        try:
            amount = float(amount_str.replace(",", ""))
        except ValueError:
            amount = 1.0
            
        value_usd = avg_price * amount if avg_price > 0 else 0
        
        if value_usd > 0 or avg_price > 0:
            standardized.append(
                {
                    "source": "DeBank",
                    "category": "NFT",
                    "asset": nft.get("collection", "Unknown"),
                    "currency": "USD",
                    "amount": amount,
                    "value_idr": None,
                    "value_usd": value_usd if value_usd > 0 else avg_price,
                    "account": "DeBank NFT",
                    "details": f"Collection: {nft.get('collection')}, Avg Price: {nft.get('avg_price')}",
                }
            )

    return standardized


def standardize_binance_data(binance_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert Binance data to standardized format."""
    standardized = []

    for asset in binance_data.get("assets", []):
        asset_symbol = asset.get("symbol", "Unknown")
        price_usd = asset.get("price_usd", 0)
        amount = asset.get("amount", 0)
        value_usd = asset.get("value_usd", 0)

        standardized.append(
            {
                "source": "Binance",
                "category": get_standard_category("Cryptocurrency", asset_symbol),
                "asset": asset_symbol,
                "currency": "USD",
                "amount": amount,
                "value_idr": None,
                "value_usd": value_usd,
                "account": "Binance Main Account",
                "details": f"Price: ${price_usd:,.2f}, Amount: {amount:,.8f}",
            }
        )

    return standardized


def standardize_alchemy_data(alchemy_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert Alchemy curated data to standardized format."""
    standardized = []

    for asset in alchemy_data.get("assets", []):
        asset_symbol = asset.get("symbol", "Unknown")
        name = asset.get("name", "Unknown Token")
        price = asset.get(
            "price", 0
        )  # Note: Alchemy curated data might have price, if not we fall back to 0
        amount = asset.get("balance", 0)
        value_usd = asset.get("value_usd", 0)

        standardized.append(
            {
                "source": "Alchemy",
                "category": get_standard_category("Cryptocurrency", asset_symbol),
                "asset": asset_symbol,
                "currency": "USD",
                "amount": amount,
                "value_idr": None,
                "value_usd": value_usd,
                "account": "Alchemy Wallet",
                "details": f"Token: {name}, Network: {asset.get('network', 'Unknown')}, Amount: {amount:,.8f}",
            }
        )

    return standardized


def standardize_manual_data(manual_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert Manual data to standardized format."""
    standardized = []
    
    for row in manual_data:
        category = row.get("category", "Unknown")
        asset = row.get("asset", "Unknown")
        standardized.append({
            "source": row.get("source", "Manual"),
            "category": get_standard_category(category, asset),
            "asset": asset,
            "currency": row.get("currency", ""),
            "amount": row.get("amount"),  # These are already parsed as floats where appropriate
            "value_idr": row.get("value_idr"),
            "value_usd": row.get("value_usd"),
            "account": row.get("account", ""),
            "details": row.get("details", "")
        })
        
    return standardized


def main():
    """Main function to integrate KSEI and DeBank data into CSV."""
    # Get today's date
    td = pendulum.now().format("YYYY-MM-DD")

    # File paths
    data_dir = get_data_dir()
    ksei_raw_path = data_dir / f"{td}_raw_ksei.json"
    debank_raw_path = data_dir / f"{td}_raw_debank.json"
    binance_raw_path = data_dir / f"{td}_raw_binance.json"
    alchemy_curated_path = data_dir / f"{td}_curated_alchemy.json"
    manual_csv_path = data_dir / "_manual_balances.csv"
    output_csv_path = data_dir / f"{td}_portfolio.csv"

    # Try to load KSEI data
    try:
        with open(ksei_raw_path, "r", encoding="utf-8") as f:
            ksei_raw = json.load(f)
        ksei_loaded = True
    except FileNotFoundError:
        print(f"KSEI data not found at {ksei_raw_path}, skipping...")
        ksei_raw = {}
        ksei_loaded = False

    # Try to load DeBank data
    try:
        with open(debank_raw_path, "r", encoding="utf-8") as f:
            debank_raw = json.load(f)
        debank_loaded = True
    except FileNotFoundError:
        print(f"DeBank data not found at {debank_raw_path}, skipping...")
        debank_raw = {}
        debank_loaded = False

    # Try to load Binance data (optional)
    try:
        with open(binance_raw_path, "r", encoding="utf-8") as f:
            binance_raw = json.load(f)
        binance_clean = binance_raw
        binance_standardized = standardize_binance_data(binance_clean)
        binance_loaded = True
    except FileNotFoundError:
        print(f"Binance data not found at {binance_raw_path}, skipping...")
        binance_standardized = []
        binance_loaded = False

    # Try to load Alchemy data (optional)
    try:
        with open(alchemy_curated_path, "r", encoding="utf-8") as f:
            alchemy_curated = json.load(f)
        alchemy_standardized = standardize_alchemy_data(alchemy_curated)
        alchemy_loaded = True
    except FileNotFoundError:
        print(f"Alchemy curated data not found at {alchemy_curated_path}, skipping...")
        alchemy_standardized = []
        alchemy_loaded = False

    # Try to load Manual CSV data
    manual_loaded = False
    manual_standardized = []
    if manual_csv_path.exists():
        try:
            with open(manual_csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                manual_raw = []
                for row in reader:
                    # Convert numeric fields
                    for field in ["amount", "value_idr", "value_usd"]:
                        if row.get(field):
                            try:
                                row[field] = float(row[field])
                            except ValueError:
                                row[field] = 0.0
                        else:
                            row[field] = None
                    manual_raw.append(row)
            manual_standardized = standardize_manual_data(manual_raw)
            manual_loaded = True
            print(f"Loaded {len(manual_standardized)} manual items.")
        except Exception as e:
            print(f"Error loading manual data: {e}")
    else:
        print("Manual data not found, skipping...")

    # Clean and process data (only if data was loaded)
    if ksei_loaded:
        ksei_clean = clean_json(ksei_raw)
        ksei_standardized = standardize_ksei_data(ksei_clean)
    else:
        ksei_standardized = []

    if debank_loaded:
        debank_clean = extract_relevant(debank_raw)
        debank_standardized = standardize_debank_data(debank_clean)
    else:
        debank_standardized = []

    # Combine all data
    all_data = (
        ksei_standardized
        + debank_standardized
        + binance_standardized
        + alchemy_standardized
        + manual_standardized
    )

    # Sort by source, category, and asset
    all_data.sort(
        key=lambda x: (
            str(x.get("category") or ""),
            str(x.get("source") or ""),
            str(x.get("asset") or ""),
        )
    )

    # Write to CSV
    fieldnames = [
        "source",
        "category",
        "asset",
        "currency",
        "amount",
        "value_idr",
        "value_usd",
        "account",
        "details",
    ]

    with open(output_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_data)

    # Print summary
    total_idr = sum(
        item["value_idr"] for item in all_data if item["value_idr"] is not None
    )
    total_usd = sum(
        item["value_usd"] for item in all_data if item["value_usd"] is not None
    )

    print(f"Portfolio integration completed!")
    print(f"Output: {output_csv_path}")
    print(f"Total assets: {len(all_data)}")

    # Build sources list
    sources_parts = []
    if ksei_loaded:
        sources_parts.append(f"KSEI ({len(ksei_standardized)} items)")
    if debank_loaded:
        sources_parts.append(f"DeBank ({len(debank_standardized)} items)")
    if binance_loaded:
        sources_parts.append(f"Binance ({len(binance_standardized)} items)")
    if alchemy_loaded:
        sources_parts.append(f"Alchemy ({len(alchemy_standardized)} items)")
    if manual_loaded:
        sources_parts.append(f"Manual ({len(manual_standardized)} items)")
    print(f"Sources: {', '.join(sources_parts) if sources_parts else 'No data sources loaded'}")

    if total_idr > 0:
        print(f"Total IDR value: {total_idr:,.2f}")
    if total_usd > 0:
        print(f"Total USD value: {total_usd:,.2f}")

    print(f"\nBreakdown by category:")

    categories = {}
    for item in all_data:
        cat = item["category"]
        if cat not in categories:
            categories[cat] = {"count": 0, "value_idr": 0, "value_usd": 0}
        categories[cat]["count"] += 1
        if item["value_idr"] is not None:
            categories[cat]["value_idr"] += item["value_idr"]
        if item["value_usd"] is not None:
            categories[cat]["value_usd"] += item["value_usd"]

    # Sort by USD value for display, with fallback to IDR
    def category_sort_key(category_data):
        if category_data[1]["value_usd"] > 0:
            return category_data[1]["value_usd"]
        else:
            return category_data[1]["value_idr"] / 16000  # Approximate for sorting only

    for cat, data in sorted(categories.items(), key=category_sort_key, reverse=True):
        currency_info = []
        if data["value_idr"] > 0:
            currency_info.append(f"IDR {data['value_idr']:,.2f}")
        if data["value_usd"] > 0:
            currency_info.append(f"USD {data['value_usd']:,.2f}")

        if not currency_info:
            currency_info = ["No value"]

        currency_str = " / ".join(currency_info)
        print(f"  {cat}: {data['count']} items, {currency_str}")

    if not categories:
        print("  No data to display")


if __name__ == "__main__":
    main()
