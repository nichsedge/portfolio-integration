# DefiLlama Client

Lightweight Python client and CLI tool for the **100% Free DefiLlama API** (`https://api.llama.fi`, `https://coins.llama.fi`, `https://yields.llama.fi`, `https://stablecoins.llama.fi`).

Provides unauthenticated, zero-cost access to:
- Multi-chain token prices (`/prices/current/{coins}`)
- DeFi yield pools and APYs (`/pools`)
- Protocol TVL and counterparty analytics (`/protocol/{slug}`)
- Stablecoin circulation and market cap metrics (`/stablecoins`)
- Protocol fees and revenue (`/overview/fees`)

## Upstream Documentation & LLM Specs

DefiLlama updates endpoints, schemas, and routing regularly. When maintaining or extending this client, consult the authoritative upstream specs:
- **Root LLM Specs**: [`https://api-docs.defillama.com/llms.txt`](https://api-docs.defillama.com/llms.txt)
- **Free Endpoints Guide**: [`https://api-docs.defillama.com/llms-free.txt`](https://api-docs.defillama.com/llms-free.txt)
- **OpenAPI 3.0 Specification**: [`https://api-docs.defillama.com/defillama-openapi-free.json`](https://api-docs.defillama.com/defillama-openapi-free.json)

> **Important**: This client targets the **Free API** only. Do NOT mix with `pro-api.llama.fi` endpoints which require paid authorization.

## CLI Usage

```bash
# Get token prices
uv run llama-fetch prices "coingecko:ethereum" "coingecko:bitcoin"

# Screen top DeFi yields (stablecoin only, filtered by chain/TVL)
uv run llama-fetch yields --stablecoin --chain arbitrum --min-tvl 5000000

# Audit protocol TVL & risk
uv run llama-fetch protocol aave-v3

# Get stablecoin rankings and supply trends
uv run llama-fetch stables --top 10

# Get top protocol fees & revenue
uv run llama-fetch fees --top 10
```
