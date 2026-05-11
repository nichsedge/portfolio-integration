import json
import csv
import pendulum
from typing import List, Dict, Any
import os
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

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
from transform_core import get_data_dir, parse_usd, get_exchange_rate


STABLE_COINS = {"USDT", "USDC", "DAI", "FDUSD", "TUSD", "BUSD", "PYUSD", "USDP"}
GOLD_ASSETS = {"PAXG", "XAUT"}


def get_standard_category(category: str, asset: str) -> str:
    """Return the correct category, separating stablecoins and gold from crypto/defi."""
    if category in ["Cryptocurrency", "DeFi Protocol"]:
        if asset in STABLE_COINS:
            return "Cash"
        if asset in GOLD_ASSETS:
            return "Gold"
    return category


def get_asset_class(category: str) -> str:
    """Group categories into broader asset classes for investment analysis."""
    mapping = {
        "Cash": "Cash & Stables",
        "Deposit": "Cash & Stables",
        "Equity": "Equities",
        "Mutual Fund": "Equities",
        "Bond": "Fixed Income",
        "P2P Syariah": "Fixed Income",
        "Cryptocurrency": "Crypto",
        "DeFi Protocol": "Crypto",
        "DeFi Yield": "Crypto",
        "DeFi Staked": "Crypto",
        "DeFi Lending": "Crypto",
        "DeFi Debt": "Crypto",
        "DeFi Rewards": "Crypto",
        "DeFi Deposit": "Crypto",
        "Gold": "Commodities",
        "NFT": "Collectibles",
    }
    return mapping.get(category, "Other")


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
                value_usd = entry.get("saldo", 0)

            standardized.append({
                "source": "KSEI",
                "category": "Cash",
                "asset": entry.get("bank", "Unknown"),
                "currency": currency,
                "amount": entry.get("saldo", 0),
                "value_idr": value_idr,
                "value_usd": value_usd,
                "account": entry.get("rekening", ""),
                "details": f"Bank: {entry.get('bank', '')}, Account: {entry.get('rekening', '')}",
            })

    # Process equity
    if "equity" in ksei_data:
        for entry in ksei_data["equity"].get("data", []):
            standardized.append({
                "source": "KSEI",
                "category": "Equity",
                "asset": entry.get("efek", "Unknown").split(" - ")[0],
                "currency": "IDR",
                "amount": entry.get("jumlah", 0),
                "value_idr": entry.get("nilaiInvestasi", 0),
                "value_usd": None,
                "account": entry.get("rekening", ""),
                "details": f"Stock: {entry.get('efek', '')}, Broker: {entry.get('partisipan', '')}, Price: {entry.get('harga', 0)}",
            })

    # Process mutual funds
    if "mutual_fund" in ksei_data:
        for entry in ksei_data["mutual_fund"].get("data", []):
            asset_name = entry.get("efek", "Unknown")
            category = "Mutual Fund"
            if "Bond" in asset_name or "Fixed Income" in asset_name:
                category = "Bond"
            
            standardized.append({
                "source": "KSEI",
                "category": category,
                "asset": asset_name,
                "currency": "IDR",
                "amount": entry.get("jumlah", 0),
                "value_idr": entry.get("nilaiInvestasi", 0),
                "value_usd": None,
                "account": entry.get("rekening", ""),
                "details": f"Fund: {entry.get('efek', '')}, Manager: {entry.get('partisipan', '')}",
            })

    # Process bonds
    if "bond" in ksei_data:
        for entry in ksei_data["bond"].get("data", []):
            standardized.append({
                "source": "KSEI",
                "category": "Bond",
                "asset": entry.get("efek", "Unknown"),
                "currency": "IDR",
                "amount": entry.get("jumlah", 0),
                "value_idr": entry.get("nilaiInvestasi", 0),
                "value_usd": None,
                "account": entry.get("rekening", ""),
                "details": f"Bond: {entry.get('efek', '')}, Issuer: {entry.get('partisipan', '')}",
            })

    return standardized


