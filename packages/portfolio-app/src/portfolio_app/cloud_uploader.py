import datetime
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Optional, Tuple

R2_DEFAULT_BUCKET = "ichsanul-dev"
GCS_DEFAULT_BUCKET = "ichsanul-portfolio-snapshots"

CRED_CANDIDATES = [
    Path.home() / "Projects" / "creds" / "cloudflare" / "r2_cred.json",
    Path.home() / "Projects" / "sansfinance" / "app" / "src" / "main" / "assets" / "r2_cred.json",
]


def load_r2_credentials() -> Tuple[Optional[str], Optional[str], Optional[str], str]:
    """Resolve R2 credentials from env or local creds repository."""
    account_id = os.getenv("R2_ACCOUNT_ID") or os.getenv("CLOUDFLARE_ACCOUNT_ID")
    access_key = os.getenv("R2_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY")
    bucket = os.getenv("R2_BUCKET_NAME") or R2_DEFAULT_BUCKET

    if not (account_id and access_key and secret_key):
        for candidate in CRED_CANDIDATES:
            if candidate.exists():
                try:
                    data = json.loads(candidate.read_text(encoding="utf-8"))
                    account_id = account_id or data.get("account_id")
                    access_key = access_key or data.get("access_key_id")
                    secret_key = secret_key or data.get("secret_access_key")
                    bucket = data.get("bucket_name") or bucket
                    if account_id and access_key and secret_key:
                        break
                except Exception:
                    continue

    return account_id, access_key, secret_key, bucket


def get_prefix_and_latest_name(file_path: Path) -> Tuple[str, Optional[str]]:
    """Determine cloud folder prefix and canonical latest object name."""
    name = file_path.name
    if "ai_state" in name:
        return "ai", "latest_state.json"
    if "ai_digest" in name:
        return "ai", "latest_digest.md"
    if "_snapshot.json" in name:
        return "snapshots", "latest.json"
    if file_path.suffix == ".json":
        return "snapshots", None
    return "misc", None


