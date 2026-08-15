# Portfolio Integration - Agent Guidelines

## ⚠️ Testing Rule for AI Agents (CRITICAL)

When updating, debugging, or fixing a specific component or data source:
* **DO NOT run the full pipeline (`secrun uv run run-all` or `--integrate`)** unless explicitly requested by the user.
* **ONLY test the specific component** you modified (always prepend with `secrun` for API keys & secrets):
  * **DeBank**: `secrun uv run debank-scrape`
  * **KSEI**: `secrun uv run ksei dump`
  * **Binance**: `secrun uv run binance-fetch`
  * **Alchemy**: `secrun uv run alchemy-fetch`
  * **Individual Transformer**: Test only the specific transformer file (e.g., `python packages/portfolio-app/src/portfolio_app/transformers/debank_transform.py`)

Running the full pipeline executes cloud uploads (GCS), triggers rate-limited APIs, and spawns unnecessary browser processes. Keep tests strictly scoped to the modified component.

---

## Secret Management (`secrun`)

Secrets (API keys, credentials, usernames/passwords) are managed via `secrun`:
* **Command**: Prepend `secrun` to any command that requires secrets (e.g. `secrun uv run ksei dump`).
* **Mechanism**: Decrypts `~/.config/secrets/secrets.enc.env` in memory using `sops exec-env` (via age key at `~/.config/sops/age/keys.txt`), falling back to `~/.secrets` if SOPS is not available.
* **Executable**: Located at `~/.local/bin/secrun`.

---

## Architecture & Multi-Repo Guidelines

This is a Python monorepo managed with `uv` that implements an ETL pipeline for portfolio aggregation:

1. **Extract**: Fetch raw data from data sources:
   - **KSEI**: Standalone repository `github.com/nichsedge/ksei` (CLI: `ksei dump`)
   - **DeBank**: Standalone repository `github.com/nichsedge/debank-scraper` (CLI: `debank-scrape`)
   - **Binance**: `packages/binance-client` (CLI: `binance-fetch`)
   - **Alchemy**: `packages/alchemy-client` (CLI: `alchemy-fetch`)
2. **Transform**: `packages/portfolio-app/src/portfolio_app/transformers/`
3. **Integrate**: `packages/portfolio-app/src/portfolio_app/integrators/portfolio_integration.py`
4. **Cloud Upload & Insights**: Uploads daily snapshot JSON/CSV to Google Cloud Storage.

### Multi-Repo Dependency Rule
* `ksei` and `debank-scraper` are independent standalone repositories.
* **Do NOT** change `pyproject.toml` to use relative path editable dependencies (e.g., `path = "../ksei"`), as this breaks portability and CI/CD.
* Keep canonical Git sources in `pyproject.toml` (`git = "https://github.com/..."`) and upgrade revisions using `uv lock --upgrade-package <package>`.

---

## Common Commands

```bash
# Sync dependencies
uv sync

# Run specific fetchers only (PREFERRED when developing, use secrun for API keys)
secrun uv run debank-scrape
secrun uv run ksei dump
secrun uv run binance-fetch
secrun uv run alchemy-fetch

# Full pipeline options (Only run when explicitly requested)
secrun uv run run-all         # Full pipeline: fetch + transform + integrate + GCS upload
secrun uv run fetch-only      # Fetch all sources in parallel
secrun uv run integrate-only  # Skip fetching, just transform and integrate

# AI Agent & MCP Integration (Hermes, Claude, Cursor, Goose)
uv run portfolio-mcp --audit    # Run automated portfolio health check
uv run portfolio-mcp --digest   # Output latest token-optimized Markdown brief
uv run portfolio-mcp --json     # Output latest token-optimized state JSON
uv run portfolio-mcp --mcp      # Run as stdio JSON-RPC 2.0 MCP server
uv run portfolio-ai-state       # Regenerate latest AI state and digest
```
