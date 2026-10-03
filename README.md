# Portfolio Integration (Go)

High-performance native Go aggregator, ETL engine, and Model Context Protocol (MCP) server for multi-asset investments. Unifies Indonesian equities and SBN Sukuk (KSEI), EVM DeFi (DeBank), centralized crypto exchanges (Binance), Solana wallets (Alchemy), and cash/P2P balances (Sans Finance) into standardized daily snapshots, SQLite SSOT, and token-optimized AI advisor state representations.

> 📦 **Legacy Python Codebase**: The previous Python implementation is permanently preserved on the [`python-archive`](https://github.com/nichsedge/portfolio-integration/tree/python-archive) branch.

---

## 🏛️ Architecture & Ecosystem Role

`portfolio-integration` serves as the **Canonical Multi-Asset Aggregator and Ingestion Engine** in the workstation's Personal Data Architecture:

1. **SSOT for Investments**: Persists all owned holdings into canonical SQLite SSOT (`data/portfolio.db` with WAL mode).
2. **Single-Leaf Snapshots**: Adheres to WUDAS (Workstation Unified Data Architecture Standard). Emits single-leaf snapshots:
   - `data/latest_snapshot.json`
   - `data/latest_ai_state.json`
   - `data/latest_ai_digest.md`
   - `data/latest_advisor.json`
3. **Cloudflare R2 Synchronization**: Syncs snapshots and SQLite database bidirectionally with Cloudflare R2 (`db/portfolio_latest.sqlite`).
4. **AI State & Model Context Protocol (MCP)**: Native JSON-RPC 2.0 stdio MCP server for agentic AI pairing (Claude Code, Cursor, Antigravity, Hermes Agent). Includes the **ADHD Focus Suite** (Clutter Sweeper, SBN Reinvestment Playbook, Deposit Router, Autonomous Vault).

---

## 📂 Project Structure

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

## ⚡ Quick Start

### Prerequisites
- Go 1.22+ (tested with Go 1.26)
- Chromium / Google Chrome installed (for headless DeBank scraping)

### Installation

```bash
# Clone the repository
git clone https://github.com/nichsedge/portfolio-integration.git
cd portfolio-integration

# Install binaries into $HOME/go/bin
go install ./cmd/...
```

Ensure `$HOME/go/bin` is in your `$PATH`.

---

## 🛠️ CLI Usage

### 1. Full Multi-Asset Pipeline
Fetches from all 5 sources, enriches yield rates, normalizes holdings, writes SQLite SSOT, generates AI state & digest, and uploads to Cloudflare R2:

```bash
portfolio run-all
```

Options:
- `--date YYYY-MM-DD`: Custom snapshot date (defaults to today)
- `--no-upload`: Skip Cloudflare R2 cloud backup

### 2. Selective Fetching
Fetch a single source without running the whole pipeline:

```bash
portfolio fetch ksei
portfolio fetch sansfinance
portfolio fetch binance
portfolio fetch alchemy
portfolio fetch debank
```

### 3. Integration & Normalization
Integrate already fetched raw files into consolidated snapshots and SQLite:

```bash
portfolio integrate
portfolio integrate --date 2026-10-01
```

### 4. AI State & ADHD Focus Suite
Regenerate `latest_ai_state.json` and `latest_ai_digest.md`:

```bash
portfolio ai-state
```

Features:
- **Clutter Sweeper**: Flags micro-holdings (<1% NW) with zero-friction consolidation directives.
- **SBN Reinvestment Playbook**: Pre-commits allocation plan for maturing Sukuk (e.g. ST013T2) to protect cashflow.
- **Autonomous Vault**: Segregates locked sovereign compounding capital from active liquidity.
- **Deposit Router**: Outputs unambiguous 1-step DCA directive based on target drift.

### 5. Sovereign Wealth & Runway Advisor
Run quantitative advisor analysis:

```bash
portfolio advisor               # Formatted terminal overview
portfolio advisor --markdown    # Clean markdown report (for notes, Telegram, cron)
portfolio advisor --json        # Structured JSON payload (latest_advisor.json)
```

### 6. Model Context Protocol (MCP) Server
Launch the JSON-RPC stdio MCP server for AI coding agents:

```bash
portfolio mcp
```

Exposed MCP tools:
- `get_portfolio_overview`: Summary balances, net worth, asset allocation.
- `get_holdings_breakdown`: Query holdings with optional category/source filters.
- `get_ai_state`: Token-optimized financial state JSON.
- `get_adhd_action_card`: Instant zero-friction deposit & clutter directives.
- `audit_portfolio`: Risk alerts, clutter rating, and maturity calendar.
- `get_rebalancing_plan`: Deposit simulation to eliminate target drift.
- `get_sovereign_runway`: 3-tier sovereign runway matrix.
- `get_upcoming_cashflow`: SBN monthly coupon calendar & maturity horizon.

---

## 🧪 Testing

Run all unit tests across all packages:

```bash
go test -v ./...
```