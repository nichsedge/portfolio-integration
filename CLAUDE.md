# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a portfolio integration system that aggregates financial data from multiple sources into a unified format. The monorepo workspace structure consists of:

- **packages/ksei-client/** - Python library for interacting with KSEI (Indonesian Central Securities Depository) API
- **packages/binance-client/** - CCXT-based cryptocurrency balance fetcher for Binance and similar exchanges
- **packages/debank-scraper/** - Playwright-based scraper for DeBank DeFi portfolio data (JavaScript/Node.js)
- **packages/transform-core/** - Shared utilities for portfolio data transformation
- **packages/portfolio-app/** - Main integration layer that processes and combines data from all sources
- **apps/pipeline-runner/** - CLI entry point to orchestrate the full pipeline

## Development Commands

**IMPORTANT: Always use `uv run` instead of `python` to execute Python scripts.** This ensures dependencies from the uv-managed virtual environment are available.

```bash
# Sync all Python packages in the workspace
cd /REDACTED_HOME/Projects/portfolio_integration
uv sync

# Run a script in a package
cd <package-dir>
uv run <script.py>

# Add new dependencies to a package
cd <package-dir>
uv add <package_name>

# For Node.js packages (debank-scraper/)
cd packages/debank-scraper
npm install
npm run scrape
```

## Environment Configuration

All projects use standardized environment variables:

| Variable | Purpose | Default Value |
|----------|---------|---------------|
| `PORTFOLIO_DATA_DIR` | Main data directory path | `/REDACTED_HOME/Projects/.data/portfolio` |
| `DATA_DIR` | Alias for PORTFOLIO_DATA_DIR (legacy) | Same as above |

### Using Custom Data Directory

```bash
# Set custom data directory for all projects
export PORTFOLIO_DATA_DIR=/path/to/your/data

# Run with custom directory
PORTFOLIO_DATA_DIR=/path/to/your/data uv run script.py
```

### Project-Specific Environment Variables

Credentials are stored in `.env` files in respective package directories:

**packages/ksei-client/.env:**
- `KSEI_USERNAME` - KSEI username
- `KSEI_PASSWORD` - KSEI password
- `KSEI_AUTH_PATH` - Authentication storage path (default: `./auth`)
- `PORTFOLIO_DATA_DIR` - Data directory (optional)

**packages/debank-scraper/.env:**
- `EVM_ADDRESS` - Wallet address to scrape
- `PORTFOLIO_DATA_DIR` - Data directory (optional)

**packages/binance-client/.env:**
- `BINANCE_API_KEY` - Binance API key
- `BINANCE_SECRET` - Binance API secret
- `TKO_API_KEY` - Tokocrypto API key (optional)
- `TKO_SECRET` - Tokocrypto API secret (optional)
- `PORTFOLIO_DATA_DIR` - Data directory (optional)
- `CRYPTO_OUT_DIR` - Legacy alias for PORTFOLIO_DATA_DIR

**packages/transform-core/** and **packages/portfolio-app/**: No env file needed, use `PORTFOLIO_DATA_DIR` via shared utilities

## Running the Pipeline

### Full Pipeline (Recommended)

```bash
# Run the entire pipeline from repo root
python -m apps.pipeline_runner.src.main

# With options:
python -m apps.pipeline_runner.src.main --fetch-only     # Just fetch raw data
python -m apps.pipeline_runner.src.main --integrate      # Skip fetching, just transform and integrate
```

### Individual Steps

```bash
# 1. Fetch raw data from each source
cd packages/ksei-client
uv run examples/fetch_and_dump_portfolios.py

cd ../debank-scraper
npm run scrape

cd ../binance-client
uv run ccxt_balance.py

# 2. Transform data
cd ../portfolio-app
uv run python -m src.portfolio_app.transformers.ksei_transform
uv run python -m src.portfolio_app.transformers.debank_transform
uv run python -m src.portfolio_app.transformers.binance_transform

# 3. Integrate all data
uv run python -m src.portfolio_app.integrators.portfolio_integration
```

## Architecture

### Monorepo Workspace Structure

```
portfolio-integration/
├── packages/                      # Independent, versioned packages
│   ├── ksei-client/               # Python - Installable, reusable KSEI library
│   ├── binance-client/            # Python - Binance balance fetcher
│   ├── debank-scraper/            # Node.js - DeBank Playwright scraper
│   ├── transform-core/            # Python - Shared utilities
│   └── portfolio-app/             # Python - Main integration app
├── apps/
│   └── pipeline-runner/           # Python - Pipeline orchestration entry point
├── pyproject.toml                 # Workspace configuration
├── pnpm-workspace.yaml            # Node.js workspace configuration
└── CLAUDE.md                      # This file
```

### Data Flow Pattern

All data follows this standardized pipeline:

1. **Raw Extraction** → `{YYYY-MM-DD}_raw_<source>.json`
2. **Cleaning/Processing** → `{YYYY-MM-DD}_curated_<source>.json`
3. **Integration** → `{YYYY-MM-DD}_portfolio.csv`

### File Naming Convention

All output files use `pendulum` for date formatting and are stored in the data directory (`PORTFOLIO_DATA_DIR` or `/REDACTED_HOME/Projects/.data/portfolio/`):

- Raw data: `{YYYY-MM-DD}_raw_<source>.json`
- Cleaned data: `{YYYY-MM-DD}_curated_<source>.json`
- Final output: `{YYYY-MM-DD}_portfolio.csv`

### Standardized Data Format

All data sources must produce standardized dictionaries with these fields:

```python
{
    "source": str,        # "KSEI", "DeBank", "Binance", "Hyperliquid"
    "category": str,      # "Cash", "Equity", "Cryptocurrency", "DeFi Protocol", etc.
    "asset": str,         # Asset name or symbol
    "currency": str,      # Currency code (IDR, USD, etc.)
    "amount": float,      # Quantity held
    "value_idr": float,   # Value in IDR (or None)
    "value_usd": float,   # Value in USD (or None)
    "account": str,       # Account identifier
    "details": str,       # Additional context/details
}
```

## Component Details

### packages/ksei-client/

Python library with both sync/async KSEI API client.

Authentication flow:
1. Password hashing via `/activation/generated` endpoint
2. Login returns JWT token
3. Token stored in `FileAuthStore` for reuse with expiration checking

Key methods:
- `get_all_portfolios_async()` - Fetches all portfolio types in parallel
- `get_cash_balances()`, `get_equity_balances()`, `get_mutual_fund_balances()`, `get_bond_balances()`

To test:
```bash
cd packages/ksei-client
uv run examples/fetch_and_dump_portfolios.py
```

### packages/binance-client/

Python tool using CCXT library to fetch cryptocurrency balances from:
- Binance (Spot + Earn/Simple Earn)
- Tokocrypto (optional)

To test:
```bash
cd packages/binance-client
uv run ccxt_balance.py
```

**Important:** The script must be run with `uv run`, not `python`, because `ccxt` is installed in the uv-managed virtual environment, not in the system Python.

Data format:
- Outputs: `{YYYY-MM-DD}_raw_binance.json`
- Structure: `{ timestamp, total_usd, assets: [{ symbol, amount, price_usd, value_usd }] }`

### packages/debank-scraper/

Playwright-based scraper that:
1. Navigates to DeBank profile page (configurable `EVM_ADDRESS`)
2. Auto-scrolls to load lazy content
3. Extracts profile data, wallet balances, and DeFi protocol positions
4. Saves to JSON with timestamp

To test:
```bash
cd packages/debank-scraper
npm run scrape
```

### packages/transform-core/

Shared utilities package to eliminate code duplication.

Exports:
- `get_data_dir()` - Get data directory from PORTFOLIO_DATA_DIR or default
- `parse_usd(value)` - Convert USD string to float, handle <$0.01 and None
- `DATA_DIR_DEFAULT` - Default data directory constant
- `FILTER_THRESHOLDS` - Threshold dict for filtering dust positions

### packages/portfolio-app/

Main integration layer containing transform scripts and integrator.

Transform scripts:
- **src/portfolio_app/transformers/ksei_transform.py** - Cleans KSEI raw JSON, filters entries < IDR 10,000
- **src/portfolio_app/transformers/debank_transform.py** - Cleans DeBank raw JSON, filters entries < $10 USD
- **src/portfolio_app/transformers/binance_transform.py** - Cleans Binance raw JSON, filters dust positions
- **src/portfolio_app/integrators/portfolio_integration.py** - Main integration script

The transformers import from `transform-core` for shared utilities like `get_data_dir()` and `FILTER_THRESHOLDS`.

### apps/pipeline-runner/

Single CLI entry point to orchestrate the full pipeline.

Usage:
```bash
python -m apps.pipeline_runner.src.main              # Full pipeline
python -m apps.pipeline_runner.src.main --fetch-only  # Only fetch raw data
python -m apps.pipeline_runner.src.main --integrate   # Only transform and integrate
```

## Important Notes

- **uv run vs python:** Always use `uv run` for Python scripts to access uv-managed dependencies
- **Filtering thresholds:** KSEI entries < IDR 10,000, DeBank entries < $10 USD, Binance positions < $0.01 USD
- **Shared utilities:** Use `from transform_core import get_data_dir, parse_usd, FILTER_THRESHOLDS` in transform scripts
- **Date formatting:** Use `pendulum.now().format('YYYY-MM-DD')` for consistency (or `datetime.now(UTC)` for Python stdlib)
- **Path configuration:** Use `get_data_dir()` from transform-core for all Python scripts
- **KSEI client:** Supports both synchronous and asynchronous operations
- **Mixed languages:** Python managed by uv, Node.js managed by npm/pnpm
- **Workspace sync:** Run `uv sync` from repo root to sync all Python packages

## Backward Compatibility

The system maintains backward compatibility with legacy environment variables:
- `CRYPTO_OUT_DIR` - Still works for binance-client, but `PORTFOLIO_DATA_DIR` takes priority
- `KSEI_OUTPUT_DIR` - Still works for ksei-client, but `PORTFOLIO_DATA_DIR` takes priority
- `DATA_DIR` - Alias for `PORTFOLIO_DATA_DIR`

## Adding a New Data Source

1. Create a new package under `packages/<name>-client/`
2. Implement data fetch script that outputs `{YYYY-MM-DD}_raw_<name>.json`
3. Use `get_data_dir()` from transform-core for data directory path
4. Create transformer script in `packages/portfolio-app/src/portfolio_app/transformers/<name>_transform.py`
5. Add pipeline step in `apps/pipeline-runner/src/main.py`
6. Update transform-core `FILTER_THRESHOLDS` if needed