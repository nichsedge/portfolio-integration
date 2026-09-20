"""
CLI tool for DefiLlama free API endpoints.
Provides quick terminal inspection for prices, yields, protocols, stablecoins, and fees.
"""

import argparse
import json
import sys

from defillama_client.client import DefiLlamaClient


def cmd_prices(client: DefiLlamaClient, args: argparse.Namespace) -> None:
    data = client.get_token_prices(args.coins)
    if args.json:
        print(json.dumps(data, indent=2))
        return

    if not data:
        print("No price data returned for query.")
        return

    print(f"\n{'Token':<32} {'Symbol':<8} {'Price (USD)':<14} {'Timestamp'}")
    print("-" * 75)
    for coin_id, info in data.items():
        price = info.get("price", 0.0)
        sym = info.get("symbol", "N/A")
        ts = info.get("timestamp", "")
        print(f"{coin_id:<32} {sym:<8} ${price:<13,.4f} {ts}")


def cmd_yields(client: DefiLlamaClient, args: argparse.Namespace) -> None:
    pools = client.get_pools(
        min_tvl=args.min_tvl,
        chain=args.chain,
        project=args.project,
        stablecoin_only=args.stablecoin,
        limit=args.limit,
    )

    if args.json:
        print(json.dumps(pools, indent=2))
        return

    if not pools:
        print("No pools matching criteria found.")
        return

    print(
        f"\n{'Project':<16} {'Symbol':<14} {'Chain':<12} {'TVL (USD)':<14} {'APY (%)':<10} {'Stable'}"
    )
    print("-" * 75)
    for p in pools:
        tvl = f"${p['tvl_usd']:,.0f}"
        apy = f"{p['apy']:.2f}%"
        stable = "YES" if p["stablecoin"] else "NO"
        print(
            f"{p['project']:<16} {p['symbol']:<14} {p['chain']:<12} {tvl:<14} {apy:<10} {stable}"
        )


def cmd_protocol(client: DefiLlamaClient, args: argparse.Namespace) -> None:
    data = client.get_protocol(args.slug)
    if args.json:
        print(json.dumps(data, indent=2))
        return

    print(f"\n=== Protocol: {data.get('name')} ({data.get('symbol', 'N/A')}) ===")
    print(f"Slug:        {data.get('slug')}")
    print(f"Category:    {data.get('category')}")
    print(f"Website:     {data.get('url')}")
    print(f"Audits:      {data.get('audits')} audit(s)")
    tvl = data.get("tvl_usd")
    if tvl is not None:
        print(f"Total TVL:   ${tvl:,.2f}")

    chain_tvls = data.get("chain_tvls", {})
    if chain_tvls:
        print("\nTop Chains by TVL:")
        sorted_chains = sorted(chain_tvls.items(), key=lambda x: x[1], reverse=True)[:5]
        for ch, val in sorted_chains:
            print(f"  - {ch:<14}: ${val:,.2f}")


def cmd_stables(client: DefiLlamaClient, args: argparse.Namespace) -> None:
    stables = client.get_stablecoins(limit=args.top)
    if args.json:
        print(json.dumps(stables, indent=2))
        return

    print(
        f"\n{'Name':<18} {'Symbol':<8} {'Market Cap (USD)':<18} {'1d (%)':<8} {'7d (%)':<8} {'Peg Type'}"
    )
    print("-" * 75)
    for s in stables:
        mcap = f"${s['mcap_usd']:,.0f}"
        c1d = f"{s['change_1d_pct']:+.2f}%"
        c7d = f"{s['change_7d_pct']:+.2f}%"
        print(
            f"{s['name']:<18} {s['symbol']:<8} {mcap:<18} {c1d:<8} {c7d:<8} {s['peg_mechanism']}"
        )


def cmd_fees(client: DefiLlamaClient, args: argparse.Namespace) -> None:
    fees = client.get_protocol_fees(limit=args.top)
    if args.json:
        print(json.dumps(fees, indent=2))
        return

    print(
        f"\n{'Name':<20} {'Category':<16} {'24h Fees (USD)':<16} {'Est Annual Fees':<16} {'24h Revenue'}"
    )
    print("-" * 85)
    for f in fees:
        f24 = f"${f['fees_24h_usd']:,.0f}"
        fa = f"${f['annual_fees_usd']:,.0f}"
        r24 = f"${f['revenue_24h_usd']:,.0f}"
        print(f"{f['name']:<20} {f['category']:<16} {f24:<16} {fa:<16} {r24}")


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="llama-fetch",
        description="DefiLlama Free API CLI (Prices, Yields, Protocols, Stablecoins, Fees)",
    )
    parser.add_argument("--json", action="store_true", help="Output raw JSON")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # prices
    p_prices = subparsers.add_parser("prices", help="Get token prices by address or coingecko ID")
    p_prices.add_argument("coins", nargs="+", help="Tokens (e.g. coingecko:ethereum ethereum:0x...)")

    # yields
    p_yields = subparsers.add_parser("yields", help="Screen DeFi yield pools")
    p_yields.add_argument("--min-tvl", type=float, default=1_000_000, help="Min pool TVL in USD")
    p_yields.add_argument("--chain", type=str, help="Filter by chain (e.g. arbitrum, ethereum)")
    p_yields.add_argument("--project", type=str, help="Filter by protocol/project")
    p_yields.add_argument("--stablecoin", action="store_true", help="Only stablecoin pools")
    p_yields.add_argument("--limit", type=int, default=20, help="Max results to display")

    # protocol
    p_proto = subparsers.add_parser("protocol", help="Get protocol TVL & details")
    p_proto.add_argument("slug", help="Protocol slug (e.g. aave-v3, uniswap)")

    # stables
    p_stables = subparsers.add_parser("stables", help="List stablecoins by market cap")
    p_stables.add_argument("--top", type=int, default=15, help="Number of stablecoins to list")

    # fees
    p_fees = subparsers.add_parser("fees", help="List protocols by fees and revenue")
    p_fees.add_argument("--top", type=int, default=15, help="Number of protocols to list")

    args = parser.parse_args(argv)

    with DefiLlamaClient() as client:
        if args.command == "prices":
            cmd_prices(client, args)
        elif args.command == "yields":
            cmd_yields(client, args)
        elif args.command == "protocol":
            cmd_protocol(client, args)
        elif args.command == "stables":
            cmd_stables(client, args)
        elif args.command == "fees":
            cmd_fees(client, args)


if __name__ == "__main__":
    main()