def standardize_debank_data(debank_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert DeBank data to standardized format."""
    standardized = []

    # Process wallet tokens
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
                    
                    category = "DeFi Protocol"
                    if pos_type == "Yield": category = "DeFi Yield"
                    elif pos_type == "Staked": category = "DeFi Staked"
                    elif pos_type == "Lending": category = "DeFi Lending"
                    elif pos_type == "Borrow": category = "DeFi Debt"
                    elif pos_type == "Rewards": category = "DeFi Rewards"
                    elif pos_type == "Deposit": category = "DeFi Deposit"

                    asset_name = f"{protocol_name} - {pool}"
                    if pos_type and pos_type not in ["Other", "Protocol"]:
                        asset_name = f"{protocol_name} ({pos_type}) - {pool}"
                    asset_name = asset_name.replace("\n", " ").strip()

                    tokens = pos.get("tokens", [])
                    token_list = [t.get("balance", "").replace("\n", " ").strip() for t in tokens if t.get("balance")]
                    token_details = ", ".join(token_list)

                    standardized.append({
                        "source": "DeBank",
                        "category": category,
                        "asset": asset_name,
                        "currency": "USD",
                        "amount": 1.0,
                        "value_idr": None,
                        "value_usd": usd_value,
                        "account": "DeBank Protocol",
                        "details": f"Protocol: {protocol_name}, Position: {pos_type}, Tokens: {token_details}",
                    })
        else:
            usd_value = parse_usd(protocol.get("value") or "0")
            if usd_value > 0:
                standardized.append({
                    "source": "DeBank",
                    "category": "DeFi Protocol",
                    "asset": protocol_name,
                    "currency": "USD",
                    "amount": 1.0,
                    "value_idr": None,
                    "value_usd": usd_value,
                    "account": "DeBank Protocol",
                    "details": f"Protocol: {protocol_name} (Summary)",
                })

    # Process NFTs
    for nft in debank_data.get("nfts", []):
        avg_price = parse_usd(nft.get("avg_price") or "0")
        amount_str = nft.get("amount") or "1"
        try:
            amount = float(amount_str.replace(",", ""))
        except ValueError:
            amount = 1.0
            
        value_usd = avg_price * amount if avg_price > 0 else 0
        
        if value_usd > 0 or avg_price > 0:
            standardized.append({
                "source": "DeBank",
                "category": "NFT",
                "asset": nft.get("collection", "Unknown"),
                "currency": "USD",
                "amount": amount,
                "value_idr": None,
                "value_usd": value_usd if value_usd > 0 else avg_price,
                "account": "DeBank NFT",
                "details": f"Collection: {nft.get('collection')}, Avg Price: {nft.get('avg_price')}",
            })

    return standardized


def standardize_binance_data(binance_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert Binance data to standardized format."""
    standardized = []
    for asset in binance_data.get("assets", []):
        asset_symbol = asset.get("symbol", "Unknown")
        price_usd = asset.get("price_usd", 0)
        amount = asset.get("amount", 0)
        value_usd = asset.get("value_usd", 0)

        standardized.append({
            "source": "Binance",
            "category": get_standard_category("Cryptocurrency", asset_symbol),
            "asset": asset_symbol,
            "currency": "USD",
            "amount": amount,
            "value_idr": None,
            "value_usd": value_usd,
            "account": "Binance Main Account",
            "details": f"Price: ${price_usd:,.2f}, Amount: {amount:,.8f}",
        })
    return standardized


def standardize_alchemy_data(alchemy_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert Alchemy curated data to standardized format."""
    standardized = []
    for asset in alchemy_data.get("assets", []):
        asset_symbol = asset.get("symbol", "Unknown")
        name = asset.get("name", "Unknown Token")
        amount = asset.get("balance", 0)
        value_usd = asset.get("value_usd", 0)

        standardized.append({
            "source": "Alchemy",
            "category": get_standard_category("Cryptocurrency", asset_symbol),
            "asset": asset_symbol,
            "currency": "USD",
            "amount": amount,
            "value_idr": None,
            "value_usd": value_usd,
            "account": "Alchemy Wallet",
            "details": f"Token: {name}, Network: {asset.get('network', 'Unknown')}, Amount: {amount:,.8f}",
        })
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
            "amount": row.get("amount"),
            "value_idr": row.get("value_idr"),
            "value_usd": row.get("value_usd"),
            "account": row.get("account", ""),
            "details": row.get("details", "")
        })
    return standardized


def generate_snapshot_json(td: str, all_data: List[Dict[str, Any]], exchange_rate: float, output_path: Path):
    """Generate a structured JSON snapshot for rich integration."""
    
    # Calculate totals
    total_assets_idr = 0.0
    total_liabilities_idr = 0.0
    
    # Group by category and asset class
    categories = {}
    asset_classes = {}
    
    for item in all_data:
        # Calculate IDR value for current item
        val_idr = item.get("value_idr")
        if val_idr is None:
            val_idr = (item.get("value_usd") or 0.0) * exchange_rate
            
        # Add to totals
        cat = item["category"]
        if "Debt" in cat or "Borrow" in cat or "Liabilities" in cat:
            total_liabilities_idr += val_idr
        else:
            total_assets_idr += val_idr
            
        # Category breakdown
        if cat not in categories:
            categories[cat] = {"value_idr": 0.0, "count": 0}
        categories[cat]["value_idr"] += val_idr
        categories[cat]["count"] += 1
        
        # Asset class breakdown
        aclass = get_asset_class(cat)
        if aclass not in asset_classes:
            asset_classes[aclass] = {"value_idr": 0.0, "count": 0}
        asset_classes[aclass]["value_idr"] += val_idr
        asset_classes[aclass]["count"] += 1

    net_worth_idr = total_assets_idr - total_liabilities_idr
    
    # Format for JSON
    snapshot = {
        "metadata": {
            "date": td,
            "exchange_rate": exchange_rate,
            "total_items": len(all_data),
            "generated_at": pendulum.now().to_iso8601_string()
        },
        "totals": {
            "net_worth_idr": round(net_worth_idr, 2),
            "net_worth_usd": round(net_worth_idr / exchange_rate, 2),
            "total_assets_idr": round(total_assets_idr, 2),
            "total_liabilities_idr": round(total_liabilities_idr, 2)
        },
        "allocation": {
            "by_category": [
                {
                    "category": k, 
                    "value_idr": round(v["value_idr"], 2), 
                    "percentage": round(v["value_idr"] / total_assets_idr * 100, 2) if total_assets_idr > 0 else 0,
                    "count": v["count"]
                }
                for k, v in sorted(categories.items(), key=lambda x: x[1]["value_idr"], reverse=True)
            ],
            "by_asset_class": [
                {
                    "asset_class": k, 
                    "value_idr": round(v["value_idr"], 2), 
                    "percentage": round(v["value_idr"] / total_assets_idr * 100, 2) if total_assets_idr > 0 else 0,
                    "count": v["count"]
                }
                for k, v in sorted(asset_classes.items(), key=lambda x: x[1]["value_idr"], reverse=True)
            ]
        },
        "holdings": all_data
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)


def print_rich_summary(td: str, all_data: List[Dict[str, Any]], exchange_rate: float, sources_info: List[str]):
    """Print a beautiful summary using Rich."""
    console = Console()
    
    # Calculate totals
    total_assets_idr = 0.0
    total_liabilities_idr = 0.0
    asset_classes = {}
    
    for item in all_data:
        val_idr = item.get("value_idr")
        if val_idr is None:
            val_idr = (item.get("value_usd") or 0.0) * exchange_rate
        
        cat = item["category"]
        if "Debt" in cat or "Borrow" in cat:
            total_liabilities_idr += val_idr
        else:
            total_assets_idr += val_idr
            
        aclass = get_asset_class(cat)
        if aclass not in asset_classes:
            asset_classes[aclass] = {"value_idr": 0.0, "count": 0}
        asset_classes[aclass]["value_idr"] += val_idr
        asset_classes[aclass]["count"] += 1

    net_worth_idr = total_assets_idr - total_liabilities_idr
    
    # Header Panel
    console.print(Panel(
        f"[bold cyan]Portfolio Snapshot[/] - [yellow]{td}[/]\n"
        f"[dim]Exchange Rate: 1 USD = {exchange_rate:,.2f} IDR[/]",
        box=box.DOUBLE, expand=False
    ))
    
    # Net Worth Summary
    console.print(f"[bold green]Net Worth: Rp {net_worth_idr:,.0f}[/] "
                  f"([dim]${net_worth_idr / exchange_rate:,.2f}[/])")
    console.print(f"  Assets: Rp {total_assets_idr:,.0f}")
    if total_liabilities_idr > 0:
        console.print(f"  Liabilities: [red]Rp {total_liabilities_idr:,.0f}[/]")
    console.print("")
    
    # Asset Class Table
    table = Table(title="Asset Allocation", box=box.ROUNDED)
    table.add_column("Asset Class", style="cyan")
    table.add_column("Value (IDR)", justify="right", style="green")
    table.add_column("Allocation", justify="right", style="yellow")
    table.add_column("Items", justify="center")
    
    for aclass, data in sorted(asset_classes.items(), key=lambda x: x[1]["value_idr"], reverse=True):
        percentage = (data["value_idr"] / total_assets_idr * 100) if total_assets_idr > 0 else 0
        table.add_row(
            aclass,
            f"{data['value_idr']:,.0f}",
            f"{percentage:.1f}%",
            str(data["count"])
        )
    
    console.print(table)
    
    # Sources Info
    console.print(f"\n[bold blue]Data Sources:[/]")
    for source in sources_info:
        console.print(f"  • {source}")
    console.print("-" * 40 + "\n")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Date in YYYY-MM-DD format")
    args = parser.parse_args()

    td = args.date or pendulum.now().format("YYYY-MM-DD")
    exchange_rate = get_exchange_rate()

    data_dir = get_data_dir()
    ksei_raw_path = data_dir / f"{td}_raw_ksei.json"
    debank_raw_path = data_dir / f"{td}_raw_debank.json"
    binance_raw_path = data_dir / f"{td}_raw_binance.json"
    alchemy_curated_path = data_dir / f"{td}_curated_alchemy.json"
    manual_csv_path = data_dir / "_manual_balances.csv"
    
    output_csv_path = data_dir / f"{td}_portfolio.csv"
    output_json_path = data_dir / f"{td}_snapshot.json"

    # Loading Data
    ksei_loaded = False
    ksei_standardized = []
    if ksei_raw_path.exists():
        try:
            with open(ksei_raw_path, "r") as f:
                ksei_clean = clean_json(json.load(f))
            ksei_standardized = standardize_ksei_data(ksei_clean)
            ksei_loaded = True
        except Exception as e: print(f"Error loading KSEI: {e}")

    debank_loaded = False
    debank_standardized = []
    if debank_raw_path.exists():
        try:
            with open(debank_raw_path, "r") as f:
                debank_clean = extract_relevant(json.load(f))
            debank_standardized = standardize_debank_data(debank_clean)
            debank_loaded = True
        except Exception as e: print(f"Error loading DeBank: {e}")

    binance_loaded = False
    binance_standardized = []
    if binance_raw_path.exists():
        try:
            with open(binance_raw_path, "r") as f:
                binance_standardized = standardize_binance_data(json.load(f))
            binance_loaded = True
        except Exception as e: print(f"Error loading Binance: {e}")

    alchemy_loaded = False
    alchemy_standardized = []
    if alchemy_curated_path.exists():
        try:
            with open(alchemy_curated_path, "r") as f:
                alchemy_standardized = standardize_alchemy_data(json.load(f))
            alchemy_loaded = True
        except Exception as e: print(f"Error loading Alchemy: {e}")

    manual_loaded = False
    manual_standardized = []
    if manual_csv_path.exists():
        try:
            with open(manual_csv_path, "r") as f:
                reader = csv.DictReader(f)
                manual_raw = []
                for row in reader:
                    for field in ["amount", "value_idr", "value_usd"]:
                        if row.get(field):
                            try: row[field] = float(row[field])
                            except: row[field] = 0.0
                        else: row[field] = None
                    manual_raw.append(row)
            manual_standardized = standardize_manual_data(manual_raw)
            manual_loaded = True
        except Exception as e: print(f"Error loading Manual: {e}")

    all_data = (
        ksei_standardized
        + debank_standardized
        + binance_standardized
        + alchemy_standardized
        + manual_standardized
    )

    all_data.sort(key=lambda x: (str(x.get("category") or ""), str(x.get("source") or ""), str(x.get("asset") or "")))

    # Add asset class to each item
    for item in all_data:
        item["asset_class"] = get_asset_class(item.get("category", "Other"))

    # Fill in missing currency values using exchange rate
    for item in all_data:
        v_idr = item.get("value_idr")
        v_usd = item.get("value_usd")
        
        if v_idr is not None and v_usd is None:
            item["value_usd"] = round(v_idr / exchange_rate, 2)
        elif v_usd is not None and v_idr is None:
            item["value_idr"] = round(v_usd * exchange_rate, 2)
        elif v_idr is None and v_usd is None:
            item["value_idr"] = 0.0
            item["value_usd"] = 0.0

    # Write CSV
    fieldnames = ["source", "category", "asset_class", "asset", "currency", "amount", "value_idr", "value_usd", "account", "details"]
    with open(output_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_data)

    # Generate JSON Snapshot
    generate_snapshot_json(td, all_data, exchange_rate, output_json_path)

    # Print Summary
    sources_info = []
    if ksei_loaded: sources_info.append(f"KSEI ({len(ksei_standardized)} items)")
    if debank_loaded: sources_info.append(f"DeBank ({len(debank_standardized)} items)")
    if binance_loaded: sources_info.append(f"Binance ({len(binance_standardized)} items)")
    if alchemy_loaded: sources_info.append(f"Alchemy ({len(alchemy_standardized)} items)")
    if manual_loaded: sources_info.append(f"Manual ({len(manual_standardized)} items)")

    print_rich_summary(td, all_data, exchange_rate, sources_info)
    print(f"Output files:\n  - CSV: {output_csv_path}\n  - JSON: {output_json_path}")


if __name__ == "__main__":
    main()
