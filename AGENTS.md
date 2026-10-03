# Portfolio Integration - AI Agent Guidelines

Universal guidelines for AI coding agents (Antigravity, Claude Code, Cursor, Copilot, Goose, Hermes, etc.) working in this repository.

---

## 🏛️ Ecosystem Role: Multi-Asset Investment Aggregator

`portfolio-integration` is the **Canonical Aggregator and ETL Engine for Multi-Asset Investments** in the workstation's Personal Data Architecture ([`~/Projects/DATA_ARCHITECTURE.md`](file:///home/al/Projects/DATA_ARCHITECTURE.md)):

* **SSOT for Investments**: Tracks Indonesian equities & SBN Sukuk (KSEI), EVM DeFi (DeBank), CEX crypto (Binance), Solana (Alchemy), and cash/P2P lending (SansFinance) inside canonical SQLite SSOT (`data/portfolio.db` with WAL mode).
* **Cash & P2P Intake**: Pulls cash and P2P lending balances from the `sansfinance` Android database snapshot on Cloudflare R2 (`portfolio fetch sansfinance`).
* **WUDAS & R2 Sync**: Adheres to the Workstation Unified Data Architecture Standard. Avoids loose dated JSON files. Emits single-leaf `latest_snapshot.json` and `latest_ai_state.json`. Syncs `portfolio.db` bidirectionally with Cloudflare R2 (`db/portfolio_latest.sqlite`) via `portfolio r2 push`.
* **Output to iERP**: Feeds high-level net worth and liquid cash totals into `ierp` (`events.db` `networth_snapshots`).
* **Owned Assets vs Market Intelligence Boundary**: Strictly separate assets you own (`amount > 0` stored in `portfolio.db`) from external market intelligence / decision support feeds (`idx-bei`). Market catalogs must NEVER be ingested into `portfolio.db` or counted toward net worth.
* **Pure Go Architecture**: The entire pipeline, ETL engine, SQLite SSOT, AI state generator, and Model Context Protocol (MCP) server are implemented in pure Go (Go 1.22+). The previous Python implementation is permanently archived on branch `python-archive`.

---

## ⚠️ Testing Rule for AI Agents (CRITICAL)

When updating, debugging, or fixing a specific component or data source:
* **DO NOT run the full pipeline (`portfolio run-all`)** unless explicitly requested by the user.
* **ONLY test the specific component** you modified:
  * **Unit Tests**: `go test -v ./pkg/...`
  * **KSEI**: `portfolio fetch ksei`
  * **SansFinance**: `portfolio fetch sansfinance`
  * **DeBank**: `debank-scrape <eth_address> -o <target_file>` or `portfolio fetch debank`
  * **Integrator**: `portfolio integrate --date <YYYY-MM-DD>`
  * **AI State & ADHD Suite**: `portfolio ai-state`
  * **Sovereign Runway Advisor**: `portfolio advisor [--markdown|--json]`
  * **MCP Server**: `echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | portfolio mcp`

Running the full pipeline executes cloud uploads (Cloudflare R2), triggers rate-limited APIs, and spawns unnecessary browser processes. Keep tests strictly scoped to the modified component.

---

## Monorepo Architecture & Packages

```text
portfolio-integration/
├── cmd/
│   ├── portfolio/            # Main unified CLI (run-all, fetch, integrate, ai-state, advisor, mcp, r2)
│   └── debank-scrape/        # Headless Chromium DeBank scraper CLI
├── pkg/
│   ├── advisor/              # 3-tier sovereign runway matrix & tactical advisor
│   ├── aistate/              # Token-efficient AI state, ADHD Focus Suite & markdown digest generator
│   ├── db/                   # Canonical SQLite SSOT (WAL mode, schema migrations)
│   ├── enricher/             # Yield enrichment engine (SBN coupons, crypto staking, bank cash rates)
│   ├── fetchers/
│   │   ├── alchemy/          # Solana SPL token & SOL balance client (JSON-RPC)
│   │   ├── binance/          # Binance REST client (HMAC-SHA256 authenticated)
│   │   ├── debank/           # DeBank EVM scraper (chromedp & raw loader)
│   │   ├── ksei/             # KSEI equities, mutual funds & SBN client (goksei)
│   │   └── sansfinance/      # SansFinance bank cash & P2P lending client (Cloudflare R2 SQLite)
│   ├── fx/                   # Exchange rate engine (Bank Indonesia & Yahoo FX with fallbacks)
│   ├── integrator/           # Holding normalization, classification & snapshot aggregation
│   ├── mcp/                  # stdio Model Context Protocol (MCP) server
│   ├── models/               # Core data structures (Snapshot, Holding, Allocation)
│   └── r2/                   # Cloudflare R2 / S3 storage uploader
├── data/                     # Local data storage (portfolio.db, snapshots, digests)
├── AGENTS.md                 # Agent guidelines and workstation integration rules
└── go.mod                    # Root Go module definition
```

