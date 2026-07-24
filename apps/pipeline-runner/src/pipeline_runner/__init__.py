#!/usr/bin/env python3
"""
Portfolio Integration Pipeline Runner

Usage:
    uv run pipeline_runner              # Run full pipeline
    uv run pipeline_runner --fetch-only # Just fetch raw data
    uv run pipeline_runner --integrate  # Just integrate

Environment Variables:
    PORTFOLIO_DATA_DIR - Custom data directory (default: /REDACTED_HOME/Projects/.data/portfolio)
"""

import argparse
import os
import subprocess
import sys
import pendulum
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

# Load environment variables from root .env file
load_dotenv()

# Add packages to path for imports
repo_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(repo_root / "packages"))


def _run_blocking_step(name: str, pkg_path: str, command: list[str], verbose: bool = False) -> bool:
    """Run a pipeline step and wait for it to complete."""
    print(f"Running: {name}")

    result = subprocess.run(command, cwd=pkg_path, capture_output=True, text=True)

    if verbose and result.stdout:
        print(result.stdout.strip())

    if result.returncode != 0:
        print(f"❌ {name} failed with exit code {result.returncode}")
        if not verbose and result.stdout:
            print(f"--- {name} STDOUT ---")
            print(result.stdout.strip())
        if result.stderr:
            print(f"--- {name} STDERR ---")
            print(result.stderr.strip())
        return False

    print(f"✓ {name} completed")
    return True


