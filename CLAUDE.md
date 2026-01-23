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

## Rules

### Running Python Scripts

**ALWAYS use `uv run` instead of `python`** for scripts that have dependencies in pyproject.toml. The only exception is for scripts that add transform-core to sys.path manually.

### Transform Scripts

Transform scripts in `portfolio-app/src/portfolio_app/transformers/` do NOT use `uv run`. They require `transform-core` to be imported manually via sys.path since uv workspace dependency injection doesn't work correctly for these scripts.

**Correct way to run transforms:**
```bash
cd /REDACTED_HOME/Projects/portfolio_integration
PYTHONPATH=/REDACTED_HOME/Projects/portfolio_integration/packages/transform-core/src \
  python packages/portfolio-app/src/portfolio_app/transformers/hyperliquid_transform.py
```

Or with environment variable:
```bash
HYPERLIQUID_WALLET_ADDRESS=0x... \
  PYTHONPATH=/REDACTED_HOME/Projects/portfolio_integration/packages/transform-core/src \
  python packages/portfolio-app/src/portfolio_app/transformers/hyperliquid_transform.py
```

### Data Source Scripts

Data fetch scripts (ksei-client, binance-client) DO use `uv run`:
```bash
cd packages/ksei-client
uv run examples/fetch_and_dump_portfolios.py

cd packages/binance-client
uv run ccxt_balance.py
```

### Node.js Scripts

Node.js scripts use npm directly (no uv):
```bash
cd packages/debank-scraper
npm install
npm run scrape
```

### Imports in Transform Scripts

Transform scripts must add transform-core to sys.path at the top:
```python
import sys
from pathlib import Path
repo_root = Path(__file__).parents[4]
sys.path.insert(0, str(repo_root / "packages"))

from transform_core import get_data_dir, FILTER_THRESHOLDS
```

### Date Formatting

Use `datetime.now(UTC)` instead of deprecated `datetime.utcnow()`. For ISO output:
```python
from datetime import datetime, UTC

# ISO 8601 format with Z suffix
timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")

# Or just date component
date_str = datetime.now(UTC).strftime("%Y-%m-%d")
```

### Environment Variables

**CRITICAL:** Never commit wallet addresses, API keys, or passwords to git. Always use environment variables.

Set environment variables via:
```bash
export HYPERLIQUID_WALLET_ADDRESS=0x...
export BINANCE_API_KEY=xxx
export BINANCE_SECRET=yyy
```

Or inline with command:
```bash
HYPERLIQUID_WALLET_ADDRESS=0x... python script.py
```

## Development Commands

```bash
# Sync all Python packages in the workspace
cd /REDACTED_HOME/Projects/portfolio_integration
uv sync

# Install transform-core in editable mode (required for transforms)
uv pip install -e packages/transform-core

# Add new dependencies to a package
cd packages/<package-name>
uv add <package_name>

# Node.js dependencies
cd packages/debank-scraper
npm install
```

## Environment Configuration

| Variable | Purpose | Default Value |
|----------|---------|---------------|
| `PORTFOLIO_DATA_DIR` | Main data directory path | `[REPO_ROOT]/data` |
| `DATA_DIR` | Alias for PORTFOLIO_DATA_DIR (legacy) | Same as above |
| `HYPERLIQUID_WALLET_ADDRESS` | EVM wallet address for Hyperliquid | (required) |

### Project-Specific Environment Variables

**packages/ksei-client/.env:**
- `KSEI_USERNAME` - KSEI username
- `KSEI_PASSWORD` - KSEI password
- `KSEI_AUTH_PATH` - Authentication storage path (default: `./auth`)

**packages/debank-scraper/.env:**
- `EVM_ADDRESS` - Wallet address to scrape
- `PORTFOLIO_DATA_DIR` - Data directory (optional)

**packages/binance-client/.env:**
- `BINANCE_API_KEY` - Binance API key
- `BINANCE_SECRET` - Binance API secret
- `TKO_API_KEY` - Tokocrypto API key (optional)
- `TKO_SECRET` - Tokocrypto API secret (optional)

## Running the Pipeline

### Pipeline Commands (Recommended)

Run optimization via `uv run`:
```bash
cd /REDACTED_HOME/Projects/portfolio_integration
uv run run-pipeline       # Full pipeline
uv run fetch              # Just fetch raw data
uv run integrate          # Just integrate existing data
```

Note: These commands are installed via the `pipeline-runner` workspace package. Run `uv sync` to ensure they are available in your environment.

### Individual Steps

