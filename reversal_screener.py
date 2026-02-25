"""
reversal_screener.py – Detect stocks reversing after a multi-day losing streak.

Strategy (Mean-Reversion Reversal):
  1. Find stocks that closed *lower* for at least REVERSAL_MIN_LOSS_DAYS consecutive
     sessions (losers streak) within the past REVERSAL_LOOKBACK_DAYS calendar days.
  2. Of those, identify ones whose *latest* close is *higher* than the previous
     session (first positive close after the streak) — the reversal candle.
  3. Extra confirmation filters (optional, all configurable):
       - RSI was oversold (< RSI_OVERSOLD) before the reversal day.
       - Volume on the reversal day ≥ VOLUME_SURGE_MULTIPLIER × 20-day avg volume.
       - Price is still above a key support level (10-day low).

  Academic basis: Overreaction / mean-reversion effect documented in Indian
  markets (Varma, 1999; Tripathy, 2009). Stocks that fell 3-5 days tend to
  recover moderately in the next 1-5 sessions.

Usage:
  python reversal_screener.py
  python reversal_screener.py --min-loss-days 4 --lookback 15 --confirm-volume

Output:
  Table: Symbol | Name | Streak Low | Reversal Close | Recovery % | RSI | Vol Surge
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
    enrich_with_indicators,
    trading_days_ago,
)


def _count_losing_streak(closes: pd.Series) -> int:
    """
    Return the length of the most recent consecutive losing-day streak
    ending at the second-to-last candle (so the last candle is the reversal).
    """
    # Work on everything except the last element (the potential reversal day)
    prior = closes.iloc[:-1].values
    streak = 0
    for i in range(len(prior) - 1, -1, -1):
        if i == 0:
            break
        if prior[i] < prior[i - 1]:
            streak += 1
        else:
            break
    return streak


def get_reversal_candidates(
    min_loss_days: int = config.REVERSAL_MIN_LOSS_DAYS,
    lookback_days: int = config.REVERSAL_LOOKBACK_DAYS,
    confirm_volume: bool = False,
    confirm_rsi: bool = False,
    top_n: int = config.TOP_N,
    min_price: float = config.MIN_PRICE,
    min_volume: int = config.MIN_VOLUME,
    exchange: str = config.EXCHANGE,
) -> pd.DataFrame:
    """
    Screen for stocks reversing after a consecutive-loss streak.

    Args:
        min_loss_days:  Minimum number of consecutive down-closes before reversal.
        lookback_days:  Calendar days of history to fetch.
        confirm_volume: If True, require volume surge on the reversal day.
        confirm_rsi:    If True, require RSI was oversold before the reversal.
        top_n:          Maximum results to return.
        min_price:      Minimum price filter (₹).
        min_volume:     Minimum average daily volume filter.
        exchange:       'NSE' or 'BSE'.

    Returns:
        DataFrame of reversal candidates sorted by streak_length descending.
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
    print("  Fetching live quotes for pre-filtering...")
    quotes = get_quotes(kite, symbols, exchange)

    ltp_map = {k.split(":")[-1]: v.get("last_price", 0) for k, v in quotes.items()}
    vol_map = {k.split(":")[-1]: v.get("volume", 0) for k, v in quotes.items()}

    candidates = [
        sym
        for sym in symbols
        if ltp_map.get(sym, 0) >= min_price and vol_map.get(sym, 0) >= min_volume
    ]
    print(f"  Candidates after price/volume filter: {len(candidates)}")
    print(f"  Scanning {lookback_days}-day history for reversal patterns...")

    rows = []
    for sym in candidates:
        token = token_map.get(sym)
        if token is None:
            continue

        hist = fetch_historical(kite, token, from_date, today, interval="day")
        if hist.empty or len(hist) < min_loss_days + 2:
            continue

        hist = enrich_with_indicators(hist)
        closes = hist["close"].reset_index(drop=True)
        volumes = hist["volume"].reset_index(drop=True)
        rsi_series = hist["rsi"].reset_index(drop=True)
        vol_avg = hist["vol_avg20"].reset_index(drop=True)

        streak = _count_losing_streak(closes)
        if streak < min_loss_days:
            continue

        # The last candle must be UP (reversal)
        if closes.iloc[-1] <= closes.iloc[-2]:
            continue

        # RSI confirmation: RSI at the bottom of the streak was oversold
        rsi_at_bottom = rsi_series.iloc[-2]
        if confirm_rsi and (pd.isna(rsi_at_bottom) or rsi_at_bottom > config.RSI_OVERSOLD):
            continue

        # Volume confirmation: today's volume ≥ surge multiplier × 20-day avg
        today_vol = volumes.iloc[-1]
        avg_vol = vol_avg.iloc[-2]
        vol_surge_ratio = (today_vol / avg_vol) if (avg_vol and avg_vol > 0) else 0
        if confirm_volume and vol_surge_ratio < config.VOLUME_SURGE_MULTIPLIER:
            continue

        streak_low = closes.iloc[-2]  # close just before the reversal candle
        reversal_close = closes.iloc[-1]
        recovery_pct = ((reversal_close - streak_low) / streak_low) * 100

        rows.append(
            {
                "symbol": sym,
                "name": names.get(sym, ""),
                "streak_length": streak,
                "streak_low": round(streak_low, 2),
                "reversal_close": round(reversal_close, 2),
                "recovery_pct": round(recovery_pct, 2),
                "rsi_at_bottom": round(rsi_at_bottom, 1) if not pd.isna(rsi_at_bottom) else None,
                "vol_surge_ratio": round(vol_surge_ratio, 2),
            }
        )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.sort_values(
        ["streak_length", "recovery_pct"], ascending=[False, False]
    ).head(top_n)
    df.reset_index(drop=True, inplace=True)
    return df


