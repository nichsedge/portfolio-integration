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
echo "SOL_ADDRESS=your_wallet_address_here" > .env

# Run the fetcher
solana-fetch
```

### Python API

```python
from solana_client import SolanaFetcher, Pubkey

# Initialize with wallet address
wallet = Pubkey.from_string("your_wallet_address")
fetcher = SolanaFetcher(wallet)

# Fetch all balances and tokens
data = fetcher.fetch_all()
print(data)
```

## Configuration

Set the following environment variables:

- `SOL_ADDRESS`: Your Solana wallet public key (required)
# RPC_URL=https://api.mainnet-beta.solana.com  # Optional

## Output

The script outputs:
- Console table with token symbols, amounts, prices, and USD values
- `solana_portfolio.json` with detailed token information
