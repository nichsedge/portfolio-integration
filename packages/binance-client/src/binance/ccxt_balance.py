import ccxt
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
load_dotenv()


def get_data_dir():
    """Get data directory from env vars with backward compatibility."""
    data_dir = os.getenv("PORTFOLIO_DATA_DIR") or os.getenv("CRYPTO_OUT_DIR") or "/home/al/Projects/.data/portfolio"
    return Path(data_dir)

def get_binance_balance(api_key, secret):
    if not api_key or not secret:
        print("Skipping Binance: API keys not found.")
        return {}
    
    try:
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': secret,
            'enableRateLimit': True,
        })
        
        balances = {}
        
        # 1. Fetch Spot Balance
        spot_balance = exchange.fetch_balance({'type': 'spot'})
        for symbol, total in spot_balance.get('total', {}).items():
            if total > 0:
                balances[symbol] = balances.get(symbol, 0) + total
        
        # 2. Fetch Earn/Simple Earn Balance (Flexible & Locked)
        # Note: CCXT uses 'sapi' for these Binance-specific endpoints
        try:
            # Flexible
            flexible = exchange.sapi_get_simple_earn_flexible_position()
            for item in flexible.get('rows', []):
                symbol = item['asset']
                total = float(item['totalAmount'])
                if total > 0:
                    balances[symbol] = balances.get(symbol, 0) + total
            
            # Locked
            locked = exchange.sapi_get_simple_earn_locked_position()
            for item in locked.get('rows', []):
                symbol = item['asset']
                total = float(item['totalAmount'])
                if total > 0:
                    balances[symbol] = balances.get(symbol, 0) + total
        except Exception as e:
            print(f"Note: Could not fetch Binance Earn balances: {e}")

        return balances
    except Exception as e:
        print(f"Error fetching balance from Binance: {e}")
        return {}

def get_exchange_balance(exchange_id, api_key, secret):
    if not api_key or not secret:
        print(f"Skipping {exchange_id}: API keys not found.")
        return {}
    
    try:
        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class({
            'apiKey': api_key,
            'secret': secret,
            'enableRateLimit': True,
        })
        balance = exchange.fetch_balance()
        return balance.get('total', {}) or {}
    except Exception as e:
        print(f"Error fetching balance from {exchange_id}: {e}")
        return {}

def get_prices_usd(symbols, exchange):
    prices = {
        'USDT': 1.0,
        'BUSD': 1.0,
        'USDC': 1.0,
        'DAI': 1.0,
        'IDRT': 0.000064, # Approximate if needed
    }
    
    # Try to fetch all tickers at once to be efficient
    try:
        tickers = exchange.fetch_tickers([f"{s}/USDT" for s in symbols if s not in prices])
        for symbol_pair, ticker in tickers.items():
            base = symbol_pair.split('/')[0]
            prices[base] = float(ticker['last'])
    except:
        # Fallback to individual fetches if fetch_tickers fails
        for symbol in symbols:
            if symbol in prices: continue
            try:
                ticker = exchange.fetch_ticker(f"{symbol}/USDT")
                prices[symbol] = float(ticker['last'])
            except:
                try:
                    ticker = exchange.fetch_ticker(f"{symbol}/BUSD")
                    prices[symbol] = float(ticker['last'])
                except:
                    pass
    return prices

def main():
    # Aggregate balances from multiple sources
    all_balances = {}
    
    # Binance (Spot + Earn)
    binance_balances = get_binance_balance(os.getenv('BINANCE_API_KEY'), os.getenv('BINANCE_SECRET'))
    for symbol, amount in binance_balances.items():
        all_balances[symbol] = all_balances.get(symbol, 0) + amount
        
    # Tokocrypto (Spot)
    tko_balances = get_exchange_balance('tokocrypto', os.getenv('TKO_API_KEY'), os.getenv('TKO_SECRET'))
    for symbol, amount in tko_balances.items():
        all_balances[symbol] = all_balances.get(symbol, 0) + amount

    if not all_balances:
        print("No balances found. Check your API keys and .env file.")
        return

    # Price Discovery
    price_exchange = ccxt.binance()
    symbols = list(all_balances.keys())
    prices_usd = get_prices_usd(symbols, price_exchange)
    
    # Calculate values
    assets_with_value = []
    total_usd = 0

    for symbol, amount in all_balances.items():
        price_usd = prices_usd.get(symbol, 0)
        val_usd = amount * price_usd
        
        if val_usd > 0.01: # Filter out dust
            assets_with_value.append({
                "symbol": symbol,
                "amount": amount,
                "price_usd": price_usd,
                "value_usd": val_usd
            })
            total_usd += val_usd

    assets_with_value.sort(key=lambda x: x['value_usd'], reverse=True)

    output = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "total_usd": total_usd,
        "assets": assets_with_value
    }

    # Use PORTFOLIO_DATA_DIR with backward compatibility for CRYPTO_OUT_DIR
    data_dir_env = os.getenv("PORTFOLIO_DATA_DIR") or os.getenv("CRYPTO_OUT_DIR")
    if data_dir_env:
        data_dir = Path(data_dir_env)
    else:
        data_dir = get_data_dir()

    os.makedirs(data_dir, exist_ok=True)
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    out_path = data_dir / f"{date_str}_raw_binance.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(assets_with_value)} assets to {out_path}")
    print(f"Total Portfolio Value: ${total_usd:,.2f}")

if __name__ == "__main__":
    main()