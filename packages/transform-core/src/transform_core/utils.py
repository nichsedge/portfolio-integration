"""
Utility functions for portfolio data transformation.
"""

import os
import re
from pathlib import Path
from typing import Union

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


def parse_usd(value: Union[str, int, float, None]) -> float:
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