def upload_via_wrangler(bucket: str, object_key: str, file_path: Path) -> bool:
    """Upload an object to R2 using wrangler CLI."""
    wrangler_cmd = ["wrangler"]
    if not shutil.which("wrangler"):
        bunx = shutil.which("bunx") or shutil.which("npx")
        if not bunx:
            return False
        wrangler_cmd = [bunx, "wrangler"]

    cmd = wrangler_cmd + [
        "r2",
        "object",
        "put",
        f"{bucket}/{object_key}",
        f"--file={file_path}",
        "--remote",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return res.returncode == 0
    except Exception as e:
        print(f"⚠️ Wrangler upload failed for {object_key}: {e}")
        return False


def upload_to_r2(file_path: Path, bucket_name: Optional[str] = None) -> bool:
    """Uploads a file to Cloudflare R2 including dated and latest keys."""
    if not file_path.exists():
        print(f"❌ Error: File {file_path} does not exist.")
        return False

    account_id, access_key, secret_key, detected_bucket = load_r2_credentials()
    bucket = bucket_name or detected_bucket

    prefix, latest_key_name = get_prefix_and_latest_name(file_path)
    destination_key = f"{prefix}/{file_path.name}"
    keys_to_upload = [destination_key]
    if latest_key_name and not file_path.name.startswith("latest"):
        keys_to_upload.append(f"{prefix}/{latest_key_name}")

    # Method 1: S3 SigV4 direct upload if credentials available
    if account_id and access_key and secret_key:
        try:
            content = file_path.read_bytes()
            payload_hash = hashlib.sha256(content).hexdigest()
            content_type = "application/json" if file_path.suffix == ".json" else "text/markdown"

            host = f"{account_id}.r2.cloudflarestorage.com"
            now = datetime.datetime.now(datetime.timezone.utc)
            amz_date = now.strftime("%Y%m%dT%H%M%SZ")
            date_stamp = now.strftime("%Y%m%d")

            for key in keys_to_upload:
                canonical_uri = f"/{bucket}/{key}"
                endpoint_url = f"https://{host}{canonical_uri}"

                headers = {
                    "content-type": content_type,
                    "host": host,
                    "x-amz-content-sha256": payload_hash,
                    "x-amz-date": amz_date,
                }
                canonical_headers = "".join([f"{k}:{v}\n" for k, v in sorted(headers.items())])
                signed_headers = ";".join(sorted(headers.keys()))
                canonical_request = (
                    f"PUT\n{canonical_uri}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
                )
                canonical_req_hash = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
                credential_scope = f"{date_stamp}/auto/s3/aws4_request"
                string_to_sign = (
                    f"AWS4-HMAC-SHA256\n{amz_date}\n{credential_scope}\n{canonical_req_hash}"
                )

                def sign(k, msg):
                    return hmac.new(k, msg.encode("utf-8"), hashlib.sha256).digest()

                k_date = sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
                k_region = sign(k_date, "auto")
                k_service = sign(k_region, "s3")
                k_signing = sign(k_service, "aws4_request")
                signature = hmac.new(
                    k_signing, string_to_sign.encode("utf-8"), hashlib.sha256
                ).hexdigest()
                auth_header = (
                    f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
                    f"SignedHeaders={signed_headers}, Signature={signature}"
                )

                req = urllib.request.Request(
                    endpoint_url,
                    data=content,
                    headers={
                        "Authorization": auth_header,
                        "Content-Type": content_type,
                        "Host": host,
                        "x-amz-date": amz_date,
                        "x-amz-content-sha256": payload_hash,
                    },
                    method="PUT",
                )
                with urllib.request.urlopen(req, timeout=20) as resp:
                    if resp.status not in (200, 201, 204):
                        raise RuntimeError(f"HTTP status {resp.status}")

                print(f"✅ Uploaded to r2://{bucket}/{key}")

            return True
        except Exception as e:
            print(f"⚠️ Direct R2 SigV4 upload failed ({e}); falling back to wrangler CLI...")

    # Method 2: Fallback to Wrangler CLI
    success = True
    for key in keys_to_upload:
        if upload_via_wrangler(bucket, key, file_path):
            print(f"✅ Uploaded to r2://{bucket}/{key}")
        else:
            print(f"❌ Failed to upload {file_path.name} to r2://{bucket}/{key}")
            success = False

    return success


def get_gcs_storage_client():
    """Initialize GCP Storage Client using configured credentials."""
    from google.cloud import storage

    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path:
        projects_dir = Path(__file__).resolve().parents[5]
        local_creds = str(projects_dir / "creds" / "gcp" / "SA_cred_general.json")
        if os.path.exists(local_creds):
            creds_path = local_creds

    if creds_path and os.path.exists(creds_path):
        return storage.Client.from_service_account_json(creds_path)

    return storage.Client()


def upload_to_gcs(file_path: Path, bucket_name: Optional[str] = None) -> bool:
    """Uploads a portfolio file to Google Cloud Storage if configured."""
    bucket_name = (
        bucket_name
        or os.getenv("PORTFOLIO_GCS_BUCKET")
        or os.getenv("GCS_BUCKET_NAME")
        or GCS_DEFAULT_BUCKET
    )

    if not file_path.exists():
        print(f"❌ Error: File {file_path} does not exist.")
        return False

    try:
        client = get_gcs_storage_client()
        bucket = client.bucket(bucket_name)

        prefix, latest_key_name = get_prefix_and_latest_name(file_path)
        destination_blob_name = f"{prefix}/{file_path.name}"

        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(str(file_path))
        print(f"✅ Uploaded to gs://{bucket_name}/{destination_blob_name}")

        if latest_key_name and not file_path.name.startswith("latest"):
            latest_blob = bucket.blob(f"{prefix}/{latest_key_name}")
            latest_blob.upload_from_filename(str(file_path))
            print(f"📌 Updated gs://{bucket_name}/{prefix}/{latest_key_name}")

        return True
    except Exception as e:
        print(f"⚠️ GCS upload failed for {file_path.name}: {e}")
        return False


def upload_to_cloud(file_path: Path, enable_gcs: Optional[bool] = None) -> Dict[str, bool]:
    """Primary upload to Cloudflare R2, with optional Google Cloud Storage (GCS) upload."""
    results = {}
    print(f"\n☁️ Uploading {file_path.name} to Cloudflare R2...")
    results["r2"] = upload_to_r2(file_path)

    # GCS is optional: only uploaded if explicitly enabled or configured
    should_upload_gcs = enable_gcs
    if should_upload_gcs is None:
        gcs_env = os.getenv("ENABLE_GCS_UPLOAD", "false").lower() in ("true", "1", "yes")
        provider_env = os.getenv("PORTFOLIO_STORAGE_PROVIDER", "r2").lower() in ("all", "both", "gcs")
        should_upload_gcs = gcs_env or provider_env

    if should_upload_gcs:
        print(f"☁️ Uploading {file_path.name} to Google Cloud Storage (optional)...")
        results["gcs"] = upload_to_gcs(file_path)
    else:
        results["gcs"] = False

    return results
