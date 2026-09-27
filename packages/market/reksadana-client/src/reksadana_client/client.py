"""Bibit API Client for fetching and decrypting Indonesian Mutual Fund data."""

import json
from pathlib import Path
from typing import Any

import httpx
import pendulum
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .models import FundProduct

BIBIT_API_URL = "https://api.bibit.id/products/filter"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Origin": "https://app.bibit.id",
    "Referer": "https://app.bibit.id/",
    "Accept": "application/json",
}


class BibitReksadanaClient:
    """Handles network extraction, AES-CBC decryption, and parsing of Indonesian mutual funds."""

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    @staticmethod
    def decrypt_payload(encrypted_data: str) -> list[dict[str, Any]]:
        """
        Decrypt the AES-CBC 128/256 payload returned by Bibit API.
        Structure:
          - First 32 hex chars (16 bytes): IV
          - Middle hex chars: Ciphertext
          - Last 32 chars: UTF-8 Secret Key
        """
        iv = bytes.fromhex(encrypted_data[:32])
        secret = encrypted_data[-32:].encode("utf-8")
        ciphertext = bytes.fromhex(encrypted_data[32:-32])

        cipher = Cipher(algorithms.AES(secret), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()

        # Remove PKCS7 padding
        pad_len = padded[-1]
        decrypted_str = padded[:-pad_len].decode("utf-8")
        return json.loads(decrypted_str)

    def fetch_page(self, page: int = 1, limit: int = 50) -> list[dict[str, Any]]:
        """Fetch a single page of mutual fund products."""
        with httpx.Client(timeout=self.timeout, headers=DEFAULT_HEADERS) as client:
            resp = client.get(BIBIT_API_URL, params={"page": page, "limit": limit})
            resp.raise_for_status()
            payload = resp.json()
            raw_data = payload.get("data")
            if not raw_data:
                return []
            return self.decrypt_payload(raw_data)

    def fetch_all(self, page_size: int = 50) -> list[FundProduct]:
        """Paginate through the complete mutual fund directory until no more products exist."""
        all_raw: list[dict[str, Any]] = []
        page = 1
        while True:
            items = self.fetch_page(page=page, limit=page_size)
            if not items:
                break
            all_raw.extend(items)
            if len(items) < page_size:
                break
            page += 1

        products: list[FundProduct] = []
        for raw in all_raw:
            try:
                prod = FundProduct.model_validate(raw)
                prod.raw_data = raw
                products.append(prod)
            except Exception:  # noqa: BLE001, S112
                continue
        return products

    def save_snapshot(
        self, products: list[FundProduct], data_dir: Path
    ) -> tuple[Path, Path]:
        """
        Save the fetched mutual fund data to:
        1. Date-based output: {YYYY-MM-DD}_market_reksadana.json
        2. Canonical leaf: market_reksadana.json
        """
        data_dir.mkdir(parents=True, exist_ok=True)
        today = pendulum.now().format("YYYY-MM-DD")
        dated_path = data_dir / f"{today}_market_reksadana.json"
        canonical_path = data_dir / "market_reksadana.json"

        # Serialize list of products
        serialized = [
            p.raw_data if p.raw_data else p.model_dump(by_alias=True)
            for p in products
        ]

        with open(dated_path, "w", encoding="utf-8") as f:
            json.dump(serialized, f, indent=2, ensure_ascii=False)

        with open(canonical_path, "w", encoding="utf-8") as f:
            json.dump(serialized, f, indent=2, ensure_ascii=False)

        return dated_path, canonical_path

    @staticmethod
    def load_catalog(data_dir: Path) -> list[FundProduct]:
        """Load fund catalog from disk (market_reksadana.json or latest raw)."""
        canonical_path = data_dir / "market_reksadana.json"
        if canonical_path.exists():
            with open(canonical_path, "r", encoding="utf-8") as f:
                raw_items = json.load(f)
                return [FundProduct.model_validate(item) for item in raw_items]

        # Look for most recent market_reksadana.json or legacy
        candidates = sorted(data_dir.glob("*_market_reksadana.json"), reverse=True)
        if not candidates:
            candidates = sorted(data_dir.glob("reksadana_catalog.json"), reverse=True)
        if candidates:
            with open(candidates[0], "r", encoding="utf-8") as f:
                raw_items = json.load(f)
                return [FundProduct.model_validate(item) for item in raw_items]

        return []
