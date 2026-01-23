import os
from pathlib import Path


def get_data_dir() -> Path:
    """
    Get the data directory path from environment variables or use default.

    Priority order:
    1. PORTFOLIO_DATA_DIR environment variable
    2. DATA_DIR environment variable (alias)
    3. Hardcoded default: [Project Root]/data

    Returns:
        Path object pointing to the data directory
    """
    # Find the repo root (assumes this file is in packages/portfolio-app/utils/path_utils.py)
    repo_root = Path(__file__).resolve().parents[3]
    data_dir_default = repo_root / "data"

    data_dir = os.getenv("PORTFOLIO_DATA_DIR") or os.getenv("DATA_DIR")
    if data_dir:
        return Path(data_dir)
    return data_dir_default