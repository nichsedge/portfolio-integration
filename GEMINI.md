# Portfolio Integration - Gemini & AI Agent Guidelines

## ⚠️ Testing Rule for AI Agents (CRITICAL)

When updating, debugging, or fixing a specific component or data source:
* **DO NOT run the full pipeline (`uv run run-all` or `--integrate`)** unless explicitly requested by the user.
* **ONLY test the specific component** you modified (use `secrun` for API keys):
  * **DeBank**: `secrun uv run debank-scrape`
  * **KSEI**: `secrun uv run ksei dump`
  * **Binance**: `secrun uv run binance-fetch`
  * **Alchemy**: `secrun uv run alchemy-fetch`
  * **Transformer**: Run only the specific transformer file (e.g. `python packages/portfolio-app/src/portfolio_app/transformers/debank_transform.py`)

Running the full pipeline uploads to GCS, consumes rate limits on third-party APIs, and launches browser scrapers unnecessarily. Keep testing isolated to the target component.
