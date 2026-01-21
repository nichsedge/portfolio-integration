#!/usr/bin/env python3
"""
Portfolio Integration Pipeline Runner

Usage:
    python -m pipeline_runner              # Run full pipeline
    python -m pipeline_runner --fetch-only # Just fetch raw data
    python -m pipeline_runner --integrate  # Just integrate

Environment Variables:
    PORTFOLIO_DATA_DIR - Custom data directory (default: /home/al/Projects/.data/portfolio)
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Add packages to path for imports
repo_root = Path(__file__).parents[3]
sys.path.insert(0, str(repo_root / "packages"))


def run_step(name: str, pkg_path: str, command: list[str]) -> bool:
    """Run a pipeline step."""
    print(f"Running: {name}")

    # For uv run commands, use the simpler approach
    if command and command[0] == "uv" and len(command) > 1 and command[1] == "run":
        result = subprocess.run(command, cwd=pkg_path, capture_output=True, text=True)
    else:
        result = subprocess.run(command, cwd=pkg_path, capture_output=True, text=True)

    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        print(f"❌ {name} failed:")
        print(result.stderr)
        return False
    print(f"✓ {name} completed\n")
    return True


def main():
    parser = argparse.ArgumentParser(description="Portfolio Integration Pipeline")
    parser.add_argument("--fetch-only", action="store_true", help="Only fetch raw data")
    parser.add_argument("--integrate", action="store_true", help="Skip fetching, just integrate")
    args = parser.parse_args()

    data_dir = os.getenv("PORTFOLIO_DATA_DIR", "/home/al/Projects/.data/portfolio")

    print("🚀 Portfolio Integration Pipeline")
    print(f"Data directory: {data_dir}\n")

    # Get repo root path
    repo_root = Path(__file__).parents[3]

    if not args.integrate:
        # Step 1: Fetch Raw Data
        print("--- Step 1: Fetch Raw Data ---")

        # KSEI
        ksei_path = repo_root / "packages/ksei-client"
        run_step("KSEI", str(ksei_path), ["uv", "run", "examples/fetch_and_dump_portfolios.py"])

        # DeBank (Node.js)
        debank_path = repo_root / "packages/debank-scraper"
        run_step("DeBank", str(debank_path), ["npm", "run", "scrape"])

        # Binance
        binance_path = repo_root / "packages/binance-client"
        run_step("Binance", str(binance_path), ["uv", "run", "ccxt_balance.py"])

    if not args.fetch_only:
        # Step 2: Transform Data
        print("--- Step 2: Transform Data ---")

        portfolio_app_path = repo_root / "packages/portfolio-app"

        # Transform - execute python files directly
        transform_files = [
            ("KSEI transform", portfolio_app_path / "src/portfolio_app/transformers/ksei_transform.py"),
            ("DeBank transform", portfolio_app_path / "src/portfolio_app/transformers/debank_transform.py"),
            ("Binance transform", portfolio_app_path / "src/portfolio_app/transformers/binance_transform.py"),
        ]

        for name, script_path in transform_files:
            if script_path.exists():
                run_step(name, str(script_path), [sys.executable, str(script_path)])
            else:
                print(f"⚠ Skipping {name}: script not found")

        # Step 3: Integrate
        print("--- Step 3: Integrate ---")
        integrator_path = portfolio_app_path / "src/portfolio_app/integrators/portfolio_integration.py"
        run_step("Integration", str(integrator_path.parent), [sys.executable, str(integrator_path)])

    print("\n✨ Pipeline completed successfully!")


if __name__ == "__main__":
    main()