"""
Unit tests for raw data transformers: KSEI, DeBank, Binance, and Alchemy.
"""

from portfolio_app.integrators.portfolio_integration import (
    get_asset_class,
    get_standard_category,
    standardize_alchemy_data,
    standardize_binance_data,
    standardize_debank_data,
    standardize_ksei_data,
)


def test_get_asset_class_and_category_mapping():
    assert get_standard_category("Cryptocurrency", "USDT") == "Stablecoin"
    assert get_standard_category("Cryptocurrency", "PAXG") == "Gold"
    assert get_standard_category("Cryptocurrency", "ETH") == "Spot"
    assert get_standard_category("DeFi Staked", "stETH") == "Staked"

    assert get_asset_class("Indo Stocks") == "Equities"
    assert get_asset_class("US Stocks") == "Equities"
    assert get_asset_class("SBN") == "Fixed Income"
    assert get_asset_class("Corporate Bond") == "Fixed Income"
    assert get_asset_class("Stablecoin") == "Cash & Equivalents"
    assert get_asset_class("Bank Account") == "Cash & Equivalents"
    assert get_asset_class("Spot") == "Crypto"
    assert get_asset_class("Gold") == "Commodities"


def test_standardize_ksei_data():
    raw_ksei = {
        "cash": {
            "data": [
                {"currCode": "IDR", "saldoIdr": 1500000.0, "saldo": 1500000.0, "bank": "PRMT2", "rekening": "12345"},
                {"currCode": "IDR", "saldoIdr": 50.0, "saldo": 50.0, "bank": "JAGO1", "rekening": "99999"} # below dust threshold
            ]
        },
        "equity": {
            "data": [
                {"efek": "BBCA - BANK CENTRAL ASIA", "jumlah": 1000, "harga": 9500, "nilaiInvestasi": 9500000.0, "partisipan": "Stockbit"}
            ]
        },
        "bond": {
            "data": [
                {"efek": "ST012T4", "jumlah": 10, "harga": 1000000, "nilaiInvestasi": 10000000.0, "partisipan": "Bareksa"}
            ]
        }
    }

    standardized = standardize_ksei_data(raw_ksei)
    assert len(standardized) == 3

    # Check RDN
    cash_item = next(x for x in standardized if x["asset"] == "Ajaib RDN")
    assert cash_item["value_idr"] == 1500000.0
    assert cash_item["category"] == "Bank Account"

    # Check Equity
    stock_item = next(x for x in standardized if x["asset"] == "BBCA")
    assert stock_item["value_idr"] == 9500000.0
    assert stock_item["category"] == "Indo Stocks"

    # Check Bond
    bond_item = next(x for x in standardized if x["asset"] == "ST012T4")
    assert bond_item["value_idr"] == 10000000.0
    assert bond_item["category"] == "SBN"


def test_standardize_debank_data():
    raw_debank = {
        "tokens": [
            {"symbol": "USDC", "amount": 500.0, "price": "1.0", "value": "$500.00"},
            {"symbol": "SHIB", "amount": 100.0, "price": "0.00001", "value": "$0.01"} # below threshold
        ],
        "protocols": [
            {
                "name": "Aave V3",
                "positions": [
                    {
                        "pool": "Ethereum Core",
                        "type": "Supplied",
                        "value": "$2,500.00",
                        "tokens": [{"balance": "1.0 ETH"}]
                    }
                ]
            }
        ]
    }

    standardized = standardize_debank_data(raw_debank)
    assert len(standardized) == 2

    usdc_token = next(x for x in standardized if x["asset"] == "USDC")
    assert usdc_token["category"] == "Stablecoin"
    assert usdc_token["value_usd"] == 500.0

    aave_pos = next(x for x in standardized if "Aave V3" in x["asset"])
    assert aave_pos["value_usd"] == 2500.0
    assert aave_pos["category"] == "Yield / LP"


def test_standardize_binance_data():
    raw_binance = {
        "assets": [
            {"symbol": "BTC", "amount": 0.05, "price_usd": 65000.0, "value_usd": 3250.0},
            {"symbol": "DUST", "amount": 1.0, "price_usd": 0.01, "value_usd": 0.01}
        ]
    }
    standardized = standardize_binance_data(raw_binance)
    assert len(standardized) == 1
    assert standardized[0]["asset"] == "BTC"
    assert standardized[0]["value_usd"] == 3250.0
    assert standardized[0]["category"] == "Spot"


def test_standardize_alchemy_data():
    raw_alchemy = {
        "assets": [
            {"symbol": "SOL", "name": "Solana", "quantity": 10.0, "price_usd": 140.0, "value_usd": 1400.0, "network": "Solana"}
        ]
    }
    standardized = standardize_alchemy_data(raw_alchemy)
    assert len(standardized) == 1
    assert standardized[0]["asset"] == "SOL"
    assert standardized[0]["value_usd"] == 1400.0
    assert standardized[0]["source"] == "SOL Wallet"
