# Portfolio Integration

Unified financial portfolio ETL pipeline and Model Context Protocol (MCP) server aggregating assets from Indonesian securities (KSEI), EVM DeFi (DeBank), centralized crypto exchanges (Binance), Solana wallets (Alchemy), and the Sans Finance app into standardized daily snapshots and AI-ready digests.

---

## Supported Data Sources

- **KSEI** (`ksei dump`): Indonesian Central Securities Depository equities, mutual funds, and cash balances.
- **DeBank** (`debank-scrape`): Multi-chain EVM wallet and DeFi protocol balances.
- **Binance** (`binance-fetch`): Centralized cryptocurrency exchange balances via CCXT.
- **Alchemy** (`alchemy-fetch`): Solana SPL token and native balance tracking via Alchemy RPC.
- **Sans Finance** (`sansfinance-fetch`): Bank cash, wallet cash, and P2P lending balances from the Sans Finance app DB (Cloudflare R2).
- **DefiLlama** (`llama-fetch`): Multi-chain token prices, live yield pools, protocol counterparty audits, and stablecoin market data via 100% free unauthenticated API ([upstream LLM docs](https://api-docs.defillama.com/llms.txt)).

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
│   ├── defillama-client/      # DefiLlama free API client (prices, yields, protocols, stables)
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

### Individual Data Fetchers & Crypto Intelligence

```bash
uv run debank-scrape    # Fetch EVM DeFi holdings
uv run ksei dump        # Fetch Indonesian equities / securities
uv run binance-fetch    # Fetch Binance balances
uv run alchemy-fetch    # Fetch Solana balances
uv run llama-fetch      # DefiLlama free API CLI (prices, yields, protocol, stables, fees)
```

### AI State & MCP Server

The repository includes a Model Context Protocol (MCP) server and token-optimized AI state generator for assistants (Antigravity, Claude, Cursor, Goose):

```bash
# Run stdio MCP server for AI assistants (default or with --mcp)
uv run portfolio-mcp

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

# Run quantitative portfolio advisor & 3-tier sovereign runway matrix (integrates with idx-bei)
uv run portfolio-advisor
uv run portfolio-advisor --markdown   # Clean Markdown brief for Telegram/cron
uv run portfolio-advisor --json       # Structured payload for downstream consumers
```

---

## Data Pipeline Flow & SQLite SSOT (WUDAS)

All portfolio data follows a standardized pipeline storing time-series and holdings in a canonical SQLite database:

1. **Extract**: Raw output saved to temporary `{YYYY-MM-DD}_raw_<source>.json`.
2. **Transform**: Normalized and curated into `{YYYY-MM-DD}_curated_<source>.json`.
3. **Integrate & Enrich**: Enriched with deterministic annual yield rates (`yield_rate` via `portfolio_app.yield_enricher` for SBN coupons, IDX dividends, P2P lending, and crypto staking), upserted into `data/portfolio.db` (SQLite with WAL mode), and emitted as `latest_snapshot.json`.
4. **Cloud & AI Digest**: Exported to `latest_ai_state.json`, `latest_ai_digest.md`, and bidirectionally synchronized with Cloudflare R2 (`db/portfolio_latest.sqlite` and `snapshots/latest.json`).

### Cloudflare R2 Bidirectional Sync

```bash
# Check sync status between local DB and Cloudflare R2
uv run scripts/sync_r2.py status

# Push local portfolio.db to R2 (atomic checkpointing + MD5 validation)
uv run scripts/sync_r2.py push

# Pull latest snapshot from R2
uv run scripts/sync_r2.py pull

# Auto-sync (checks timestamps, avoids unnecessary bandwidth)
uv run scripts/sync_r2.py auto
```

---

## Sans Finance (Cash & P2P Accounts)

Off-chain cash and P2P lending balances are sourced from the Sans Finance Android
app database via the `sansfinance-fetch` CLI (`packages/sansfinance-client/`),
which downloads the latest SQLite snapshot from Cloudflare R2 and emits
`{YYYY-MM-DD}_raw_sansfinance.json`. Portfolio holdings stored in the app are
deliberately excluded — they originate from KSEI / DeBank / Binance / Alchemy in
this same pipeline, so re-importing them would double-count.

---

## License

This project is licensed under the [MIT License](LICENSE).