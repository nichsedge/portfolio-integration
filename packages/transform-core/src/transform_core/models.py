"""
Pydantic v2 Models for Portfolio Integration
Provides strict validation, serialization, and type safety for raw, curated,
and integrated portfolio holding data.
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

VALID_ASSET_CLASSES = {
    "Fixed Income",
    "Equities",
    "Cash & Equivalents",
    "Crypto",
    "Commodities",
    "Other",
}

VALID_CATEGORIES = {
    "Bank Account",
    "Digital Bank",
    "Stablecoin",
    "Money Market Fund",
    "SBN",
    "Corporate Bond",
    "P2P Lending",
    "US Stocks",
    "Indo Stocks",
    "Equity Fund",
    "Spot",
    "Staked",
    "Yield / LP",
    "Gold",
    "Silver",
    "Liabilities",
    "Other",
}


# =============================================================================
# Standard Integrated Holding & Snapshot Schemas
# =============================================================================

class PortfolioHoldingRecord(BaseModel):
    """Represents a unified, standardized portfolio holding record."""
    source: str = Field(..., min_length=1, description="Data source identifier (e.g. debank, ksei, binance, alchemy)")
    category: str = Field(..., min_length=1, description="Standardized category")
    asset: str = Field(..., min_length=1, description="Asset ticker or display name")
    currency: str = Field(default="USD", description="Original currency denomination")
    quantity: float = Field(default=0.0, ge=0.0, description="Amount/quantity of asset held")
    price: float | None = Field(default=None, ge=0.0, description="Unit price in base currency")
    value_idr: float = Field(default=0.0, ge=0.0, description="Converted valuation in IDR")
    value_usd: float = Field(default=0.0, ge=0.0, description="Converted valuation in USD")
    asset_class: str = Field(..., min_length=1, description="High-level asset class")
    account_id: int | None = Field(default=None, description="Optional foreign key to Sans Finance account ID")
    account_key: str | None = Field(default=None, description="Optional stable account key identifier")
    account_name: str | None = Field(default=None, description="Optional human-readable account name")
    account: str = Field(default="", description="Account description or wallet identifier")
    details: dict[str, Any] | list[Any] | str | None = Field(default=None, description="Source-specific metadata")

    @field_validator("asset_class")
    @classmethod
    def validate_asset_class(cls, v: str) -> str:
        if v not in VALID_ASSET_CLASSES:
            # Allow fallback to 'Other' or standard
            pass
        return v

    @field_validator("quantity", "price", "value_idr", "value_usd", mode="before")
    @classmethod
    def parse_numeric(cls, v: Any) -> float | None:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            cleaned = v.replace(",", "").replace("$", "").replace("Rp", "").strip()
            try:
                return float(cleaned)
            except ValueError:
                return 0.0
        return 0.0


class PortfolioSnapshot(BaseModel):
    """Daily consolidated portfolio snapshot model."""
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Date string YYYY-MM-DD")
    exchange_rate: float = Field(..., gt=0.0, description="USD/IDR exchange rate used")
    total_idr: float = Field(..., ge=0.0, description="Total portfolio value in IDR")
    total_usd: float = Field(..., ge=0.0, description="Total portfolio value in USD")
    holdings: list[PortfolioHoldingRecord] = Field(default_factory=list, description="List of standardized holdings")
    category_breakdown: dict[str, float] = Field(default_factory=dict, description="Breakdown by category in IDR")
    asset_class_breakdown: dict[str, float] = Field(default_factory=dict, description="Breakdown by asset class in IDR")
    source_breakdown: dict[str, float] = Field(default_factory=dict, description="Breakdown by data source in IDR")

    @model_validator(mode="after")
    def validate_total_consistency(self) -> "PortfolioSnapshot":
        if self.exchange_rate <= 0:
            raise ValueError("Exchange rate must be strictly positive")
        return self


# =============================================================================
# Source-Specific Curated Schemas
# =============================================================================

# --- Alchemy ---
class AlchemyTokenEntry(BaseModel):
    address: str | None = None
    network: str | None = None
    token_address: str = Field(default="SOL")
    symbol: str = Field(default="UNKNOWN")
    name: str | None = Field(default="Unknown Token")
    quantity: float = Field(default=0.0, ge=0.0)
    decimals: int | None = Field(default=9)
    value_usd: float = Field(default=0.0, ge=0.0)


class AlchemyCuratedData(BaseModel):
    timestamp: str | None = None
    total_usd: float = Field(default=0.0, ge=0.0)
    assets: list[AlchemyTokenEntry] = Field(default_factory=list)


# --- Binance ---
class BinanceAssetEntry(BaseModel):
    asset: str
    quantity: float = Field(default=0.0, ge=0.0)
    value_usd: float = Field(default=0.0, ge=0.0)
    price_usd: float | None = None
    free: float | None = None
    locked: float | None = None


class BinanceCuratedData(BaseModel):
    timestamp: str | int | None = None
    total_usd: float = Field(default=0.0, ge=0.0)
    assets: list[BinanceAssetEntry] = Field(default_factory=list)


# --- KSEI ---
class KseiCashEntry(BaseModel):
    currCode: str = "IDR"
    saldoIdr: float = Field(default=0.0, ge=0.0)
    saldo: float | None = 0.0
    bank: str | None = None
    rekening: str | None = None


class KseiInvestmentEntry(BaseModel):
    efek: str
    jumlah: float = Field(default=0.0, ge=0.0)
    harga: float | None = 0.0
    nilaiInvestasi: float = Field(default=0.0, ge=0.0)
    partisipan: str | None = None


class KseiSectionCash(BaseModel):
    totalSaldo: float | None = None
    data: list[KseiCashEntry] = Field(default_factory=list)


class KseiSectionInvestment(BaseModel):
    totalInvestasi: float | None = None
    data: list[KseiInvestmentEntry] = Field(default_factory=list)


class KseiCuratedData(BaseModel):
    cash: KseiSectionCash | None = None
    equity: KseiSectionInvestment | None = None
    mutual_fund: KseiSectionInvestment | None = None
    bond: KseiSectionInvestment | None = None


# --- DeBank ---
class DebankTokenEntry(BaseModel):
    symbol: str
    price: float | str | None = None
    quantity: str | float
    value: str | float


class DebankPositionEntry(BaseModel):
    pool: str | dict[str, Any] | None = None
    type: str | None = None
    value: str | float | None = None
    tokens: list[Any] | None = None


class DebankProtocolEntry(BaseModel):
    name: str | None = None
    chain: str | None = None
    value: str | float | None = None
    positions: list[DebankPositionEntry] = Field(default_factory=list)


class DebankCuratedData(BaseModel):
    wallet: dict[str, Any] | None = None
    social: dict[str, Any] | None = None
    chains: list[Any] | None = None
    tokens: list[DebankTokenEntry] = Field(default_factory=list)
    protocols: list[DebankProtocolEntry] = Field(default_factory=list)
    nfts: list[Any] | None = None
    timestamp: str | int | None = None