def print_reversals(df: pd.DataFrame, min_loss_days: int) -> None:
    """Pretty-print the reversal candidates table."""
    if df.empty:
        print("No reversal candidates found matching the criteria.")
        return

    display = df.rename(
        columns={
            "symbol": "Symbol",
            "name": "Name",
            "streak_length": "Losing Streak",
            "streak_low": "Streak Low (₹)",
            "reversal_close": "Reversal Close (₹)",
            "recovery_pct": "Recovery %",
            "rsi_at_bottom": "RSI (Bottom)",
            "vol_surge_ratio": "Vol Surge ×",
        }
    )
    print(f"\n{'='*70}")
    print(
        f"  REVERSAL CANDIDATES (≥{min_loss_days} consecutive losses)  |  {date.today()}"
    )
    print(f"{'='*70}")
    print(tabulate(display, headers="keys", tablefmt="simple", showindex=True))
    print(f"\nTotal: {len(df)} stocks\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Screen for stocks reversing after a multi-day losing streak."
    )
    parser.add_argument(
        "--min-loss-days",
        type=int,
        default=config.REVERSAL_MIN_LOSS_DAYS,
        help=f"Min consecutive losing days (default: {config.REVERSAL_MIN_LOSS_DAYS})",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=config.REVERSAL_LOOKBACK_DAYS,
        help=f"Calendar days of history to scan (default: {config.REVERSAL_LOOKBACK_DAYS})",
    )
    parser.add_argument(
        "--confirm-volume",
        action="store_true",
        help="Require volume surge on the reversal day",
    )
    parser.add_argument(
        "--confirm-rsi",
        action="store_true",
        help="Require RSI was oversold before the reversal",
    )
    parser.add_argument("--top", type=int, default=config.TOP_N)
    parser.add_argument("--min-price", type=float, default=config.MIN_PRICE)
    parser.add_argument("--min-volume", type=int, default=config.MIN_VOLUME)
    parser.add_argument("--exchange", default=config.EXCHANGE, choices=["NSE", "BSE"])
    args = parser.parse_args()

    try:
        df = get_reversal_candidates(
            min_loss_days=args.min_loss_days,
            lookback_days=args.lookback,
            confirm_volume=args.confirm_volume,
            confirm_rsi=args.confirm_rsi,
            top_n=args.top,
            min_price=args.min_price,
            min_volume=args.min_volume,
            exchange=args.exchange,
        )
        print_reversals(df, args.min_loss_days)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
