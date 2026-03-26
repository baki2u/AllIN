"""
screener.py – Combined entry point for all AllIN Zerodha screening strategies
              and popular investor account views.

Runs any combination of the available strategies and prints results.

Available strategies:
  all               – Run every screening strategy
  gainers-today     – Today's top % gainers
  gainers-weekly    – Past N-day top % gainers
  reversal          – Stocks reversing after a multi-day losing streak
  rsi-bounce        – RSI oversold bounce (RSI crossing back above threshold)
  volume-surge      – Volume surge on a positive-close day (accumulation)
  breakout-52w      – Price near or at 52-week high breakout
  golden-cross      – 20-day SMA crossing above 50-day SMA

Popular account views (run standalone or alongside strategies):
  portfolio         – Portfolio holdings with unrealised P&L
  positions         – Current open positions (intraday + overnight)
  orders            – Today's order book, tradebook, and GTT orders

Order management (delegates to place_order.py):
  place-order       – Place, modify, or cancel orders (run for full help)

Usage examples:
  python screener.py                          # Run all screening strategies
  python screener.py gainers-today reversal   # Run selected strategies
  python screener.py --top 10 all             # Top 10 results per strategy
  python screener.py reversal --min-loss-days 4 --confirm-volume
  python screener.py portfolio                # View portfolio holdings
  python screener.py positions orders         # View positions and orders
  python screener.py portfolio positions orders gainers-today  # Mix freely
  python screener.py place-order              # Show order placement help
"""

import argparse
import sys
from datetime import date

from tabulate import tabulate

import config
from gainers_today import get_gainers_today, print_gainers
from gainers_weekly import get_gainers_weekly, print_weekly_gainers
from reversal_screener import get_reversal_candidates, print_reversals
from strategies import (
    rsi_oversold_bounce,
    volume_surge_up,
    breakout_52w_high,
    sma_golden_cross,
)
from kite_client import get_kite_client
from portfolio import get_holdings, print_holdings
from positions import get_positions, print_positions
from orders import get_orders, print_orders, get_trades, print_trades, get_gtts, print_gtts
from place_order import market_status_message

STRATEGIES = [
    "gainers-today",
    "gainers-weekly",
    "reversal",
    "rsi-bounce",
    "volume-surge",
    "breakout-52w",
    "golden-cross",
]

ACCOUNT_VIEWS = [
    "portfolio",
    "positions",
    "orders",
]

ORDER_VIEWS = [
    "place-order",
]


def _section(title: str) -> None:
    print(f"\n{'#'*70}")
    print(f"  {title}")
    print(f"{'#'*70}\n")


def run_account_views(args: argparse.Namespace) -> None:
    """Run selected account-view commands (portfolio, positions, orders)."""
    views = set(args.commands)
    kite = get_kite_client()

    if "portfolio" in views:
        _section("PORTFOLIO HOLDINGS")
        df = get_holdings(kite)
        print_holdings(df)

    if "positions" in views:
        _section("OPEN POSITIONS")
        df = get_positions(kite)
        print_positions(df)

    if "orders" in views:
        _section("TODAY'S ORDERS & TRADES")
        df_orders = get_orders(kite)
        print_orders(df_orders)
        df_trades = get_trades(kite)
        print_trades(df_trades)
        _section("GTT ORDERS")
        df_gtts = get_gtts(kite)
        print_gtts(df_gtts)


