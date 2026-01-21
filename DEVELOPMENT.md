# DEVELOPMENT.md

Portfolio Integration Monorepo Development Guide

## Workspace Structure

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
└── pyproject.toml                 # Workspace config
```

## Setup

### Initial Setup

```bash
# Clone the repository
git clone <repository-url>
cd portfolio-integration

# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync all Python packages
uv sync

# Install Node.js dependencies for DeBank
cd packages/debank-scraper
npm install
cd ../..
```

### Environment Variables

All packages use `PORTFOLIO_DATA_DIR` to specify where data files are stored:

```bash
# Set custom data directory
export PORTFOLIO_DATA_DIR=/path/to/your/data

# Or per-command
PORTFOLIO_DATA_DIR=/path/to/data uv run script.py
```

Default: `/home/al/Projects/.data/portfolio`

## Running Locally

### Run Full Pipeline

```bash
# From repository root
python -m apps.pipeline_runner.src.main

# Or if installed
python -m pipeline_runner

# Options:
# --fetch-only    # Just fetch raw data
# --integrate     # Skip fetching, just transform and integrate
```

### Run Individual Components

#### KSEI Client

```bash
cd packages/ksei-client
uv run examples/fetch_and_dump_portfolios.py
```

#### DeBank Scraper

```bash
cd packages/debank-scraper
npm run scrape
```

#### Binance Client

```bash
cd packages/binance-client
uv run ccxt_balance.py
```

#### Portfolio Transforms

```bash
cd packages/portfolio-app

# Transform individual sources
python src/portfolio_app/transformers/ksei_transform.py
python src/portfolio_app/transformers/debank_transform.py
python src/portfolio_app/transformers/binance_transform.py

# Integrate all
python src/portfolio_app/integrators/portfolio_integration.py
```

## Package Management

### Adding a Dependency to a Package

```bash
# Navigate to the package directory
cd packages/<package-name>

# Add dependency
uv add <package_name>

# Add dev dependency
uv add --dev <package_name>
```

### Building Packages

```bash
# Build a specific package
cd packages/ksei-client
uv build

# Or from workspace root
uv build --package ksei-client
```

## Publishing Packages

### KSEI Client (Python)

```bash
cd packages/ksei-client
uv publish
```

### Other Packages

Each package is independently versioned in its `pyproject.toml` and can be published if needed.

## Dependency Sharing

The `transform-core` package provides shared utilities:

```python
from transform_core import get_data_dir, parse_usd, FILTER_THRESHOLDS

# Get data directory
data_dir = get_data_dir()

# Parse USD value
value = parse_usd("$123.45")

# Get filter threshold
threshold = FILTER_THRESHOLDS["ksei_idr"]
```

## Common Issues

### Import Errors

If you get import errors when running scripts:

1. Run `uv sync` from the repository root to ensure workspace is synced
2. For transform scripts, the `sys.path` manipulation should handle imports automatically

### Missing Dependencies

```bash
# Sync all packages
cd /path/to/portfolio-integration
uv sync

# Sync specific package
cd packages/<package-name>
uv sync
```

### Node.js Install Issues (DeBank)

```bash
cd packages/debank-scraper
rm -rf node_modules package-lock.json
npm install
```