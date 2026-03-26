"""
gainers_weekly.py – Screen for the top percentage gainers over the past week.

Strategy:
  For each NSE equity instrument, compare the current LTP against the closing
  price from WEEKLY_LOOKBACK_DAYS ago (config default: 7 calendar days).
  Rank by weekly change % descending.

  Historical context: Weekly momentum (5-day returns) has been shown to
  persist for 1–4 weeks in large-cap Indian equities (Jegadeesh-Titman
  short-term momentum effect), making it a useful scan for swing trades.

Usage:
  python gainers_weekly.py
  python gainers_weekly.py --top 20 --lookback 5 --min-price 100

Output:
  Table: Symbol | Name | 7d Ago Close | LTP | Weekly % | Daily % | Volume
"""

import argparse
import sys
from datetime import date

import pandas as pd
from tabulate import tabulate

import config
from kite_client import get_kite_client
from data_fetcher import (
    get_instruments,
    get_quotes,
    fetch_historical,
    trading_days_ago,
)


def get_gainers_weekly(
    top_n: int = config.TOP_N,
    lookback_days: int = config.WEEKLY_LOOKBACK_DAYS,
    min_price: float = config.MIN_PRICE,
    min_volume: int = config.MIN_VOLUME,
    exchange: str = config.EXCHANGE,
) -> pd.DataFrame:
    """
    Return the top *top_n* gainers measured over the past *lookback_days* calendar days.

    Args:
        top_n:         Number of top results.
        lookback_days: How many calendar days to look back (e.g. 7 = one week).
        min_price:     Minimum current price filter (₹).
        min_volume:    Minimum average daily volume filter.
        exchange:      'NSE' or 'BSE'.

    Returns:
        DataFrame sorted by weekly_change_pct descending.
    """
    kite = get_kite_client()
    today = date.today()
    from_date = trading_days_ago(lookback_days, today)

    print(f"[{today}] Fetching instruments from {exchange}...")
    instruments_df = get_instruments(kite, exchange)
    symbols = instruments_df["tradingsymbol"].tolist()
    token_map = dict(
        zip(instruments_df["tradingsymbol"], instruments_df["instrument_token"])
    )
    names = dict(zip(instruments_df["tradingsymbol"], instruments_df["name"]))

    print(f"  Total equity instruments: {len(symbols)}")
    print("  Fetching live quotes...")
    quotes = get_quotes(kite, symbols, exchange)

    # Build a quick LTP + volume map from quotes
    ltp_map: dict = {}
    vol_map: dict = {}
    for key, q in quotes.items():
        sym = key.split(":")[-1]
        ltp_map[sym] = q.get("last_price", 0)
        vol_map[sym] = q.get("volume", 0)

    # Filter candidates before fetching historical (saves API calls)
    candidates = [
        sym
        for sym in symbols
        if ltp_map.get(sym, 0) >= min_price and vol_map.get(sym, 0) >= min_volume
    ]
    print(f"  Candidates after filters: {len(candidates)}")
    print(f"  Fetching {lookback_days}-day historical data (one request per stock)...")

    rows = []
    for sym in candidates:
        token = token_map.get(sym)
        if token is None:
            continue

        hist = fetch_historical(kite, token, from_date, today, interval="day")
        if hist.empty or len(hist) < 2:
            continue

        close_start = hist.iloc[0]["close"]
        ltp = ltp_map[sym]
        if close_start <= 0:
            continue

        weekly_pct = ((ltp - close_start) / close_start) * 100

        # Daily change from quotes
        ohlc = quotes.get(f"{exchange}:{sym}", {}).get("ohlc", {})
        prev_close = ohlc.get("close", 0)
        daily_pct = (
            ((ltp - prev_close) / prev_close) * 100 if prev_close > 0 else 0.0
        )

        avg_volume = hist["volume"].mean()

        rows.append(
            {
                "symbol": sym,
                "name": names.get(sym, ""),
                "close_start": round(close_start, 2),
                "ltp": round(ltp, 2),
                "weekly_change_pct": round(weekly_pct, 2),
                "daily_change_pct": round(daily_pct, 2),
                "avg_volume": int(avg_volume),
                "today_volume": int(vol_map.get(sym, 0)),
            }
        )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df[df["weekly_change_pct"] > 0]
    df = df.sort_values("weekly_change_pct", ascending=False).head(top_n)
    df.reset_index(drop=True, inplace=True)
    return df


def print_weekly_gainers(df: pd.DataFrame, lookback_days: int) -> None:
    """Pretty-print the weekly gainers table."""
    if df.empty:
        print("No weekly gainers found matching the criteria.")
        return

    display = df.rename(
        columns={
            "symbol": "Symbol",
            "name": "Name",
            "close_start": f"{lookback_days}d Ago Close (₹)",
            "ltp": "LTP (₹)",
            "weekly_change_pct": f"{lookback_days}d Change %",
            "daily_change_pct": "Today %",
            "avg_volume": "Avg Volume",
            "today_volume": "Today Volume",
        }
    )
    print(f"\n{'='*70}")
    print(f"  TOP {lookback_days}-DAY GAINERS  |  {date.today()}")
    print(f"{'='*70}")
    print(tabulate(display, headers="keys", tablefmt="simple", showindex=True))
    print(f"\nTotal: {len(df)} stocks\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Screen NSE stocks for weekly (N-day) top gainers."
    )
    parser.add_argument("--top", type=int, default=config.TOP_N)
    parser.add_argument(
        "--lookback",
        type=int,
        default=config.WEEKLY_LOOKBACK_DAYS,
        help="Calendar days to look back (default: 7)",
    )
    parser.add_argument("--min-price", type=float, default=config.MIN_PRICE)
    parser.add_argument("--min-volume", type=int, default=config.MIN_VOLUME)
    parser.add_argument("--exchange", default=config.EXCHANGE, choices=["NSE", "BSE"])
    args = parser.parse_args()

    try:
        df = get_gainers_weekly(
            top_n=args.top,
            lookback_days=args.lookback,
            min_price=args.min_price,
            min_volume=args.min_volume,
            exchange=args.exchange,
        )
        print_weekly_gainers(df, args.lookback)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