def run_strategies(args: argparse.Namespace) -> None:
    run_all = "all" in args.strategies
    strategies = set(args.strategies)

    if run_all or "gainers-today" in strategies:
        _section("TODAY'S TOP GAINERS")
        df = get_gainers_today(
            top_n=args.top,
            min_price=args.min_price,
            min_volume=args.min_volume,
            exchange=args.exchange,
        )
        print_gainers(df)

    if run_all or "gainers-weekly" in strategies:
        _section(f"TOP {args.lookback}-DAY GAINERS")
        df = get_gainers_weekly(
            top_n=args.top,
            lookback_days=args.lookback,
            min_price=args.min_price,
            min_volume=args.min_volume,
            exchange=args.exchange,
        )
        print_weekly_gainers(df, args.lookback)

    if run_all or "reversal" in strategies:
        _section(f"REVERSAL AFTER ≥{args.min_loss_days} CONSECUTIVE LOSSES")
        df = get_reversal_candidates(
            min_loss_days=args.min_loss_days,
            lookback_days=args.reversal_lookback,
            confirm_volume=args.confirm_volume,
            confirm_rsi=args.confirm_rsi,
            top_n=args.top,
            min_price=args.min_price,
            min_volume=args.min_volume,
            exchange=args.exchange,
        )
        print_reversals(df, args.min_loss_days)

    if run_all or "rsi-bounce" in strategies:
        _section("RSI OVERSOLD BOUNCE")
        df = rsi_oversold_bounce(
            top_n=args.top,
            rsi_threshold=args.rsi_threshold,
            min_price=args.min_price,
            min_volume=args.min_volume,
            exchange=args.exchange,
        )
        if df.empty:
            print("No RSI oversold bounce candidates found.\n")
        else:
            print(tabulate(df, headers="keys", tablefmt="simple", showindex=True))
            print(f"\nTotal: {len(df)} stocks\n")

    if run_all or "volume-surge" in strategies:
        _section("VOLUME SURGE + POSITIVE CLOSE")
        df = volume_surge_up(
            top_n=args.top,
            surge_multiplier=args.vol_surge,
            min_price=args.min_price,
            min_volume=args.min_volume,
            exchange=args.exchange,
        )
        if df.empty:
            print("No volume surge candidates found.\n")
        else:
            print(tabulate(df, headers="keys", tablefmt="simple", showindex=True))
            print(f"\nTotal: {len(df)} stocks\n")

    if run_all or "breakout-52w" in strategies:
        _section("52-WEEK HIGH BREAKOUT")
        df = breakout_52w_high(
            top_n=args.top,
            proximity_pct=args.proximity_pct,
            min_price=args.min_price,
            min_volume=args.min_volume,
            exchange=args.exchange,
        )
        if df.empty:
            print("No 52-week high breakout candidates found.\n")
        else:
            print(tabulate(df, headers="keys", tablefmt="simple", showindex=True))
            print(f"\nTotal: {len(df)} stocks\n")

    if run_all or "golden-cross" in strategies:
        _section("SMA GOLDEN CROSS (20 > 50)")
        df = sma_golden_cross(
            top_n=args.top,
            min_price=args.min_price,
            min_volume=args.min_volume,
            exchange=args.exchange,
        )
        if df.empty:
            print("No golden cross candidates found.\n")
        else:
            print(tabulate(df, headers="keys", tablefmt="simple", showindex=True))
            print(f"\nTotal: {len(df)} stocks\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AllIN – Zerodha-powered stock screener and account viewer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    all_commands = STRATEGIES + ACCOUNT_VIEWS + ORDER_VIEWS + ["all"]
    parser.add_argument(
        "commands",
        nargs="*",
        default=["all"],
        choices=all_commands,
        metavar="COMMAND",
        help=(
            f"Strategies: {', '.join(STRATEGIES + ['all'])}  |  "
            f"Account views: {', '.join(ACCOUNT_VIEWS)}  |  "
            f"Orders: {', '.join(ORDER_VIEWS)}  (default: all strategies)"
        ),
    )

    # Common filters
    common = parser.add_argument_group("common filters")
    common.add_argument("--top", type=int, default=config.TOP_N, help="Top N results per strategy")
    common.add_argument("--min-price", type=float, default=config.MIN_PRICE, help="Min price filter (₹)")
    common.add_argument("--min-volume", type=int, default=config.MIN_VOLUME, help="Min volume filter")
    common.add_argument("--exchange", default=config.EXCHANGE, choices=["NSE", "BSE"])

    # Weekly gainers
    weekly = parser.add_argument_group("weekly gainers")
    weekly.add_argument("--lookback", type=int, default=config.WEEKLY_LOOKBACK_DAYS, help="Days to look back for weekly gainers")

    # Reversal
    rev = parser.add_argument_group("reversal")
    rev.add_argument("--min-loss-days", type=int, default=config.REVERSAL_MIN_LOSS_DAYS)
    rev.add_argument("--reversal-lookback", type=int, default=config.REVERSAL_LOOKBACK_DAYS)
    rev.add_argument("--confirm-volume", action="store_true")
    rev.add_argument("--confirm-rsi", action="store_true")

    # RSI bounce
    rsi_grp = parser.add_argument_group("rsi bounce")
    rsi_grp.add_argument("--rsi-threshold", type=float, default=config.RSI_OVERSOLD)

    # Volume surge
    vol_grp = parser.add_argument_group("volume surge")
    vol_grp.add_argument("--vol-surge", type=float, default=config.VOLUME_SURGE_MULTIPLIER)

    # 52w breakout
    brkout = parser.add_argument_group("52w breakout")
    brkout.add_argument("--proximity-pct", type=float, default=config.HIGH_52W_PROXIMITY_PCT)

    args = parser.parse_args()

    # Separate commands by category
    requested = set(args.commands)
    account_cmds = requested & set(ACCOUNT_VIEWS)
    order_cmds = requested & set(ORDER_VIEWS)
    strategy_cmds = requested - account_cmds - order_cmds  # may include 'all'

    print(f"\nAllIN  |  {date.today()}  |  Exchange: {args.exchange}")
    print(f"Commands: {', '.join(args.commands)}\n")

    try:
        # Run account views first if any were explicitly requested
        if account_cmds:
            args.commands = list(account_cmds)
            run_account_views(args)

        # Show order placement help if requested
        if order_cmds:
            _section("ORDER PLACEMENT")
            print(f"  Market status: {market_status_message()}\n")
            print("  Use place_order.py directly to place, modify, or cancel orders:")
            print("    python place_order.py buy RELIANCE 10")
            print("    python place_order.py buy INFY 10 --order-type LIMIT --price 1500")
            print("    python place_order.py sell TCS 5 --product CNC")
            print("    python place_order.py gtt buy RELIANCE 10 --trigger-price 2400 --price 2395")
            print("    python place_order.py modify ORDER_ID --price 1510")
            print("    python place_order.py cancel ORDER_ID")
            print("    python place_order.py --help   # Full documentation\n")

        # Run screening strategies (skip if only account/order views were requested)
        has_strategies = bool(strategy_cmds)
        if has_strategies:
            args.strategies = list(strategy_cmds)
            run_strategies(args)

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(0)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
