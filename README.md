# Portfolio Integration

A comprehensive monorepo for integrating portfolio data from multiple financial sources.

## Overview

This system extracts and integrates portfolio data from various financial platforms:

- **KSEI** - Indonesian Central Securities Depository
- **DeBank** - DeFi portfolio tracking platform
- **Binance** - Cryptocurrency exchange
- **Manual CSV** - For bank accounts, cash, and other non-API assets

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
uv run run-all

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
└── AGENTS.md                      # AI assistant guidance
```

## Workflow

### Data Pipeline

All data follows a standardized pipeline:

1. **Raw Extraction** → `{YYYY-MM-DD}_raw_<source>.json`
2. **Cleaning/Processing** → `{YYYY-MM-DD}_curated_<source>.json`
3. **Manual Data** (Optional) → `_manual_balances.csv`
4. **Integration** → `{YYYY-MM-DD}_portfolio.csv`

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

## Manual Asset Tracking

For assets that do not have an API (e.g., local bank accounts, cash, physical gold), you can maintain a CSV file.

1. Create a `_manual_balances.csv` file in your data directory (default: `data/`).
2. Use the format provided in `data/manual_balances_template.csv`.
3. The pipeline will automatically detect this file and integrate it into the final portfolio snapshot.

Required columns in `_manual_balances.csv`:
- `source`: The name of the source (e.g., "Bank", "Physical")
- `category`: Asset category (e.g., "Cash", "Asset")
- `asset`: Name of the asset (e.g., "BCA", "Gold")
- `currency`: Currency code (e.g., "IDR", "USD")
- `amount`: Quantity held
- `value_idr`: Total value in IDR (optional if `value_usd` is provided)
- `value_usd`: Total value in USD (optional if `value_idr` is provided)
- `account`: Account identifier or description
- `details`: Any additional notes

## Adding New Data Sources

### Fetcher Package Pattern

When adding a new data source, follow this standardized pattern:

#### 1. Create Package Structure

```
packages/<source>-client/
├── README.md
├── pyproject.toml
├── .env
├── src/
│   └── <source>_client/
│       ├── __init__.py
│       └── fetcher.py
└── examples/
    └── fetch_example.py
```

#### 2. Package Configuration (`pyproject.toml`)

```toml
[project]
name = "<source>-client"
version = "0.1.0"
description = "Client for fetching data from <source>"
requires-python = ">=3.12"
dependencies = [
    # Add required dependencies
]

[project.scripts]
<source>-fetch = "<source>_client:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/<source>_client"]
```

#### 3. Fetcher Implementation (`src/<source>_client/fetcher.py`)

```python
import os
import json
from datetime import datetime
from pathlib import Path

def main(output_dir=None):
    """Main entry point for the fetcher."""
    # Use provided output_dir or environment variable or current directory
    if output_dir is None:
        output_dir = os.getenv("<SOURCE>_OUTPUT_DIR", ".")
    
    # Fetch data logic here
    data = fetch_data()
    
    # Save with standardized naming: YYYY-MM-DD_raw_<source>.json
    current_date = datetime.now().strftime("%Y-%m-%d")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    output_file = output_path / f"{current_date}_raw_<source>.json"
    
    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved to {output_file}")
```

#### 4. Pipeline Integration

**Add to `apps/pipeline-runner/pyproject.toml`:**
```toml
dependencies = [
    # ... other dependencies
    "<source>-client",
]

[tool.uv.sources]
<source>-client = { workspace = true }

[project.scripts]
fetch-<source> = "run-all:fetch_<source>_entrypoint"
```

**Add entrypoint to `apps/pipeline-runner/src/pipeline_runner/__init__.py`:**
```python
def fetch_<source>_entrypoint():
    """Entry point for <source> fetch command."""
    from <source>_client import main as <source>_main
    
    # Get data directory
    repo_root = Path(__file__).resolve().parents[4]
    default_data_dir = repo_root / "data"
    data_dir = os.getenv("PORTFOLIO_DATA_DIR") or os.getenv("DATA_DIR") or str(default_data_dir)
    
    print("🚀 Fetching <source> data...")
    print(f"Data directory: {data_dir}\n")
    
    # Call fetcher with output directory
    <source>_main(output_dir=data_dir)
```

#### 5. Output Format

- **File naming:** `YYYY-MM-DD_raw_<source>.json`
- **Location:** Standardized data directory (default: `data/`)
- **Format:** JSON with consistent structure

### Example: Alchemy Client

See `packages/alchemy-client/` for a complete reference implementation following this pattern.
```

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `PORTFOLIO_DATA_DIR` | Main data directory path | `/REDACTED_HOME/Projects/.data/portfolio` |

## License

[Add license information here]