"""Tests for orderbook fetching, liquidity analysis, and DCA calculations."""

import pytest
from binance_client.orderbook import (
    analyze_orderbook,
    find_bid_walls,
    normalize_symbol,
    simulate_market_buy,
)


def test_normalize_symbol():
    assert normalize_symbol("PAXG/USDT") == ("PAXG", "USDT", "PAXGUSDT", "PAXG_USDT")
    assert normalize_symbol("PAXGUSDT") == ("PAXG", "USDT", "PAXGUSDT", "PAXG_USDT")
    assert normalize_symbol("xaut_usdt") == ("XAUT", "USDT", "XAUTUSDT", "XAUT_USDT")
    assert normalize_symbol("BTC-USDC") == ("BTC", "USDC", "BTCUSDC", "BTC_USDC")


def test_simulate_market_buy():
    # Asks: [[price, qty], ...]
    asks = [
        [4200.0, 0.01],  # $42
        [4210.0, 0.02],  # $84.20
        [4220.0, 0.05],  # $211.00
    ]
    # Budget $50: fills first level completely ($42) and $8 from second level
    sim = simulate_market_buy(asks, budget_usd=50.0)

    assert sim["spent_usd"] == 50.0
    assert sim["best_ask"] == 4200.0
    assert sim["avg_fill_price"] > 4200.0
    assert sim["slippage_usd"] > 0.0
    assert sim["estimated_taker_fee_usd"] == pytest.approx(0.05, abs=0.001)


def test_find_bid_walls():
    # Bids: [[price, qty], ...]
    bids = [
        [4200.0, 0.5],
        [4195.0, 0.2],
        [4190.0, 10.0],  # Major wall ($41,900)
        [4180.0, 0.1],
        [4150.0, 20.0],  # Deep wall ($83,000)
    ]
    walls = find_bid_walls(bids, top_n=5)
    assert len(walls) >= 2
    prices = [w["price"] for w in walls]
    assert 4190.0 in prices or 4150.0 in prices


def test_analyze_orderbook():
    mock_orderbook = {
        "exchange": "tokocrypto",
        "symbol": "PAXG/USDT",
        "bids": [
            [4270.0, 1.0],
            [4265.0, 5.0],
            [4250.0, 15.0],
            [4200.0, 20.0],
        ],
        "asks": [
            [4271.0, 1.0],
            [4275.0, 2.0],
            [4280.0, 5.0],
        ],
    }
    ticker = {
        "last_price": 4270.5,
        "high_price_24h": 4300.0,
        "low_price_24h": 4220.0,
        "price_change_pct": 0.5,
        "volume_24h": 100.0,
        "quote_volume_24h": 427000.0,
    }

    res = analyze_orderbook(mock_orderbook, budget_usd=50.0, ticker=ticker, usd_idr_rate=17900.0)

    assert res["exchange"] == "tokocrypto"
    assert res["symbol"] == "PAXG/USDT"
    assert res["pricing"]["best_bid"] == 4270.0
    assert res["pricing"]["best_ask"] == 4271.0
    assert res["pricing"]["spread_usd"] == 1.0
    assert len(res["recommended_limit_orders"]) == 3
    assert res["dca_verdict"]["budget_usd"] == 50.0
    assert "market_buy_recommended" in res["dca_verdict"]
