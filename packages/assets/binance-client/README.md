# get-binance

Fetch cryptocurrency balances from Binance and similar exchanges using CCXT.

## Installation

```bash
uv sync
```

## Usage

```bash
# Create .env file from template
cp .env.template .env
# Edit .env with your API credentials

# Run the script
uv run binance-fetch
```

## Environment Variables

- `BINANCE_API_KEY` - Binance API key
- `BINANCE_SECRET` - Binance API secret
- `TKO_API_KEY` - Tokocrypto API key (optional)
- `TKO_SECRET` - Tokocrypto API secret (optional)
- `PORTFOLIO_DATA_DIR` - Output directory for data files (default: /REDACTED_HOME/Projects/.data/portfolio)