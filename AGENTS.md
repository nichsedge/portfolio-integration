# Portfolio Integration - AI Agent Guidelines

Universal guidelines for AI coding agents (Antigravity, Claude Code, Cursor, Copilot, Goose, Hermes, etc.) working in this repository.

---

## 🏛️ Ecosystem Role: Multi-Asset Investment Aggregator

`portfolio-integration` is the **Canonical Aggregator and ETL Engine for Multi-Asset Investments** in the workstation's Personal Data Architecture ([`~/Projects/DATA_ARCHITECTURE.md`](file:///home/al/Projects/DATA_ARCHITECTURE.md)):

* **SSOT for Investments**: Tracks Indonesian equities (KSEI), EVM DeFi (DeBank), CEX crypto (Binance), and Solana (Alchemy) inside canonical SQLite SSOT (`data/portfolio.db` with WAL mode).
* **Cash & P2P Intake**: Pulls cash and P2P lending balances from the `sansfinance` Android database snapshot on Cloudflare R2 (`sansfinance-fetch`).
* **WUDAS & R2 Sync**: Adheres to the Workstation Unified Data Architecture Standard. Avoids loose dated JSON files. Emits single-leaf `latest_snapshot.json` and `latest_ai_state.json`. Syncs `portfolio.db` bidirectionally with Cloudflare R2 (`db/portfolio_latest.sqlite`) via `uv run scripts/sync_r2.py [status|push|pull|auto]`.
* **Output to iERP**: Feeds high-level net worth and liquid cash totals into `ierp` (`events.db` `networth_snapshots`).
* **Boundary**: Do NOT track individual operational expenses, budgets, or cash pacing here (those belong in `sansfinance`). Do NOT track personal life events or contacts here (those belong in `ierp`).

---

## ⚠️ Testing Rule for AI Agents (CRITICAL)

When updating, debugging, or fixing a specific component or data source:
* **DO NOT run the full pipeline (`uv run run-all` or `--integrate`)** unless explicitly requested by the user.
* **ONLY test the specific component** you modified:
  * **DeBank**: `uv run debank-scrape`
  * **KSEI**: `uv run ksei dump`
  * **Binance**: `uv run binance-fetch`
  * **Alchemy**: `uv run alchemy-fetch`
  * **SansFinance**: `uv run sansfinance-fetch`
  * **DefiLlama**: `uv run llama-fetch <subcommand>` or `uv run pytest packages/defillama-client/tests/`
  * **Individual Transformer**: Test only the specific transformer file (e.g. `python packages/portfolio-app/src/portfolio_app/transformers/debank_transform.py`)

Running the full pipeline executes cloud uploads (GCS), triggers rate-limited APIs, and spawns unnecessary browser processes. Keep tests strictly scoped to the modified component.

---

## 🦙 DefiLlama Free API & Upstream Protocol