---

## Common Commands

```bash
# Build and install binaries
go install ./cmd/...

# Run specific fetchers only (PREFERRED when developing)
portfolio fetch ksei
portfolio fetch sansfinance
portfolio fetch binance
portfolio fetch alchemy
portfolio fetch debank

# Integration & State Generation
portfolio integrate             # Integrate existing raw data into JSON snapshot and SQLite SSOT
portfolio ai-state              # Regenerate latest AI state and digest
portfolio advisor               # Sovereign runway matrix & tactical recommendations
portfolio advisor --markdown    # Non-ANSI Markdown briefing for Telegram/cron
portfolio advisor --json        # Structured JSON payload (includes ADHD Focus Suite)

# AI Agent & MCP Integration (Claude, Cursor, Antigravity, Hermes)
portfolio mcp                   # Run as stdio JSON-RPC 2.0 MCP server

# Cloudflare R2 Operations
portfolio r2 push               # Push SQLite database to Cloudflare R2
portfolio r2 status             # Check R2 connection status

# Run full pipeline (Only run when explicitly requested)
portfolio run-all               # Full pipeline: fetch + enrich + integrate + ai-state + R2 upload
```

---

## Data Pipeline File Conventions

All data files use date-based naming in the configured data directory (from `PORTFOLIO_DATA_DIR` env var or `data/` default):

- **Raw output**: `YYYY-MM-DD_raw_<source>.json`
- **Curated output**: `YYYY-MM-DD_curated_<source>.json`
- **Final integrated snapshot**: `YYYY-MM-DD_snapshot.json` & `latest_snapshot.json`
- **AI state & digest**: `latest_ai_state.json` & `latest_ai_digest.md`
- **Advisor payload**: `latest_advisor.json`
- **SQLite SSOT**: `portfolio.db`

### Standard Integration Schema (`models.Holding`)
- `source`: Data source name (`ksei`, `debank`, `binance`, `alchemy`, `sansfinance`)
- `category`: Asset category (`SBN`, `Indo Stocks`, `Spot`, `Bank Account`, etc.)
- `asset`: Asset symbol or ticker name
- `currency`: Asset denomination currency (`USD`, `IDR`, etc.)
- `quantity`: Quantity held
- `value_idr`: Value converted to IDR
- `value_usd`: Value converted to USD
- `asset_class`: Broad asset class (`Fixed Income`, `Equities`, `Crypto`, `Cash & Equivalents`, `Commodities`)
- `yield_rate`: Real-world annual yield (e.g. 0.064 for 6.4% Sukuk, 0.06 for digital bank)
- `allocation_percentage`: Percentage of total assets
- `account`: Account or wallet identifier
- `details`: Additional metadata string

---

## Environment Variables

- `PORTFOLIO_DATA_DIR` (or `DATA_DIR`): Data directory path (defaults to `REPO_ROOT/data`)
- `KSEI_USERNAME` / `KSEI_PASSWORD`: KSEI login credentials
- `ETH_ADDRESS`: DeBank EVM wallet address
- `BINANCE_API_KEY` / `BINANCE_API_SECRET`: Binance API credentials
- `SOL_ADDRESS` / `ALCHEMY_API_KEY`: Alchemy Solana configuration
- `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`: Cloudflare R2 credentials
