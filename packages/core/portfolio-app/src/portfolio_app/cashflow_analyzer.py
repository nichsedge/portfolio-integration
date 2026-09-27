"""
Cashflow & Spending Analyzer for Sans Finance SQLite Database
Integrates Android cashflow, bank accounts, and daily expenses into the AI portfolio engine.
"""

import os
import sqlite3
import pendulum
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    from transform_core import get_data_dir, get_exchange_rate
except ImportError:
    repo_root = Path(__file__).resolve().parents[4]
    import sys
    sys.path.append(str(repo_root / "packages/transform-core/src"))
    from transform_core import get_data_dir, get_exchange_rate


def get_gcs_storage_client():
    """Initializes Google Cloud Storage client using service account or ADC."""
    from google.cloud import storage
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path:
        projects_dir = Path(__file__).resolve().parents[5]
        candidate = projects_dir / "creds" / "gcp" / "SA_cred_general.json"
        if candidate.exists():
            creds_path = str(candidate)

    if creds_path and os.path.exists(creds_path):
        return storage.Client.from_service_account_json(creds_path)
    return storage.Client()


def pull_sans_finance_db_from_r2(target_path: Path) -> bool:
    """Pulls the latest Sans Finance SQLite snapshot from Cloudflare R2."""
    try:
        from sansfinance_client.fetcher import download_db
        target_path.parent.mkdir(parents=True, exist_ok=True)
        download_db(target_path)
        return target_path.exists() and target_path.stat().st_size > 0
    except Exception as e:
        print(f"⚠️ Warning: Could not pull Sans Finance DB from R2: {e}")
        return False


def pull_sans_finance_db_from_gcs(target_path: Path, bucket_name: Optional[str] = None) -> bool:
    """Pulls the latest Sans Finance SQLite snapshot from GCS."""
    if not bucket_name:
        bucket_name = os.getenv("PORTFOLIO_GCS_BUCKET") or os.getenv("GCS_BUCKET_NAME") or "ichsanul-portfolio-snapshots"
    
    blob_name = "db/sans_finance_latest.sqlite"
    try:
        client = get_gcs_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if not blob.exists():
            return False
        target_path.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(target_path))
        return True
    except Exception as e:
        print(f"⚠️ Warning: Could not pull Sans Finance DB from GCS: {e}")
        return False


def resolve_sans_finance_db(data_dir: Optional[Path] = None, auto_pull_gcs: bool = True) -> Optional[Path]:
    """Finds the Sans Finance SQLite database locally or pulls it from R2 / GCS."""
    if data_dir is None:
        data_dir = get_data_dir()

    # 1. Check direct env var
    env_path = os.getenv("SANS_FINANCE_DB_PATH")
    if env_path and Path(env_path).exists():
        return Path(env_path)

    # 2. Check local data directory candidates
    candidates = [
        data_dir / "sans_finance_latest.sqlite",
        data_dir / "sans_finance_db_snapshot.sqlite",
        Path(__file__).resolve().parents[5] / "sansfinance" / "sans_finance_latest.sqlite",
        Path(__file__).resolve().parents[5] / "sansfinance" / "sans_finance_db_snapshot.sqlite",
    ]
    for c in candidates:
        if c.exists():
            return c

    # 3. Pull from Cloud (R2 first, then GCS) if enabled
    if auto_pull_gcs:
        target_path = data_dir / "sans_finance_latest.sqlite"
        if pull_sans_finance_db_from_r2(target_path):
            return target_path
        if pull_sans_finance_db_from_gcs(target_path):
            return target_path

    return None


