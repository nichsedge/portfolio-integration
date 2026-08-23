# Sans Finance Client

Fetches the latest Sans Finance (Android app) SQLite database from Cloudflare R2 and
extracts non-investment accounts (bank cash, wallet cash, P2P lending) for the
portfolio-integration pipeline.

## Usage

```bash
uv run sansfinance-fetch
```

Output: `{YYYY-MM-DD}_raw_sansfinance.json` in the pipeline data directory.

## Credentials

Resolved from env (`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`,
optional `R2_BUCKET_NAME`) or falls back to the creds bundled with the APK at
`~/Projects/sansfinance/app/src/main/assets/r2_cred.json`. Falls back to
`wrangler r2 object get` when direct signed download is unavailable.

## Scope note

Only accounts unique to the APK are emitted. Portfolio holdings stored in the
APK originate from this same pipeline (KSEI / DeBank / Binance / Alchemy), so
they are deliberately excluded to avoid double-counting.
