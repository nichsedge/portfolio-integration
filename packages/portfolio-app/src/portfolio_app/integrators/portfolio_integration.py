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

    # Process wallets
    for wallet in debank_data.get("wallets", []):
        usd_value = parse_usd(wallet.get("USD Value", 0))
        standardized.append(
            {
                "source": "DeBank",
                "category": "Crypto Wallet",
                "asset": wallet.get("chain", "Unknown"),
                "currency": "USD",
                "amount": 1,  # Wallets don't have amount, just value
                "value_idr": None,
                "value_usd": usd_value,
                "account": wallet.get("Address", ""),
                "details": f"Wallet: {wallet.get('name', '')}, Chain: {wallet.get('chain', '')}",
            }
        )

    # Process protocols
    for protocol in debank_data.get("protocols", []):
        protocol_name = (
            protocol.get("name") or f"Protocol {protocol.get('id', 'Unknown')}"
        )
        protocol_chain = protocol.get("chain") or "Unknown"
        protocol_value = parse_usd(protocol.get("usdValue", 0))

        # If protocol has data entries, process them
        for entry in protocol.get("data", []):
            usd_value = parse_usd(entry.get("USD Value", 0))
            if usd_value >= 10:
                token = entry.get("token", {})
                standardized.append(
                    {
                        "source": "DeBank",
                        "category": "DeFi Protocol",
                        "asset": token.get("symbol", "Unknown"),
                        "currency": "USD",
                        "amount": float(entry.get("amount", 0)),
                        "value_idr": None,
                        "value_usd": usd_value,
                        "account": f"{protocol_name} on {protocol_chain}",
                        "details": f"Protocol: {protocol_name}, Chain: {protocol_chain}, Token: {token.get('symbol', '')}",
                    }
                )

        # If protocol has no data entries but has value, add it as a single entry
        if not protocol.get("data") and protocol_value >= 10:
            standardized.append(
                {
                    "source": "DeBank",
                    "category": "DeFi Protocol",
                    "asset": "Unknown",
                    "currency": "USD",
                    "amount": 0.0,
                    "value_idr": None,
                    "value_usd": protocol_value,
                    "account": f"{protocol_name} on {protocol_chain}",
                    "details": f"Protocol: {protocol_name}, Chain: {protocol_chain}",
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
                "category": "Cryptocurrency",
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
                "category": "Cryptocurrency",
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
    output_csv_path = data_dir / f"{td}_portfolio.csv"

    # Load KSEI and DeBank raw data
    with open(ksei_raw_path, "r", encoding="utf-8") as f:
        ksei_raw = json.load(f)

    with open(debank_raw_path, "r", encoding="utf-8") as f:
        debank_raw = json.load(f)

    # Try to load Binance data (optional)
    try:
        with open(binance_raw_path, "r", encoding="utf-8") as f:
            binance_raw = json.load(f)
        binance_clean = binance_raw
        binance_standardized = standardize_binance_data(binance_clean)
        binance_loaded = True
    except FileNotFoundError:
        print("Binance data not found, skipping...")
        binance_standardized = []
        binance_loaded = False

    # Try to load Alchemy data (optional)
    try:
        with open(alchemy_curated_path, "r", encoding="utf-8") as f:
            alchemy_curated = json.load(f)
        alchemy_standardized = standardize_alchemy_data(alchemy_curated)
        alchemy_loaded = True
    except FileNotFoundError:
        print("Alchemy curated data not found, skipping...")
        alchemy_standardized = []
        alchemy_loaded = False

    # Clean and process data
    ksei_clean = clean_json(ksei_raw)
    debank_clean = extract_relevant(debank_raw)

    # Standardize data
    ksei_standardized = standardize_ksei_data(ksei_clean)
    debank_standardized = standardize_debank_data(debank_clean)

    # Combine all data
    all_data = (
        ksei_standardized
        + debank_standardized
        + binance_standardized
        + alchemy_standardized
    )

    # Sort by source, category, and asset
    all_data.sort(
        key=lambda x: (
            str(x.get("source") or ""),
            str(x.get("category") or ""),
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
    sources_parts = [
        f"KSEI ({len(ksei_standardized)} items)",
        f"DeBank ({len(debank_standardized)} items)",
    ]
    if binance_loaded:
        sources_parts.append(f"Binance ({len(binance_standardized)} items)")
    if alchemy_loaded:
        sources_parts.append(f"Alchemy ({len(alchemy_standardized)} items)")
    print(f"Sources: {', '.join(sources_parts)}")

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


if __name__ == "__main__":
    main()
