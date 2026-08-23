"""
Unit tests for Pydantic data models across transform-core.
"""

import pytest
from pydantic import ValidationError
from transform_core.models import (
    AlchemyCuratedData,
    AlchemyTokenEntry,
    BinanceAssetEntry,
    BinanceCuratedData,
    KseiCashEntry,
    KseiCuratedData,
    KseiSectionCash,
    PortfolioHoldingRecord,
    PortfolioSnapshot,
)


def test_portfolio_holding_record_valid():
    holding = PortfolioHoldingRecord(
        source="debank",
        category="Spot",
        asset="ETH",
        currency="USD",
        quantity=1.5,
        price=3000.0,
        value_idr=70000000.0,
        value_usd=4500.0,
        asset_class="Crypto",
        account="0x123",
    )
    assert holding.asset == "ETH"
    assert holding.quantity == 1.5
    assert holding.value_usd == 4500.0


def test_portfolio_holding_record_numeric_cleaning():
    holding = PortfolioHoldingRecord(
        source="ksei",
        category="Indo Stocks",
        asset="BBCA",
        currency="IDR",
        quantity="1,000",
        price="9,500",
        value_idr="Rp9,500,000",
        value_usd="$600.00",
        asset_class="Equities",
    )
    assert holding.quantity == 1000.0
    assert holding.value_idr == 9500000.0
    assert holding.value_usd == 600.0


def test_portfolio_holding_record_invalid():
    with pytest.raises(ValidationError):
        PortfolioHoldingRecord(
            source="",  # Empty string invalid
            category="Spot",
            asset="ETH",
            asset_class="Crypto",
        )


def test_portfolio_snapshot_valid():
    snapshot = PortfolioSnapshot(
        date="2026-08-22",
        exchange_rate=16000.0,
        total_idr=160000000.0,
        total_usd=10000.0,
        holdings=[
            PortfolioHoldingRecord(
                source="binance",
                category="Spot",
                asset="BTC",
                quantity=0.1,
                value_usd=6000.0,
                value_idr=96000000.0,
                asset_class="Crypto",
            )
        ],
        category_breakdown={"Spot": 96000000.0},
        asset_class_breakdown={"Crypto": 96000000.0},
        source_breakdown={"binance": 96000000.0},
    )
    assert snapshot.total_usd == 10000.0
    assert len(snapshot.holdings) == 1


def test_alchemy_curated_model():
    data = AlchemyCuratedData(
        timestamp="2026-08-22T00:00:00Z",
        total_usd=150.0,
        assets=[
            AlchemyTokenEntry(
                token_address="SOL",
                symbol="SOL",
                name="Solana",
                quantity=1.0,
                value_usd=150.0,
            )
        ]
    )
    assert len(data.assets) == 1
    assert data.total_usd == 150.0


def test_binance_curated_model():
    data = BinanceCuratedData(
        total_usd=2000.0,
        assets=[
            BinanceAssetEntry(
                asset="USDT",
                quantity=2000.0,
                value_usd=2000.0,
            )
        ]
    )
    assert data.assets[0].asset == "USDT"


def test_ksei_curated_model():
    data = KseiCuratedData(
        cash=KseiSectionCash(
            data=[
                KseiCashEntry(saldoIdr=1000000.0, bank="BCA")
            ]
        )
    )
    assert data.cash is not None
    assert len(data.cash.data) == 1
    assert data.cash.data[0].saldoIdr == 1000000.0
