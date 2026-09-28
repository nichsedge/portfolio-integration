# Portfolio Integration

Unified financial portfolio ETL pipeline and Model Context Protocol (MCP) server aggregating assets from Indonesian securities (KSEI), EVM DeFi (DeBank), centralized crypto exchanges (Binance), Solana wallets (Alchemy), and the Sans Finance app into standardized daily snapshots and AI-ready digests.

---

## Architecture & Data Categorization

The pipeline strictly separates **Owned Portfolio Assets** from **Market Intelligence & Decision Support**:

### 1. 💼 Personal Portfolio Holdings (What You Own)
*Ingested into the canonical SQLite SSOT (`data/portfolio.db`), aggregated into daily net worth snapshots, and fed into iERP.*
- **KSEI** (`ksei dump`): Indonesian Central Securities Depository equities, mutual fund units, and SBN bonds.
- **DeBank** (`debank-scrape`): Multi-chain EVM wallet balances and active DeFi protocol positions.
- **Binance** (`binance-fetch`): Centralized cryptocurrency exchange balances via CCXT.
- **Alchemy** (`alchemy-fetch`): Solana SPL token and native balance tracking via Alchemy RPC.
- **Sans Finance** (`sansfinance-fetch`): Bank cash, wallet cash, and P2P lending balances from the Sans Finance app DB (Cloudflare R2).

### 2. 🧠 Market Intelligence & Decision Support (What the Market Offers)
*Yardsticks, screeners, and benchmark feeds used exclusively by `portfolio-advisor` and `portfolio-mcp` for capital allocation decisions.*
- **Reksa Dana Indonesia** (`reksadana-fetch` & `reksadana-screen`): Complete Indonesian mutual fund market universe (150+ funds across 17 tier-1 asset managers), live NAV, AUM, historical CAGR, Max Drawdown, Expense Ratios, and underlying holdings.
- **DefiLlama** (`llama-fetch`): Multi-chain token prices, live yield pools, protocol counterparty audits, and stablecoin market data via 100% free unauthenticated API ([upstream LLM docs](https://api-docs.defillama.com/llms.txt)).
- **IDX-BEI** (DuckDB / MCP): Parquet datasets for Indonesian stock fundamentals, broker accumulation/distribution, and corporate actions.

---

## Monorepo Architecture

Managed with [`uv`](https://github.com/astral-sh/uv) workspace:

```
portfolio-integration/
├── apps/
│   └── pipeline-runner/          # Pipeline orchestrator and batch ETL runner
├── packages/
│   ├── assets/                   # Personal portfolio holdings & connectors (What You Own)
│   │   ├── alchemy-client/       # Solana SPL token & native balance fetcher
│   │   ├── binance-client/       # Binance exchange client via CCXT
│   │   └── sansfinance-client/   # Cash & P2P accounts fetcher from R2
│   ├── market/                   # Market intelligence & decision support (What The Market Offers)
│   │   ├── defillama-client/     # DefiLlama free API client (prices, yields, protocols, stables)
│   │   └── reksadana-client/     # Indonesian mutual funds ETL and quantitative screener
│   └── core/                     # Shared kernel & processing engines
│       ├── transform-core/       # Shared parsing and data directory resolution utilities
│       └── portfolio-app/        # Transformers, SQLite SSOT integrator, MCP server & Advisor
├── data/                         # Local storage: portfolio.db, latest_snapshot.json, market_*.json
├── AGENTS.md                     # Universal AI coding guidelines
└── pyproject.toml                # Root uv workspace coordinator
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
uv run reksadana-fetch  # Fetch complete Indonesian mutual funds universe (Bibit API)
uv run reksadana-screen # Quantitative screener for Indonesian mutual funds (PU, OB, SH, CP)
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

# Output zero-friction ADHD action card (DCA target, dust cleaning, SBN rollover)
uv run portfolio-mcp --adhd

# Regenerate latest AI state and digest directly
uv run portfolio-ai-state

# Launch interactive terminal portfolio dashboard
uv run portfolio-dashboard

# Run quantitative portfolio advisor & 3-tier sovereign runway matrix (integrates with idx-bei)
uv run portfolio-advisor
uv run portfolio-advisor --markdown   # Clean Markdown brief for Telegram/cron
uv run portfolio-advisor --json       # Structured payload for downstream consumers (SansFinance / iERP)
```

### ADHD Focus & Cognitive Simplicity Suite

Built into `portfolio-advisor`, `portfolio-ai-state`, and `portfolio-mcp` to eliminate analysis paralysis and cognitive overload:
- **🧹 Clutter & Dust Sweeper Audit**: Detects fragmented micro-holdings (<1% of NW or <Rp 3M) across multiple brokerages/wallets, calculates a 0-100 Cognitive Clutter Score, and provides 1-step sweeping instructions.
- **🎯 Autopilot SBN Reinvestment Playbook**: Flags maturing Sukuk/SBN series (e.g. ST013T2 Rp 61M in November 2026), quantifies lost monthly cashflow, and pre-commits an exact rebalancing allocation split.
- **⚡ Zero-Brain Deposit Router**: Replaces complex allocation math with a single, unambiguous next action (e.g. *"Deposit Rp 5,000,000 into Equities (Stockbit -> SRI-KEHATI). Zero debate."*).
- **🧘 Autonomous Vault vs Actionable Wealth**: Classifies locked compounding assets (state Sukuk) into an autonomous layer, reassuring the user that ~47% of their wealth is compounding on autopilot.


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