**1. Fetch raw data:**
```bash
cd packages/ksei-client
uv run examples/fetch_and_dump_portfolios.py

cd ../debank-scraper
npm run scrape

cd ../binance-client
uv run ccxt_balance.py

cd /REDACTED_HOME/Projects/portfolio_integration
HYPERLIQUID_WALLET_ADDRESS=0x... \
  PYTHONPATH=/REDACTED_HOME/Projects/portfolio_integration/packages/transform-core/src \
  python packages/portfolio-app/src/portfolio_app/transformers/hyperliquid_transform.py
```

**2. Transform data:**
```bash
cd /REDACTED_HOME/Projects/portfolio_integration

PYTHONPATH=/REDACTED_HOME/Projects/portfolio_integration/packages/transform-core/src \
  python packages/portfolio-app/src/portfolio_app/transformers/ksei_transform.py

PYTHONPATH=/REDACTED_HOME/Projects/portfolio_integration/packages/transform-core/src \
  python packages/portfolio_app/src/portfolio_app/transformers/debank_transform.py

PYTHONPATH=/REDACTED_HOME/Projects/portfolio_integration/packages/transform-core/src \
  python packages/portfolio_app/src/portfolio_app/transformers/binance_transform.py
```

**3. Integrate all data:**
```bash
PYTHONPATH=/REDACTED_HOME/Projects/portfolio_integration/packages/transform-core/src \
  python packages/portfolio-app/src/portfolio_app/integrators/portfolio_integration.py
```

## Architecture

### Monorepo Workspace Structure

```
portfolio-integration/
├── packages/
│   ├── ksei-client/          # Python - KSEI API client
│   ├── binance-client/       # Python - Binance CCXT client
│   ├── debank-scraper/       # Node.js - DeBank scraper
│   ├── transform-core/       # Python - Shared utilities
│   └── portfolio-app/        # Python - Integration app
├── apps/
│   └── pipeline-runner/      # Python - Pipeline orchestration
├── pyproject.toml            # Workspace configuration
└── CLAUDE.md                 # This file
```

### Data Flow Pattern

1. **Raw Extraction** → `{YYYY-MM-DD}_raw_<source>.json`
2. **Cleaning/Processing** → `{YYYY-MM-DD}_curated_<source>.json`
3. **Integration** → `{YYYY-MM-DD}_portfolio.csv`

### Standardized Data Format

All data sources must produce:
```python
{
    "source": str,        # "KSEI", "DeBank", "Binance", "Hyperliquid"
    "category": str,      # "Cash", "Equity", "Cryptocurrency", "Vault Position", etc.
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

### packages/transform-core/

Shared utilities - must be added to sys.path manually. Install with:
```bash
uv pip install -e packages/transform-core
```

Exports:
- `get_data_dir()` - Get data directory from PORTFOLIO_DATA_DIR
- `parse_usd(value)` - Convert USD string to float
- `DATA_DIR_DEFAULT` - Default data directory constant
- `FILTER_THRESHOLDS` - Threshold dict for filtering

### packages/ksei-client/

To test:
```bash
cd packages/ksei-client
uv run examples/fetch_and_dump_portfolios.py
```

### packages/binance-client/

To test:
```bash
cd packages/binance-client
uv run ccxt_balance.py
```

### packages/portfolio-app/

**Transform Scripts - Run with PYTHONPATH:**
```bash
cd /REDACTED_HOME/Projects/portfolio_integration
PYTHONPATH=packages/transform-core/src \
  python packages/portfolio-app/src/portfolio_app/transformers/hyperliquid_transform.py
```

## Important Notes

- **uv run for data source scripts** (ksei-client, binance-client)
- **PYTHONPATH for transform scripts** (portfolio-app/transformers/)
- **npm for Node.js** (debank-scraper)
- **Deprecation warning:** Use `datetime.now(UTC)` not `datetime.utcnow()`
- **Never commit:** Wallet addresses, API keys, passwords
- **Filter thresholds:** KSEI < IDR 10,000, DeBank < $10, Binance < $0.01, Hyperliquid < $10
- **Path imports:** Transform scripts add transform-core via sys.path

## Backward Compatibility

- `CRYPTO_OUT_DIR` - Legacy alias for PORTFOLIO_DATA_DIR
- `KSEI_OUTPUT_DIR` - Legacy alias for PORTFOLIO_DATA_DIR
- `DATA_DIR` - Alias for PORTFOLIO_DATA_DIR

## Adding a New Data Source

1. Create package `packages/<name>-client/`
2. Implement fetch script outputting `{YYYY-MM-DD}_raw_<name>.json`
3. Create transformer `packages/portfolio-app/src/portfolio_app/transformers/<name>_transform.py`
   - Add sys.path import pattern for transform-core
   - Use `get_data_dir()` and `FILTER_THRESHOLDS`
4. Add pipeline step in `apps/pipeline-runner/src/main.py`
5. Update transform-core `FILTER_THRESHOLDS` if needed