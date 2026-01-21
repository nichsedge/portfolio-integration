"""
Utility functions for portfolio data transformation.
"""

import os
import re
from pathlib import Path
from typing import Union

DATA_DIR_DEFAULT = "/home/al/Projects/.data/portfolio"


def get_data_dir() -> Path:
    """
    Get the data directory path from environment variables or use default.

    Priority:
    1. PORTFOLIO_DATA_DIR environment variable
    2. DATA_DIR environment variable (alias)
    3. Hardcoded default: /home/al/Projects/.data/portfolio

    Returns:
        Path object pointing to the data directory
    """
    data_dir = os.getenv("PORTFOLIO_DATA_DIR") or os.getenv("DATA_DIR") or DATA_DIR_DEFAULT
    return Path(data_dir)


def parse_usd(value: Union[str, int, float, None]) -> float:
    """
    Convert a USD string like '$123.45' to float, handle '<$0.01' and None.

    Args:
        value: The value to parse (string, int, float, or None)

    Returns:
        float: The parsed USD value, or 0.0 if unparseable

    Examples:
        >>> parse_usd("$123.45")
        123.45
        >>> parse_usd("<$0.01")
        0.0
        >>> parse_usd(None)
        0.0
        >>> parse_usd(100)
        100.0
    """
    if value is None or isinstance(value, (int, float)):
        return float(value or 0)
    if '<' in str(value):
        return 0.0
    value = str(value).replace('$', '').replace(',', '').strip()
    try:
        return float(value)
    except ValueError:
        return 0.0