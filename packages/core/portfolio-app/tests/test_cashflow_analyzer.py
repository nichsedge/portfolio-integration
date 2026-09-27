"""
Unit tests for Cashflow Analyzer (Sans Finance SQLite integration).
"""

import sqlite3
from pathlib import Path

import pendulum
import pytest
from portfolio_app.cashflow_analyzer import (
    calculate_runway,
    get_cashflow_metrics,
    get_live_accounts,
)


@pytest.fixture
def mock_sans_db(tmp_path: Path) -> Path:
    """Creates a temporary mock SQLite database with Sans Finance schema."""
    db_file = tmp_path / "mock_sans_finance.sqlite"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()

    # Create tables
    cursor.execute("""
        CREATE TABLE accounts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            currency TEXT NOT NULL,
            balance INTEGER NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE categories (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE expenses (
            id TEXT PRIMARY KEY,
            date INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            currency TEXT NOT NULL,
            type TEXT NOT NULL,
            category_id TEXT,
            title TEXT
        )
    """)

    # Seed accounts (stored in cents, e.g. 50,000,000 IDR -> 5,000,000,000 cents)
    cursor.executemany("""
        INSERT INTO accounts (id, name, type, currency, balance) VALUES (?, ?, ?, ?, ?)
    """, [
        ("acc_1", "Superbank Main", "Checking", "IDR", 5000000000),      # Rp 50,000,000
        ("acc_2", "Aladin Bank", "Digital Bank", "IDR", 2000000000),     # Rp 20,000,000
        ("acc_3", "Wise USD", "Digital Bank", "USD", 50000),            # $500.00
        ("acc_4", "Stockbit Portfolio", "Investment", "IDR", 1000000000) # Excluded from liquid cash
    ])

    # Seed categories
    cursor.executemany("""
        INSERT INTO categories (id, name) VALUES (?, ?)
    """, [
        ("cat_1", "Salary"),
        ("cat_2", "Food"),
        ("cat_3", "Rent"),
    ])

    # Seed transactions for current month
    now = pendulum.now()
    tx_time_ms = int(now.subtract(days=5).timestamp() * 1000)

    cursor.executemany("""
        INSERT INTO expenses (id, date, amount, currency, type, category_id, title) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [
        ("tx_1", tx_time_ms, 1500000000, "IDR", "INCOME", "cat_1", "Monthly Salary"),     # Rp 15,000,000
        ("tx_2", tx_time_ms, 200000000, "IDR", "EXPENSE", "cat_2", "Groceries"),         # Rp 2,000,000
        ("tx_3", tx_time_ms, 300000000, "IDR", "EXPENSE", "cat_3", "Apartment Rent"),    # Rp 3,000,000
    ])

    conn.commit()
    conn.close()
    return db_file


def test_get_live_accounts(mock_sans_db: Path):
    fx = 16000.0
    res = get_live_accounts(mock_sans_db, exchange_rate=fx)

    assert len(res["accounts"]) == 4
    # Liquid accounts: 50,000,000 IDR + 20,000,000 IDR + (500 USD * 16000 = 8,000,000 IDR) = 78,000,000 IDR
    assert res["total_liquid_idr"] == 78000000.0
    assert res["total_liquid_usd"] == 4875.0


def test_get_cashflow_metrics(mock_sans_db: Path):
    fx = 16000.0
    cf = get_cashflow_metrics(mock_sans_db, months=3, exchange_rate=fx)

    assert cf["total_income_idr"] == 15000000.0
    assert cf["total_expense_idr"] == 5000000.0
    assert cf["avg_monthly_income_idr"] == 15000000.0
    assert cf["avg_monthly_burn_idr"] == 5000000.0
    assert cf["overall_savings_rate_pct"] == pytest.approx(66.7, 0.1)

    top_cats = cf["top_categories"]
    assert len(top_cats) == 2
    assert top_cats[0]["category"] == "Rent"
    assert top_cats[0]["amount_idr"] == 3000000.0


def test_calculate_runway():
    # 60m liquid / 5m burn = 12 months -> Fortress
    r1 = calculate_runway(60000000.0, 5000000.0)
    assert r1["runway_months"] == 12.0
    assert r1["health"] == "Fortress"

    # 15m liquid / 5m burn = 3 months -> Moderate
    r2 = calculate_runway(15000000.0, 5000000.0)
    assert r2["runway_months"] == 3.0
    assert r2["health"] == "Moderate"

    # 5m liquid / 5m burn = 1 month -> Critical
    r3 = calculate_runway(5000000.0, 5000000.0)
    assert r3["runway_months"] == 1.0
    assert r3["health"] == "Critical"
