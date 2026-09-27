# Portfolio Transform Core

Shared utilities for portfolio data transformation across all sources.

## Features

- `get_data_dir()` - Get data directory from PORTFOLIO_DATA_DIR environment variable
- `parse_usd()` - Parse USD strings to float, handling edge cases
- `DATA_DIR_DEFAULT` - Constant for default data directory
- `FILTER_THRESHOLDS` - Dictionary of filtering thresholds for each currency (IDR, USD)

## Usage

```python
from transform_core import get_data_dir, parse_usd, FILTER_THRESHOLDS

# Get data directory
data_dir = get_data_dir()

# Parse USD value
value = parse_usd("$123.45")  # 123.45
value = parse_usd("<$0.01")   # 0.0

# Get filter threshold
threshold = FILTER_THRESHOLDS["IDR"]  # 50000
```