def get_live_accounts(db_path: Path, exchange_rate: float) -> Dict[str, Any]:
    """Reads live account balances (cash, checking, e-wallets)."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    accounts = []
    total_liquid_idr = 0.0
    total_liquid_usd = 0.0

    try:
        cursor.execute("SELECT id, name, type, currency, balance FROM accounts ORDER BY balance DESC")
        for row in cursor.fetchall():
            bal_cents = row["balance"] or 0
            bal = bal_cents / 100.0
            curr = (row["currency"] or "IDR").upper()
            acc_type = row["type"] or "Other"

            if curr == "IDR":
                val_idr = bal
                val_usd = bal / exchange_rate if exchange_rate > 0 else 0.0
            else:
                val_usd = bal
                val_idr = bal * exchange_rate

            is_liquid = acc_type.lower() not in {"investment", "credit"}
            if is_liquid:
                total_liquid_idr += val_idr
                total_liquid_usd += val_usd

            accounts.append({
                "id": row["id"],
                "name": row["name"],
                "type": acc_type,
                "currency": curr,
                "balance": bal,
                "value_idr": round(val_idr, 2),
                "value_usd": round(val_usd, 2),
                "is_liquid": is_liquid,
            })
    except Exception as e:
        print(f"⚠️ Error reading accounts: {e}")
    finally:
        conn.close()

    return {
        "accounts": accounts,
        "total_liquid_idr": round(total_liquid_idr, 2),
        "total_liquid_usd": round(total_liquid_usd, 2),
    }


def get_cashflow_metrics(db_path: Path, months: int = 3, exchange_rate: float = 16000.0) -> Dict[str, Any]:
    """Calculates income, monthly expenses, savings rate, burn rate, and top categories."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    now = pendulum.now()
    start_time_ms = int(now.subtract(months=months).start_of("month").timestamp() * 1000)

    monthly_stats: Dict[str, Dict[str, float]] = {}
    category_totals: Dict[str, float] = {}
    total_income_idr = 0.0
    total_expense_idr = 0.0

    try:
        # Load category lookup
        cat_map = {}
        try:
            cursor.execute("SELECT id, name FROM categories")
            for c in cursor.fetchall():
                cat_map[c["id"]] = c["name"]
        except Exception:
            pass

        # Query expenses table
        query = """
            SELECT date, amount, currency, type, category_id, title
            FROM expenses
            WHERE date >= ?
            ORDER BY date ASC
        """
        cursor.execute(query, (start_time_ms,))
        rows = cursor.fetchall()

        for row in rows:
            dt_ms = row["date"]
            tx_dt = pendulum.from_timestamp(dt_ms / 1000.0)
            month_key = tx_dt.format("YYYY-MM")
            if month_key not in monthly_stats:
                monthly_stats[month_key] = {"income": 0.0, "expense": 0.0, "net": 0.0}

            amt = (row["amount"] or 0) / 100.0
            curr = (row["currency"] or "IDR").upper()
            amt_idr = amt if curr == "IDR" else amt * exchange_rate
            tx_type = (row["type"] or "EXPENSE").upper()

            if tx_type == "INCOME":
                monthly_stats[month_key]["income"] += amt_idr
                total_income_idr += amt_idr
            elif tx_type == "EXPENSE":
                monthly_stats[month_key]["expense"] += amt_idr
                total_expense_idr += amt_idr

                cat_id = row["category_id"]
                cat_name = cat_map.get(cat_id, "Uncategorized")
                category_totals[cat_name] = category_totals.get(cat_name, 0.0) + amt_idr

        for m_key, m_val in monthly_stats.items():
            m_val["net"] = m_val["income"] - m_val["expense"]
            m_val["savings_rate_pct"] = round(
                ((m_val["income"] - m_val["expense"]) / m_val["income"] * 100) if m_val["income"] > 0 else 0.0,
                1
            )

    except Exception as e:
        print(f"⚠️ Error reading cashflow expenses: {e}")
    finally:
        conn.close()

    month_count = max(len(monthly_stats), 1)
    avg_monthly_burn_idr = total_expense_idr / month_count
    avg_monthly_income_idr = total_income_idr / month_count
    avg_monthly_savings_idr = avg_monthly_income_idr - avg_monthly_burn_idr
    overall_savings_rate = (
        (total_income_idr - total_expense_idr) / total_income_idr * 100
        if total_income_idr > 0 else 0.0
    )

    # Top spending categories
    top_categories = sorted(
        [
            {
                "category": k,
                "amount_idr": round(v, 2),
                "amount_usd": round(v / exchange_rate, 2),
                "pct": round(v / total_expense_idr * 100, 1) if total_expense_idr > 0 else 0.0
            }
            for k, v in category_totals.items()
        ],
        key=lambda x: x["amount_idr"],
        reverse=True
    )

    return {
        "analysis_period_months": months,
        "total_income_idr": round(total_income_idr, 2),
        "total_expense_idr": round(total_expense_idr, 2),
        "avg_monthly_income_idr": round(avg_monthly_income_idr, 2),
        "avg_monthly_income_usd": round(avg_monthly_income_idr / exchange_rate, 2),
        "avg_monthly_burn_idr": round(avg_monthly_burn_idr, 2),
        "avg_monthly_burn_usd": round(avg_monthly_burn_idr / exchange_rate, 2),
        "avg_monthly_savings_idr": round(avg_monthly_savings_idr, 2),
        "overall_savings_rate_pct": round(overall_savings_rate, 1),
        "monthly_history": [
            {
                "month": k,
                "income_idr": round(v["income"], 2),
                "expense_idr": round(v["expense"], 2),
                "net_idr": round(v["net"], 2),
                "savings_rate_pct": v.get("savings_rate_pct", 0.0),
            }
            for k, v in sorted(monthly_stats.items())
        ],
        "top_categories": top_categories[:8],
    }


