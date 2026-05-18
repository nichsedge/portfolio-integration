# Solana Client

A Python client for fetching Solana token holdings and prices from a wallet address.

## Features

- Fetch SOL balance and all SPL token holdings
- Enrich tokens with metadata from Jupiter Token List
- Fetch current prices from DexScreener API
- Output to console and JSON file

## Installation

```bash
uv pip install -e packages/solana-client
```

## Usage

### Command Line

```bash
# Set your wallet address in .env
echo "SOLANA_WALLET_ADDRESS=your_wallet_address_here" > .env

# Run the fetcher
solana-fetch
```

### Python API

```python
from solana_client import fetch_holdings
from solders.pubkey import Pubkey

wallet = Pubkey.from_string("your_wallet_address")
holdings = fetch_holdings(wallet)
print(holdings)
```

## Configuration

Create a `.env` file with:

```
SOLANA_WALLET_ADDRESS=your_wallet_address_here
# RPC_URL=https://api.mainnet-beta.solana.com  # Optional
```

## Output

The script outputs:
- Console table with token symbols, amounts, prices, and USD values
- `solana_portfolio.json` with detailed token information
