# Portfolio Integration

A comprehensive monorepo for integrating portfolio data from multiple financial sources.

## Overview

This system extracts and integrates portfolio data from various financial platforms:

- **KSEI** - Indonesian Central Securities Depository
- **DeBank** - DeFi portfolio tracking platform
- **Binance** - Cryptocurrency exchange
- **Hyperliquid** - DeFi protocol

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) for Python package management
- Node.js for the DeBank scraper

### Installation

```bash
# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone this repository
git clone <repository-url>
cd portfolio-integration

# Sync all Python packages
uv sync

# Install Node.js dependencies
cd packages/debank-scraper
npm install
cd ../..
```

### Usage

```bash
# Set custom data directory (optional)
export PORTFOLIO_DATA_DIR=/path/to/your/data

# Run full pipeline
python -m apps.pipeline_runner.src.main

# Or just:
python -m pipeline_runner

# Options:
# --fetch-only    # Just fetch raw data
# --integrate     # Skip fetching, just transform and integrate
```

## Project Structure

```
portfolio-integration/
├── packages/                      # Independent packages
│   ├── ksei-client/               # KSEI API client
│   ├── binance-client/            # Binance CCXT client
│   ├── debank-scraper/            # DeBank Playwright scraper
│   ├── transform-core/            # Shared utilities
│   └── portfolio-app/             # Integration app
├── apps/                          # Entry points
│   └── pipeline-runner/           # Orchestrates the pipeline
├── CONTRIBUTING.md                # How to contribute
├── DEVELOPMENT.md                 # Development guide
└── CLAUDE.md                      # AI assistant guidance
```

## Workflow

### Data Pipeline

All data follows a standardized pipeline:

1. **Raw Extraction** → `{YYYY-MM-DD}_raw_<source>.json`
2. **Cleaning/Processing** → `{YYYY-MM-DD}_curated_<source>.json`
3. **Integration** → `{YYYY-MM-DD}_portfolio.csv`

### Running Individual Components

```bash
# Fetch KSEI data
cd packages/ksei-client
uv run examples/fetch_and_dump_portfolios.py

# Fetch DeBank data
cd packages/debank-scraper
npm run scrape

# Fetch Binance data
cd packages/binance-client
uv run ccxt_balance.py

# Transform and integrate
cd packages/portfolio-app

# Transform (optional - done by pipeline)
python src/portfolio_app/transformers/ksei_transform.py
python src/portfolio_app/transformers/debank_transform.py
python src/portfolio_app/transformers/binance_transform.py

# Integrate (optional - done by pipeline)
python src/portfolio_app/integrators/portfolio_integration.py
```

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `PORTFOLIO_DATA_DIR` | Main data directory path | `/REDACTED_HOME/Projects/.data/portfolio` |

## License

[Add license information here]