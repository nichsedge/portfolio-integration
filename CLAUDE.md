# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a Python monorepo for integrating portfolio data from multiple financial sources (KSEI, DeBank, Binance, Solana, Hyperliquid). It uses `uv` for Python package management and follows a modular, package-based architecture.

## Development Commands

### Setup
```bash
# Install all Python dependencies
uv sync

# Install Node.js dependencies for DeBank scraper
cd packages/debank-scraper && npm install
```

### Running the Pipeline
```bash
# Run full pipeline (fetch + transform + integrate)
uv run pipeline_runner

# Fetch only (no transformation)
uv run pipeline_runner --fetch-only

# Transform and integrate only (skip fetching)
uv run pipeline_runner --integrate

# Run individual fetchers
cd packages/ksei-client && uv run examples/fetch_and_dump_portfolios.py
cd packages/debank-scraper && npm run scrape
cd packages/binance-client && uv run ccxt_balance.py
cd packages/alchemy-client && uv run alchemy-fetch
```

### Data Directory
Set custom data directory via environment variable:
```bash
export PORTFOLIO_DATA_DIR=/path/to/your/data
```
Default: `{repo_root}/data`

## Architecture

### Monorepo Structure
- **`packages/`** - Independent packages (clients, transformers, shared utilities)
- **`apps/`** - Entry points and orchestration
- **`data/`** - Pipeline output (git-ignored)

### Key Packages
- **`transform-core`** - Shared utilities (`get_data_dir()`, `parse_usd()`, `FILTER_THRESHOLDS`)
- **`portfolio-app`** - Contains transformers and integrators
- **`alchemy-client`** - Fetcher package for Solana holdings via Alchemy
- **`debank-scraper`** - Node.js Playwright-based scraper
- **`pipeline-runner`** - Orchestrates the entire pipeline

### Data Pipeline Flow

The pipeline follows a three-stage transformation:

1. **Fetch (Raw)** - `{YYYY-MM-DD}_raw_{source}.json`
   - Each client package fetches data from its source
   - Output: Raw JSON files with all data

2. **Transform (Curated)** - `{YYYY-MM-DD}_curated_{source}.json`
   - Transformers in `portfolio-app/transformers/` filter and clean data
   - Apply `FILTER_THRESHOLDS` from `transform-core/constants.py`
   - Output: Cleaned JSON files

3. **Integrate (Portfolio)** - `{YYYY-MM-DD}_portfolio.csv`
   - Integrator in `portfolio-app/integrators/portfolio_integration.py`
   - Standardizes all sources into unified CSV format
   - Output: Single CSV with standardized columns

### Pipeline Orchestration

The `pipeline-runner` app (`apps/pipeline-runner/src/pipeline_runner/__init__.py`) orchestrates the entire flow:
- Calls each fetcher's `main()` function with `output_dir` parameter
- Executes transformers sequentially
- Runs final integration

### Workspace Dependencies

All packages use workspace references in `pyproject.toml`:
```toml
[tool.uv.sources]
transform-core = { workspace = true }
portfolio-app = { workspace = true }
```

The root `pyproject.toml` defines workspace members:
```toml
[tool.uv.workspace]
members = ["packages/*", "apps/*"]
```

## Adding New Data Sources

Follow the standardized fetcher package pattern documented in README.md:

1. Create package in `packages/{source}-client/`
2. Implement `main(output_dir=None)` in `src/{source}_client/__init__.py`
3. Output to `{YYYY-MM-DD}_raw_{source}.json`
4. Add workspace dependency to `apps/pipeline-runner/pyproject.toml`
5. Create transformer in `packages/portfolio-app/src/portfolio_app/transformers/{source}_transform.py`
6. Update integrator to handle new source

See `packages/alchemy-client/` for reference implementation.

## Important Conventions

### File Naming
- Raw data: `{YYYY-MM-DD}_raw_{source}.json`
- Curated data: `{YYYY-MM-DD}_curated_{source}.json`
- Integrated portfolio: `{YYYY-MM-DD}_portfolio.csv`

### Data Access
Always use `get_data_dir()` from `transform_core` instead of hardcoding paths:
```python
from transform_core import get_data_dir
data_dir = get_data_dir()  # Respects PORTFOLIO_DATA_DIR env var
```

### Transformers Pattern
Each transformer should:
- Import `get_data_dir()` and relevant constants from `transform_core`
- Load from `{date}_raw_{source}.json`
- Apply filtering based on `FILTER_THRESHOLDS`
- Save to `{date}_curated_{source}.json`
- Be executable as `__main__`

### Integration Format
The integrator standardizes all sources into:
```python
{
    "source": str,      # "KSEI", "DeBank", "Binance", etc.
    "category": str,    # "Cash", "Equity", "Crypto", etc.
    "asset": str,       # Asset name/symbol
    "currency": str,    # "IDR", "USD", etc.
    "amount": float,    # Quantity
    "value_idr": float, # Value in IDR (or None)
    "value_usd": float, # Value in USD (or None)
    "account": str,     # Account identifier
    "details": str      # Additional context
}
```

## Python Version
Requires Python 3.12+ (specified in all `pyproject.toml` files)
