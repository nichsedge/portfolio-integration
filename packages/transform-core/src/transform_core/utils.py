"""
Utility functions for portfolio data transformation.
"""

import os
import re
from pathlib import Path

import requests

# Find the repo root (assumes this file is in packages/transform-core/src/transform_core/utils.py)
REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR_DEFAULT = REPO_ROOT / "data"


def get_data_dir() -> Path:
    """
    Get the data directory path from environment variables or use default.

    Priority:
    1. PORTFOLIO_DATA_DIR environment variable
    2. DATA_DIR environment variable (alias)
    3. Hardcoded default: [Project Root]/data

    Returns:
        Path object pointing to the data directory
    """
    data_dir = os.getenv("PORTFOLIO_DATA_DIR") or os.getenv("DATA_DIR")
    if data_dir:
        return Path(data_dir)
    return DATA_DIR_DEFAULT


def parse_usd(value: str | float | None) -> float:
    """
    Convert a USD string like '$123.45' or '472.16 USDC' to float, handle '<$0.01' and None.

    Args:
        value: The value to parse (string, int, float, or None)

    Returns:
        float: The parsed USD value, or 0.0 if unparseable
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    val_str = str(value).replace(",", "").strip()
    if "<" in val_str:
        return 0.0

    # Extract numeric part (e.g., from '472.16 USDC' or '$472.16')
    match = re.search(r"[-+]?\d*\.?\d+", val_str)
    if match:
        try:
            return float(match.group())
        except ValueError:
            return 0.0
    return 0.0


from .resilience import retry_with_backoff


def _fetch_hexarate() -> float:
    response = requests.get('https://hexarate.paikama.co/api/rates/USD/IDR/latest', timeout=8)
    response.raise_for_status()
    data = response.json()
    return float(data['data']['mid'])


def _fetch_open_er_api() -> float:
    response = requests.get('https://open.er-api.com/v6/latest/USD', timeout=8)
    response.raise_for_status()
    data = response.json()
    return float(data['rates']['IDR'])


def _fetch_frankfurter() -> float:
    response = requests.get('https://api.frankfurter.app/latest?from=USD&to=IDR', timeout=8)
    response.raise_for_status()
    data = response.json()
    return float(data['rates']['IDR'])


@retry_with_backoff(max_attempts=3, initial_delay=1.0, max_delay=5.0, retry_exceptions=(requests.RequestException,))
def _fetch_rate_with_retry() -> float:
    for fetcher in (_fetch_hexarate, _fetch_open_er_api, _fetch_frankfurter):
        try:
            return fetcher()
        except Exception:
            continue
    raise RuntimeError("All FX rate providers failed")


def get_exchange_rate() -> float:
    """Fetch latest USD to IDR exchange rate with resilient retries and multi-source fallbacks."""
    cache_file = get_data_dir() / ".fx_rate_cache.json"
    try:
        rate = _fetch_rate_with_retry()
        if 10000.0 <= rate <= 30000.0:
            try:
                cache_file.write_text(json.dumps({"rate": rate, "timestamp": str(datetime.now())}))
            except Exception:
                pass
            return rate
    except Exception as e:
        print(f"Warning: Failed to fetch live FX rate ({e}). Attempting cache fallback...")

    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text())
            cached_rate = float(cached.get("rate", 0))
            if 10000.0 <= cached_rate <= 30000.0:
                print(f"Using cached FX rate: {cached_rate}")
                return cached_rate
        except Exception:
            pass

    print("Warning: Using default fallback FX rate 15500.0")
    return 15500.0
