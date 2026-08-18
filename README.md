# Portfolio Integration

Unified financial portfolio ETL pipeline and Model Context Protocol (MCP) server aggregating assets from Indonesian securities (KSEI), EVM DeFi (DeBank), centralized crypto exchanges (Binance), Solana wallets (Alchemy), and manual tracking into standardized daily snapshots and AI-ready digests.

---

## Supported Data Sources

- **KSEI** (`ksei dump`): Indonesian Central Securities Depository equities, mutual funds, and cash balances.
- **DeBank** (`debank-scrape`): Multi-chain EVM wallet and DeFi protocol balances.
- **Binance** (`binance-fetch`): Centralized cryptocurrency exchange balances via CCXT.
- **Alchemy** (`alchemy-fetch`): Solana SPL token and native balance tracking via Alchemy RPC.
- **Manual CSV** (`_manual_balances.csv`): Off-chain assets (bank accounts, cash, physical commodities).

---

## Monorepo Architecture

Managed with [`uv`](https://github.com/astral-sh/uv) workspace:

```
portfolio-integration/
├── apps/
│   └── pipeline-runner/       # Pipeline orchestrator and batch commands
├── packages/
│   ├── alchemy-client/        # Solana token holdings fetcher
│   ├── binance-client/        # Binance exchange client via CCXT
│   ├── transform-core/        # Shared parsing and data directory utilities
│   └── portfolio-app/         # Transformers, integrators, MCP server & AI state tools
├── AGENTS.md                  # Guidelines for AI coding assistants
└── pyproject.toml             # Root workspace coordinator
```

---

## Quick Start

### Prerequisites

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) for workspace and dependency management

### Installation

```bash
# Clone the repository
git clone https://github.com/nichsedge/portfolio-integration.git
cd portfolio-integration

# Sync workspace virtualenv and dependencies
uv sync
```

### Configuration

Copy `.env.template` to `.env` and fill in the required credentials:

```bash
cp .env.template .env
```

| Variable | Description |
|---|---|
| `PORTFOLIO_DATA_DIR` | Directory where daily JSON snapshots & CSVs are stored (default: `data/`) |
| `KSEI_USERNAME` / `KSEI_PASSWORD` | KSEI account credentials |
| `ETH_ADDRESS` | EVM address for DeBank DeFi scraping |
| `BINANCE_API_KEY` / `BINANCE_API_SECRET` | Binance read-only API credentials |
| `SOL_ADDRESS` / `ALCHEMY_API_KEY` | Solana address and Alchemy API key |
| `PORTFOLIO_GCS_BUCKET` | Optional Google Cloud Storage bucket for cloud sync |

---

## CLI & Pipeline Usage

### Full Pipeline Orchestration

```bash
# Full pipeline: Fetch all sources -> Transform -> Integrate -> Cloud Sync & AI Digest
uv run run-all

# Fetch raw data only across all sources in parallel
uv run fetch-only

# Transform and integrate without re-fetching
uv run integrate-only
```

### Individual Data Fetchers

```bash
uv run debank-scrape    # Fetch EVM DeFi holdings
uv run ksei dump        # Fetch Indonesian equities / securities
uv run binance-fetch    # Fetch Binance balances
uv run alchemy-fetch    # Fetch Solana balances
```

### AI State & MCP Server

The repository includes a Model Context Protocol (MCP) server and token-optimized AI state generator for assistants (Antigravity, Claude, Cursor, Goose):

```bash
# Run stdio MCP server for AI assistants
uv run portfolio-mcp --mcp

# Generate token-optimized Markdown brief
uv run portfolio-mcp --digest

# Output latest state JSON
uv run portfolio-mcp --json

# Run automated portfolio health check
uv run portfolio-mcp --audit

# Regenerate latest AI state and digest directly
uv run portfolio-ai-state

# Launch interactive terminal portfolio dashboard
uv run portfolio-dashboard
```

---

## Data Pipeline Flow

All data follows a standardized 4-stage pipeline:

1. **Extract**: Raw output saved to `{YYYY-MM-DD}_raw_<source>.json`.
2. **Transform**: Normalized and curated into `{YYYY-MM-DD}_curated_<source>.json`.
3. **Integrate**: Merged with optional `_manual_balances.csv` into unified `{YYYY-MM-DD}_portfolio.csv` & `{YYYY-MM-DD}_snapshot.json`.
4. **Cloud & AI Digest**: Uploaded to Google Cloud Storage (if configured) and rendered into `latest_ai_state.json` & `latest_ai_digest.md`.

---

## Manual Asset Tracking

For assets without API access (e.g. physical gold, savings accounts), create a `_manual_balances.csv` in your `PORTFOLIO_DATA_DIR`:

```csv
source,category,asset,currency,amount,value_idr,value_usd,account,details
Manual,cash,BCA,IDR,5000000,5000000,,Checking,Savings Account
Manual,precious_metal,Gold,IDR,10,13500000,,Safe,Physical 10g Bar
```

---

## License

This project is licensed under the [MIT License](LICENSE).