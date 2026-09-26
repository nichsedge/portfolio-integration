from portfolio_app.yield_enricher import (
    DEFAULT_DEFI_YIELD,
    DEFAULT_MMF_YIELD,
    DEFAULT_P2P_YIELD,
    DEFAULT_SBN_YIELD,
    YieldEnricher,
    enrich_holdings_with_yield,
)


def test_sbn_sukuk_rates():
    enricher = YieldEnricher()

    # Exact registry matches
    assert enricher.resolve_holding_yield({"asset": "ST013T2", "category": "SBN", "asset_class": "Fixed Income"}) == 0.0640
    assert enricher.resolve_holding_yield({"asset": "ST012T4", "category": "SBN", "asset_class": "Fixed Income"}) == 0.0655
    assert enricher.resolve_holding_yield({"asset": "ST014T2", "category": "SBN", "asset_class": "Fixed Income"}) == 0.0640
    assert enricher.resolve_holding_yield({"asset": "ST010T4", "category": "SBN", "asset_class": "Fixed Income"}) == 0.0640
    assert enricher.resolve_holding_yield({"asset": "SR021T5", "category": "SBN", "asset_class": "Fixed Income"}) == 0.0645
    assert enricher.resolve_holding_yield({"asset": "ORI026T6", "category": "SBN", "asset_class": "Fixed Income"}) == 0.0640
    assert enricher.resolve_holding_yield({"asset": "PBS003", "category": "SBN", "asset_class": "Fixed Income"}) == 0.0600

    # Unlisted generic bond fallback
    assert enricher.resolve_holding_yield({"asset": "GENERIC_BOND_99", "category": "Corporate Bond", "asset_class": "Fixed Income"}) == DEFAULT_SBN_YIELD


def test_p2p_lending_rate():
    enricher = YieldEnricher()
    assert enricher.resolve_holding_yield({"asset": "ALAMI P2P", "category": "P2P Lending", "asset_class": "Fixed Income"}) == DEFAULT_P2P_YIELD
    assert enricher.resolve_holding_yield({"asset": "Hijra P2P", "category": "P2P Lending", "asset_class": "Fixed Income"}) == DEFAULT_P2P_YIELD


def test_crypto_staking_and_defi():
    enricher = YieldEnricher()
    assert enricher.resolve_holding_yield({"asset": "SOL Staked", "category": "Staked", "asset_class": "Crypto"}) == 0.0680
    assert enricher.resolve_holding_yield({"asset": "Lido Staked ETH", "category": "Staked", "asset_class": "Crypto"}) == 0.0320
    assert enricher.resolve_holding_yield({"asset": "Other Staked Token", "category": "Staked", "asset_class": "Crypto"}) == 0.0500
    assert enricher.resolve_holding_yield({"asset": "Aave USDC Pool", "category": "Yield / LP", "asset_class": "Crypto"}) == DEFAULT_DEFI_YIELD


def test_money_market_fund():
    enricher = YieldEnricher()
    assert enricher.resolve_holding_yield({"asset": "Sucorinvest Sharia Money Market Fund", "category": "Money Market Fund", "asset_class": "Cash & Equivalents"}) == DEFAULT_MMF_YIELD


def test_non_yielding_assets():
    enricher = YieldEnricher()
    assert enricher.resolve_holding_yield({"asset": "BCA Checking", "category": "Bank Account", "asset_class": "Cash & Equivalents"}) == 0.0
    assert enricher.resolve_holding_yield({"asset": "BTC", "category": "Spot", "asset_class": "Crypto"}) == 0.0
    assert enricher.resolve_holding_yield({"asset": "Physical Gold", "category": "Gold", "asset_class": "Commodities"}) == 0.0


def test_enrich_holdings_with_yield():
    holdings = [
        {"asset": "ST012T4", "category": "SBN", "asset_class": "Fixed Income", "value_idr": 90000000.0},
        {"asset": "ALAMI", "category": "P2P Lending", "asset_class": "Fixed Income", "value_idr": 15000000.0},
        {"asset": "SOL Staked", "category": "Staked", "asset_class": "Crypto", "value_idr": 20000000.0},
        {"asset": "BCA", "category": "Bank Account", "asset_class": "Cash & Equivalents", "value_idr": 5000000.0},
    ]

    enriched = enrich_holdings_with_yield(holdings)

    assert enriched[0]["yield_rate"] == 0.0655
    assert enriched[1]["yield_rate"] == 0.1150
    assert enriched[2]["yield_rate"] == 0.0680
    assert enriched[3]["yield_rate"] == 0.0
