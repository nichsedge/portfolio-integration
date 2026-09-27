"""
Orderbook Fetcher & Liquidity Analyzer for Binance and Tokocrypto.

Provides real-time orderbook depth extraction, bid/ask wall detection,
slippage simulation for DCA budgets, and optimal limit order price recommendations.
"""

import argparse
import json
import logging
import socket
import sys
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def patch_dns_with_doh() -> None:
    """
    Patch socket.getaddrinfo to resolve blocked exchange domains (Binance, etc.)
    via Cloudflare DNS-over-HTTPS (DoH) for Indonesian ISP compatibility.
    """
    original_getaddrinfo = socket.getaddrinfo

    def doh_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if isinstance(host, str) and (
            host == "binance.com"
            or host.endswith(".binance.com")
            or host == "binance.vision"
            or host.endswith(".binance.vision")
            or host == "tokocrypto.com"
            or host.endswith(".tokocrypto.com")
        ):
            try:
                url = f"https://cloudflare-dns.com/dns-query?name={urllib.parse.quote(host)}&type=A"
                req = urllib.request.Request(url, headers={"Accept": "application/dns-json", "User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=5) as response:
                    data = json.loads(response.read().decode())
                    ips = [ans["data"] for ans in data.get("Answer", []) if ans.get("type") == 1]
                    if ips:
                        return original_getaddrinfo(ips[0], port, family, type, proto, flags)
            except Exception:
                pass
        return original_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = doh_getaddrinfo


# Activate DNS patch on import
try:
    patch_dns_with_doh()
except Exception:
    pass


BINANCE_ENDPOINTS = [
    "https://data-api.binance.vision/api/v3",
    "https://api1.binance.com/api/v3",
    "https://api2.binance.com/api/v3",
    "https://api3.binance.com/api/v3",
    "https://api.binance.me/api/v3",
    "https://api.binance.com/api/v3",
]

TOKOCRYPTO_BASE_URL = "https://www.tokocrypto.com/open/v1"


def normalize_symbol(symbol: str) -> Tuple[str, str, str, str]:
    """
    Normalize symbol variations (e.g. PAXG/USDT, PAXGUSDT, paxg-usdt)
    Returns: (base, quote, binance_symbol, tokocrypto_symbol)
    """
    clean = symbol.upper().replace("-", "/").replace("_", "/")
    if "/" in clean:
        parts = clean.split("/")
        base, quote = parts[0], parts[1]
    else:
        # Common quote currencies
        for q in ["USDT", "USDC", "BUSD", "BIDR", "IDR", "BTC", "ETH"]:
            if clean.endswith(q) and len(clean) > len(q):
                base = clean[:-len(q)]
                quote = q
                break
        else:
            base = clean
            quote = "USDT"

    binance_symbol = f"{base}{quote}"
    tokocrypto_symbol = f"{base}_{quote}"
    return base, quote, binance_symbol, tokocrypto_symbol


def fetch_orderbook(symbol: str = "PAXG/USDT", exchange: str = "tokocrypto", limit: int = 100) -> Dict[str, Any]:
    """
    Fetch live orderbook depth from Tokocrypto or Binance with automatic fallback.
    Returns standardized dict:
      {
        "exchange": str,
        "symbol": str,
        "base": str,
        "quote": str,
        "bids": [[price, qty], ...], # descending
        "asks": [[price, qty], ...]  # ascending
      }
    """
    base, quote, binance_sym, toko_sym = normalize_symbol(symbol)
    exchange = exchange.lower().strip()

    if exchange == "tokocrypto":
        # Tokocrypto supports limits: 5, 10, 20, 50, 100
        toko_limit = min(limit, 100)
        url = f"{TOKOCRYPTO_BASE_URL}/market/depth?symbol={toko_sym}&limit={toko_limit}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=7) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
                if raw.get("code") == 0 and "data" in raw:
                    data = raw["data"]
                    bids = [[float(p), float(q)] for p, q in data.get("bids", [])]
                    asks = [[float(p), float(q)] for p, q in data.get("asks", [])]
                    bids.sort(key=lambda x: x[0], reverse=True)
                    asks.sort(key=lambda x: x[0])
                    return {
                        "exchange": "tokocrypto",
                        "symbol": f"{base}/{quote}",
                        "base": base,
                        "quote": quote,
                        "bids": bids,
                        "asks": asks,
                    }
                elif raw.get("code") == 2802:
                    raise ValueError(f"Trading pair {toko_sym} does not exist on Tokocrypto.")
        except Exception as e:
            if "does not exist" in str(e):
                raise
            logger.warning(f"Tokocrypto fetch failed ({e}), falling back to Binance mirror...")
            # Fallback to Binance since Tokocrypto shares Binance Cloud liquidity
            pass

    # Binance fetch with multiple redundant endpoints
    errors = []
    for base_url in BINANCE_ENDPOINTS:
        url = f"{base_url}/depth?symbol={binance_sym}&limit={limit}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if "bids" in data and "asks" in data:
                    bids = [[float(p), float(q)] for p, q in data.get("bids", [])]
                    asks = [[float(p), float(q)] for p, q in data.get("asks", [])]
                    bids.sort(key=lambda x: x[0], reverse=True)
                    asks.sort(key=lambda x: x[0])
                    return {
                        "exchange": "binance",
                        "symbol": f"{base}/{quote}",
                        "base": base,
                        "quote": quote,
                        "bids": bids,
                        "asks": asks,
                    }
        except Exception as e:
            errors.append(f"{base_url}: {e}")

    raise ConnectionError(f"Failed to fetch orderbook for {symbol} from all endpoints. Errors: {errors}")


def fetch_24h_ticker(symbol: str = "PAXG/USDT") -> Dict[str, Any]:
    """Fetch 24-hour ticker statistics (last price, high, low, volume)."""
    base, quote, binance_sym, _ = normalize_symbol(symbol)
    for base_url in BINANCE_ENDPOINTS:
        url = f"{base_url}/ticker/24hr?symbol={binance_sym}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                d = json.loads(resp.read().decode("utf-8"))
                return {
                    "last_price": float(d.get("lastPrice", 0)),
                    "high_price_24h": float(d.get("highPrice", 0)),
                    "low_price_24h": float(d.get("lowPrice", 0)),
                    "price_change_pct": float(d.get("priceChangePercent", 0)),
                    "volume_24h": float(d.get("volume", 0)),
                    "quote_volume_24h": float(d.get("quoteVolume", 0)),
                }
        except Exception:
            continue
    return {}


def simulate_market_buy(asks: List[List[float]], budget_usd: float) -> Dict[str, Any]:
    """
    Simulate executing a market buy order for a specific budget in quote currency (USD).
    Computes fill quantity, weighted average price, and slippage.
    """
    if not asks:
        return {"error": "Empty asks in orderbook"}

    remaining_usd = budget_usd
    total_qty = 0.0
    spent_usd = 0.0
    best_ask = asks[0][0]

    for price, qty in asks:
        level_value = price * qty
        if remaining_usd <= level_value:
            fill_qty = remaining_usd / price
            total_qty += fill_qty
            spent_usd += remaining_usd
            remaining_usd = 0.0
            break
        else:
            total_qty += qty
            spent_usd += level_value
            remaining_usd -= level_value

    if total_qty == 0:
        return {"error": "Insufficient liquidity to simulate market buy"}

    avg_fill_price = spent_usd / total_qty
    slippage_usd = avg_fill_price - best_ask
    slippage_pct = (slippage_usd / best_ask) * 100.0 if best_ask > 0 else 0.0

    return {
        "budget_usd": budget_usd,
        "spent_usd": round(spent_usd, 4),
        "total_qty": round(total_qty, 6),
        "avg_fill_price": round(avg_fill_price, 4),
        "best_ask": best_ask,
        "slippage_usd": round(slippage_usd, 4),
        "slippage_pct": round(slippage_pct, 4),
        "estimated_taker_fee_usd": round(budget_usd * 0.001, 4),  # Standard 0.1% fee
    }


def find_bid_walls(bids: List[List[float]], top_n: int = 5) -> List[Dict[str, Any]]:
    """
    Detect significant bid walls (liquidity clusters) in the orderbook.
    """
    if not bids:
        return []

    best_bid = bids[0][0]
    total_vol = sum(q for _, q in bids)
    avg_vol_per_level = total_vol / len(bids) if bids else 1.0

    # Cluster bids by rounding or detecting spikes
    walls = []
    cum_vol = 0.0
    cum_val = 0.0

    for price, qty in bids:
        val = price * qty
        cum_vol += qty
        cum_val += val
        distance_pct = ((best_bid - price) / best_bid) * 100.0

        # Mark as wall if volume is significantly higher than average level
        is_wall = qty >= (avg_vol_per_level * 2.0) or val >= 25_000.0

        walls.append({
            "price": price,
            "qty": round(qty, 4),
            "value_usd": round(val, 2),
            "distance_pct": round(distance_pct, 2),
            "cum_qty": round(cum_vol, 4),
            "cum_val_usd": round(cum_val, 2),
            "is_wall": is_wall,
        })

    # Return top walls sorted by value
    only_walls = [w for w in walls if w["is_wall"]]
    only_walls.sort(key=lambda x: x["value_usd"], reverse=True)
    return only_walls[:top_n]


def analyze_orderbook(
    orderbook: Dict[str, Any],
    budget_usd: float = 50.0,
    ticker: Optional[Dict[str, Any]] = None,
    usd_idr_rate: float = 17915.0,
) -> Dict[str, Any]:
    """
    Comprehensive quantitative orderbook analysis for trading and DCA decisions.
    """
    bids = orderbook.get("bids", [])
    asks = orderbook.get("asks", [])

    if not bids or not asks:
        return {"error": "Incomplete orderbook data"}

    best_bid = bids[0][0]
    best_ask = asks[0][0]
    mid_price = (best_bid + best_ask) / 2.0
    spread_usd = best_ask - best_bid
    spread_pct = (spread_usd / mid_price) * 100.0

    # Simulation for user's budget
    sim = simulate_market_buy(asks, budget_usd)

    # Liquidity depth brackets
    depth_brackets = {}
    for pct in [0.2, 0.5, 1.0, 2.0, 3.0, 5.0]:
        target_price = best_bid * (1 - pct / 100.0)
        bracket_vol = sum(q for p, q in bids if p >= target_price)
        bracket_val = sum(p * q for p, q in bids if p >= target_price)
        depth_brackets[f"-{pct}%"] = {
            "price_threshold": round(target_price, 2),
            "cum_qty": round(bracket_vol, 4),
            "cum_usd": round(bracket_val, 2),
        }

    # Detect major bid walls
    walls = find_bid_walls(bids, top_n=5)

    # Tactical limit order recommendations
    # Tier 1 (Aggressive / Quick Maker Fill): Queue right at or 1 cent above top bid wall or best bid
    tier1_price = round(best_bid + 0.01 if (best_ask - best_bid) > 0.05 else best_bid, 2)

    # Tier 2 (Micro-Dip / Behind Primary Bid Wall): Look for first significant wall in top 1%
    tier2_price = round(best_bid * 0.992, 2)  # default -0.8%
    for w in walls:
        if 0.2 <= w["distance_pct"] <= 1.5:
            # Queue slightly in front of the wall to get filled before it gets swept
            tier2_price = round(w["price"] + 0.01, 2)
            break

    # Tier 3 (Swing / Deep Liquidity Pool): Major support wall around 2-4% dip
    tier3_price = round(best_bid * 0.975, 2)  # default -2.5%
    for w in walls:
        if 1.5 < w["distance_pct"] <= 4.0:
            tier3_price = round(w["price"] + 0.01, 2)
            break

    # DCA verdict for small budget
    slippage_pct = sim.get("slippage_pct", 0.0)
    can_market_buy = slippage_pct < 0.05 and spread_pct < 0.05

    dca_verdict = {
        "budget_usd": budget_usd,
        "budget_idr": round(budget_usd * usd_idr_rate),
        "slippage_pct": slippage_pct,
        "spread_pct": round(spread_pct, 4),
        "market_buy_recommended": can_market_buy,
        "verdict_reason": (
            f"Untuk modal ${budget_usd:.0f}, slippage market buy sangat tipis ({slippage_pct:.4f}%), "
            f"hanya berbeda sekitar ${(budget_usd * slippage_pct / 100):.3f} (beberapa sen). "
            f"Market Buy langsung AMAN dieksekusi tanpa takut boncos. "
            f"Namun jika ingin hemat taker fee atau mengincar wick drop, gunakan Limit Order di Tier 1 atau Tier 2."
        ) if can_market_buy else (
            f"Spread atau slippage agak lebar ({slippage_pct:.3f}%). Sangat disarankan pasang Limit Order."
        )
    }

    return {
        "exchange": orderbook.get("exchange"),
        "symbol": orderbook.get("symbol"),
        "timestamp_utc": pendulum_now_iso(),
        "usd_idr_rate": usd_idr_rate,
        "pricing": {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": round(mid_price, 2),
            "spread_usd": round(spread_usd, 4),
            "spread_pct": round(spread_pct, 4),
            "price_idr_per_gram": round((mid_price * usd_idr_rate) / 31.1035, 2),
        },
        "ticker_24h": ticker or {},
        "simulation_market_buy": sim,
        "bid_walls": walls,
        "depth_brackets": depth_brackets,
        "recommended_limit_orders": [
            {
                "tier": "Tier 1: Quick Maker (Hemat Fee / Frontrun)",
                "price_usd": tier1_price,
                "price_idr_per_gram": round((tier1_price * usd_idr_rate) / 31.1035),
                "discount_pct": round(((mid_price - tier1_price) / mid_price) * 100.0, 2),
                "fill_probability": "Sangat Tinggi (Menit - Jam)",
                "strategy": "Pasang limit bid tepat di atas atau setara best bid untuk menjadi maker (fee lebih murah) tanpa menunggu lama.",
            },
            {
                "tier": "Tier 2: Micro Dip (Antre di Support Wall 1)",
                "price_usd": tier2_price,
                "price_idr_per_gram": round((tier2_price * usd_idr_rate) / 31.1035),
                "discount_pct": round(((mid_price - tier2_price) / mid_price) * 100.0, 2),
                "fill_probability": "Sedang (12 - 24 Jam)",
                "strategy": "Antre di depan tembok beli (bid wall) pertama untuk menangkap wick koreksi harian.",
            },
            {
                "tier": "Tier 3: Swing Support (Diskon Koreksi / Deep Bid Wall)",
                "price_usd": tier3_price,
                "price_idr_per_gram": round((tier3_price * usd_idr_rate) / 31.1035),
                "discount_pct": round(((mid_price - tier3_price) / mid_price) * 100.0, 2),
                "fill_probability": "Rendah - Sedang (Butuh Volatilitas Tinggi)",
                "strategy": "Antre di zona diskon 2% - 3.5% untuk menangkap flash dump atau koreksi sehat pasar emas.",
            },
        ],
        "dca_verdict": dca_verdict,
    }


def pendulum_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def render_terminal_analysis(result: Dict[str, Any]) -> None:
    """Format and print beautiful quantitative analysis in terminal."""
    if "error" in result:
        print(f"\n❌ Error: {result['error']}\n")
        return

    p = result["pricing"]
    sim = result["simulation_market_buy"]
    verdict = result["dca_verdict"]
    ticker = result.get("ticker_24h", {})
    walls = result.get("bid_walls", [])
    tiers = result.get("recommended_limit_orders", [])

    print("\n" + "=" * 76)
    print(f"  📊 ORDERBOOK LIQUIDITY & ENTRY ANALYSIS: {result['symbol']} ({result['exchange'].upper()})")
    print("=" * 76)

    print(f"\n[1] TOP OF BOOK & SPREAD")
    print(f"  • Best Bid : ${p['best_bid']:,.2f}")
    print(f"  • Best Ask : ${p['best_ask']:,.2f}")
    print(f"  • Mid Price: ${p['mid_price']:,.2f}  (~Rp {p['price_idr_per_gram']:,.0f} / gram emas)")
    print(f"  • Spread   : ${p['spread_usd']:,.2f} ({p['spread_pct']:.4f}%) -> {'SANGAT KETAT (Liquid)' if p['spread_pct'] < 0.05 else 'CUKUP KETAT'}")

    if ticker:
        print(f"\n[2] 24H MARKET RANGE")
        print(f"  • High 24h : ${ticker.get('high_price_24h', 0):,.2f}")
        print(f"  • Low 24h  : ${ticker.get('low_price_24h', 0):,.2f}")
        print(f"  • Change   : {ticker.get('price_change_pct', 0):+.2f}%")
        print(f"  • 24h Vol  : ${ticker.get('quote_volume_24h', 0):,.0f} USD")

    print(f"\n[3] SIMULASI DCA ${verdict['budget_usd']:.0f} (~Rp {verdict['budget_idr']:,})")
    print(f"  • Estimasi Token Diperoleh: {sim.get('total_qty', 0):.6f} {result['symbol'].split('/')[0]}")
    print(f"  • Harga Rata-rata Beli    : ${sim.get('avg_fill_price', 0):,.2f}")
    print(f"  • Slippage vs Best Ask    : ${sim.get('slippage_usd', 0):.4f} ({sim.get('slippage_pct', 0):.4f}%)")
    print(f"  • Estimasi Biaya Fee (0.1%): ${sim.get('estimated_taker_fee_usd', 0):.4f}")
    print(f"  • STATUS EKSEKUSI         : {'✅ MARKET BUY AMAN' if verdict['market_buy_recommended'] else '⚠️ SARAN LIMIT ORDER'}")
    print(f"    -> {verdict['verdict_reason']}")

    if walls:
        print(f"\n[4] DETEKSI BID WALLS UTAMA (TEMBOK BELI / SUPPORT LOKAL)")
        print(f"  {'Harga (USD)':<14} {'Jarak (%)':<11} {'Ukuran (USD)':<15} {'Kumulatif (USD)':<16}")
        print("  " + "-" * 56)
        for w in walls:
            print(f"  ${w['price']:<13,.2f} -{w['distance_pct']:<9.2f}% ${w['value_usd']:<14,.0f} ${w['cum_val_usd']:<15,.0f}")

    print(f"\n[5] 🎯 REKOMENDASI ANTREAN LIMIT ORDER (HARGA MASUK)")
    for t in tiers:
        print(f"\n  ▶ {t['tier']}")
        print(f"    • Harga Limit : ${t['price_usd']:,.2f}  (Rp {t['price_idr_per_gram']:,} / gram)")
        print(f"    • Diskon      : -{t['discount_pct']:.2f}% dari harga saat ini")
        print(f"    • Probabilitas: {t['fill_probability']}")
        print(f"    • Taktik      : {t['strategy']}")

    print("\n" + "=" * 76 + "\n")


def main() -> None:
    """CLI Entrypoint for orderbook liquidity analysis."""
    parser = argparse.ArgumentParser(description="Analyze Orderbook Depth, Slippage, and Entry Tiers")
    parser.add_argument("--symbol", default="PAXG/USDT", help="Trading pair (default: PAXG/USDT)")
    parser.add_argument("--exchange", default="tokocrypto", choices=["tokocrypto", "binance"], help="Exchange (tokocrypto or binance)")
    parser.add_argument("--budget", type=float, default=50.0, help="DCA purchase budget in USD (default: 50.0)")
    parser.add_argument("--limit", type=int, default=100, help="Orderbook depth limit (default: 100)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of formatted text")
    args = parser.parse_args()

    try:
        orderbook = fetch_orderbook(symbol=args.symbol, exchange=args.exchange, limit=args.limit)
        ticker = fetch_24h_ticker(symbol=args.symbol)
        analysis = analyze_orderbook(orderbook, budget_usd=args.budget, ticker=ticker)

        if args.json:
            print(json.dumps(analysis, indent=2))
        else:
            render_terminal_analysis(analysis)
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}, indent=2))
        else:
            print(f"\n❌ Error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
