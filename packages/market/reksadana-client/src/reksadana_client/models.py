"""Pydantic data models for Indonesian Mutual Funds (Reksa Dana)."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NavInfo(BaseModel):
    date: str | None = None
    value: float | None = None
    first_date: str | None = None


class AumInfo(BaseModel):
    date: str | None = None
    value: float | None = None


class CagrInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    cagr_1y: float | None = Field(default=None, alias="1y")
    cagr_3y: float | None = Field(default=None, alias="3y")
    cagr_5y: float | None = Field(default=None, alias="5y")
    cagr_10y: float | None = Field(default=None, alias="10y")
    all: float | None = None


class DrawdownInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mdd_1y: float | None = Field(default=None, alias="1y")
    mdd_3y: float | None = Field(default=None, alias="3y")
    mdd_5y: float | None = Field(default=None, alias="5y")
    mdd_10y: float | None = Field(default=None, alias="10y")
    all: float | None = None


class SimpleReturnInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    return_1d: float | None = Field(default=None, alias="1d")
    return_1m: float | None = Field(default=None, alias="1m")
    return_3m: float | None = Field(default=None, alias="3m")
    return_ytd: float | None = Field(default=None, alias="ytd")
    return_1y: float | None = Field(default=None, alias="1y")
    return_3y: float | None = Field(default=None, alias="3y")
    return_5y: float | None = Field(default=None, alias="5y")


class ExpenseRatioInfo(BaseModel):
    percentage: float | None = None


class InvestmentManagerInfo(BaseModel):
    name: str = ""
    ojkCode: str | None = None


class CustodianBankInfo(BaseModel):
    name: str = ""
    ojkCode: str | None = None


class AssetAllocation(BaseModel):
    name: str
    percentage: float


class HoldingItem(BaseModel):
    symbol: str | None = None
    name: str
    date: str | None = None
    annualDividend: float | None = None
    product_type: str | None = None


class FundProduct(BaseModel):
    """Normalized Mutual Fund holding with key risk/return performance metrics."""

    id: int
    symbol: str
    name: str
    type: str  # Pasar Uang, Obligasi, Saham, Campuran, Reksadana Global
    sharia: bool = False
    riskprofile: str | None = None  # Conservative, Moderate, Aggressive
    tradeable: int = 1
    minbuy: float | None = None
    minsell: float | None = None
    nav: NavInfo = Field(default_factory=NavInfo)
    aum: AumInfo = Field(default_factory=AumInfo)
    cagr: CagrInfo = Field(default_factory=CagrInfo)
    maxdrawdown: DrawdownInfo = Field(default_factory=DrawdownInfo)
    simplereturn: SimpleReturnInfo = Field(default_factory=SimpleReturnInfo)
    expenseratio: ExpenseRatioInfo = Field(default_factory=ExpenseRatioInfo)
    investment_manager: InvestmentManagerInfo = Field(default_factory=InvestmentManagerInfo)
    custodian_bank: CustodianBankInfo = Field(default_factory=CustodianBankInfo)
    asset: list[AssetAllocation] = Field(default_factory=list)
    holding: list[HoldingItem] = Field(default_factory=list)
    raw_data: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @property
    def cagr_1y_pct(self) -> float:
        return (self.cagr.cagr_1y or 0.0) * 100.0

    @property
    def cagr_3y_pct(self) -> float:
        return (self.cagr.cagr_3y or 0.0) * 100.0

    @property
    def cagr_5y_pct(self) -> float:
        return (self.cagr.cagr_5y or 0.0) * 100.0

    @property
    def drawdown_1y_pct(self) -> float:
        return (self.maxdrawdown.mdd_1y or 0.0) * 100.0

    @property
    def expense_ratio_pct(self) -> float:
        return (self.expenseratio.percentage or 0.0) * 100.0

    @property
    def aum_idr(self) -> float:
        return self.aum.value or 0.0

    @property
    def calmar_ratio_1y(self) -> float:
        """Calmar Ratio = 1Y CAGR / abs(1Y MDD). Measures return earned per unit of max drawdown."""
        mdd = abs(self.maxdrawdown.mdd_1y or 0.0)
        cagr = self.cagr.cagr_1y or 0.0
        if mdd <= 0.0001:
            return cagr * 1000.0  # Ultra-high score for funds with zero drawdown
        return cagr / mdd
