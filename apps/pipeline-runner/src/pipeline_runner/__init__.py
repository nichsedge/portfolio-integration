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


def _wait_for_steps(steps: Dict[str, subprocess.Popen[Any]], timeout: int = 180) -> Dict[str, Dict[str, Any]]:
    """Wait for all subprocesses to complete with a timeout and return results."""
    results: Dict[str, Any] = {}

    for name, proc in steps.items():
        if proc is None:
            continue
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            results[name] = {
                "returncode": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
            }
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            results[name] = {
                "returncode": -1,
                "stdout": stdout,
                "stderr": f"❌ Process timed out after {timeout}s and was terminated.",
            }

    print("\n--- Fetch Results ---")
    for name, res in results.items():
        if res["returncode"] != 0:
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
    return results


def _attempt_fallback_cache(failed_sources: list[str], data_dir: Path, today: str) -> bool:
    """Attempts to copy previous day's raw data for failed sources."""
    import shutil
    source_map = {
        "KSEI": "ksei",
        "DeBank": "debank",
        "Binance": "binance",
        "Alchemy": "alchemy"
    }

    all_recovered = True
    for name in failed_sources:
        src_tag = source_map.get(name, name.lower())
        # Find latest available previous raw or curated file
        pattern = f"*_raw_{src_tag}.json" if src_tag != "alchemy" else "*_curated_alchemy.json"
        prev_files = sorted([
            f for f in data_dir.glob(pattern)
            if not f.name.startswith(today) and not f.name.startswith("latest")
        ])

        if prev_files:
            latest_prev = prev_files[-1]
            target_name = f"{today}_raw_{src_tag}.json" if src_tag != "alchemy" else f"{today}_curated_alchemy.json"
            target_path = data_dir / target_name
            shutil.copyfile(latest_prev, target_path)
            print(f"⚠️ [FALLBACK] Reused cached {name} data from {latest_prev.name} -> {target_name}")
        else:
            print(f"❌ [FALLBACK FAILED] No historical cache found for {name}")
            all_recovered = False

    return all_recovered


def _is_indonesia_market_holiday(day) -> bool:
    """True if `day` (date or 'YYYY-MM-DD' str) is an Indonesian public holiday."""
    import datetime as _dt
    if isinstance(day, str):
        day = _dt.date.fromisoformat(day)
    try:
        import holidays as pyholidays
        return day in pyholidays.country_holidays("ID", years=day.year)
    except ImportError:
        # Fallback: weekends only
        return day.weekday() >= 5


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
        "--fallback-cached", action="store_true", help="Fallback to previous day's cache if a fetch fails"
    )
    parser.add_argument(
        "--timeout", type=int, default=180, help="Per-fetcher subprocess timeout in seconds (default 180)"
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

    today = pendulum.now().format("YYYY-MM-DD")

    if not args.integrate and not args.backfill:
        print("--- Step 1: Fetch Raw Data ---")
        processes = {}

        ksei_is_holiday = _is_indonesia_market_holiday(today)
        if ksei_is_holiday:
            print(f"🇮🇩 {today} is an Indonesian public holiday — KSEI market closed, skipping fetch (cache fallback will be used)")
            processes["KSEI"] = None  # marker: skipped, not failed
        else:
            processes["KSEI"] = _start_non_blocking_step(
                "KSEI", str(repo_root), ["uv", "run", "ksei", "dump", "--output", str(data_dir)]
            )
        
        processes["DeBank"] = _start_non_blocking_step(
            "DeBank", str(repo_root), ["uv", "run", "debank-scrape", "--output", str(data_dir)]
        )
        
        binance_path = repo_root / "packages/binance-client"
        processes["Binance"] = _start_non_blocking_step("Binance", str(binance_path), ["uv", "run", "binance-fetch"])
        
        alchemy_path = repo_root / "packages/alchemy-client"
        if alchemy_path.exists():
            processes["Alchemy"] = _start_non_blocking_step("Alchemy", str(alchemy_path), ["uv", "run", "alchemy-fetch"])

        sansfinance_path = repo_root / "packages/sansfinance-client"
        if sansfinance_path.exists():
            processes["SansFinance"] = _start_non_blocking_step("SansFinance", str(sansfinance_path), ["uv", "run", "sansfinance-fetch"])

        fetch_results = _wait_for_steps(processes, timeout=args.timeout)
        fetch_results = {k: v for k, v in fetch_results.items() if v is not None}
        failed_steps = [name for name, res in fetch_results.items() if res["returncode"] != 0]

        # On Indonesian holidays KSEI is closed: treat as a failed step so the
        # cache fallback copies the last good raw KSEI file for today's date.
        if ksei_is_holiday:
            failed_steps.append("KSEI")

        if failed_steps:
            if args.fallback_cached:
                print(f"⚠️ Attempting cache fallback for failed steps: {', '.join(failed_steps)}")
                if not _attempt_fallback_cache(failed_steps, data_dir, today):
                    print("\nPipeline failed during data fetching and fallback failed. Aborting.")
                    sys.exit(1)
            else:
                print("\nPipeline failed during data fetching. Run with --fallback-cached to use previous day's data. Aborting.")
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
                
            # Set verbose=True for integration to show the rich summary
            if _run_blocking_step("Integration", str(integrator_path.parent), integrate_cmd, verbose=True):
                # Upload to Cloud (Cloudflare R2 & GCS) if configured
                try:
                    sys.path.insert(0, str(portfolio_app_path / "src"))
                    from portfolio_app.cloud_uploader import upload_to_cloud
                    
                    output_json_path = data_dir / f"{current_date}_snapshot.json"
                    output_ai_state_path = data_dir / f"{current_date}_ai_state.json"
                    output_ai_digest_path = data_dir / f"{current_date}_ai_digest.md"
                    
                    print(f"\n--- Step 3.5: Cloud Upload ({current_date}) ---")
                    upload_to_cloud(output_json_path)
                    if output_ai_state_path.exists():
                        upload_to_cloud(output_ai_state_path)
                    if output_ai_digest_path.exists():
                        upload_to_cloud(output_ai_digest_path)
                except Exception as e:
                    print(f"⚠️ Cloud upload failed: {e}")

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
