# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture Overview

This is a Python monorepo managed with `uv` that implements a 3-stage ETL pipeline for aggregating financial portfolio data from multiple platforms:

1. **Extract:** Fetch raw data from automated sources (KSEI, DeBank, Binance, Alchemy)
2. **Transform:** Clean and filter each source into a curated format
3. **Load:** Integrate all sources into a unified portfolio CSV and snapshot JSON
4. **Visualize:** Generate portfolio insights, plots, and AI state digest

### Workspace Structure

```
packages/          # Independent uv packages
├── ksei-client/   # Indonesian securities API (Python)
├── debank-scraper/# DeFi portfolio (Node.js/Playwright)
├── binance-client/# Crypto exchange via CCXT (Python)
├── alchemy-client/# Solana token holdings (Python)
├── transform-core/# Shared utilities (data dir resolution, parsing)
└── portfolio-app/ # Transformers + integrators

apps/
└── pipeline-runner/ # Main pipeline orchestrator
```

When working across packages, use `sys.path.insert(0, str(repo_root / "packages"))` to enable imports (see pipeline_runner/__init__.py:22). REPO_ROOT is computed as `Path(__file__).resolve().parents[4]` from the pipeline_runner.

## ⚠️ Testing Rule for AI Agents (CRITICAL)

When updating, debugging, or modifying a specific component:
* **DO NOT run `uv run run-all`** (it triggers GCS uploads and calls all external APIs unnecessarily).
* **ONLY test the individual component you touched:**
  * **DeBank**: `uv run debank-scrape`
  * **KSEI**: `uv run ksei dump`
  * **Binance**: `uv run binance-fetch`
  * **Alchemy**: `uv run alchemy-fetch`

## Common Commands

```bash
# Install/update dependencies
uv sync

# Individual fetchers (PREFERRED for development & testing)
uv run debank-scrape
uv run ksei dump
uv run binance-fetch
uv run alchemy-fetch

# Full pipeline options (ONLY when explicitly requested)
uv run run-all         # Full pipeline: fetch + transform + integrate + GCS upload
uv run fetch-only      # Only fetch raw data for all sources
uv run integrate-only  # Skip fetching, just transform/integrate

# AI Agent & MCP Integration (Hermes, Claude, Cursor, Goose)
uv run portfolio-mcp --audit    # Run automated portfolio health check
uv run portfolio-mcp --digest   # Output latest token-optimized Markdown brief
uv run portfolio-mcp --json     # Output latest token-optimized state JSON
uv run portfolio-mcp --mcp      # Run as stdio JSON-RPC 2.0 MCP server
uv run portfolio-ai-state       # Regenerate latest AI state and digest
```

## Data Pipeline File Conventions

All data files use date-based naming in the configured data directory (from `PORTFOLIO_DATA_DIR` env var or `data/` default):

- Raw output: `YYYY-MM-DD_raw_<source>.json`
- Curated output: `YYYY-MM-DD_curated_<source>.json`
- Final integrated: `YYYY-MM-DD_portfolio.csv` & `YYYY-MM-DD_snapshot.json`
- AI digest: `latest_ai_state.json` & `latest_ai_digest.md`

The standard integration schema is:
- `source` - Data source name
- `category` - Asset category (equity, crypto, defi, etc.)
- `asset` - Asset name/symbol
- `currency` - Asset currency
- `amount` - Quantity held
- `value_idr` - Value in IDR
- `value_usd` - Value in USD
- `account` - Account identifier
- `details` - Additional metadata

## Adding a New Data Source

Follow the standardized fetcher package pattern:

1. **Create package structure** under `packages/<source>-client/` with:
   - `pyproject.toml` with `[project.scripts].<source>-fetch` entrypoint
   - `src/<source>_client/fetcher.py` with `main(output_dir=None)` function
   - Output file naming: `{current_date}_raw_<source>.json`

2. **Create transformer** in `packages/portfolio-app/transformers/<source>_transform.py`:
   - Read raw `{date}_raw_<source>.json`
   - Parse using `transform_core.utils.get_data_dir()` for paths
   - Filter using `FILTER_THRESHOLDS` from transform_core (if needed)
   - Output `{date}_curated_<source>.json`

3. **Add integration function** in `packages/portfolio-app/integrators/portfolio_integration.py`:
   - `standardize_<source>_data()` returns list of dicts matching the schema
   - Register in main integration flow

4. **Add to pipeline** in `apps/pipeline-runner/src/pipeline_runner/__init__.py`:
   - Add fetch step in Step 1
   - Add transform file in `transform_files` list in Step 2

## Environment Variables

- `PORTFOLIO_DATA_DIR` (or `DATA_DIR`) - Data directory path
- `KSEI_USERNAME` / `KSEI_PASSWORD` - KSEI credentials
- `EVM_ADDRESS` - DeBank wallet address
- `BINANCE_API_KEY` / `BINANCE_API_SECRET` - Binance API
- `WALLET_ADDRESS` / `ALCHEMY_API_KEY` - Alchemy configuration

## Key Implementation Details

- **Data directory resolution**: All packages use `transform_core.utils.get_data_dir()` which checks `PORTFOLIO_DATA_DIR` → `DATA_DIR` → default `REPO_ROOT/data`
- **Date handling**: All files use `datetime.now().strftime("%Y-%m-%d")` for consistent naming
- **Pipelines**: The pipeline-runner executes fetchers as subprocesses for isolation; transforms run via direct Python execution
- **Node.js scrapers**: DeBank scraper uses Playwright and `npm run scrape` commands