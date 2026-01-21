import os
from pathlib import Path


def get_data_dir() -> Path:
    """
    Get the data directory path from environment variables or use default.

    Priority order:
    1. PORTFOLIO_DATA_DIR environment variable
    2. DATA_DIR environment variable (alias)
    3. Hardcoded default: /REDACTED_HOME/Projects/.data/portfolio

    Returns:
        Path object pointing to the data directory
    """
    data_dir = os.getenv("PORTFOLIO_DATA_DIR") or os.getenv("DATA_DIR") or "/REDACTED_HOME/Projects/.data/portfolio"
    return Path(data_dir)