import os
from pathlib import Path
from google.cloud import storage

def get_storage_client() -> storage.Client:
    """Initialize a GCP Storage Client using configured credentials."""
    # 1. Check for standard environment variable
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    
    # 2. Fallback to local creds repository path
    if not creds_path:
        projects_dir = Path(__file__).resolve().parents[5]
        local_creds = str(projects_dir / "creds" / "gcp" / "SA_cred_general.json")
        if os.path.exists(local_creds):
            creds_path = local_creds
            
    if creds_path:
        print(f"🔑 Using service account credentials from: {creds_path}")
        return storage.Client.from_service_account_json(creds_path)
    
    print("ℹ️ Using Google Application Default Credentials (ADC)")
    return storage.Client()

def upload_to_gcs(file_path: Path, bucket_name: str = None) -> bool:
    """Uploads a portfolio file to Google Cloud Storage if a bucket is configured."""
    if not bucket_name:
        bucket_name = os.getenv("PORTFOLIO_GCS_BUCKET")
        
    if not bucket_name:
        print("⚠️ PORTFOLIO_GCS_BUCKET is not set. Skipping GCS upload.")
        return False
        
    if not file_path.exists():
        print(f"❌ Error: File {file_path} does not exist.")
        return False

    try:
        client = get_storage_client()
        bucket = client.bucket(bucket_name)
        
        # Decide prefix folder in GCS based on file extension
        prefix = "snapshots" if file_path.suffix == ".json" else "portfolios"
        destination_blob_name = f"{prefix}/{file_path.name}"
        
        blob = bucket.blob(destination_blob_name)
        
        print(f"☁️ Uploading {file_path.name} to gs://{bucket_name}/{destination_blob_name}...")
        blob.upload_from_filename(str(file_path))
        print(f"✅ Successfully uploaded to gs://{bucket_name}/{destination_blob_name}")
        return True
    except Exception as e:
        print(f"❌ Failed to upload {file_path.name} to GCS: {e}")
        return False
