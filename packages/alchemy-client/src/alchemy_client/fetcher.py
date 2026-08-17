"""Alchemy Client - Fetch token holdings from Alchemy API."""

import os
import json
import requests
import pendulum
from pathlib import Path
from dotenv import load_dotenv


def main(output_dir=None):
    """Main entry point for the Alchemy fetcher.

    Args:
        output_dir: Directory to save output file. If None, uses PORTFOLIO_DATA_DIR
                    env var or current directory.
    """
    try:
        load_dotenv()
    except ImportError:
        print("Warning: python-dotenv not installed. Using environment variables only.")

    wallet_address = os.getenv("SOL_ADDRESS")
    alchemy_api_key = os.getenv("ALCHEMY_API_KEY")

    if not wallet_address:
        print("Error: SOL_ADDRESS not found in environment")
        return

    if not alchemy_api_key:
        print("Error: ALCHEMY_API_KEY not found in environment")
        return

    # Use provided output_dir or environment variable or current directory
    if output_dir is None:
        output_dir = os.getenv("PORTFOLIO_DATA_DIR", ".")

    url = (
        f"https://api.g.alchemy.com/data/v1/{alchemy_api_key}/assets/tokens/by-address"
    )

    payload = {
        "addresses": [{"address": wallet_address, "networks": ["solana-mainnet"]}]
    }
    headers = {"Content-Type": "application/json"}

    print(f"Fetching holdings for wallet: {wallet_address}")

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error during API request: {e}")
        return
    except (KeyError, TypeError) as e:
        print(f"Error parsing JSON data: {e}")
        return

    # Process the data to get token holdings
    tokens = data.get("data", {}).get("tokens", [])

    results = []
    for token in tokens:
        # Parse token balance from hex to decimal
        raw_balance = int(token.get("tokenBalance") or "0", 16)

        # Get metadata
        meta = token.get("tokenMetadata", {}) or {}
        decimals = meta.get("decimals", 9) or 9

        # Calculate human-readable balance
        balance_adj = raw_balance / (10**decimals)

        # Get USD price if available
        value_usd = None
        if token.get("tokenPrices"):
            for price in token["tokenPrices"]:
                if price.get("currency") == "usd":
                    price_value = float(price.get("value") or 0)
                    value_usd = balance_adj * price_value
                    break

        results.append(
            {
                "address": token.get("address"),
                "network": token.get("network"),
                "tokenAddress": token.get("tokenAddress"),
                "balance": balance_adj,
                "symbol": meta.get("symbol") or "SOL",
                "name": meta.get("name"),
                "decimals": decimals,
                "value_usd": value_usd,
            }
        )

    # Sort by value_usd if available
    results.sort(key=lambda x: x.get("value_usd") or 0, reverse=True)

    # Output summary
    print("\n--- Alchemy Holdings ---")
    print(f"{'Symbol':<15} {'Amount':>15} {'Value (USD)':>15}")
    print("-" * 50)
    for r in results:
        symbol = r.get("symbol") or "SOL"
        balance = r.get("balance") or 0
        value = r.get("value_usd") or 0
        print(f"{symbol:<15} {balance:>15,.4f} {value:>15,.2f}")

    # Save to file
    current_date = pendulum.now().to_date_string()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    output_file = output_path / f"{current_date}_raw_alchemy.json"

    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved results to {output_file}")


if __name__ == "__main__":
    main()
