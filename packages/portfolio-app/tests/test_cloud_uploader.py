"""Unit tests for cloud_uploader."""
from pathlib import Path
from portfolio_app.cloud_uploader import get_prefix_and_latest_name, load_r2_credentials


def test_get_prefix_and_latest_name():
    prefix, latest = get_prefix_and_latest_name(Path("2026-08-24_snapshot.json"))
    assert prefix == "snapshots"
    assert latest == "latest.json"

    prefix, latest = get_prefix_and_latest_name(Path("2026-08-24_ai_state.json"))
    assert prefix == "ai"
    assert latest == "latest_state.json"

    prefix, latest = get_prefix_and_latest_name(Path("2026-08-24_ai_digest.md"))
    assert prefix == "ai"
    assert latest == "latest_digest.md"

    prefix, latest = get_prefix_and_latest_name(Path("2026-08-24_curated_ksei.json"))
    assert prefix == "snapshots"
    assert latest is None


def test_load_r2_credentials(monkeypatch):
    monkeypatch.setenv("R2_ACCOUNT_ID", "test_acc")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "test_key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "test_sec")
    monkeypatch.setenv("R2_BUCKET_NAME", "test_bucket")

    acc, key, sec, bucket = load_r2_credentials()
    assert acc == "test_acc"
    assert key == "test_key"
    assert sec == "test_sec"
    assert bucket == "test_bucket"
