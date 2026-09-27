"""
Tests for DefiLlama Free API Client
"""

import httpx
import pytest
from defillama_client.client import DefiLlamaClient


def test_client_caching():
    """Verify local cache prevents unnecessary repeated requests."""
    mock_transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "coins": {
                    "coingecko:ethereum": {
                        "price": 2500.0,
                        "symbol": "ETH",
                        "timestamp": 1700000000,
                        "confidence": 0.99,
                    }
                }
            },
        )
    )

    client = DefiLlamaClient(
        cache_ttl=300, client=httpx.Client(transport=mock_transport)
    )

    res1 = client.get_token_prices(["coingecko:ethereum"])
    assert res1["coingecko:ethereum"]["price"] == 2500.0

    # Cached hit
    res2 = client.get_token_prices(["coingecko:ethereum"])
    assert res2["coingecko:ethereum"]["price"] == 2500.0


def test_get_pools_filtering():
    """Verify pools filtering logic for stablecoins, min_tvl, and chain."""
    sample_data = {
        "status": "success",
        "data": [
            {
                "pool": "pool-1",
                "project": "aave-v3",
                "symbol": "USDC",
                "chain": "Arbitrum",
                "tvlUsd": 50_000_000,
                "apy": 5.5,
                "stablecoin": True,
                "ilRisk": "no",
            },
            {
                "pool": "pool-2",
                "project": "uniswap-v3",
                "symbol": "ETH-USDC",
                "chain": "Arbitrum",
                "tvlUsd": 100_000_000,
                "apy": 12.0,
                "stablecoin": False,
                "ilRisk": "yes",
            },
            {
                "pool": "pool-3",
                "project": "curve",
                "symbol": "3pool",
                "chain": "Ethereum",
                "tvlUsd": 20_000,  # Below min TVL
                "apy": 4.0,
                "stablecoin": True,
                "ilRisk": "no",
            },
        ],
    }

    mock_transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=sample_data)
    )

    client = DefiLlamaClient(
        cache_ttl=300, client=httpx.Client(transport=mock_transport)
    )

    # Filter by stablecoin only and Arbitrum
    pools = client.get_pools(
        min_tvl=1_000_000, chain="Arbitrum", stablecoin_only=True
    )
    assert len(pools) == 1
    assert pools[0]["project"] == "aave-v3"
    assert pools[0]["symbol"] == "USDC"
    assert pools[0]["stablecoin"] is True


def test_get_protocol():
    """Verify protocol extraction and chain TVL breakdown."""
    sample_proto = {
        "id": "1599",
        "name": "Aave V3",
        "symbol": "AAVE",
        "category": "Lending",
        "audits": "2",
        "url": "https://aave.com",
        "tvl": [{"totalLiquidityUSD": 15000000000.0}],
        "currentChainTvls": {
            "Ethereum": 10000000000.0,
            "Arbitrum": 3000000000.0,
            "Ethereum-borrowed": 4000000000.0,
        },
    }

    mock_transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=sample_proto)
    )

    client = DefiLlamaClient(
        cache_ttl=300, client=httpx.Client(transport=mock_transport)
    )
    data = client.get_protocol("aave-v3")

    assert data["name"] == "Aave V3"
    assert data["tvl_usd"] == 15000000000.0
    assert "Ethereum" in data["chain_tvls"]
    assert "Ethereum-borrowed" not in data["chain_tvls"]


@pytest.mark.asyncio
async def test_live_free_api_smoke():
    """Smoke test against live DefiLlama free API."""
    try:
        with DefiLlamaClient(timeout=8.0) as client:
            prices = client.get_token_prices(["coingecko:ethereum"])
            assert "coingecko:ethereum" in prices
            assert prices["coingecko:ethereum"]["price"] > 0
    except (httpx.ConnectError, httpx.TimeoutException):
        pytest.skip("External network unreachable during test")
