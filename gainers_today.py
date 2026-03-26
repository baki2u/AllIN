"""
gainers_today.py – Screen for today's top percentage gainers on NSE/BSE.

Strategy:
  Fetch live quotes for all NSE EQ instruments and rank by intraday
  percentage change (last_price vs previous close).

Usage:
  python gainers_today.py
  python gainers_today.py --top 30 --min-price 50 --min-volume 500000

Output:
  Table of top gainers sorted by % change (descending), with columns:
  Symbol | Name | Prev Close | LTP | Change % | Volume | Turnover (Cr)
"""

import argparse
import sys
from datetime import date

import pandas as pd
from tabulate import tabulate

import config
from kite_client import get_kite_client
from data_fetcher import get_instruments, get_quotes


def get_gainers_today(
    top_n: int = config.TOP_N,
    min_price: float = config.MIN_PRICE,
    min_volume: int = config.MIN_VOLUME,
    exchange: str = config.EXCHANGE,
) -> pd.DataFrame:
    """
    Fetch all NSE equity quotes and return the top *top_n* gainers for today.

    Args:
        top_n:      Number of top gainers to return.
        min_price:  Minimum LTP filter (₹).
        min_volume: Minimum traded volume filter.
        exchange:   Exchange ('NSE' or 'BSE').

    Returns:
        DataFrame with top gainers, sorted by change_pct descending.
    """
    kite = get_kite_client()

    print(f"[{date.today()}] Fetching instruments from {exchange}...")
    instruments_df = get_instruments(kite, exchange)
    symbols = instruments_df["tradingsymbol"].tolist()
    names = dict(zip(instruments_df["tradingsymbol"], instruments_df["name"]))

    print(f"  Total equity instruments: {len(symbols)}")
    print("  Fetching live quotes (this may take a moment)...")

    quotes = get_quotes(kite, symbols, exchange)

    rows = []
    for key, q in quotes.items():
        symbol = key.split(":")[-1]
        ohlc = q.get("ohlc", {})
        prev_close = ohlc.get("close", 0)
        ltp = q.get("last_price", 0)
        volume = q.get("volume", 0)

        if prev_close <= 0 or ltp <= 0:
            continue
        if ltp < min_price:
            continue
        if volume < min_volume:
            continue

        change_pct = ((ltp - prev_close) / prev_close) * 100
        turnover_cr = (ltp * volume) / 1e7

        rows.append(
            {
                "symbol": symbol,
                "name": names.get(symbol, ""),
                "prev_close": round(prev_close, 2),
                "ltp": round(ltp, 2),
                "change_pct": round(change_pct, 2),
                "volume": int(volume),
                "turnover_cr": round(turnover_cr, 2),
            }
        )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df[df["change_pct"] > 0]  # Gainers only
    df = df.sort_values("change_pct", ascending=False).head(top_n)
    df.reset_index(drop=True, inplace=True)
    return df


def print_gainers(df: pd.DataFrame) -> None:
    """Pretty-print the gainers table to stdout."""
    if df.empty:
        print("No gainers found matching the criteria.")
        return

    display = df.rename(
        columns={
            "symbol": "Symbol",
            "name": "Name",
            "prev_close": "Prev Close (₹)",
            "ltp": "LTP (₹)",
            "change_pct": "Change %",
            "volume": "Volume",
            "turnover_cr": "Turnover (Cr ₹)",
        }
    )
    print(f"\n{'='*70}")
    print(f"  TODAY'S TOP GAINERS  |  {date.today()}")
    print(f"{'='*70}")
    print(tabulate(display, headers="keys", tablefmt="simple", showindex=True))
    print(f"\nTotal: {len(df)} stocks\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Screen today's top NSE gainers.")
    parser.add_argument(
        "--top", type=int, default=config.TOP_N, help="Number of top gainers to show"
    )
    parser.add_argument(
        "--min-price", type=float, default=config.MIN_PRICE, help="Minimum LTP filter (₹)"
    )
    parser.add_argument(
        "--min-volume", type=int, default=config.MIN_VOLUME, help="Minimum volume filter"
    )
    parser.add_argument(
        "--exchange", default=config.EXCHANGE, choices=["NSE", "BSE"], help="Exchange"
    )
    args = parser.parse_args()

    try:
        df = get_gainers_today(
            top_n=args.top,
            min_price=args.min_price,
            min_volume=args.min_volume,
            exchange=args.exchange,
        )
        print_gainers(df)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
