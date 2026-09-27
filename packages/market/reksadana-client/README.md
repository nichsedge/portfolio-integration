# Reksa Dana Client (`reksadana-client`)

Quantitative client and ETL fetcher for Indonesian Mutual Funds (*Reksa Dana*).

---

## ⚡ Features

- **Full Indonesian Mutual Fund Universe**: Ingests all 150+ mutual funds across top 17 Investment Managers (Sucorinvest, Batavia, Mandiri, Manulife, Bahana, Sinarmas, Trimegah, BNP Paribas, Schroder, etc.).
- **Institutional Quality Data**: Real-time NAV, AUM, CAGR (1Y, 3Y, 5Y), Max Drawdown, Expense Ratios, Asset Allocations, and Top 10 Securities Breakdown.
- **Quantitative Screener (`reksadana-screen`)**: Terminal ranking and filtering by Calmar ratio, Sharpe proxy, CAGR, downside volatility, Sharia compliance, and minimum fund size.
- **Unified Pipeline Storage**: Saves `{YYYY-MM-DD}_raw_reksadana.json` and canonical `reksadana_catalog.json` into configured data directory.

---

## 🚀 CLI Usage

```bash
# Fetch latest universe and update data/reksadana_catalog.json
uv run reksadana-fetch

# Screen top Money Market funds (0% Drawdown, lowest expense ratio)
uv run reksadana-screen --type pasar_uang

# Screen top Fixed Income / Obligasi funds sorted by 1Y CAGR
uv run reksadana-screen --type obligasi --sort cagr_1y

# Screen Sharia funds with AUM > Rp 500 Billion
uv run reksadana-screen --sharia --min-aum 500b

# Deep-dive into a specific fund (holdings & asset allocation)
uv run reksadana-screen --detail "Danamas Stabil"

# Output structured JSON for downstream pipelines
uv run reksadana-screen --type pasar_uang --json
```
