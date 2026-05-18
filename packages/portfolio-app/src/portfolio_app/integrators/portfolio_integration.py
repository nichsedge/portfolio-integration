import json
import csv
import pendulum
from typing import List, Dict, Any
import os
from pathlib import Path
import re
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
from transform_core import get_data_dir, parse_usd, get_exchange_rate, FILTER_THRESHOLDS


STABLE_COINS = {"USDT", "USDC", "DAI", "FDUSD", "TUSD", "BUSD", "PYUSD", "USDP"}
GOLD_ASSETS = {"PAXG", "XAUT"}

VALID_CATEGORIES = {
    "Bank Account", "Digital Bank", "Stablecoin", "Money Market Fund",
    "SBN", "Corporate Bond", "P2P Lending",
    "US Stocks", "Indo Stocks", "Equity Fund",
    "Spot", "Staked", "Yield / LP",
    "Gold", "Silver"
}


def get_standard_category(category: str, asset: str) -> str:
    """Return the standardized category based on asset type and original category."""
    # Specific asset overrides take priority
    if asset in STABLE_COINS:
        return "Stablecoin"
    if asset in GOLD_ASSETS:
        return "Gold"
    
    # If already a valid standard category, keep it as is
    if category in VALID_CATEGORIES:
        return category
    
    # Transform legacy/raw categories
    if category == "Cryptocurrency":
        return "Spot"
    
    if "Staked" in category:
        return "Staked"
        
    # DeFi keywords (avoiding collision with Fixed Income terms like 'Lending')
    if any(term in category for term in ["Yield", "LP", "Protocol", "Vault", "Rewards"]):
        return "Yield / LP"
        
    # Specific check for crypto lending vs P2P lending
    if "Lending" in category and "P2P" not in category:
        return "Yield / LP"

    return category


def get_asset_class(category: str) -> str:
    """Group categories into broader asset classes for investment analysis."""
    mapping = {
        # Cash & Equivalents
        "Bank Account": "Cash & Equivalents",
        "Digital Bank": "Cash & Equivalents",
        "Stablecoin": "Cash & Equivalents",
        "Money Market Fund": "Cash & Equivalents",
        
        # Fixed Income
        "SBN": "Fixed Income",
        "Corporate Bond": "Fixed Income",
        "P2P Lending": "Fixed Income",
        
        # Equities
        "US Stocks": "Equities",
        "Indo Stocks": "Equities",
        "Equity Fund": "Equities",
        
        # Crypto
        "Spot": "Crypto",
        "Staked": "Crypto",
        "Yield / LP": "Crypto",
        
        # Commodities
        "Gold": "Commodities",
        "Silver": "Commodities",
    }
    
    # Handle legacy categories or variations
    if category not in mapping:
        if category in ["Cash", "Deposit"]: return "Cash & Equivalents"
        if category in ["Equity", "Indo Stocks"]: return "Equities"
        if category in ["Mutual Fund", "Equity Fund"]: return "Equities"
        if category in ["Bond", "SBN"]: return "Fixed Income"
        if category in ["P2P Syariah", "P2P Lending"]: return "Fixed Income"
        if category in ["Cryptocurrency", "Spot"]: return "Crypto"
        if category in ["DeFi Protocol", "DeFi Yield", "Yield / LP"]: return "Crypto"
        if category in ["DeFi Staked", "Staked"]: return "Crypto"
        
    return mapping.get(category, "Other")


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower())
    return cleaned.strip("-")


