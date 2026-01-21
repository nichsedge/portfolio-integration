# CONTRIBUTING.md

Contributing to Portfolio Integration

## How to Add a New Data Source

### 1. Create a New Extractor Package

Create a new directory under `packages/<source-name>-client/` with:
- `src/<source_name>/__init__.py` - Package initialization
- `src/<source_name>/client.py` - Main client/fetcher code
- `pyproject.toml` - Package configuration

Add the new package to the workspace `pyproject.toml`.

### 2. Create a Transformer

Create `packages/portfolio-app/src/portfolio_app/transformers/<source>_transform.py`:

```python
import json
import pendulum
import sys
from pathlib import Path

# Import from transform-core
repo_root = Path(__file__).parents[4]
sys.path.insert(0, str(repo_root / "packages"))
from transform_core import get_data_dir, FILTER_THRESHOLDS

def clean_<source>_data(raw_data):
    """Clean and extract relevant <source> data."""
    # Your cleaning logic here
    return cleaned_data

# Main execution
td = pendulum.now().format('YYYY-MM-DD')
data_dir = get_data_dir()
raw_path = data_dir / f"{td}_raw_<source>.json"
curated_path = data_dir / f"{td}_curated_<source>.json"
```

### 3. Update the Pipeline Runner

Add your new step to `apps/pipeline-runner/src/main.py`:
- Add fetch step in the `not args.integrate` section
- Add transform step in the `not args.fetch_only` section

### 4. Add Integration Logic

Add `standardize_<source>_data()` function to the portfolio integrator.

### 5. Add Filter Threshold

Add your source to `FILTER_THRESHOLDS` in `packages/transform-core/src/transform_core/constants.py`.

## Code Style Guidelines

- **Python**: Follow PEP 8
- **Type Hints**: Use type hints for all public functions
- **Docstrings**: Use Google-style docstrings
- **Imports**: Group imports (stdlib, third-party, local)

## Testing

- Each package should have its own tests
- Test with sample data files before committing

## Submitting Changes

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

Happy contributing!