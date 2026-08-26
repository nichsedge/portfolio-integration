"""Fetch the latest Sans Finance SQLite snapshot from Cloudflare R2 and emit raw JSON.

Downloads ``db/sans_finance_latest.sqlite`` from the configured R2 bucket,
reads the latest portfolio holdings + non-investment accounts, and writes
``{YYYY-MM-DD}_raw_sansfinance.json`` following the pipeline convention.

Credentials are resolved from (in order):
1. Environment: R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY (/ R2_BUCKET_NAME)
2. ``~/Projects/sansfinance/app/src/main/assets/r2_cred.json`` (the APK's bundled creds)

The wrangler CLI (``wrangler r2 object get ... --remote``) is used as a fallback
when direct S3-signed download is unavailable.
"""

import json
import os
import sqlite3
import tempfile
from pathlib import Path

import pendulum

try:
    from transform_core import get_data_dir
except ImportError:
    get_data_dir = None

R2_BUCKET_NAME = "ichsanul-dev"
R2_BLOB_NAME = "db/sans_finance_latest.sqlite"

CRED_CANDIDATES = [
    Path.home() / "Projects" / "sansfinance" / "app" / "src" / "main" / "assets" / "r2_cred.json",
]

# Account types from the Sans Finance app that count toward cash net worth.
INCLUDED_ACCOUNT_TYPES = {"Cash", "Bank Account", "P2P Lending"}


def load_r2_credentials():
    """Resolve R2 credentials from env or the sansfinance repo's bundled creds."""
    account_id = os.getenv("R2_ACCOUNT_ID") or os.getenv("CLOUDFLARE_ACCOUNT_ID")
    access_key = os.getenv("R2_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY")
    bucket = os.getenv("R2_BUCKET_NAME") or R2_BUCKET_NAME

    if not (account_id and access_key and secret_key):
        for candidate in CRED_CANDIDATES:
            if candidate.exists():
                try:
                    data = json.loads(candidate.read_text())
                    account_id = account_id or data.get("account_id")
                    access_key = access_key or data.get("access_key_id")
                    secret_key = secret_key or data.get("secret_access_key")
                    bucket = data.get("bucket_name") or bucket
                    break
                except Exception:
                    continue
    return account_id, access_key, secret_key, bucket


def _download_via_wrangler(bucket: str, dest: Path) -> bool:
    import subprocess

    cmd = ["wrangler"]
    if not any(_which(c) for c in ("wrangler",)):
        bunx = _which("bunx") or _which("npx")
        if not bunx:
            return False
        cmd = [bunx, "wrangler"]
    result = subprocess.run(
        cmd + ["r2", "object", "get", f"{bucket}/{R2_BLOB_NAME}", f"--file={dest}", "--remote"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return result.returncode == 0 and dest.exists()


def _which(name: str):
    from shutil import which

    return which(name)


def download_db(dest: Path) -> None:
    """Download the SQLite DB to dest via signed URL or wrangler fallback."""
    account_id, access_key, secret_key, bucket = load_r2_credentials()

    if account_id and access_key and secret_key:
        try:
            url = download_url(account_id, access_key, secret_key, bucket)
            import urllib.request

            urllib.request.urlretrieve(url, dest)
            if dest.exists() and dest.stat().st_size > 0:
                return
        except Exception as e:
            print(f"⚠️ Direct R2 download failed ({e}); trying wrangler fallback...")

    if _download_via_wrangler(bucket, dest):
        return

    raise RuntimeError("Failed to download Sans Finance DB from R2 (no credentials or CLI).")


def download_url(account_id: str, access_key: str, secret_key: str, bucket: str) -> str:
    """Generate a presigned GET URL for the DB object."""
    import datetime
    import hashlib
    import hmac

    host = f"{account_id}.r2.cloudflarestorage.com"
    key = R2_BLOB_NAME.replace("/", "%2F")
    now = int(datetime.datetime.now(datetime.UTC).timestamp())
    datestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d")
    scope = f"{datestamp}/auto/s3/aws4_request"
    canonical = f"GET\n/{bucket}/{key}\n\nhost:{host}\nx-amz-content-sha256:UNSIGNED-PAYLOAD\nx-amz-date:{now}\n"
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n{now}\n{scope}\n{hashlib.sha256(canonical.encode()).hexdigest()}"
    )

    def hmac_sha256(key, msg):
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    k_date = hmac_sha256(f"AWS4{secret_key}".encode(), datestamp)
    k_region = hmac_sha256(k_date, "auto")
    k_service = hmac_sha256(k_region, "s3")
    k_signing = hmac_sha256(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()

    query = (
        f"?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential={access_key}%2F{scope}"
        f"&X-Amz-Date={now}&X-Amz-Expires=60&X-Amz-SignedHeaders={signed_headers}&X-Amz-Signature={signature}"
    )
    return f"https://{host}/{bucket}/{key}{query}"


def extract_raw(db_path: Path) -> dict:
    """Extract accounts + latest portfolio snapshot summary from the SQLite DB."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        header = conn.execute(
            "SELECT snapshotDate, exchangeRateUsd FROM portfolio_snapshot_headers "
            "ORDER BY snapshotDate DESC LIMIT 1"
        ).fetchone()
        accounts = [
            {
                "name": row["name"],
                "type": row["type"],
                # Balances are stored in cents; convert to major units.
                "balance": (row["balance"] or 0) / 100.0,
                "currency": row["currency"] or "IDR",
            }
            for row in conn.execute("SELECT name, type, balance, currency FROM accounts")
            if row["type"] in INCLUDED_ACCOUNT_TYPES
        ]
        holdings_count = 0
        holdings_total_idr = 0.0
        if header:
            stats = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(value_idr), 0) FROM portfolio_holdings WHERE snapshot_date = ?",
                (header["snapshotDate"],),
            ).fetchone()
            holdings_count, holdings_total_idr = stats[0], float(stats[1])
        return {
            "latest_snapshot_date": header["snapshotDate"] if header else None,
            "exchange_rate_usd": header["exchangeRateUsd"] if header else None,
            "holdings_count": holdings_count,
            "portfolio_value_idr": holdings_total_idr,
            "accounts": accounts,
        }
    finally:
        conn.close()


def main(output_dir=None):
    if output_dir is None:
        output_dir = os.getenv("PORTFOLIO_DATA_DIR") or (
            get_data_dir() if get_data_dir else "."
        )
    data_dir = Path(output_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        print("⬇️ Downloading Sans Finance DB from R2...")
        download_db(tmp_path)
        raw = extract_raw(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    raw["timestamp"] = pendulum.now("UTC").isoformat()

    date_str = pendulum.now().format("YYYY-MM-DD")
    out_path = data_dir / f"{date_str}_raw_sansfinance.json"
    out_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    total_cash = sum(a["balance"] for a in raw["accounts"] if a["currency"] == "IDR")
    print(
        f"Wrote {len(raw['accounts'])} accounts "
        f"(cash+P2P ≈ Rp {total_cash:,.0f}) to {out_path}"
    )


if __name__ == "__main__":
    main()