def enrich_account_identity(items: List[Dict[str, Any]]) -> None:
    """Attach account_name and account_key for downstream account linking."""
    for item in items:
        source = str(item.get("source") or "").strip() or "unknown"
        legacy_account = str(item.get("account") or "").strip()
        account_name = legacy_account or source

        source_key = _slugify(source) or "unknown"
        account_key_raw = legacy_account if legacy_account else account_name
        account_key = f"{source_key}:{_slugify(account_key_raw) or 'default'}"

        item["account_name"] = account_name
        item["account_key"] = account_key

        # Keep backward compatibility with older consumers.
        if not legacy_account:
            item["account"] = account_name


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

            bank_code = entry.get("bank", "Unknown")
            asset_name = bank_code
            if bank_code == "PRMT2":
                asset_name = "Ajaib RDN"
            elif bank_code == "JAGO1":
                asset_name = "Stockbit RDN"

            # Filter dust
            if currency == "IDR":
                if value_idr < FILTER_THRESHOLDS["IDR"]:
                    continue
            elif currency == "USD":
                if value_usd < FILTER_THRESHOLDS["USD"]:
                    continue

            standardized.append({
                "source": "KSEI",
                "category": "Bank Account",
                "asset": asset_name,
                "currency": currency,
                "quantity": entry.get("saldo", 0),
                "price": 1.0,
                "value_idr": value_idr,
                "value_usd": value_usd,
                "account": entry.get("rekening", ""),
                "details": f"Bank: {bank_code}, Account: {entry.get('rekening', '')}",
            })

    # Process equity
    if "equity" in ksei_data:
        for entry in ksei_data["equity"].get("data", []):
            # Filter dust
            value_idr = entry.get("nilaiInvestasi", 0)
            if value_idr < FILTER_THRESHOLDS["IDR"]:
                continue

            standardized.append({
                "source": "KSEI",
                "category": "Indo Stocks",
                "asset": entry.get("efek", "Unknown").split(" - ")[0],
                "currency": "IDR",
                "quantity": entry.get("jumlah", 0),
                "price": entry.get("harga", 0),
                "value_idr": value_idr,
                "value_usd": None,
                "account": entry.get("rekening", ""),
                "details": f"Stock: {entry.get('efek', '')}, Broker: {entry.get('partisipan', '')}",
            })

    # Process mutual funds
    if "mutual_fund" in ksei_data:
        for entry in ksei_data["mutual_fund"].get("data", []):
            asset_name = entry.get("efek", "Unknown")
            category = "Equity Fund"
            if any(term in asset_name for term in ["Bond", "Fixed Income", "SBN", "Obligasi"]):
                # Check if it's explicitly a government-related fund
                if any(term in asset_name for term in ["SBN", "Sovereign", "Government", "SST", "INDON", "INDOGB"]):
                    category = "SBN"
                else:
                    # Default for general bond funds
                    category = "Corporate Bond"
            elif any(term in asset_name for term in ["Pasar Uang", "Money Market", "Liquidity"]):
                category = "Money Market Fund"
            
            # Filter dust
            value_idr = entry.get("nilaiInvestasi", 0)
            if value_idr < FILTER_THRESHOLDS["IDR"]:
                continue

            standardized.append({
                "source": "KSEI",
                "category": category,
                "asset": asset_name,
                "currency": "IDR",
                "quantity": entry.get("jumlah", 0),
                "price": value_idr / entry.get("jumlah") if entry.get("jumlah") else 0,
                "value_idr": value_idr,
                "value_usd": None,
                "account": entry.get("rekening", ""),
                "details": f"Fund: {entry.get('efek', '')}, Manager: {entry.get('partisipan', '')}",
            })

    # Process bonds
    if "bond" in ksei_data:
        for entry in ksei_data["bond"].get("data", []):
            # Filter dust
            value_idr = entry.get("nilaiInvestasi", 0)
            if value_idr < FILTER_THRESHOLDS["IDR"]:
                continue

            asset_name = entry.get("efek", "Unknown")
            category = "SBN"
            # If it doesn't look like a government bond, categorize as Corporate
            if not any(term in asset_name for term in ["ORI", "SR", "ST", "FR", "SBN", "PBS", "INDON", "INDOGB"]):
                category = "Corporate Bond"

            standardized.append({
                "source": "KSEI",
                "category": category,
                "asset": asset_name,
                "currency": "IDR",
                "quantity": entry.get("jumlah", 0),
                "price": value_idr / entry.get("jumlah") if entry.get("jumlah") else 0,
                "value_idr": value_idr,
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
        if usd_value >= FILTER_THRESHOLDS["USD"]:
            symbol = token.get("symbol", "Unknown")
            amount_str = token.get("quantity") or token.get("amount") or "0"
            if isinstance(amount_str, str):
                amount_str = amount_str.replace(",", "")
            
            try:
                amount = float(amount_str)
            except ValueError:
                amount = 0.0

            if symbol not in token_aggregation:
                token_aggregation[symbol] = {
                    "source": "EVM Wallet",
                    "category": get_standard_category("Cryptocurrency", symbol),
                    "asset": symbol,
                    "currency": "USD",
                    "quantity": 0.0,
                    "price": token.get("price", 0),
                    "value_idr": None,
                    "value_usd": 0.0,
                    "account": "DeBank Wallet",
                    "details": "",
                }
            
            token_aggregation[symbol]["quantity"] += amount
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
                if usd_value >= FILTER_THRESHOLDS["USD"]:
                    pool = pos.get("pool", "Unknown Pool")
                    pos_type = pos.get("type", "Protocol")
                    
                    if pos_type == "Staked":
                        category = "Staked"
                    else:
                        category = "Yield / LP"

                    asset_name = f"{protocol_name} - {pool}"
                    if pos_type and pos_type not in ["Other", "Protocol"]:
                        asset_name = f"{protocol_name} ({pos_type}) - {pool}"
                    asset_name = asset_name.replace("\n", " ").strip()

                    tokens = pos.get("tokens", [])
                    token_list = [t.get("balance", "").replace("\n", " ").strip() for t in tokens if t.get("balance")]
                    token_details = ", ".join(token_list)

                    standardized.append({
                        "source": "EVM Wallet",
                        "category": category,
                        "asset": asset_name,
                        "currency": "USD",
                        "quantity": 1.0,
                        "price": usd_value,
                        "value_idr": None,
                        "value_usd": usd_value,
                        "account": "DeBank Protocol",
                        "details": f"Protocol: {protocol_name}, Position: {pos_type}, Tokens: {token_details}",
                    })
        else:
            usd_value = parse_usd(protocol.get("value") or "0")
            if usd_value >= FILTER_THRESHOLDS["USD"]:
                standardized.append({
                    "source": "EVM Wallet",
                    "category": "Yield / LP",
                    "asset": protocol_name,
                    "currency": "USD",
                    "quantity": 1.0,
                    "price": usd_value,
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
        
        if value_usd >= FILTER_THRESHOLDS["USD"]:
            standardized.append({
                "source": "EVM Wallet",
                "category": "Spot",
                "asset": nft.get("collection", "Unknown"),
                "currency": "USD",
                "quantity": amount,
                "price": avg_price,
                "value_idr": None,
                "value_usd": value_usd if value_usd > 0 else avg_price,
                "account": "DeBank NFT",
                "details": f"Collection: {nft.get('collection')}",
            })

    return standardized


def standardize_binance_data(binance_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert Binance data to standardized format."""
    standardized = []
    for asset in binance_data.get("assets", []):
        asset_symbol = asset.get("symbol", "Unknown")
        price_usd = asset.get("price_usd", 0)
        amount = asset.get("quantity") or asset.get("amount") or 0
        value_usd = asset.get("value_usd", 0)

        # Filter dust
        if value_usd < FILTER_THRESHOLDS["USD"]:
            continue

        standardized.append({
            "source": "Binance",
            "category": get_standard_category("Cryptocurrency", asset_symbol),
            "asset": asset_symbol,
            "currency": "USD",
            "quantity": amount,
            "price": price_usd,
            "value_idr": None,
            "value_usd": value_usd,
            "account": "Binance Main Account",
            "details": "",
        })
    return standardized


def standardize_alchemy_data(alchemy_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert Alchemy curated data to standardized format."""
    standardized = []
    for asset in alchemy_data.get("assets", []):
        asset_symbol = asset.get("symbol", "Unknown")
        name = asset.get("name", "Unknown Token")
        amount = asset.get("quantity") or asset.get("balance") or 0
        value_usd = asset.get("value_usd", 0)

        # Filter dust
        if value_usd < FILTER_THRESHOLDS["USD"]:
            continue

        standardized.append({
            "source": "SOL Wallet",
            "category": get_standard_category("Cryptocurrency", asset_symbol),
            "asset": asset_symbol,
            "currency": "USD",
            "quantity": amount,
            "price": asset.get("price_usd") or (value_usd / amount if amount else 0),
            "value_idr": None,
            "value_usd": value_usd,
            "account": "Alchemy Wallet",
            "details": f"Token: {name}, Network: {asset.get('network', 'Unknown')}",
        })
    return standardized


def standardize_solana_data(solana_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert Solana curated data to standardized format."""
    standardized = []
    for asset in solana_data.get("assets", []):
        asset_symbol = asset.get("symbol", "Unknown")
        name = asset.get("name", "Unknown Token")
        amount = asset.get("quantity") or asset.get("amount") or 0
        value_usd = asset.get("value_usd", 0)

        # Filter dust
        if value_usd < FILTER_THRESHOLDS["USD"]:
            continue

        standardized.append({
            "source": "Solana",
            "category": get_standard_category("Cryptocurrency", asset_symbol),
            "asset": asset_symbol,
            "currency": "USD",
            "quantity": amount,
            "price": asset.get("price", 0),
            "value_idr": None,
            "value_usd": value_usd,
            "account": "Solana Wallet",
            "details": f"Token: {name}",
        })
    return standardized


def standardize_hyperliquid_data(hl_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert Hyperliquid curated data to standardized format."""
    standardized = []
    for pos in hl_data.get("vault_positions", []):
        value_usd = pos.get("value_usd", 0)
        
        # Filter dust
        if value_usd < FILTER_THRESHOLDS["USD"]:
            continue

        standardized.append({
            "source": "Hyperliquid",
            "category": get_standard_category(pos.get("category", "Vault Position"), pos.get("asset", "")),
            "asset": pos.get("asset", "Unknown"),
            "currency": "USD",
            "quantity": pos.get("amount") or pos.get("quantity") or 1.0,
            "price": pos.get("price_usd") or (value_usd / pos.get("amount", 1) if pos.get("amount") else 0),
            "value_idr": None,
            "value_usd": value_usd,
            "account": pos.get("account", "Hyperliquid"),
            "details": pos.get("details", ""),
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
            "quantity": row.get("quantity") or row.get("amount"),
            "price": row.get("price"),
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
        if any(term in cat for term in ["Debt", "Borrow", "Liabilities"]):
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
        if any(term in cat for term in ["Debt", "Borrow", "Liabilities"]):
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
    parser.add_argument("--skip-manual", action="store_true", help="Skip loading manual balances")
    args = parser.parse_args()

    td = args.date or pendulum.now().format("YYYY-MM-DD")
    exchange_rate = get_exchange_rate()

    data_dir = get_data_dir()
    ksei_raw_path = data_dir / f"{td}_raw_ksei.json"
    debank_raw_path = data_dir / f"{td}_raw_debank.json"
    binance_raw_path = data_dir / f"{td}_raw_binance.json"
    alchemy_curated_path = data_dir / f"{td}_curated_alchemy.json"
    solana_curated_path = data_dir / f"{td}_curated_solana.json"
    hyperliquid_curated_path = data_dir / f"{td}_curated_hyperliquid.json"
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
                    for field in ["quantity", "amount", "price", "value_idr", "value_usd"]:
                        if row.get(field):
                            try: row[field] = float(row[field])
                            except: row[field] = 0.0
                        else: row[field] = None
                    manual_raw.append(row)
            manual_standardized = standardize_manual_data(manual_raw)
            manual_loaded = True
        except Exception as e: print(f"Error loading Manual: {e}")

    solana_loaded = False
    solana_standardized = []
    if solana_curated_path.exists():
        try:
            with open(solana_curated_path, "r") as f:
                solana_standardized = standardize_solana_data(json.load(f))
            solana_loaded = True
        except Exception as e: print(f"Error loading Solana: {e}")

    hyperliquid_loaded = False
    hyperliquid_standardized = []
    if hyperliquid_curated_path.exists():
        try:
            with open(hyperliquid_curated_path, "r") as f:
                hyperliquid_standardized = standardize_hyperliquid_data(json.load(f))
            hyperliquid_loaded = True
        except Exception as e: print(f"Error loading Hyperliquid: {e}")

    # Condition: manual balances are only for "today" by default, unless it's a specific date run
    # Actually, the user says they are always latest, so we should skip them if td != today
    today_str = pendulum.now().format("YYYY-MM-DD")
    if args.skip_manual:
        if manual_loaded:
            print(f"ℹ Skipping manual balances for backfill/historical date {td}")
            manual_loaded = False
            manual_standardized = []

    all_data = (
        ksei_standardized
        + debank_standardized
        + binance_standardized
        + alchemy_standardized
        + solana_standardized
        + hyperliquid_standardized
        + manual_standardized
    )

    all_data.sort(key=lambda x: (str(x.get("category") or ""), str(x.get("source") or ""), str(x.get("asset") or "")))

    # Add asset class to each item
    for item in all_data:
        item["asset_class"] = get_asset_class(item.get("category", "Other"))

    # Add stable account identity fields for consumers that can link holdings to accounts.
    enrich_account_identity(all_data)

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
    fieldnames = [
        "source",
        "category",
        "asset_class",
        "asset",
        "currency",
        "quantity",
        "price",
        "value_idr",
        "value_usd",
        "account_key",
        "account_name",
        "account",
        "details",
    ]
    with open(output_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_data)

    # Generate JSON Snapshot
    generate_snapshot_json(td, all_data, exchange_rate, output_json_path)

    # Print Summary
    sources_info = []
    if ksei_loaded: sources_info.append(f"KSEI ({len(ksei_standardized)} items)")
    if debank_loaded: sources_info.append(f"EVM Wallet ({len(debank_standardized)} items)")
    if binance_loaded: sources_info.append(f"Binance ({len(binance_standardized)} items)")
    if alchemy_loaded: sources_info.append(f"SOL Wallet ({len(alchemy_standardized)} items)")
    if solana_loaded: sources_info.append(f"Solana ({len(solana_standardized)} items)")
    if hyperliquid_loaded: sources_info.append(f"Hyperliquid ({len(hyperliquid_standardized)} items)")
    if manual_loaded: sources_info.append(f"Manual ({len(manual_standardized)} items)")

    print_rich_summary(td, all_data, exchange_rate, sources_info)
    print(f"Output files:\n  - CSV: {output_csv_path}\n  - JSON: {output_json_path}")


if __name__ == "__main__":
    main()
