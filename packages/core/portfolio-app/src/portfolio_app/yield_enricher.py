"""
Portfolio Yield Enrichment Engine.

Enriches multi-asset holdings with deterministic, real-world annual yield rates (APY / Dividend Yield)
for:
1. Sovereign Debt & Sukuk (SBN / SBSN / ORI / SR / ST / PBS / FR)
2. Indonesian Equities (IDX Dividend Yield derived from companyDetails or market parquet)
3. P2P Lending (P2P Syariah / productive SME lending)
4. Crypto Staking & DeFi Yield / Liquidity Pools
5. Money Market Funds (Reksa Dana Pasar Uang)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("portfolio_app.yield_enricher")

# Official issuance coupon rates for Sovereign Sukuk & Retail Bonds (Kemenkeu DJPPR)
SBN_REGISTRY: dict[str, float] = {
    # Sukuk Tabungan (ST)
    "ST014T2": 0.0640,
    "ST014T4": 0.0650,
    "ST013T2": 0.0640,
    "ST013T4": 0.0650,
    "ST012T2": 0.0640,
    "ST012T4": 0.0655,
    "ST011T2": 0.0630,
    "ST011T4": 0.0650,
    "ST010T2": 0.0625,
    "ST010T4": 0.0640,
    "ST009": 0.0615,
    "ST008": 0.0580,
    # Sukuk Ritel (SR)
    "SR021T3": 0.0625,
    "SR021T5": 0.0645,
    "SR020T3": 0.0630,
    "SR020T5": 0.0640,
    "SR019T3": 0.0595,
    "SR019T5": 0.0610,
    "SR018T3": 0.0625,
    "SR018T5": 0.0640,
    "SR017": 0.0590,
    "SR016": 0.0495,
    # Obligasi Negara Ritel (ORI)
    "ORI026T3": 0.0630,
    "ORI026T6": 0.0640,
    "ORI025T3": 0.0625,
    "ORI025T6": 0.0640,
    "ORI024T3": 0.0610,
    "ORI024T6": 0.0635,
    "ORI023T3": 0.0590,
    "ORI023T6": 0.0610,
    # Project-Based Sukuk (PBS)
    "PBS003": 0.0600,
    "PBS032": 0.04875,
    "PBS036": 0.05375,
    "PBS038": 0.05875,
    # Fixed Rate Government Bonds (FR)
    "FR0070": 0.08375,
    "FR0081": 0.0650,
    "FR0096": 0.0700,
}

# Crypto Staking Benchmark APY
CRYPTO_STAKING_RATES: dict[str, float] = {
    "SOL": 0.0680,
    "ETH": 0.0320,
    "DOT": 0.1150,
    "ATOM": 0.1350,
    "NEAR": 0.0750,
    "SUI": 0.0350,
    "ADA": 0.0280,
}

# Standard defaults by category
DEFAULT_P2P_YIELD: float = 0.1150       # 11.5% APY typical for productive P2P Syariah (ALAMI, Hijra)
DEFAULT_SBN_YIELD: float = 0.0625       # 6.25% generic SBN/Sukuk benchmark
DEFAULT_MMF_YIELD: float = 0.0480       # 4.80% net annualized yield for Pasar Uang funds
DEFAULT_DEFI_YIELD: float = 0.0750      # 7.50% standard LP / Yield farming pool
DEFAULT_STAKED_YIELD: float = 0.0500    # 5.00% generic PoS staking


class YieldEnricher:
    """Calculates and enriches real-world annual yields across multi-asset holdings."""

    def __init__(self, idx_root: Path | None = None):
        if idx_root is None:
            # Sibling project ../idx-bei
            self.idx_root = Path(__file__).resolve().parents[5] / "idx-bei"
        else:
            self.idx_root = Path(idx_root)

        self._company_details: dict[str, Any] | None = None
        self._listed_shares_map: dict[str, float] | None = None
        self._latest_prices_map: dict[str, float] | None = None

    def _load_idx_data(self) -> None:
        """Lazy load IDX company details and stock prices if available."""
        if self._company_details is not None:
            return

        self._company_details = {}
        self._listed_shares_map = {}
        self._latest_prices_map = {}

        details_file = self.idx_root / "data" / "companyDetailsByKodeEmiten.json"
        if details_file.exists():
            try:
                with open(details_file, "r", encoding="utf-8") as f:
                    self._company_details = json.load(f)
            except Exception as e:  # noqa: BLE001
                log.warning(f"Failed to load IDX company details from {details_file}: {e}")

        stock_parquet = self.idx_root / "data" / "parquet" / "stock_summary.parquet"
        if stock_parquet.exists():
            try:
                import duckdb
                con = duckdb.connect()
                df = con.execute(f"""
                    WITH latest_date AS (SELECT MAX(Date) as max_d FROM "{stock_parquet}")
                    SELECT s.StockCode, s.Close, s.ListedShares 
                    FROM "{stock_parquet}" s 
                    JOIN latest_date ld ON s.Date = ld.max_d
                """).df()
                self._latest_prices_map = dict(zip(df["StockCode"], df["Close"]))
                self._listed_shares_map = dict(zip(df["StockCode"], df["ListedShares"]))
                con.close()
            except Exception as e:  # noqa: BLE001
                log.warning(f"Failed to query IDX stock parquet with DuckDB: {e}")

    def get_stock_dividend_yield(self, ticker: str, current_price: float | None = None) -> float:
        """Calculate trailing dividend yield for an IDX stock."""
        ticker = ticker.strip().upper()
        self._load_idx_data()

        if not self._company_details or ticker not in self._company_details:
            return 0.0

        company_info = self._company_details.get(ticker, {})
        divs = company_info.get("Dividen") or []
        if not divs:
            return 0.0

        # Resolve price
        price = current_price or (self._latest_prices_map.get(ticker) if self._latest_prices_map else None) or 0.0
        if price <= 0:
            return 0.0

        # Calculate DPS from latest fiscal year / announcements
        # Group by latest announced book year
        latest_year = divs[0].get("TahunBuku")
        year_divs = [d for d in divs if d.get("TahunBuku") == latest_year]

        total_dps = 0.0
        shares = self._listed_shares_map.get(ticker, 0.0) if self._listed_shares_map else 0.0

        for d in year_divs:
            dps_item = float(d.get("CashDividenPerSaham", 0.0) or 0.0)
            total_cash_div = float(d.get("CashDividenTotal", 0.0) or 0.0)

            if total_cash_div > 0 and shares > 0:
                total_dps += (total_cash_div / shares)
            elif dps_item > 0:
                total_dps += dps_item

        if total_dps > 0 and price > 0:
            return round(total_dps / price, 4)

        return 0.0

    def resolve_holding_yield(self, holding: dict[str, Any]) -> float:
        """Resolve deterministic APY / Yield Rate for a single holding."""
        category = str(holding.get("category", "")).strip()
        asset_name = str(holding.get("asset", "")).strip().upper()
        asset_class = str(holding.get("asset_class", "")).strip()

        # 1. Sovereign Debt & Sukuk (SBN / Fixed Income)
        if category in ["SBN", "Corporate Bond"] or asset_class == "Fixed Income":
            # Match specific known code in registry (e.g. ST013T2, ST014T2)
            for code, rate in SBN_REGISTRY.items():
                if code in asset_name:
                    return rate

            # Regex pattern for Sukuk / ORI series (e.g. ST014, SR021, ORI026)
            for code_prefix, rate in SBN_REGISTRY.items():
                prefix = re.match(r"^[A-Z]+\d+", code_prefix)
                if prefix and prefix.group(0) in asset_name:
                    return rate

            if category == "P2P Lending":
                return DEFAULT_P2P_YIELD

            return DEFAULT_SBN_YIELD

        # 2. P2P Lending
        if category == "P2P Lending":
            return DEFAULT_P2P_YIELD

        # 3. Indonesian Equities (Indo Stocks)
        if category == "Indo Stocks" or (asset_class == "Equities" and len(asset_name) == 4 and asset_name.isalpha()):
            price = float(holding.get("price") or 0.0)
            return self.get_stock_dividend_yield(asset_name, current_price=price)

        # 4. Money Market Funds
        if category == "Money Market Fund":
            return DEFAULT_MMF_YIELD

        # 5. Crypto Staking & Yield
        if category == "Staked":
            for coin, rate in CRYPTO_STAKING_RATES.items():
                if coin in asset_name:
                    return rate
            return DEFAULT_STAKED_YIELD

        if category == "Yield / LP":
            return DEFAULT_DEFI_YIELD

        # 6. Cash, Digital Bank, Spot Crypto, Commodities, etc.
        return 0.0

    def enrich(self, holdings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Enrich holding dictionaries in-place with `yield_rate` field."""
        for item in holdings:
            rate = self.resolve_holding_yield(item)
            item["yield_rate"] = round(rate, 4)
        return holdings


_GLOBAL_ENRICHER: YieldEnricher | None = None


def get_yield_enricher() -> YieldEnricher:
    """Singleton getter for YieldEnricher."""
    global _GLOBAL_ENRICHER
    if _GLOBAL_ENRICHER is None:
        _GLOBAL_ENRICHER = YieldEnricher()
    return _GLOBAL_ENRICHER


def enrich_holdings_with_yield(holdings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convenience helper to enrich holdings list with yield_rate."""
    enricher = get_yield_enricher()
    return enricher.enrich(holdings)
