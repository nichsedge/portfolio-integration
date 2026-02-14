import os
import json
import requests
import time
from solana.rpc.api import Client
from solders.pubkey import Pubkey
from solana.rpc.types import TokenAccountOpts

# Constants
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6u2C158cH4p7ix88Kz51b"
WRAPPED_SOL_MINT = "So11111111111111111111111111111111111111112"


def get_token_metadata():
    """Fetch token list from Jupiter for metadata resolution.

    Falls back to the Solana Labs token-list if Jupiter is unavailable.
    """
    print("Fetching token metadata from Jupiter...")
    try:
        # Try the strict list first
        response = requests.get("https://token.jup.ag/strict", timeout=10)
        response.raise_for_status()
        tokens = response.json()
        return {t["address"]: t for t in tokens}
    except Exception as e:
        print(f"Warning: Failed to fetch token metadata from Jupiter: {e}")
        # Fallback: try Solana token list
        try:
            print("Attempting fallback token list from Solana token-list...")
            response = requests.get(
                "https://raw.githubusercontent.com/solana-labs/token-list/main/src/tokens/solana.tokenlist.json",
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            tokens = data.get("tokens", [])
            return {t["address"]: t for t in tokens}
        except Exception as e2:
            print(f"Warning: Failed to fetch fallback token list: {e2}")
            # Final fallback: return empty dict, we'll use mint addresses as symbols
            return {}


def get_token_prices(mints):
    """Fetch current prices for given mints using DexScreener API.

    Returns a tuple (prices, symbols) where `prices` maps mint -> price (float)
    and `symbols` maps mint -> inferred symbol (if available from the price API).
    """
    if not mints:
        return {}, {}
    print(f"Fetching prices for {len(mints)} tokens...")
    prices = {}
    symbols = {}

    # DexScreener allows querying individual tokens
    for mint in mints:
        try:
            response = requests.get(
                f"https://api.dexscreener.com/latest/dex/tokens/{mint}", timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                pairs = data.get("pairs", [])
                if pairs:
                    # Get the first pair's price (usually the most liquid)
                    price = pairs[0].get("priceUsd")
                    if price:
                        prices[mint] = float(price)
                    # Try to infer a symbol from common fields in the pair data
                    pair0 = pairs[0]
                    symbol = None
                    # Common nested token object keys
                    for key in ("baseToken", "token", "token0", "token1"):
                        part = pair0.get(key)
                        if isinstance(part, dict):
                            symbol = part.get("symbol") or part.get("name")
                            if symbol:
                                break
                    # Some responses use top-level symbol fields
                    if not symbol:
                        symbol = (
                            pair0.get("baseTokenSymbol")
                            or pair0.get("tokenSymbol")
                            or pair0.get("pairBaseTokenSymbol")
                        )
                    if symbol:
                        symbols[mint] = symbol
            time.sleep(0.3)  # Rate limiting for DexScreener
        except Exception as e:
            print(f"Warning: Failed to fetch price for {mint[:8]}...: {e}")
            continue

    return prices, symbols


def call_with_retry(func, *args, max_retries=3, initial_delay=2, **kwargs):
    """Call a function with exponential backoff for rate limiting."""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "Too Many Requests" in err_str:
                delay = initial_delay * (2**attempt)
                print(f"Rate limited (429). Retrying in {delay}s...")
                time.sleep(delay)
            elif "unrecognized Token program id" in err_str:
                # If the RPC doesn't support the program ID for this method, skip it
                print(
                    f"Warning: RPC does not recognize program ID in {func.__name__}. Skipping."
                )
                return None
            else:
                print(f"Rpc error: {e}")
                raise e
    raise Exception(f"Max retries reached for {func.__name__}")


def fetch_holdings(client, owner_pubkey, program_id):
    """Fetch token accounts for a specific program ID."""
    try:
        opts = TokenAccountOpts(program_id=Pubkey.from_string(program_id))

        # Use the retry wrapper for RPC calls
        response = call_with_retry(
            client.get_token_accounts_by_owner_json_parsed, owner_pubkey, opts
        )

        holdings = []
        if response and response.value:
            for account in response.value:
                info = account.account.data.parsed["info"]
                mint = info["mint"]
                amount = float(info["tokenAmount"]["uiAmount"] or 0)
                if amount > 0:
                    holdings.append(
                        {"mint": mint, "amount": amount, "program_id": program_id}
                    )
        return holdings
    except Exception as e:
        print(f"Error fetching holdings for {program_id}: {e}")
        return []


def main(output_dir=None):
    """Main entry point for the Solana fetcher."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        print("Warning: python-dotenv not installed. Using environment variables only.")

    wallet_addr = os.getenv("SOLANA_WALLET_ADDRESS")
    rpc_url = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")

    # Use provided output_dir or environment variable or current directory
    if output_dir is None:
        output_dir = os.getenv("PORTFOLIO_DATA_DIR", ".")

    if not wallet_addr:
        print("Error: SOLANA_WALLET_ADDRESS not found in environment")
        return

    print(f"Fetching holdings for wallet: {wallet_addr}")
    client = Client(rpc_url)
    owner_pubkey = Pubkey.from_string(wallet_addr)

    # 1. Fetch SOL Balance
    sol_balance_resp = call_with_retry(client.get_balance, owner_pubkey)
    sol_amount = (
        sol_balance_resp.value / 1e9
        if sol_balance_resp and sol_balance_resp.value
        else 0
    )

    # 2. Fetch SPL Tokens
    tokens = fetch_holdings(client, owner_pubkey, TOKEN_PROGRAM_ID)

    # 3. Fetch Token2022
    tokens_2022 = fetch_holdings(client, owner_pubkey, TOKEN_2022_PROGRAM_ID)

    all_tokens = tokens + tokens_2022

    # 4. Add SOL to the list
    all_tokens.append(
        {
            "mint": WRAPPED_SOL_MINT,
            "amount": sol_amount,
            "symbol": "SOL",
            "name": "Solana",
            "program_id": "Native",
        }
    )

    # 5. Enrich with Metadata and Prices
    metadata = get_token_metadata()
    mints_to_price = list(set([t["mint"] for t in all_tokens]))
    prices, price_symbols = get_token_prices(mints_to_price)

    results = []
    for t in all_tokens:
        mint = t["mint"]
        meta = metadata.get(mint, {})
        price = prices.get(mint, 0)

        # Resolve symbol: explicit symbol on token -> Jupiter/Solana tokenlist -> DexScreener inferred -> short mint fallback
        t["symbol"] = (
            t.get("symbol")
            or meta.get("symbol")
            or price_symbols.get(mint)
            or (mint[:8] + "...")
        )
        t["name"] = t.get("name") or meta.get("name", "Unknown Token")
        t["price"] = price
        t["value_usd"] = t["amount"] * price

        results.append(t)

    # Sort by value
    results.sort(key=lambda x: x["value_usd"], reverse=True)

    # Output
    print("\n--- Solana Portfolio ---")
    print(f"{'Symbol':<15} {'Amount':>15} {'Price':>10} {'Value (USD)':>15}")
    print("-" * 60)
    for r in results:
        print(
            f"{r['symbol']:<15} {r['amount']:>15,.4f} {r['price']:>10,.2f} {r['value_usd']:>15,.2f}"
        )

    # Save to file
    import pendulum
    from pathlib import Path
    
    current_date = pendulum.now().to_date_string()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    output_file = output_path / f"{current_date}_raw_solana.json"

    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved detailed results to {output_file}")


if __name__ == "__main__":
    main()
