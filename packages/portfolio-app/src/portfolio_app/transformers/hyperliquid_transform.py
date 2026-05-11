"""Hyperliquid vault fetcher and transformer.

Fetches vault positions and user vaults from Hyperliquid API.
"""

import json
import os
import requests
import pendulum
from pathlib import Path
from typing import List, Dict, Any

# Add transform-core to path
repo_root = Path(__file__).parents[4]
import sys

sys.path.insert(0, str(repo_root / "packages"))

from transform_core import get_data_dir, FILTER_THRESHOLDS

HYPERLIQUID_API_BASE = "https://api.hyperliquid.xyz"


def fetch_vault_positions(wallet_address: str) -> List[Dict[str, Any]]:
    """Fetch vault positions for a specific wallet address.

    Args:
        wallet_address: EVM wallet address

    Returns:
        List of vault position dictionaries
    """
    url = f"{HYPERLIQUID_API_BASE}/info"
    data = {"type": "userVaultEquities", "user": wallet_address}

    try:
        response = requests.post(url, json=data, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching vault positions: {e}")
        return []


def fetch_vault_info(vault_address: str) -> Dict[str, Any]:
    """Fetch detailed information about a specific vault.

    Args:
        vault_address: Vault contract address

    Returns:
        Vault information dictionary
    """
    url = f"{HYPERLIQUID_API_BASE}/info"
    data = {"type": "vault", "vaultAddress": vault_address}

    try:
        response = requests.post(url, json=data, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching vault info: {e}")
        return {}


def fetch_user_vaults(wallet_address: str) -> List[Dict[str, Any]]:
    """Fetch vaults created/managed by the wallet address.

    Args:
        wallet_address: EVM wallet address

    Returns:
        List of user vault dictionaries
    """
    url = f"{HYPERLIQUID_API_BASE}/info"
    data = {"type": "userVaults", "user": wallet_address}

    try:
        response = requests.post(url, json=data, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching user vaults: {e}")
        return []


def parse_usd_value(value: Any) -> float:
    """Parse USD value from API response, handling various formats.

    Args:
        value: Value from API (number, string, or None)

    Returns:
        Float USD value (0.0 if parsing fails)
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # Remove common formatting and convert
        value = value.replace("$", "").replace(",", "").strip()
        if "<" in value:
            return 0.0
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def standardize_vault_position(
    position: Dict[str, Any], wallet_address: str
) -> Dict[str, Any]:
    """Convert a vault position to the standardized format.

    Args:
        position: Vault position data from API
        wallet_address: User's wallet address

    Returns:
        Standardized portfolio entry
    """
    vault_address = position.get("vaultAddress", "")
    vault_name = position.get("vaultName", f"Vault {vault_address[:8]}...")

    # Get USD value of position (equity field from new API)
    usd_value = parse_usd_value(position.get("equity", 0))

    # Get locked timestamp if available
    locked_until = position.get("lockedUntilTimestamp", "")

    # Create details string
    details_parts = [
        f"Vault: {vault_name}",
        f"Address: {vault_address}",
        f"Wallet: {wallet_address}",
    ]

    if locked_until:
        details_parts.append(f"Locked until: {locked_until}")

    return {
        "source": "Hyperliquid",
        "category": "Vault Position",
        "asset": vault_name,
        "currency": "USD",
        "amount": 1.0,  # Representing share units
        "value_idr": None,
        "value_usd": usd_value,
        "account": f"{vault_name} ({vault_address[:8]}...)",
        "details": ", ".join(details_parts),
    }


def standardize_user_vault(
    vault: Dict[str, Any], wallet_address: str
) -> List[Dict[str, Any]]:
    """Convert a user-created vault to standardized format(s).

    Args:
        vault: User vault data from API
        wallet_address: Managing wallet address

    Returns:
        List of standardized portfolio entries
    """
    standardized = []
    vault_address = vault.get("address", "")
    vault_name = vault.get("name", f"Vault {vault_address[:8]}...")

    # Add the vault itself (not a position, but the vault creation)
    if vault.get("totalValueUsd", 0):
        standardized.append(
            {
                "source": "Hyperliquid",
                "category": "Vault Management",
                "asset": vault_name,
                "currency": "USD",
                "amount": 0.0,
                "value_idr": None,
                "value_usd": parse_usd_value(vault.get("totalValueUsd", 0)),
                "account": f"Manager: {wallet_address[:8]}...",
                "details": f"Created vault: {vault_name}, TVL: ${vault.get('totalValueUsd', 0):,.2f}",
            }
        )

    return standardized


def fetch_and_process_hyperliquid_data(wallet_address: str) -> Dict[str, Any]:
    """Fetch all Hyperliquid data for a wallet.

    Args:
        wallet_address: EVM wallet address

    Returns:
        Dictionary with raw and standardized data
    """
    print(f"Fetching Hyperliquid data for wallet: {wallet_address}")

    # Fetch vault positions (investments in vaults)
    positions = fetch_vault_positions(wallet_address)
    investments = []

    threshold = FILTER_THRESHOLDS.get("USD", 5)

    for position in positions:
        standardized = standardize_vault_position(position, wallet_address)
        if standardized["value_usd"] >= threshold:
            investments.append(standardized)

    # Fetch user-created vaults
    user_vaults = fetch_user_vaults(wallet_address)
    created_vaults = []

    for vault in user_vaults:
        vault_standardized = standardize_user_vault(vault, wallet_address)
        created_vaults.extend(vault_standardized)

    # Combine all data
    all_data = investments + created_vaults

    print(
        f"Found {len(investments)} vault investments and {len(created_vaults)} created vaults"
    )

    return {
        "raw": {"positions": positions, "user_vaults": user_vaults},
        "standardized": all_data,
    }


def save_hyperliquid_data(
    wallet_address: str, output_dir: Path = None
) -> Dict[str, Any]:
    """Fetch and save Hyperliquid data to JSON files.

    Args:
        wallet_address: EVM wallet address
        output_dir: Output directory (defaults to data dir from env)

    Returns:
        Dictionary with raw and standardized data
    """
    if output_dir is None:
        output_dir = get_data_dir()

    data = fetch_and_process_hyperliquid_data(wallet_address)

    # Use ISO date format
    date_str = pendulum.now("UTC").to_date_string()

    # Save raw data
    raw_path = output_dir / f"{date_str}_raw_hyperliquid.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(data["raw"], f, indent=2)

    # Save cleaned data (same as standardized for now)
    cleaned_path = output_dir / f"{date_str}_curated_hyperliquid.json"
    with open(cleaned_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": pendulum.now("UTC").to_iso8601_string().replace("+00:00", "Z"),
            "vault_positions": data["standardized"]
        }, f, indent=2)

    print(f"Saved raw data to {raw_path}")
    print(f"Saved curated data to {cleaned_path}")

    return data


def main():
    """Main entry point - fetch wallet address from environment and save data."""
    wallet_address = os.getenv("HYPERLIQUID_WALLET_ADDRESS")

    if not wallet_address:
        print("Error: HYPERLIQUID_WALLET_ADDRESS environment variable not set")
        print("Set it with: export HYPERLIQUID_WALLET_ADDRESS=0x...")
        return

    data = save_hyperliquid_data(wallet_address)
    print(f"\nTotal vault positions found: {len(data['standardized'])}")


if __name__ == "__main__":
    main()
