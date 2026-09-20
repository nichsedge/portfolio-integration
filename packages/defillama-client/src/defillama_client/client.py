"""
DefiLlama Free API Client

Provides zero-auth, free access to DeFiLlama analytics:
- Multi-chain token prices (coins.llama.fi)
- Yield pools and APY (yields.llama.fi)
- Protocol TVL & risk data (api.llama.fi)
- Stablecoin market metrics (stablecoins.llama.fi)
- Protocol fees and revenue (api.llama.fi)
"""

import time
from typing import Any, Self

import httpx


class DefiLlamaClient:
    """Client for DeFiLlama's public unauthenticated APIs."""

    API_BASE = "https://api.llama.fi"
    COINS_BASE = "https://coins.llama.fi"
    YIELDS_BASE = "https://yields.llama.fi"
    STABLECOINS_BASE = "https://stablecoins.llama.fi"

    def __init__(
        self,
        cache_ttl: int = 300,
        timeout: float = 15.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.cache_ttl = cache_ttl
        self.timeout = timeout
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self._cache: dict[str, tuple[float, Any]] = {}

    def _get_cached(self, key: str) -> Any | None:
        if key in self._cache:
            ts, val = self._cache[key]
            if time.time() - ts < self.cache_ttl:
                return val
            del self._cache[key]
        return None

    def _set_cache(self, key: str, val: Any) -> None:
        self._cache[key] = (time.time(), val)

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def get_token_prices(
        self, coins: list[str] | str, search_width: str = "4h"
    ) -> dict[str, Any]:
        """
        Fetch current token prices by chain:address or coingecko:id.
        Examples: 'coingecko:ethereum', 'ethereum:0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9'
        """
        if isinstance(coins, str):
            coins = [c.strip() for c in coins.split(",") if c.strip()]

        if not coins:
            return {}

        coins_query = ",".join(coins)
        cache_key = f"prices:{coins_query}:{search_width}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        url = f"{self.COINS_BASE}/prices/current/{coins_query}?searchWidth={search_width}"
        resp = self._client.get(url)
        resp.raise_for_status()
        data = resp.json().get("coins", {})

        self._set_cache(cache_key, data)
        return data

    def get_pools(
        self,
        min_tvl: float = 1_000_000.0,
        chain: str | None = None,
        project: str | None = None,
        stablecoin_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Fetch active DeFi yield pools and filter by criteria.
        Data comes from yields.llama.fi/pools.
        """
        cache_key = "pools:all"
        cached = self._get_cached(cache_key)
        if cached is None:
            url = f"{self.YIELDS_BASE}/pools"
            resp = self._client.get(url)
            resp.raise_for_status()
            cached = resp.json().get("data", [])
            self._set_cache(cache_key, cached)

        filtered: list[dict[str, Any]] = []
        for pool in cached:
            tvl = float(pool.get("tvlUsd") or 0.0)
            if tvl < min_tvl:
                continue

            if chain and pool.get("chain", "").lower() != chain.lower():
                continue

            if project and pool.get("project", "").lower() != project.lower():
                continue

            if stablecoin_only and not pool.get("stablecoin"):
                continue

            filtered.append(
                {
                    "pool_id": pool.get("pool"),
                    "project": pool.get("project"),
                    "symbol": pool.get("symbol"),
                    "chain": pool.get("chain"),
                    "tvl_usd": round(tvl, 2),
                    "apy": round(float(pool.get("apy") or 0.0), 2),
                    "apy_base": round(float(pool.get("apyBase") or 0.0), 2),
                    "apy_reward": round(float(pool.get("apyReward") or 0.0), 2)
                    if pool.get("apyReward") is not None
                    else None,
                    "apy_pct_30d": round(float(pool.get("apyPct30D") or 0.0), 2)
                    if pool.get("apyPct30D") is not None
                    else None,
                    "stablecoin": pool.get("stablecoin", False),
                    "il_risk": pool.get("ilRisk", "no"),
                }
            )

        filtered.sort(key=lambda x: x["apy"], reverse=True)
        return filtered[:limit]

    def get_protocol(self, slug: str) -> dict[str, Any]:
        """
        Fetch full historical TVL, category, chain distribution, and audits for a protocol.
        """
        cache_key = f"protocol:{slug}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        url = f"{self.API_BASE}/protocol/{slug}"
        resp = self._client.get(url)
        resp.raise_for_status()
        raw = resp.json()

        chain_tvls = {}
        if "currentChainTvls" in raw:
            chain_tvls = {
                k: round(v, 2)
                for k, v in raw["currentChainTvls"].items()
                if not k.endswith("-borrowed")
                and not k.endswith("-staking")
                and not k.endswith("-pool2")
                and k not in {"borrowed", "staking", "pool2"}
            }

        result = {
            "id": raw.get("id"),
            "name": raw.get("name"),
            "slug": slug,
            "symbol": raw.get("symbol"),
            "category": raw.get("category"),
            "url": raw.get("url"),
            "description": raw.get("description"),
            "audits": raw.get("audits"),
            "audit_links": raw.get("audit_links", []),
            "tvl_usd": round(float(raw.get("tvl", [{}])[-1].get("totalLiquidityUSD", 0.0)), 2)
            if raw.get("tvl")
            else None,
            "chain_tvls": chain_tvls,
            "chains": raw.get("chains", []),
        }

        self._set_cache(cache_key, result)
        return result

    def get_stablecoins(self, limit: int = 20) -> list[dict[str, Any]]:
        """
        Fetch circulating supply and market capitalization of stablecoins.
        """
        cache_key = "stablecoins:all"
        cached = self._get_cached(cache_key)
        if cached is None:
            url = f"{self.STABLECOINS_BASE}/stablecoins"
            resp = self._client.get(url)
            resp.raise_for_status()
            cached = resp.json().get("peggedAssets", [])
            self._set_cache(cache_key, cached)

        results: list[dict[str, Any]] = []
        for asset in cached:
            circ = asset.get("circulating", {})
            mcap = float(circ.get("peggedUSD") or 0.0)
            if mcap <= 0:
                continue

            prev_day = float(asset.get("circulatingPrevDay", {}).get("peggedUSD") or mcap)
            prev_week = float(asset.get("circulatingPrevWeek", {}).get("peggedUSD") or mcap)

            change_1d = round(((mcap - prev_day) / prev_day) * 100, 2) if prev_day > 0 else 0.0
            change_7d = round(((mcap - prev_week) / prev_week) * 100, 2) if prev_week > 0 else 0.0

            chains = list(asset.get("chainCirculating", {}).keys())

            results.append(
                {
                    "name": asset.get("name"),
                    "symbol": asset.get("symbol"),
                    "peg_mechanism": asset.get("pegMechanism"),
                    "mcap_usd": round(mcap, 2),
                    "change_1d_pct": change_1d,
                    "change_7d_pct": change_7d,
                    "chains_count": len(chains),
                    "top_chains": chains[:5],
                }
            )

        results.sort(key=lambda x: x["mcap_usd"], reverse=True)
        return results[:limit]

    def get_protocol_fees(self, limit: int = 20) -> list[dict[str, Any]]:
        """
        Fetch protocol fees and revenue from api.llama.fi/overview/fees.
        """
        cache_key = "fees:all"
        cached = self._get_cached(cache_key)
        if cached is None:
            url = f"{self.API_BASE}/overview/fees"
            resp = self._client.get(url)
            resp.raise_for_status()
            cached = resp.json().get("protocols", [])
            self._set_cache(cache_key, cached)

        results: list[dict[str, Any]] = []
        for p in cached:
            fees_24h = float(p.get("total24h") or 0.0)
            rev_24h = float(p.get("dailyRevenue") or 0.0)
            annual_fees = fees_24h * 365.0
            annual_rev = rev_24h * 365.0

            results.append(
                {
                    "name": p.get("name"),
                    "slug": p.get("module"),
                    "category": p.get("category"),
                    "fees_24h_usd": round(fees_24h, 2),
                    "annual_fees_usd": round(annual_fees, 2),
                    "revenue_24h_usd": round(rev_24h, 2),
                    "annual_revenue_usd": round(annual_rev, 2),
                }
            )

        results.sort(key=lambda x: x["fees_24h_usd"], reverse=True)
        return results[:limit]
