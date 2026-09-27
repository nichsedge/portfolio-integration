"""Unit tests for Reksa Dana client and screener."""

from reksadana_client.client import BibitReksadanaClient
from reksadana_client.models import (
    AumInfo,
    CagrInfo,
    DrawdownInfo,
    ExpenseRatioInfo,
    FundProduct,
    InvestmentManagerInfo,
    NavInfo,
)
from reksadana_client.screener import (
    MutualFundScreener,
    format_idr_compact,
    parse_aum_string,
)


def test_parse_aum_string():
    assert parse_aum_string("1t") == 1e12
    assert parse_aum_string("500b") == 500e9
    assert parse_aum_string("200m") == 200e9  # 'm' in Indonesia finance often means miliar (billion)
    assert parse_aum_string("50miliar") == 50e9
    assert parse_aum_string("2triliun") == 2e12
    assert parse_aum_string("") == 0.0
    assert parse_aum_string(None) == 0.0


def test_format_idr_compact():
    assert format_idr_compact(16.5e12) == "Rp 16.50 T"
    assert format_idr_compact(500e9) == "Rp 500.00 M"
    assert format_idr_compact(25e6) == "Rp 25.00 Jt"


def test_decrypt_payload():
    import json
    import os

    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    secret_key = "12345678901234567890123456789012"  # 32 chars
    iv = os.urandom(16)
    data = [{"id": 1, "name": "Test Fund"}]
    raw_bytes = json.dumps(data).encode("utf-8")

    # PKCS7 padding
    pad_len = 16 - (len(raw_bytes) % 16)
    padded = raw_bytes + bytes([pad_len] * pad_len)

    cipher = Cipher(algorithms.AES(secret_key.encode("utf-8")), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()

    # Payload format: iv_hex (32) + ciphertext_hex + secret_key (32)
    payload = iv.hex() + ciphertext.hex() + secret_key

    decrypted = BibitReksadanaClient.decrypt_payload(payload)
    assert decrypted == data


def test_fund_product_properties():
    fund = FundProduct(
        id=1,
        symbol="RD001",
        name="Test Money Market",
        type="Pasar Uang",
        sharia=True,
        nav=NavInfo(value=1500.0, date="2026-09-25"),
        aum=AumInfo(value=1e12, date="2026-08-01"),
        cagr=CagrInfo(cagr_1y=0.05, cagr_3y=0.055),
        maxdrawdown=DrawdownInfo(mdd_1y=-0.001),
        expenseratio=ExpenseRatioInfo(percentage=0.008),
        investment_manager=InvestmentManagerInfo(name="PT Test Asset Management", ojkCode="TST01"),
    )

    assert fund.cagr_1y_pct == 5.0
    assert fund.cagr_3y_pct == 5.5
    assert fund.drawdown_1y_pct == -0.1
    assert fund.expense_ratio_pct == 0.8
    assert fund.aum_idr == 1e12
    assert fund.calmar_ratio_1y == 50.0  # 0.05 / 0.001


def test_screener_filtering_and_ranking():
    funds = [
        FundProduct(
            id=1,
            symbol="RD01",
            name="Mega Cash Pasar Uang",
            type="Pasar Uang",
            sharia=False,
            cagr=CagrInfo(cagr_1y=0.048),
            maxdrawdown=DrawdownInfo(mdd_1y=0.0),
            aum=AumInfo(value=500e9),
            expenseratio=ExpenseRatioInfo(percentage=0.005),
        ),
        FundProduct(
            id=2,
            symbol="RD02",
            name="Sharia Money Market",
            type="Pasar Uang",
            sharia=True,
            cagr=CagrInfo(cagr_1y=0.045),
            maxdrawdown=DrawdownInfo(mdd_1y=-0.002),
            aum=AumInfo(value=1e12),
            expenseratio=ExpenseRatioInfo(percentage=0.006),
        ),
        FundProduct(
            id=3,
            symbol="RD03",
            name="Alpha Bond Fund",
            type="Obligasi",
            sharia=False,
            cagr=CagrInfo(cagr_1y=0.065),
            maxdrawdown=DrawdownInfo(mdd_1y=-0.015),
            aum=AumInfo(value=2e12),
            expenseratio=ExpenseRatioInfo(percentage=0.012),
        ),
    ]

    screener = MutualFundScreener(funds)

    # Filter by type
    pu = screener.filter_and_rank(fund_type="pasar_uang")
    assert len(pu) == 2
    assert pu[0].symbol == "RD01"  # 4.8% > 4.5%

    # Filter by sharia
    sharia = screener.filter_and_rank(sharia_only=True)
    assert len(sharia) == 1
    assert sharia[0].symbol == "RD02"

    # Filter by min AUM
    big = screener.filter_and_rank(min_aum=1e12)
    assert len(big) == 2
    assert {b.symbol for b in big} == {"RD02", "RD03"}

    # Sort by expense ratio (lowest first)
    low_fee = screener.filter_and_rank(sort_by="expense_ratio")
    assert low_fee[0].symbol == "RD01"  # 0.5% lowest
