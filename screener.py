"""
screener.py – Combined entry point for all AllIN Zerodha screening strategies.

Runs any combination of the available strategies and prints results.

Available strategies:
  all               – Run every strategy
  gainers-today     – Today's top % gainers
  gainers-weekly    – Past N-day top % gainers
  reversal          – Stocks reversing after a multi-day losing streak
  rsi-bounce        – RSI oversold bounce (RSI crossing back above threshold)
  volume-surge      – Volume surge on a positive-close day (accumulation)
  breakout-52w      – Price near or at 52-week high breakout
  golden-cross      – 20-day SMA crossing above 50-day SMA

Usage examples:
  python screener.py                          # Run all strategies
  python screener.py gainers-today reversal   # Run selected strategies
  python screener.py --top 10 all             # Top 10 results per strategy
  python screener.py reversal --min-loss-days 4 --confirm-volume
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

STRATEGIES = [
    "gainers-today",
    "gainers-weekly",
    "reversal",
    "rsi-bounce",
    "volume-surge",
    "breakout-52w",
    "golden-cross",
]


def _section(title: str) -> None:
    print(f"\n{'#'*70}")
    print(f"  {title}")
    print(f"{'#'*70}\n")


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
        description="AllIN – Zerodha-powered stock screener.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "strategies",
        nargs="*",
        default=["all"],
        choices=STRATEGIES + ["all"],
        metavar="STRATEGY",
        help=f"Strategies to run: {', '.join(STRATEGIES + ['all'])} (default: all)",
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

    print(f"\nAllIN Stock Screener  |  {date.today()}  |  Exchange: {args.exchange}")
    print(f"Strategies: {', '.join(args.strategies)}\n")

    try:
        run_strategies(args)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(0)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