DefiLlama continuously releases new endpoints, modifies metrics, and refines routing. When working on `packages/defillama-client/`:
* **Canonical Upstream Reference**: Prior to adding, editing, or debugging endpoints, inspect:
  - **Root LLM Specs**: [`https://api-docs.defillama.com/llms.txt`](https://api-docs.defillama.com/llms.txt)
  - **Free Endpoints List**: [`https://api-docs.defillama.com/llms-free.txt`](https://api-docs.defillama.com/llms-free.txt)
  - **Free OpenAPI Specification**: [`https://api-docs.defillama.com/defillama-openapi-free.json`](https://api-docs.defillama.com/defillama-openapi-free.json)
* **Strict Free Tier Only**: Only consume public unauthenticated routes (`api.llama.fi`, `coins.llama.fi`, `yields.llama.fi`, `stablecoins.llama.fi`). NEVER route requests to `pro-api.llama.fi` without user API keys.
* **Rate-Limit Guard**: Honor caching (`cache_ttl >= 300`) to respect free-tier fair use limits (~300 req/min).

---

## Architecture & Multi-Repo Guidelines

This is a Python monorepo managed with `uv` implementing a 4-stage ETL pipeline for financial portfolio aggregation:

1. **Extract**: Fetch raw data from data sources:
   - **KSEI**: Standalone repository `github.com/nichsedge/ksei` (CLI: `ksei dump`)
   - **DeBank**: Standalone repository `github.com/nichsedge/debank-scraper` (CLI: `debank-scrape`)
   - **Binance**: `packages/binance-client` (CLI: `binance-fetch`)
   - **Alchemy**: `packages/alchemy-client` (CLI: `alchemy-fetch`)
   - **SansFinance**: `packages/sansfinance-client` (CLI: `sansfinance-fetch`) — pulls cash & P2P accounts from the Sans Finance app DB on Cloudflare R2
2. **Transform**: Clean and filter raw sources into curated JSON (`packages/portfolio-app/src/portfolio_app/transformers/`)
3. **Integrate & Enrich**: Merge curated sources, enrich each holding with real-world annual yields (`yield_rate` via `portfolio_app.yield_enricher`), persist to `data/portfolio.db` (SQLite SSOT), and emit unified snapshot JSON (`latest_snapshot.json`).
4. **Cloud Upload & Insights**: Upload daily snapshots to Cloudflare R2 (`snapshots/latest.json`), push DB to R2 (`db/portfolio_latest.sqlite`), and generate AI state digests (`latest_ai_state.json` & `latest_ai_digest.md`).

### Workspace Structure

```
packages/
├── alchemy-client/   # Solana token holdings fetcher
├── binance-client/   # Binance exchange client via CCXT
├── defillama-client/ # DefiLlama free API client (prices, yields, protocols, stables)
├── sansfinance-client/ # Cash & P2P accounts fetcher from R2
├── transform-core/   # Shared utilities (data dir resolution, parsing)
└── portfolio-app/    # Transformers, integrators, and MCP server

apps/
└── pipeline-runner/  # Main pipeline orchestrator
```

### Multi-Repo Dependency Rule
* `ksei` and `debank-scraper` are independent standalone repositories.
* **Do NOT** change `pyproject.toml` to use relative path editable dependencies (e.g., `path = "../ksei"`), as this breaks portability and CI/CD.
* Keep canonical Git sources in `pyproject.toml` (`git = "https://github.com/..."`) and upgrade revisions using `uv lock --upgrade-package <package>`.

---

## Common Commands

```bash
# Sync dependencies
uv sync

# Run specific fetchers only (PREFERRED when developing)
uv run debank-scrape
uv run ksei dump
uv run binance-fetch
uv run alchemy-fetch
uv run sansfinance-fetch
uv run llama-fetch prices "coingecko:ethereum"   # DefiLlama free API CLI

# Full pipeline options (Only run when explicitly requested)
uv run run-all         # Full pipeline: fetch + transform + integrate + GCS upload
uv run fetch-only      # Fetch all sources in parallel
uv run integrate-only  # Skip fetching, just transform and integrate

# AI Agent & MCP Integration (Hermes, Claude, Cursor, Goose, Antigravity)
uv run portfolio-mcp          # Run as stdio JSON-RPC 2.0 MCP server (default or --mcp)
uv run portfolio-mcp --audit    # Run automated portfolio health check
uv run portfolio-mcp --digest   # Output latest token-optimized Markdown brief
uv run portfolio-mcp --json     # Output latest token-optimized state JSON
uv run portfolio-ai-state       # Regenerate latest AI state and digest
uv run portfolio-advisor        # Quantitative advisor & 3-tier sovereign runway matrix (multi-cycle idx-bei signals)
uv run portfolio-advisor --markdown # Non-ANSI Markdown briefing for Telegram/cron
uv run portfolio-advisor --json     # Structured JSON payload for downstream apps
```

---

## Data Pipeline File Conventions

All data files use date-based naming in the configured data directory (from `PORTFOLIO_DATA_DIR` env var or `data/` default):

- **Raw output**: `YYYY-MM-DD_raw_<source>.json`
- **Curated output**: `YYYY-MM-DD_curated_<source>.json`
- **Final integrated**: `YYYY-MM-DD_portfolio.csv` & `YYYY-MM-DD_snapshot.json`
- **AI digest**: `latest_ai_state.json` & `latest_ai_digest.md`

### Standard Integration Schema
- `source`: Data source name (`ksei`, `debank`, `binance`, `alchemy`, etc.)
- `category`: Asset category (`equity`, `crypto`, `defi`, `cash`, etc.)
- `asset`: Asset symbol or ticker name
- `currency`: Asset denomination currency (`USD`, `IDR`, etc.)
- `amount`: Quantity held
- `value_idr`: Value converted to IDR
- `value_usd`: Value converted to USD
- `account`: Account or wallet identifier
- `details`: Additional metadata dictionary

---

## Adding a New Data Source

Follow the standardized fetcher package pattern:

1. **Create package structure** under `packages/<source>-client/` (or external repo for complex scrapers):
   - `pyproject.toml` with `[project.scripts].<source>-fetch` entrypoint.
   - Output naming: `{current_date}_raw_<source>.json`.
2. **Create transformer** in `packages/portfolio-app/src/portfolio_app/transformers/<source>_transform.py`:
   - Read raw `{date}_raw_<source>.json`.
   - Parse using `transform_core.utils.get_data_dir()` for directory paths.
   - Filter / clean data and output `{date}_curated_<source>.json`.
3. **Add integration function** in `packages/portfolio-app/src/portfolio_app/integrators/portfolio_integration.py`:
   - Implement `standardize_<source>_data()` returning records matching the schema.
   - Register in the main integration workflow.
4. **Register in pipeline** in `apps/pipeline-runner/src/pipeline_runner/__init__.py`:
   - Add fetch step to fetch phase.
   - Add transform module to transform phase list.

---

## Environment Variables

- `PORTFOLIO_DATA_DIR` (or `DATA_DIR`): Data directory path (defaults to `REPO_ROOT/data`)
- `KSEI_USERNAME` / `KSEI_PASSWORD`: KSEI login credentials
- `ETH_ADDRESS`: DeBank EVM wallet address
- `BINANCE_API_KEY` / `BINANCE_API_SECRET`: Binance API credentials
- `SOL_ADDRESS` / `ALCHEMY_API_KEY`: Alchemy Solana configuration
- `PORTFOLIO_GCS_BUCKET` (or `GCS_BUCKET_NAME`): Google Cloud Storage bucket destination

---

## Key Implementation Details

- **Data directory resolution**: All packages resolve paths through `transform_core.utils.get_data_dir()`, checking `PORTFOLIO_DATA_DIR` -> `DATA_DIR` -> `REPO_ROOT/data`.
- **Date handling**: Standardized on `datetime.now().strftime("%Y-%m-%d")`.
- **Process isolation**: The pipeline runner invokes fetchers via isolated subprocesses.