def _start_non_blocking_step(
    name: str, pkg_path: str, command: list[str]
) -> subprocess.Popen[Any]:
    """Start a pipeline step subprocess for parallel execution."""
    print(f"Starting: {name}")

    process = subprocess.Popen(
        command,
        cwd=pkg_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return process


def _wait_for_steps(steps: Dict[str, subprocess.Popen[Any]]) -> bool:
    """Wait for all subprocesses to complete and log results. Returns False on any failure."""
    all_success = True
    results: Dict[str, Any] = {}

    for name, proc in steps.items():
        stdout, stderr = proc.communicate()
        results[name] = {
            "returncode": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }

    print("\n--- Fetch Results ---")
    for name, res in results.items():
        if res["returncode"] != 0:
            all_success = False
            print(f"❌ {name} failed with exit code {res['returncode']}")
            if res["stdout"]:
                print(f"--- {name} STDOUT ---")
                print(res["stdout"].strip())
            if res["stderr"]:
                print(f"--- {name} STDERR ---")
                print(res["stderr"].strip())
        else:
            print(f"✓ {name} completed")
            first_line = res["stdout"].splitlines()[0] if res["stdout"] else ""
            if first_line:
                print(f"  > {first_line.strip()}")

    print()
    return all_success


def main():
    parser = argparse.ArgumentParser(description="Portfolio Integration Pipeline")
    parser.add_argument("--fetch-only", action="store_true", help="Only fetch raw data")
    parser.add_argument(
        "--integrate", action="store_true", help="Skip fetching, just integrate"
    )
    parser.add_argument(
        "--backfill", action="store_true", help="Generate for all dates that exist in data/"
    )
    parser.add_argument(
        "--skip-manual", action="store_true", help="Skip manual balances in integration"
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[4]
    default_data_dir = repo_root / "data"

    data_dir_path = (
        os.getenv("PORTFOLIO_DATA_DIR")
        or os.getenv("DATA_DIR")
        or str(default_data_dir)
    )
    data_dir = Path(data_dir_path)

    print("🚀 Portfolio Integration Pipeline")
    print(f"Data directory: {data_dir}\n")

    if not args.integrate and not args.backfill:
        print("--- Step 1: Fetch Raw Data ---")
        processes = {}
        
        ksei_path = repo_root / "packages/ksei-client"
        processes["KSEI"] = _start_non_blocking_step("KSEI", str(ksei_path), ["uv", "run", "examples/fetch_and_dump_portfolios.py"])
        
        debank_path = repo_root / "packages/debank-scraper"
        processes["DeBank"] = _start_non_blocking_step("DeBank", str(debank_path), ["uv", "run", "debank-scrape"])
        
        binance_path = repo_root / "packages/binance-client"
        processes["Binance"] = _start_non_blocking_step("Binance", str(binance_path), ["uv", "run", "binance-fetch"])
        
        alchemy_path = repo_root / "packages/alchemy-client"
        if alchemy_path.exists():
            processes["Alchemy"] = _start_non_blocking_step("Alchemy", str(alchemy_path), ["uv", "run", "alchemy-fetch"])


        if not _wait_for_steps(processes):
            print("\nPipeline failed during data fetching. Aborting.")
            sys.exit(1)

    if not args.fetch_only:
        dates_to_process = [pendulum.now().format("YYYY-MM-DD")]
        
        if args.backfill:
            print("--- Backfill Mode: Identifying dates ---")
            import re
            # Improved regex to find dates in all raw files
            raw_files = list(data_dir.glob("*_raw_*.json")) + list(data_dir.glob("*-raw-*.json"))
            found_dates = set()
            for f in raw_files:
                match = re.search(r"(\d{4}-\d{2}-\d{2})", f.name)
                if match:
                    found_dates.add(match.group(1))
            
            if not found_dates:
                print("No raw data files found for backfill.")
                sys.exit(0)
                
            dates_to_process = sorted(list(found_dates))
            print(f"Found {len(dates_to_process)} dates to process: {', '.join(dates_to_process)}")

        portfolio_app_path = repo_root / "packages/portfolio-app"

        for current_date in dates_to_process:
            print(f"\nProcessing date: {current_date}")
            print(f"--- Step 2: Transform Data ({current_date}) ---")

            # Dynamically find all transformers
            transformers_dir = portfolio_app_path / "src/portfolio_app/transformers"
            transform_scripts = sorted(list(transformers_dir.glob("*_transform.py")))
            
            for script_path in transform_scripts:
                name = script_path.stem.replace("_", " ").title()
                _run_blocking_step(name, str(script_path.parent), [sys.executable, str(script_path), "--date", current_date])

            print(f"--- Step 3: Integrate ({current_date}) ---")
            integrator_path = portfolio_app_path / "src/portfolio_app/integrators/portfolio_integration.py"
            
            integrate_cmd = [sys.executable, str(integrator_path), "--date", current_date]
            if args.skip_manual:
                integrate_cmd.append("--skip-manual")
                
            # Set verbose=True for integration to show the rich summary
            if _run_blocking_step("Integration", str(integrator_path.parent), integrate_cmd, verbose=True):
                # Upload to GCS if configured
                try:
                    sys.path.insert(0, str(portfolio_app_path / "src"))
                    from portfolio_app.gcs_uploader import upload_to_gcs
                    
                    output_csv_path = data_dir / f"{current_date}_portfolio.csv"
                    output_json_path = data_dir / f"{current_date}_snapshot.json"
                    
                    print(f"\n--- Step 3.5: GCS Upload ({current_date}) ---")
                    upload_to_gcs(output_json_path)
                    upload_to_gcs(output_csv_path)
                except Exception as e:
                    print(f"⚠️ GCS upload failed: {e}")

        print("\n--- Step 4: Generate Insights ---")
        insights_path = portfolio_app_path / "src/portfolio_app/generate_insights.py"
        if insights_path.exists():
            _run_blocking_step("Insights Generation", str(repo_root), [sys.executable, str(insights_path)])
        else:
            print(f"⚠ Skipping Insights Generation: {insights_path} not found")

    print("\n✨ Pipeline completed successfully!")


def fetch_entrypoint():
    if "--fetch-only" not in sys.argv:
        sys.argv.append("--fetch-only")
    main()


def integrate_entrypoint():
    if "--integrate" not in sys.argv:
        sys.argv.append("--integrate")
    main()


if __name__ == "__main__":
    main()