def calculate_runway(liquid_assets_idr: float, monthly_burn_idr: float) -> Dict[str, Any]:
    """Calculates financial runway based on liquid reserves and average monthly burn rate."""
    if monthly_burn_idr <= 0:
        return {
            "runway_months": 999.0,
            "health": "Fortress",
            "description": "Zero or negligible monthly burn detected.",
        }

    runway_months = round(liquid_assets_idr / monthly_burn_idr, 1)

    if runway_months < 3.0:
        health = "Critical"
        desc = "Under 3 months of emergency runway. Prioritize liquid cash accumulation."
    elif runway_months < 6.0:
        health = "Moderate"
        desc = "Between 3-6 months runway. Acceptable standard emergency buffer."
    elif runway_months < 12.0:
        health = "Strong"
        desc = "Between 6-12 months runway. Strong safety buffer with high resilience."
    else:
        health = "Fortress"
        desc = "Over 12 months runway. Exceptional financial security."

    return {
        "runway_months": runway_months,
        "health": health,
        "description": desc,
    }


def reconstruct_historical_net_worth(db_path: Path, snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Reconstructs historical cash balances and True Net Worth for each snapshot date
    by walking backward through the transaction ledger.
    """
    if not db_path.exists() or not snapshots:
        return []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # 1. Get current non-investment cash balances (in cents)
        cursor.execute("""
            SELECT a.id, a.name, a.type, a.balance 
            FROM accounts a
            JOIN account_types t ON a.type = t.name
            WHERE t.isLiability = 0 AND a.type != 'Investment'
        """)
        current_accounts = {row["id"]: row["balance"] or 0 for row in cursor.fetchall()}

        # 2. Get all transactions sorted by date
        cursor.execute("""
            SELECT id, account_id, to_account_id, amount, type, date 
            FROM expenses 
            ORDER BY date ASC
        """)
        transactions = cursor.fetchall()

        results = []
        for s in snapshots:
            d_str = s.get("metadata", {}).get("date") or s.get("date")
            if not d_str:
                continue

            dt = pendulum.parse(d_str).end_of("day")
            ts_ms = int(dt.timestamp() * 1000)

            balances_at_ts = dict(current_accounts)
            for tx in transactions:
                tx_date = tx["date"]
                if tx_date > ts_ms:
                    tx_type = (tx["type"] or "EXPENSE").upper()
                    amt = tx["amount"] or 0
                    acc_from = tx["account_id"]
                    acc_to = tx["to_account_id"]

                    if tx_type == "EXPENSE":
                        if acc_from in balances_at_ts:
                            balances_at_ts[acc_from] += amt
                    elif tx_type == "INCOME":
                        if acc_from in balances_at_ts:
                            balances_at_ts[acc_from] -= amt
                    elif tx_type == "TRANSFER":
                        if acc_from in balances_at_ts:
                            balances_at_ts[acc_from] += amt
                        if acc_to and acc_to in balances_at_ts:
                            balances_at_ts[acc_to] -= amt

            total_cash_idr = sum(balances_at_ts.values()) / 100.0
            port_val = s.get("totals", {}).get("net_worth_idr") or s.get("total_value_idr") or 0.0
            exchange_rate = s.get("metadata", {}).get("exchange_rate") or 16000.0

            true_net_worth_idr = port_val + total_cash_idr
            true_net_worth_usd = true_net_worth_idr / exchange_rate if exchange_rate > 0 else 0.0

            results.append({
                "date": d_str,
                "portfolio_value_idr": round(port_val, 2),
                "reconstructed_cash_idr": round(total_cash_idr, 2),
                "true_net_worth_idr": round(true_net_worth_idr, 2),
                "true_net_worth_usd": round(true_net_worth_usd, 2),
                "exchange_rate": exchange_rate,
            })

        return results
    except Exception as e:
        print(f"⚠️ Error reconstructing historical net worth: {e}")
        return []
    finally:
        conn.close()

